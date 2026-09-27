import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

import numpy as np

from voice_loop import analyse_audio, record_audio, save_plot


class AudioAnalysisTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.directory = Path(self.temp_dir.name)

    def write_wav(self, name, samples, sample_rate=16_000):
        path = self.directory / name
        with wave.open(str(path), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(sample_rate)
            wav.writeframes(samples.astype("<i2").tobytes())
        return path

    def test_sine_wave_has_expected_metadata_and_levels(self):
        time = np.arange(16_000) / 16_000
        samples = np.round(0.2 * 32767 * np.sin(2 * np.pi * 440 * time))
        report = analyse_audio(self.write_wav("tone.wav", samples))

        self.assertEqual(report["sample_rate_hz"], 16_000)
        self.assertEqual(report["channels"], 1)
        self.assertEqual(report["bit_depth"], 16)
        self.assertEqual(report["duration_seconds"], 1)
        self.assertAlmostEqual(report["peak_dbfs"], -13.98, delta=0.1)
        self.assertAlmostEqual(report["rms_dbfs"], -17.0, delta=0.1)
        self.assertEqual(report["clipped_samples_percent"], 0)
        self.assertLess(report["silent_frames_percent"], 5)

    def test_silence_and_clipping_are_reported(self):
        silent = analyse_audio(self.write_wav("silent.wav", np.zeros(16_000)))
        clipped = analyse_audio(
            self.write_wav("clipped.wav", np.full(16_000, 32767))
        )

        self.assertIsNone(silent["peak_dbfs"])
        self.assertEqual(silent["silent_frames_percent"], 100)
        self.assertEqual(clipped["clipped_samples_percent"], 100)

    def test_plot_is_saved(self):
        tone = self.write_wav("plot.wav", np.zeros(4_000))
        output = self.directory / "plot.png"
        save_plot(tone, output)
        self.assertGreater(output.stat().st_size, 0)

    def test_recording_stop_writes_only_captured_frames(self):
        class InputStream:
            reads = 0

            def read(self, count):
                self.reads += 1
                return bytes(count * 2)

            def stop_stream(self):
                pass

            def close(self):
                pass

        class Audio:
            def get_default_input_device_info(self):
                return {"defaultSampleRate": 16_000}

            def open(self, **kwargs):
                return stream

            def terminate(self):
                pass

        class FakePyAudio:
            paInt16 = 8

            @staticmethod
            def PyAudio():
                return Audio()

        stream = InputStream()
        output = self.directory / "stopped.wav"
        with patch("voice_loop._pyaudio", return_value=FakePyAudio):
            record_audio(output, 2, stop_requested=lambda: stream.reads > 0)

        with wave.open(str(output), "rb") as wav:
            self.assertEqual(wav.getnframes(), 1024)
        self.assertEqual(stream.reads, 1)


if __name__ == "__main__":
    unittest.main()
