import json

import pytest
from flask import Flask

from joinlivecounting import config, storage
from joinlivecounting.config import threads as thread_config

THREADS_FIXTURE = {
    "defaults": {
        "permissions": ["update"],
        "welcome_template": "*/u/{user} joined {thread}*",
        "max_contributors": 9900,
        "rate_limits": [{"seconds": 60, "max": 3}],
    },
    "threads": {
        "abc123": {"name": "testthread"},
        "def456": {
            "name": "eventthread",
            "permissions": [],
            "max_contributors": 5,
            "rate_limits": [{"seconds": 60, "max": 1}, {"seconds": 3600, "max": 2}],
            "return_url": "https://counting.gg/live",
        },
    },
}


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """Any real HTTP call fails loudly instead of reaching Reddit."""

    def explode(*args, **kwargs):
        raise AssertionError("test attempted a real network request")

    monkeypatch.setattr("prawcore.sessions.Session.request", explode)
    monkeypatch.setattr("requests.Session.request", explode, raising=False)


@pytest.fixture(autouse=True)
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATABASE_FILE", str(tmp_path / "test.db"))
    storage.init()
    return config.DATABASE_FILE


@pytest.fixture(autouse=True)
def threads_file(tmp_path, monkeypatch):
    path = tmp_path / "threads.json"
    path.write_text(json.dumps(THREADS_FIXTURE), encoding="utf-8")
    monkeypatch.setattr(config, "THREADS_FILE", str(path))
    monkeypatch.setattr(thread_config, "_cache", {"mtime": None, "threads": {}})
    return path


@pytest.fixture(autouse=True)
def empty_lists(monkeypatch):
    monkeypatch.setattr(config, "JOIN_ALLOWLIST", set())
    monkeypatch.setattr(config, "JOIN_DENYLIST", set())


@pytest.fixture
def thread():
    return thread_config.resolve("testthread")


@pytest.fixture
def small_thread():
    return thread_config.resolve("eventthread")


@pytest.fixture
def client(monkeypatch):
    from joinlivecounting.web.routes import bp

    monkeypatch.setattr(config, "ALLOWED_RETURN_HOSTS", {"counting.gg"})
    app = Flask("test")
    app.secret_key = "test-secret"
    app.register_blueprint(bp)
    app.config.update(TESTING=True)
    return app.test_client()


class FakeRedditor:
    def __init__(self, name, permissions=None):
        self.name = name
        if permissions is not None:
            self.permissions = permissions

    def __str__(self):
        return self.name


class FakeContributors:
    def __init__(self, thread):
        self.thread = thread

    def __call__(self):
        return list(self.thread.contributors)

    def invite(self, redditor, *, permissions=None):
        if self.thread.invite_error:
            raise self.thread.invite_error
        self.thread.invited.append((str(redditor), permissions))

    def accept_invite(self):
        if self.thread.accept_error:
            raise self.thread.accept_error
        self.thread.accepted += 1


class FakeContrib:
    def __init__(self, thread):
        self.thread = thread

    def add(self, body):
        if self.thread.welcome_error:
            raise self.thread.welcome_error
        self.thread.posts.append(body)


class FakeLiveThread:
    def __init__(self, thread_id, contributors=()):
        self.id = thread_id
        self.contributors = list(contributors)
        self.invited = []
        self.posts = []
        self.accepted = 0
        self.invite_error = None
        self.accept_error = None
        self.welcome_error = None
        self.contributor = FakeContributors(self)
        self.contrib = FakeContrib(self)


class FakeReddit:
    def __init__(self, username=None, live_thread=None):
        self._username = username
        self._live = live_thread
        self.user = self

    def me(self):
        if isinstance(self._username, Exception):
            raise self._username
        return FakeRedditor(self._username)

    def live(self, thread_id):
        if self._live is None:
            self._live = FakeLiveThread(thread_id)
        return self._live


@pytest.fixture
def fake_live():
    return FakeLiveThread("abc123")


@pytest.fixture
def as_bot(monkeypatch, fake_live):
    from joinlivecounting.reddit import join as join_flow

    monkeypatch.setattr(join_flow.client, "bot", lambda: FakeReddit(live_thread=fake_live))
    return fake_live
