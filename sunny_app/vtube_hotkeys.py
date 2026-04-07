"""Hotkeys de exemplo (demo/vtube) — movimentos variados durante a fala."""

from __future__ import annotations

from sunny_app.config import VTubeConfig

# Mesmos UUIDs do demo/vtube/vtube_demo.py (exceto "Remove Expressions", reservado para idle).
DEMO_TALKING_HOTKEY_IDS: list[str] = [
    "71be07c2837d452d9b45922f01fe662e",  # Heart Eyes
    "3491e43df9e74db4b39a1825a1629c92",  # Eyes Cry
    "308daf8b71eb4b8eacb92c5169d58175",  # Angry Sign
    "6f0db717502847cca5c0f054bd8b8341",  # Shock Sign
    "aa6b89d333b247e4866b3d960d2d108c",  # Anim Shake
    "57c37fe88bab489bae9915571edf2359",  # (sem nome)
]


def effective_talking_hotkeys(cfg: VTubeConfig) -> list[str]:
    """Lista usada durante o áudio: talking_hotkey_ids > hotkey_talking_id único > IDs do demo."""
    raw = cfg.talking_hotkey_ids or []
    cleaned = [x.strip() for x in raw if isinstance(x, str) and x.strip()]
    if cleaned:
        return cleaned
    single = (cfg.hotkey_talking_id or "").strip()
    if single:
        return [single]
    return list(DEMO_TALKING_HOTKEY_IDS)
