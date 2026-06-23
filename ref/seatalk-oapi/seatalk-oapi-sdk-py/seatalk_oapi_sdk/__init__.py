__version__ = "0.1.0"

from .client import Client, WebSocketClosedError
from .dispatcher import EventDispatcher
from .errors import (
    AlreadyConnectedError,
    KickError,
    MissingCallbackIDError,
    MissingCredentialError,
    NotConnectedError,
    NotRegisteredError,
    RegisterError,
    SopConnError,
)
from .protocol import *
