from __future__ import annotations

import argparse
import os
import ollama
import re
import sys
import tempfile
import threading
import traceback
from pathlib import Path

from sunny_app.config import LlmConfig

from sunny_app.audio_capture import record_phrase
from sunny_app.config import AppConfig, load_config

from sunny_app.ollama_sync import sync_ollama_model
from sunny_app.playback import play_mp3_file
from sunny_app.stt import WhisperSTT
from sunny_app.tts import synthesize
from sunny_app.vtube_client import VTubeClient

_VTUBE_HOTKEY_32 = re.compile(r"^[0-9a-fA-F]{32}$")
_VTUBE_HOTKEY_UUID = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)
# Zero-width / BOM que alguns modelos colocam após "|" e deixam TTS/terminal "vazios".
_INVISIBLE_TAIL_CHARS = "\u200b\u200c\u200d\u2060\ufeff"

message_history = []

def generate_reply(cfg: LlmConfig, user_text: str) -> str:
    print(f"🤖 Generating reply for: {user_text}")


    message_history.append({'role': 'user', 'content': user_text})

    # 3. Envia o histórico COMPLETO para o Ollama
    response = ollama.chat(model=cfg.ollama_model, messages=message_history)

    # 4. Pega a resposta do modelo
    llm_reply = response['message']['content']
    print(f"🤖 LLM reply: {llm_reply}")

    # 5. Faz o APPEND da resposta da IA no histórico para a próxima rodada
    message_history.append({'role': 'assistant', 'content': llm_reply})

    print(f"🤖 LLM reply: {llm_reply}")
    return llm_reply

def _is_vtube_hotkey_id(s: str) -> bool:
    t = s.strip()
    return bool(_VTUBE_HOTKEY_32.match(t) or _VTUBE_HOTKEY_UUID.match(t))


def _normalize_hotkey_head(head: str) -> str:
    """Aceita ids como no modelfile ou com colchetes literais «<uuid>»."""
    t = head.strip().strip("<>").strip()
    return t


def _normalize_speech_tail(tail: str) -> str:
    t = tail.strip()
    for ch in _INVISIBLE_TAIL_CHARS:
        t = t.replace(ch, "")
    return t.strip()


def _split_llm_reply(reply: str) -> tuple[str, str | None]:
    """Se `hotkeyId|texto` com id VTube válido, retorna (texto para TTS, hotkey). Caso contrário (reply inteiro, None)."""
    raw = (reply or "").strip()
    if "|" not in raw:
        return raw, None
    head, _, tail = raw.partition("|")
    head = _normalize_hotkey_head(head)
    tail = _normalize_speech_tail(tail)
    if not tail or not _is_vtube_hotkey_id(head):
        return raw, None
    return tail, head


def _speech_for_display(reply: str) -> str:
    """Texto legível para o terminal (mesmo que o TTS quando o parse é válido)."""
    tts, _ = _split_llm_reply(reply)
    if tts:
        return tts
    r = (reply or "").strip()
    return r if r else "(sem texto — o modelo não devolveu texto falável)"

# Pedido ao arrancar (uma vez por sessão). Frases neutras para não disparar recusa de segurança do modelo.
INTRO_PROMPT = (
    "Se apresente (Não precisa mencionar caracteristicas fisicas, pois estou te vendo no VTube Studio)"
    "conte uma curiosidade engraçada inventada (preferencialmente absurada) sobre vc"
    "[respostas CURTAS, apenas uma frase]"
)

def _deliver_speech(
    cfg: AppConfig,
    vtube: VTubeClient | None,
    reply: str,
) -> None:
    """TTS, reprodução e hotkey VTube (pose do LLM em loop durante o áudio quando id|texto)."""
    tts_text, llm_hotkey = _split_llm_reply(reply)

    mp3_bytes = synthesize(cfg.tts, tts_text)
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
        tmp.write(mp3_bytes)
        tmp_path = Path(tmp.name)

    stop_event = threading.Event()
    workers: list[threading.Thread] = []

    if vtube is not None and llm_hotkey:
        vtube_client = vtube
        hotkey_id = llm_hotkey

        def _llm_hotkey_loop() -> None:
            interval = max(0.05, float(cfg.vtube.talking_trigger_interval_sec))
            while not stop_event.is_set():
                try:
                    vtube_client.trigger_hotkey(hotkey_id)
                except Exception as exc:
                    print(f"🤖 VTube hotkey (LLM): {exc}", flush=True)
                if stop_event.wait(timeout=interval):
                    break

        t = threading.Thread(target=_llm_hotkey_loop, name="vtube-llm-hotkey-loop", daemon=True)
        workers.append(t)
        t.start()

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
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass

    if vtube is not None and cfg.vtube.hotkey_idle_id:
        try:
            vtube.trigger_hotkey(cfg.vtube.hotkey_idle_id)
        except Exception as exc:
            print(f"VTube idle hotkey: {exc}")


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
        print(
            "  Poses durante a fala: hotkey escolhido pelo modelo (formato hotkeyId|texto).",
            flush=True,
        )

    print("\nApresentação automática (nome + curiosidade)…", flush=True)
    try:
        intro_reply = generate_reply(cfg.llm, INTRO_PROMPT)
        print(f"Sunny intro_reply: {_speech_for_display(intro_reply)}", flush=True)
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
            reply = generate_reply(cfg.llm, user_text + "[respostas CURTAS, apenas uma frase]")
            print(f"Sunny: {_speech_for_display(reply)}")
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
