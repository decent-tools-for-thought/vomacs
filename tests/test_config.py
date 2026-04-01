from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from vomacs import config


class ConfigTests(unittest.TestCase):
    def test_config_dir_prefers_xdg_config_home(self) -> None:
        with mock.patch.dict(
            "os.environ", {"XDG_CONFIG_HOME": "/xdg/config"}, clear=True
        ):
            self.assertEqual(config.config_dir(), Path("/xdg/config/vomacs"))

    def test_config_dir_falls_back_to_home_config(self) -> None:
        with (
            mock.patch.dict("os.environ", {}, clear=True),
            mock.patch("vomacs.config.Path.home", return_value=Path("/home/tester")),
        ):
            self.assertEqual(config.config_dir(), Path("/home/tester/.config/vomacs"))

    def test_default_socket_path_uses_runtime_dir(self) -> None:
        with mock.patch.dict(
            "os.environ", {"XDG_RUNTIME_DIR": "/run/user/1000"}, clear=True
        ):
            self.assertEqual(
                config.default_socket_path(),
                Path("/run/user/1000/vomacs/control.sock"),
            )

    def test_runtime_dir_falls_back_to_tmp_uid(self) -> None:
        with (
            mock.patch.dict("os.environ", {}, clear=True),
            mock.patch("vomacs.config.os.getuid", return_value=1234),
        ):
            self.assertEqual(config.runtime_dir(), Path("/tmp/vomacs-1234/vomacs"))

    def test_load_config_creates_default_and_merges_overrides(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            config_path = base / "config" / "custom.json"
            override = {
                "openai": {"model": "whisper-1"},
                "audio": {"keep_recordings": True},
            }
            config_path.parent.mkdir(parents=True)
            config_path.write_text(json.dumps(override), encoding="utf-8")

            with (
                mock.patch.dict(
                    "os.environ",
                    {
                        "XDG_STATE_HOME": str(base / "state"),
                        "XDG_RUNTIME_DIR": str(base / "runtime"),
                    },
                    clear=True,
                ),
            ):
                merged = config.load_config(config_path)

            self.assertEqual(merged["openai"]["model"], "whisper-1")
            self.assertTrue(merged["audio"]["keep_recordings"])
            self.assertEqual(
                merged["openai"]["realtime"]["sample_rate_hz"],
                config.DEFAULT_CONFIG["openai"]["realtime"]["sample_rate_hz"],
            )
            self.assertTrue((base / "state" / "vomacs").is_dir())
            self.assertTrue((base / "runtime" / "vomacs").is_dir())

    def test_load_config_writes_default_when_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            config_path = base / "config.json"

            with (
                mock.patch.dict(
                    "os.environ",
                    {
                        "XDG_CONFIG_HOME": str(base / "config-home"),
                        "XDG_STATE_HOME": str(base / "state"),
                        "XDG_RUNTIME_DIR": str(base / "runtime"),
                    },
                    clear=True,
                ),
            ):
                loaded = config.load_config(config_path)

            self.assertEqual(loaded, config.DEFAULT_CONFIG)
            self.assertEqual(
                json.loads(config_path.read_text(encoding="utf-8")),
                config.DEFAULT_CONFIG,
            )

    def test_write_default_config_preserves_existing_file_without_force(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            config_path = base / "config.json"
            existing = copy.deepcopy(config.DEFAULT_CONFIG)
            existing["output"]["mode"] = "stdout"
            config_path.write_text(json.dumps(existing), encoding="utf-8")

            with mock.patch.dict(
                "os.environ",
                {
                    "XDG_STATE_HOME": str(base / "state"),
                    "XDG_RUNTIME_DIR": str(base / "runtime"),
                },
                clear=True,
            ):
                path = config.write_default_config(config_path, overwrite=False)

            self.assertEqual(path, config_path)
            self.assertEqual(
                json.loads(config_path.read_text(encoding="utf-8")), existing
            )
