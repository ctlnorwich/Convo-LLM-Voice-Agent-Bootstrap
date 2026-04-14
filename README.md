# Conversational LLM Voice Agent Bootstrap

A template and playground for digital artists to easier experiment with conversational LLM (Large Language Model) voice agents and explore the technology critically. It is a local first application, defaulting to lightweight on-device models for privacy and sustainability concerns.

**How it works**: 

All voice based conversational llm agents consist of three parts.

- **STT**: Speech-to-Tech. Whisper is the locally run general-purpose speech recognition model used here.
- **LLM**: Large-Language Models. Ollama is the default application we use to run different LLMs locally but is switchable to use an online model like OpenAIs chatGPT, Googles Gemini, or Anthropics Claude.
- **TTS**: Text-to-Speech. Piper is the speech system that generates voices from provided text.

All of these are themselves programs that use a neural network transformer architecture (the T in ChatGPT). This is the groundbreaking programming technique that has made many modern "AI" programs possible. 

**User flow**:

1. Waits for a trigger (Dafault is the Enter key) to begin listening.
2. Whisper transcribes your speech to text.
3. Ollama running a LLM model as a service generates a text response from the transcription. (Online models are queried though a HTTP request)
4. Piper speaks the response aloud in a voice.
5. Repeat until either program is terminated with Ctrl+C or 

> [!NOTE]
> When using Ollama the script starts the Ollama server automatically, checks that the model you specified in `config.json` is downloaded (and pulls it if not), and shuts the server down cleanly when you exit.

> [!CAUTION]
> A LLM is not true intelligence. It does not truly understand the world, form intentions, or reason from first principles - it predicts likely next words by learning statistical patterns from enormous text datasets. Its outputs may feel intelligent but this is because those patterns encode a huge amount of human language, knowledge, and style. LLMs are in reality the result of advanced data science using massive computing power to do large-scale training, optimization, and probability; not conscious thought or independent understanding.

---

## Quick Start — macOS

### Install system dependencies

```bash
brew install portaudio ffmpeg ollama
```

- `portaudio` — used by sounddevice for microphone capture
- `ollama` — runs local LLM models

### Install Python dependencies

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
uv python install 3.11
uv venv --python 3.11
source .venv/bin/activate
uv sync
```

### Download Piper English voices

```bash
./download_english_piper_voices.sh voices
```

Then choose one voice in `config.json`, for example:

```json
"tts": {
  "voice_model_path": "voices/en_US/lessac/medium/en_US-lessac-medium.onnx"
}
```

### Configure and run

Edit `config.json` to set your model and preambles, then:

```bash
uv run main.py
```

The script starts Ollama, pulls the model if needed, and is ready to talk.
Press Enter to record each prompt.

Say `exit` or `quit` to stop the session.

---

## Quick Start — Raspberry Pi

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

### Download Piper English voices

```bash
./download_english_piper_voices.sh voices
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

Say `exit` or `quit` to stop the session.

If audio playback fails, ensure one of `aplay`, `paplay`, or `ffplay` is installed.

---

## Logs

The app writes logs to dedicated folders:

- `llm_logs/ollama_server.log` — Ollama server start/runtime logs
- `chat_logs/<ISO_DATETIME>__<MODEL>.json` — one JSON file per chat session
- `temp_audio/` — temporary input/output WAV files used during each turn

Each chat session JSON includes:

- `meta.llm` — exact `llm` config values used for that session
- `meta.prompts` — exact `prompts` config values used for that session
- `messages` — timestamped user/assistant text messages

Example filename:

- `chat_logs/2026-04-13T18-45-02__llama3.2_3b.json`

---

## 4) Configuration — config.json

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

Whisper model guidance:

- `base` is the recommended default on macOS/desktop
- `tiny` is recommended on Raspberry Pi for lower RAM/CPU usage

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

## API keys

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

## Preambles

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

## Trigger modes

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

## English Piper voices

This project includes a downloader for all English voices under:

- `https://huggingface.co/rhasspy/piper-voices/tree/main/en`

The selectable English voices currently include:

| Locale | Speaker | Quality | Voice id |
|--------|---------|---------|----------|
| en_GB | alan | low | en_GB-alan-low |
| en_GB | alan | medium | en_GB-alan-medium |
| en_GB | alba | medium | en_GB-alba-medium |
| en_GB | aru | medium | en_GB-aru-medium |
| en_GB | cori | high | en_GB-cori-high |
| en_GB | cori | medium | en_GB-cori-medium |
| en_GB | jenny_dioco | medium | en_GB-jenny_dioco-medium |
| en_GB | northern_english_male | medium | en_GB-northern_english_male-medium |
| en_GB | semaine | medium | en_GB-semaine-medium |
| en_GB | southern_english_female | low | en_GB-southern_english_female-low |
| en_GB | vctk | medium | en_GB-vctk-medium |
| en_US | amy | low | en_US-amy-low |
| en_US | amy | medium | en_US-amy-medium |
| en_US | arctic | medium | en_US-arctic-medium |
| en_US | bryce | medium | en_US-bryce-medium |
| en_US | danny | low | en_US-danny-low |
| en_US | hfc_female | medium | en_US-hfc_female-medium |
| en_US | hfc_male | medium | en_US-hfc_male-medium |
| en_US | joe | medium | en_US-joe-medium |
| en_US | john | medium | en_US-john-medium |
| en_US | kathleen | low | en_US-kathleen-low |
| en_US | kristin | medium | en_US-kristin-medium |
| en_US | kusal | medium | en_US-kusal-medium |
| en_US | l2arctic | medium | en_US-l2arctic-medium |
| en_US | lessac | high | en_US-lessac-high |
| en_US | lessac | low | en_US-lessac-low |
| en_US | lessac | medium | en_US-lessac-medium |
| en_US | libritts | high | en_US-libritts-high |

These are English voice models. Many other languages are available in the same
Hugging Face repository under other language folders.

[!CAUTION]
>> These voices are trained from Mozillas's Common Voice dataset which is open licenced data. Other voice files can be found when searching "piper-tts trained models" but many of these are trained off proprietary voice data such as voice actors work, youtube videos and other data that is intellectual property. Using these could be considered unethical unless you have permission from the rights holders.

---

## Debugging

If the app fails to start or run, check these first:

- Ollama failed to start:
  read `llm_logs/ollama_server.log` for the exact startup error.
- Ollama port conflict:
  another service may already be on your configured `llm.ollama_base_url` port.
  stop the conflicting process or update the base URL in `config.json`.
- Model pull/generation errors:
  verify `llm.model` exists for the selected provider and confirm network access.
- Piper synthesis/playback errors:
  verify `tts.voice_model_path` points to a valid `.onnx` file and ensure the matching
  `.onnx.json` file exists alongside it.
- No serial trigger response:
  install pyserial (`uv add pyserial`) and confirm `trigger.serial_port` and baud rate.

---

## License

This project is licensed under the GNU General Public License v3.0 or later
(GPL-3.0-or-later). See [LICENSE](LICENSE) for the full license text.
