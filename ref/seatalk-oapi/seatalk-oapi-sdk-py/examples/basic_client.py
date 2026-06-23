#!/usr/bin/env python3
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from seatalk_oapi_sdk import Client, DEFAULT_WEB_SOCKET_URL, EventDispatcher


def main() -> None:
    parser = argparse.ArgumentParser(description="Connect to seatalk open platform and print received envelopes.")
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

    client = Client(
        app_id=args.app_id,
        app_secret=args.app_secret,
        ws_url=args.url,
        dispatcher=EventDispatcher(),
        logger=logger,
    )
    try:
        result = client.connect()
        print("registered ok, session token:", result.token)
        client.start()
    except KeyboardInterrupt:
        print("shutting down")
    finally:
        client.close()


if __name__ == "__main__":
    main()
