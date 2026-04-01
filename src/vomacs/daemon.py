from __future__ import annotations

import json
import os
import socketserver
import tempfile
import threading
import time
import traceback
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

from vomacs import kde
from vomacs.audio import maybe_prepare_upload_audio, start_recording, stop_recording
from vomacs.config import default_socket_path, load_config, state_dir
from vomacs.hooks import hook_list, run_commands, run_text_filters
from vomacs.openai_api import (
    start_realtime_transcription,
    transcribe_file,
    transcription_backend,
)
from vomacs.output import deliver_text, resolve_target


@dataclass
class Session:
    session_id: str
    backend: str
    audio_path: Path
    started_at: float
    target_window: dict[str, Any] | None
    ffmpeg_process: Any | None = None
    realtime_transcriber: Any | None = None


@dataclass
class Controller:
    config_path: Path | None = None
    config: dict[str, Any] = field(init=False)
    lock: threading.RLock = field(default_factory=threading.RLock, init=False)
    phase: str = field(default="idle", init=False)
    session: Session | None = field(default=None, init=False)
    worker: threading.Thread | None = field(default=None, init=False)
    last_result: dict[str, Any] | None = field(default=None, init=False)

    def __post_init__(self) -> None:
        self.config = load_config(self.config_path)

    def handle_request(self, request: dict[str, Any]) -> dict[str, Any]:
        action = request.get("action")
        try:
            if action == "start":
                return self.start()
            if action == "stop":
                return self.stop()
            if action == "toggle":
                return self.toggle()
            if action == "cancel":
                return self.cancel()
            if action == "status":
                return self.status()
            if action == "reload":
                return self.reload()
            return {"ok": False, "error": f"Unknown action: {action}"}
        except Exception as exc:  # pragma: no cover
            return {"ok": False, "error": str(exc)}

    def reload(self) -> dict[str, Any]:
        with self.lock:
            self.config = load_config(self.config_path)
            return {"ok": True, "phase": self.phase}

    def start(self) -> dict[str, Any]:
        with self.lock:
            if self.phase != "idle":
                return {
                    "ok": False,
                    "error": f"Cannot start while phase is {self.phase}",
                }

            session_id = uuid.uuid4().hex
            backend = transcription_backend(self.config)
            audio_path = self._allocate_audio_path(session_id)
            target_window = self._capture_start_target()

            try:
                realtime_transcriber = None
                process = None
                if backend == "realtime":
                    realtime_transcriber = start_realtime_transcription(
                        self.config, audio_path
                    )
                else:
                    process = start_recording(self.config, audio_path)

                session = Session(
                    session_id=session_id,
                    backend=backend,
                    audio_path=audio_path,
                    started_at=time.time(),
                    target_window=target_window,
                    ffmpeg_process=process,
                    realtime_transcriber=realtime_transcriber,
                )
            except Exception:
                self._cleanup_audio(audio_path)
                raise

            self.session = session
            self.phase = "recording"
            self.last_result = None

            env = self._session_env(session, phase="recording")
            run_commands(hook_list(self.config, "recording_started"), env)
            if backend == "realtime":
                run_commands(
                    hook_list(self.config, "transcription_started"),
                    self._session_env(session, phase="transcribing"),
                )
            return {
                "ok": True,
                "phase": self.phase,
                "backend": backend,
                "session_id": session.session_id,
                "audio_path": str(audio_path),
                "target_window": target_window,
            }

    def stop(self) -> dict[str, Any]:
        with self.lock:
            if self.phase != "recording" or not self.session:
                return {"ok": False, "error": "No active recording"}

            session = self.session
            if session.backend == "realtime":
                if not session.realtime_transcriber:
                    return {"ok": False, "error": "Realtime recording is not available"}
                session.realtime_transcriber.stop_capture()
            else:
                if not session.ffmpeg_process:
                    return {"ok": False, "error": "No active recording"}
                stop_recording(session.ffmpeg_process)
                session.ffmpeg_process = None
            self.phase = "processing"

            env = self._session_env(session, phase="processing")
            run_commands(hook_list(self.config, "recording_stopped"), env)

            self.worker = threading.Thread(
                target=self._process_session,
                args=(session,),
                name=f"vomacs-process-{session.session_id}",
                daemon=True,
            )
            self.worker.start()
            return {"ok": True, "phase": self.phase, "session_id": session.session_id}

    def toggle(self) -> dict[str, Any]:
        with self.lock:
            current_phase = self.phase
        if current_phase == "idle":
            return self.start()
        if current_phase == "recording":
            return self.stop()
        return {"ok": False, "error": f"Cannot toggle while phase is {current_phase}"}

    def cancel(self) -> dict[str, Any]:
        with self.lock:
            if self.phase != "recording" or not self.session:
                return {"ok": False, "error": "No active recording"}

            session = self.session
            if session.backend == "realtime" and session.realtime_transcriber:
                session.realtime_transcriber.cancel()
            elif session.ffmpeg_process:
                stop_recording(session.ffmpeg_process)
                session.ffmpeg_process = None

            env = self._session_env(session, phase="idle")
            run_commands(hook_list(self.config, "recording_cancelled"), env)
            self._cleanup_audio(session.audio_path)
            self.session = None
            self.phase = "idle"
            self.last_result = {
                "status": "cancelled",
                "session_id": session.session_id,
            }
            return {"ok": True, "phase": self.phase, "session_id": session.session_id}

    def status(self) -> dict[str, Any]:
        with self.lock:
            payload: dict[str, Any] = {"ok": True, "phase": self.phase}
            if self.session:
                payload["session_id"] = self.session.session_id
                payload["backend"] = self.session.backend
                payload["audio_path"] = str(self.session.audio_path)
                payload["started_at"] = self.session.started_at
                payload["target_window"] = self.session.target_window
                if (
                    self.session.backend == "realtime"
                    and self.session.realtime_transcriber
                ):
                    payload["realtime"] = (
                        self.session.realtime_transcriber.status_snapshot()
                    )
            if self.last_result:
                payload["last_result"] = self.last_result
            return payload

    def _allocate_audio_path(self, session_id: str) -> Path:
        configured_dir = self.config["audio"].get("recordings_dir")
        if configured_dir:
            base_dir = Path(str(configured_dir)).expanduser()
            base_dir.mkdir(parents=True, exist_ok=True)
            return base_dir / f"{session_id}.wav"

        state_dir().mkdir(parents=True, exist_ok=True)
        fd, raw_path = tempfile.mkstemp(
            prefix=f"{session_id}-", suffix=".wav", dir=state_dir()
        )
        os.close(fd)
        return Path(raw_path)

    def _capture_start_target(self) -> dict[str, Any] | None:
        provider = self.config["target"].get("provider")
        if provider == "kde_kwin":
            try:
                return kde.query_active_window()
            except Exception:
                return None
        return None

    def _session_env(
        self,
        session: Session,
        *,
        phase: str,
        transcript: str | None = None,
        target_window: dict[str, Any] | None = None,
        upload_audio_path: Path | None = None,
    ) -> dict[str, str]:
        env = {
            "VT_SESSION_ID": session.session_id,
            "VT_TRANSCRIPTION_BACKEND": session.backend,
            "VT_PHASE": phase,
            "VT_AUDIO_PATH": str(session.audio_path),
            "VT_STARTED_AT_EPOCH": str(session.started_at),
        }
        if upload_audio_path is not None:
            env["VT_UPLOAD_AUDIO_PATH"] = str(upload_audio_path)
        if transcript is not None:
            env["VT_TRANSCRIPT_LENGTH"] = str(len(transcript))
        env.update(kde.target_env(target_window or session.target_window))
        return env

    def _process_session(self, session: Session) -> None:
        if session.backend == "realtime":
            self._process_realtime_session(session)
            return
        self._process_file_session(session)

    def _process_file_session(self, session: Session) -> None:
        target_window = resolve_target(self.config, session.target_window)
        upload_audio_path = session.audio_path
        try:
            env = self._session_env(
                session, phase="preparing", target_window=target_window
            )
            run_commands(self.config["pipelines"].get("before_transcription", []), env)
            upload_audio_path = maybe_prepare_upload_audio(
                self.config, session.audio_path
            )

            env = self._session_env(
                session,
                phase="transcribing",
                target_window=target_window,
                upload_audio_path=upload_audio_path,
            )
            run_commands(hook_list(self.config, "transcription_started"), env)

            transcript = transcribe_file(self.config, upload_audio_path)
            transcript = run_text_filters(
                self.config["pipelines"].get("after_transcription", []),
                transcript,
                self._session_env(
                    session,
                    phase="transcribed",
                    transcript=transcript,
                    target_window=target_window,
                    upload_audio_path=upload_audio_path,
                ),
            ).strip()

            env = self._session_env(
                session,
                phase="transcribed",
                transcript=transcript,
                target_window=target_window,
                upload_audio_path=upload_audio_path,
            )
            run_commands(
                hook_list(self.config, "transcription_finished"),
                env,
                stdin_text=transcript,
            )
            run_commands(
                hook_list(self.config, "output_started"), env, stdin_text=transcript
            )
            deliver_text(self.config, transcript, target=target_window, env=env)
            run_commands(
                hook_list(self.config, "output_finished"), env, stdin_text=transcript
            )

            result = {
                "status": "ok",
                "session_id": session.session_id,
                "backend": session.backend,
                "completed_at": time.time(),
                "target_window": target_window,
                "transcript_preview": transcript[:240],
            }
            with self.lock:
                self.last_result = result
                self.phase = "idle"
                self.session = None
        except Exception as exc:
            error_env = self._session_env(
                session,
                phase="failed",
                target_window=target_window,
                upload_audio_path=upload_audio_path,
            )
            error_env["VT_ERROR"] = str(exc)
            try:
                run_commands(hook_list(self.config, "transcription_failed"), error_env)
                run_commands(hook_list(self.config, "output_failed"), error_env)
            except Exception:
                pass

            with self.lock:
                self.last_result = {
                    "status": "error",
                    "session_id": session.session_id,
                    "backend": session.backend,
                    "completed_at": time.time(),
                    "error": str(exc),
                    "traceback": traceback.format_exc(),
                }
                self.phase = "idle"
                self.session = None
        finally:
            if upload_audio_path != session.audio_path:
                try:
                    upload_audio_path.unlink(missing_ok=True)
                except OSError:
                    pass
            self._cleanup_audio(session.audio_path)

    def _process_realtime_session(self, session: Session) -> None:
        target_window = resolve_target(self.config, session.target_window)
        try:
            if not session.realtime_transcriber:
                raise RuntimeError("Realtime transcription session is not available")

            transcript = session.realtime_transcriber.finalize()
            transcript = run_text_filters(
                self.config["pipelines"].get("after_transcription", []),
                transcript,
                self._session_env(
                    session,
                    phase="transcribed",
                    transcript=transcript,
                    target_window=target_window,
                ),
            ).strip()

            env = self._session_env(
                session,
                phase="transcribed",
                transcript=transcript,
                target_window=target_window,
            )
            run_commands(
                hook_list(self.config, "transcription_finished"),
                env,
                stdin_text=transcript,
            )
            run_commands(
                hook_list(self.config, "output_started"), env, stdin_text=transcript
            )
            deliver_text(self.config, transcript, target=target_window, env=env)
            run_commands(
                hook_list(self.config, "output_finished"), env, stdin_text=transcript
            )

            result = {
                "status": "ok",
                "session_id": session.session_id,
                "backend": session.backend,
                "completed_at": time.time(),
                "target_window": target_window,
                "transcript_preview": transcript[:240],
            }
            with self.lock:
                self.last_result = result
                self.phase = "idle"
                self.session = None
        except Exception as exc:
            error_env = self._session_env(
                session,
                phase="failed",
                target_window=target_window,
            )
            error_env["VT_ERROR"] = str(exc)
            try:
                run_commands(hook_list(self.config, "transcription_failed"), error_env)
                run_commands(hook_list(self.config, "output_failed"), error_env)
            except Exception:
                pass

            with self.lock:
                self.last_result = {
                    "status": "error",
                    "session_id": session.session_id,
                    "backend": session.backend,
                    "completed_at": time.time(),
                    "error": str(exc),
                    "traceback": traceback.format_exc(),
                }
                self.phase = "idle"
                self.session = None
        finally:
            if session.realtime_transcriber:
                session.realtime_transcriber.close()
            self._cleanup_audio(session.audio_path)

    def _cleanup_audio(self, path: Path) -> None:
        if self.config["audio"].get("keep_recordings"):
            return
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass


class ControlHandler(socketserver.StreamRequestHandler):
    def handle(self) -> None:
        line = self.rfile.readline()
        if not line:
            return
        request = json.loads(line.decode("utf-8"))
        server = cast("ControlServer", self.server)
        response = server.controller.handle_request(request)
        self.wfile.write((json.dumps(response) + "\n").encode("utf-8"))


class ControlServer(socketserver.ThreadingUnixStreamServer):
    allow_reuse_address = True

    def __init__(self, socket_path: Path, controller: Controller) -> None:
        self.controller = controller
        self.socket_path = socket_path
        if socket_path.exists():
            socket_path.unlink()
        socket_path.parent.mkdir(parents=True, exist_ok=True)
        super().__init__(str(socket_path), ControlHandler)


def serve_forever(
    config_path: Path | None = None, socket_path: Path | None = None
) -> None:
    controller = Controller(config_path)
    server = ControlServer(socket_path or default_socket_path(), controller)
    try:
        server.serve_forever()
    finally:
        server.server_close()
        if Path(server.socket_path).exists():
            Path(server.socket_path).unlink(missing_ok=True)
