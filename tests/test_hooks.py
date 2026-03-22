from __future__ import annotations

import subprocess
import unittest
from unittest import mock

from vomacsd import hooks


class HooksTests(unittest.TestCase):
    def test_hook_list_returns_stringified_commands(self) -> None:
        config = {"hooks": {"recording_started": ["echo one", 2]}}
        self.assertEqual(
            hooks.hook_list(config, "recording_started"), ["echo one", "2"]
        )

    def test_hook_list_rejects_non_list_values(self) -> None:
        with self.assertRaises(TypeError):
            hooks.hook_list(
                {"hooks": {"recording_started": "echo one"}}, "recording_started"
            )

    def test_run_commands_passes_env_and_stdin(self) -> None:
        with mock.patch("subprocess.run") as run:
            hooks.run_commands(
                ["echo ready"], {"VT_PHASE": "recording"}, stdin_text="hello"
            )

        run.assert_called_once()
        kwargs = run.call_args.kwargs
        self.assertEqual(kwargs["input"], "hello")
        self.assertEqual(kwargs["env"]["VT_PHASE"], "recording")

    def test_run_text_filters_chains_stdout(self) -> None:
        with mock.patch(
            "subprocess.run",
            side_effect=[
                subprocess.CompletedProcess(args=[], returncode=0, stdout="first\n"),
                subprocess.CompletedProcess(args=[], returncode=0, stdout="second\n"),
            ],
        ) as run:
            result = hooks.run_text_filters(
                ["cmd1", "cmd2"], "seed", {"VT_PHASE": "testing"}
            )

        self.assertEqual(result, "second\n")
        first_input = run.call_args_list[0].kwargs["input"]
        second_input = run.call_args_list[1].kwargs["input"]
        self.assertEqual(first_input, "seed")
        self.assertEqual(second_input, "first\n")
