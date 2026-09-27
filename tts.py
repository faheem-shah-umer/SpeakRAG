"""Synthesize an answer to WAV with a local Piper ONNX voice."""

from __future__ import annotations

import argparse
import re
import sys
import wave
from functools import lru_cache
from pathlib import Path
from typing import Callable


ROOT = Path(__file__).resolve().parent
VOICE_DIR = ROOT / "models" / "piper"
DEFAULT_OUTPUT = ROOT / "recordings" / "answer.wav"
DEFAULT_VOICE = "en_GB-alba-medium"
VOICES = (
    {"name": "Alba", "language": "British English", "model": DEFAULT_VOICE},
    {"name": "Lessac", "language": "US English", "model": "en_US-lessac-medium"},
)


def list_voices() -> list[dict[str, str]]:
    """These Piper voices are downloaded on first use and then work offline."""
    return list(VOICES)


def spoken_text(answer: str) -> str:
    """Keep citation numbers visible in the answer, but omit them from speech."""
    without_citations = re.sub(r"\[(?:\d+(?:\s*,\s*\d+)*)\]", "", answer)
    plain = re.sub(r"\s+", " ", without_citations.replace("**", ""))
    return re.sub(r"\s+([.,!?;:])", r"\1", plain).strip()


@lru_cache(maxsize=2)
def _load_voice(model: str):
    from piper import PiperVoice
    from piper.download_voices import download_voice

    VOICE_DIR.mkdir(parents=True, exist_ok=True)
    model_path = VOICE_DIR / f"{model}.onnx"
    config_path = VOICE_DIR / f"{model}.onnx.json"
    if not model_path.is_file() or not config_path.is_file():
        download_voice(model, VOICE_DIR)
    return PiperVoice.load(model_path)


def synthesize_speech(
    answer: str,
    output: Path = DEFAULT_OUTPUT,
    voice: str | None = None,
    rate: float = 1.0,
    stop_requested: Callable[[], bool] | None = None,
) -> Path:
    """Create a PCM WAV; rate below 1 is faster and above 1 is slower."""
    from piper import SynthesisConfig

    speech = spoken_text(answer)
    if not speech:
        raise ValueError("There is no answer text to speak.")
    model = voice or DEFAULT_VOICE
    if model not in {item["model"] for item in VOICES}:
        raise ValueError(f"Unknown voice: {model}")
    if not 0.5 <= rate <= 2.0:
        raise ValueError("Speech rate must be between 0.5 and 2.0.")

    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.unlink(missing_ok=True)
    try:
        engine = _load_voice(model)
        with wave.open(str(output), "wb") as wav:
            first_chunk = True
            for chunk in engine.synthesize(speech, syn_config=SynthesisConfig(length_scale=rate)):
                if stop_requested and stop_requested():
                    raise InterruptedError("Speech synthesis stopped.")
                if first_chunk:
                    wav.setframerate(chunk.sample_rate)
                    wav.setsampwidth(chunk.sample_width)
                    wav.setnchannels(chunk.sample_channels)
                    first_chunk = False
                wav.writeframes(chunk.audio_int16_bytes)
            if first_chunk:
                raise RuntimeError("The speech engine returned no audio.")
    except Exception:
        output.unlink(missing_ok=True)
        raise
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("text", nargs="?", help="Text to speak")
    parser.add_argument("--list-voices", action="store_true")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--voice", choices=[item["model"] for item in VOICES], default=DEFAULT_VOICE)
    parser.add_argument("--rate", type=float, default=1.0, help="Length scale: 0.85 fast, 1 normal, 1.2 slow")
    parser.add_argument("--play", action="store_true", help="Play the generated WAV with PyAudio")
    args = parser.parse_args()
    try:
        if args.list_voices:
            for voice in VOICES:
                print(f"{voice['model']} ({voice['language']})")
            return
        if not args.text:
            parser.error("Provide text to speak, or use --list-voices.")
        path = synthesize_speech(args.text, args.output, args.voice, args.rate)
        print(path)
        if args.play:
            from voice_loop import play_audio
            play_audio(path)
    except (OSError, RuntimeError, ValueError) as exc:
        parser.exit(1, f"TTS error: {exc}\n")


if __name__ == "__main__":
    sys.exit(main())
