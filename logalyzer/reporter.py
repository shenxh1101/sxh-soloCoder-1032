from typing import List, Optional, Dict, Any
from datetime import datetime
import os

from .models import LogEntry, StatsResult, FilterOptions
from .analyzer import analyze_stats


def format_size(size_bytes: int) -> str:
    units = ["B", "KB", "MB", "GB"]
    size = float(size_bytes)
    for unit in units:
        if size < 1024.0:
            if unit == "B":
                return f"{int(size)} {unit}"
            return f"{size:.2f} {unit}"
        size /= 1024.0
    return f"{size:.2f} TB"


def format_timestamp(ts: Optional[datetime]) -> str:
    if ts is None:
        return "-"
    return ts.strftime("%Y-%m-%d %H:%M:%S")


def build_report(
    entries: List[LogEntry],
    stats_result: StatsResult,
    filter_options: FilterOptions,
    title: str = "Log Analysis Report",
    include_samples: int = 5,
    path: str = "",
) -> Dict[str, Any]:
    timestamps = [e.timestamp for e in entries if e.timestamp]
    min_time = min(timestamps) if timestamps else None
    max_time = max(timestamps) if timestamps else None

    error_entries = [
        e for e in entries
        if e.level and e.level in ("ERROR", "FATAL", "CRITICAL")
    ]

    entries_with_stack = [
        e for e in entries
        if e.stack_trace and len(e.stack_trace) > 0
    ]

    sample_entries = entries[:include_samples] if entries else []
    sample_errors = error_entries[:include_samples] if error_entries else []
    sample_stacks = entries_with_stack[:include_samples] if entries_with_stack else []

    return {
        "title": title,
        "generated_at": datetime.now(),
        "path": path,
        "summary": {
            "total_entries": len(entries),
            "error_count": len(error_entries),
            "warning_count": len([e for e in entries if e.level and e.level in ("WARN", "WARNING")]),
            "stack_trace_count": len(entries_with_stack),
            "time_range": {
                "start": min_time,
                "end": max_time,
            },
            "unique_apis": len(stats_result.api_stats),
            "unique_exceptions": len(stats_result.exception_counts),
        },
        "filter": {
            "start_time": filter_options.start_time,
            "end_time": filter_options.end_time,
            "levels": filter_options.levels,
            "keywords": filter_options.keywords,
            "exclude_keywords": filter_options.exclude_keywords,
            "request_id": filter_options.request_id,
            "api_path": filter_options.api_path,
            "has_stack_trace": filter_options.has_stack_trace,
            "min_duration_ms": filter_options.min_duration_ms,
        },
        "stats": stats_result,
        "samples": {
            "entries": sample_entries,
            "errors": sample_errors,
            "stack_traces": sample_stacks,
        },
        "is_empty": len(entries) == 0,
    }


def _strip_emoji(text: str) -> str:
    emoji_chars = {
        "📊": "===",
        "📈": "->",
        "📉": "->",
        "🐌": "->",
        "🔥": "->",
        "🔍": "->",
        "💥": "!!",
        "📝": "->",
        "⚠️": "[!]",
        "🥇": "1.",
        "🥈": "2.",
        "🥉": "3.",
    }
    for emoji, replacement in emoji_chars.items():
        text = text.replace(emoji, replacement)
    return text


def format_report_text(report: Dict[str, Any], use_emoji: bool = True) -> str:
    lines = []
    lines.append("=" * 80)
    lines.append(f"  {report['title']}")
    lines.append(f"  Generated at: {format_timestamp(report['generated_at'])}")
    lines.append("=" * 80)
    lines.append("")

    if report["is_empty"]:
        lines.append("⚠️  NO MATCHING ENTRIES FOUND")
        lines.append("")
        lines.append("The filter criteria did not match any log entries.")
        lines.append("")
        lines.append("Filter conditions used:")
        f = report["filter"]
        if f["start_time"]:
            lines.append(f"  - Start time: {format_timestamp(f['start_time'])}")
        if f["end_time"]:
            lines.append(f"  - End time: {format_timestamp(f['end_time'])}")
        if f["levels"]:
            lines.append(f"  - Levels: {', '.join(f['levels'])}")
        if f["keywords"]:
            lines.append(f"  - Keywords: {', '.join(f['keywords'])}")
        if f["exclude_keywords"]:
            lines.append(f"  - Exclude: {', '.join(f['exclude_keywords'])}")
        if f["request_id"]:
            lines.append(f"  - Request ID: {f['request_id']}")
        if f["api_path"]:
            lines.append(f"  - API Path: {f['api_path']}")
        if f["has_stack_trace"] is not None:
            lines.append(f"  - Has stack trace: {f['has_stack_trace']}")
        if f["min_duration_ms"] is not None:
            lines.append(f"  - Min duration: {f['min_duration_ms']}ms")
        lines.append("")
        lines.append("Suggestions:")
        lines.append("  - Try relaxing the filter criteria")
        lines.append("  - Check the time range covers the expected period")
        lines.append("  - Verify keywords are spelled correctly")
        lines.append("")
        lines.append("=" * 80)
        return "\n".join(lines)

    s = report["summary"]
    lines.append("📊 SUMMARY")
    lines.append("-" * 80)
    lines.append(f"  Data source:      {report.get('path', '-')}")
    lines.append(f"  Total entries:    {s['total_entries']:,}")
    lines.append(f"  Errors:           {s['error_count']:,}")
    lines.append(f"  Warnings:         {s['warning_count']:,}")
    lines.append(f"  Stack traces:     {s['stack_trace_count']:,}")
    lines.append(f"  Unique APIs:      {s['unique_apis']}")
    lines.append(f"  Unique exceptions:{s['unique_exceptions']}")
    if s["time_range"]["start"] and s["time_range"]["end"]:
        lines.append(f"  Time range:       {format_timestamp(s['time_range']['start'])} → {format_timestamp(s['time_range']['end'])}")
    lines.append("")

    lines.append("🔍 FILTER CONDITIONS")
    lines.append("-" * 80)
    f = report["filter"]
    if report.get("path"):
        lines.append(f"  Path:             {report.get('path')}")
    if f["start_time"]:
        lines.append(f"  Start time:       {format_timestamp(f['start_time'])}")
    if f["end_time"]:
        lines.append(f"  End time:         {format_timestamp(f['end_time'])}")
    if f["levels"]:
        lines.append(f"  Levels:           {', '.join(f['levels'])}")
    if f["keywords"]:
        lines.append(f"  Keywords:         {', '.join(f['keywords'])}")
    if f["exclude_keywords"]:
        lines.append(f"  Exclude keywords: {', '.join(f['exclude_keywords'])}")
    if f["request_id"]:
        lines.append(f"  Request ID:       {f['request_id']}")
    if f["api_path"]:
        lines.append(f"  API Path:         {f['api_path']}")
    if f["has_stack_trace"] is not None:
        lines.append(f"  Has stack trace:  {f['has_stack_trace']}")
    if f["min_duration_ms"] is not None:
        lines.append(f"  Min duration:     {f['min_duration_ms']}ms")
    has_any_filter = any([
        f.get(k) for k in ["start_time", "end_time", "levels", "keywords",
                          "exclude_keywords", "request_id", "api_path",
                          "min_duration_ms"]
    ]) or f.get("has_stack_trace") is not None or report.get("path")
    if not has_any_filter:
        lines.append("  (No filters applied)")
    lines.append("")

    stats = report["stats"]

    if stats.level_counts:
        lines.append("📈 LEVEL DISTRIBUTION")
        lines.append("-" * 80)
        for level in ["TRACE", "DEBUG", "INFO", "WARNING", "ERROR", "FATAL", "CRITICAL"]:
            count = stats.level_counts.get(level, 0)
            if count > 0:
                pct = (count / s["total_entries"] * 100) if s["total_entries"] else 0
                lines.append(f"  {level.upper():<10} {count:>8,} ({pct:>5.1f}%)")
        lines.append("")

    if stats.error_trend:
        lines.append("📉 ERROR TREND (5-min buckets)")
        lines.append("-" * 80)
        max_err = max(stats.error_trend.values()) if stats.error_trend else 0
        for bucket in sorted(stats.error_trend.keys()):
            count = stats.error_trend[bucket]
            bar_len = min(30, int(count / max_err * 30)) if max_err else 0
            bar = "█" * bar_len
            lines.append(f"  {bucket} {count:>4} {bar}")
        lines.append("")

    if stats.slowest_apis:
        lines.append("🐌 SLOWEST APIs (by avg time)")
        lines.append("-" * 80)
        lines.append(f"  {'Rank':<5} {'Avg(ms)':>8} {'P95(ms)':>8} {'Count':>6} API Path")
        for i, (path, avg, p95, count) in enumerate(stats.slowest_apis, 1):
            medal = ""
            if i == 1:
                medal = "🥇"
            elif i == 2:
                medal = "🥈"
            elif i == 3:
                medal = "🥉"
            lines.append(f"  {medal}{i:<4} {avg:>8.1f} {p95:>8.1f} {count:>6} {path[:50]}")
        lines.append("")

    if stats.most_frequent_exceptions:
        lines.append("🔥 MOST FREQUENT EXCEPTIONS")
        lines.append("-" * 80)
        lines.append(f"  {'Rank':<5} {'Count':>6} Exception: Message")
        for i, (key, count) in enumerate(stats.most_frequent_exceptions, 1):
            medal = ""
            if i == 1:
                medal = "🥇"
            elif i == 2:
                medal = "🥈"
            elif i == 3:
                medal = "🥉"
            lines.append(f"  {medal}{i:<4} {count:>6} {key[:80]}")
        lines.append("")

    if stats.api_stats:
        lines.append("🔍 API PERFORMANCE DETAILS")
        lines.append("-" * 80)
        lines.append(f"  {'API Path':<40} {'Count':>6} {'Avg':>8} {'P50':>8} {'P90':>8} {'P95':>8} {'Errors':>6}")
        sorted_apis = sorted(stats.api_stats.values(), key=lambda x: x.avg_time, reverse=True)
        for api in sorted_apis[:10]:
            err = "!" if api.error_count > 0 else " "
            lines.append(f"  {err}{api.path:<39} {api.count:>6} {api.avg_time:>8.1f} {api.p50:>8.1f} {api.p90:>8.1f} {api.p95:>8.1f} {api.error_count:>6}")
        lines.append("")

    samples = report["samples"]

    if samples["errors"]:
        lines.append("💥 SAMPLE ERRORS")
        lines.append("-" * 80)
        for i, entry in enumerate(samples["errors"], 1):
            lines.append(f"  [{i}] {format_timestamp(entry.timestamp)} {entry.level}")
            lines.append(f"      {entry.message[:100]}")
            if entry.api_path:
                lines.append(f"      API: {entry.api_path}")
            if entry.request_id:
                lines.append(f"      ReqID: {entry.request_id}")
            if entry.stack_trace:
                lines.append(f"      Stack trace ({len(entry.stack_trace)} lines):")
                for line in entry.stack_trace[:3]:
                    lines.append(f"        {line}")
                if len(entry.stack_trace) > 3:
                    lines.append(f"        ... and {len(entry.stack_trace) - 3} more lines")
            lines.append("")

    if samples["stack_traces"]:
        lines.append("📋 SAMPLE STACK TRACES")
        lines.append("-" * 80)
        for i, entry in enumerate(samples["stack_traces"], 1):
            if entry.timestamp:
                lines.append(f"  [{i}] {format_timestamp(entry.timestamp)} {entry.level or ''}")
            else:
                lines.append(f"  [{i}] Stack trace")
            if entry.message and entry.message.strip():
                lines.append(f"      {entry.message[:100]}")
            if entry.stack_trace:
                lines.append(f"      Stack trace ({len(entry.stack_trace)} lines):")
                for line in entry.stack_trace[:5]:
                    lines.append(f"        {line}")
                if len(entry.stack_trace) > 5:
                    lines.append(f"        ... and {len(entry.stack_trace) - 5} more lines")
            lines.append("")

    if samples["entries"] and not samples["errors"] and not samples["stack_traces"]:
        lines.append("📝 SAMPLE ENTRIES")
        lines.append("-" * 80)
        for i, entry in enumerate(samples["entries"], 1):
            lines.append(f"  [{i}] {format_timestamp(entry.timestamp)} {entry.level}")
            lines.append(f"      {entry.message[:100]}")
        lines.append("")

    lines.append("=" * 80)
    lines.append("  End of Report")
    lines.append("=" * 80)

    content = "\n".join(lines)
    if not use_emoji:
        content = _strip_emoji(content)
    return content


def format_report_markdown(report: Dict[str, Any], use_emoji: bool = True) -> str:
    lines = []
    lines.append(f"# {report['title']}")
    lines.append("")
    lines.append(f"*Generated at: {format_timestamp(report['generated_at'])}*")
    lines.append("")

    if report["is_empty"]:
        lines.append("## ⚠️ No Matching Entries Found")
        lines.append("")
        lines.append("The filter criteria did not match any log entries.")
        lines.append("")
        lines.append("### Filter Conditions Used")
        lines.append("")
        f = report["filter"]
        items = []
        if f["start_time"]:
            items.append(f"- **Start time:** {format_timestamp(f['start_time'])}")
        if f["end_time"]:
            items.append(f"- **End time:** {format_timestamp(f['end_time'])}")
        if f["levels"]:
            items.append(f"- **Levels:** {', '.join(f['levels'])}")
        if f["keywords"]:
            items.append(f"- **Keywords:** {', '.join(f['keywords'])}")
        if f["exclude_keywords"]:
            items.append(f"- **Exclude:** {', '.join(f['exclude_keywords'])}")
        if f["request_id"]:
            items.append(f"- **Request ID:** {f['request_id']}")
        if f["api_path"]:
            items.append(f"- **API Path:** {f['api_path']}")
        if f["has_stack_trace"] is not None:
            items.append(f"- **Has stack trace:** {f['has_stack_trace']}")
        if f["min_duration_ms"] is not None:
            items.append(f"- **Min duration:** {f['min_duration_ms']}ms")

        if items:
            lines.extend(items)
        else:
            lines.append("- No filters applied")
        lines.append("")
        lines.append("### Suggestions")
        lines.append("")
        lines.append("- Try relaxing the filter criteria")
        lines.append("- Check the time range covers the expected period")
        lines.append("- Verify keywords are spelled correctly")
        lines.append("")
        return "\n".join(lines)

    s = report["summary"]
    lines.append("## 📊 Summary")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    if report.get("path"):
        lines.append(f"| Data source | {report.get('path')} |")
    lines.append(f"| Total entries | {s['total_entries']:,} |")
    lines.append(f"| Errors | {s['error_count']:,} |")
    lines.append(f"| Warnings | {s['warning_count']:,} |")
    lines.append(f"| Stack traces | {s['stack_trace_count']:,} |")
    lines.append(f"| Unique APIs | {s['unique_apis']} |")
    lines.append(f"| Unique exceptions | {s['unique_exceptions']} |")
    if s["time_range"]["start"] and s["time_range"]["end"]:
        lines.append(f"| Time range | {format_timestamp(s['time_range']['start'])} → {format_timestamp(s['time_range']['end'])} |")
    lines.append("")

    lines.append("## 🔍 Filter Conditions")
    lines.append("")
    f = report["filter"]
    items = []
    if report.get("path"):
        items.append(f"- **Data source:** {report.get('path')}")
    if f["start_time"]:
        items.append(f"- **Start time:** {format_timestamp(f['start_time'])}")
    if f["end_time"]:
        items.append(f"- **End time:** {format_timestamp(f['end_time'])}")
    if f["levels"]:
        items.append(f"- **Levels:** {', '.join(f['levels'])}")
    if f["keywords"]:
        items.append(f"- **Keywords:** {', '.join(f['keywords'])}")
    if f["exclude_keywords"]:
        items.append(f"- **Exclude keywords:** {', '.join(f['exclude_keywords'])}")
    if f["request_id"]:
        items.append(f"- **Request ID:** {f['request_id']}")
    if f["api_path"]:
        items.append(f"- **API Path:** {f['api_path']}")
    if f["has_stack_trace"] is not None:
        items.append(f"- **Has stack trace:** {f['has_stack_trace']}")
    if f["min_duration_ms"] is not None:
        items.append(f"- **Min duration:** {f['min_duration_ms']}ms")
    if items:
        lines.extend(items)
    else:
        lines.append("_No filters applied_")
    lines.append("")

    stats = report["stats"]

    if stats.level_counts:
        lines.append("## 📈 Level Distribution")
        lines.append("")
        lines.append("| Level | Count | Percentage |")
        lines.append("|-------|-------|------------|")
        for level in ["TRACE", "DEBUG", "INFO", "WARNING", "ERROR", "FATAL", "CRITICAL"]:
            count = stats.level_counts.get(level, 0)
            if count > 0:
                pct = (count / s["total_entries"] * 100) if s["total_entries"] else 0
                lines.append(f"| {level.upper()} | {count:,} | {pct:.1f}% |")
        lines.append("")

    if stats.error_trend:
        lines.append("## 📉 Error Trend (5-min buckets)")
        lines.append("")
        lines.append("| Time Bucket | Error Count |")
        lines.append("|-------------|-------------|")
        for bucket in sorted(stats.error_trend.keys()):
            count = stats.error_trend[bucket]
            lines.append(f"| {bucket} | {count} |")
        lines.append("")

    if stats.slowest_apis:
        lines.append("## 🐌 Slowest APIs (by avg time)")
        lines.append("")
        lines.append("| Rank | Avg(ms) | P95(ms) | Count | API Path |")
        lines.append("|------|---------|---------|-------|----------|")
        for i, (path, avg, p95, count) in enumerate(stats.slowest_apis, 1):
            medal = ""
            if i == 1:
                medal = "🥇 "
            elif i == 2:
                medal = "🥈 "
            elif i == 3:
                medal = "🥉 "
            lines.append(f"| {medal}{i} | {avg:.1f} | {p95:.1f} | {count} | {path} |")
        lines.append("")

    if stats.most_frequent_exceptions:
        lines.append("## 🔥 Most Frequent Exceptions")
        lines.append("")
        lines.append("| Rank | Count | Exception: Message |")
        lines.append("|------|-------|-------------------|")
        for i, (key, count) in enumerate(stats.most_frequent_exceptions, 1):
            medal = ""
            if i == 1:
                medal = "🥇 "
            elif i == 2:
                medal = "🥈 "
            elif i == 3:
                medal = "🥉 "
            lines.append(f"| {medal}{i} | {count} | {key} |")
        lines.append("")

    if stats.api_stats:
        lines.append("## 🔍 API Performance Details")
        lines.append("")
        lines.append("| API Path | Count | Avg(ms) | P50(ms) | P90(ms) | P95(ms) | Errors |")
        lines.append("|----------|-------|---------|---------|---------|---------|--------|")
        sorted_apis = sorted(stats.api_stats.values(), key=lambda x: x.avg_time, reverse=True)
        for api in sorted_apis[:15]:
            err_marker = "⚠️ " if api.error_count > 0 else ""
            lines.append(f"| {err_marker}{api.path} | {api.count} | {api.avg_time:.1f} | {api.p50:.1f} | {api.p90:.1f} | {api.p95:.1f} | {api.error_count} |")
        lines.append("")

    samples = report["samples"]

    if samples["errors"]:
        lines.append("## 💥 Sample Errors")
        lines.append("")
        for i, entry in enumerate(samples["errors"], 1):
            lines.append(f"### [{i}] {format_timestamp(entry.timestamp)} - {entry.level}")
            lines.append("")
            lines.append(f"**Message:** {entry.message}")
            lines.append("")
            if entry.api_path:
                lines.append(f"- **API:** {entry.api_path}")
            if entry.request_id:
                lines.append(f"- **Request ID:** {entry.request_id}")
            if entry.source_file:
                lines.append(f"- **Source:** {entry.source_file}:{entry.line_number}")
            lines.append("")
            if entry.stack_trace:
                lines.append("**Stack trace:**")
                lines.append("")
                lines.append("```")
                for line in entry.stack_trace[:10]:
                    lines.append(line)
                if len(entry.stack_trace) > 10:
                    lines.append(f"... and {len(entry.stack_trace) - 10} more lines")
                lines.append("```")
            lines.append("")

    if samples["stack_traces"]:
        lines.append("## 📋 Sample Stack Traces")
        lines.append("")
        for i, entry in enumerate(samples["stack_traces"], 1):
            if entry.timestamp:
                lines.append(f"### [{i}] {format_timestamp(entry.timestamp)} - {entry.level or 'Stack'}")
            else:
                lines.append(f"### [{i}] Stack Trace")
            lines.append("")
            if entry.message and entry.message.strip():
                lines.append(f"**Message:** {entry.message}")
                lines.append("")
            if entry.source_file:
                lines.append(f"- **Source:** {entry.source_file}:{entry.line_number}")
                lines.append("")
            if entry.stack_trace:
                lines.append("**Stack trace:**")
                lines.append("")
                lines.append("```")
                for line in entry.stack_trace[:10]:
                    lines.append(line)
                if len(entry.stack_trace) > 10:
                    lines.append(f"... and {len(entry.stack_trace) - 10} more lines")
                lines.append("```")
            lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("*Report generated by logalyzer*")

    content = "\n".join(lines)
    if not use_emoji:
        content = _strip_emoji(content)
    return content


def generate_report(
    entries: List[LogEntry],
    filter_options: FilterOptions,
    output_path: str,
    format_type: str = "markdown",
    title: str = "Log Analysis Report",
    include_samples: int = 5,
    time_bucket_minutes: int = 5,
    path: str = "",
) -> None:
    if not entries:
        stats_result = StatsResult()
    else:
        stats_result = analyze_stats(iter(entries), time_bucket_minutes=time_bucket_minutes)

    report_data = build_report(
        entries=entries,
        stats_result=stats_result,
        filter_options=filter_options,
        title=title,
        include_samples=include_samples,
        path=path,
    )

    if format_type == "markdown":
        content = format_report_markdown(report_data)
    else:
        content = format_report_text(report_data)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)
