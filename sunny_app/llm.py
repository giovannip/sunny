from ollama import chat
from ollama import ChatResponse

from sunny_app.config import LlmConfig

def generate_reply(cfg: LlmConfig, user_text: str, messages: list[dict[str, str]]) -> str:
    print(f"🤖 Generating reply for: {user_text}")
    print(f"🤖 Messages: {messages}")
    messages.append({
        'role': 'user',
        'content': user_text,
    })
    response: ChatResponse = chat(model=cfg.ollama_model, messages=messages)
    llm_reply = response['message']['content']
    print(f"🤖 LLM reply: {llm_reply}")
    return llm_reply
