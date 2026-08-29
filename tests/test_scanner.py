import pytest

from joinlivecounting.reddit import scanner
from joinlivecounting.storage import contributors

from conftest import FakeLiveThread, FakeRedditor, FakeReddit


@pytest.fixture
def scanned(monkeypatch):
    live = FakeLiveThread("abc123")

    def install(people):
        live.contributors = people
        monkeypatch.setattr(scanner.client, "bot", lambda: FakeReddit(live_thread=live))
        return live

    return install


class TestScan:
    def test_records_the_contributor_count(self, scanned):
        scanned([FakeRedditor("a", ["all"]), FakeRedditor("b", ["update"])])
        assert scanner.scan("abc123") == 2
        assert contributors.baseline("abc123")[0] == 2

    def test_records_zero_permission_users_as_blocked(self, scanned):
        scanned([FakeRedditor("keeper", ["update"]), FakeRedditor("banned", [])])
        scanner.scan("abc123")
        assert contributors.is_blocked("abc123", "banned") is True
        assert contributors.is_blocked("abc123", "keeper") is False

    def test_a_missing_permissions_attribute_is_not_blocked(self, scanned):
        scanned([FakeRedditor("mystery")])
        scanner.scan("abc123")
        assert contributors.blocked_count("abc123") == 0

    def test_blocked_users_still_count_towards_the_total(self, scanned):
        scanned([FakeRedditor("a", []), FakeRedditor("b", [])])
        assert scanner.scan("abc123") == 2

    def test_regranting_permissions_clears_the_block(self, scanned):
        live = scanned([FakeRedditor("alice", [])])
        scanner.scan("abc123")
        assert contributors.is_blocked("abc123", "alice") is True
        live.contributors = [FakeRedditor("alice", ["update"])]
        scanner.scan("abc123")
        assert contributors.is_blocked("abc123", "alice") is False

    def test_an_empty_thread_scans_to_zero(self, scanned):
        scanned([])
        assert scanner.scan("abc123") == 0
        assert contributors.baseline("abc123")[0] == 0


class TestScanFailure:
    @pytest.fixture
    def broken(self, monkeypatch):
        def explode():
            raise RuntimeError("reddit is down")

        monkeypatch.setattr(scanner.client, "bot", explode)

    def test_returns_none(self, broken):
        assert scanner.scan("abc123") is None

    def test_leaves_no_baseline(self, broken):
        scanner.scan("abc123")
        assert contributors.baseline("abc123") is None

    def test_does_not_wipe_an_existing_blocklist(self, broken):
        contributors.set_blocked("abc123", ["banned"])
        scanner.scan("abc123")
        assert contributors.is_blocked("abc123", "banned") is True


class TestTick:
    def test_scans_every_configured_thread(self, monkeypatch):
        seen = []
        monkeypatch.setattr(scanner, "scan", lambda tid: seen.append(tid) or 1)
        scanner._tick()
        assert sorted(seen) == ["abc123", "def456"]

    def test_a_second_tick_does_not_rescan(self, monkeypatch):
        seen = []
        monkeypatch.setattr(scanner, "scan", lambda tid: seen.append(tid) or 1)
        scanner._tick()
        scanner._tick()
        assert len(seen) == 2

    def test_a_failed_scan_is_retried_next_tick(self, monkeypatch):
        attempts = []
        monkeypatch.setattr(scanner, "scan", lambda tid: attempts.append(tid) or None)
        scanner._tick()
        scanner._tick()
        assert attempts.count("abc123") == 2
