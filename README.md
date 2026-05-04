# Hermes SeaTalk Plugin

External SeaTalk platform plugin for Hermes Agent.

## Layout

The repository root is the Hermes plugin directory. Hermes imports the root
`adapter.py` shim, while implementation code lives in the standard Python
package `hermes_seatalk/`.

```text
hermes-seatalk/
  plugin.yaml
  pyproject.toml
  adapter.py
  hermes_seatalk/
    adapter.py
    client.py
    coalescer.py
    relay.py
    targets.py
    webhook.py
```

## Install

```bash
git clone https://github.com/arxeme/hermes-seatalk.git ~/.hermes/plugins/seatalk
hermes plugins enable seatalk-platform
```

Then configure the runtime values in `~/.hermes/.env` or run:

```bash
hermes gateway setup
```

User-installed plugins only appear in the messaging-platform setup menu after
they are enabled with `hermes plugins enable`.

## Configuration

Both modes require:

- `SEATALK_APP_ID`
- `SEATALK_APP_SECRET`
- `SEATALK_SIGNING_SECRET`
- `SEATALK_MODE`, either `relay` or `webhook`

Relay mode additionally requires `SEATALK_RELAY_URL`.

Webhook mode does not require `SEATALK_RELAY_URL`; `SEATALK_WEBHOOK_HOST`,
`SEATALK_WEBHOOK_PORT`, and `SEATALK_WEBHOOK_PATH` have defaults.
