from typing import Iterator, List, Optional
from datetime import datetime

from .models import LogEntry, FilterOptions


def matches_filter(entry: LogEntry, options: FilterOptions) -> bool:
    if options.start_time and entry.timestamp:
        if entry.timestamp < options.start_time:
            return False

    if options.end_time and entry.timestamp:
        if entry.timestamp > options.end_time:
            return False

    if options.levels:
        if not entry.level or entry.level.upper() not in [l.upper() for l in options.levels]:
            return False

    if options.keywords:
        text = entry.raw.lower()
        if not all(kw.lower() in text for kw in options.keywords):
            return False

    if options.exclude_keywords:
        text = entry.raw.lower()
        if any(kw.lower() in text for kw in options.exclude_keywords):
            return False

    if options.request_id:
        if not entry.request_id or options.request_id.lower() not in entry.request_id.lower():
            return False

    if options.api_path:
        if not entry.api_path or options.api_path.lower() not in entry.api_path.lower():
            return False

    if options.has_stack_trace is not None:
        has_stack = entry.stack_trace is not None and len(entry.stack_trace) > 0
        if has_stack != options.has_stack_trace:
            return False

    if options.min_duration_ms is not None:
        if entry.duration_ms is None or entry.duration_ms < options.min_duration_ms:
            return False

    return True


def filter_entries(
    entries: Iterator[LogEntry],
    options: FilterOptions,
) -> Iterator[LogEntry]:
    for entry in entries:
        if matches_filter(entry, options):
            yield entry


def get_context_entries(
    all_entries: List[LogEntry],
    target_entry: LogEntry,
    before: int = 5,
    after: int = 5,
) -> List[LogEntry]:
    try:
        idx = all_entries.index(target_entry)
    except ValueError:
        return []

    start_idx = max(0, idx - before)
    end_idx = min(len(all_entries), idx + after + 1)

    return all_entries[start_idx:end_idx]


def find_entries_by_request_id(
    entries: List[LogEntry],
    request_id: str,
) -> List[LogEntry]:
    return [
        entry for entry in entries
        if entry.request_id and request_id.lower() in entry.request_id.lower()
    ]


def sort_entries(
    entries: List[LogEntry],
    by: str = "timestamp",
    reverse: bool = False,
) -> List[LogEntry]:
    def sort_key(entry: LogEntry):
        if by == "timestamp":
            return (entry.timestamp or datetime.min, entry.line_number)
        elif by == "level":
            from .parser import level_priority
            return (level_priority(entry.level), entry.timestamp or datetime.min)
        elif by == "file":
            return (entry.source_file, entry.line_number)
        elif by == "duration":
            return (entry.duration_ms or 0, entry.timestamp or datetime.min)
        else:
            return (entry.line_number, entry.source_file)

    return sorted(entries, key=sort_key, reverse=reverse)


def merge_entries(
    file_entries: List[List[LogEntry]],
    sort_by: str = "timestamp",
) -> List[LogEntry]:
    merged = []
    for entries in file_entries:
        merged.extend(entries)
    return sort_entries(merged, by=sort_by)
