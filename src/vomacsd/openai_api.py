from __future__ import annotations

import base64
import json
import mimetypes
import os
import threading
import time
import urllib.error
import urllib.request
import uuid
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from vomacsd.audio import pcm_chunk_size_bytes, start_pcm_stream, stop_recording


def _multipart_body(
    *,
    fields: dict[str, str],
    files: list[tuple[str, str, bytes, str]],
) -> tuple[str, bytes]:
    boundary = f"----vomacsd-{uuid.uuid4().hex}"
    body = bytearray()

    for name, value in fields.items():
        body.extend(f"--{boundary}\r\n".encode("utf-8"))
        body.extend(
            f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("utf-8")
        )
        body.extend(value.encode("utf-8"))
        body.extend(b"\r\n")

    for field_name, filename, content, content_type in files:
        body.extend(f"--{boundary}\r\n".encode("utf-8"))
        body.extend(
            (
                f'Content-Disposition: form-data; name="{field_name}"; '
                f'filename="{filename}"\r\n'
            ).encode("utf-8")
        )
        body.extend(f"Content-Type: {content_type}\r\n\r\n".encode("utf-8"))
        body.extend(content)
        body.extend(b"\r\n")

    body.extend(f"--{boundary}--\r\n".encode("utf-8"))
    return f"multipart/form-data; boundary={boundary}", bytes(body)


def _api_key(config: dict[str, Any]) -> str:
    openai = config["openai"]
    if openai.get("api_key"):
        return str(openai["api_key"])

    env_name = openai.get("api_key_env")
    if env_name:
        value = os.environ.get(str(env_name))
        if value:
            return value

    raise RuntimeError(
        "No OpenAI API key configured. Set openai.api_key or export the configured api_key_env."
    )


def transcription_backend(config: dict[str, Any]) -> str:
    return str(config["openai"].get("backend", "file"))


def transcribe_file(config: dict[str, Any], audio_path: Path) -> str:
    openai = config["openai"]
    api_key = _api_key(config)
    audio_bytes = audio_path.read_bytes()
    mime_type = mimetypes.guess_type(audio_path.name)[0] or "audio/wav"

    fields = {"model": str(openai["model"])}
    if openai.get("language"):
        fields["language"] = str(openai["language"])
    if openai.get("prompt"):
        fields["prompt"] = str(openai["prompt"])
    if openai.get("temperature") is not None:
        fields["temperature"] = str(openai["temperature"])

    content_type, body = _multipart_body(
        fields=fields,
        files=[("file", audio_path.name, audio_bytes, mime_type)],
    )
    request = urllib.request.Request(
        url=f"{str(openai['base_url']).rstrip('/')}/audio/transcriptions",
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": content_type,
        },
    )

    timeout = int(openai.get("timeout_seconds", 120))
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"OpenAI request failed with {exc.code}: {error_body}") from exc

    text = payload.get("text")
    if not isinstance(text, str) or not text.strip():
        raise RuntimeError(f"OpenAI response did not contain transcription text: {payload!r}")
    return text.strip()


@dataclass
class TranscriptSegment:
    item_id: str
    created_index: int
    previous_item_id: str | None = None
    commit_index: int | None = None
    partial_text: str = ""
    completed_text: str | None = None


class RealtimeTranscriber:
    def __init__(self, config: dict[str, Any], audio_path: Path) -> None:
        self.config = config
        self.audio_path = audio_path
        self.openai = config["openai"]
        self.realtime = self.openai.get("realtime", {})
        self.sample_rate_hz = int(self.realtime.get("sample_rate_hz", 24000))
        self.channels = 1
        self.chunk_ms = int(self.realtime.get("chunk_ms", 100))
        self.chunk_size_bytes = pcm_chunk_size_bytes(
            sample_rate_hz=self.sample_rate_hz,
            channels=self.channels,
            chunk_ms=self.chunk_ms,
        )
        self.connect_timeout_seconds = float(self.realtime.get("connect_timeout_seconds", 20))
        self.finalize_timeout_seconds = float(self.realtime.get("finalize_timeout_seconds", 15))
        self.settle_seconds = max(0.4, self.chunk_ms / 1000.0 * 2)
        self._state_lock = threading.RLock()
        self._send_lock = threading.RLock()
        self._session_created = threading.Event()
        self._receiver_finished = threading.Event()
        self._stream_finished = threading.Event()
        self._receiver_thread: threading.Thread | None = None
        self._stream_thread: threading.Thread | None = None
        self._ws: Any | None = None
        self._ffmpeg_process: Any | None = None
        self._closed = False
        self._audio_started = False
        self._audio_bytes_since_commit = 0
        self._segments: dict[str, TranscriptSegment] = {}
        self._segment_counter = 0
        self._commit_counter = 0
        self._last_event_at = time.monotonic()
        self._error: Exception | None = None
        self._session_id: str | None = None

    def start(self) -> None:
        websocket_module = _load_websocket_client()
        session_payload = _realtime_transcription_session_payload(self.config)
        session_data = _create_realtime_client_secret_session(self.config, session_payload)
        self._session_id = _realtime_session_id(session_data)
        secret = _realtime_client_secret_value(session_data)
        self._ws = websocket_module.create_connection(
            _realtime_url(self.config),
            header=[f"Authorization: Bearer {secret}"],
            timeout=self.connect_timeout_seconds,
            enable_multithread=True,
        )
        self._ws.settimeout(1.0)

        self._receiver_thread = threading.Thread(
            target=self._receive_loop,
            name=f"vomacsd-realtime-recv-{self.audio_path.stem}",
            daemon=True,
        )
        self._receiver_thread.start()

        if not self._session_created.wait(timeout=self.connect_timeout_seconds):
            self.close()
            raise RuntimeError("Timed out waiting for OpenAI Realtime session.created")

        self._ffmpeg_process = start_pcm_stream(
            self.config,
            sample_rate_hz=self.sample_rate_hz,
            channels=self.channels,
        )
        self._audio_started = True
        self._stream_thread = threading.Thread(
            target=self._stream_audio_loop,
            name=f"vomacsd-realtime-audio-{self.audio_path.stem}",
            daemon=True,
        )
        self._stream_thread.start()

    def stop_capture(self) -> None:
        process = self._ffmpeg_process
        if process is not None:
            stop_recording(process)
        self._ffmpeg_process = None

        thread = self._stream_thread
        if thread is not None:
            thread.join(timeout=self.finalize_timeout_seconds)
            if thread.is_alive():
                raise RuntimeError("Timed out while waiting for the realtime audio stream to stop")
        self._raise_if_error()

    def finalize(self) -> str:
        self.stop_capture()
        self._raise_if_error()

        should_commit = self._should_send_final_commit()
        finalize_started = time.monotonic()
        if should_commit:
            self._send_event({"type": "input_audio_buffer.commit"})

        deadline = time.monotonic() + self.finalize_timeout_seconds
        while time.monotonic() < deadline:
            self._raise_if_error()
            with self._state_lock:
                pending = self._pending_segments_locked()
                quiet_for = time.monotonic() - self._last_event_at
            waited_long_enough = time.monotonic() - finalize_started >= self.settle_seconds
            if pending == 0 and quiet_for >= self.settle_seconds / 2 and (
                not should_commit or waited_long_enough
            ):
                break
            time.sleep(0.05)

        with self._state_lock:
            pending = self._pending_segments_locked()
        if pending:
            self.close()
            raise RuntimeError(
                f"Timed out waiting for {pending} realtime transcription segment(s) to complete"
            )

        transcript = self.current_transcript()
        self.close()

        if not transcript.strip():
            raise RuntimeError("OpenAI Realtime session did not produce transcription text")
        return transcript.strip()

    def cancel(self) -> None:
        try:
            self.stop_capture()
        except Exception:
            pass
        self.close()

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        ws = self._ws
        self._ws = None
        if ws is not None:
            try:
                ws.close()
            except Exception:
                pass
        thread = self._receiver_thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=2.0)

    def status_snapshot(self) -> dict[str, Any]:
        with self._state_lock:
            completed_segments = sum(
                1 for segment in self._segments.values() if segment.completed_text is not None
            )
            return {
                "session_id": self._session_id,
                "completed_segments": completed_segments,
                "tracked_segments": len(self._segments),
                "partial_transcript": self._joined_partial_locked(),
            }

    def current_transcript(self) -> str:
        with self._state_lock:
            return self._joined_transcript_locked().strip()

    def _stream_audio_loop(self) -> None:
        try:
            process = self._ffmpeg_process
            if process is None or process.stdout is None:
                raise RuntimeError("Realtime audio process is not available")

            with wave.open(str(self.audio_path), "wb") as wav_file:
                wav_file.setnchannels(self.channels)
                wav_file.setsampwidth(2)
                wav_file.setframerate(self.sample_rate_hz)

                while True:
                    chunk = process.stdout.read(self.chunk_size_bytes)
                    if not chunk:
                        break
                    wav_file.writeframes(chunk)
                    with self._state_lock:
                        self._audio_bytes_since_commit += len(chunk)
                    self._send_event(
                        {
                            "type": "input_audio_buffer.append",
                            "audio": base64.b64encode(chunk).decode("ascii"),
                        }
                    )
        except Exception as exc:
            self._set_error(exc)
        finally:
            self._stream_finished.set()

    def _receive_loop(self) -> None:
        try:
            while True:
                ws = self._ws
                if ws is None:
                    break
                try:
                    raw_message = ws.recv()
                except Exception as exc:
                    if _looks_like_ws_timeout(exc):
                        continue
                    if self._closed and _looks_like_ws_closed(exc):
                        break
                    if self._closed:
                        break
                    self._set_error(RuntimeError(f"Realtime websocket receive failed: {exc}"))
                    break

                if raw_message is None:
                    continue
                if isinstance(raw_message, bytes):
                    raw_message = raw_message.decode("utf-8")
                event = json.loads(raw_message)
                self._handle_event(event)
        finally:
            self._receiver_finished.set()

    def _handle_event(self, event: dict[str, Any]) -> None:
        event_type = str(event.get("type", ""))
        with self._state_lock:
            self._last_event_at = time.monotonic()

            if event_type == "session.created":
                if self._session_id is None:
                    self._session_id = _realtime_session_id(event)
                self._session_created.set()
                return

            if event_type == "input_audio_buffer.committed":
                item_id = event.get("item_id")
                if isinstance(item_id, str):
                    segment = self._segment_locked(item_id)
                    segment.previous_item_id = _as_optional_str(event.get("previous_item_id"))
                    segment.commit_index = self._commit_counter
                    self._commit_counter += 1
                    self._audio_bytes_since_commit = 0
                return

            if event_type == "conversation.item.input_audio_transcription.delta":
                item_id = event.get("item_id")
                if isinstance(item_id, str):
                    segment = self._segment_locked(item_id)
                    segment.partial_text += str(event.get("delta", ""))
                return

            if event_type == "conversation.item.input_audio_transcription.completed":
                item_id = event.get("item_id")
                if isinstance(item_id, str):
                    segment = self._segment_locked(item_id)
                    transcript = str(event.get("transcript", "")).strip()
                    segment.completed_text = transcript
                    if transcript:
                        segment.partial_text = transcript
                return

            if event_type == "error":
                error_payload = event.get("error")
                message = _format_realtime_error(error_payload)
                self._set_error(RuntimeError(f"OpenAI Realtime error: {message}"))

    def _segment_locked(self, item_id: str) -> TranscriptSegment:
        segment = self._segments.get(item_id)
        if segment is None:
            segment = TranscriptSegment(item_id=item_id, created_index=self._segment_counter)
            self._segments[item_id] = segment
            self._segment_counter += 1
        return segment

    def _pending_segments_locked(self) -> int:
        return sum(
            1
            for segment in self._segments.values()
            if segment.commit_index is not None and segment.completed_text is None
        )

    def _joined_transcript_locked(self) -> str:
        parts = [
            text
            for text in (
                (segment.completed_text or "").strip()
                for segment in self._ordered_segments_locked()
            )
            if text
        ]
        return " ".join(parts)

    def _joined_partial_locked(self) -> str:
        parts = []
        for segment in self._ordered_segments_locked():
            text = (segment.completed_text or segment.partial_text).strip()
            if text:
                parts.append(text)
        return " ".join(parts)

    def _ordered_segments_locked(self) -> list[TranscriptSegment]:
        segments = sorted(self._segments.values(), key=_segment_sort_key)
        by_id = {segment.item_id: segment for segment in segments}
        children_by_previous: dict[str | None, list[TranscriptSegment]] = {}
        for segment in segments:
            children_by_previous.setdefault(segment.previous_item_id, []).append(segment)

        ordered: list[TranscriptSegment] = []
        seen: set[str] = set()

        def append_chain(segment: TranscriptSegment) -> None:
            if segment.item_id in seen:
                return
            seen.add(segment.item_id)
            ordered.append(segment)
            for child in children_by_previous.get(segment.item_id, []):
                append_chain(child)

        for segment in segments:
            if segment.previous_item_id not in by_id:
                append_chain(segment)
        for segment in segments:
            append_chain(segment)
        return ordered

    def _send_event(self, payload: dict[str, Any]) -> None:
        with self._send_lock:
            self._raise_if_error()
            if self._closed or self._ws is None:
                raise RuntimeError("Realtime websocket is not available")
            self._ws.send(json.dumps(payload))

    def _should_send_final_commit(self) -> bool:
        if not self._audio_started:
            return False
        turn_detection = self.realtime.get("turn_detection")
        with self._state_lock:
            buffered_audio = self._audio_bytes_since_commit > 0
        return turn_detection is None or buffered_audio

    def _set_error(self, exc: Exception) -> None:
        with self._state_lock:
            if self._error is None:
                self._error = exc

    def _raise_if_error(self) -> None:
        with self._state_lock:
            error = self._error
        if error is not None:
            raise error


def start_realtime_transcription(config: dict[str, Any], audio_path: Path) -> RealtimeTranscriber:
    transcriber = RealtimeTranscriber(config, audio_path)
    try:
        transcriber.start()
    except Exception:
        transcriber.close()
        raise
    return transcriber


def _load_websocket_client() -> Any:
    try:
        import websocket
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "Realtime transcription requires the websocket-client package. "
            "Install project dependencies or run `pip install websocket-client`."
        ) from exc
    return websocket


def _realtime_url(config: dict[str, Any]) -> str:
    openai = config["openai"]
    realtime = openai.get("realtime", {})
    return str(realtime.get("url", "wss://api.openai.com/v1/realtime")).rstrip("/")


def _realtime_transcription_session_payload(config: dict[str, Any]) -> dict[str, Any]:
    openai = config["openai"]
    realtime = openai.get("realtime", {})
    audio_input: dict[str, Any] = {
        "format": {
            "type": "audio/pcm",
            "rate": int(realtime.get("sample_rate_hz", 24000)),
        },
        "transcription": {
            "model": str(openai["model"]),
        },
        "turn_detection": realtime.get("turn_detection"),
    }
    if realtime.get("noise_reduction", "__missing__") != "__missing__":
        audio_input["noise_reduction"] = realtime.get("noise_reduction")
    if openai.get("language"):
        audio_input["transcription"]["language"] = str(openai["language"])
    if openai.get("prompt"):
        audio_input["transcription"]["prompt"] = str(openai["prompt"])

    session: dict[str, Any] = {
        "type": "transcription",
        "audio": {"input": audio_input},
    }
    include = realtime.get("include") or []
    if include:
        session["include"] = [str(value) for value in include]
    return {"session": session}


def _create_realtime_client_secret_session(
    config: dict[str, Any],
    payload: dict[str, Any],
) -> dict[str, Any]:
    openai = config["openai"]
    api_key = _api_key(config)
    request = urllib.request.Request(
        url=f"{str(openai['base_url']).rstrip('/')}/realtime/client_secrets",
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )

    timeout = int(openai.get("timeout_seconds", 120))
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"OpenAI request failed with {exc.code}: {error_body}") from exc


def _realtime_client_secret_value(payload: dict[str, Any]) -> str:
    value = payload.get("value")
    if isinstance(value, str) and value:
        return value
    client_secret = payload.get("client_secret")
    if isinstance(client_secret, dict):
        value = client_secret.get("value")
        if isinstance(value, str) and value:
            return value
    raise RuntimeError(f"Realtime client secret response did not contain a usable secret: {payload!r}")


def _realtime_session_id(payload: dict[str, Any]) -> str | None:
    session = payload.get("session")
    if isinstance(session, dict):
        session_id = session.get("id")
        if isinstance(session_id, str) and session_id:
            return session_id
    return None


def _format_realtime_error(error_payload: Any) -> str:
    if isinstance(error_payload, dict):
        message = error_payload.get("message")
        if isinstance(message, str) and message:
            return message
    return json.dumps(error_payload, sort_keys=True)


def _as_optional_str(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _segment_sort_key(segment: TranscriptSegment) -> tuple[bool, int, int]:
    return (
        segment.commit_index is None,
        segment.commit_index if segment.commit_index is not None else segment.created_index,
        segment.created_index,
    )


def _looks_like_ws_timeout(exc: Exception) -> bool:
    return exc.__class__.__name__ == "WebSocketTimeoutException"


def _looks_like_ws_closed(exc: Exception) -> bool:
    return exc.__class__.__name__ in {"WebSocketConnectionClosedException", "BrokenPipeError"}
