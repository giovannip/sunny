from __future__ import annotations

import argparse
import json
import sys
import tempfile
import traceback
from pathlib import Path

from sunny_app.audio_capture import record_phrase
from sunny_app.config import AppConfig, load_config

from sunny_app.llm import generate_reply
from sunny_app.playback import play_mp3_file
from sunny_app.stt import WhisperSTT
from sunny_app.tts import synthesize

from sunny_app.vtube_client import VTubeClient

# Hotkey "Remove Expressions" — limpa expressões antes de aplicar as do JSON.
_VTUBE_REMOVE_EXPRESSIONS_HOTKEY_ID = "9b01a4b29d1247aaa165c6c7232a436a"

def _print_capture_report(diag: dict) -> None:
    if diag.get("timeout_wait"):
        return
    print(
        f"  Captura: {diag['duration_sec']:.2f}s | "
        f"pico RMS {diag['peak_rms']:.5f} | limiar {diag['threshold']:.5f} | "
        f"pico onda {diag['peak_abs']:.4f}",
        flush=True,
    )
    if not diag.get("saw_above_threshold"):
        print(
            "  Aviso: nenhum trecho passou do limiar; o áudio pode estar muito baixo.",
            flush=True,
        )
    elif diag["peak_abs"] < 0.02:
        print(
            "  Aviso: sinal baixo — suba o ganho do microfone ou aproxime-se.",
            flush=True,
        )

# Pedido ao arrancar (uma vez por sessão). Frases neutras para não disparar recusa de segurança do modelo.
INTRO_PROMPT = (
    "Se apresente (Não precisa mencionar caracteristicas fisicas, pois estou te vendo no VTube Studio)"
    "conte uma curiosidade engraçada inventada (preferencialmente absurada) sobre vc"
    "[respostas CURTAS, apenas uma frase]"
    "Responda APENAS com o objeto JSON (expressions, annimation, message) conforme as regras do sistema."
)

def _deliver_speech(
    cfg: AppConfig,
    vtube: VTubeClient | None,
    reply: str,
) -> None:
    """JSON do LLM: remove expressões (paralelo ao TTS), aplica expressões, animação em loop no áudio."""

    print(f"_deliver_speech: reply: {reply}", flush=True)

    reply_obj = None
    # Parse reply from JSON
    try:
        reply_obj = json.loads(reply)
    except Exception as e:
        print(f"Erro ao decodificar resposta do modelo: {e}\nResposta recebida: {reply!r}", flush=True)
        return

    expression_hotkeys = reply_obj.get("expressions", [])
    animation_hotkey = reply_obj.get("annimation", None)
    message = reply_obj.get("message", "")

    print(f"_deliver_speech: expression_hotkeys: {expression_hotkeys}", flush=True)
    print(f"_deliver_speech: animation_hotkey: {animation_hotkey}", flush=True)
    print(f"_deliver_speech: message: {message}", flush=True)

    tts_text = message.strip()
    if not tts_text:
        print(
            "Aviso: campo message vazio ou resposta não-JSON — nada a falar. "
            "Confira se o modelo devolve JSON válido com message.",
            flush=True,
        )
        return

    print(f"🤖 {tts_text}", flush=True)

    mp3_bytes = synthesize(cfg.tts, tts_text)
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
        tmp.write(mp3_bytes)
        tmp_path = Path(tmp.name)

    if vtube is not None:
        print(f"🤖 remove expressions: {_VTUBE_REMOVE_EXPRESSIONS_HOTKEY_ID}", flush=True)
        vtube.trigger_hotkey(_VTUBE_REMOVE_EXPRESSIONS_HOTKEY_ID)

        for hid in expression_hotkeys:
            print(f"🤖 expression hotkey: {hid}", flush=True)
            vtube.trigger_hotkey(hid)

        if animation_hotkey:
            print(f"🤖 animation hotkey: {animation_hotkey}", flush=True)
            vtube.trigger_hotkey(animation_hotkey)

    try:
        play_mp3_file(
            tmp_path,
            cfg.playback.prefer_ffplay,
            cfg.playback.playback_speed,
        )
    except Exception as e:
        print(f"🤖_deliver_speech: error: {e}", flush=True)
    finally:
        print(f"🤖_deliver_speech: finally", flush=True)
        vtube.trigger_hotkey(_VTUBE_REMOVE_EXPRESSIONS_HOTKEY_ID)
        try:
            print(f"🤖_deliver_speech: unlinking tmp_path: {tmp_path}", flush=True)
            tmp_path.unlink(missing_ok=True)
        except OSError:
            print(f"🤖_deliver_speech: error: {e}", flush=True)
            pass


def main() -> None:
    parser = argparse.ArgumentParser(description="Sunny VTuber voice loop")
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Path to config YAML (default: cwd/config.yaml or SUNNY_CONFIG)",
    )
    args = parser.parse_args()

    print("Sunny — carregando configuração…", flush=True)
    cfg = load_config(args.config)

    mic = cfg.audio.input_device
    mic_note = f"microfone [{mic}]" if mic is not None else "microfone (dispositivo padrão)"
    print(
        f"  OK — LLM ({cfg.llm.provider}): «{cfg.llm.model}», {mic_note}",
        flush=True,
    )

    stt = WhisperSTT(cfg.stt)
    vtube: VTubeClient | None = None
    if cfg.vtube.enabled:
        print("Conectando ao VTube Studio…", flush=True)
        vtube = VTubeClient(cfg.vtube)
        vtube.connect()
        print("  VTube Studio conectado.", flush=True)
        print(
            "  VTube: JSON com expressions + annimation (loop na fala) + message; "
            "remove expressões e TTS em paralelo antes de aplicar expressões.",
            flush=True,
        )

    print("\nApresentação automática (nome + curiosidade)…", flush=True)
    try:
        intro_reply = generate_reply(cfg.llm, INTRO_PROMPT)
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
            audio, cap_diag = record_phrase(cfg.audio.input_device, cfg.audio)
            if audio.size == 0:
                print(
                    "Sem áudio: passou o tempo esperando fala ou o nível ficou "
                    "sempre abaixo do limiar. Aumente o ganho do microfone, confira "
                    "`audio.input_device`, ou reduza `min_abs_threshold` / "
                    "`energy_factor`; `preroll_chunks` e `chunk_ms` (como no demo "
                    "speech_recon) ajudam a não cortar o início da frase.\n",
                    flush=True,
                )
                continue
            _print_capture_report(cap_diag)
            print("Transcrevendo…", flush=True)
            user_text = stt.transcribe(audio, sampling_rate=cfg.audio.sample_rate)
            if not user_text.strip():
                print("(Transcrição vazia — tente de novo.)\n", flush=True)
                continue

            print(f"Você: {user_text}")
            reply = generate_reply(
                cfg.llm,
                user_text
                + "[respostas CURTAS, apenas uma frase]"
                + " Responda APENAS JSON: expressions, annimation, message.",
            )
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
