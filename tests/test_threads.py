import json

import pytest

from joinlivecounting import config
from joinlivecounting.config.threads import RateLimit, UnknownThread, all_threads, get, resolve


class TestParsing:
    def test_loads_every_configured_thread(self):
        assert set(all_threads()) == {"abc123", "def456"}

    def test_inherits_defaults(self, thread):
        assert thread.permissions == ["update"]
        assert thread.max_contributors == 9900

    def test_overrides_beat_defaults(self, small_thread):
        assert small_thread.max_contributors == 5
        assert small_thread.return_url == "https://counting.gg/live"

    def test_empty_permissions_is_preserved_not_defaulted(self, small_thread):
        assert small_thread.permissions == []

    def test_return_url_defaults_to_the_thread_on_reddit(self, thread):
        assert thread.return_url == "https://www.reddit.com/live/abc123"

    def test_rate_limits_sort_shortest_window_first(self, small_thread):
        assert [limit.seconds for limit in small_thread.rate_limits] == [60, 3600]


class TestResolve:
    def test_by_id(self):
        assert resolve("abc123").name == "testthread"

    def test_by_alias(self):
        assert resolve("testthread").thread_id == "abc123"

    def test_alias_is_case_insensitive(self):
        assert resolve("TestThread").thread_id == "abc123"

    def test_unknown_returns_none(self):
        assert resolve("nope") is None

    def test_get_raises_for_unknown(self):
        with pytest.raises(UnknownThread):
            get("nope")

    def test_id_wins_over_another_threads_alias(self, threads_file, monkeypatch):
        from joinlivecounting.config import threads as tc

        threads_file.write_text(
            json.dumps(
                {
                    "defaults": {},
                    "threads": {"aaa": {"name": "bbb"}, "bbb": {"name": "other"}},
                }
            ),
            encoding="utf-8",
        )
        monkeypatch.setattr(tc, "_cache", {"mtime": None, "threads": {}})
        assert resolve("bbb").name == "other"


class TestRateLimitWording:
    @pytest.mark.parametrize(
        "seconds,expected",
        [
            (60, "10 per minute"),
            (3600, "10 per hour"),
            (86400, "10 per day"),
            (7200, "10 per 2 hours"),
            (300, "10 per 5 minutes"),
            (45, "10 per 45 seconds"),
        ],
    )
    def test_windows_read_naturally(self, seconds, expected):
        assert str(RateLimit(seconds, 10)) == expected


class TestHotReload:
    def test_edits_are_picked_up_without_a_restart(self, threads_file):
        assert resolve("newthread") is None
        data = json.loads(threads_file.read_text(encoding="utf-8"))
        data["threads"]["zzz999"] = {"name": "newthread"}
        threads_file.write_text(json.dumps(data), encoding="utf-8")
        assert resolve("newthread").thread_id == "zzz999"

    def test_limits_can_be_retuned_live(self, threads_file, thread):
        assert thread.rate_limits[0].max == 3
        data = json.loads(threads_file.read_text(encoding="utf-8"))
        data["defaults"]["rate_limits"] = [{"seconds": 60, "max": 500}]
        threads_file.write_text(json.dumps(data), encoding="utf-8")
        assert resolve("testthread").rate_limits[0].max == 500

    def test_broken_json_keeps_the_last_good_config(self, threads_file):
        assert resolve("testthread") is not None
        threads_file.write_text("{ not json", encoding="utf-8")
        assert resolve("testthread") is not None

    def test_a_deleted_file_keeps_the_last_good_config(self, threads_file):
        assert resolve("testthread") is not None
        threads_file.unlink()
        assert resolve("testthread") is not None

    def test_a_missing_file_with_no_cache_raises(self, tmp_path, monkeypatch):
        from joinlivecounting.config import threads as tc

        monkeypatch.setattr(config, "THREADS_FILE", str(tmp_path / "gone.json"))
        monkeypatch.setattr(tc, "_cache", {"mtime": None, "threads": {}})
        with pytest.raises(config.ConfigError):
            all_threads()


class TestNameSets:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("", set()),
            ("alice", {"alice"}),
            ("u/alice, /u/Bob", {"alice", "bob"}),
            ("Alice,,  bob  ", {"alice", "bob"}),
        ],
    )
    def test_parsing(self, raw, expected, monkeypatch):
        monkeypatch.setenv("SOME_LIST", raw)
        assert config._name_set("SOME_LIST") == expected
