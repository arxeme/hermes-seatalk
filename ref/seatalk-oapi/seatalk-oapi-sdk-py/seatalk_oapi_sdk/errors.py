from __future__ import annotations

from typing import Optional

from .protocol import Envelope


class SopConnError(Exception):
    pass


class MissingCredentialError(SopConnError):
    pass


class AlreadyConnectedError(SopConnError):
    pass


class NotConnectedError(SopConnError):
    pass


class NotRegisteredError(SopConnError):
    pass


class MissingCallbackIDError(SopConnError):
    pass


class RegisterError(SopConnError):
    def __init__(self, code: int, message: str) -> None:
        super().__init__("register rejected: code=%d msg=%s" % (code, message))
        self.code = code
        self.message = message


class KickError(SopConnError):
    def __init__(self, message: str = "", envelope: Optional[Envelope] = None) -> None:
        super().__init__("kicked: " + message if message else "kicked")
        self.message = message
        self.envelope = envelope
