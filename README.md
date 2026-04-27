# broker-token

Generates an OAuth2 access token for a broker (Schwab or Tastytrade) and writes it to a JSON file. Intended as the first step in the stock analysis pipeline; the resulting token file is consumed by `token_refresher`.

## Installation

```bash
pip install -e /path/to/broker_token
```

## Credentials setup

Create the env file for your broker and add your client credentials:

**Schwab** — `~/.config/schwab/schwab.env`:
```
SCHWAB_CLIENT_ID=your_client_id
SCHWAB_CLIENT_SECRET=your_client_secret
```

**Tastytrade** — `~/.config/tasty/tasty.env`:
```
TASTY_CLIENT_ID=your_client_id
TASTY_CLIENT_SECRET=your_client_secret
```

## Prerequisites

The OAuth2 redirect URI is `https://myapp.kelyons.com/callback`. Your machine must resolve `myapp.kelyons.com` to `127.0.0.1` (add an entry to `/etc/hosts` or equivalent). A self-signed TLS certificate (`server.crt` / `server.key`) is generated automatically in the current directory if absent.

## Usage

```bash
# Schwab (default), writes token.json
broker-token

# Specify broker and output file
broker-token --broker schwab --token-file token_schwab.json
broker-token --broker tasty   --token-file token_tasty.json

# Also runnable as a module
python -m broker_token --broker schwab --token-file token_schwab.json
```

### Options

| Option | Default | Description |
|---|---|---|
| `--broker`, `-b` | `schwab` | Broker to authenticate (`schwab` or `tasty`) |
| `--token-file`, `-o` | `token.json` | Path to write the resulting token JSON |

## Token file format

The generated token file contains the fields required by `token_refresher`:

```json
{
    "access_token": "...",
    "refresh_token": "...",
    "expiration_timestamp": "2026-01-01T00:00:00",
    "refresh_token_expiration_timestamp": "2026-01-07T23:00:00",
    "client_id": "...",
    "client_secret": "..."
}
```

Timestamps are ISO 8601 strings. `expiration_timestamp` is derived from `expires_in` (minus a 30-second buffer). `refresh_token_expiration_timestamp` is set to 6 days 23 hours from the time of issue.
