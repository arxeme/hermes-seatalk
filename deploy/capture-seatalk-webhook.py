#!/usr/bin/env python3
"""Capture and verify SeaTalk webhook requests without printing secrets.

This helper is for Phase 2 W2-05 protocol verification. It reads app_id and
signing_secret from a local YAML file, starts a temporary webhook endpoint, and
prints sanitized request facts needed to decide whether shared multi-account
webhook routing is safe.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import sys
import time
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


MAX_BODY_BYTES = 1024 * 1024


@dataclass(frozen=True)
class Account:
    account_id: str
    app_id: str
    signing_secret: str


def _strip_yaml_value(value: str) -> str:
    value = value.strip()
    if not value:
        return ""
    if value[0] in {"'", '"'} and value[-1:] == value[0]:
        return value[1:-1]
    return value


def _mini_yaml_load(text: str) -> dict[str, Any]:
    """Parse the small YAML subset used by deploy/app.local.

    PyYAML is preferred when available. This fallback supports:
    - flat top-level key: value files
    - platforms.seatalk.extra.accounts.<id>.key: value
    - accounts.<id>.key: value
    """
    root: dict[str, Any] = {}
    stack: list[tuple[int, dict[str, Any]]] = [(-1, root)]
    for raw_line in text.splitlines():
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        indent = len(raw_line) - len(raw_line.lstrip(" "))
        line = raw_line.strip()
        if ":" not in line:
            continue
        key, raw_value = line.split(":", 1)
        key = key.strip()
        value = _strip_yaml_value(raw_value)
        while stack and indent <= stack[-1][0]:
            stack.pop()
        parent = stack[-1][1]
        if value:
            parent[key] = value
            continue
        child: dict[str, Any] = {}
        parent[key] = child
        stack.append((indent, child))
    return root


def _load_yaml(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    if not text.strip():
        raise SystemExit(f"ERROR: app file is empty: {path}")
    try:
        import yaml  # type: ignore
    except Exception:
        data = _mini_yaml_load(text)
    else:
        loaded = yaml.safe_load(text) or {}
        data = loaded if isinstance(loaded, dict) else {}
    if not isinstance(data, dict):
        raise SystemExit(f"ERROR: app file must contain a YAML mapping: {path}")
    return data


def _accounts_from_data(data: dict[str, Any]) -> list[Account]:
    candidates = (
        data.get("accounts"),
        (data.get("seatalk") or {}).get("accounts") if isinstance(data.get("seatalk"), dict) else None,
        ((data.get("platforms") or {}).get("seatalk") or {}).get("extra", {}).get("accounts")
        if isinstance(data.get("platforms"), dict)
        and isinstance((data.get("platforms") or {}).get("seatalk"), dict)
        and isinstance(((data.get("platforms") or {}).get("seatalk") or {}).get("extra"), dict)
        else None,
    )
    accounts: list[Account] = []
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        for account_id, cfg in candidate.items():
            if not isinstance(cfg, dict):
                continue
            app_id = str(cfg.get("app_id") or cfg.get("appId") or "").strip()
            signing_secret = str(cfg.get("signing_secret") or cfg.get("signingSecret") or "").strip()
            if app_id and signing_secret:
                accounts.append(Account(str(account_id), app_id, signing_secret))
        if accounts:
            return accounts

    app_id = str(data.get("app_id") or data.get("appId") or "").strip()
    signing_secret = str(data.get("signing_secret") or data.get("signingSecret") or "").strip()
    if app_id and signing_secret:
        return [Account("default", app_id, signing_secret)]
    raise SystemExit("ERROR: no account with app_id and signing_secret found")


def _mask(value: str) -> str:
    if len(value) <= 6:
        return "***"
    return f"{value[:2]}***{value[-4:]}"


def _signature(raw_body: bytes, secret: str, encoding: str) -> str:
    return hashlib.sha256(raw_body + secret.encode(encoding)).hexdigest()


def _match_signature(raw_body: bytes, signature: str | None, accounts: list[Account]) -> tuple[Account | None, str | None]:
    if not signature:
        return None, None
    signature = signature.strip().lower()
    for account in accounts:
        for encoding in ("utf-8", "latin1"):
            calculated = _signature(raw_body, account.signing_secret, encoding)
            if hmac.compare_digest(calculated, signature):
                return account, encoding
    return None, None


def _safe_json_keys(value: Any) -> list[str]:
    return sorted(str(key) for key in value.keys()) if isinstance(value, dict) else []


def _print_json(record: dict[str, Any]) -> None:
    print(json.dumps(record, ensure_ascii=False, sort_keys=True), flush=True)


def _make_handler(accounts: list[Account], path: str):
    class Handler(BaseHTTPRequestHandler):
        server_version = "SeaTalkCapture/1.0"

        def log_message(self, fmt: str, *args: Any) -> None:
            return

        def do_POST(self) -> None:  # noqa: N802
            if self.path.split("?", 1)[0] != path:
                self.send_response(404)
                self.end_headers()
                self.wfile.write(b"Not Found")
                return

            raw_length = self.headers.get("Content-Length")
            try:
                length = int(raw_length or "0")
            except ValueError:
                length = 0
            if length > MAX_BODY_BYTES:
                self.send_response(413)
                self.end_headers()
                self.wfile.write(b"Payload Too Large")
                return

            raw_body = self.rfile.read(length)
            signature = self.headers.get("Signature")
            account, encoding = _match_signature(raw_body, signature, accounts)
            record: dict[str, Any] = {
                "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "path": self.path.split("?", 1)[0],
                "content_type": self.headers.get("Content-Type"),
                "content_length": len(raw_body),
                "signature_present": bool(signature),
                "signature_valid": account is not None,
                "signature_encoding": encoding,
                "matched_account_id": account.account_id if account else None,
                "matched_app_id_masked": _mask(account.app_id) if account else None,
            }

            payload: dict[str, Any] | None = None
            if account is None:
                record["result"] = "forbidden"
                _print_json(record)
                self.send_response(403)
                self.end_headers()
                self.wfile.write(b"Forbidden")
                return

            try:
                decoded = raw_body.decode("utf-8")
                parsed = json.loads(decoded)
                if isinstance(parsed, dict):
                    payload = parsed
            except Exception as exc:  # noqa: BLE001
                record["json_error"] = type(exc).__name__

            if payload is None:
                record["result"] = "malformed_json"
                _print_json(record)
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b"Malformed JSON")
                return

            event = payload.get("event")
            payload_app_id = payload.get("app_id") or payload.get("appId")
            event_type = payload.get("event_type")
            record.update(
                {
                    "result": "accepted",
                    "payload_keys": _safe_json_keys(payload),
                    "event_keys": _safe_json_keys(event),
                    "event_type": event_type,
                    "payload_has_app_id": bool(payload_app_id),
                    "payload_app_id_masked": _mask(str(payload_app_id)) if payload_app_id else None,
                    "payload_app_id_matches_signature_account": (
                        str(payload_app_id) == account.app_id if payload_app_id else None
                    ),
                    "event_has_seatalk_challenge": (
                        isinstance(event, dict) and "seatalk_challenge" in event
                    ),
                }
            )
            _print_json(record)

            if event_type == "event_verification":
                challenge = event.get("seatalk_challenge") if isinstance(event, dict) else None
                body = json.dumps({"seatalk_challenge": challenge}).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return

            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"OK")

    return Handler


def main() -> int:
    parser = argparse.ArgumentParser(description="Capture SeaTalk webhook requests and print sanitized verification facts.")
    parser.add_argument("--app-file", default=str(Path(__file__).with_name("app.local")), help="YAML file with app_id/signing_secret or accounts")
    parser.add_argument("--host", default="0.0.0.0", help="listen host")
    parser.add_argument("--port", type=int, default=8080, help="listen port")
    parser.add_argument("--path", default="/callback", help="webhook callback path")
    parser.add_argument("--show-config", action="store_true", help="print sanitized account summary and exit")
    args = parser.parse_args()

    callback_path = args.path if args.path.startswith("/") else f"/{args.path}"
    accounts = _accounts_from_data(_load_yaml(Path(args.app_file)))
    summary = {
        "app_file": args.app_file,
        "accounts": [
            {"account_id": account.account_id, "app_id_masked": _mask(account.app_id)}
            for account in accounts
        ],
    }
    _print_json({"loaded": summary})
    if args.show_config:
        return 0

    httpd = ThreadingHTTPServer((args.host, args.port), _make_handler(accounts, callback_path))
    bind_host, bind_port = httpd.server_address[:2]
    _print_json({"listening": {"host": bind_host, "port": bind_port, "path": callback_path}})
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        _print_json({"stopped": True})
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
