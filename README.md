# VTuber AI — Starter Project

A Python project that implements a virtual assistant named **Sunny**, designed to interact with you through voice conversation.

## What it includes

- **Speech recognition**
- **LLM responses**
- **Text-to-speech**
- **Avatar animation triggers**

## Sunny app (`sunny_app/`)

End-to-end loop: microphone → [Faster Whisper](https://github.com/SYSTRAN/faster-whisper) → LLM (`llm.provider`: default [Ollama](https://ollama.com), or any OpenAI-compatible `/v1/chat/completions` API) → [ElevenLabs](https://elevenlabs.io) → MP3 playback, with optional VTube Studio hotkeys while audio plays.

### Prerequisites

Install dependencies from the repository root:

```bash
py -m pip install -r requirements-sunny.txt
```

### Configuration

1. Copy [`sunny_app/config.example.yaml`](sunny_app/config.example.yaml) to **`config.yaml` at the repository root**.
2. Fill in `tts.elevenlabs_api_key`, `tts.voice_id`, and (if you use the avatar) set `vtube.enabled: true` with `plugin_name`, `auth_token`, and hotkey IDs.

`config.yaml` is listed in `.gitignore` so secrets stay local.

Do not put real API keys, VTube tokens, or personal file paths in this repository or in copies of these docs you publish (issues, gists, etc.). The YAML keys named above are configuration field names only, not secret values.

### LLM backend and the Sunny model (Ollama)

The persona template for the default Ollama flow lives in [`sunny_app/sunny.modelfile`](sunny_app/sunny.modelfile). After you edit it, recreate the local model yourself, for example:

```bash
ollama pull <base-from-FROM-line>
ollama create sunny -f sunny_app/sunny.modelfile
```

Use `llm.provider: ollama`, `llm.model: sunny` (or whatever name you passed to `ollama create`), and optional `llm.api_base` if Ollama is not on the default host.

For other APIs, set `llm.provider: openai_compatible`, `llm.api_base` (e.g. `https://api.openai.com/v1` or Ollama’s OpenAI endpoint `http://localhost:11434/v1`), `llm.model`, and `llm.api_key` (or `OPENAI_API_KEY`).

### Services

- **LLM**: with `provider: ollama`, Ollama must be running and the name in `llm.model` must exist. Optional `llm.system_prompt` adds an extra system message on every request.
- If `vtube.enabled` is true, open **VTube Studio** with the WebSocket API enabled.

### Run

From the repository root:

```bash
py -m sunny_app.main
```

Alternate config path:

```bash
set SUNNY_CONFIG=C:\path\to\config.yaml
py -m sunny_app.main
```

Or:

```bash
py -m sunny_app.main --config C:\path\to\config.yaml
```

On Unix-like systems, use `export SUNNY_CONFIG=/path/to/config.yaml` instead of `set`.

### Audio playback

On **Windows**, playback uses **MCI** by default (`playback.prefer_ffplay: false`). On other platforms, install **`ffplay`** (FFmpeg) or **`mpv`** for blocking playback until the file finishes.

