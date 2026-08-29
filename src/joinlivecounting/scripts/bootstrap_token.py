import secrets
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

import praw

from .. import config

STATE = secrets.token_urlsafe(16)
result: dict[str, str] = {}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        params = parse_qs(urlparse(self.path).query)
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()

        if params.get("state", [None])[0] != STATE:
            self.wfile.write(b"state mismatch -- start over")
            return

        if "error" in params:
            self.wfile.write(f"reddit said: {params['error'][0]}".encode())
            return

        result["code"] = params.get("code", [""])[0]
        self.wfile.write(b"Got it. Close this tab and return to the terminal.")

    def log_message(self, *args):
        pass


def main() -> int:
    reddit = praw.Reddit(
        client_id=config.CLIENT_ID,
        client_secret=config.CLIENT_SECRET,
        redirect_uri=config.REDIRECT_URI,
        user_agent=config.USER_AGENT,
    )

    url = reddit.auth.url(scopes=config.BOT_SCOPES, state=STATE, duration="permanent")
    port = urlparse(config.REDIRECT_URI).port or 80

    print("\nLog into Reddit as the BOT account, then open:\n")
    print(f"  {url}\n")
    print(f"Waiting for the redirect on port {port} ...")

    server = HTTPServer(("localhost", port), Handler)
    server.timeout = 0.5

    try:
        while "code" not in result:
            server.handle_request()
    except KeyboardInterrupt:
        print("\nCancelled.")
        return 1

    refresh_token = reddit.auth.authorize(result["code"])
    print(f"\nAuthorised as: u/{reddit.user.me()}")
    print("\nPaste this into .env:\n")
    print(f"REDDIT_BOT_REFRESH_TOKEN={refresh_token}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
