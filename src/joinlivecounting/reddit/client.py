import praw

from .. import config


def bot() -> praw.Reddit:
    return praw.Reddit(
        client_id=config.CLIENT_ID,
        client_secret=config.CLIENT_SECRET,
        refresh_token=config.require_bot_token(),
        user_agent=config.USER_AGENT,
    )


def _unauthenticated() -> praw.Reddit:
    return praw.Reddit(
        client_id=config.CLIENT_ID,
        client_secret=config.CLIENT_SECRET,
        redirect_uri=config.REDIRECT_URI,
        user_agent=config.USER_AGENT,
    )


def user_auth_url(state: str) -> str:
    return _unauthenticated().auth.url(
        scopes=config.USER_SCOPES, state=state, duration="temporary"
    )


def user_from_code(code: str) -> praw.Reddit:
    reddit = _unauthenticated()
    reddit.auth.authorize(code)
    return reddit
