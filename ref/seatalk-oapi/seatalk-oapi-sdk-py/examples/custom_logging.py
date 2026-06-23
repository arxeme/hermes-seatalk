#!/usr/bin/env python3
from __future__ import annotations

import argparse
import logging
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from seatalk_oapi_sdk import Client, DEFAULT_WEB_SOCKET_URL, Envelope, EventDispatcher


def print_compact_envelope(envelope: Envelope) -> None:
    print("recv:", json.dumps(envelope.to_dict(), ensure_ascii=False, separators=(",", ":")))


def print_invalid_frame(payload: bytes, err: Exception) -> None:
    print("invalid frame:", payload.decode("utf-8", errors="replace"), "error:", err)


def main() -> None:
    parser = argparse.ArgumentParser(description="Connect to seatalk open platform with custom SDK logging.")
    parser.add_argument("--url", default=DEFAULT_WEB_SOCKET_URL)
    parser.add_argument("--app-id", required=True)
    parser.add_argument("--app-secret", required=True)
    parser.add_argument("--log-level", default="DEBUG", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logger = logging.getLogger("seatalk_oapi_sdk_py")

    dispatcher = EventDispatcher().on_envelope(print_compact_envelope).on_invalid_frame(print_invalid_frame)
    client = Client(args.app_id, args.app_secret, ws_url=args.url, dispatcher=dispatcher, logger=logger)
    try:
        client.run()
    except KeyboardInterrupt:
        print("shutting down")
    finally:
        client.close()


if __name__ == "__main__":
    main()
