from __future__ import annotations

import base64
import hashlib
import json
import os
import socket
import ssl
import struct
import threading
import uuid
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urlparse

from .dispatcher import EventDispatcher
from .errors import (
    AlreadyConnectedError,
    MissingCallbackIDError,
    MissingCredentialError,
    NotConnectedError,
    NotRegisteredError,
    RegisterError,
)
from .protocol import (
    CODE_OK,
    COMMAND_ACK,
    COMMAND_PING,
    COMMAND_REGISTER,
    DEFAULT_WEB_SOCKET_URL,
    Envelope,
    Header,
    RegisterResult,
    RegisterSettings,
)


class WebSocketClosedError(Exception):
    def __init__(self, code: int = 0, reason: str = "") -> None:
        super().__init__("websocket closed: code=%s reason=%s" % (code, reason))
        self.code = code
        self.reason = reason


class Client:
    def __init__(
        self,
        app_id: str,
        app_secret: str,
        ws_url: str = DEFAULT_WEB_SOCKET_URL,
        request_headers: Optional[Dict[str, str]] = None,
        handshake_timeout: float = 15.0,
        write_timeout: float = 10.0,
        ping_interval: float = 15.0,
        read_limit: int = 1024 * 1024,
        dispatcher: Optional[EventDispatcher] = None,
        logger: Any = None,
    ) -> None:
        self.app_id = app_id
        self.app_secret = app_secret
        self.ws_url = ws_url
        self.request_headers = dict(request_headers or {})
        self.handshake_timeout = handshake_timeout
        self.write_timeout = write_timeout
        self.ping_interval = ping_interval
        self._fallback_ping_interval = ping_interval
        self.read_limit = read_limit
        self.dispatcher = dispatcher or EventDispatcher()
        self.logger = logger

        self._conn: Optional[_WebSocket] = None
        self._token = ""
        self._lock = threading.RLock()

    def connect(self) -> RegisterResult:
        if not self.app_id or not self.app_secret:
            raise MissingCredentialError("seatalk oapi sdk: app_id and app_secret are required")

        with self._lock:
            if self._conn is not None:
                raise AlreadyConnectedError("seatalk oapi sdk: already connected")

        conn = _WebSocket.connect(
            self.ws_url,
            request_headers=self.request_headers,
            handshake_timeout=self.handshake_timeout,
            write_timeout=self.write_timeout,
            read_limit=self.read_limit,
            logger=self.logger,
        )

        with self._lock:
            if self._conn is not None:
                conn.close()
                raise AlreadyConnectedError("seatalk oapi sdk: already connected")
            self._conn = conn
            self._token = ""

        try:
            self.send(
                Envelope(
                    cmd=COMMAND_REGISTER,
                    header=Header(app_id=self.app_id, app_secret=self.app_secret),
                )
            )
            result = self._read_register_ok(conn)
        except Exception:
            self.close()
            raise

        with self._lock:
            self._token = result.token
            self.ping_interval = result.heartbeat_interval or self._fallback_ping_interval
        return result

    def run(self) -> None:
        self.connect()
        try:
            self.start()
        finally:
            self.close()

    def start(self, stop_event: Optional[threading.Event] = None) -> None:
        if stop_event is None:
            self.listen()
            return

        errors = []

        def _listen() -> None:
            try:
                self.listen()
            except Exception as exc:  # pragma: no cover - exercised through caller checks
                errors.append(exc)

        thread = threading.Thread(target=_listen, name="sop-conn-listen", daemon=True)
        thread.start()
        while thread.is_alive():
            if stop_event.wait(0.1):
                self.close()
                break
        thread.join()
        if errors:
            raise errors[0]

    def listen(self) -> None:
        conn = self._current_conn()
        if conn is None:
            raise NotConnectedError("seatalk oapi sdk: not connected")

        ping_stop = threading.Event()
        ping_errors = []
        ping_thread: Optional[threading.Thread] = None
        ping_interval = self.ping_interval
        if ping_interval > 0:
            ping_thread = threading.Thread(
                target=self._ping_loop,
                args=(ping_stop, ping_errors, ping_interval),
                name="sop-conn-ping",
                daemon=True,
            )
            ping_thread.start()

        try:
            while True:
                try:
                    opcode, payload = conn.read_message()
                except WebSocketClosedError:
                    if ping_errors:
                        raise ping_errors[0]
                    return
                except OSError:
                    if ping_errors:
                        raise ping_errors[0]
                    if self._current_conn() is None:
                        return
                    raise

                if opcode != _OP_TEXT:
                    continue

                try:
                    raw = json.loads(payload.decode("utf-8"))
                    env = Envelope.from_dict(raw)
                except Exception as exc:
                    self.dispatcher.handle_invalid_frame(payload, Exception("invalid json frame: %s" % exc))
                    continue

                self.dispatcher.dispatch(self, env)
        finally:
            ping_stop.set()
            if ping_thread is not None:
                ping_thread.join(timeout=1.0)

    def send(self, envelope: Envelope) -> None:
        conn = self._current_conn()
        if conn is None:
            raise NotConnectedError("seatalk oapi sdk: not connected")
        if not envelope.header.rid:
            envelope.header.rid = uuid.uuid4().hex
        conn.write_json(envelope.to_dict())
        if self.logger is not None:
            self.logger.debug("sent %s command rid=%s", envelope.cmd, envelope.header.rid)

    def ack(self, callback_id: str) -> None:
        if not callback_id:
            raise MissingCallbackIDError("seatalk oapi sdk: callback_id is required")
        token = self.token
        if not token:
            raise NotRegisteredError("seatalk oapi sdk: not registered")
        self.send(Envelope(cmd=COMMAND_ACK, header=Header(token=token, callback_id=callback_id)))

    def ping(self) -> None:
        token = self.token
        if not token:
            raise NotRegisteredError("seatalk oapi sdk: not registered")
        self.send(Envelope(cmd=COMMAND_PING, header=Header(token=token)))

    def _ping_loop(self, stop_event: threading.Event, errors: list, interval: float) -> None:
        while not stop_event.wait(interval):
            try:
                self.ping()
            except Exception as exc:  # pragma: no cover - depends on socket timing
                errors.append(exc)
                self.close()
                return

    @property
    def token(self) -> str:
        with self._lock:
            return self._token

    def close(self) -> None:
        with self._lock:
            conn = self._conn
            self._conn = None
            self._token = ""
        if conn is not None:
            conn.close()

    def _current_conn(self) -> Optional["_WebSocket"]:
        with self._lock:
            return self._conn

    def _read_register_ok(self, conn: "_WebSocket") -> RegisterResult:
        while True:
            opcode, payload = conn.read_message()
            if opcode != _OP_TEXT:
                continue
            try:
                env = Envelope.from_dict(json.loads(payload.decode("utf-8")))
            except Exception as exc:
                raise ValueError("invalid json in register phase: %s" % exc)
            if env.cmd != COMMAND_REGISTER:
                raise ValueError('expected cmd "%s" first, got "%s" (%s)' % (COMMAND_REGISTER, env.cmd, env.message))
            if env.code != CODE_OK:
                raise RegisterError(env.code, env.message)
            if not env.header.token:
                raise ValueError("register ok but empty token")
            settings = RegisterSettings.from_dict(env.data)
            return RegisterResult(
                app_id=env.header.app_id,
                token=env.header.token,
                sid=env.header.sid,
                heartbeat_interval=float(settings.heartbeat_interval),
                heartbeat_timeout=float(settings.heartbeat_timeout),
            )


_OP_CONTINUATION = 0x0
_OP_TEXT = 0x1
_OP_BINARY = 0x2
_OP_CLOSE = 0x8
_OP_PING = 0x9
_OP_PONG = 0xA
_CLOSE_NORMAL = 1000
_WS_MAGIC = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


class _WebSocket:
    def __init__(self, sock: socket.socket, write_timeout: float, read_limit: int, logger: Any = None) -> None:
        self._sock = sock
        self._write_timeout = write_timeout
        self._read_limit = read_limit
        self._logger = logger
        self._write_lock = threading.Lock()
        self._closed = False

    @classmethod
    def connect(
        cls,
        ws_url: str,
        request_headers: Dict[str, str],
        handshake_timeout: float,
        write_timeout: float,
        read_limit: int,
        logger: Any = None,
    ) -> "_WebSocket":
        parsed = urlparse(ws_url)
        if parsed.scheme not in ("ws", "wss"):
            raise ValueError("unsupported websocket scheme: %s" % parsed.scheme)
        if not parsed.hostname:
            raise ValueError("missing websocket host")

        port = parsed.port or (443 if parsed.scheme == "wss" else 80)
        raw_sock = socket.create_connection((parsed.hostname, port), timeout=handshake_timeout)
        if parsed.scheme == "wss":
            raw_sock = ssl.create_default_context().wrap_socket(raw_sock, server_hostname=parsed.hostname)
        raw_sock.settimeout(handshake_timeout)

        key = base64.b64encode(os.urandom(16)).decode("ascii")
        path = parsed.path or "/"
        if parsed.query:
            path += "?" + parsed.query
        host = parsed.hostname
        if parsed.port is not None:
            host = "%s:%d" % (host, parsed.port)

        headers = {
            "Host": host,
            "Upgrade": "websocket",
            "Connection": "Upgrade",
            "Sec-WebSocket-Key": key,
            "Sec-WebSocket-Version": "13",
        }
        headers.update(request_headers)

        request = ["GET %s HTTP/1.1" % path]
        request.extend("%s: %s" % (name, value) for name, value in headers.items())
        request.append("")
        request.append("")
        raw_sock.sendall("\r\n".join(request).encode("ascii"))

        response = cls._read_http_response(raw_sock)
        cls._validate_handshake(response, key)
        raw_sock.settimeout(None)
        return cls(raw_sock, write_timeout=write_timeout, read_limit=read_limit, logger=logger)

    def read_message(self) -> Tuple[int, bytes]:
        while True:
            opcode, payload = self._read_frame()
            if opcode == _OP_PING:
                self._log("received ping frame: %s", payload.decode("utf-8", errors="replace"))
                self._send_frame(_OP_PONG, payload)
                continue
            if opcode == _OP_PONG:
                continue
            if opcode == _OP_CLOSE:
                code, reason = _parse_close_payload(payload)
                self._send_close()
                raise WebSocketClosedError(code, reason)
            if opcode in (_OP_TEXT, _OP_BINARY):
                return opcode, payload
            if opcode == _OP_CONTINUATION:
                continue

    def write_json(self, value: Any) -> None:
        payload = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self._send_frame(_OP_TEXT, payload)

    def close(self) -> None:
        self._send_close()
        try:
            self._sock.close()
        finally:
            self._closed = True

    @staticmethod
    def _read_http_response(sock: socket.socket) -> bytes:
        chunks = []
        total = 0
        while True:
            chunk = sock.recv(4096)
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            data = b"".join(chunks)
            if b"\r\n\r\n" in data:
                return data.split(b"\r\n\r\n", 1)[0]
            if total > 64 * 1024:
                raise ValueError("websocket handshake response too large")
        raise ValueError("websocket handshake failed: empty response")

    @staticmethod
    def _validate_handshake(response: bytes, key: str) -> None:
        lines = response.decode("iso-8859-1").split("\r\n")
        if not lines or " 101 " not in lines[0]:
            raise ValueError("websocket handshake failed: %s" % (lines[0] if lines else "empty status"))
        headers: Dict[str, str] = {}
        for line in lines[1:]:
            if ":" not in line:
                continue
            name, value = line.split(":", 1)
            headers[name.strip().lower()] = value.strip()
        accept = base64.b64encode(hashlib.sha1((key + _WS_MAGIC).encode("ascii")).digest()).decode("ascii")
        if headers.get("sec-websocket-accept") != accept:
            raise ValueError("websocket handshake failed: invalid Sec-WebSocket-Accept")

    def _read_frame(self) -> Tuple[int, bytes]:
        header = self._recv_exact(2)
        b1, b2 = header[0], header[1]
        opcode = b1 & 0x0F
        masked = (b2 & 0x80) != 0
        length = b2 & 0x7F
        if length == 126:
            length = struct.unpack("!H", self._recv_exact(2))[0]
        elif length == 127:
            length = struct.unpack("!Q", self._recv_exact(8))[0]
        if length > self._read_limit:
            raise ValueError("websocket frame exceeds read limit: %d" % length)
        mask = self._recv_exact(4) if masked else None
        payload = self._recv_exact(length) if length else b""
        if mask is not None:
            payload = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
        return opcode, payload

    def _recv_exact(self, length: int) -> bytes:
        data = bytearray()
        while len(data) < length:
            chunk = self._sock.recv(length - len(data))
            if not chunk:
                raise WebSocketClosedError()
            data.extend(chunk)
        return bytes(data)

    def _send_frame(self, opcode: int, payload: bytes = b"") -> None:
        with self._write_lock:
            if self._closed:
                return
            first = 0x80 | opcode
            mask_key = os.urandom(4)
            length = len(payload)
            if length < 126:
                header = struct.pack("!BB", first, 0x80 | length)
            elif length <= 0xFFFF:
                header = struct.pack("!BBH", first, 0x80 | 126, length)
            else:
                header = struct.pack("!BBQ", first, 0x80 | 127, length)
            masked = bytes(byte ^ mask_key[index % 4] for index, byte in enumerate(payload))
            old_timeout = self._sock.gettimeout()
            try:
                if self._write_timeout:
                    self._sock.settimeout(self._write_timeout)
                self._sock.sendall(header + mask_key + masked)
            finally:
                self._sock.settimeout(old_timeout)

    def _send_close(self) -> None:
        if self._closed:
            return
        try:
            self._send_frame(_OP_CLOSE, struct.pack("!H", _CLOSE_NORMAL))
        except OSError:
            pass
        self._closed = True

    def _log(self, fmt: str, *args: Any) -> None:
        if self._logger is None:
            return
        if hasattr(self._logger, "debug"):
            self._logger.debug(fmt, *args)
        elif hasattr(self._logger, "info"):
            self._logger.info(fmt, *args)


def _parse_close_payload(payload: bytes) -> Tuple[int, str]:
    if len(payload) < 2:
        return 0, ""
    code = struct.unpack("!H", payload[:2])[0]
    reason = payload[2:].decode("utf-8", errors="replace")
    return code, reason
