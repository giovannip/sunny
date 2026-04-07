from __future__ import annotations

from typing import Iterable

from sunny_app.config import TtsConfig


def _iter_to_bytes(stream: Iterable[bytes] | bytes) -> bytes:
    if isinstance(stream, (bytes, bytearray)):
        return bytes(stream)
    parts: list[bytes] = []
    for chunk in stream:
        if isinstance(chunk, bytes):
            parts.append(chunk)
        elif isinstance(chunk, bytearray):
            parts.append(bytes(chunk))
        else:
            parts.append(bytes(chunk))
    return b"".join(parts)


def synthesize(cfg: TtsConfig, text: str) -> bytes:
    from elevenlabs import ElevenLabs

    client = ElevenLabs(api_key=cfg.elevenlabs_api_key.strip())
    stream = client.text_to_speech.convert(
        voice_id=cfg.voice_id.strip(),
        text=text,
        model_id=cfg.model_id,
        output_format=cfg.output_format,
    )
    return _iter_to_bytes(stream)
