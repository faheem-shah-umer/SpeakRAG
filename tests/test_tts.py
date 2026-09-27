"""Check that spoken answers remain readable and omit visual citations."""

import unittest

from tts import spoken_text, synthesize_speech


class SpeechTextTests(unittest.TestCase):
    def test_citation_markers_are_not_spoken(self):
        answer = "**Check the charging cable** [1, 2].\nThen try again [3]."
        self.assertEqual(spoken_text(answer), "Check the charging cable. Then try again.")

    def test_empty_speech_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "no answer text"):
            synthesize_speech("[1]")


if __name__ == "__main__":
    unittest.main()
