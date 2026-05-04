# Hermes SeaTalk Plugin

SeaTalk messaging platform plugin for Hermes Agent.

## Layout

The repository root is the Hermes plugin directory. Hermes imports the root
`adapter.py` shim, while implementation code lives in the standard Python
package `hermes_seatalk/`.

```text
hermes-seatalk/
  plugin.yaml
  pyproject.toml
  adapter.py
  env.example
  hermes_seatalk/
    adapter.py
    client.py
    coalescer.py
    dispatcher.py
    relay.py
    targets.py
    webhook.py
```

## Install

Install the plugin under the user plugin directory and enable its platform id:

```bash
git clone https://github.com/arxeme/hermes-seatalk.git ~/.hermes/plugins/seatalk
hermes plugins enable seatalk-platform
```

`hermes plugins enable seatalk-platform` only records the plugin as enabled in
Hermes configuration. The plugin code is loaded and `register(ctx)` runs when a
Hermes process starts or when Hermes performs plugin discovery. Restart the
gateway after enabling the plugin or changing SeaTalk configuration:

```bash
hermes gateway restart
```

If your Hermes installation does not provide `hermes gateway restart`, stop the
running gateway process and start it again with the command normally used in
that deployment.

## Setup TUI

User-installed plugins appear in `hermes setup` / `hermes gateway setup` only
after `hermes plugins enable seatalk-platform` has been executed. The setup
wizard writes runtime values to `~/.hermes/.env`; it does not clone, install, or
enable the plugin.

```bash
hermes gateway setup
```

The SeaTalk wizard asks for values in this order:

1. Common credentials: `SEATALK_APP_ID`, `SEATALK_APP_SECRET`,
   `SEATALK_SIGNING_SECRET`.
2. Inbound mode: `relay` or `webhook`.
3. Mode-specific values.
4. Optional defaults and authorization controls.

After saving, restart the relevant Hermes process so the new env values are
visible to the gateway and plugin loader.

## Configuration

Copy `env.example` into `~/.hermes/.env` or enter the same values through the
setup TUI.

Common values required by both modes:

```bash
SEATALK_APP_ID=your_app_id
SEATALK_APP_SECRET=your_app_secret
SEATALK_SIGNING_SECRET=your_signing_secret
SEATALK_MODE=relay
```

Relay mode uses a WebSocket relay service to receive SeaTalk callbacks. Only
`SEATALK_RELAY_URL` is additionally required; webhook host, port, and path are
ignored even if stale values remain in the env file.

```bash
SEATALK_MODE=relay
SEATALK_RELAY_URL=wss://relay.example.com/ws
```

Webhook mode runs a local HTTP callback endpoint. It does not require
`SEATALK_RELAY_URL`; host, port, and path have defaults and can be changed when
needed. Configure the SeaTalk Bot App callback URL to point at the externally
reachable endpoint, usually through a reverse proxy or tunnel that terminates
TLS.

```bash
SEATALK_MODE=webhook
SEATALK_WEBHOOK_HOST=0.0.0.0
SEATALK_WEBHOOK_PORT=8646
SEATALK_WEBHOOK_PATH=/callback
```

Optional home channel and authorization values:

```bash
SEATALK_HOME_CHANNEL=group/123
SEATALK_HOME_CHANNEL_NAME=SeaTalk Home
SEATALK_HOME_CHANNEL_THREAD_ID=
SEATALK_ALLOWED_USERS=alice@example.com,bob@example.com
SEATALK_ALLOW_ALL_USERS=false
SEATALK_GROUP_ALLOWED_USERS=group/123,group/456
SEATALK_REQUIRE_MENTION=true
```

`SEATALK_ALLOWED_USERS` is the Hermes user authorization allowlist. SeaTalk
sender email is preferred as `user_id`; when email is unavailable, employee code
is preserved as the fallback identity. `SEATALK_GROUP_ALLOWED_USERS` is a
SeaTalk channel pre-filter for group chats. Passing the group filter does not
authorize every user in that group; the message still goes through the Hermes
user authorization path.

## Status And Troubleshooting

Use Hermes status and logs to separate static configuration from runtime
connectivity:

```bash
hermes gateway status
```

Static connected state means the required SeaTalk credentials for the selected
mode are present. Runtime health comes from the running adapter: relay mode
health depends on the WebSocket connection, while webhook mode health depends on
the callback server being started and receiving valid signed events.

Common checks:

- SeaTalk does not appear in setup TUI: run
  `hermes plugins enable seatalk-platform`, then restart or rerun setup.
- `send_message(target="seatalk")` reports no live adapter: start or restart the
  gateway with the plugin enabled and valid SeaTalk config.
- Relay mode is not receiving events: verify `SEATALK_RELAY_URL`, relay service
  reachability, and gateway logs.
- Webhook mode rejects events: verify the SeaTalk callback URL, raw-body
  signing secret, and reverse proxy body forwarding.
- Authorized group still rejects a sender: check both `SEATALK_GROUP_ALLOWED_USERS`
  and `SEATALK_ALLOWED_USERS` / `SEATALK_ALLOW_ALL_USERS`.
- Config changed but behavior did not: restart the gateway process that loads
  `~/.hermes/.env`.

## Tests

The automated suite uses fake SeaTalk HTTP/WebSocket objects and does not need
real Bot App credentials:

```bash
PYTHONDONTWRITEBYTECODE=1 uv run --directory ../../hermes-agent pytest
```

Real SeaTalk verification is manual and tracked separately in
`docs/test/e2e_hermes-seatalk-plugin_runbook_zh.md`.
