from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from judge.config import load_paths, resolve_runtime_config
from judge.scorer import score_answers


class ConfigAndScoringTests(unittest.TestCase):
    @patch.dict(os.environ, {"OPENROUTER_API_KEY": "env-key", "OPENROUTER_MODEL": "env-model", "OPENROUTER_BASE_URL": "env-url"})
    def test_runtime_precedence(self) -> None:
        config = {
            "defaults": {"openrouter_key": "default-key", "openrouter_model": "default-model"},
            "solutions": {"team": {"openrouter_key": "team-key"}},
        }
        resolved = resolve_runtime_config("team", config, "cli-key", "cli-model", "cli-url")
        self.assertEqual(resolved.openrouter_key, "team-key")
        self.assertEqual(resolved.openrouter_model, "default-model")
        self.assertEqual(resolved.openrouter_base_url, "cli-url")

    def test_exact_match_is_strict(self) -> None:
        correct, audit = score_answers({"1": "Ngo", "2": "11"}, {"1": "ngo", "2": "11"})
        self.assertEqual(correct, 1)
        self.assertEqual(audit, [{"id": "1", "correct": False}, {"id": "2", "correct": True}])

    def test_paths_are_relative_to_judge_config(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config_dir = root / "config"
            config_dir.mkdir()
            config = config_dir / "judge.toml"
            config.write_text('[paths]\nsolutions = "../solutions"\nresults = "../results"\n', encoding="utf-8")
            paths = load_paths(config)
            self.assertEqual(paths["solutions"], root / "solutions")
            self.assertEqual(paths["results"], root / "results")
