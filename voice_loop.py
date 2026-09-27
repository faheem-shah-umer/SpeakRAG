"""Record, inspect, and replay WAV audio for the first SpeakRAG milestone."""

from __future__ import annotations

import argparse
import json
import os
import sys
import wave
from pathlib import Path
from typing import Callable

import librosa
import numpy as np


CHUNK_FRAMES = 1024
SILENCE_DBFS = -40.0
CLIPPING_LEVEL = 0.999


def _pyaudio():
    try:
        import pyaudio
    except ImportError as exc:
        raise RuntimeError("PyAudio is missing. Install the packages in requirements.txt.") from exc
    return pyaudio


def list_devices() -> None:
    for device in get_audio_devices():
        print(
            f"{device['index']:>3}  {device['name']}  "
            f"input={device['maxInputChannels']}  "
            f"output={device['maxOutputChannels']}  "
            f"default_rate={device['defaultSampleRate']:.0f} Hz"
        )


def get_audio_devices() -> list[dict]:
    pyaudio = _pyaudio()
    audio = pyaudio.PyAudio()
    try:
        devices = []
        for index in range(audio.get_device_count()):
            device = audio.get_device_info_by_index(index)
            if device["maxInputChannels"] or device["maxOutputChannels"]:
                devices.append(device)
        return devices
    finally:
        audio.terminate()


def record_audio(
    output: Path,
    seconds: float,
    sample_rate: int | None = None,
    channels: int = 1,
    input_device: int | None = None,
    stop_requested: Callable[[], bool] | None = None,
    on_progress: Callable[[float], None] | None = None,
) -> Path:
    if seconds <= 0 or (sample_rate is not None and sample_rate <= 0) or channels <= 0:
        raise ValueError("Duration, sample rate, and channel count must be positive.")

    pyaudio = _pyaudio()
    audio = pyaudio.PyAudio()
    stream = None
    frames: list[bytes] = []
    try:
        device = (
            audio.get_default_input_device_info()
            if input_device is None
            else audio.get_device_info_by_index(input_device)
        )
        recording_rate = sample_rate or round(device["defaultSampleRate"])
        stream = audio.open(
            format=pyaudio.paInt16,
            channels=channels,
            rate=recording_rate,
            input=True,
            input_device_index=input_device,
            frames_per_buffer=CHUNK_FRAMES,
        )
        total = round(seconds * recording_rate)
        remaining = total
        while remaining and not (stop_requested and stop_requested()):
            count = min(CHUNK_FRAMES, remaining)
            frames.append(stream.read(count))
            remaining -= count
            if on_progress:
                on_progress((total - remaining) / total)
    finally:
        if stream is not None:
            stream.stop_stream()
            stream.close()
        audio.terminate()

    if not frames:
        raise RuntimeError("Recording stopped before any audio was captured.")
    output.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(output), "wb") as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(2)
        wav.setframerate(recording_rate)
        wav.writeframes(b"".join(frames))
    return output


def play_audio(
    path: Path,
    output_device: int | None = None,
    stop_requested: Callable[[], bool] | None = None,
) -> None:
    pyaudio = _pyaudio()
    audio = pyaudio.PyAudio()
    stream = None
    try:
        with wave.open(str(path), "rb") as wav:
            if wav.getcomptype() != "NONE":
                raise ValueError("Playback supports uncompressed PCM WAV files only.")
            stream = audio.open(
                format=audio.get_format_from_width(wav.getsampwidth()),
                channels=wav.getnchannels(),
                rate=wav.getframerate(),
                output=True,
                output_device_index=output_device,
                frames_per_buffer=CHUNK_FRAMES,
            )
            while chunk := wav.readframes(CHUNK_FRAMES):
                if stop_requested and stop_requested():
                    break
                stream.write(chunk)
    finally:
        if stream is not None:
            stream.stop_stream()
            stream.close()
        audio.terminate()


def _dbfs(level: float) -> float | None:
    return round(20 * np.log10(level), 2) if level > 0 else None


def analyse_audio(path: Path) -> dict[str, float | int | None]:
    with wave.open(str(path), "rb") as wav:
        if wav.getcomptype() != "NONE":
            raise ValueError("Analysis supports uncompressed PCM WAV files only.")
        bit_depth = wav.getsampwidth() * 8
        channels = wav.getnchannels()

    # sr=None preserves the file's sample rate; mono=False preserves its channels.
    samples, sample_rate = librosa.load(path, sr=None, mono=False)
    if samples.size == 0:
        raise ValueError("The WAV file contains no audio samples.")
    mono = samples.mean(axis=0) if samples.ndim == 2 else samples
    peak = float(np.max(np.abs(samples)))
    rms = float(np.sqrt(np.mean(np.square(samples, dtype=np.float64))))
    clipping_percent = float(np.mean(np.abs(samples) >= CLIPPING_LEVEL) * 100)
    frame_rms = librosa.feature.rms(
        y=mono, frame_length=1024, hop_length=512, center=True
    )[0]
    silence_level = 10 ** (SILENCE_DBFS / 20)

    return {
        "sample_rate_hz": sample_rate,
        "channels": channels,
        "bit_depth": bit_depth,
        "duration_seconds": round(mono.size / sample_rate, 3),
        "peak_dbfs": _dbfs(peak),
        "rms_dbfs": _dbfs(rms),
        "crest_factor_db": round(20 * np.log10(peak / rms), 2) if rms else None,
        "dc_offset": round(float(np.mean(mono)), 6),
        "clipped_samples_percent": round(clipping_percent, 3),
        "silent_frames_percent": round(float(np.mean(frame_rms < silence_level) * 100), 1),
        "silence_threshold_dbfs": SILENCE_DBFS,
    }


def save_plot(path: Path, output: Path) -> None:
    os.environ.setdefault("MPLCONFIGDIR", str(Path(__file__).resolve().parent / ".mplconfig"))
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure

    samples, sample_rate = librosa.load(path, sr=None, mono=True)
    if samples.size == 0:
        raise ValueError("The WAV file contains no audio samples.")
    times = np.arange(samples.size) / sample_rate
    spectrum = librosa.amplitude_to_db(
        np.abs(librosa.stft(samples)), ref=np.max
    )

    figure = Figure(figsize=(12, 4.4), layout="constrained", facecolor="#10191f")
    FigureCanvasAgg(figure)
    axes = figure.subplots(2, 1)
    for axis in axes:
        axis.set_facecolor("#10191f")
        axis.tick_params(colors="#a9b9b1", labelsize=11)
        axis.title.set_color("#f6f2e9")
        axis.xaxis.label.set_color("#a9b9b1")
        axis.yaxis.label.set_color("#a9b9b1")
        for spine in axis.spines.values():
            spine.set_color("#3a5158")
    axes[0].plot(times, samples, color="#d6eab9", linewidth=0.7)
    axes[0].set(xlabel="Time (s)", ylabel="Amplitude", title="Waveform", ylim=(-1.05, 1.05))
    axes[0].grid(color="#315058", alpha=0.55)
    image = axes[1].imshow(
        spectrum,
        origin="lower",
        aspect="auto",
        extent=(0, samples.size / sample_rate, 0, sample_rate / 2),
        cmap="magma",
        vmin=-80,
        vmax=0,
    )
    axes[1].set(xlabel="Time (s)", ylabel="Frequency (Hz)", title="Spectrogram")
    colorbar = figure.colorbar(image, ax=axes[1])
    colorbar.ax.tick_params(colors="#a9b9b1", labelsize=10)
    colorbar.set_label("dB relative to peak", color="#a9b9b1")
    output.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output, dpi=150, facecolor=figure.get_facecolor())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("devices", help="List microphone and speaker devices")

    record = commands.add_parser("record", help="Record a PCM WAV file")
    loop = commands.add_parser("loop", help="Record, analyse, and replay audio")
    for command in (record, loop):
        command.add_argument("--output", type=Path, default=Path("recordings/voice.wav"))
        command.add_argument("--seconds", type=float, default=5.0)
        command.add_argument("--sample-rate", type=int, help="Hz; defaults to the device's native rate")
        command.add_argument("--channels", type=int, default=1)
        command.add_argument("--input-device", type=int)
    loop.add_argument("--output-device", type=int)
    loop.add_argument("--plot", type=Path, help="Save a waveform and spectrogram PNG")

    play = commands.add_parser("play", help="Replay a PCM WAV file")
    play.add_argument("file", type=Path)
    play.add_argument("--output-device", type=int)

    analyse = commands.add_parser("analyse", help="Inspect a PCM WAV file")
    analyse.add_argument("file", type=Path)
    analyse.add_argument("--plot", type=Path, help="Save a waveform and spectrogram PNG")

    args = parser.parse_args(argv)
    try:
        if args.command == "devices":
            list_devices()
        elif args.command == "record":
            print("Recording...", flush=True)
            path = record_audio(
                args.output, args.seconds, args.sample_rate, args.channels, args.input_device
            )
            print(f"Saved {path}")
        elif args.command == "play":
            print("Playing...", flush=True)
            play_audio(args.file, args.output_device)
        elif args.command == "analyse":
            print(json.dumps(analyse_audio(args.file), indent=2))
            if args.plot:
                save_plot(args.file, args.plot)
                print(f"Saved {args.plot}")
        elif args.command == "loop":
            print("Recording...", flush=True)
            path = record_audio(
                args.output, args.seconds, args.sample_rate, args.channels, args.input_device
            )
            print(f"Saved {path}")
            print(json.dumps(analyse_audio(path), indent=2))
            if args.plot:
                save_plot(path, args.plot)
                print(f"Saved {args.plot}")
            print("Playing...", flush=True)
            play_audio(path, args.output_device)
    except (OSError, ValueError, RuntimeError) as exc:
        parser.exit(1, f"Audio error: {exc}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
