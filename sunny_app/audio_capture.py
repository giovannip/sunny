from __future__ import annotations

from typing import List

import numpy as np
import sounddevice as sd

from sunny_app.config import AudioConfig


def _rms_mono(chunk: np.ndarray) -> float:
    if chunk.size == 0:
        return 0.0
    x = chunk.astype(np.float64, copy=False)
    return float(np.sqrt(np.mean(x * x)))


def record_phrase(device: int | None, cfg: AudioConfig) -> np.ndarray:
    """Record a single spoken phrase after noise calibration; returns float32 mono."""
    chunk_samples = max(1, int(cfg.sample_rate * cfg.chunk_ms / 1000.0))
    calib_seconds = 0.5
    calib_chunks = max(1, int(calib_seconds * 1000.0 / cfg.chunk_ms))

    noise_rms_vals: List[float] = []

    def noise_floor() -> float:
        if not noise_rms_vals:
            return cfg.min_abs_threshold
        return float(np.mean(noise_rms_vals))

    def threshold() -> float:
        return max(cfg.min_abs_threshold, noise_floor() * cfg.energy_factor)

    recorded: List[np.ndarray] = []

    with sd.InputStream(
        device=device,
        channels=1,
        dtype="float32",
        samplerate=cfg.sample_rate,
        blocksize=chunk_samples,
    ) as stream:
        # Calibrate noise (~0.5s)
        for _ in range(calib_chunks):
            chunk, _ = stream.read(chunk_samples)
            chunk = np.asarray(chunk).reshape(-1)
            noise_rms_vals.append(_rms_mono(chunk))

        thr = threshold()
        # Wait for speech onset (bounded — otherwise we block forever in silence)
        max_wait_chunks = max(
            1, int(cfg.max_wait_for_speech_sec * 1000.0 / float(cfg.chunk_ms))
        )
        for _ in range(max_wait_chunks):
            chunk, _ = stream.read(chunk_samples)
            chunk = np.asarray(chunk).reshape(-1)
            if _rms_mono(chunk) > thr:
                recorded.append(chunk.copy())
                break
        else:
            return np.zeros(0, dtype=np.float32)

        silent = 0
        total_samples = chunk_samples
        max_samples = int(cfg.max_seconds * cfg.sample_rate)

        while True:
            if total_samples >= max_samples:
                break
            chunk, _ = stream.read(chunk_samples)
            chunk = np.asarray(chunk).reshape(-1)
            recorded.append(chunk.copy())
            total_samples += chunk_samples
            if _rms_mono(chunk) <= thr:
                silent += 1
                if silent >= cfg.silence_chunks:
                    break
            else:
                silent = 0

    if not recorded:
        return np.zeros(0, dtype=np.float32)
    return np.concatenate(recorded, axis=0).astype(np.float32)
