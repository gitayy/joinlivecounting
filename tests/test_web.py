import pytest

from joinlivecounting import config
from joinlivecounting.storage import contributors, joins
from joinlivecounting.web import pages
from joinlivecounting.web.urls import safe_return_url


class TestReturnUrlAllowlist:
    def test_missing_falls_back_to_the_thread(self, thread):
        assert safe_return_url(None, thread) == thread.return_url

    @pytest.mark.parametrize(
        "candidate",
        [
            "https://evil.example.com/phish",
            "http://counting.gg.evil.com/",
            "javascript:alert(1)",
            "//counting.gg/protocol-relative",
            "/relative/path",
            "data:text/html,<script>",
            "ftp://counting.gg/x",
        ],
    )
    def test_rejects_anything_not_allowlisted(self, candidate, thread, monkeypatch):
        monkeypatch.setattr(config, "ALLOWED_RETURN_HOSTS", {"counting.gg"})
        assert safe_return_url(candidate, thread) == thread.return_url

    def test_accepts_an_allowlisted_host(self, thread, monkeypatch):
        monkeypatch.setattr(config, "ALLOWED_RETURN_HOSTS", {"counting.gg"})
        assert safe_return_url("https://counting.gg/ok", thread) == "https://counting.gg/ok"

    def test_host_match_is_case_insensitive(self, thread, monkeypatch):
        monkeypatch.setattr(config, "ALLOWED_RETURN_HOSTS", {"counting.gg"})
        assert safe_return_url("https://COUNTING.GG/x", thread) == "https://COUNTING.GG/x"

    def test_an_empty_allowlist_rejects_everything(self, thread, monkeypatch):
        monkeypatch.setattr(config, "ALLOWED_RETURN_HOSTS", set())
        assert safe_return_url("https://counting.gg/x", thread) == thread.return_url


class TestPages:
    @pytest.mark.parametrize(
        "outcome", ["ok", "already", "declined", "blocked", "full", "busy", "error"]
    )
    def test_every_outcome_renders(self, outcome, thread, client):
        with client.application.test_request_context():
            out = pages.render(outcome, thread, thread.return_url, user="alice", limit="3 per minute")
        html = out[0] if isinstance(out, tuple) else out
        assert f"join={outcome}" in html

    @pytest.mark.parametrize("outcome", ["ok", "already"])
    def test_success_reads_as_in_progress(self, outcome, thread, client):
        with client.application.test_request_context():
            html = pages.render(outcome, thread, thread.return_url, user="alice")
        assert "Joining" in html
        assert "You're in" not in html
        assert 'http-equiv="refresh"' in html

    @pytest.mark.parametrize("outcome", ["declined", "blocked", "full", "busy", "error"])
    def test_failures_do_not_redirect(self, outcome, thread, client):
        with client.application.test_request_context():
            out = pages.render(outcome, thread, thread.return_url, limit="3 per minute")
        html = out[0] if isinstance(out, tuple) else out
        assert 'http-equiv="refresh"' not in html

    def test_error_detail_is_shown(self, thread, client):
        with client.application.test_request_context():
            html = pages.render("error", thread, thread.return_url, detail="invite failed: BOOM")
        assert "invite failed: BOOM" in html

    def test_the_limit_is_named_on_the_busy_page(self, thread, client):
        with client.application.test_request_context():
            out = pages.render("busy", thread, thread.return_url, limit="3 per minute")
        html = out[0] if isinstance(out, tuple) else out
        assert "3 per minute" in html


class TestRoutes:
    def test_health_lists_threads(self, client):
        body = client.get("/health").get_json()
        assert set(body["threads"]) == {"abc123", "def456"}

    def test_health_reports_an_unscanned_count_as_unknown(self, client):
        assert client.get("/health").get_json()["threads"]["abc123"]["contributors"] is None

    def test_health_reflects_the_baseline_plus_joins(self, client):
        contributors.set_baseline("abc123", 10, 1.0)
        joins.claim("abc123", "someone", ())
        assert client.get("/health").get_json()["threads"]["abc123"]["contributors"] == 11

    def test_join_redirects_to_reddit(self, client, monkeypatch):
        from joinlivecounting.web import routes

        monkeypatch.setattr(routes.client, "user_auth_url", lambda state: "https://reddit/auth")
        response = client.get("/threads/testthread/join")
        assert response.status_code == 302
        assert response.headers["Location"] == "https://reddit/auth"

    def test_join_accepts_an_id_as_well_as_an_alias(self, client, monkeypatch):
        from joinlivecounting.web import routes

        monkeypatch.setattr(routes.client, "user_auth_url", lambda state: "https://reddit/auth")
        assert client.get("/threads/abc123/join").status_code == 302

    def test_unknown_thread_is_a_404_page(self, client):
        response = client.get("/threads/nope/join")
        assert response.status_code == 404
        assert "Unknown thread" in response.get_data(as_text=True)

    def test_a_full_thread_refuses_before_oauth(self, client):
        contributors.set_baseline("def456", 5, 1.0)
        response = client.get("/threads/eventthread/join")
        assert response.status_code == 503
        assert "Thread is full" in response.get_data(as_text=True)

    def test_a_rate_limited_thread_refuses_before_oauth(self, client):
        joins.claim("def456", "someone", ())
        response = client.get("/threads/eventthread/join")
        assert response.status_code == 429
        assert "Too many people joining" in response.get_data(as_text=True)

    def test_callback_without_state_is_an_error(self, client):
        response = client.get("/callback?code=x&state=y")
        assert "Something went wrong" in response.get_data(as_text=True)

    def test_a_declined_authorisation_says_so(self, client):
        response = client.get("/callback?error=access_denied")
        assert "Authorisation declined" in response.get_data(as_text=True)
