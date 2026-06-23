from __future__ import annotations

import sys
import unittest
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import seatalk_oapi_sdk.client as client_module  # noqa: E402
from seatalk_oapi_sdk import CODE_OK, COMMAND_ACK, COMMAND_PING, COMMAND_REGISTER, Client  # noqa: E402


class FakeWebSocket:
    def __init__(self) -> None:
        self.messages = []
        self.closed = False

    def write_json(self, value) -> None:
        self.messages.append(value)

    def close(self) -> None:
        self.closed = True


class FakeRegisterWebSocket(FakeWebSocket):
    def __init__(self, response) -> None:
        super().__init__()
        self.response = response

    def read_message(self):
        return 1, json.dumps(self.response).encode("utf-8")


class FakeLogger:
    def __init__(self) -> None:
        self.messages = []

    def debug(self, fmt, *args) -> None:
        self.messages.append(fmt % args if args else fmt)


class ClientTest(unittest.TestCase):
    def test_connect_uses_server_heartbeat_interval(self) -> None:
        conn = FakeRegisterWebSocket(
            {
                "cmd": COMMAND_REGISTER,
                "header": {"app_id": "app-1", "sid": "sid-1", "token": "token-1"},
                "code": CODE_OK,
                "message": "ok",
                "data": {"heartbeat_interval": 9, "heartbeat_timeout": 27},
            }
        )
        original_connect = client_module._WebSocket.__dict__["connect"]
        client_module._WebSocket.connect = staticmethod(lambda *args, **kwargs: conn)
        try:
            client = Client("app-1", "secret-1", ping_interval=15.0)
            result = client.connect()
        finally:
            client_module._WebSocket.connect = original_connect

        self.assertEqual(result.token, "token-1")
        self.assertEqual(result.sid, "sid-1")
        self.assertEqual(result.heartbeat_interval, 9.0)
        self.assertEqual(result.heartbeat_timeout, 27.0)
        self.assertEqual(client.ping_interval, 9.0)
        self.assertEqual(len(conn.messages), 1)
        self.assertEqual(conn.messages[0]["cmd"], COMMAND_REGISTER)
        self.assertEqual(conn.messages[0]["header"]["app_id"], "app-1")
        self.assertEqual(conn.messages[0]["header"]["app_secret"], "secret-1")
        self.assertTrue(conn.messages[0]["header"]["rid"])

    def test_ping_sends_session_token(self) -> None:
        logger = FakeLogger()
        client = Client("app-1", "secret-1", logger=logger)
        conn = FakeWebSocket()
        client._conn = conn
        client._token = "token-1"

        client.ping()

        self.assertEqual(len(conn.messages), 1)
        self.assertEqual(conn.messages[0]["cmd"], COMMAND_PING)
        self.assertEqual(conn.messages[0]["header"]["token"], "token-1")
        self.assertTrue(conn.messages[0]["header"]["rid"])
        self.assertIn("sent ping command rid=%s" % conn.messages[0]["header"]["rid"], logger.messages)

    def test_ack_sends_session_token(self) -> None:
        client = Client("app-1", "secret-1")
        conn = FakeWebSocket()
        client._conn = conn
        client._token = "token-1"

        client.ack("callback-1")

        self.assertEqual(len(conn.messages), 1)
        self.assertEqual(conn.messages[0]["cmd"], COMMAND_ACK)
        self.assertEqual(conn.messages[0]["header"]["token"], "token-1")
        self.assertEqual(conn.messages[0]["header"]["callback_id"], "callback-1")
        self.assertTrue(conn.messages[0]["header"]["rid"])


if __name__ == "__main__":
    unittest.main()
