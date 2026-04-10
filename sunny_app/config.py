from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import yaml


@dataclass
class AudioConfig:
    sample_rate: int = 16000
    # Blocos maiores (~100 ms) + pré-roll estáveis como no demo speech_recon.
    chunk_ms: int = 100
    silence_chunks: int = 10
    max_seconds: float = 30.0
    # Stop waiting for first speech after this many seconds (avoids infinite silence).
    max_wait_for_speech_sec: float = 120.0
    energy_factor: float = 1.75
    min_abs_threshold: float = 0.004
    # Inclui áudio antes de cruzar o limiar (evita cortar a primeira sílaba).
    preroll_chunks: int = 5
    input_device: Optional[int] = None


@dataclass
class SttConfig:
    whisper_model: str = "base"
    # cpu = sem CUDA (evita erro cublas64_*.dll se a GPU/CUDA não estiverem corretas). Use cuda se tiveres drivers NVIDIA.
    device: str = "cpu"
    compute_type: str = "default"
    language: Optional[str] = None
    # Com segmentação por silêncio na captura, VAD interno costuma piorar (igual ao demo).
    vad_filter: bool = False
    beam_size: int = 10
    patience: float = 1.1
    best_of: int = 5
    repetition_penalty: float = 1.05
    no_repeat_ngram_size: int = 0
    condition_on_previous_text: bool = False
    # null = texto padrão pt-BR (demo speech_recon)
    initial_prompt: Optional[str] = None
    # null = lista curta pt-BR para viés léxico (faster-whisper)
    hotwords: Optional[str] = None


@dataclass
class LlmConfig:
    # ollama | openai_compatible (API /v1/chat/completions)
    provider: str = "ollama"
    model: str = "sunny"
    # Ollama: host opcional, ex. http://127.0.0.1:11434 (null = cliente padrão / OLLAMA_HOST).
    # openai_compatible: URL base obrigatória, ex. https://api.openai.com/v1 ou http://localhost:11434/v1
    api_base: Optional[str] = None
    # Só para openai_compatible; se vazio, usa env OPENAI_API_KEY
    api_key: Optional[str] = None
    # Opcional: mensagem de sistema em cada pedido (além do que o modelo já traz no template).
    system_prompt: Optional[str] = None


@dataclass
class TtsConfig:
    elevenlabs_api_key: str = ""
    voice_id: str = ""
    model_id: str = "eleven_multilingual_v2"
    output_format: str = "mp3_44100_128"


@dataclass
class VTubeConfig:
    enabled: bool = False
    ws_url: str = "ws://127.0.0.1:8001"
    plugin_name: str = ""
    plugin_developer: str = "SunnyApp"
    auth_token: str = ""
    hotkey_talking_id: str = ""
    # Lista de hotkeys: um é escolhido aleatoriamente a cada disparo durante a fala (vazio = usa demo ou hotkey_talking_id)
    talking_hotkey_ids: list[str] = field(default_factory=list)
    hotkey_idle_id: str = ""
    # Re-disparar com esta cadência (valores menores = mais troca de pose)
    talking_trigger_interval_sec: float = 0.45
    # ID do parâmetro de boca no VTube Studio (ex. UUID em Model → Parameters). Se preenchido, injeta abertura durante o áudio (boca “mexe”).
    mouth_parameter_id: Optional[str] = None
    mouth_jitter_interval_sec: float = 0.18


@dataclass
class PlaybackConfig:
    prefer_ffplay: bool = False
    # Velocidade de reprodução do MP3 (1.0 = normal). Requer ffplay ou mpv no PATH se ≠ 1.
    playback_speed: float = 1.35


@dataclass
class AppConfig:
    audio: AudioConfig = field(default_factory=AudioConfig)
    stt: SttConfig = field(default_factory=SttConfig)
    llm: LlmConfig = field(default_factory=LlmConfig)
    tts: TtsConfig = field(default_factory=TtsConfig)
    vtube: VTubeConfig = field(default_factory=VTubeConfig)
    playback: PlaybackConfig = field(default_factory=PlaybackConfig)


def _merge_dataclass(cls: type, data: dict[str, Any]) -> Any:
    from dataclasses import asdict, fields

    base = asdict(cls())
    merged = {**base, **(data or {})}
    field_names = {f.name for f in fields(cls)}
    kwargs = {k: merged[k] for k in field_names if k in merged}
    return cls(**kwargs)


def load_config(path: Optional[Path] = None) -> AppConfig:
    if path is None:
        env = os.environ.get("SUNNY_CONFIG")
        if env:
            path = Path(env)
        else:
            path = Path.cwd() / "config.yaml"
    if not path.is_file():
        raise FileNotFoundError(
            f"Config not found: {path.resolve()}\n"
            "Copy sunny_app/config.example.yaml to config.yaml and fill in keys."
        )
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise ValueError("config.yaml must be a mapping at the root")

    audio = _merge_dataclass(AudioConfig, raw.get("audio") or {})
    stt = _merge_dataclass(SttConfig, raw.get("stt") or {})
    llm_raw = dict(raw.get("llm") or {})
    if "model" not in llm_raw and "ollama_model" in llm_raw:
        llm_raw["model"] = llm_raw.get("ollama_model")
    if "api_base" not in llm_raw and "ollama_host" in llm_raw:
        llm_raw["api_base"] = llm_raw.get("ollama_host")
    for _obsolete in (
        "sync_modelfile_on_startup",
        "ollama_modelfile",
        "ollama_model",
        "ollama_host",
    ):
        llm_raw.pop(_obsolete, None)
    llm = _merge_dataclass(LlmConfig, llm_raw)
    tts = _merge_dataclass(TtsConfig, raw.get("tts") or {})
    vtube = _merge_dataclass(VTubeConfig, raw.get("vtube") or {})
    if vtube.talking_hotkey_ids is None:
        vtube.talking_hotkey_ids = []
    playback = _merge_dataclass(PlaybackConfig, raw.get("playback") or {})

    cfg = AppConfig(
        audio=audio,
        stt=stt,
        llm=llm,
        tts=tts,
        vtube=vtube,
        playback=playback,
    )
    _validate_config(cfg)
    return cfg


def _validate_config(cfg: AppConfig) -> None:
    if not (cfg.tts.elevenlabs_api_key or "").strip():
        raise ValueError("tts.elevenlabs_api_key is required")
    if not (cfg.tts.voice_id or "").strip():
        raise ValueError("tts.voice_id is required")
    if cfg.vtube.enabled:
        if not (cfg.vtube.auth_token or "").strip():
            raise ValueError("vtube.auth_token is required when vtube.enabled is true")
        if not (cfg.vtube.plugin_name or "").strip():
            raise ValueError("vtube.plugin_name is required when vtube.enabled is true")
