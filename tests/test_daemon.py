from __future__ import annotations

import copy
import unittest
from pathlib import Path
from unittest import mock

from vomacsd.config import DEFAULT_CONFIG
from vomacsd.daemon import Controller, Session


class DaemonTests(unittest.TestCase):
    def _controller(self) -> Controller:
        with mock.patch(
            "vomacsd.daemon.load_config", return_value=copy.deepcopy(DEFAULT_CONFIG)
        ):
            return Controller(config_path=Path("/tmp/config.json"))

    def test_handle_request_routes_known_action(self) -> None:
        controller = self._controller()
        with mock.patch.object(
            controller, "start", return_value={"ok": True, "phase": "recording"}
        ):
            response = controller.handle_request({"action": "start"})

        self.assertEqual(response, {"ok": True, "phase": "recording"})

    def test_handle_request_rejects_unknown_action(self) -> None:
        controller = self._controller()
        response = controller.handle_request({"action": "nope"})
        self.assertEqual(response, {"ok": False, "error": "Unknown action: nope"})

    def test_toggle_starts_when_idle(self) -> None:
        controller = self._controller()
        with mock.patch.object(controller, "start", return_value={"ok": True}) as start:
            response = controller.toggle()

        self.assertEqual(response, {"ok": True})
        start.assert_called_once_with()

    def test_toggle_stops_when_recording(self) -> None:
        controller = self._controller()
        controller.phase = "recording"
        with mock.patch.object(controller, "stop", return_value={"ok": True}) as stop:
            response = controller.toggle()

        self.assertEqual(response, {"ok": True})
        stop.assert_called_once_with()

    def test_toggle_rejects_other_phases(self) -> None:
        controller = self._controller()
        controller.phase = "processing"
        response = controller.toggle()
        self.assertEqual(
            response, {"ok": False, "error": "Cannot toggle while phase is processing"}
        )

    def test_status_includes_session_and_last_result(self) -> None:
        controller = self._controller()
        controller.phase = "recording"
        controller.session = Session(
            session_id="abc123",
            backend="realtime",
            audio_path=Path("/tmp/audio.wav"),
            started_at=12.5,
            target_window={"caption": "Editor"},
            realtime_transcriber=mock.Mock(
                status_snapshot=mock.Mock(return_value={"segments": 1})
            ),
        )
        controller.last_result = {"status": "ok"}

        status = controller.status()

        self.assertEqual(status["phase"], "recording")
        self.assertEqual(status["session_id"], "abc123")
        self.assertEqual(status["realtime"], {"segments": 1})
        self.assertEqual(status["last_result"], {"status": "ok"})
