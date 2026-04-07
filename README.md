# VTuber AI — Starter Project

A Python project that implements a virtual assistant named **Sunny**, designed to interact with you through voice conversation.

## What it includes

- **Speech recognition**
- **LLM responses**
- **Text-to-speech**
- **Avatar animation triggers**

## Sunny app (`sunny_app/`)

End-to-end loop: microphone → [Faster Whisper](https://github.com/SYSTRAN/faster-whisper) → [Ollama](https://ollama.com) → [ElevenLabs](https://elevenlabs.io) → MP3 playback, with optional VTube Studio hotkeys while audio plays.

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

### Ollama and the Sunny model

The model is defined in [`sunny_app/sunny.modelfile`](sunny_app/sunny.modelfile).

With `llm.sync_modelfile_on_startup: true` (default), starting the app runs `ollama pull` on the `FROM` image and `ollama create` so the model named in `llm.ollama_model` matches the Modelfile.

To skip sync (faster startup):

- Set `llm.sync_modelfile_on_startup: false`, or  
- Set environment variable `SUNNY_SKIP_OLLAMA_SYNC=1`, or  
- Pass `--skip-ollama-sync`.

### Services

- **Ollama** must be running with the model configured in `llm.ollama_model` (e.g. `sunny`). Runtime personality comes from `llm.system_prompt`: `null` uses the built-in default; override it in YAML if you want.
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

### Sync Ollama model manually (Modelfile update)

From a shell whose working directory is the repository root, with `config.yaml` in place:

```bash
py -c "from sunny_app.config import load_config; from sunny_app.ollama_sync import sync_ollama_model; sync_ollama_model(load_config())"
```

PowerShell example using placeholder paths only:

```powershell
Set-Location "C:\path\to\your\VTuberAI-clone"
$env:SUNNY_CONFIG = "C:\path\to\your\VTuberAI-clone\config.yaml"
py -c "from sunny_app.config import load_config; from sunny_app.ollama_sync import sync_ollama_model; sync_ollama_model(load_config())"
```
