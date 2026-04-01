from __future__ import annotations

import io
import unittest
from unittest import mock

from vomacs import output


class OutputTests(unittest.TestCase):
    def test_resolve_target_returns_start_target_for_start_mode(self) -> None:
        config = {"target": {"provider": "kde_kwin", "mode": "focused_on_start"}}
        target = {"caption": "Editor"}
        self.assertEqual(output.resolve_target(config, target), target)

    def test_resolve_target_falls_back_to_start_target_on_kde_error(self) -> None:
        config = {"target": {"provider": "kde_kwin", "mode": "focused_on_finish"}}
        target = {"caption": "Editor"}
        with mock.patch(
            "vomacs.output.kde.query_active_window", side_effect=RuntimeError("boom")
        ):
            self.assertEqual(output.resolve_target(config, target), target)

    def test_deliver_text_stdout_prints_text(self) -> None:
        stdout = io.StringIO()
        with mock.patch("sys.stdout", stdout):
            output.deliver_text(
                {"output": {"mode": "stdout"}}, "hello", target=None, env={}
            )

        self.assertEqual(stdout.getvalue(), "hello\n")

    def test_deliver_text_clipboard_then_command_runs_both(self) -> None:
        with (
            mock.patch("vomacs.output._set_clipboard") as set_clipboard,
            mock.patch("vomacs.output._run_output_command") as run_output_command,
        ):
            output.deliver_text(
                {"output": {"mode": "clipboard_then_command", "command": "cat"}},
                "hello",
                target={"caption": "Editor"},
                env={"VT_PHASE": "done"},
            )

        set_clipboard.assert_called_once()
        run_output_command.assert_called_once()

    def test_run_output_command_requires_command(self) -> None:
        with self.assertRaises(RuntimeError):
            output._run_output_command({}, "hello", {"VT_PHASE": "done"}, None)

    def test_run_output_command_merges_target_env(self) -> None:
        with (
            mock.patch(
                "vomacs.output.kde.target_env", return_value={"VT_TARGET_UUID": "123"}
            ),
            mock.patch("subprocess.run") as run,
        ):
            output._run_output_command(
                {"command": "cat >/dev/null"},
                "hello",
                {"VT_PHASE": "done"},
                {"uuid": "123"},
            )

        kwargs = run.call_args.kwargs
        self.assertEqual(kwargs["input"], "hello")
        self.assertEqual(kwargs["env"]["VT_PHASE"], "done")
        self.assertEqual(kwargs["env"]["VT_TARGET_UUID"], "123")
