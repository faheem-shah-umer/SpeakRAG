import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from asr import transcribe_audio


class ASRTests(unittest.TestCase):
    def test_transcription_collects_segments_and_text(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "spoken.wav"
            path.write_bytes(b"placeholder")
            segments = iter(
                [
                    SimpleNamespace(start=0.0, end=1.2, text=" Hello"),
                    SimpleNamespace(start=1.2, end=2.0, text=" world."),
                ]
            )
            model = SimpleNamespace(
                transcribe=lambda *args, **kwargs: (
                    segments,
                    SimpleNamespace(language="en"),
                )
            )
            with patch("asr._model", return_value=model):
                result = transcribe_audio(path)

        self.assertEqual(result["text"], "Hello world.")
        self.assertEqual(len(result["segments"]), 2)
        self.assertEqual(result["segments"][0]["start"], 0.0)
        self.assertEqual(result["language"], "en")
        self.assertGreaterEqual(result["model_load_seconds"], 0)
        self.assertGreaterEqual(result["transcription_seconds"], 0)

    def test_missing_file_is_rejected_before_loading_model(self):
        with patch("asr._model") as load:
            with self.assertRaisesRegex(ValueError, "existing WAV"):
                transcribe_audio(Path("missing.wav"))
            load.assert_not_called()


if __name__ == "__main__":
    unittest.main()
