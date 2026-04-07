from __future__ import annotations

import os
import re

import ollama

from sunny_app.config import LlmConfig

# Quando llm.system_prompt é null — mesmo texto do sunny.modelfile (pt-BR).
DEFAULT_SYSTEM_PROMPT = None # """ """

# Respostas curtas de recusa comuns (Llama 3.x e similares) — dispara um re-pedido mais curto.
_REFUSAL_PATTERNS = (
    r"não posso atender",
    r"não posso ajudar",
    r"não posso cumprir",
    r"não posso (?:fornecer|criar|gerar|continuar)",
    r"não estou (?:autorizado|em condições)",
    r"desculpe.{0,40}não posso",
    r"lamento.{0,40}não posso",
    r"como (?:um )?assistente (?:de )?ia",
)


def _looks_like_generic_refusal(text: str) -> bool:
    if not text or len(text) > 400:
        return False
    low = text.lower()
    for pat in _REFUSAL_PATTERNS:
        if re.search(pat, low, re.DOTALL | re.IGNORECASE):
            return True
    if "desculpe" in low and "não posso" in low and len(text) < 280:
        return True
    return False


def _system_text(cfg: LlmConfig) -> str:
    raw = cfg.system_prompt
    if raw is None:
        return DEFAULT_SYSTEM_PROMPT
    text = raw.strip()
    return text if text else DEFAULT_SYSTEM_PROMPT


def _ollama_generate(cfg: LlmConfig, system: str, prompt: str) -> str:
    if cfg.ollama_host:
        os.environ["OLLAMA_HOST"] = cfg.ollama_host
    response = ollama.generate(
        model=cfg.ollama_model,
        system=system,
        prompt=prompt,
        options={
            "num_predict": 96,
            "temperature": 0.82,
            "top_p": 0.88,
            "repeat_penalty": 1.1,
        },
    )
    text = response.get("response", "")
    if isinstance(text, str):
        return text.strip()
    return str(text).strip()


def generate_reply(cfg: LlmConfig, user_text: str) -> str:
    system = _system_text(cfg)
    out = _ollama_generate(cfg, system, user_text)

    if _looks_like_generic_refusal(out):
        retry_prompt = (
            f"{user_text}\n\n"
            ""
        )
        out = _ollama_generate(cfg, system, retry_prompt)

    return out
