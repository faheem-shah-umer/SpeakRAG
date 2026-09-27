"""Check answer-provider wiring without sending handbook text to a cloud API."""

import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from handbook_rag import _generate, make_prompt


class HandbookGenerationTests(unittest.TestCase):
    def setUp(self):
        self.messages = make_prompt("How does charging work?", [{
            "title": "Sample manual", "pdf_page": 12, "text": "Connect the charger."
        }])

    @patch("openai.OpenAI")
    def test_openai_uses_configured_model_and_returns_text(self, client_type):
        client_type.return_value.chat.completions.create.return_value = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="Connect it [1]."))]
        )
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key", "OPENAI_MODEL": "test-model"}, clear=True):
            answer = _generate(self.messages)
        self.assertEqual(answer, "Connect it [1].")
        client_type.return_value.chat.completions.create.assert_called_once_with(
            model="test-model", messages=self.messages
        )

    @patch("openai.AzureOpenAI")
    def test_azure_uses_deployment(self, client_type):
        client_type.return_value.chat.completions.create.return_value = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="Use page 12 [1]."))]
        )
        settings = {
            "AZURE_OPENAI_ENDPOINT": "https://example.openai.azure.com/",
            "AZURE_OPENAI_API_KEY": "test-key",
            "AZURE_OPENAI_API_VERSION": "test-version",
            "AZURE_OPENAI_CHAT_DEPLOYMENT": "test-deployment",
        }
        with patch.dict(os.environ, settings, clear=True):
            answer = _generate(self.messages)
        self.assertEqual(answer, "Use page 12 [1].")
        client_type.return_value.chat.completions.create.assert_called_once_with(
            model="test-deployment", messages=self.messages
        )


if __name__ == "__main__":
    unittest.main()
