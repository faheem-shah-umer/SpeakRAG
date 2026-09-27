"""Transcribe a local WAV file with faster-whisper."""

from __future__ import annotations

import argparse
import json
import time
from functools import lru_cache
from pathlib import Path


MODELS = ("tiny.en", "base.en", "base")
MODEL_DIR = Path(__file__).resolve().parent / "models"


@lru_cache(maxsize=2)
def _model(name: str):
    from faster_whisper import WhisperModel

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    return WhisperModel(
        name,
        device="cpu",
        compute_type="int8",
        download_root=str(MODEL_DIR),
    )


def transcribe_audio(path: Path, model_name: str = "base.en") -> dict:
    path = Path(path)
    if model_name not in MODELS:
        raise ValueError(f"Choose one of these models: {', '.join(MODELS)}")
    if not path.is_file() or path.suffix.lower() != ".wav":
        raise ValueError("Choose an existing WAV file.")

    started = time.perf_counter()
    model = _model(model_name)
    model_ready = time.perf_counter()
    language = "en" if model_name.endswith(".en") else None
    segments, info = model.transcribe(str(path), beam_size=5, language=language)
    # faster-whisper returns a generator; iterating runs the transcription.
    parts = [
        {
            "start": round(segment.start, 2),
            "end": round(segment.end, 2),
            "text": segment.text.strip(),
        }
        for segment in segments
    ]
    return {
        "text": " ".join(part["text"] for part in parts if part["text"]),
        "segments": parts,
        "language": info.language,
        "model": model_name,
        "model_load_seconds": round(model_ready - started, 2),
        "transcription_seconds": round(time.perf_counter() - model_ready, 2),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file", type=Path, help="WAV file to transcribe")
    parser.add_argument("--model", choices=MODELS, default="base.en")
    parser.add_argument("--json", action="store_true", help="Print structured output")
    args = parser.parse_args()
    try:
        result = transcribe_audio(args.file, args.model)
    except (OSError, RuntimeError, ValueError) as exc:
        parser.exit(1, f"ASR error: {exc}\n")
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(f"Model: {result['model']} | Language: {result['language']}")
        print(f"Transcript: {result['text'] or '[No speech detected]'}")
        for segment in result["segments"]:
            print(f"[{segment['start']:.2f}-{segment['end']:.2f}s] {segment['text']}")


if __name__ == "__main__":
    main()
