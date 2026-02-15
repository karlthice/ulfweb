#!/usr/bin/env python3
"""Download Piper TTS voice models from HuggingFace."""

import json
import sys
from pathlib import Path

import requests
from tqdm import tqdm


# Voice models to download (language_code, voice_key)
VOICES = [
    ("is", "is_IS-salka-medium"),
    ("en", "en_US-lessac-medium"),
    ("no", "no_NO-talesyntese-medium"),
    ("sv", "sv_SE-nst-medium"),
    ("da", "da_DK-talesyntese-medium"),
    ("de", "de_DE-thorsten-high"),
    ("fr", "fr_FR-siwis-medium"),
    ("it", "it_IT-riccardo-x_low"),
    ("es", "es_ES-sharvard-medium"),
]

# Base URL for Piper voices on HuggingFace
BASE_URL = "https://huggingface.co/rhasspy/piper-voices/resolve/main"
VOICES_JSON_URL = f"{BASE_URL}/voices.json"


def download_file(url: str, dest_path: Path, desc: str = "") -> bool:
    """Download a file with progress bar."""
    try:
        response = requests.get(url, stream=True, allow_redirects=True)
        response.raise_for_status()

        total_size = int(response.headers.get("content-length", 0))

        with open(dest_path, "wb") as f:
            with tqdm(
                total=total_size,
                unit="B",
                unit_scale=True,
                desc=desc,
                ncols=80
            ) as pbar:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
                    pbar.update(len(chunk))

        return True
    except Exception as e:
        print(f"Error downloading {url}: {e}")
        if dest_path.exists():
            dest_path.unlink()
        return False


def get_voice_files(voice_key: str, voices_data: dict) -> dict:
    """Get file paths for a voice from voices.json data."""
    voice_info = voices_data.get(voice_key, {})
    return voice_info.get("files", {})


def download_voice(voice_key: str, voices_dir: Path, voices_data: dict) -> bool:
    """Download a Piper voice model and config."""
    files = get_voice_files(voice_key, voices_data)

    if not files:
        print(f"  Voice '{voice_key}' not found in voices.json")
        return False

    # Find the .onnx and .onnx.json files
    onnx_file = None
    json_file = None

    for file_path in files:
        if file_path.endswith(".onnx") and not file_path.endswith(".onnx.json"):
            onnx_file = file_path
        elif file_path.endswith(".onnx.json"):
            json_file = file_path

    if not onnx_file:
        print(f"  No ONNX model found for '{voice_key}'")
        return False

    # Local file names
    model_path = voices_dir / f"{voice_key}.onnx"
    config_path = voices_dir / f"{voice_key}.onnx.json"

    # Skip if already downloaded
    if model_path.exists() and config_path.exists():
        print(f"  Already downloaded")
        return True

    # Download model
    model_url = f"{BASE_URL}/{onnx_file}"
    if not download_file(model_url, model_path, f"  {voice_key}.onnx"):
        return False

    # Download config if available
    if json_file:
        config_url = f"{BASE_URL}/{json_file}"
        if not download_file(config_url, config_path, f"  {voice_key}.onnx.json"):
            # Config is optional, don't fail
            print(f"  Warning: Could not download config file")

    return True


def main():
    """Download all voice models."""
    # Determine voices directory
    script_dir = Path(__file__).parent
    project_dir = script_dir.parent
    voices_dir = project_dir / "data" / "voices"

    print(f"Downloading Piper TTS voices to: {voices_dir}")
    print()

    # Create voices directory
    voices_dir.mkdir(parents=True, exist_ok=True)

    # Download voices.json first
    print("Fetching voice catalog...")
    try:
        response = requests.get(VOICES_JSON_URL, allow_redirects=True)
        response.raise_for_status()
        voices_data = response.json()
        print(f"Found {len(voices_data)} voices in catalog")
        print()
    except Exception as e:
        print(f"Error fetching voices.json: {e}")
        sys.exit(1)

    # Download each voice
    success_count = 0
    fail_count = 0

    for lang_code, voice_key in VOICES:
        print(f"[{lang_code.upper()}] {voice_key}")
        if download_voice(voice_key, voices_dir, voices_data):
            success_count += 1
        else:
            fail_count += 1
        print()

    # Summary
    print("-" * 40)
    print(f"Downloaded: {success_count}/{len(VOICES)} voices")
    if fail_count > 0:
        print(f"Failed: {fail_count} voices")
        sys.exit(1)
    else:
        print("All voices downloaded successfully!")


if __name__ == "__main__":
    main()
