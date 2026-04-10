from __future__ import annotations

from collections import deque

import numpy as np
import sounddevice as sd

from sunny_app.config import AudioConfig


def _rms_mono(chunk: np.ndarray) -> float:
    if chunk.size == 0:
        return 0.0
    x = chunk.astype(np.float64, copy=False)
    return float(np.sqrt(np.mean(x * x)) + 1e-10)


def _rec(frames: int, device: int | None, sample_rate: int) -> np.ndarray:
    return sd.rec(
        frames,
        samplerate=sample_rate,
        channels=1,
        dtype=np.float32,
        device=device,
    )


def record_phrase(device: int | None, cfg: AudioConfig) -> tuple[np.ndarray, dict]:
    """Grava uma frase após calibração de ruído; inclui pré-roll antes do limiar (demo speech_recon)."""
    sr = cfg.sample_rate
    chunk_samples = max(1, int(sr * cfg.chunk_ms / 1000.0))
    preroll_max = max(0, int(cfg.preroll_chunks))

    cal = _rec(int(0.5 * sr), device, sr)
    sd.wait()
    noise_floor = _rms_mono(cal.reshape(-1))
    threshold = max(noise_floor * cfg.energy_factor, cfg.min_abs_threshold)

    chunks: list[np.ndarray] = []
    preroll: deque[np.ndarray] | None = (
        deque(maxlen=preroll_max) if preroll_max > 0 else None
    )
    in_speech = False
    silent_run = 0
    wait_chunks = 0
    max_wait_chunks = max(1, int(cfg.max_wait_for_speech_sec * 1000.0 / float(cfg.chunk_ms)))
    peak_rms = 0.0
    saw_above_threshold = False

    while True:
        chunk = _rec(chunk_samples, device, sr)
        sd.wait()
        chunk = np.asarray(chunk).reshape(-1)
        rms = _rms_mono(chunk)
        peak_rms = max(peak_rms, rms)

        if rms > threshold:
            if not in_speech and preroll:
                chunks.extend(list(preroll))
                preroll.clear()
            in_speech = True
            silent_run = 0
            saw_above_threshold = True
        elif in_speech:
            silent_run += 1
            if silent_run >= cfg.silence_chunks:
                break
        else:
            if preroll is not None:
                preroll.append(chunk)
            wait_chunks += 1
            if wait_chunks >= max_wait_chunks:
                diag = {
                    "noise_floor": noise_floor,
                    "threshold": threshold,
                    "peak_rms": peak_rms,
                    "peak_abs": 0.0,
                    "duration_sec": 0.0,
                    "used_pad": False,
                    "saw_above_threshold": False,
                    "timeout_wait": True,
                }
                return np.zeros(0, dtype=np.float32), diag

        if in_speech:
            chunks.append(chunk)
            if len(chunks) * chunk_samples >= int(cfg.max_seconds * sr):
                break

    if not chunks:
        diag = {
            "noise_floor": noise_floor,
            "threshold": threshold,
            "peak_rms": peak_rms,
            "peak_abs": 0.0,
            "duration_sec": 0.0,
            "used_pad": False,
            "saw_above_threshold": saw_above_threshold,
            "timeout_wait": False,
        }
        return np.zeros(0, dtype=np.float32), diag

    audio = np.concatenate(chunks, axis=0).astype(np.float32)
    peak_abs = float(np.max(np.abs(audio)))
    dur_sec = len(audio) / float(sr)
    diag = {
        "noise_floor": noise_floor,
        "threshold": threshold,
        "peak_rms": peak_rms,
        "peak_abs": peak_abs,
        "duration_sec": dur_sec,
        "used_pad": False,
        "saw_above_threshold": saw_above_threshold,
        "timeout_wait": False,
    }
    return audio, diag
