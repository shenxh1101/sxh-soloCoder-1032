import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timedelta
from logalyzer.models import FilterOptions, LogEntry
from logalyzer.filters import (
    matches_filter,
    filter_entries,
    sort_entries,
    merge_entries,
)
from logalyzer.analyzer import analyze_stats, find_slow_apis, trace_request_flow


def create_test_entry(
    level="INFO",
    message="test message",
    hours_ago=0,
    request_id=None,
    api_path=None,
    duration_ms=None,
    has_stack=False,
):
    entry = LogEntry(raw=message, message=message, level=level)
    entry.timestamp = datetime.now() - timedelta(hours=hours_ago)
    entry.request_id = request_id
    entry.api_path = api_path
    entry.duration_ms = duration_ms
    if has_stack:
        entry.stack_trace = ["    at com.example.Test.test(Test.java:123)"]
    return entry


def test_matches_filter_level():
    entry = create_test_entry(level="ERROR")
    options = FilterOptions(levels=["ERROR", "FATAL"])
    assert matches_filter(entry, options) is True

    options2 = FilterOptions(levels=["INFO"])
    assert matches_filter(entry, options2) is False


def test_matches_filter_time_range():
    now = datetime.now()
    entry = create_test_entry(hours_ago=1)
    options = FilterOptions(start_time=now - timedelta(hours=2), end_time=now)
    assert matches_filter(entry, options) is True

    options2 = FilterOptions(start_time=now - timedelta(minutes=30))
    assert matches_filter(entry, options2) is False


def test_matches_filter_keywords():
    entry = create_test_entry(message="User login successful for admin")
    options = FilterOptions(keywords=["login", "admin"])
    assert matches_filter(entry, options) is True

    options2 = FilterOptions(keywords=["error"])
    assert matches_filter(entry, options2) is False


def test_matches_filter_exclude():
    entry = create_test_entry(message="User login successful for admin")
    options = FilterOptions(exclude_keywords=["debug"])
    assert matches_filter(entry, options) is True

    options2 = FilterOptions(exclude_keywords=["admin"])
    assert matches_filter(entry, options2) is False


def test_matches_filter_request_id():
    entry = create_test_entry(request_id="req-123")
    options = FilterOptions(request_id="req-123")
    assert matches_filter(entry, options) is True

    options2 = FilterOptions(request_id="req-456")
    assert matches_filter(entry, options2) is False


def test_matches_filter_api_path():
    entry = create_test_entry(api_path="/api/users")
    options = FilterOptions(api_path="/api/users")
    assert matches_filter(entry, options) is True


def test_matches_filter_has_stack():
    entry1 = create_test_entry(has_stack=True)
    entry2 = create_test_entry(has_stack=False)
    options = FilterOptions(has_stack_trace=True)
    assert matches_filter(entry1, options) is True
    assert matches_filter(entry2, options) is False

    options2 = FilterOptions(has_stack_trace=False)
    assert matches_filter(entry1, options2) is False
    assert matches_filter(entry2, options2) is True


def test_matches_filter_min_duration():
    entry1 = create_test_entry(duration_ms=500)
    entry2 = create_test_entry(duration_ms=1500)
    options = FilterOptions(min_duration_ms=1000)
    assert matches_filter(entry1, options) is False
    assert matches_filter(entry2, options) is True


def test_filter_entries():
    entries = [
        create_test_entry(level="INFO", message="normal entry"),
        create_test_entry(level="ERROR", message="error entry 1"),
        create_test_entry(level="WARN", message="warning entry"),
        create_test_entry(level="ERROR", message="error entry 2"),
    ]
    options = FilterOptions(levels=["ERROR"])
    filtered = list(filter_entries(iter(entries), options))
    assert len(filtered) == 2
    assert all(e.level == "ERROR" for e in filtered)


def test_sort_entries_by_timestamp():
    entries = [
        create_test_entry(hours_ago=3),
        create_test_entry(hours_ago=1),
        create_test_entry(hours_ago=2),
    ]
    sorted_entries = sort_entries(entries, by="timestamp")
    assert sorted_entries[0].timestamp < sorted_entries[1].timestamp < sorted_entries[2].timestamp


def test_sort_entries_by_level():
    entries = [
        create_test_entry(level="INFO"),
        create_test_entry(level="ERROR"),
        create_test_entry(level="DEBUG"),
    ]
    sorted_entries = sort_entries(entries, by="level")
    levels = [e.level for e in sorted_entries]
    assert levels == ["DEBUG", "INFO", "ERROR"]


def test_sort_entries_by_duration():
    entries = [
        create_test_entry(duration_ms=100),
        create_test_entry(duration_ms=500),
        create_test_entry(duration_ms=200),
    ]
    sorted_entries = sort_entries(entries, by="duration")
    durations = [e.duration_ms for e in sorted_entries]
    assert durations == [100, 200, 500]


def test_merge_entries():
    file1_entries = [
        create_test_entry(hours_ago=3),
        create_test_entry(hours_ago=1),
    ]
    file2_entries = [
        create_test_entry(hours_ago=4),
        create_test_entry(hours_ago=2),
    ]
    merged = merge_entries([file1_entries, file2_entries])
    assert len(merged) == 4
    timestamps = [e.timestamp for e in merged]
    assert all(timestamps[i] <= timestamps[i+1] for i in range(3))


def test_analyze_stats():
    entries = [
        create_test_entry(level="INFO", message="ok", api_path="/api/users", duration_ms=100),
        create_test_entry(level="INFO", message="ok", api_path="/api/users", duration_ms=200),
        create_test_entry(level="ERROR", message="failed", api_path="/api/orders", duration_ms=500),
        create_test_entry(level="WARNING", message="warn", api_path="/api/products", duration_ms=300),
    ]
    stats = analyze_stats(iter(entries))
    assert stats.total_entries == 4
    assert stats.level_counts["INFO"] == 2
    assert stats.level_counts["ERROR"] == 1
    assert "/api/users" in stats.api_stats
    assert stats.api_stats["/api/users"].count == 2
    assert stats.api_stats["/api/users"].avg_time == 150.0
    assert stats.api_stats["/api/orders"].error_count == 1


def test_find_slow_apis():
    entries = [
        create_test_entry(api_path="/api/fast", duration_ms=100),
        create_test_entry(api_path="/api/slow", duration_ms=2000),
        create_test_entry(api_path="/api/medium", duration_ms=800),
    ]
    slow = find_slow_apis(entries, threshold_ms=1000, limit=10)
    assert len(slow) == 1
    assert slow[0].api_path == "/api/slow"


def test_trace_request_flow():
    entries = [
        create_test_entry(request_id="req-123", message="start", hours_ago=3),
        create_test_entry(request_id="req-456", message="other"),
        create_test_entry(request_id="req-123", message="process", hours_ago=2),
        create_test_entry(request_id="req-123", message="end", hours_ago=1),
    ]
    traced = trace_request_flow(entries, "req-123")
    assert len(traced) == 3
    assert all(e.request_id == "req-123" for e in traced)
    assert traced[0].message == "start"
    assert traced[-1].message == "end"


if __name__ == "__main__":
    test_matches_filter_level()
    print("test_matches_filter_level passed")
    test_matches_filter_time_range()
    print("test_matches_filter_time_range passed")
    test_matches_filter_keywords()
    print("test_matches_filter_keywords passed")
    test_matches_filter_exclude()
    print("test_matches_filter_exclude passed")
    test_matches_filter_request_id()
    print("test_matches_filter_request_id passed")
    test_matches_filter_api_path()
    print("test_matches_filter_api_path passed")
    test_matches_filter_has_stack()
    print("test_matches_filter_has_stack passed")
    test_matches_filter_min_duration()
    print("test_matches_filter_min_duration passed")
    test_filter_entries()
    print("test_filter_entries passed")
    test_sort_entries_by_timestamp()
    print("test_sort_entries_by_timestamp passed")
    test_sort_entries_by_level()
    print("test_sort_entries_by_level passed")
    test_sort_entries_by_duration()
    print("test_sort_entries_by_duration passed")
    test_merge_entries()
    print("test_merge_entries passed")
    test_analyze_stats()
    print("test_analyze_stats passed")
    test_find_slow_apis()
    print("test_find_slow_apis passed")
    test_trace_request_flow()
    print("test_trace_request_flow passed")
    print("All filter tests passed!")
