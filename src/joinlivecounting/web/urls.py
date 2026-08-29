import logging
from urllib.parse import urlsplit

from .. import config
from ..config.threads import ThreadConfig

log = logging.getLogger(__name__)


def safe_return_url(candidate: str | None, thread: ThreadConfig) -> str:
    if not candidate:
        return thread.return_url

    parsed = urlsplit(candidate)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        log.warning(f"rejected return url {candidate!r}: not an absolute http(s) url")
        return thread.return_url

    if parsed.netloc.lower() not in config.ALLOWED_RETURN_HOSTS:
        log.warning(f"rejected return url host {parsed.netloc!r}: not allowlisted")
        return thread.return_url

    return candidate
