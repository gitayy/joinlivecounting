from urllib.parse import urlencode

from flask import render_template

from .. import config

# When we successfully join, upon redirect, Reddit sometimes still doesn't
# show the textbox immediately, likely due to permissions not propagating fully...
# So we pretend to still be "Joining..." so users don't close the window before
# it redirects
OUTCOMES = {
    "ok": ("Joining…", ""),
    "already": ("Joining…", ""),
    "declined": ("Authorisation declined", "Nothing was changed."),
    "full": ("Thread is full", "{thread} has reached its contributor limit."),
    "busy": (
        "Too many people joining",
        "{thread} is limited to {limit}. Please try again shortly.",
    ),
    "blocked": (
        "You cannot join this thread",
        "Please contact the moderators if you believe this is a mistake.",
    ),
    "error": ("Something went wrong", "You were not added to the thread."),
}

AUTO_REDIRECT = {"ok", "already"}


def render(outcome, thread=None, url=None, user=None, detail=None, limit=None, status=200):
    target = None
    if url:
        separator = "&" if "?" in url else "?"
        params = {"join": outcome}
        if user:
            params["user"] = user
        target = f"{url}{separator}{urlencode(params)}"

    heading, message = OUTCOMES[outcome]
    body = render_template(
        "result.html",
        outcome=outcome,
        heading=heading,
        message=message.format(
            user=user or "you",
            thread=thread.name if thread else "the thread",
            limit=limit or "",
        ),
        detail=detail,
        target=target,
        delay=config.RESULT_REDIRECT_SECONDS,
        auto=outcome in AUTO_REDIRECT,
    )
    return (body, status) if status != 200 else body
