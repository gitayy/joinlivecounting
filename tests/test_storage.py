import sqlite3
import time

from joinlivecounting import config
from joinlivecounting.config.threads import RateLimit
from joinlivecounting.storage import contributors, joins

MINUTE = RateLimit(60, 3)
HOUR = RateLimit(3600, 5)


def age_joins(thread_id, seconds):
    conn = sqlite3.connect(config.DATABASE_FILE)
    conn.execute(
        "UPDATE joins SET joined_at = joined_at - ? WHERE thread_id = ?",
        (seconds, thread_id),
    )
    conn.commit()
    conn.close()


class TestRateLimits:
    def test_allows_up_to_the_limit(self):
        for i in range(3):
            assert joins.claim("t", f"u{i}", (MINUTE,)) is None

    def test_blocks_past_the_limit(self):
        for i in range(3):
            joins.claim("t", f"u{i}", (MINUTE,))
        assert joins.claim("t", "u4", (MINUTE,)) == MINUTE

    def test_blocked_join_is_not_recorded(self):
        for i in range(3):
            joins.claim("t", f"u{i}", (MINUTE,))
        joins.claim("t", "u4", (MINUTE,))
        assert len(joins.recent("t", 60)) == 3

    def test_reports_the_first_limit_exceeded(self):
        for i in range(3):
            joins.claim("t", f"u{i}", (MINUTE, HOUR))
        assert joins.claim("t", "u4", (MINUTE, HOUR)) == MINUTE

    def test_a_longer_window_still_binds_after_a_short_one_slides(self):
        for i in range(3):
            joins.claim("t", f"u{i}", (MINUTE, HOUR))
        age_joins("t", 120)
        assert joins.claim("t", "u4", (MINUTE, HOUR)) is None
        assert joins.claim("t", "u5", (MINUTE, HOUR)) is None
        assert joins.claim("t", "u6", (MINUTE, HOUR)) == HOUR

    def test_windows_slide_rather_than_reset(self):
        for i in range(3):
            joins.claim("t", f"u{i}", (MINUTE,))
        age_joins("t", 30)
        assert joins.claim("t", "u4", (MINUTE,)) == MINUTE
        age_joins("t", 31)
        assert joins.claim("t", "u4", (MINUTE,)) is None

    def test_threads_have_separate_budgets(self):
        for i in range(3):
            joins.claim("a", f"u{i}", (MINUTE,))
        assert joins.claim("b", "u0", (MINUTE,)) is None

    def test_no_limits_configured_never_blocks(self):
        for i in range(50):
            assert joins.claim("t", f"u{i}", ()) is None

    def test_release_frees_a_slot(self):
        for i in range(3):
            joins.claim("t", f"u{i}", (MINUTE,))
        assert joins.claim("t", "u4", (MINUTE,)) == MINUTE
        joins.release("t", "u0")
        assert joins.claim("t", "u4", (MINUTE,)) is None

    def test_release_removes_only_one_row(self):
        joins.claim("t", "same", (HOUR,))
        joins.claim("t", "same", (HOUR,))
        joins.release("t", "same")
        assert len(joins.recent("t", 60)) == 1

    def test_first_exceeded_does_not_consume_a_slot(self):
        for i in range(3):
            joins.claim("t", f"u{i}", (MINUTE,))
        joins.release("t", "u0")
        assert joins.first_exceeded("t", (MINUTE,)) is None
        assert joins.first_exceeded("t", (MINUTE,)) is None
        assert joins.claim("t", "new", (MINUTE,)) is None

    def test_survives_a_reconnect(self):
        for i in range(3):
            joins.claim("t", f"u{i}", (MINUTE,))
        assert joins.first_exceeded("t", (MINUTE,)) == MINUTE


class TestBaseline:
    def test_unscanned_thread_has_no_baseline(self):
        assert contributors.baseline("t") is None

    def test_baseline_round_trips(self):
        now = time.time()
        contributors.set_baseline("t", 42, now)
        count, scanned_at = contributors.baseline("t")
        assert count == 42
        assert scanned_at == now

    def test_joins_since_counts_only_newer_rows(self):
        joins.claim("t", "old", ())
        age_joins("t", 500)
        cutoff = time.time() - 100
        joins.claim("t", "new", ())
        assert joins.joins_since("t", cutoff) == 1

    def test_claimed_but_unscanned_reads_as_unknown(self):
        contributors.claim_scan("t", 86400)
        assert contributors.baseline("t") is None


class TestScanClaim:
    def test_first_claim_wins(self):
        assert contributors.claim_scan("t", 86400) is not None

    def test_second_claim_loses(self):
        contributors.claim_scan("t", 86400)
        assert contributors.claim_scan("t", 86400) is None

    def test_fresh_baseline_is_not_reclaimed(self):
        contributors.set_baseline("t", 10, time.time())
        assert contributors.claim_scan("t", 86400) is None

    def test_stale_baseline_is_reclaimed(self):
        contributors.set_baseline("t", 10, time.time() - 90000)
        assert contributors.claim_scan("t", 86400) is not None

    def test_restoring_the_time_makes_it_claimable_again(self):
        contributors.set_baseline("t", 10, time.time() - 90000)
        previous = contributors.claim_scan("t", 86400)
        assert contributors.claim_scan("t", 86400) is None
        contributors.restore_scan_time("t", previous)
        assert contributors.claim_scan("t", 86400) is not None


class TestBlocked:
    def test_nobody_blocked_by_default(self):
        assert contributors.is_blocked("t", "someone") is False

    def test_blocked_user_is_recognised(self):
        contributors.set_blocked("t", ["banned_user"])
        assert contributors.is_blocked("t", "banned_user") is True

    def test_lookup_is_case_insensitive(self):
        contributors.set_blocked("t", ["Banned_User"])
        assert contributors.is_blocked("t", "bAnNeD_uSeR") is True

    def test_rescan_replaces_the_previous_set(self):
        contributors.set_blocked("t", ["first"])
        contributors.set_blocked("t", ["second"])
        assert contributors.is_blocked("t", "first") is False
        assert contributors.is_blocked("t", "second") is True

    def test_empty_scan_clears_everyone(self):
        contributors.set_blocked("t", ["a", "b"])
        contributors.set_blocked("t", [])
        assert contributors.blocked_count("t") == 0

    def test_threads_keep_separate_lists(self):
        contributors.set_blocked("a", ["x"])
        assert contributors.is_blocked("b", "x") is False
