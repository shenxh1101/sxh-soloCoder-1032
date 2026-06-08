import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime
from logalyzer.parser import (
    parse_log_line,
    parse_timestamp,
    parse_level,
    extract_request_id,
    extract_api_path,
    extract_duration,
    extract_exception_type,
    is_stack_trace_line,
    find_log_files,
    parse_log_file,
)


def test_parse_timestamp():
    ts = parse_timestamp("2024-01-15 10:00:01.123")
    assert ts is not None
    assert ts.year == 2024
    assert ts.month == 1
    assert ts.day == 15
    assert ts.hour == 10
    assert ts.minute == 0
    assert ts.second == 1

    ts2 = parse_timestamp("2024/01/15 10:00:01")
    assert ts2 is not None

    ts3 = parse_timestamp("[15/Jan/2024:10:00:01+0800]")
    assert ts3 is not None


def test_parse_level():
    assert parse_level("2024-01-15 10:00:01 INFO test") == "INFO"
    assert parse_level("2024-01-15 10:00:01 warn test") == "WARNING"
    assert parse_level("2024-01-15 10:00:01 ERROR test") == "ERROR"
    assert parse_level("no level here") is None


def test_extract_request_id():
    assert extract_request_id("request_id=abc-123-xyz test") == "abc-123-xyz"
    assert extract_request_id("X-Request-ID: 550e8400-e29b-41d4-a716-446655440000 test") == "550e8400-e29b-41d4-a716-446655440000"
    assert extract_request_id("trace_id=test-123") == "test-123"
    assert extract_request_id("no id here") is None


def test_extract_api_path():
    assert extract_api_path('"GET /api/users/12345 HTTP/1.1" 200 456') == '/api/users/12345'
    assert extract_api_path('GET /api/orders test') == '/api/orders'
    assert extract_api_path('path=/api/products') == '/api/products'
    assert extract_api_path('no path here') is None


def test_extract_duration():
    assert extract_duration('duration=123ms') == 123.0
    assert extract_duration('took 456') == 456.0
    assert extract_duration('耗时=789') == 789.0
    assert extract_duration('no duration here') is None


def test_extract_exception_type():
    assert extract_exception_type('java.lang.NullPointerException: test') == 'java.lang.NullPointerException'
    assert extract_exception_type('MyCustomError: something went wrong') == 'MyCustomError'
    assert extract_exception_type('no exception here') is None


def test_is_stack_trace_line():
    assert is_stack_trace_line('    at com.example.service.OrderService.processOrder(OrderService.java:123)') is True
    assert is_stack_trace_line('Caused by: java.lang.NullPointerException') is True
    assert is_stack_trace_line('2024-01-15 10:00:00 INFO test') is False


def test_parse_log_line_standard_format():
    line = '2024-01-15 10:00:01.123 INFO com.example.service.UserService: Starting user authentication'
    entry = parse_log_line(line)
    assert entry is not None
    assert entry.level == 'INFO'
    assert entry.logger == 'com.example.service.UserService'
    assert entry.timestamp is not None
    assert 'Starting user authentication' in entry.message


def test_parse_log_line_with_thread():
    line = '2024-01-15 10:00:01.123 [main] INFO com.example.Test - Test message'
    entry = parse_log_line(line)
    assert entry is not None
    assert entry.level == 'INFO'
    assert entry.thread == 'main'


def test_parse_log_line_bracket_format():
    line = '[2024-01-15 10:00:01.123] [INFO] Test message'
    entry = parse_log_line(line)
    assert entry is not None
    assert entry.level == 'INFO'


def test_parse_log_line_with_request_id():
    line = '2024-01-15 10:00:01.123 INFO service: request_id=abc-123 test'
    entry = parse_log_line(line)
    assert entry.request_id == 'abc-123'


def test_find_log_files():
    test_dir = os.path.join(os.path.dirname(__file__), 'test_data')
    files = find_log_files(test_dir, recursive=False)
    assert len(files) >= 2
    assert any('app.log' in f for f in files)
    assert any('access.log' in f for f in files)


def test_parse_log_file():
    test_file = os.path.join(os.path.dirname(__file__), 'test_data', 'app.log')
    entries = list(parse_log_file(test_file))
    assert len(entries) > 0

    error_entries = [e for e in entries if e.level == 'ERROR']
    assert len(error_entries) >= 2

    entries_with_stack = [e for e in entries if e.stack_trace]
    assert len(entries_with_stack) >= 2

    entries_with_duration = [e for e in entries if e.duration_ms is not None]
    assert len(entries_with_duration) >= 4


if __name__ == '__main__':
    test_parse_timestamp()
    print('test_parse_timestamp passed')
    test_parse_level()
    print('test_parse_level passed')
    test_extract_request_id()
    print('test_extract_request_id passed')
    test_extract_api_path()
    print('test_extract_api_path passed')
    test_extract_duration()
    print('test_extract_duration passed')
    test_extract_exception_type()
    print('test_extract_exception_type passed')
    test_is_stack_trace_line()
    print('test_is_stack_trace_line passed')
    test_parse_log_line_standard_format()
    print('test_parse_log_line_standard_format passed')
    test_parse_log_line_with_thread()
    print('test_parse_log_line_with_thread passed')
    test_parse_log_line_bracket_format()
    print('test_parse_log_line_bracket_format passed')
    test_parse_log_line_with_request_id()
    print('test_parse_log_line_with_request_id passed')
    test_find_log_files()
    print('test_find_log_files passed')
    test_parse_log_file()
    print('test_parse_log_file passed')
    print('All tests passed!')
