"""Exercise the desktop workflow without starting an audio device or API call."""

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from desktop_app import SpeakRAGWindow


class DesktopWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = SpeakRAGWindow()

    def tearDown(self):
        self.window.close()

    def test_navigation_tracks_three_stages(self):
        self.window.nav_buttons[1].click()
        self.assertEqual(self.window.tabs.currentIndex(), 1)
        self.assertEqual(self.window.step_badge.text(), "STEP 2 OF 3")
        self.assertTrue(self.window.nav_buttons[1].property("active"))

    def test_transcript_moves_to_question(self):
        self.window.current_transcript = {"text": "How do I charge?"}
        self.window._use_transcript()
        self.assertEqual(self.window.tabs.currentIndex(), 2)
        self.assertEqual(self.window.handbook_query.text(), "How do I charge?")

    def test_only_generated_answer_can_be_spoken(self):
        self.window._job_result({"task": "ask", "answer": "Check the manual [1].", "hits": []})
        self.window._set_busy(False)
        self.assertTrue(self.window.speak_answer_button.isEnabled())
        self.window._job_result({"task": "search", "answer": None, "hits": []})
        self.window._set_busy(False)
        self.assertFalse(self.window.speak_answer_button.isEnabled())


if __name__ == "__main__":
    unittest.main()
