import logging
import threading
import time

from .. import config
from ..config import threads
from ..storage import contributors as contributor_store
from . import client

log = logging.getLogger(__name__)

_started = False
_lock = threading.Lock()


def scan(thread_id: str) -> int | None:
    started = time.time()
    try:
        bot_thread = client.bot().live(thread_id)
        contributors = list(bot_thread.contributor())
    except Exception as exc:
        log.warning(f"contributor scan failed for {thread_id}: {type(exc).__name__}: {exc}")
        return None

    blocked = []
    for contributor in contributors:
        permissions = getattr(contributor, "permissions", None)
        if permissions is not None and len(permissions) == 0:
            blocked.append(str(contributor))

    count = len(contributors)
    contributor_store.set_baseline(thread_id, count, started)
    contributor_store.set_blocked(thread_id, blocked)
    log.info(
        f"scanned {thread_id}: {count} contributors, {len(blocked)} blocked,"
        f" in {time.time() - started:.1f}s"
    )
    return count


def _tick() -> None:
    for thread in threads.all_threads().values():
        previous = contributor_store.claim_scan(thread.thread_id, config.CONTRIBUTOR_SCAN_SECONDS)
        if previous is None:
            continue
        if scan(thread.thread_id) is None:
            contributor_store.restore_scan_time(thread.thread_id, previous)


def _loop() -> None:
    while True:
        try:
            _tick()
        except Exception:
            log.exception("scanner tick failed")
        time.sleep(config.SCAN_CHECK_SECONDS)


def start() -> None:
    global _started
    with _lock:
        if _started:
            return
        _started = True
    threading.Thread(target=_loop, name="contributor-scanner", daemon=True).start()
