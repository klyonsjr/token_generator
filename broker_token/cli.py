import argparse
import datetime
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from broker_token.oauth import get_access_token, get_authorization_code

# ---------------------------------------------------------------------------
# Broker configuration
# ---------------------------------------------------------------------------

_ENV_FILE_PATH = {
    "schwab": os.path.expanduser("~/.config/schwab/schwab.env"),
    "tasty": os.path.expanduser("~/.config/tasty/tasty.env"),
}

_CLIENT_ID_VAR = {
    "schwab": "SCHWAB_CLIENT_ID",
    "tasty": "TASTY_CLIENT_ID",
}

_CLIENT_SECRET_VAR = {
    "schwab": "SCHWAB_CLIENT_SECRET",
    "tasty": "TASTY_CLIENT_SECRET",
}

_APP_HOST = {
    "schwab": "myapp.kelyons.com",
    "tasty": "myapp.kelyons.com",
}

_AUTH_URL = {
    "schwab": "https://api.schwabapi.com/v1/oauth/authorize",
    "tasty": "https://my.tastytrade.com/auth.html",
}

_ACCESS_URL = {
    "schwab": "https://api.schwabapi.com/v1/oauth/token",
    "tasty": "https://api.tastyworks.com/oauth/token",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def write_token_file(path: str, token_data: dict) -> None:
    """Serialize *token_data* to *path* as indented JSON."""
    with open(path, "w") as f:
        json.dump(token_data, f, indent=4)


def _load_credentials(broker: str) -> tuple[str, str]:
    """Load client_id and client_secret for *broker* from its env file.

    Raises RuntimeError if credentials are not found.
    """
    env_path = _ENV_FILE_PATH[broker]
    load_dotenv(env_path)

    client_id = os.getenv(_CLIENT_ID_VAR[broker])
    client_secret = os.getenv(_CLIENT_SECRET_VAR[broker])

    if not client_id or not client_secret:
        raise RuntimeError(
            f"Client credentials not found. "
            f"Set {_CLIENT_ID_VAR[broker]} and {_CLIENT_SECRET_VAR[broker]} "
            f"in {env_path}"
        )

    return client_id, client_secret


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate an OAuth2 token for a broker and write it to a JSON file."
    )
    parser.add_argument(
        "--broker", "-b",
        choices=list(_AUTH_URL.keys()),
        default="schwab",
        help="Broker to authenticate with (default: schwab)",
    )
    parser.add_argument(
        "--token-file", "-o",
        default="token.json",
        help="Path to write the token JSON (default: token.json)",
    )
    args = parser.parse_args()

    broker = args.broker
    token_file = args.token_file
    host = _APP_HOST[broker]

    try:
        client_id, client_secret = _load_credentials(broker)
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        code = get_authorization_code(
            host=host,
            port=443,
            client_id=client_id,
            auth_url=_AUTH_URL[broker],
        )
    except (RuntimeError, TimeoutError) as e:
        print(f"Error obtaining authorization code: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"Authorization code received.")

    try:
        token_data = get_access_token(
            authorization_code=code,
            client_id=client_id,
            client_secret=client_secret,
            access_url=_ACCESS_URL[broker],
            host=host,
        )
    except Exception as e:
        print(f"Error exchanging authorization code for token: {e}", file=sys.stderr)
        sys.exit(1)

    token_data["client_id"] = client_id
    token_data["client_secret"] = client_secret

    # Ensure all datetime values are ISO strings for JSON serialization
    for k, v in list(token_data.items()):
        if isinstance(v, datetime.datetime):
            token_data[k] = v.isoformat()

    write_token_file(token_file, token_data)
    print(f"Token written to {token_file}")
