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

Install the plugin from GitHub, enable its platform id, and restart the gateway:

```bash
hermes plugins install arxeme/hermes-seatalk --enable && hermes gateway restart
```

`hermes plugins install arxeme/hermes-seatalk --enable` clones the plugin into
the user plugin directory and records `seatalk-platform` as enabled in Hermes
configuration. The plugin code is loaded and `register(ctx)` runs when a Hermes
process starts or when Hermes performs plugin discovery. Restart the gateway
after changing SeaTalk configuration:

```bash
hermes gateway restart
```

If your Hermes installation does not provide `hermes gateway restart`, stop the
running gateway process and start it again with the command normally used in
that deployment.

## Setup TUI

User-installed plugins appear in `hermes setup` / `hermes gateway setup` only
after `hermes plugins enable seatalk-platform` has been executed. The setup
wizard writes SeaTalk accounts, including `app_secret` and `signing_secret`, to
`~/.hermes/config.yaml`; it does not clone, install, enable the plugin, or write
SeaTalk secrets to `~/.hermes/.env`.

```bash
hermes gateway setup
```

The SeaTalk wizard asks for values in this order:

1. Account id and action: add/edit, disable, or remove.
2. App identity and secrets: `app_id`, `app_secret`, and `signing_secret`.
3. Inbound mode: `webhook` or `relay`.
4. Mode-specific values.
5. SeaTalk authorization policy.

The wizard does not write SeaTalk or global allow-all settings. SeaTalk DMs
remain deny-by-default unless an account `allow_from` is configured or
`dm_policy` is explicitly opened. Group access is controlled separately by each
account `group_policy` and defaults to `disabled`. The wizard does not offer
`dm_policy=pairing`. Home channel uses Hermes' standard env mechanism; set it
with `/sethome` from SeaTalk, or by writing `SEATALK_HOME_CHANNEL` in
`~/.hermes/.env`.
After saving, restart the relevant Hermes process so the new config is visible
to the gateway and plugin loader.

## Configuration

All SeaTalk runtime settings and Bot App secrets live in
`~/.hermes/config.yaml`. Protect this file as a secret-bearing configuration
file:

```yaml
platforms:
  seatalk:
    enabled: true
    extra:
      accounts:
        default:
          enabled: true
          app_id: your_app_id
          app_secret: your_app_secret
          signing_secret: your_signing_secret
          mode: webhook
          webhook_host: 0.0.0.0
          webhook_port: 8080
          webhook_path: /callback
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
      accounts:
        default:
          enabled: true
          app_id: your_app_id
          app_secret: your_app_secret
          signing_secret: your_signing_secret
          mode: relay
          relay_url: wss://relay.example.com/ws
```

Configure the SeaTalk Bot App callback URL to point at the externally reachable
endpoint, usually through a reverse proxy or tunnel that terminates TLS.

`dm_policy` controls direct messages. With the default `allowlist`, `allow_from`
must match the SeaTalk sender email or employee code. `open` allows all direct
messages. `pairing` is not supported by this plugin version.

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

Home channel is not stored in `config.yaml`. It follows Hermes' standard env
contract:

```dotenv
SEATALK_HOME_CHANNEL=default:group/123
SEATALK_HOME_CHANNEL_THREAD_ID=
SEATALK_HOME_CHANNEL_NAME=SeaTalk Home
```

`SEATALK_HOME_CHANNEL` is a SeaTalk target string and may use
`group/<group_id>` for groups. `group_allow_from` is different: it stores raw
SeaTalk group ids only. When multiple accounts are configured, use an
account-qualified target such as `staging:group/123`.

The repository publishes installable runtime content through the `publish`
branch. `scripts/publish-release.sh` keeps that branch limited to plugin runtime
files and README content; it does not publish docs, tests, deploy helpers, or
local configuration.

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
  `~/.hermes/config.yaml`.

## Tests

The automated suite uses fake SeaTalk HTTP/WebSocket objects and does not need
real Bot App credentials:

```bash
PYTHONDONTWRITEBYTECODE=1 uv run --directory ../../hermes-agent pytest
```

Real SeaTalk verification is manual and tracked separately in
`docs/test/e2e_hermes-seatalk-plugin_runbook_zh.md`.
