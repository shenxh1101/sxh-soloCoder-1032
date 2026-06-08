import os
from datetime import datetime
from typing import Iterator, List, Optional, Tuple
from dateutil import parser as date_parser

from .models import LogEntry, LogFile
from .constants import (
    TIMESTAMP_PATTERNS,
    LEVEL_PATTERN,
    REQUEST_ID_PATTERNS,
    API_PATH_PATTERNS,
    DURATION_PATTERNS,
    EXCEPTION_PATTERN,
    STACK_TRACE_LINE_PATTERN,
    LOG_LINE_PATTERNS,
    DEFAULT_ENCODINGS,
    LOG_LEVEL_PRIORITY,
)


def detect_encoding(file_path: str) -> str:
    for encoding in DEFAULT_ENCODINGS:
        try:
            with open(file_path, "r", encoding=encoding) as f:
                f.read(1024 * 1024)
                return encoding
        except (UnicodeDecodeError, UnicodeError):
            continue
    return "utf-8"


def parse_timestamp(text: str) -> Optional[datetime]:
    for pattern in TIMESTAMP_PATTERNS:
        match = pattern.search(text)
        if match:
            ts_str = match.group(0)
            try:
                return date_parser.parse(ts_str, fuzzy=True)
            except (ValueError, TypeError):
                continue
    return None


def parse_level(text: str) -> Optional[str]:
    match = LEVEL_PATTERN.search(text)
    if match:
        level = match.group(1).upper()
        if level == "WARN":
            level = "WARNING"
        return level
    return None


def extract_request_id(text: str) -> Optional[str]:
    for pattern in REQUEST_ID_PATTERNS:
        match = pattern.search(text)
        if match:
            return match.group(1)
    return None


def extract_api_path(text: str) -> Optional[str]:
    for pattern in API_PATH_PATTERNS:
        match = pattern.search(text)
        if match:
            return match.group(1)
    return None


def extract_duration(text: str) -> Optional[float]:
    for pattern in DURATION_PATTERNS:
        match = pattern.search(text)
        if match:
            try:
                return float(match.group(1))
            except (ValueError, TypeError):
                continue
    return None


def extract_exception_type(text: str) -> Optional[str]:
    match = EXCEPTION_PATTERN.search(text)
    if match:
        return match.group(1)
    return None


def is_stack_trace_line(line: str) -> bool:
    return bool(STACK_TRACE_LINE_PATTERN.match(line))


def parse_log_line(line: str) -> Optional[LogEntry]:
    line = line.rstrip("\n").rstrip("\r")
    if not line.strip():
        return None

    entry = LogEntry(raw=line)

    for pattern in LOG_LINE_PATTERNS:
        match = pattern.match(line)
        if match:
            groups = match.groupdict()
            if "timestamp" in groups and groups["timestamp"]:
                entry.timestamp = parse_timestamp(groups["timestamp"])
            if "level" in groups and groups["level"]:
                level = groups["level"].upper()
                entry.level = "WARNING" if level == "WARN" else level
            if "logger" in groups and groups["logger"]:
                entry.logger = groups["logger"]
            if "thread" in groups and groups["thread"]:
                entry.thread = groups["thread"]
            if "message" in groups and groups["message"]:
                entry.message = groups["message"]
            break

    if entry.timestamp is None:
        entry.timestamp = parse_timestamp(line)
    if entry.level is None:
        entry.level = parse_level(line)
    if entry.message is None:
        entry.message = line

    entry.request_id = extract_request_id(line)
    entry.api_path = extract_api_path(line)
    entry.duration_ms = extract_duration(line)

    exc_type = extract_exception_type(line)
    if exc_type:
        entry.metadata["exception_type"] = exc_type

    return entry


def parse_log_file(
    file_path: str,
    encoding: Optional[str] = None,
) -> Iterator[LogEntry]:
    if encoding is None:
        encoding = detect_encoding(file_path)

    current_entry: Optional[LogEntry] = None
    line_number = 0

    try:
        with open(file_path, "r", encoding=encoding, errors="replace") as f:
            for line in f:
                line_number += 1

                if is_stack_trace_line(line):
                    if current_entry is not None:
                        if current_entry.stack_trace is None:
                            current_entry.stack_trace = []
                        current_entry.stack_trace.append(line.rstrip("\n").rstrip("\r"))
                    continue

                if current_entry is not None:
                    current_entry.line_number = line_number - 1
                    current_entry.source_file = file_path
                    yield current_entry

                current_entry = parse_log_line(line)
                if current_entry is not None:
                    current_entry.source_file = file_path
                    current_entry.line_number = line_number

            if current_entry is not None:
                current_entry.line_number = line_number
                current_entry.source_file = file_path
                yield current_entry

    except Exception as e:
        raise RuntimeError(f"Failed to parse log file {file_path}: {e}")


def count_file_lines(file_path: str, encoding: str) -> int:
    count = 0
    try:
        with open(file_path, "r", encoding=encoding, errors="replace") as f:
            for _ in f:
                count += 1
    except Exception:
        pass
    return count


def to_naive(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt.astimezone().replace(tzinfo=None)
    return dt


def compare_times(dt1: Optional[datetime], dt2: Optional[datetime]) -> int:
    dt1_naive = to_naive(dt1)
    dt2_naive = to_naive(dt2)
    if dt1_naive is None and dt2_naive is None:
        return 0
    if dt1_naive is None:
        return -1
    if dt2_naive is None:
        return 1
    if dt1_naive < dt2_naive:
        return -1
    if dt1_naive > dt2_naive:
        return 1
    return 0


def scan_log_file(file_path: str) -> LogFile:
    stat = os.stat(file_path)
    encoding = detect_encoding(file_path)
    log_file = LogFile(
        path=file_path,
        size=stat.st_size,
        modified=datetime.fromtimestamp(stat.st_mtime),
        encoding=encoding,
    )

    log_file.raw_line_count = count_file_lines(file_path, encoding)

    min_time: Optional[datetime] = None
    max_time: Optional[datetime] = None
    level_counts = {}

    for entry in parse_log_file(file_path, encoding):
        log_file.line_count += 1
        if entry.level:
            level_counts[entry.level] = level_counts.get(entry.level, 0) + 1
        if entry.timestamp:
            if min_time is None or compare_times(entry.timestamp, min_time) < 0:
                min_time = entry.timestamp
            if max_time is None or compare_times(entry.timestamp, max_time) > 0:
                max_time = entry.timestamp

    log_file.level_counts = level_counts
    if min_time and max_time:
        log_file.time_range = (min_time, max_time)

    return log_file


def find_log_files(path: str, recursive: bool = True, extensions: Optional[List[str]] = None) -> List[str]:
    if extensions is None:
        extensions = [".log", ".txt", ".out", ".err"]

    result = []

    if os.path.isfile(path):
        if any(path.endswith(ext) for ext in extensions):
            result.append(os.path.abspath(path))
        return result

    if os.path.isdir(path):
        if recursive:
            for root, dirs, files in os.walk(path):
                for file in files:
                    if any(file.endswith(ext) for ext in extensions):
                        result.append(os.path.abspath(os.path.join(root, file)))
        else:
            for file in os.listdir(path):
                full_path = os.path.join(path, file)
                if os.path.isfile(full_path) and any(file.endswith(ext) for ext in extensions):
                    result.append(os.path.abspath(full_path))

    return sorted(result)


def level_priority(level: Optional[str]) -> int:
    if level is None:
        return -1
    return LOG_LEVEL_PRIORITY.get(level, -1)
