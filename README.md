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
wizard writes SeaTalk secrets to `~/.hermes/.env` and non-secret runtime policy
to `~/.hermes/config.yaml`; it does not clone, install, or enable the plugin.

```bash
hermes gateway setup
```

The SeaTalk wizard asks for values in this order:

1. App identity and secrets: `app_id` in `config.yaml`, plus
   `SEATALK_APP_SECRET` and `SEATALK_SIGNING_SECRET` in `.env`.
2. Inbound mode: `webhook` or `relay`.
3. Mode-specific values.
4. Optional defaults and SeaTalk authorization policy.

The wizard does not write SeaTalk or global allow-all settings. SeaTalk DMs
remain deny-by-default unless `platforms.seatalk.extra.allow_from` is configured
or `dm_policy` is explicitly opened. Group access is controlled separately by
`group_policy` and defaults to `disabled`.
After saving, restart the relevant Hermes process so the new config is visible
to the gateway and plugin loader.

## Configuration

Use `~/.hermes/.env` only for SeaTalk secrets:

```dotenv
SEATALK_APP_SECRET=your_app_secret
SEATALK_SIGNING_SECRET=your_signing_secret
```

All non-secret SeaTalk runtime settings live in `~/.hermes/config.yaml`:

```yaml
platforms:
  seatalk:
    enabled: true
    extra:
      app_id: your_app_id
      mode: webhook
      webhook_host: 0.0.0.0
      webhook_port: 8080
      webhook_path: /callback
      home_channel: group/123
      home_channel_name: SeaTalk Home
      home_channel_thread_id:
      dm_policy: allowlist
      allow_from:
        - alice@example.com
        - bob@example.com
      group_policy: open
      group_allow_from: []
      group_sender_allow_from:
        - alice@example.com
        - bob@example.com
      processing_indicator: typing
      media_allow_hosts:
        - openapi.seatalk.io
      outbound_coalescing: true
```

Webhook mode runs a local HTTP callback endpoint and replaces `relay_url` with
listener settings. Relay mode uses a WebSocket relay service to receive SeaTalk
callbacks and requires only `relay_url` in addition to the shared settings:

```yaml
platforms:
  seatalk:
    enabled: true
    extra:
      app_id: your_app_id
      mode: relay
      relay_url: wss://relay.example.com/ws
```

Configure the SeaTalk Bot App callback URL to point at the externally reachable
endpoint, usually through a reverse proxy or tunnel that terminates TLS.

`dm_policy` controls direct messages. With the default `allowlist`, `allow_from`
must match the SeaTalk sender email or employee code. `open` allows all direct
messages. `pairing` delegates direct-message approval to Hermes pairing and
cannot be combined with enabled group access.

`group_policy` controls group chats. The default `disabled` rejects all group
messages. `allowlist` requires the raw SeaTalk `group_id` to appear in
`group_allow_from`; do not prefix values with `group/`. `open` allows all
groups. For either enabled group policy, `group_sender_allow_from` can restrict
which users may trigger Hermes inside those groups. Leaving
`group_sender_allow_from` empty means every sender in the allowed groups can
trigger Hermes, so keep it populated when groups are open but users must remain
restricted.

SeaTalk sender email is preferred as `user_id`; when email is unavailable,
employee code is preserved as the fallback identity. SeaTalk policy is enforced
by the plugin before messages are passed into Hermes.

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
- Relay mode is not receiving events: verify `relay_url`, relay service
  reachability, and gateway logs.
- Webhook mode rejects events: verify the SeaTalk callback URL, raw-body
  signing secret, and reverse proxy body forwarding.
- Authorized group still rejects a sender: check `group_policy`,
  `group_allow_from`, and `group_sender_allow_from`.
- Config changed but behavior did not: restart the gateway process that loads
  `~/.hermes/config.yaml` and `~/.hermes/.env`.

## Tests

The automated suite uses fake SeaTalk HTTP/WebSocket objects and does not need
real Bot App credentials:

```bash
PYTHONDONTWRITEBYTECODE=1 uv run --directory ../../hermes-agent pytest
```

Real SeaTalk verification is manual and tracked separately in
`docs/test/e2e_hermes-seatalk-plugin_runbook_zh.md`.
