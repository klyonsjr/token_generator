import argparse
import datetime
import json
import os
import sys
import tempfile
from pathlib import Path

from dotenv import load_dotenv

try:
    import yaml
except ImportError:
    print(
        "Error: PyYAML is required but not installed. "
        "Install it with 'pip install pyyaml'.",
        file=sys.stderr,
    )
    sys.exit(1)

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
# Constants
# ---------------------------------------------------------------------------

# Fixed marker substituted for any Sensitive_Field value that would otherwise
# be emitted to standard output or standard error (R4.4).
REDACTION_MARKER = "***REDACTED***"

# Token_Data fields whose values are credentials/secrets (per the glossary).
SENSITIVE_FIELDS = frozenset(
    {"access_token", "refresh_token", "client_id", "client_secret"}
)


def redact_sensitive(mapping: dict) -> dict:
    """Return a copy of *mapping* safe to emit to stdout/stderr (R4.4).

    Every field name is preserved. Each Sensitive_Field value
    (``access_token``, ``refresh_token``, ``client_id``, ``client_secret``)
    is replaced with ``REDACTION_MARKER``; all other values are unchanged.

    This function is pure: it performs no I/O and does not mutate its input.
    """
    return {
        key: (REDACTION_MARKER if key in SENSITIVE_FIELDS else value)
        for key, value in mapping.items()
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def write_token_file(path: str, token_data: dict) -> None:
    """Serialize *token_data* to *path* as indented JSON."""
    with open(path, "w") as f:
        json.dump(token_data, f, indent=4)


def resolve_yaml_path(json_path: str, yaml_arg: str | None) -> str:
    """Return the YAML output path, or raise ValueError on an invalid path.

    - If *yaml_arg* is provided and non-blank, it takes precedence (R3.3).
    - If *yaml_arg* is empty or whitespace-only, raise ValueError (R3.5).
    - Otherwise derive from *json_path*: replace the extension in the final
      path segment with ``.yaml`` (R3.1), or append ``.yaml`` if the final
      segment has no ``.`` (R3.2).
    - If the resolved path equals *json_path*, raise ValueError (R3.4).

    This function is pure: it performs no I/O and no printing.
    """
    if yaml_arg is not None:
        if yaml_arg.strip() == "":
            raise ValueError("YAML path is invalid: empty or whitespace-only")
        resolved = yaml_arg
    else:
        # Operate on the final path segment (basename) only so directory
        # components are preserved.
        head, tail = os.path.split(json_path)
        if "." in tail:
            new_tail = tail[: tail.rfind(".")] + ".yaml"
            resolved = os.path.join(head, new_tail) if head else new_tail
        else:
            resolved = json_path + ".yaml"

    if resolved == json_path:
        raise ValueError("YAML and JSON output paths conflict")

    return resolved


def write_yaml_token_file(path: str, token_data: dict) -> None:
    """Serialize *token_data* to *path* as YAML with owner-only permissions.

    Writes atomically via a temporary file in the destination directory,
    applies ``0o600`` permissions before the file becomes visible, then
    renames it into place. On any failure, removes the temporary file so no
    partial or truncated YAML file is left at the destination (R1.5, R5.3).

    The function raises on failure and never prints; all user-facing
    messaging and exit codes live in ``main()``.
    """
    # Serialize first so a serialization error occurs before the destination
    # directory is touched (R1.2).
    serialized = yaml.safe_dump(
        token_data, default_flow_style=False, sort_keys=False
    )

    # Create the temp file in the destination directory so the final
    # os.replace is atomic on POSIX (R1.5).
    dir_name = os.path.dirname(path) or "."
    fd, temp_path = tempfile.mkstemp(dir=dir_name)

    try:
        with os.fdopen(fd, "w") as f:
            f.write(serialized)

        # Apply owner-only permissions before the file becomes visible at the
        # destination (R4.1). If chmod fails, clean up and re-raise a
        # permission error (R4.2).
        try:
            os.chmod(temp_path, 0o600)
        except OSError as e:
            raise PermissionError(
                f"Could not set permissions on {path}: {e}"
            ) from e

        # Atomically overwrite any existing file (R1.6).
        os.replace(temp_path, path)
    except BaseException:
        # Remove the temp file so no partial/truncated destination file
        # remains, then re-raise (R1.5, R5.3).
        try:
            os.remove(temp_path)
        except OSError:
            pass
        raise


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
    parser.add_argument(
        "--yaml-file", "-y",
        default=None,
        help="Path to write the token YAML (default: derived from --token-file)",
    )
    args = parser.parse_args()

    broker = args.broker
    token_file = args.token_file
    host = _APP_HOST[broker]

    # Resolve and validate the YAML output path before any file is written, so
    # an invalid or colliding path aborts the run without writing either file
    # (R3.4, R3.5).
    try:
        yaml_path = resolve_yaml_path(token_file, args.yaml_file)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

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

    # Write the JSON file first. Its content is independent of any YAML
    # argument (R2.1, R2.3, R2.4). On failure, report to stderr and leave any
    # pre-existing JSON file unchanged (R2.5).
    try:
        write_token_file(token_file, token_data)
    except OSError as e:
        print(f"Error writing token file {token_file}: {e}", file=sys.stderr)
        sys.exit(1)

    # Write the YAML file second. The writer cleans up any partial file on
    # failure; report a message including the YAML path and cause, then exit
    # non-zero, leaving the JSON file unchanged (R1.5, R5.1, R5.2).
    try:
        write_yaml_token_file(yaml_path, token_data)
    except Exception as e:
        print(f"Error writing YAML token file {yaml_path}: {e}", file=sys.stderr)
        sys.exit(1)

    # Confirmation names both paths only; no Sensitive_Field value is emitted
    # (R4.3, R5.4).
    print(f"Token written to {token_file} and {yaml_path}")
