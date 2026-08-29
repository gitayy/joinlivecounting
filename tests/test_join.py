import praw
import prawcore
import pytest

from joinlivecounting import config
from joinlivecounting.reddit import join as join_flow
from joinlivecounting.storage import contributors, joins

from conftest import FakeRedditor, FakeReddit


def api_error(name, message="something"):
    return praw.exceptions.RedditAPIException([[name, message, None]])


def response_error(status=403):
    class Response:
        status_code = status

    return prawcore.exceptions.ResponseException(Response())


def as_user(name, live):
    return FakeReddit(username=name, live_thread=live)


class TestHappyPath:
    def test_returns_the_username_and_marks_it_new(self, thread, as_bot):
        assert join_flow.join(as_user("alice", as_bot), thread) == ("alice", True)

    def test_invites_with_the_configured_permissions(self, thread, as_bot):
        join_flow.join(as_user("alice", as_bot), thread)
        assert as_bot.invited == [("alice", ["update"])]

    def test_empty_permissions_are_passed_through(self, small_thread, as_bot):
        join_flow.join(as_user("alice", as_bot), small_thread)
        assert as_bot.invited == [("alice", [])]

    def test_accepts_the_invite(self, thread, as_bot):
        join_flow.join(as_user("alice", as_bot), thread)
        assert as_bot.accepted == 1

    def test_posts_the_welcome(self, thread, as_bot):
        join_flow.join(as_user("alice", as_bot), thread)
        assert as_bot.posts == ["*/u/alice joined testthread*"]

    def test_records_the_join(self, thread, as_bot):
        join_flow.join(as_user("alice", as_bot), thread)
        assert [r["username"] for r in joins.recent(thread.thread_id, 60)] == ["alice"]

    def test_a_failed_welcome_does_not_fail_the_join(self, thread, as_bot):
        as_bot.welcome_error = api_error("RATELIMIT")
        assert join_flow.join(as_user("alice", as_bot), thread) == ("alice", True)
        assert as_bot.accepted == 1


class TestAlreadyContributor:
    @pytest.fixture
    def already(self, as_bot):
        as_bot.contributors = [FakeRedditor("alice", ["update"])]
        as_bot.invite_error = api_error("LIVEUPDATE_ALREADY_CONTRIBUTOR", "already")
        as_bot.accept_error = api_error("LIVEUPDATE_NO_INVITE_FOUND", "no pending invite")
        return as_bot

    def test_reports_not_newly_joined(self, thread, already):
        assert join_flow.join(as_user("alice", already), thread) == ("alice", False)

    def test_does_not_post_a_second_welcome(self, thread, already):
        join_flow.join(as_user("alice", already), thread)
        assert already.posts == []

    def test_does_not_consume_a_rate_limit_slot(self, thread, already):
        join_flow.join(as_user("alice", already), thread)
        assert joins.recent(thread.thread_id, 60) == []

    def test_matches_the_contributor_case_insensitively(self, thread, already):
        already.contributors = [FakeRedditor("ALICE", ["update"])]
        assert join_flow.join(as_user("alice", already), thread) == ("alice", False)


class TestFailures:
    def test_unidentifiable_user_raises(self, thread, as_bot):
        with pytest.raises(join_flow.JoinError, match="could not identify"):
            join_flow.join(as_user(response_error(), as_bot), thread)

    def test_invite_failure_raises_and_frees_the_slot(self, thread, as_bot):
        as_bot.invite_error = api_error("SUBREDDIT_NOTALLOWED", "nope")
        with pytest.raises(join_flow.JoinError, match="invite failed"):
            join_flow.join(as_user("alice", as_bot), thread)
        assert joins.recent(thread.thread_id, 60) == []

    def test_no_invite_found_without_membership_is_a_real_error(self, thread, as_bot):
        as_bot.accept_error = api_error("LIVEUPDATE_NO_INVITE_FOUND", "no pending invite")
        with pytest.raises(join_flow.JoinError, match="accepting the invite failed"):
            join_flow.join(as_user("alice", as_bot), thread)
        assert joins.recent(thread.thread_id, 60) == []

    def test_a_failed_join_leaves_no_welcome(self, thread, as_bot):
        as_bot.accept_error = api_error("LIVEUPDATE_NO_INVITE_FOUND")
        with pytest.raises(join_flow.JoinError):
            join_flow.join(as_user("alice", as_bot), thread)
        assert as_bot.posts == []


class TestBlocking:
    def test_zero_permission_contributor_is_refused(self, thread, as_bot):
        contributors.set_blocked(thread.thread_id, ["alice"])
        with pytest.raises(join_flow.NotAllowed):
            join_flow.join(as_user("alice", as_bot), thread)

    def test_a_blocked_user_consumes_no_slot(self, thread, as_bot):
        contributors.set_blocked(thread.thread_id, ["alice"])
        with pytest.raises(join_flow.NotAllowed):
            join_flow.join(as_user("alice", as_bot), thread)
        assert joins.recent(thread.thread_id, 60) == []

    def test_a_blocked_user_is_never_invited(self, thread, as_bot):
        contributors.set_blocked(thread.thread_id, ["alice"])
        with pytest.raises(join_flow.NotAllowed):
            join_flow.join(as_user("alice", as_bot), thread)
        assert as_bot.invited == []

    def test_allowlist_overrides_the_block(self, thread, as_bot, monkeypatch):
        contributors.set_blocked(thread.thread_id, ["alice"])
        monkeypatch.setattr(config, "JOIN_ALLOWLIST", {"alice"})
        assert join_flow.join(as_user("alice", as_bot), thread) == ("alice", True)

    def test_denylist_blocks_an_unblocked_user(self, thread, as_bot, monkeypatch):
        monkeypatch.setattr(config, "JOIN_DENYLIST", {"alice"})
        with pytest.raises(join_flow.NotAllowed):
            join_flow.join(as_user("alice", as_bot), thread)

    def test_denylist_beats_allowlist(self, thread, as_bot, monkeypatch):
        monkeypatch.setattr(config, "JOIN_ALLOWLIST", {"alice"})
        monkeypatch.setattr(config, "JOIN_DENYLIST", {"alice"})
        with pytest.raises(join_flow.NotAllowed):
            join_flow.join(as_user("alice", as_bot), thread)


class TestCapacity:
    def test_full_thread_refuses(self, small_thread, as_bot):
        contributors.set_baseline(small_thread.thread_id, 5, 1.0)
        with pytest.raises(join_flow.ThreadFull):
            join_flow.join(as_user("alice", as_bot), small_thread)

    def test_a_full_thread_consumes_no_slot(self, small_thread, as_bot):
        contributors.set_baseline(small_thread.thread_id, 5, 1.0)
        with pytest.raises(join_flow.ThreadFull):
            join_flow.join(as_user("alice", as_bot), small_thread)
        assert joins.recent(small_thread.thread_id, 60) == []

    def test_recorded_joins_count_towards_the_cap(self, small_thread, as_bot):
        contributors.set_baseline(small_thread.thread_id, 4, 1.0)
        assert join_flow.is_full(small_thread) is False
        joins.claim(small_thread.thread_id, "someone", ())
        assert join_flow.is_full(small_thread) is True

    def test_an_unknown_count_is_never_full(self, small_thread):
        assert join_flow.is_full(small_thread) is False

    def test_rate_limit_refuses(self, small_thread, as_bot):
        join_flow.join(as_user("alice", as_bot), small_thread)
        with pytest.raises(join_flow.RateLimited) as caught:
            join_flow.join(as_user("bob", as_bot), small_thread)
        assert caught.value.limit.seconds == 60

    def test_a_rate_limited_user_is_never_invited(self, small_thread, as_bot):
        join_flow.join(as_user("alice", as_bot), small_thread)
        as_bot.invited.clear()
        with pytest.raises(join_flow.RateLimited):
            join_flow.join(as_user("bob", as_bot), small_thread)
        assert as_bot.invited == []


class TestErrorClassifiers:
    @pytest.mark.parametrize(
        "name,already,no_invite",
        [
            ("LIVEUPDATE_ALREADY_CONTRIBUTOR", True, False),
            ("LIVEUPDATE_NO_INVITE_FOUND", False, True),
            ("SUBREDDIT_NOTALLOWED", False, False),
        ],
    )
    def test_reddit_error_names(self, name, already, no_invite):
        exc = api_error(name)
        assert join_flow._already_on_thread(exc) is already
        assert join_flow._no_pending_invite(exc) is no_invite
