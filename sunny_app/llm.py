"""Geração de respostas por LLM: backend escolhido via `LlmConfig.provider`."""
import ollama
from typing import Any

from sunny_app.config import LlmConfig

_message_history: list[dict[str, str]] = []

def generate_reply(cfg: LlmConfig, user_text: str) -> str:
    print(f"🤖 Generating reply for: {user_text}")

    _message_history.append({"role": "user", "content": user_text})
    kwargs: dict[str, Any] = {"model": cfg.model, "messages": _message_history}
    if (cfg.api_base or "").strip():
        kwargs["host"] = cfg.api_base.strip()
    _response = ollama.chat(**kwargs)

    _llm_reply = _response["message"]["content"]
    print(f"🤖 LLM reply (raw): {_llm_reply}")

    _message_history.append({"role": "assistant", "content": _llm_reply})
    return _llm_reply
