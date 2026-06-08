import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timedelta, timezone

from logalyzer.models import LogEntry, FilterOptions, ApiStats
from logalyzer.parser import parse_timestamp, to_naive, compare_times
from logalyzer.analyzer import percentile, get_time_bucket_key, analyze_stats
from logalyzer.cli import parse_relative_time
from logalyzer.filters import matches_filter
from logalyzer.config import SavedQuery, build_command_from_query


def test_percentile():
    data = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
    assert abs(percentile(data, 50) - 5.5) < 0.001
    assert abs(percentile(data, 90) - 9.1) < 0.001
    assert abs(percentile(data, 95) - 9.55) < 0.001
    assert percentile([], 50) == 0.0
    assert percentile([42], 50) == 42


def test_get_time_bucket_key():
    ts = datetime(2024, 1, 15, 10, 23, 45)
    assert get_time_bucket_key(ts, 5) == "2024-01-15 10:20"
    assert get_time_bucket_key(ts, 15) == "2024-01-15 10:15"
    assert get_time_bucket_key(ts, 60) == "2024-01-15 10:00"

    ts2 = datetime(2024, 1, 15, 10, 58, 0)
    assert get_time_bucket_key(ts2, 5) == "2024-01-15 10:55"


def test_to_naive():
    dt_naive = datetime(2024, 1, 15, 10, 0, 0)
    dt_utc = datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
    dt_east = datetime(2024, 1, 15, 18, 0, 0, tzinfo=timezone(timedelta(hours=8)))

    assert to_naive(dt_naive) == dt_naive
    assert to_naive(None) is None

    naive_from_utc = to_naive(dt_utc)
    assert naive_from_utc.tzinfo is None

    naive_from_east = to_naive(dt_east)
    assert naive_from_east.tzinfo is None


def test_compare_times():
    dt1 = datetime(2024, 1, 15, 10, 0, 0)
    dt2 = datetime(2024, 1, 15, 11, 0, 0)

    assert compare_times(dt1, dt2) < 0
    assert compare_times(dt2, dt1) > 0
    assert compare_times(dt1, dt1) == 0

    dt_tz = datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
    dt_local = datetime(2024, 1, 15, 18, 0, 0)

    result = compare_times(dt_tz, dt_local)
    assert result is not None

    assert compare_times(None, dt1) < 0
    assert compare_times(dt1, None) > 0
    assert compare_times(None, None) == 0


def test_parse_relative_time_ago():
    now = datetime.now()

    result = parse_relative_time("1h ago")
    assert result is not None
    assert (now - result).total_seconds() >= 3600 - 1
    assert (now - result).total_seconds() <= 3600 + 1

    result = parse_relative_time("30m ago")
    assert result is not None
    assert (now - result).total_seconds() >= 1800 - 1
    assert (now - result).total_seconds() <= 1800 + 1

    result = parse_relative_time("2d ago")
    assert result is not None
    assert (now - result).days >= 1
    assert (now - result).days <= 3

    result = parse_relative_time("1hr ago")
    assert result is not None

    result = parse_relative_time("15min ago")
    assert result is not None

    result = parse_relative_time("10s ago")
    assert result is not None


def test_parse_relative_time_simple():
    now = datetime.now()

    result = parse_relative_time("1h")
    assert result is not None
    assert (now - result).total_seconds() >= 3600 - 1

    result = parse_relative_time("yesterday")
    assert result is not None
    assert result.hour == 0
    assert result.minute == 0

    result = parse_relative_time("now")
    assert result is not None

    result = parse_relative_time("today")
    assert result is not None
    assert result.hour == 0


def test_timezone_filter():
    dt_utc_early = datetime(2024, 1, 15, 2, 0, 0, tzinfo=timezone.utc)
    dt_utc_late = datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
    dt_naive = datetime(2024, 1, 15, 12, 0, 0)

    entry_tz_early = LogEntry(raw="test1", timestamp=dt_utc_early, level="INFO")
    entry_tz_late = LogEntry(raw="test2", timestamp=dt_utc_late, level="INFO")
    entry_naive = LogEntry(raw="test3", timestamp=dt_naive, level="INFO")

    filter_start = FilterOptions(start_time=datetime(2024, 1, 15, 0, 0, 0))
    filter_end = FilterOptions(end_time=datetime(2024, 1, 15, 23, 59, 59))

    assert matches_filter(entry_tz_early, filter_start) is True
    assert matches_filter(entry_tz_late, filter_start) is True
    assert matches_filter(entry_naive, filter_start) is True

    assert matches_filter(entry_tz_early, filter_end) is True
    assert matches_filter(entry_tz_late, filter_end) is True
    assert matches_filter(entry_naive, filter_end) is True

    filter_middle = FilterOptions(
        start_time=datetime(2024, 1, 15, 11, 0, 0),
        end_time=datetime(2024, 1, 15, 13, 0, 0)
    )
    assert matches_filter(entry_naive, filter_middle) is True


def test_analyze_stats_enhanced():
    entries = []
    for i in range(5):
        entry = LogEntry(raw=f"2024-01-15 10:0{i}:00 INFO test {i}", message=f"test {i}", level="INFO")
        entry.timestamp = datetime(2024, 1, 15, 10, i, 0)
        entry.api_path = "/api/users"
        entry.duration_ms = 100.0 + i * 10
        entries.append(entry)

    for i in range(3):
        entry = LogEntry(
            raw=f"2024-01-15 10:0{i+5}:00 ERROR NullPointerException: error {i}",
            message=f"error {i}",
            level="ERROR"
        )
        entry.timestamp = datetime(2024, 1, 15, 10, 5 + i, 0)
        entry.api_path = "/api/orders"
        entry.duration_ms = 200.0 + i * 50
        entry.stack_trace = ["    at Test.test(Test.java:123)"]
        entry.metadata["exception_type"] = "NullPointerException"
        entries.append(entry)

    stats = analyze_stats(iter(entries), time_bucket_minutes=5, top_n=5)

    assert stats.total_entries == 8
    assert "/api/users" in stats.api_stats
    assert "/api/orders" in stats.api_stats

    api_users = stats.api_stats["/api/users"]
    assert api_users.count == 5
    assert abs(api_users.avg_time - 120.0) < 0.001
    assert abs(api_users.p50 - 120.0) < 0.001
    assert api_users.p90 >= 130.0
    assert api_users.p95 >= 135.0

    assert len(stats.error_trend) > 0
    assert len(stats.slowest_apis) == 2
    assert len(stats.most_frequent_exceptions) > 0
    assert len(stats.exception_groups) > 0


def test_build_command_from_query():
    query = SavedQuery(
        name="errors",
        description="Show errors",
        command="filter",
        options={
            "path": "./logs",
            "levels": ["ERROR", "FATAL"],
            "keywords": ["timeout"],
            "exclude": ["heartbeat"],
            "request_id": None,
            "min_duration": None,
        },
    )

    cmd = build_command_from_query(query)
    assert "logalyzer filter" in cmd
    assert "./logs" in cmd
    assert "-l ERROR" in cmd
    assert "-l FATAL" in cmd
    assert "-k 'timeout'" in cmd
    assert "-x 'heartbeat'" in cmd


def test_saved_query_with_usage():
    query = SavedQuery(
        name="test_query",
        command="filter",
        options={"path": "./logs"},
        uses_count=5,
        last_used_at=datetime(2024, 1, 15, 10, 0, 0),
    )
    assert query.uses_count == 5
    assert query.last_used_at is not None
    assert query.name == "test_query"


if __name__ == "__main__":
    test_percentile()
    print("test_percentile passed")
    test_get_time_bucket_key()
    print("test_get_time_bucket_key passed")
    test_to_naive()
    print("test_to_naive passed")
    test_compare_times()
    print("test_compare_times passed")
    test_parse_relative_time_ago()
    print("test_parse_relative_time_ago passed")
    test_parse_relative_time_simple()
    print("test_parse_relative_time_simple passed")
    test_timezone_filter()
    print("test_timezone_filter passed")
    test_analyze_stats_enhanced()
    print("test_analyze_stats_enhanced passed")
    test_build_command_from_query()
    print("test_build_command_from_query passed")
    test_saved_query_with_usage()
    print("test_saved_query_with_usage passed")
    print("All enhancement tests passed!")
