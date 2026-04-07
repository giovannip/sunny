"""Na inicialização, garante imagem base atualizada e modelo local recriado a partir do Modelfile."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from sunny_app.config import AppConfig

_PACKAGE_DIR = Path(__file__).resolve().parent
_DEFAULT_MODELFILE = _PACKAGE_DIR / "sunny.modelfile"


def _skip_by_env() -> bool:
    v = os.environ.get("SUNNY_SKIP_OLLAMA_SYNC", "").strip().lower()
    return v in ("1", "true", "yes", "on")


def resolve_modelfile_path(cfg: AppConfig) -> Path:
    raw = (cfg.llm.ollama_modelfile or "").strip()
    if raw:
        p = Path(raw).expanduser()
        if not p.is_absolute():
            p = Path.cwd() / p
        return p.resolve()
    return _DEFAULT_MODELFILE


def parse_from_base_image(modelfile: Path) -> str:
    text = modelfile.read_text(encoding="utf-8")
    for line in text.splitlines():
        s = line.strip()
        if s.upper().startswith("FROM "):
            return s[5:].strip().strip('"').strip("'")
    return "qwen2.5:3b"


def sync_ollama_model(cfg: AppConfig) -> None:
    """`ollama pull` na base do Modelfile e `ollama create` para alinhar o modelo local ao arquivo."""
    if not cfg.llm.sync_modelfile_on_startup:
        print("Sincronização Ollama desligada (llm.sync_modelfile_on_startup: false).", flush=True)
        return
    if _skip_by_env():
        print("Sincronização Ollama ignorada (SUNNY_SKIP_OLLAMA_SYNC).", flush=True)
        return

    ollama_bin = shutil.which("ollama")
    if not ollama_bin:
        raise FileNotFoundError(
            "Comando `ollama` não encontrado no PATH. Instale o Ollama e confira se está acessível no terminal."
        )

    mf = resolve_modelfile_path(cfg)
    if not mf.is_file():
        raise FileNotFoundError(
            f"Modelfile não encontrado: {mf}\n"
            "Defina llm.ollama_modelfile no config ou mantenha sunny_app/sunny.modelfile."
        )

    if cfg.llm.ollama_host:
        os.environ["OLLAMA_HOST"] = cfg.llm.ollama_host.strip()

    base = parse_from_base_image(mf)
    model = cfg.llm.ollama_model.strip()
    if not model:
        raise ValueError("llm.ollama_model não pode ser vazio")

    print(f"Ollama: atualizando imagem base «{base}» (pull)…", flush=True)
    r_pull = subprocess.run(
        [ollama_bin, "pull", base],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if r_pull.returncode != 0:
        print(
            f"Aviso: `ollama pull {base}` saiu com código {r_pull.returncode}. "
            "Se a base já existir localmente, o create pode funcionar mesmo assim.\n"
            f"{(r_pull.stderr or r_pull.stdout or '').strip()}\n",
            flush=True,
        )
    else:
        print("  Base atualizada ou já em dia.", flush=True)

    print(f"Ollama: recriando modelo «{model}» a partir de {mf.name}…", flush=True)
    r_create = subprocess.run(
        [ollama_bin, "create", model, "-f", str(mf)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if r_create.returncode != 0:
        msg = (r_create.stderr or r_create.stdout or "").strip()
        raise RuntimeError(
            f"`ollama create {model}` falhou (código {r_create.returncode}).\n{msg}"
        )
    print("  Modelo local alinhado ao Modelfile.", flush=True)
