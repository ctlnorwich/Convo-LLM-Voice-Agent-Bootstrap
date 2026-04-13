from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
import textwrap
import time
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

import requests
import sounddevice as sd
import soundfile as sf
import whisper


@dataclass
class AudioSettings:
    sample_rate_hz: int = 16_000
    channels: int = 1
    # Maximum recording length in seconds before the recording is forced to stop.
    max_record_seconds: float = 10.0
    # Size of each audio chunk analysed for silence detection (in samples).
    vad_chunk_samples: int = 1_600    # 100 ms at 16 kHz
    # RMS amplitude below this value is considered silence (0.0–1.0 scale).
    vad_silence_threshold: float = 0.01
    # How many consecutive silent chunks must follow speech before recording stops.
    vad_silence_chunks: int = 15     # ~1.5 seconds of trailing silence
    input_device: int | None = None
    temp_recording_file: Path = Path("temp_audio/recording.wav")


@dataclass
class WhisperSettings:
    # Valid Whisper model names: tiny, base, small, medium, large, turbo
    # Use "base" on macOS/desktop, "tiny" on Raspberry Pi for best performance.
    model_name: str = "base"
    language: str = "en"


@dataclass
class TriggerSettings:
    source: str = "keyboard"  # "keyboard" or "serial"
    serial_port: str = "/dev/ttyUSB0"
    serial_baud_rate: int = 115_200
    serial_trigger_text: str = "TRIGGER"


@dataclass
class LLMSettings:
    provider: str = "ollama"  # "ollama", "openai", "gemini", "anthropic"
    model: str = "llama3.2:3b"
    ollama_base_url: str = "http://127.0.0.1:11434"
    max_history_turns: int = 6


@dataclass
class TTSSettings:
    piper_binary: str = "piper"
    voice_model_path: Path = Path("voices/en_US-lessac-medium.onnx")
    output_wav: Path = Path("temp_audio/tts_output.wav")
    speaker_id: int | None = None


@dataclass
class PromptSettings:
    # Session preamble is included in every turn and sets overall behavior.
    session_preamble: str = (
        "You are an assistant collaborating with a digital artist. "
        "Be concise, concrete, and imagination-friendly."
    )
    # Request preamble is also included every turn and can be changed per project.
    request_preamble: str = "Respond in plain spoken English."


@dataclass
class AppSettings:
    keys_file: Path = Path("keys.json")
    config_file: Path = Path("config.json")
    audio: AudioSettings = field(default_factory=AudioSettings)
    whisper: WhisperSettings = field(default_factory=WhisperSettings)
    trigger: TriggerSettings = field(default_factory=TriggerSettings)
    llm: LLMSettings = field(default_factory=LLMSettings)
    tts: TTSSettings = field(default_factory=TTSSettings)
    prompts: PromptSettings = field(default_factory=PromptSettings)


@dataclass
class OllamaRuntime:
    process: subprocess.Popen | None = None
    started_with_start_cmd: bool = False


def _update_dataclass_fields(target: object, updates: dict[str, object]) -> None:
    for key, value in updates.items():
        if not hasattr(target, key):
            continue
        if key.endswith("_path") and isinstance(value, str):
            setattr(target, key, Path(value))
        elif key.endswith("_file") and isinstance(value, str):
            setattr(target, key, Path(value))
        else:
            setattr(target, key, value)


def load_app_settings() -> AppSettings:
    settings = AppSettings()

    if not settings.config_file.exists():
        return settings

    raw = json.loads(settings.config_file.read_text(encoding="utf-8"))

    # Allow top-level override of keys/config file paths.
    if isinstance(raw.get("keys_file"), str):
        settings.keys_file = Path(str(raw["keys_file"]))
    if isinstance(raw.get("config_file"), str):
        settings.config_file = Path(str(raw["config_file"]))

    if isinstance(raw.get("audio"), dict):
        _update_dataclass_fields(settings.audio, raw["audio"])
    if isinstance(raw.get("whisper"), dict):
        _update_dataclass_fields(settings.whisper, raw["whisper"])
    if isinstance(raw.get("trigger"), dict):
        _update_dataclass_fields(settings.trigger, raw["trigger"])
    if isinstance(raw.get("llm"), dict):
        _update_dataclass_fields(settings.llm, raw["llm"])
    if isinstance(raw.get("tts"), dict):
        _update_dataclass_fields(settings.tts, raw["tts"])
    if isinstance(raw.get("prompts"), dict):
        _update_dataclass_fields(settings.prompts, raw["prompts"])

    return settings


def load_keys(keys_file: Path) -> dict[str, str]:
    if not keys_file.exists():
        return {}
    data = json.loads(keys_file.read_text(encoding="utf-8"))
    return {str(key): str(value) for key, value in data.items()}


def wait_for_trigger(settings: TriggerSettings) -> None:
    if settings.source == "keyboard":
        input("Press Enter to record the next prompt (Ctrl+C to quit)... ")
        return

    if settings.source == "serial":
        wait_for_serial_trigger(settings)
        return

    raise ValueError(f"Unknown trigger source: {settings.source}")


def wait_for_serial_trigger(settings: TriggerSettings) -> None:
    """
    Waits for a serial trigger line that contains serial_trigger_text.

    If you do not want serial triggering, keep trigger.source = "keyboard".
    """

    try:
        import serial
    except ImportError as exc:
        raise RuntimeError(
            "Serial trigger selected, but pyserial is not installed. "
            "Install with: pip install pyserial"
        ) from exc

    print(
        f"Listening for serial trigger on {settings.serial_port} "
        f"at {settings.serial_baud_rate} baud..."
    )

    with serial.Serial(settings.serial_port, settings.serial_baud_rate, timeout=1) as ser:
        while True:
            line = ser.readline().decode("utf-8", errors="ignore").strip()
            if settings.serial_trigger_text in line:
                print("Serial trigger received.")
                return


# Example serial sender (microcontroller side):
#   send line: TRIGGER\n
# Example to enable serial in this script:
#   1. Set trigger.source = "serial" in AppSettings.
#   2. Set trigger.serial_port to your device path.


def record_audio(settings: AudioSettings) -> Path:
    """
    Record from the microphone using voice-activity detection (VAD).

    Recording stops when either:
      - A lull in audio (silence after speech) is detected, or
      - max_record_seconds is reached.

    The silence detector works by splitting the incoming audio into small chunks
    and computing the RMS amplitude of each.  A chunk whose RMS is below
    vad_silence_threshold is treated as silence.  Once speech has been detected,
    recording stops after vad_silence_chunks consecutive silent chunks.
    """
    import numpy as np

    # Create the temp audio folder if it does not already exist.
    settings.temp_recording_file.parent.mkdir(parents=True, exist_ok=True)

    chunk_size = settings.vad_chunk_samples
    max_chunks = int(
        settings.max_record_seconds * settings.sample_rate_hz / chunk_size
    )

    recorded_chunks: list[object] = []
    speech_detected = False
    consecutive_silent_chunks = 0

    print(
        f"Listening (max {settings.max_record_seconds:.0f}s, "
        "stops automatically after silence)..."
    )

    with sd.InputStream(
        samplerate=settings.sample_rate_hz,
        channels=settings.channels,
        dtype="float32",
        device=settings.input_device,
        blocksize=chunk_size,
    ) as stream:
        for _ in range(max_chunks):
            chunk, _ = stream.read(chunk_size)
            recorded_chunks.append(chunk.copy())

            rms = float(np.sqrt(np.mean(chunk ** 2)))

            if rms >= settings.vad_silence_threshold:
                speech_detected = True
                consecutive_silent_chunks = 0
            elif speech_detected:
                consecutive_silent_chunks += 1
                if consecutive_silent_chunks >= settings.vad_silence_chunks:
                    print("Silence detected — stopping recording.")
                    break

    if not speech_detected:
        print("No speech detected.")

    audio_data = np.concatenate(recorded_chunks, axis=0)
    sf.write(str(settings.temp_recording_file), audio_data, settings.sample_rate_hz)
    return settings.temp_recording_file


def transcribe_audio(model: whisper.Whisper, audio_file: Path, language: str) -> str:
    result = model.transcribe(str(audio_file), language=language)
    transcript = str(result.get("text", "")).strip()
    return transcript


# ---------------------------------------------------------------------------
# Ollama lifecycle helpers
# ---------------------------------------------------------------------------

def is_ollama_running(base_url: str) -> bool:
    """Return True if the Ollama HTTP API is reachable."""
    try:
        response = requests.get(f"{base_url}/api/tags", timeout=3)
        return response.status_code == 200
    except Exception:
        return False


def ollama_supports_start_stop() -> bool:
    """Return True if this local Ollama CLI supports service-level start/stop."""
    try:
        result = subprocess.run(
            ["ollama", "help"],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return False

    output = result.stdout.lower()
    return "\n  start" in output and "\n  stop" in output


def ollama_host_from_base_url(base_url: str) -> str:
    """Convert a base URL into host:port format for OLLAMA_HOST."""
    parsed = urlparse(base_url)
    if parsed.hostname and parsed.port:
        return f"{parsed.hostname}:{parsed.port}"
    # Fall back to the default Ollama host if parsing fails.
    return "127.0.0.1:11434"


def start_ollama_if_needed(base_url: str) -> OllamaRuntime | None:
    """
    Start 'ollama serve' in the background if it is not already running.
    Returns the Popen handle if we started it, None if it was already running.
    """
    if is_ollama_running(base_url):
        print("Ollama is already running.")
        return None

    if not shutil.which("ollama"):
        raise RuntimeError(
            "'ollama' command not found. Install Ollama from https://ollama.com"
        )

    log_dir = Path("temp_audio")
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "ollama_server.log"

    ollama_host = ollama_host_from_base_url(base_url)
    env = os.environ.copy()
    env["OLLAMA_HOST"] = ollama_host

    if ollama_supports_start_stop():
        print(f"Starting Ollama with start command on {ollama_host}...", end="", flush=True)
        result = subprocess.run(
            ["ollama", "start"],
            check=False,
            capture_output=True,
            text=True,
            env=env,
        )
        log_file.write_text(
            (result.stdout or "") + (result.stderr or ""),
            encoding="utf-8",
        )

        if result.returncode != 0 and not is_ollama_running(base_url):
            raise RuntimeError(
                "Failed to start Ollama with 'ollama start'. "
                f"See {log_file} for details."
            )

        for _ in range(60):
            time.sleep(1)
            if is_ollama_running(base_url):
                print(" ready.")
                return OllamaRuntime(process=None, started_with_start_cmd=True)
            print(".", end="", flush=True)

        print()
        raise RuntimeError(
            "Ollama did not become ready within 60 seconds after 'ollama start'. "
            f"See {log_file} for details."
        )

    print(f"Starting Ollama in the background on {ollama_host}...", end="", flush=True)
    ollama_process = subprocess.Popen(
        ["ollama", "serve"],
        stdout=log_file.open("w", encoding="utf-8"),
        stderr=subprocess.STDOUT,
        env=env,
    )

    # Wait up to 60 seconds for the API to become available.
    for _ in range(60):
        time.sleep(1)
        if ollama_process.poll() is not None:
            # Common case: a different Ollama process already owns the port.
            # If the API is reachable, treat that as success.
            if is_ollama_running(base_url):
                print(" already running.")
                return None

            log_text = ""
            try:
                log_text = log_file.read_text(encoding="utf-8")
            except OSError:
                pass

            if "address already in use" in log_text:
                raise RuntimeError(
                    "Ollama port is already in use but the API is not reachable at "
                    f"{base_url}. Check config.json llm.ollama_base_url or stop the "
                    "other process using that port."
                )

            raise RuntimeError(
                "Ollama process exited before becoming ready. "
                f"See {log_file} for details."
            )
        if is_ollama_running(base_url):
            print(" ready.")
            return OllamaRuntime(process=ollama_process, started_with_start_cmd=False)
        print(".", end="", flush=True)

    print()  # newline after the dots
    ollama_process.terminate()
    raise RuntimeError(
        "Ollama did not become ready within 60 seconds. "
        f"See {log_file} for startup logs."
    )


def stop_ollama(ollama_runtime: OllamaRuntime | None) -> None:
    """Stop Ollama if it was started by this script."""
    if ollama_runtime is None:
        return

    if ollama_runtime.started_with_start_cmd:
        print("Stopping Ollama with stop command...")
        subprocess.run(["ollama", "stop"], check=False, capture_output=True, text=True)
        return

    ollama_process = ollama_runtime.process
    if ollama_process is None:
        return

    print("Stopping Ollama...")
    ollama_process.terminate()
    try:
        ollama_process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        ollama_process.kill()


def ensure_ollama_model(model: str, base_url: str) -> None:
    """
    Verify that the model in config.json is available locally.
    If not, pull it automatically so the user never has to run 'ollama pull' manually.
    """
    response = requests.get(f"{base_url}/api/tags", timeout=10)
    response.raise_for_status()
    local_model_names = [entry["name"] for entry in response.json().get("models", [])]

    # Ollama sometimes stores names without a tag; handle both "model" and "model:tag" forms.
    def names_match(config_name: str, local_name: str) -> bool:
        return config_name == local_name or config_name.split(":")[0] == local_name.split(":")[0]

    if any(names_match(model, local) for local in local_model_names):
        print(f"Model '{model}' is available.")
        return

    print(f"Model '{model}' not found locally. Pulling from Ollama library (this may take a while)...")
    result = subprocess.run(["ollama", "pull", model], check=False)
    if result.returncode != 0:
        raise RuntimeError(
            f"Failed to pull model '{model}'. "
            "Check the model name in config.json and your internet connection."
        )
    print(f"Model '{model}' is ready.")


# ---------------------------------------------------------------------------


def build_prompt(
    user_text: str,
    prompts: PromptSettings,
    history: list[tuple[str, str]],
    max_history_turns: int,
) -> str:
    history_tail = history[-max_history_turns:]
    history_lines: list[str] = []
    for user_turn, assistant_turn in history_tail:
        history_lines.append(f"User: {user_turn}")
        history_lines.append(f"Assistant: {assistant_turn}")

    history_block = "\n".join(history_lines) if history_lines else "(No prior turns)"

    return textwrap.dedent(
        f"""
        SESSION PREAMBLE:
        {prompts.session_preamble}

        REQUEST PREAMBLE:
        {prompts.request_preamble}

        CONVERSATION HISTORY:
        {history_block}

        USER INPUT:
        {user_text}

        ASSISTANT OUTPUT:
        """
    ).strip()


def call_llm(prompt: str, settings: LLMSettings, keys: dict[str, str]) -> str:
    provider = settings.provider.lower()

    if provider == "ollama":
        return call_ollama(prompt, settings)
    if provider == "openai":
        return call_openai(prompt, settings, keys)
    if provider == "gemini":
        return call_gemini(prompt, settings, keys)
    if provider == "anthropic":
        return call_anthropic(prompt, settings, keys)

    raise ValueError(f"Unsupported provider: {settings.provider}")


def call_ollama(prompt: str, settings: LLMSettings) -> str:
    response = requests.post(
        f"{settings.ollama_base_url}/api/generate",
        json={"model": settings.model, "prompt": prompt, "stream": False},
        timeout=120,
    )
    response.raise_for_status()
    payload = response.json()
    return str(payload.get("response", "")).strip()


def call_openai(prompt: str, settings: LLMSettings, keys: dict[str, str]) -> str:
    api_key = keys.get("OPENAI_API_KEY", "")
    if not api_key:
        raise RuntimeError("Missing OPENAI_API_KEY in keys.json")

    response = requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "model": settings.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.8,
        },
        timeout=120,
    )
    response.raise_for_status()
    payload = response.json()
    return str(payload["choices"][0]["message"]["content"]).strip()


def call_gemini(prompt: str, settings: LLMSettings, keys: dict[str, str]) -> str:
    api_key = keys.get("GEMINI_API_KEY", "")
    if not api_key:
        raise RuntimeError("Missing GEMINI_API_KEY in keys.json")

    response = requests.post(
        (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{settings.model}:generateContent?key={api_key}"
        ),
        json={"contents": [{"parts": [{"text": prompt}]}]},
        timeout=120,
    )
    response.raise_for_status()
    payload = response.json()
    return str(payload["candidates"][0]["content"]["parts"][0]["text"]).strip()


def call_anthropic(prompt: str, settings: LLMSettings, keys: dict[str, str]) -> str:
    api_key = keys.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise RuntimeError("Missing ANTHROPIC_API_KEY in keys.json")

    response = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": settings.model,
            "max_tokens": 1024,
            "messages": [{"role": "user", "content": prompt}],
        },
        timeout=120,
    )
    response.raise_for_status()
    payload = response.json()
    return str(payload["content"][0]["text"]).strip()


def speak_with_piper(text: str, settings: TTSSettings) -> None:
    if not text:
        return

    piper_command = [
        settings.piper_binary,
        "--model",
        str(settings.voice_model_path),
        "--output_file",
        str(settings.output_wav),
    ]
    if settings.speaker_id is not None:
        piper_command.extend(["--speaker", str(settings.speaker_id)])

    process = subprocess.run(
        piper_command,
        input=text,
        text=True,
        capture_output=True,
        check=False,
    )
    if process.returncode != 0:
        raise RuntimeError(
            "Piper synthesis failed:\n"
            f"STDOUT:\n{process.stdout}\n"
            f"STDERR:\n{process.stderr}"
        )

    play_audio_file(settings.output_wav)


def play_audio_file(audio_file: Path) -> None:
    system_name = platform.system().lower()

    if system_name == "darwin":
        subprocess.run(["afplay", str(audio_file)], check=True)
        return

    if system_name == "linux":
        for player in ("aplay", "paplay", "ffplay"):
            if shutil.which(player):
                if player == "ffplay":
                    subprocess.run(
                        [
                            "ffplay",
                            "-nodisp",
                            "-autoexit",
                            "-loglevel",
                            "error",
                            str(audio_file),
                        ],
                        check=True,
                    )
                else:
                    subprocess.run([player, str(audio_file)], check=True)
                return
        raise RuntimeError(
            "No Linux audio player found. Install one of: aplay, paplay, ffplay"
        )

    raise RuntimeError(f"Unsupported OS for audio playback: {platform.system()}")


def main() -> None:
    settings = load_app_settings()
    keys = load_keys(settings.keys_file)

    # If using Ollama, start it in the background and ensure the configured model
    # is present locally.  The user only needs to edit config.json and run the script.
    ollama_runtime: OllamaRuntime | None = None
    if settings.llm.provider.lower() == "ollama":
        ollama_runtime = start_ollama_if_needed(settings.llm.ollama_base_url)
        ensure_ollama_model(settings.llm.model, settings.llm.ollama_base_url)

    print(f"Loading Whisper model: {settings.whisper.model_name}")
    whisper_model = whisper.load_model(settings.whisper.model_name)

    history: list[tuple[str, str]] = []

    print("Ready. Say 'exit' or 'quit' to stop.")

    try:
        while True:
            try:
                wait_for_trigger(settings.trigger)
                audio_file = record_audio(settings.audio)
                user_text = transcribe_audio(
                    whisper_model, audio_file, language=settings.whisper.language
                )

                if not user_text:
                    print("No speech detected. Try again.")
                    continue

                print(f"You said: {user_text}")

                if user_text.strip().lower() in {"exit", "quit"}:
                    print("Stopping conversation loop.")
                    break

                prompt = build_prompt(
                    user_text,
                    settings.prompts,
                    history,
                    max_history_turns=settings.llm.max_history_turns,
                )
                assistant_text = call_llm(prompt, settings.llm, keys)
                print(f"Assistant: {assistant_text}")

                speak_with_piper(assistant_text, settings.tts)
                history.append((user_text, assistant_text))

            except KeyboardInterrupt:
                print("\nInterrupted. Exiting.")
                break
            except Exception as exc:  # Keep loop alive for runtime hiccups.
                print(f"Error: {exc}", file=sys.stderr)
                time.sleep(0.2)
    finally:
        # Always stop Ollama if we started it, even on crash or Ctrl+C.
        stop_ollama(ollama_runtime)


if __name__ == "__main__":
    main()
