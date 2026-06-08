from typing import List, Dict, Iterator, Optional
from collections import defaultdict
from datetime import datetime
from dataclasses import dataclass, field
import statistics

from .models import LogEntry, StatsResult, ApiStats
from .constants import EXCEPTION_PATTERN


@dataclass
class GroupTimeBucket:
    bucket: str
    count: int = 0
    error_count: int = 0
    p95: float = 0
    durations: List[float] = field(default_factory=list)


@dataclass
class GroupStats:
    key: str
    total_count: int = 0
    error_count: int = 0
    avg_time: float = 0
    p95: float = 0
    time_buckets: Dict[str, GroupTimeBucket] = field(default_factory=dict)
    durations: List[float] = field(default_factory=list)


def percentile(data: List[float], p: float) -> float:
    if not data:
        return 0.0
    sorted_data = sorted(data)
    k = (len(sorted_data) - 1) * (p / 100.0)
    f = int(k)
    c = min(f + 1, len(sorted_data) - 1)
    if f == c:
        return sorted_data[f]
    return sorted_data[f] + (sorted_data[c] - sorted_data[f]) * (k - f)


def get_time_bucket_key(ts: datetime, bucket_minutes: int = 5) -> str:
    bucket = (ts.minute // bucket_minutes) * bucket_minutes
    return ts.strftime(f"%Y-%m-%d %H:{bucket:02d}")


def extract_exception_type_from_entry(entry: LogEntry) -> Optional[str]:
    exc_match = EXCEPTION_PATTERN.search(entry.raw)
    if exc_match:
        return exc_match.group(1)

    if entry.stack_trace:
        for line in entry.stack_trace:
            if line.startswith("Caused by:"):
                exc_match = EXCEPTION_PATTERN.search(line)
                if exc_match:
                    return exc_match.group(1)

            exc_match = EXCEPTION_PATTERN.search(line)
            if exc_match:
                return exc_match.group(1)

    return None


def analyze_stats(
    entries: Iterator[LogEntry],
    time_bucket_minutes: int = 5,
    top_n: int = 10,
) -> StatsResult:
    result = StatsResult()
    error_messages: Dict[str, int] = defaultdict(int)
    exception_groups: Dict[tuple, int] = defaultdict(int)

    for entry in entries:
        result.total_entries += 1

        if entry.level:
            result.level_counts[entry.level] = result.level_counts.get(entry.level, 0) + 1

        if entry.timestamp:
            hour_key = entry.timestamp.strftime("%Y-%m-%d %H:00")
            result.time_distribution[hour_key] = result.time_distribution.get(hour_key, 0) + 1

            if entry.level and entry.level in ("ERROR", "FATAL", "CRITICAL"):
                bucket_key = get_time_bucket_key(entry.timestamp, time_bucket_minutes)
                result.error_trend[bucket_key] = result.error_trend.get(bucket_key, 0) + 1

        if entry.api_path and entry.duration_ms is not None:
            path = entry.api_path.split("?")[0]
            if path not in result.api_stats:
                result.api_stats[path] = ApiStats(path=path)
            stats = result.api_stats[path]
            stats.count += 1
            stats.total_time += entry.duration_ms
            stats.max_time = max(stats.max_time, entry.duration_ms)
            stats.min_time = min(stats.min_time, entry.duration_ms)
            stats.durations.append(entry.duration_ms)
            if entry.level and entry.level in ("ERROR", "FATAL", "CRITICAL"):
                stats.error_count += 1

        has_exception = False
        exc_type = extract_exception_type_from_entry(entry)

        if exc_type:
            result.exception_counts[exc_type] = result.exception_counts.get(exc_type, 0) + 1
            has_exception = True

        if entry.stack_trace and len(entry.stack_trace) > 0:
            if entry.message:
                key = entry.message[:100]
                error_messages[key] += 1

        elif entry.level and entry.level in ("ERROR", "FATAL", "CRITICAL"):
            if entry.message:
                key = entry.message[:100]
                error_messages[key] += 1

        if has_exception and exc_type and entry.message:
            group_key = (exc_type, entry.message[:80])
            exception_groups[group_key] += 1

    for stats in result.api_stats.values():
        if stats.count > 0:
            stats.avg_time = stats.total_time / stats.count
            if stats.durations:
                stats.p50 = percentile(stats.durations, 50)
                stats.p90 = percentile(stats.durations, 90)
                stats.p95 = percentile(stats.durations, 95)
        if stats.min_time == float("inf"):
            stats.min_time = 0

    for (exc_type, msg), count in exception_groups.items():
        msg_clean = msg.strip()
        exc_type_pattern = exc_type.replace(".", r"\.") + r":\s*"
        import re
        if re.match(f"^{exc_type_pattern}", msg_clean):
            msg_clean = re.sub(f"^{exc_type_pattern}", "", msg_clean)
        elif msg_clean.startswith(exc_type):
            msg_clean = msg_clean[len(exc_type):].lstrip(": ")
        group_key = f"{exc_type}: {msg_clean}" if msg_clean else exc_type
        result.exception_groups[group_key] = count

    sorted_errors = sorted(error_messages.items(), key=lambda x: x[1], reverse=True)
    result.top_errors = sorted_errors[:top_n]

    sorted_apis = sorted(
        result.api_stats.values(),
        key=lambda x: x.avg_time,
        reverse=True
    )
    result.slowest_apis = [(api.path, api.avg_time, api.p95, api.count) for api in sorted_apis[:top_n]]

    sorted_exceptions = sorted(
        result.exception_groups.items(),
        key=lambda x: x[1],
        reverse=True
    )
    result.most_frequent_exceptions = sorted_exceptions[:top_n]

    return result


def analyze_group_stats(
    entries: List[LogEntry],
    group_by: str = "api_path",
    time_bucket_minutes: int = 5,
) -> Dict[str, GroupStats]:
    groups: Dict[str, GroupStats] = {}

    for entry in entries:
        if group_by == "api_path":
            key = entry.api_path
        elif group_by == "request_id":
            key = entry.request_id
        else:
            continue

        if not key:
            continue

        if key not in groups:
            groups[key] = GroupStats(key=key)

        group = groups[key]
        group.total_count += 1

        if entry.level and entry.level in ("ERROR", "FATAL", "CRITICAL"):
            group.error_count += 1

        if entry.duration_ms is not None:
            group.durations.append(entry.duration_ms)

        if entry.timestamp:
            bucket_key = get_time_bucket_key(entry.timestamp, time_bucket_minutes)
            if bucket_key not in group.time_buckets:
                group.time_buckets[bucket_key] = GroupTimeBucket(bucket=bucket_key)
            bucket = group.time_buckets[bucket_key]
            bucket.count += 1
            if entry.level and entry.level in ("ERROR", "FATAL", "CRITICAL"):
                bucket.error_count += 1
            if entry.duration_ms is not None:
                bucket.durations.append(entry.duration_ms)

    for group in groups.values():
        if group.durations:
            group.avg_time = sum(group.durations) / len(group.durations)
            group.p95 = percentile(group.durations, 95)
        for bucket in group.time_buckets.values():
            if bucket.durations:
                bucket.p95 = percentile(bucket.durations, 95)

    return groups


def find_slow_apis(
    entries: List[LogEntry],
    threshold_ms: float = 1000,
    limit: int = 20,
) -> List[LogEntry]:
    slow = [
        e for e in entries
        if e.duration_ms is not None and e.duration_ms >= threshold_ms
    ]
    slow.sort(key=lambda e: e.duration_ms or 0, reverse=True)
    return slow[:limit]


def find_error_entries(entries: List[LogEntry]) -> List[LogEntry]:
    return [
        e for e in entries
        if e.level and e.level in ("ERROR", "FATAL", "CRITICAL")
    ]


def find_entries_with_stack_trace(entries: List[LogEntry]) -> List[LogEntry]:
    return [
        e for e in entries
        if e.stack_trace and len(e.stack_trace) > 0
    ]


def trace_request_flow(
    entries: List[LogEntry],
    request_id: str,
) -> List[LogEntry]:
    from .filters import find_entries_by_request_id, sort_entries

    related = find_entries_by_request_id(entries, request_id)
    return sort_entries(related, by="timestamp")
