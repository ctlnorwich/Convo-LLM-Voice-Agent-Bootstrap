#!/usr/bin/env bash
set -euo pipefail

# Download all English Piper voices from rhasspy/piper-voices.
#
# Usage:
#   ./download_english_piper_voices.sh [TARGET_DIR]
#
# Example:
#   ./download_english_piper_voices.sh voices

target_dir="${1:-voices}"
mkdir -p "$target_dir"

echo "Fetching English voice file list from Hugging Face..."

python3 - <<'PY' "$target_dir"
import json
import pathlib
import subprocess
import sys
import urllib.request

base_url = "https://huggingface.co/rhasspy/piper-voices/resolve/main"
api_url = "https://huggingface.co/api/models/rhasspy/piper-voices/tree/main/en?recursive=1"

target_dir = pathlib.Path(sys.argv[1])
target_dir.mkdir(parents=True, exist_ok=True)

items = json.loads(urllib.request.urlopen(api_url, timeout=60).read().decode())

voice_onnx_files = []
for item in items:
    path = item.get("path", "")
    if not path.endswith(".onnx"):
        continue
    if "_RT" in path:
        # Skip RT variants by default to avoid duplicate voice choices.
        continue
    voice_onnx_files.append(path)

voice_onnx_files = sorted(set(voice_onnx_files))
print(f"Found {len(voice_onnx_files)} English voice models to download.")

for onnx_path in voice_onnx_files:
    json_path = onnx_path + ".json"

    rel_onnx = onnx_path.replace("en/", "", 1)
    rel_json = json_path.replace("en/", "", 1)

    out_onnx = target_dir / rel_onnx
    out_json = target_dir / rel_json
    out_onnx.parent.mkdir(parents=True, exist_ok=True)

    url_onnx = f"{base_url}/{onnx_path}"
    url_json = f"{base_url}/{json_path}"

    if out_onnx.exists() and out_json.exists():
        print(f"Skipping existing: {rel_onnx}")
        continue

    print(f"Downloading: {rel_onnx}")
    subprocess.run(["curl", "-L", "-o", str(out_onnx), url_onnx], check=True)
    subprocess.run(["curl", "-L", "-o", str(out_json), url_json], check=True)

print("Done.")
PY
