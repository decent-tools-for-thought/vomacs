from __future__ import annotations

import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from vomacs import cli


class CliTests(unittest.TestCase):
    def test_main_without_command_prints_help(self) -> None:
        stdout = io.StringIO()
        with mock.patch("sys.stdout", stdout):
            result = cli.main([])

        self.assertEqual(result, 0)
        self.assertIn("vomacs", stdout.getvalue())

    def test_print_default_config_outputs_json(self) -> None:
        stdout = io.StringIO()
        with mock.patch("sys.stdout", stdout):
            result = cli.main(["print-default-config"])

        self.assertEqual(result, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["openai"]["backend"], "file")

    def test_init_config_prints_created_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.json"
            stdout = io.StringIO()
            with (
                mock.patch("sys.stdout", stdout),
                mock.patch(
                    "vomacs.cli.write_default_config", return_value=config_path
                ) as write_default,
            ):
                result = cli.main(
                    ["--config", str(config_path), "init-config", "--force"]
                )

        self.assertEqual(result, 0)
        write_default.assert_called_once_with(config_path, overwrite=True)
        self.assertEqual(stdout.getvalue().strip(), str(config_path))

    def test_serve_delegates_to_daemon(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.json"
            socket_path = Path(tmpdir) / "control.sock"
            with mock.patch("vomacs.cli.serve_forever") as serve_forever:
                result = cli.main(
                    [
                        "--config",
                        str(config_path),
                        "--socket",
                        str(socket_path),
                        "serve",
                    ]
                )

        self.assertEqual(result, 0)
        serve_forever.assert_called_once_with(
            config_path=config_path, socket_path=socket_path
        )

    def test_command_prints_response_and_uses_exit_code(self) -> None:
        stdout = io.StringIO()
        with (
            mock.patch("sys.stdout", stdout),
            mock.patch(
                "vomacs.cli._send", return_value={"ok": True, "phase": "idle"}
            ) as send,
        ):
            result = cli.main(["status"])

        self.assertEqual(result, 0)
        send.assert_called_once()
        self.assertEqual(json.loads(stdout.getvalue()), {"ok": True, "phase": "idle"})

    def test_missing_socket_reports_actionable_error(self) -> None:
        stderr = io.StringIO()
        with (
            mock.patch("sys.stderr", stderr),
            mock.patch("vomacs.cli._send", side_effect=FileNotFoundError),
        ):
            result = cli.main(["status"])

        self.assertEqual(result, 1)
        self.assertIn("Daemon socket not found", stderr.getvalue())
        self.assertIn("serve", stderr.getvalue())

    def test_connection_refused_reports_error(self) -> None:
        stderr = io.StringIO()
        with (
            mock.patch("sys.stderr", stderr),
            mock.patch("vomacs.cli._send", side_effect=ConnectionRefusedError),
        ):
            result = cli.main(["status"])

        self.assertEqual(result, 1)
        self.assertIn("Could not connect to daemon socket", stderr.getvalue())

    def test_permission_error_reports_tmp_hint(self) -> None:
        stderr = io.StringIO()
        with (
            mock.patch("sys.stderr", stderr),
            mock.patch("vomacs.cli._send", side_effect=PermissionError),
        ):
            result = cli.main(["status"])

        self.assertEqual(result, 1)
        self.assertIn("prefer a socket path under /tmp", stderr.getvalue())

    def test_send_round_trips_json_payload(self) -> None:
        client = mock.MagicMock()
        client.recv.return_value = b'{"ok": true, "phase": "idle"}'
        client.__enter__.return_value = client
        with mock.patch("socket.socket", return_value=client):
            response = cli._send(Path("/tmp/control.sock"), {"action": "status"})

        self.assertEqual(response, {"ok": True, "phase": "idle"})
        client.connect.assert_called_once_with("/tmp/control.sock")
        client.sendall.assert_called_once_with(b'{"action": "status"}\n')
