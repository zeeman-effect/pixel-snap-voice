#!/usr/bin/env python3
"""Transcribe dumped 48 kHz WAV files with a local whisper.cpp binary.

Nothing here runs on the recorder. Dump the USB volume first, then:

    python software/transcribe.py recordings/20260828-181742.wav
    python software/transcribe.py --dir /media/PSV/recordings
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path


def find_whisper(explicit: str | None) -> str:
    if explicit:
        return explicit
    for name in ("whisper-cli", "whisper-cpp", "main"):
        found = shutil.which(name)
        if found:
            return found
    env = os.environ.get("WHISPER_CLI")
    if env:
        return env
    raise SystemExit(
        "whisper.cpp CLI not found. Build https://github.com/ggerganov/whisper.cpp "
        "and put `whisper-cli` on PATH, or pass --bin / set WHISPER_CLI."
    )


def find_model(explicit: str | None) -> str:
    if explicit:
        return explicit
    env = os.environ.get("WHISPER_MODEL")
    if env:
        return env
    home = Path.home()
    candidates = [
        home / "whisper.cpp" / "models" / "ggml-base.en.bin",
        home / "models" / "ggml-base.en.bin",
        Path("models") / "ggml-base.en.bin",
    ]
    for p in candidates:
        if p.is_file():
            return str(p)
    raise SystemExit(
        "No ggml model found. Download e.g. ggml-base.en.bin from whisper.cpp "
        "and pass --model (or set WHISPER_MODEL)."
    )


def wavs_from(path: Path, directory: Path | None) -> list[Path]:
    if directory:
        files = sorted(directory.glob("*.wav"))
        if not files:
            raise SystemExit(f"no WAV files in {directory}")
        return files
    if not path:
        raise SystemExit("pass a WAV file or --dir")
    if not path.is_file():
        raise SystemExit(f"not a file: {path}")
    return [path]


def transcribe(bin_path: str, model: str, wav: Path, language: str) -> None:
    # whisper.cpp resamples 48 kHz PCM to 16 kHz internally.
    cmd = [bin_path, "-m", model, "-f", str(wav), "-l", language, "-nt"]
    print("+", " ".join(cmd))
    subprocess.check_call(cmd)


def main() -> int:
    p = argparse.ArgumentParser(description="Local whisper.cpp transcription of dumped recorder WAVs")
    p.add_argument("wav", nargs="?", type=Path, help="one 48 kHz 16-bit mono WAV")
    p.add_argument("--dir", type=Path, help="folder of WAVs (USB dump /recordings)")
    p.add_argument("--bin", help="whisper.cpp CLI path")
    p.add_argument("--model", help="ggml model path")
    p.add_argument("--language", default="en")
    args = p.parse_args()

    binary = find_whisper(args.bin)
    model = find_model(args.model)
    for wav in wavs_from(args.wav, args.dir):
        transcribe(binary, model, wav, args.language)
    return 0


if __name__ == "__main__":
    sys.exit(main())
