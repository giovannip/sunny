from __future__ import annotations

import numpy as np
from faster_whisper import WhisperModel

from sunny_app.config import SttConfig

_DEFAULT_INITIAL_PROMPT = (
    "Transcrição em português do Brasil. "
    "Exemplos: não, tá, pra, pro, cadê, cê, tô, né, hum, então, beleza."
)

_DEFAULT_HOTWORDS = (
    "não tá pra pro cadê você obrigado por favor então porque "
    "assim também só já ainda bem feito"
)


def _peak_normalize(audio: np.ndarray, target: float = 0.95) -> np.ndarray:
    peak = float(np.max(np.abs(audio)))
    if peak < 1e-8:
        return audio
    return np.clip(audio * (target / peak), -1.0, 1.0)


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
        x = audio_np.astype(np.float64, copy=False).reshape(-1)
        target_sr = 16000
        if sampling_rate != target_sr:
            n_out = max(1, round(len(x) * target_sr / float(sampling_rate)))
            old_idx = np.arange(len(x), dtype=np.float64)
            new_idx = np.linspace(0.0, len(x) - 1, n_out)
            x = np.interp(new_idx, old_idx, x).astype(np.float32)
        else:
            x = x.astype(np.float32)

        x = _peak_normalize(x)

        cfg = self._cfg
        initial_prompt = (
            cfg.initial_prompt.strip()
            if (cfg.initial_prompt or "").strip()
            else _DEFAULT_INITIAL_PROMPT
        )
        hotwords_raw = cfg.hotwords
        hotwords = (
            hotwords_raw.strip()
            if (hotwords_raw or "").strip()
            else _DEFAULT_HOTWORDS
        )

        kwargs: dict = {
            "task": "transcribe",
            "beam_size": cfg.beam_size,
            "patience": cfg.patience,
            "best_of": cfg.best_of,
            "vad_filter": cfg.vad_filter,
            "condition_on_previous_text": cfg.condition_on_previous_text,
            "repetition_penalty": cfg.repetition_penalty,
            "no_repeat_ngram_size": cfg.no_repeat_ngram_size,
            "initial_prompt": initial_prompt,
            "hotwords": hotwords,
        }
        if cfg.language:
            kwargs["language"] = cfg.language

        segments, _info = self._model.transcribe(x, **kwargs)
        parts = [s.text for s in segments]
        return " ".join(p.strip() for p in parts if p.strip()).strip()
