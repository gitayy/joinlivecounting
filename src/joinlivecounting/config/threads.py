import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

from .. import config

log = logging.getLogger(__name__)

FALLBACK_PERMISSIONS = ["update"]
FALLBACK_WELCOME = "*/u/{user} has joined the thread*"
FALLBACK_MAX_CONTRIBUTORS = 9900

WINDOW_NAMES = {60: "minute", 3600: "hour", 86400: "day"}


class UnknownThread(KeyError):
    pass


@dataclass(frozen=True)
class RateLimit:
    seconds: int
    max: int

    @property
    def window(self) -> str:
        named = WINDOW_NAMES.get(self.seconds)
        if named:
            return named
        if self.seconds % 3600 == 0:
            return f"{self.seconds // 3600} hours"
        if self.seconds % 60 == 0:
            return f"{self.seconds // 60} minutes"
        return f"{self.seconds} seconds"

    def __str__(self) -> str:
        return f"{self.max} per {self.window}"


@dataclass(frozen=True)
class ThreadConfig:
    thread_id: str
    name: str
    permissions: list[str]
    welcome_template: str
    return_url: str
    max_contributors: int
    rate_limits: tuple[RateLimit, ...] = field(default=())


def _rate_limits(raw) -> tuple[RateLimit, ...]:
    limits = []
    for entry in raw or []:
        seconds = int(entry["seconds"])
        maximum = int(entry["max"])
        if seconds > 0 and maximum >= 0:
            limits.append(RateLimit(seconds=seconds, max=maximum))
    return tuple(sorted(limits, key=lambda limit: limit.seconds))


def _parse(raw: dict) -> dict[str, ThreadConfig]:
    defaults = raw.get("defaults") or {}
    configured = raw.get("threads") or {}

    loaded: dict[str, ThreadConfig] = {}
    for thread_id, overrides in configured.items():
        merged = {**defaults, **(overrides or {})}
        loaded[thread_id] = ThreadConfig(
            thread_id=thread_id,
            name=merged.get("name", thread_id),
            permissions=list(merged.get("permissions", FALLBACK_PERMISSIONS)),
            welcome_template=merged.get("welcome_template", FALLBACK_WELCOME),
            return_url=merged.get("return_url")
            or f"https://www.reddit.com/live/{thread_id}",
            max_contributors=int(
                merged.get("max_contributors", FALLBACK_MAX_CONTRIBUTORS)
            ),
            rate_limits=_rate_limits(merged.get("rate_limits")),
        )

    if not loaded:
        raise config.ConfigError(f"{config.THREADS_FILE} defines no threads")
    return loaded


_cache: dict = {"mtime": None, "threads": {}}


def all_threads() -> dict[str, ThreadConfig]:
    path = Path(config.THREADS_FILE)
    try:
        mtime = path.stat().st_mtime_ns
    except OSError:
        if not _cache["threads"]:
            raise config.ConfigError(f"{path} not found")
        return _cache["threads"]

    if mtime != _cache["mtime"]:
        try:
            loaded = _parse(json.loads(path.read_text(encoding="utf-8")))
        except Exception:
            if not _cache["threads"]:
                raise
            log.exception(f"{path} is unreadable; keeping the previous config")
            _cache["mtime"] = mtime
            return _cache["threads"]
        _cache["threads"] = loaded
        _cache["mtime"] = mtime
        log.info(f"loaded {len(loaded)} thread(s) from {path}")

    return _cache["threads"]


def get(thread_id: str) -> ThreadConfig:
    try:
        return all_threads()[thread_id]
    except KeyError:
        raise UnknownThread(thread_id) from None


def find(thread_id: str | None) -> ThreadConfig | None:
    return all_threads().get(thread_id) if thread_id else None


def resolve(key: str) -> ThreadConfig | None:
    loaded = all_threads()
    if key in loaded:
        return loaded[key]

    wanted = key.casefold()
    for thread in loaded.values():
        if thread.name.casefold() == wanted:
            return thread
    return None
