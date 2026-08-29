import logging

import praw
import prawcore

from .. import config
from ..config.threads import RateLimit, ThreadConfig
from ..storage import contributors as contributor_store
from ..storage import joins as join_store
from . import client

log = logging.getLogger(__name__)


class JoinError(RuntimeError):
    pass


class ThreadFull(JoinError):
    pass


class NotAllowed(JoinError):
    pass


class RateLimited(JoinError):
    def __init__(self, limit: RateLimit):
        super().__init__(f"rate limit reached: {limit}")
        self.limit = limit


def _already_on_thread(exc: Exception) -> bool:
    text = str(exc).upper()
    return "ALREADY" in text or "CONFLICT" in text


def _no_pending_invite(exc: Exception) -> bool:
    return "NO_INVITE_FOUND" in str(exc).upper()


def _is_contributor(bot_thread, username: str) -> bool:
    wanted = username.casefold()
    try:
        return any(str(c).casefold() == wanted for c in bot_thread.contributor())
    except Exception:
        log.exception(f"could not read contributors for {bot_thread.id}")
        return False


def is_blocked(thread: ThreadConfig, username: str) -> bool:
    name = username.casefold()
    if name in config.JOIN_DENYLIST:
        return True
    if name in config.JOIN_ALLOWLIST:
        return False
    return contributor_store.is_blocked(thread.thread_id, name)


def estimated_contributors(thread_id: str) -> int | None:
    row = contributor_store.baseline(thread_id)
    if row is None:
        return None
    count, scanned_at = row
    return count + join_store.joins_since(thread_id, scanned_at)


def is_full(thread: ThreadConfig) -> bool:
    estimate = estimated_contributors(thread.thread_id)
    return estimate is not None and estimate >= thread.max_contributors


def join(user_reddit: praw.Reddit, thread: ThreadConfig) -> tuple[str, bool]:
    try:
        username = str(user_reddit.user.me())
    except prawcore.exceptions.ResponseException as exc:
        raise JoinError(f"could not identify the authorising user: {exc}") from exc

    if is_blocked(thread, username):
        raise NotAllowed(f"{username} is not permitted to join {thread.name}")

    if is_full(thread):
        raise ThreadFull(f"{thread.name} is at its contributor cap")

    bot_thread = client.bot().live(thread.thread_id)

    exceeded = join_store.claim(thread.thread_id, username, thread.rate_limits)
    if exceeded is not None:
        raise RateLimited(exceeded)

    claimed = True
    try:
        try:
            bot_thread.contributor.invite(username, permissions=thread.permissions)
        except praw.exceptions.RedditAPIException as exc:
            if not _already_on_thread(exc):
                raise JoinError(f"invite failed: {exc}") from exc

        try:
            user_reddit.live(thread.thread_id).contributor.accept_invite()
        except praw.exceptions.RedditAPIException as exc:
            if _already_on_thread(exc) or _no_pending_invite(exc):
                if _is_contributor(bot_thread, username):
                    join_store.release(thread.thread_id, username)
                    claimed = False
                    return username, False
            raise JoinError(f"accepting the invite failed: {exc}") from exc
    except Exception:
        if claimed:
            join_store.release(thread.thread_id, username)
        raise

    try:
        bot_thread.contrib.add(
            thread.welcome_template.format(user=username, thread=thread.name)
        )
    except praw.exceptions.RedditAPIException:
        log.exception(f"welcome post failed for {username} on {thread.thread_id}")

    return username, True
