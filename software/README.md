# software

Computer-side helpers. Nothing here runs on the recorder in v1.

## Transcribe dumped WAVs

The recorder writes 48 kHz 16-bit mono PCM. [whisper.cpp](https://github.com/ggerganov/whisper.cpp) resamples to 16 kHz on the computer.

1. Plug in USB-C. The device is a drive; copy `/recordings/*.wav`.
2. Build whisper.cpp so `whisper-cli` is on your PATH (or set `WHISPER_CLI`).
3. Download a ggml model, e.g. `ggml-base.en.bin` (`WHISPER_MODEL` or `--model`).

```bash
python software/transcribe.py /path/to/recordings/20260828-181742.wav
python software/transcribe.py --dir /path/to/recordings
```

No cloud API. An Android app while the recorder is snapped on is out of scope.
