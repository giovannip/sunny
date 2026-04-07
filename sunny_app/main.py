from __future__ import annotations

import argparse
import os
import random
import sys
import tempfile
import threading
import traceback
from pathlib import Path

from sunny_app.audio_capture import record_phrase
from sunny_app.config import AppConfig, load_config
from sunny_app.llm import generate_reply
from sunny_app.ollama_sync import sync_ollama_model
from sunny_app.playback import play_mp3_file
from sunny_app.stt import WhisperSTT
from sunny_app.tts import synthesize
from sunny_app.vtube_client import VTubeClient
from sunny_app.vtube_hotkeys import effective_talking_hotkeys

# Pedido ao arrancar (uma vez por sessão). Frases neutras para não disparar recusa de segurança do modelo.
INTRO_PROMPT = (
    "Apresentação de stream em UMA frase curta, em personagem: o seu nome (Sunny), vc é uma adolecente de 18 anos, mimada, sagaz, fala muito palavrão/humor adulto ok. Sem terapia."
    "uma curiosidade engraçada inventada (preferencialmente absurada) sobre vc, e um comentário sarcástico de humor negro"
    "Tom de humor desrespeitoso e sarcástico (nome Sunny, vibe de sol com veneno)"
    "Homer negro, ofensas e piadas sexuais são encorajadas."
)


def _deliver_speech(
    cfg: AppConfig,
    vtube: VTubeClient | None,
    reply: str,
) -> None:
    """TTS, reprodução e hotkeys VTube (igual a um turno do loop principal)."""
    mp3_bytes = synthesize(cfg.tts, reply)
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
        tmp.write(mp3_bytes)
        tmp_path = Path(tmp.name)

    stop_event = threading.Event()
    workers: list[threading.Thread] = []
    mouth_id = (cfg.vtube.mouth_parameter_id or "").strip()

    if vtube is not None and mouth_id:
        w_mouth = threading.Thread(
            target=_mouth_jitter_loop,
            args=(vtube, mouth_id, cfg.vtube.mouth_jitter_interval_sec, stop_event),
            daemon=True,
        )
        w_mouth.start()
        workers.append(w_mouth)

    talk_ids = effective_talking_hotkeys(cfg.vtube)
    if vtube is not None and talk_ids:
        try:
            vtube.trigger_hotkey(random.choice(talk_ids))
        except Exception as exc:
            print(f"VTube hotkey inicial: {exc}", flush=True)
        w_talk = threading.Thread(
            target=_talking_hotkey_loop,
            args=(
                vtube,
                talk_ids,
                cfg.vtube.talking_trigger_interval_sec,
                stop_event,
            ),
            daemon=True,
        )
        w_talk.start()
        workers.append(w_talk)

    try:
        play_mp3_file(
            tmp_path,
            cfg.playback.prefer_ffplay,
            cfg.playback.playback_speed,
        )
    finally:
        stop_event.set()
        for w in workers:
            w.join(timeout=10.0)
        if vtube is not None and mouth_id:
            try:
                vtube.inject_mouth_value(mouth_id, 0.0)
            except Exception:
                pass
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass

    if vtube is not None and cfg.vtube.hotkey_idle_id:
        try:
            vtube.trigger_hotkey(cfg.vtube.hotkey_idle_id)
        except Exception as exc:
            print(f"VTube idle hotkey: {exc}")


def _talking_hotkey_loop(
    client: VTubeClient,
    hotkey_ids: list[str],
    interval_sec: float,
    stop: threading.Event,
) -> None:
    if not hotkey_ids:
        return
    while not stop.is_set():
        try:
            client.trigger_hotkey(random.choice(hotkey_ids))
        except Exception as exc:
            print(f"VTube talking hotkey: {exc}", flush=True)
        if stop.wait(timeout=interval_sec):
            break


def _mouth_jitter_loop(
    client: VTubeClient,
    parameter_id: str,
    interval_sec: float,
    stop: threading.Event,
) -> None:
    """Varia a abertura da boca durante o áudio (precisa de mouth_parameter_id correto no VTube)."""
    while not stop.is_set():
        try:
            client.inject_mouth_value(parameter_id, random.uniform(0.2, 0.95))
        except Exception as exc:
            print(f"VTube boca (inject): {exc}", flush=True)
            break
        if stop.wait(timeout=interval_sec):
            break


def main() -> None:
    parser = argparse.ArgumentParser(description="Sunny VTuber voice loop")
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Path to config YAML (default: cwd/config.yaml or SUNNY_CONFIG)",
    )
    parser.add_argument(
        "--skip-ollama-sync",
        action="store_true",
        help="Não executar ollama pull/create (equivale a SUNNY_SKIP_OLLAMA_SYNC=1)",
    )
    args = parser.parse_args()
    if args.skip_ollama_sync:
        os.environ["SUNNY_SKIP_OLLAMA_SYNC"] = "1"

    print("Sunny — carregando configuração…", flush=True)
    cfg = load_config(args.config)

    sync_ollama_model(cfg)

    mic = cfg.audio.input_device
    mic_note = f"microfone [{mic}]" if mic is not None else "microfone (dispositivo padrão)"
    print(f"  OK — Ollama: «{cfg.llm.ollama_model}», {mic_note}", flush=True)

    stt = WhisperSTT(cfg.stt)
    vtube: VTubeClient | None = None
    if cfg.vtube.enabled:
        print("Conectando ao VTube Studio…", flush=True)
        vtube = VTubeClient(cfg.vtube)
        vtube.connect()
        print("  VTube Studio conectado.", flush=True)
        _pool = effective_talking_hotkeys(cfg.vtube)
        print(
            f"  Hotkeys durante fala: {len(_pool)} poses (escolha aleatória a cada disparo).",
            flush=True,
        )
        if not (cfg.vtube.mouth_parameter_id or "").strip():
            print(
                "  Opcional: vtube.mouth_parameter_id para sincronizar boca (ID do parâmetro no modelo).",
                flush=True,
            )

    print("\nApresentação automática (nome + curiosidade)…", flush=True)
    try:
        intro_reply = generate_reply(cfg.llm, INTRO_PROMPT)
        print(f"Sunny: {intro_reply}", flush=True)
        _deliver_speech(cfg, vtube, intro_reply)
    except Exception as exc:
        print(f"Aviso: apresentação inicial falhou ({exc}). O app segue em modo escuta.\n", flush=True)

    print(
        "\nModo escuta. Fale quando quiser — "
        f"até {cfg.audio.max_wait_for_speech_sec:.0f}s esperando a primeira sílaba "
        "(Ctrl+C para sair).\n",
        flush=True,
    )

    try:
        while True:
            print("Ouvindo…", flush=True)
            audio = record_phrase(cfg.audio.input_device, cfg.audio)
            if audio.size == 0:
                print(
                    "Sem áudio: passou o tempo esperando fala ou o nível ficou "
                    "sempre abaixo do limiar. Aumente o ganho do microfone ou reduza "
                    "`audio.min_abs_threshold` / `energy_factor` no config.\n",
                    flush=True,
                )
                continue
            print("Transcrevendo…", flush=True)
            user_text = stt.transcribe(audio, sampling_rate=cfg.audio.sample_rate)
            if not user_text.strip():
                print("(Transcrição vazia — tente de novo.)\n", flush=True)
                continue

            print(f"Você: {user_text}")
            reply = generate_reply(cfg.llm, user_text)
            print(f"Sunny: {reply}")
            _deliver_speech(cfg, vtube, reply)

    except KeyboardInterrupt:
        print("\nEncerrando.", flush=True)
    finally:
        if vtube is not None:
            vtube.close()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Erro: {exc}", file=sys.stderr, flush=True)
        traceback.print_exc()
        sys.exit(1)
