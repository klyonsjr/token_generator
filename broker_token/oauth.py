import datetime
import http.server
import json
import ssl
import time
import urllib.parse
import webbrowser

import requests

from broker_token.cert import create_self_signed_cert


class _OAuth2Handler(http.server.BaseHTTPRequestHandler):
    """HTTP handler that captures the OAuth2 authorization code from the redirect."""

    def __init__(self, *args, **kwargs):
        self._authorization_code = None
        super().__init__(*args, **kwargs)

    def do_GET(self):
        parsed_params = {}
        if "?" in self.path:
            _, query_string = self.path.split("?", 1)
            params = urllib.parse.parse_qs(query_string)
            for key, values in params.items():
                parsed_params[key] = values[0] if len(values) == 1 else values

        if "code" in parsed_params:
            self._authorization_code = parsed_params["code"]

        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()
        self.wfile.write(
            b"<html><body><h1>Authorization received.</h1>"
            b"<p>You can close this window.</p></body></html>"
        )

    def do_POST(self):
        content_length = int(self.headers.get("Content-Length", 0))
        parsed_data = {}
        if content_length > 0:
            post_data = self.rfile.read(content_length)
            try:
                parsed_data = json.loads(post_data.decode())
            except (ValueError, UnicodeDecodeError):
                try:
                    decoded = post_data.decode()
                    raw = urllib.parse.parse_qs(decoded)
                    for key, values in raw.items():
                        parsed_data[key] = values[0] if len(values) == 1 else values
                except Exception:
                    pass

        if "code" in parsed_data:
            self._authorization_code = parsed_data["code"]

        self.send_response(200)
        self.send_header("Content-type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"status": "success"}).encode())

    def log_message(self, format, *args):
        pass  # suppress default access log output

    def get_authorization_code(self):
        return self._authorization_code


class _OAuth2HTTPServer(http.server.HTTPServer):
    """HTTPServer that stores the authorization code once it has been received."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.authorization_code = None

    def finish_request(self, request, client_address):
        handler = self.RequestHandlerClass(request, client_address, self)
        code = handler.get_authorization_code()
        if code:
            self.authorization_code = code

    def get_authorization_code(self):
        return self.authorization_code


def get_authorization_code(
    host: str,
    port: int,
    client_id: str,
    auth_url: str,
    cert_path: str = "server.crt",
    key_path: str = "server.key",
    timeout: int = 300,
) -> str:
    """Run a local HTTPS server, open the browser to *auth_url*, and return the
    authorization code delivered to the redirect URI.

    Raises RuntimeError if the certificate cannot be created or the server cannot start.
    Raises TimeoutError if no code is received within *timeout* seconds.
    """
    import threading

    if not __import__("os").path.exists(cert_path) or not __import__("os").path.exists(key_path):
        if not create_self_signed_cert(cert_path, key_path):
            raise RuntimeError("Could not create SSL certificate")

    server = _OAuth2HTTPServer((host, port), _OAuth2Handler)

    context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    context.load_cert_chain(cert_path, key_path)
    server.socket = context.wrap_socket(server.socket, server_side=True)

    def _run():
        try:
            server.serve_forever()
        except Exception:
            pass

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    time.sleep(1)

    params = {
        "client_id": client_id,
        "redirect_uri": f"https://{host}/callback",
        "response_type": "code",
    }
    url = auth_url + "?" + "&".join(
        f"{k}={urllib.parse.quote(str(v))}" for k, v in params.items()
    )
    print(f"Opening browser to: {url}")
    webbrowser.open(url)
    print("Waiting for authorization code (complete the flow in your browser)…")

    deadline = time.time() + timeout
    while True:
        if time.time() > deadline:
            server.shutdown()
            thread.join(timeout=5)
            raise TimeoutError("Timed out waiting for authorization code")
        code = server.get_authorization_code()
        if code:
            break
        time.sleep(0.5)

    server.shutdown()
    thread.join(timeout=5)
    return code


def get_access_token(
    authorization_code: str,
    client_id: str,
    client_secret: str,
    access_url: str,
    host: str,
) -> dict:
    """Exchange *authorization_code* for an access token dict.

    Adds ``expiration_timestamp`` and ``refresh_token_expiration_timestamp``
    fields (ISO strings) derived from the ``expires_in`` / ``refresh_token_expires_in``
    fields in the response.

    Raises requests.RequestException on HTTP failure.
    Raises ValueError on JSON parse failure.
    """
    import base64

    headers = {
        "Authorization": "Basic "
        + base64.b64encode(f"{client_id}:{client_secret}".encode()).decode(),
        "Content-Type": "application/x-www-form-urlencoded",
    }
    data = {
        "code": authorization_code,
        "redirect_uri": f"https://{host}/callback",
        "grant_type": "authorization_code",
    }

    response = requests.post(access_url, data=data, headers=headers)
    response.raise_for_status()
    token_data = response.json()

    now = datetime.datetime.now()
    token_data["expiration_timestamp"] = (
        now + datetime.timedelta(seconds=int(token_data.get("expires_in", 0)) - 30)
    ).isoformat()
    token_data["refresh_token_expiration_timestamp"] = (
        now + datetime.timedelta(days=6, hours=23)
    ).isoformat()

    return token_data
