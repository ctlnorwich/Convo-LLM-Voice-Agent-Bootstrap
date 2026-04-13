# Conversational LLM Template (Voice First)

A Python template for digital artists to experiment with conversational LLM workflows:

- **STT**: Whisper (runs locally)
- **LLM**: Ollama by default, switchable to OpenAI, Gemini, or Anthropic
- **TTS**: Piper (local, English voice)

How it works:

1. Press Enter (or send a serial trigger) to begin recording
2. Whisper transcribes your speech
3. The LLM generates a response
4. Piper speaks the response aloud

**To use:** edit `config.json`, then run `uv run main.py`. That's it.

When using Ollama the script starts the Ollama server automatically, checks that
the model you specified in `config.json` is downloaded (and pulls it if not), and
shuts the server down cleanly when you exit.

---

## 1) Quick Start — macOS

### Install system dependencies

```bash
brew install portaudio ffmpeg ollama
```

- `portaudio` — used by sounddevice for microphone capture
- `ollama` — runs local LLM models
- Piper TTS is a Python dependency, no separate install needed

### Install Python dependencies

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
uv python install 3.11
uv venv --python 3.11
source .venv/bin/activate
uv sync
```

### Download a Piper English voice

```bash
mkdir -p voices
curl -L -o voices/en_US-lessac-medium.onnx \
  https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx
curl -L -o voices/en_US-lessac-medium.onnx.json \
  https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx.json
```

### Configure and run

Edit `config.json` to set your model and preambles, then:

```bash
uv run main.py
```

The script starts Ollama, pulls the model if needed, and is ready to talk.
Press Enter to record each prompt.

---

## 2) Quick Start — Raspberry Pi

### Install system dependencies

```bash
sudo apt update
sudo apt install -y python3-dev portaudio19-dev ffmpeg curl git
```

Install Ollama:

```bash
curl -fsSL https://ollama.com/install.sh | sh
```

Piper TTS is a Python dependency; it is installed automatically by `uv sync`.

### Install Python dependencies

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
uv python install 3.11
uv venv --python 3.11
source .venv/bin/activate
uv sync
```

### Download a Piper English voice

```bash
mkdir -p voices
curl -L -o voices/en_US-lessac-medium.onnx \
  https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx
curl -L -o voices/en_US-lessac-medium.onnx.json \
  https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx.json
```

### Configure and run

Edit `config.json`. For Raspberry Pi, use a smaller model and the `tiny` Whisper
model to fit within available RAM:

```json
"whisper": { "model_name": "tiny", "language": "en" },
"llm":     { "provider": "ollama", "model": "llama3.2:1b", ... }
```

Then run:

```bash
uv run main.py
```

The script starts Ollama, pulls the model if needed, and is ready to talk.

If audio playback fails, ensure one of `aplay`, `paplay`, or `ffplay` is installed.

---

## 3) Configuration — config.json

All runtime settings live in `config.json`. Edit it freely; no Python code changes
are needed.

```
config.json
├── audio        — sample rate, recording length, input device
├── whisper      — model name (tiny/base/small/medium/large/turbo), language
├── trigger      — keyboard or serial trigger mode
├── llm          — provider, model name, Ollama URL, history length
├── tts          — piper binary path, voice model path
└── prompts      — session preamble, per-request preamble
```

### Changing the LLM provider

Set `llm.provider` to one of:

| Value       | Needs key in keys.json  | Example model            |
|-------------|-------------------------|--------------------------|
| `ollama`    | No                      | `llama3.2:3b`            |
| `openai`    | `OPENAI_API_KEY`        | `gpt-4o-mini`            |
| `gemini`    | `GEMINI_API_KEY`        | `gemini-1.5-flash`       |
| `anthropic` | `ANTHROPIC_API_KEY`     | `claude-3-5-sonnet-latest` |

Set `llm.model` to any model name valid for that provider.
When using Ollama, the model is pulled automatically on first run.

---

## 4) API keys

For online providers, create a `keys.json` file in the project root:

```json
{
  "OPENAI_API_KEY": "your_openai_key",
  "GEMINI_API_KEY": "your_gemini_key",
  "ANTHROPIC_API_KEY": "your_anthropic_key"
}
```

You only need the key for the provider you are using. A template is at `keys.example.json`.

---

## 5) Preambles

In `config.json` under `prompts`:

- `session_preamble` — sets the overall character and behavior for the whole session
- `request_preamble` — a brief instruction added to every individual request

Example:

```json
"prompts": {
  "session_preamble": "You are a surreal co-creator for visual experiments.",
  "request_preamble": "Keep responses under 80 words and include one concrete scene idea."
}
```

---

## 6) Trigger modes

Set `trigger.source` in `config.json`:

- `"keyboard"` — press Enter before each recording (default)
- `"serial"` — wait for a serial line containing the trigger text

For serial mode, also set `serial_port`, `serial_baud_rate`, and `serial_trigger_text`,
then install pyserial:

```bash
uv add pyserial
```

The microcontroller should send a line containing the trigger text (default: `TRIGGER`).

---

## 7) Notes

- Whisper model options: `tiny`, `base`, `small`, `medium`, `large`, `turbo`.
  Use `base` on macOS/desktop. Use `tiny` on Raspberry Pi.
- Say `exit` or `quit` to stop the session.
- Temporary recordings are stored in `temp_audio/` and overwritten each turn.
- If Piper fails, confirm the voice model `.onnx` path in `config.json` is correct.
