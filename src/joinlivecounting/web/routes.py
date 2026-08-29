import logging
import secrets

from flask import Blueprint, redirect, render_template, request, session

from .. import storage
from ..config import threads as thread_config
from ..reddit import client, join as join_flow
from . import pages
from .urls import safe_return_url

log = logging.getLogger(__name__)
bp = Blueprint("join", __name__, template_folder="templates")


@bp.get("/health")
def health():
    loaded = thread_config.all_threads()
    return {
        "status": "ok",
        "threads": {
            t.thread_id: {
                "name": t.name,
                "max_contributors": t.max_contributors,
                "rate_limits": [str(limit) for limit in t.rate_limits],
                "contributors": join_flow.estimated_contributors(t.thread_id),
                "blocked": storage.contributors.blocked_count(t.thread_id),
            }
            for t in loaded.values()
        },
    }

@bp.get("/threads/<key>/join")
def join(key: str):
    thread = thread_config.resolve(key)
    if thread is None:
        log.warning(f"join requested for unknown thread {key!r}")
        return render_template(
            "result.html",
            outcome="error",
            heading="Unknown thread",
            message=f"Could not find thread “{key}”",
            detail=None,
            target=None,
            delay=0,
            auto=False,
        ), 404

    return_url = safe_return_url(request.args.get("return"), thread)

    if join_flow.is_full(thread):
        log.info(f"join refused: {thread.name} is full")
        return pages.render("full", thread, thread.return_url, status=503)

    exceeded = storage.joins.first_exceeded(thread.thread_id, thread.rate_limits)
    if exceeded is not None:
        log.info(f"join refused: {thread.name} over {exceeded}")
        return pages.render("busy", thread, thread.return_url, limit=str(exceeded), status=429)

    state = secrets.token_urlsafe(32)
    session["oauth_state"] = state
    session["thread_id"] = thread.thread_id
    session["return_url"] = return_url

    return redirect(client.user_auth_url(state))

@bp.get("/callback")
def callback():
    expected_state = session.pop("oauth_state", None)
    thread = thread_config.find(session.pop("thread_id", None))
    return_url = session.pop("return_url", None) or (
        thread.return_url if thread else "https://www.reddit.com/"
    )

    if request.args.get("error"):
        log.info(f"authorisation declined: {request.args['error']}")
        return pages.render("declined", thread, return_url)

    if not expected_state or request.args.get("state") != expected_state:
        log.warning("state mismatch on callback")
        return pages.render(
            "error", thread, return_url,
            detail="The sign-in link expired or was already used. Start again from the site.",
        )

    code = request.args.get("code")
    if not code or thread is None:
        return pages.render(
            "error", thread, return_url,
            detail="The session was lost before Reddit sent you back. Start again from the site.",
        )

    try:
        user_reddit = client.user_from_code(code)
        username, newly_joined = join_flow.join(user_reddit, thread)
    except join_flow.NotAllowed as exc:
        log.info(f"join refused: {exc}")
        return pages.render("blocked", thread, return_url, status=403)
    except join_flow.ThreadFull:
        log.info(f"join refused at callback: {thread.name} is full")
        return pages.render("full", thread, return_url, status=503)
    except join_flow.RateLimited as exc:
        log.info(f"join refused at callback: {thread.name} over {exc.limit}")
        return pages.render("busy", thread, return_url, limit=str(exc.limit), status=429)
    except join_flow.JoinError as exc:
        log.warning(f"join failed on {thread.thread_id}: {exc}")
        return pages.render("error", thread, return_url, detail=str(exc))
    except Exception as exc:
        log.exception(f"unexpected failure joining {thread.thread_id}")
        return pages.render("error", thread, return_url, detail=f"{type(exc).__name__}: {exc}")

    log.info(f"{username} joined {thread.name} (new={newly_joined})")
    return pages.render(
        "ok" if newly_joined else "already", thread, return_url, user=username
    )
