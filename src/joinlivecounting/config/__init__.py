import os

from dotenv import load_dotenv

load_dotenv()


class ConfigError(RuntimeError):
    pass


def _required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ConfigError(f"Missing required env var: {name}")
    return value


def _optional(name: str, fallback: str) -> str:
    return os.environ.get(name, "").strip() or fallback


CLIENT_ID = _required("REDDIT_CLIENT_ID")
CLIENT_SECRET = _required("REDDIT_CLIENT_SECRET")
REDIRECT_URI = _required("OAUTH_REDIRECT_URI")
USER_AGENT = _required("REDDIT_USER_AGENT")

BOT_REFRESH_TOKEN = os.environ.get("REDDIT_BOT_REFRESH_TOKEN", "").strip()

THREADS_FILE = _optional("THREADS_FILE", "threads.json")
DATABASE_FILE = _optional("DATABASE_FILE", "joins.db")
CONTRIBUTOR_SCAN_SECONDS = float(_optional("CONTRIBUTOR_SCAN_SECONDS", "86400"))
SCAN_CHECK_SECONDS = float(_optional("SCAN_CHECK_SECONDS", "300"))

ALLOWED_RETURN_HOSTS = {
    host.strip().lower()
    for host in _optional("ALLOWED_RETURN_HOSTS", "").split(",")
    if host.strip()
}

def _name_set(name: str) -> set[str]:
    return {
        entry.strip().lstrip("/").removeprefix("u/").casefold()
        for entry in _optional(name, "").split(",")
        if entry.strip()
    }


JOIN_ALLOWLIST = _name_set("JOIN_ALLOWLIST")
JOIN_DENYLIST = _name_set("JOIN_DENYLIST")

PORT = int(_optional("PORT", "8080"))
RESULT_REDIRECT_SECONDS = float(_optional("RESULT_REDIRECT_SECONDS", "0.7"))
FLASK_SECRET_KEY = _required("FLASK_SECRET_KEY")

BOT_SCOPES = ["livemanage", "submit", "identity", "read"]
USER_SCOPES = ["identity", "livemanage"]


def require_bot_token() -> str:
    if not BOT_REFRESH_TOKEN:
        raise ConfigError(
            "REDDIT_BOT_REFRESH_TOKEN is not set. "
            "Run `python bootstrap_token.py` and paste the result into .env."
        )
    return BOT_REFRESH_TOKEN
