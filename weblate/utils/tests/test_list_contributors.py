# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import Mock, patch

from django.test import SimpleTestCase
from git import Actor, Commit

if TYPE_CHECKING:
    from types import ModuleType


def load_list_contributors_module() -> ModuleType:
    script = Path(__file__).resolve().parents[3] / "scripts" / "list-contributors.py"
    spec = importlib.util.spec_from_file_location("list_contributors", script)
    if spec is None or spec.loader is None:
        msg = "Could not load list-contributors.py"
        raise RuntimeError(msg)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ListContributorsTest(SimpleTestCase):
    def test_nonhuman_authors_are_excluded(self) -> None:
        module = load_list_contributors_module()
        for author in (
            "Deleted User",
            "Codex",
            "GPT",
            "ChatGPT",
            "DeepSeek",
            "Qwen",
            "Claude Sonnet 5",
            "Claude Opus 5.5",
            "Claude Haiku 4.5",
            "claude fable 5.1",
            "Claude 3.5 Sonnet",
            "GPT-4o",
            "GPT-5.4-mini",
            "ChatGPT 5",
            "Codex 5.3",
            "Gemini 2.5 Pro",
            "Grok 3",
            "Grok-4",
            "DeepSeek V3",
            "DeepSeek R1",
            "DeepSeek-R1",
            "deepseek r1",
            "Llama 3.1",
            "Qwen 2.5",
            "Qwen2.5",
            "Qwen2.5-Coder",
            "DeepSeekR1",
            "GPT4o",
            "Mistral Large 3",
            "Mistral-7B-Instruct-v0.3",
            "Mistral 7B Instruct v0.3",
            "Anthropic Claude 3.5 Sonnet",
            "Google Gemini 2.5 Pro",
            "OpenAI GPT-4o",
            "OpenAI Codex 5.3",
            "xAI Grok 4",
            "Meta Llama 3.1",
            "Alibaba Qwen2.5-Coder",
            "Mistral AI Mistral-7B-Instruct-v0.3",
        ):
            for name in (author, author.lower(), author.upper()):
                with self.subTest(author=name):
                    self.assertFalse(module.is_valid_author(name))

    def test_existing_bot_authors_are_excluded(self) -> None:
        module = load_list_contributors_module()
        for author in (
            "GitHub",
            "Copilot",
            "dependabot[bot]",
            "Translator (bot)",
            "Weblate add-on",
        ):
            with self.subTest(author=author):
                self.assertFalse(module.is_valid_author(author))

    def test_human_authors_are_retained(self) -> None:
        module = load_list_contributors_module()
        for author in (
            "Claude",
            "Claude Monet",
            "Claudette",
            "Gemini Smith",
            "Grok",
            "Mistral",
            "Jane Doe",
            "user123",
            "Jane Claude Sonnet 5",
            "Deleted User Smith",
            "Codex Smith",
            "Qwen Smith",
            "Jane Mistral-7B-Instruct-v0.3",
            "Jane OpenAI GPT-4o",
            "Anthropic Claude Monet",
            "Google Gemini Smith",
        ):
            with self.subTest(author=author):
                self.assertTrue(module.is_valid_author(author))

    def test_commit_authors_are_filtered(self) -> None:
        module = load_list_contributors_module()
        commit = Mock(
            spec=Commit,
            author=Actor("Claude Monet", "claude@example.com"),
            committer=Actor("Claude Sonnet 5", "noreply@anthropic.com"),
            message=(
                "Improve translations\n\n"
                "Co-Authored-By: Claude  Opus 5.5 <noreply@anthropic.com>\n"
                "Co-authored-by: Deleted User <deleted@example.com>\n"
                "Co-authored-by: Claude Monet <claude@example.com>\n"
                "Co-authored-by: nijel <michal@weblate.org>\n"
            ),
        )

        self.assertEqual(
            module.get_commit_authors(commit), {"Claude Monet", "Michal Čihař"}
        )

    def test_unversioned_llm_commit_authors_are_filtered(self) -> None:
        module = load_list_contributors_module()
        commit = Mock(
            spec=Commit,
            author=Actor("codex", "codex@openai.com"),
            committer=Actor("CODEX", "codex@openai.com"),
            message=(
                "Improve translations\n\n"
                "Co-authored-by: deleted user <deleted@example.com>\n"
                "Co-authored-by: Qwen2.5-Coder <model@example.com>\n"
                "Co-authored-by: Mistral-7B-Instruct-v0.3 <model@example.com>\n"
                "Co-authored-by: Anthropic Claude 3.5 Sonnet <model@example.com>\n"
                "Co-authored-by: Claude Monet <claude@example.com>\n"
            ),
        )

        self.assertEqual(module.get_commit_authors(commit), {"Claude Monet"})

    def test_contributor_names_are_escaped(self) -> None:
        module = load_list_contributors_module()
        contributors = {
            "code": ["Jane *Doe*", "John_Doe", "Doe, Jane"],
            "translations": [],
            "docs": [],
        }

        with patch.object(module, "get_contributors", return_value=contributors):
            output = module.get_contributors_text()

        self.assertIn(r"Jane \*Doe\*, John\_Doe, Doe\, Jane", output)
