from __future__ import annotations

import unittest

from judge.docker_runner import valid_entrypoint


class EntrypointTests(unittest.TestCase):
    def test_accepts_language_specific_entrypoints(self) -> None:
        self.assertTrue(valid_entrypoint(["python", "main.py"]))
        self.assertTrue(valid_entrypoint(["node", "main.js"]))
        self.assertTrue(valid_entrypoint(["./app"]))

    def test_rejects_missing_or_invalid_entrypoints(self) -> None:
        self.assertFalse(valid_entrypoint(None))
        self.assertFalse(valid_entrypoint([]))
        self.assertFalse(valid_entrypoint([""]))
