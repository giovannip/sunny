from __future__ import annotations

import numpy as np
from faster_whisper import WhisperModel

from sunny_app.config import SttConfig


class WhisperSTT:
    def __init__(self, cfg: SttConfig) -> None:
        self._cfg = cfg
        print(
            f"Carregando Whisper (modelo «{cfg.whisper_model}», device={cfg.device}, "
            f"compute={cfg.compute_type})… "
            "Na primeira vez o download pode demorar vários minutos.",
            flush=True,
        )
        self._model = WhisperModel(
            cfg.whisper_model,
            device=cfg.device,
            compute_type=cfg.compute_type,
        )
        print("Whisper pronto.", flush=True)

    def transcribe(self, audio_np: np.ndarray, sampling_rate: int = 16000) -> str:
        if audio_np.size == 0:
            return ""
        # faster-whisper: numpy mono float32 a 16 kHz (sem parâmetro sampling_rate na API atual).
        x = audio_np.astype(np.float64, copy=False).reshape(-1)
        target_sr = 16000
        if sampling_rate != target_sr:
            n_out = max(1, round(len(x) * target_sr / float(sampling_rate)))
            old_idx = np.arange(len(x), dtype=np.float64)
            new_idx = np.linspace(0.0, len(x) - 1, n_out)
            x = np.interp(new_idx, old_idx, x).astype(np.float32)
        else:
            x = x.astype(np.float32)

        kwargs = {
            "beam_size": self._cfg.beam_size,
            "vad_filter": self._cfg.vad_filter,
        }
        if self._cfg.language:
            kwargs["language"] = self._cfg.language
        if self._cfg.initial_prompt:
            kwargs["initial_prompt"] = self._cfg.initial_prompt

        segments, _info = self._model.transcribe(x, **kwargs)
        parts = [s.text for s in segments]
        return " ".join(p.strip() for p in parts if p.strip()).strip()
