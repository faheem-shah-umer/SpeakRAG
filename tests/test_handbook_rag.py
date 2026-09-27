"""Check OpenRouter request wiring without sending real handbook text."""

import os
import unittest
from unittest.mock import patch

from handbook_rag import OPENROUTER_MODEL, OPENROUTER_URL, _generate, make_prompt


class HandbookGenerationTests(unittest.TestCase):
    def setUp(self):
        self.messages = make_prompt("How does charging work?", [{
            "title": "Sample manual", "pdf_page": 12, "text": "Connect the charger."
        }])

    @patch("handbook_rag.load_dotenv")
    @patch("handbook_rag.requests.post")
    def test_lowercase_env_key_sends_reasoning_request(self, post, _load_dotenv):
        post.return_value.ok = True
        post.return_value.json.return_value = {
            "choices": [{"message": {"content": "Connect it [1].", "reasoning_details": []}}]
        }
        with patch.dict(os.environ, {"openrouter": "test-key"}, clear=True):
            answer = _generate(self.messages)
        self.assertEqual(answer, "Connect it [1].")
        post.assert_called_once_with(
            OPENROUTER_URL,
            headers={"Authorization": "Bearer test-key"},
            json={
                "model": OPENROUTER_MODEL,
                "messages": self.messages,
                "reasoning": {"enabled": True},
                "max_tokens": 2048,
            },
            timeout=(10, 120),
        )

    @patch("handbook_rag.load_dotenv")
    @patch("handbook_rag.requests.post")
    def test_canonical_env_key_is_accepted(self, post, _load_dotenv):
        post.return_value.ok = True
        post.return_value.json.return_value = {
            "choices": [{"message": {"content": "Use page 12 [1]."}}]
        }
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key"}, clear=True):
            self.assertEqual(_generate(self.messages), "Use page 12 [1].")

    @patch("handbook_rag.load_dotenv")
    @patch("handbook_rag.requests.post")
    def test_missing_key_does_not_call_api(self, post, _load_dotenv):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(ValueError, "OPENROUTER_API_KEY"):
                _generate(self.messages)
        post.assert_not_called()


if __name__ == "__main__":
    unittest.main()
