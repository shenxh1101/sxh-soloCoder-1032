import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tempfile
from datetime import datetime, timedelta

from logalyzer.models import LogEntry, FilterOptions, SavedQuery
from logalyzer.cli import validate_time_bucket, validate_limit, validate_positive_int
from logalyzer.analyzer import extract_exception_type_from_entry, analyze_group_stats
from logalyzer.reporter import build_report, format_report_markdown, format_report_text
from logalyzer.config import build_command_from_query


def create_test_log_entry(level="INFO", message="test", timestamp=None,
                          api_path=None, request_id=None, duration_ms=None,
                          raw=None, stack_trace=None):
    if timestamp is None:
        timestamp = datetime.now()
    return LogEntry(
        timestamp=timestamp,
        level=level,
        message=message,
        raw=raw or f"{timestamp.isoformat()} {level} {message}",
        source_file="test.log",
        line_number=1,
        api_path=api_path,
        request_id=request_id,
        duration_ms=duration_ms,
        stack_trace=stack_trace,
    )


def test_validate_time_bucket():
    assert validate_time_bucket(5) == 5
    assert validate_time_bucket(0) == 5
    assert validate_time_bucket(-1) == 5
    assert validate_time_bucket(60) == 60


def test_validate_limit():
    assert validate_limit(10) == 10
    assert validate_limit(0) is None
    assert validate_limit(-5) is None
    assert validate_limit(None) is None


def test_validate_positive_int():
    assert validate_positive_int(10, "--test") == 10
    assert validate_positive_int(0, "--test") is None
    assert validate_positive_int(-5, "--test") is None
    assert validate_positive_int(None, "--test") is None


def test_extract_exception_type_from_main_exception():
    entry = create_test_log_entry(
        level="ERROR",
        message="Error processing request",
        raw="2024-01-15 10:00:00 ERROR java.lang.NullPointerException: Error processing request",
    )
    exc_type = extract_exception_type_from_entry(entry)
    assert exc_type == "java.lang.NullPointerException"


def test_extract_exception_type_from_caused_by():
    entry = create_test_log_entry(
        level="ERROR",
        message="Error processing request",
        raw="2024-01-15 10:00:00 ERROR Error processing request",
        stack_trace=[
            "Error processing request",
            "\tat com.example.Service.process(Service.java:123)",
            "Caused by: java.io.IOException: Connection refused",
            "\tat com.example.Client.connect(Client.java:456)",
        ],
    )
    exc_type = extract_exception_type_from_entry(entry)
    assert exc_type == "java.io.IOException"


def test_extract_exception_type_from_stack_line():
    entry = create_test_log_entry(
        level="ERROR",
        message="Error processing request",
        raw="2024-01-15 10:00:00 ERROR Error processing request",
        stack_trace=[
            "\tat com.example.Service.process(Service.java:123)",
            "\tat com.example.Controller.handle(Controller.java:789)",
        ],
    )
    exc_type = extract_exception_type_from_entry(entry)
    assert exc_type is None


def test_extract_exception_type_custom_error():
    entry = create_test_log_entry(
        level="ERROR",
        message="DB error",
        raw="2024-01-15 10:00:00 ERROR com.myapp.DatabaseError: Connection timeout",
    )
    exc_type = extract_exception_type_from_entry(entry)
    assert exc_type == "com.myapp.DatabaseError"


def test_analyze_group_stats_by_api_path():
    now = datetime.now()
    entries = []
    for i in range(20):
        ts = now + timedelta(minutes=i)
        api = "/api/users" if i % 2 == 0 else "/api/orders"
        level = "ERROR" if i % 5 == 0 else "INFO"
        entries.append(create_test_log_entry(
            level=level,
            message=f"Request {i}",
            timestamp=ts,
            api_path=api,
            request_id=f"req-{i}",
            duration_ms=100 + i * 10,
        ))

    group_stats = analyze_group_stats(entries, group_by="api_path", time_bucket_minutes=10)

    assert len(group_stats) == 2
    assert "/api/users" in group_stats
    assert "/api/orders" in group_stats

    users_stats = group_stats["/api/users"]
    assert users_stats.total_count == 10
    assert users_stats.error_count >= 1
    assert len(users_stats.time_buckets) >= 1

    for bucket in users_stats.time_buckets.values():
        assert bucket.count >= 0
        assert bucket.error_count >= 0
        assert bucket.error_count <= bucket.count


def test_analyze_group_stats_by_request_id():
    now = datetime.now()
    entries = []
    for i in range(15):
        ts = now + timedelta(minutes=i)
        req_id = f"req-{i % 3}"
        level = "ERROR" if i % 4 == 0 else "INFO"
        entries.append(create_test_log_entry(
            level=level,
            message=f"Request {i}",
            timestamp=ts,
            api_path="/api/test",
            request_id=req_id,
            duration_ms=50 + i * 5,
        ))

    group_stats = analyze_group_stats(entries, group_by="request_id", time_bucket_minutes=10)

    assert len(group_stats) == 3
    assert "req-0" in group_stats
    assert "req-1" in group_stats
    assert "req-2" in group_stats

    req0_stats = group_stats["req-0"]
    assert req0_stats.total_count == 5
    assert req0_stats.avg_time >= 0
    assert req0_stats.error_count >= 0


def test_build_report_empty():
    options = FilterOptions(
        levels=["ERROR"],
        keywords=["error"],
    )
    from logalyzer.analyzer import analyze_stats
    stats_result = analyze_stats(iter([]))

    report = build_report([], stats_result, options, title="Empty Test Report")

    assert report["is_empty"] is True
    assert report["title"] == "Empty Test Report"
    assert report["summary"]["total_entries"] == 0
    assert report["summary"]["error_count"] == 0
    assert report["filter"]["levels"] == ["ERROR"]
    assert report["filter"]["keywords"] == ["error"]


def test_build_report_with_data():
    now = datetime.now()
    entries = []
    for i in range(30):
        ts = now + timedelta(minutes=i)
        level = "ERROR" if i % 10 == 0 else "INFO"
        api = "/api/a" if i % 2 == 0 else "/api/b"
        entries.append(create_test_log_entry(
            level=level,
            message=f"Message {i}",
            timestamp=ts,
            api_path=api,
            request_id=f"req-{i}",
            duration_ms=100 + i * 5,
        ))

    entries[0].stack_trace = [
        "java.lang.NullPointerException: Null value",
        "\tat com.example.Method.call(Method.java:100)",
    ]

    from logalyzer.analyzer import analyze_stats
    stats_result = analyze_stats(iter(entries), time_bucket_minutes=10)

    options = FilterOptions(
        levels=["INFO", "ERROR"],
    )

    report = build_report(entries, stats_result, options, include_samples=3)

    assert report["is_empty"] is False
    assert report["summary"]["total_entries"] == 30
    assert report["summary"]["error_count"] >= 3
    assert report["summary"]["stack_trace_count"] == 1
    assert len(report["samples"]["entries"]) == 3
    assert len(report["samples"]["errors"]) >= 1
    assert len(report["samples"]["stack_traces"]) == 1


def test_format_report_markdown_empty():
    options = FilterOptions(levels=["ERROR"])
    from logalyzer.analyzer import analyze_stats
    stats_result = analyze_stats(iter([]))
    report_data = build_report([], stats_result, options)

    content = format_report_markdown(report_data)

    assert "No Matching Entries Found" in content
    assert "Filter Conditions Used" in content
    assert "Suggestions" in content
    assert "ERROR" in content


def test_format_report_text_with_data():
    now = datetime.now()
    entries = []
    for i in range(10):
        ts = now + timedelta(minutes=i)
        level = "ERROR" if i == 0 else "INFO"
        entries.append(create_test_log_entry(
            level=level,
            message=f"Message {i}",
            timestamp=ts,
            api_path="/api/test",
            duration_ms=100 + i * 10,
        ))

    from logalyzer.analyzer import analyze_stats
    stats_result = analyze_stats(iter(entries), time_bucket_minutes=5)

    options = FilterOptions()
    report_data = build_report(entries, stats_result, options)

    content = format_report_text(report_data)

    assert "SUMMARY" in content
    assert "LEVEL DISTRIBUTION" in content
    assert "10 total entries" in content.lower() or "Total entries" in content
    assert "=" * 80 in content


def test_build_command_from_query_complete():
    query = SavedQuery(
        name="full-errors",
        description="Full error query template",
        command="filter",
        options={
            "path": "/var/log/app",
            "recursive": True,
            "merge": False,
            "sort": "duration",
            "reverse": True,
            "since": "1h ago",
            "until": "now",
            "levels": ["ERROR", "FATAL"],
            "keywords": ["timeout", "exception"],
            "exclude": ["healthcheck"],
            "request_id": None,
            "api_path": "/api/",
            "has_stack": True,
            "min_duration": 1000,
            "format": "raw",
            "limit": 100,
            "context": 5,
            "show_stack": False,
        },
    )

    cmd = build_command_from_query(query)

    assert "logalyzer filter" in cmd
    assert "/var/log/app" in cmd
    assert "-r" in cmd
    assert "--no-merge" in cmd
    assert "--sort duration" in cmd
    assert "--reverse" in cmd
    assert "--since '1h ago'" in cmd
    assert "--until 'now'" in cmd
    assert "-l ERROR" in cmd
    assert "-l FATAL" in cmd
    assert "-k 'timeout'" in cmd
    assert "-k 'exception'" in cmd
    assert "-x 'healthcheck'" in cmd
    assert "--api-path /api/" in cmd
    assert "--has-stack" in cmd
    assert "--min-duration 1000" in cmd
    assert "-f raw" in cmd
    assert "-n 100" in cmd
    assert "-C 5" in cmd
    assert "--no-stack-trace" in cmd


def test_reporter_output_to_file():
    with tempfile.TemporaryDirectory() as tmpdir:
        now = datetime.now()
        entries = [
            create_test_log_entry(
                level="ERROR",
                message="Critical error",
                timestamp=now,
                api_path="/api/critical",
                duration_ms=5000,
                stack_trace=[
                    "com.myapp.ServiceError: Critical failure",
                    "\tat com.myapp.Service.process(Service.java:200)",
                ],
            ),
            create_test_log_entry(
                level="INFO",
                message="Normal operation",
                timestamp=now + timedelta(seconds=1),
                api_path="/api/normal",
                duration_ms=100,
            ),
        ]

        from logalyzer.reporter import generate_report

        output_md = os.path.join(tmpdir, "report.md")
        options = FilterOptions(levels=["ERROR", "INFO"])

        generate_report(
            entries=entries,
            filter_options=options,
            output_path=output_md,
            format_type="markdown",
            title="Test Report",
        )

        assert os.path.exists(output_md)
        with open(output_md, "r", encoding="utf-8") as f:
            content = f.read()

        assert "# Test Report" in content
        assert "Summary" in content
        assert "Slowest APIs" in content
        assert "Critical failure" in content

        output_txt = os.path.join(tmpdir, "report.txt")
        generate_report(
            entries=entries,
            filter_options=options,
            output_path=output_txt,
            format_type="text",
        )

        assert os.path.exists(output_txt)
        with open(output_txt, "r", encoding="utf-8") as f:
            content_txt = f.read()

        assert "SUMMARY" in content_txt
        assert "SLOWEST APIs" in content_txt


def test_empty_report_generation():
    with tempfile.TemporaryDirectory() as tmpdir:
        from logalyzer.reporter import generate_report

        output_md = os.path.join(tmpdir, "empty_report.md")
        options = FilterOptions(levels=["ERROR"], keywords=["nonexistent"])

        generate_report(
            entries=[],
            filter_options=options,
            output_path=output_md,
            format_type="markdown",
            title="Empty Search Report",
        )

        assert os.path.exists(output_md)
        with open(output_md, "r", encoding="utf-8") as f:
            content = f.read()

        assert "No Matching Entries Found" in content
        assert "Filter Conditions Used" in content
        assert "ERROR" in content
        assert "nonexistent" in content
        assert "Suggestions" in content


def test_absolute_time_template_save_show():
    start_dt = datetime(2024, 1, 15, 10, 0, 0)
    end_dt = datetime(2024, 1, 15, 11, 0, 0)

    query = SavedQuery(
        name="time-window-errors",
        description="Errors in specific time window",
        command="filter",
        options={
            "path": "/var/log/app.log",
            "start_time": start_dt.isoformat(),
            "end_time": end_dt.isoformat(),
            "levels": ["ERROR"],
            "limit": 50,
        },
    )

    cmd = build_command_from_query(query)

    assert "--start-time" in cmd
    assert "--end-time" in cmd
    assert start_dt.isoformat() in cmd
    assert end_dt.isoformat() in cmd
    assert "-l ERROR" in cmd
    assert "-n 50" in cmd
    assert "/var/log/app.log" in cmd


def test_watch_pending_stack_auto_flush():
    from logalyzer.watcher import LogFileTracker
    from datetime import datetime
    import time

    with tempfile.TemporaryDirectory() as tmpdir:
        log_file = os.path.join(tmpdir, "app.log")

        with open(log_file, "w", encoding="utf-8") as f:
            f.write("")

        tracker = LogFileTracker(log_file, start_from_end=True)

        error_line = "2024-01-15 10:00:00 ERROR Request failed"
        exc_line = "java.lang.NullPointerException: User not found"
        stack_line_1 = "    at com.example.Service.getUser(Service.java:123)"
        stack_line_2 = "    at com.example.Controller.handle(Controller.java:45)"

        with open(log_file, "a", encoding="utf-8") as f:
            f.write(error_line + "\n")
            f.write(exc_line + "\n")
            f.write(stack_line_1 + "\n")
            f.write(stack_line_2 + "\n")

        lines = tracker.read_new_lines()
        entries = tracker.process_new_lines(lines)

        assert len(entries) == 0

        assert tracker.has_pending_stack(max_wait_seconds=0.5) is True
        assert tracker.current_entry is not None
        assert tracker.current_entry.level == "ERROR"

        time.sleep(0.6)

        assert tracker.has_pending_stack(max_wait_seconds=0.5) is False

        entry = tracker.flush()
        assert entry is not None
        assert entry.level == "ERROR"
        assert len(entry.stack_trace) == 3
        assert "java.lang.NullPointerException: User not found" in entry.stack_trace
        assert "at com.example.Service.getUser" in entry.stack_trace[1]


def test_report_includes_filter_conditions():
    now = datetime.now()
    entries = [
        create_test_log_entry(
            level="ERROR",
            message="Test error",
            timestamp=now,
            api_path="/api/test",
            duration_ms=100,
        ),
    ]

    from logalyzer.analyzer import analyze_stats

    stats_result = analyze_stats(iter(entries))
    options = FilterOptions(
        levels=["ERROR"],
        keywords=["test"],
        exclude_keywords=["healthcheck"],
        api_path="/api/",
        min_duration_ms=50,
        has_stack_trace=False,
    )

    report_data = build_report(
        entries, stats_result, options,
        path="/var/log/app.log",
    )

    text_content = format_report_text(report_data, use_emoji=False)
    md_content = format_report_markdown(report_data, use_emoji=False)

    for content in [text_content, md_content]:
        assert "/var/log/app.log" in content
        assert "ERROR" in content
        assert "test" in content
        assert "healthcheck" in content
        assert "/api/" in content
        assert "50" in content

    assert "FILTER CONDITIONS" in text_content
    assert "Filter Conditions" in md_content


def test_report_java_stack_shows_exception_header():
    from logalyzer.parser import parse_log_line
    from logalyzer.analyzer import analyze_stats

    error_line = "2024-01-15 10:00:00 ERROR Processing request failed"
    exc_line = "java.lang.IllegalArgumentException: Invalid user ID"
    stack_line_1 = "    at com.example.UserService.validate(UserService.java:123)"
    stack_line_2 = "    at com.example.UserController.create(UserController.java:45)"
    stack_line_3 = "Caused by: java.lang.NumberFormatException: For input string: 'abc'"
    stack_line_4 = "    at java.lang.Integer.parseInt(Integer.java:580)"

    entry = parse_log_line(error_line)
    entry.source_file = "test.log"
    entry.line_number = 1

    exc_entry = parse_log_line(exc_line)
    stack_entry_1 = parse_log_line(stack_line_1)
    stack_entry_2 = parse_log_line(stack_line_2)
    stack_entry_3 = parse_log_line(stack_line_3)
    stack_entry_4 = parse_log_line(stack_line_4)

    entry.stack_trace = [
        exc_line, stack_line_1, stack_line_2, stack_line_3, stack_line_4
    ]

    entries = [entry]
    stats_result = analyze_stats(iter(entries))
    options = FilterOptions(levels=["ERROR"])

    report_data = build_report(entries, stats_result, options, path="test.log")

    md_content = format_report_markdown(report_data, use_emoji=False)
    text_content = format_report_text(report_data, use_emoji=False)

    for content in [md_content, text_content]:
        assert "java.lang.IllegalArgumentException" in content
        assert "Invalid user ID" in content
        assert "at com.example.UserService.validate" in content
        assert "at com.example.UserController.create" in content
        assert "Caused by:" in content
        assert "java.lang.NumberFormatException" in content


if __name__ == "__main__":
    test_validate_time_bucket()
    test_validate_limit()
    test_validate_positive_int()
    test_extract_exception_type_from_main_exception()
    test_extract_exception_type_from_caused_by()
    test_extract_exception_type_from_stack_line()
    test_extract_exception_type_custom_error()
    test_analyze_group_stats_by_api_path()
    test_analyze_group_stats_by_request_id()
    test_build_report_empty()
    test_build_report_with_data()
    test_format_report_markdown_empty()
    test_format_report_text_with_data()
    test_build_command_from_query_complete()
    test_reporter_output_to_file()
    test_empty_report_generation()
    test_absolute_time_template_save_show()
    test_watch_pending_stack_auto_flush()
    test_report_includes_filter_conditions()
    test_report_java_stack_shows_exception_header()
    print("All round 3 tests passed!")
