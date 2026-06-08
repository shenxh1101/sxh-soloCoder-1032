import os
from typing import List, Optional
from datetime import datetime, timedelta
import click
from dateutil import parser as date_parser

from . import __version__
from .models import FilterOptions, SavedQuery
from .parser import find_log_files, parse_log_file, scan_log_file
from .filters import filter_entries, sort_entries, merge_entries, get_context_entries
from .analyzer import analyze_stats, trace_request_flow, find_slow_apis, find_error_entries
from .output import print_log_entries, print_scan_results, print_stats, print_trace_flow, print_group_stats, console
from .exporter import export_entries, auto_detect_format
from .config import save_query, list_queries, delete_query, get_query
from .watcher import watch_logs
from .reporter import build_report, format_report_markdown, format_report_text


def parse_time_range(ctx, param, value):
    if value is None:
        return None
    result = parse_relative_time(value)
    if result is None:
        raise click.BadParameter(f"Invalid datetime format: {value}")
    return result


def parse_relative_time(value: str) -> Optional[datetime]:
    if not value:
        return None

    value = value.lower().strip()

    if value.endswith(" ago"):
        value = value[:-4].strip()

    if value in ("now", "today", "yesterday"):
        now = datetime.now()
        if value == "now":
            return now
        elif value == "today":
            return now.replace(hour=0, minute=0, second=0, microsecond=0)
        elif value == "yesterday":
            return (now - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)

    units = {
        "m": "minutes",
        "min": "minutes",
        "mins": "minutes",
        "h": "hours",
        "hr": "hours",
        "hrs": "hours",
        "d": "days",
        "w": "weeks",
        "s": "seconds",
        "sec": "seconds",
        "secs": "seconds",
    }

    for suffix, unit in sorted(units.items(), key=lambda x: len(x[0]), reverse=True):
        if value.endswith(suffix):
            try:
                num = int(value[:-len(suffix)])
                delta = timedelta(**{unit: num})
                return datetime.now() - delta
            except (ValueError, TypeError):
                pass

    try:
        return date_parser.parse(value)
    except (ValueError, TypeError):
        return None


def collect_entries(
    path: str,
    recursive: bool,
    merge: bool,
    sort_by: str = "timestamp",
) -> tuple[List, List]:
    files = find_log_files(path, recursive=recursive)
    if not files:
        return [], []

    all_entries = []
    file_entries_list = []

    for file_path in files:
        try:
            entries = list(parse_log_file(file_path))
            file_entries_list.append(entries)
            all_entries.extend(entries)
        except Exception as e:
            console.print(f"[yellow]Warning: Failed to parse {file_path}: {e}[/yellow]")

    if merge and len(file_entries_list) > 1:
        all_entries = merge_entries(file_entries_list, sort_by=sort_by)

    return files, all_entries


def build_filter_options(
    start_time: Optional[datetime],
    end_time: Optional[datetime],
    since: Optional[str],
    until: Optional[str],
    levels: Optional[List[str]],
    keywords: Optional[List[str]],
    exclude: Optional[List[str]],
    request_id: Optional[str],
    api_path: Optional[str],
    has_stack: Optional[bool],
    min_duration: Optional[float],
) -> FilterOptions:
    if since:
        start_time = parse_relative_time(since) or start_time
    if until:
        end_time = parse_relative_time(until) or end_time

    return FilterOptions(
        start_time=start_time,
        end_time=end_time,
        levels=levels,
        keywords=keywords,
        exclude_keywords=exclude,
        request_id=request_id,
        api_path=api_path,
        has_stack_trace=has_stack,
        min_duration_ms=min_duration,
    )


def validate_positive_int(value: Optional[int], param_name: str) -> Optional[int]:
    if value is None:
        return None
    if value <= 0:
        console.print(f"[yellow]Warning: {param_name} should be a positive number, got {value}. Using None instead.[/yellow]")
        return None
    return value


def validate_time_bucket(value: int, param_name: str = "--time-bucket") -> int:
    if value <= 0:
        console.print(f"[yellow]Warning: {param_name} should be a positive number, got {value}. Using default 5 minutes instead.[/yellow]")
        return 5
    return value


def validate_limit(value: Optional[int]) -> Optional[int]:
    if value is None:
        return None
    if value <= 0:
        console.print(f"[yellow]Warning: limit should be a positive number, got {value}. No limit will be applied.[/yellow]")
        return None
    return value


def check_query_overwrite(name: str) -> bool:
    from .config import get_query
    existing = get_query(name)
    if existing:
        console.print(f"[yellow]Query '{name}' already exists (created {existing.created_at.strftime('%Y-%m-%d %H:%M')}, used {existing.uses_count} times)[/yellow]")
        try:
            response = click.prompt(
                "Do you want to overwrite it? [y/N]",
                default="N",
                show_default=False
            ).strip().lower()
            return response in ("y", "yes")
        except click.Abort:
            return False
    return True


@click.group()
@click.version_option(version=__version__, prog_name="logalyzer")
def main():
    """Logalyzer - Fast local log analysis tool for developers and DevOps."""
    pass


@main.command()
@click.argument("path", type=click.Path(exists=True))
@click.option("--recursive/--no-recursive", "-r/-R", default=True, help="Recurse into subdirectories")
@click.option("--ext", multiple=True, default=[".log", ".txt", ".out", ".err"], help="File extensions to include")
def scan(path, recursive, ext):
    """Scan and display summary of log files."""
    files = find_log_files(path, recursive=recursive, extensions=list(ext))
    if not files:
        console.print("[yellow]No log files found[/yellow]")
        return

    with console.status("[cyan]Scanning files...[/cyan]"):
        log_files = []
        for file_path in files:
            try:
                lf = scan_log_file(file_path)
                log_files.append(lf)
            except Exception as e:
                console.print(f"[yellow]Warning: Failed to scan {file_path}: {e}[/yellow]")

    print_scan_results(log_files)


@main.command()
@click.argument("path", type=click.Path(exists=True))
@click.option("--recursive/--no-recursive", "-r/-R", default=True, help="Recurse into subdirectories")
@click.option("--merge/--no-merge", default=True, help="Merge and sort entries from multiple files")
@click.option("--sort", type=click.Choice(["timestamp", "level", "file", "duration"]), default="timestamp", help="Sort order")
@click.option("--reverse", is_flag=True, help="Reverse sort order")
@click.option("--start-time", callback=parse_time_range, help="Filter entries after this time (e.g., '2024-01-01 10:00:00')")
@click.option("--end-time", callback=parse_time_range, help="Filter entries before this time")
@click.option("--since", help="Relative start time (e.g., '1h', '30m', '2d', 'yesterday')")
@click.option("--until", help="Relative end time (e.g., 'now', '1h ago')")
@click.option("--level", "-l", "levels", multiple=True, help="Filter by log level (e.g., ERROR,WARN)")
@click.option("--keyword", "-k", "keywords", multiple=True, help="Filter by keyword (case-insensitive)")
@click.option("--exclude", "-x", multiple=True, help="Exclude entries containing keyword")
@click.option("--request-id", help="Filter by request/trace ID")
@click.option("--api-path", help="Filter by API path")
@click.option("--has-stack/--no-stack", default=None, help="Filter entries with/without stack trace")
@click.option("--min-duration", type=float, help="Filter entries with duration >= N ms")
@click.option("--format", "-f", "format_type", type=click.Choice(["table", "raw", "compact"]), default="table", help="Output format")
@click.option("--limit", "-n", type=int, help="Limit number of entries to display")
@click.option("--context", "-C", type=int, help="Show N lines of context around matching entries")
@click.option("--show-stack/--no-stack-trace", default=True, help="Show/hide stack traces")
@click.option("--save-query", "save_query_name", help="Save this filter with a name")
@click.option("--force", is_flag=True, help="Force overwrite existing query without confirmation")
def filter(path, recursive, merge, sort, reverse, start_time, end_time, since, until,
           levels, keywords, exclude, request_id, api_path, has_stack, min_duration,
           format_type, limit, context, show_stack, save_query_name, force):
    """Filter log entries by various criteria."""
    options = build_filter_options(
        start_time, end_time, since, until, levels, list(keywords) if keywords else None,
        list(exclude) if exclude else None, request_id, api_path, has_stack, min_duration
    )

    limit = validate_limit(limit)
    context = validate_positive_int(context, "--context")

    if save_query_name:
        from .config import save_query as save_query_fn
        if not force and not check_query_overwrite(save_query_name):
            console.print(f"[yellow]Save cancelled by user[/yellow]")
            return

        query = SavedQuery(
            name=save_query_name,
            description="Filter query saved from CLI",
            command="filter",
            options={
                "path": path,
                "recursive": recursive,
                "merge": merge,
                "sort": sort,
                "reverse": reverse,
                "start_time": start_time.isoformat() if start_time else None,
                "end_time": end_time.isoformat() if end_time else None,
                "since": since,
                "until": until,
                "levels": list(levels) if levels else None,
                "keywords": list(keywords) if keywords else None,
                "exclude": list(exclude) if exclude else None,
                "request_id": request_id,
                "api_path": api_path,
                "has_stack": has_stack,
                "min_duration": min_duration,
                "format": format_type,
                "limit": limit,
                "context": context,
                "show_stack": show_stack,
            },
        )
        save_query_fn(query)
        console.print(f"[green]Query saved as '{save_query_name}'[/green]")

    with console.status("[cyan]Parsing logs...[/cyan]"):
        files, all_entries = collect_entries(path, recursive, merge, sort_by=sort)

    if not all_entries:
        console.print("[yellow]No entries found[/yellow]")
        return

    with console.status("[cyan]Filtering entries...[/cyan]"):
        filtered = list(filter_entries(iter(all_entries), options))

    if reverse:
        filtered = list(reversed(filtered))
    else:
        filtered = sort_entries(filtered, by=sort)

    if context and context > 0:
        result = []
        seen = set()
        for entry in filtered:
            ctx_entries = get_context_entries(all_entries, entry, before=context, after=context)
            for ctx in ctx_entries:
                key = (ctx.source_file, ctx.line_number)
                if key not in seen:
                    seen.add(key)
                    result.append(ctx)
        filtered = sort_entries(result, by=sort)

    console.print(f"[dim]Found {len(filtered)} matching entries out of {len(all_entries)} total[/dim]")
    print_log_entries(filtered, show_stack=show_stack, limit=limit, format_type=format_type)


@main.command()
@click.argument("path", type=click.Path(exists=True))
@click.option("--recursive/--no-recursive", "-r/-R", default=True, help="Recurse into subdirectories")
@click.option("--merge/--no-merge", default=True, help="Merge entries from multiple files")
@click.option("--start-time", callback=parse_time_range, help="Filter entries after this time")
@click.option("--end-time", callback=parse_time_range, help="Filter entries before this time")
@click.option("--since", help="Relative start time (e.g., '1h', '30m', '1h ago')")
@click.option("--until", help="Relative end time (e.g., 'now', '30m ago')")
@click.option("--level", "-l", "levels", multiple=True, help="Filter by log level")
@click.option("--keyword", "-k", "keywords", multiple=True, help="Filter by keyword")
@click.option("--time-bucket", type=int, default=5, help="Error trend time bucket in minutes")
@click.option("--top-n", type=int, default=10, help="Number of items in top rankings")
@click.option("--slow-threshold", type=float, default=1000, help="Threshold for slow APIs (ms)")
@click.option("--top-slow", type=int, default=10, help="Show top N slow APIs")
@click.option("--group-by", type=click.Choice(["api_path", "request_id"]), help="Group view by field")
@click.option("--filter-api", help="Only show stats for specific API path")
@click.option("--filter-request", help="Only show stats for specific request ID")
def stats(path, recursive, merge, start_time, end_time, since, until,
          levels, keywords, time_bucket, top_n, slow_threshold, top_slow,
          group_by, filter_api, filter_request):
    """Display statistics: level distribution, API percentiles, error trend, exception rankings."""
    options = build_filter_options(
        start_time, end_time, since, until, list(levels) if levels else None,
        list(keywords) if keywords else None, None, None, None, None, None
    )

    time_bucket = validate_time_bucket(time_bucket)
    top_n = validate_positive_int(top_n, "--top-n") or 10
    top_slow = validate_positive_int(top_slow, "--top-slow") or 10

    with console.status("[cyan]Parsing logs...[/cyan]"):
        files, all_entries = collect_entries(path, recursive, merge)

    if not all_entries:
        console.print("[yellow]No entries found[/yellow]")
        return

    with console.status("[cyan]Filtering entries...[/cyan]"):
        filtered = list(filter_entries(iter(all_entries), options))

    if not filtered:
        console.print("[yellow]No matching entries found[/yellow]")
        return

    if filter_api:
        filtered = [e for e in filtered if e.api_path and filter_api.lower() in e.api_path.lower()]
    if filter_request:
        filtered = [e for e in filtered if e.request_id and filter_request.lower() in e.request_id.lower()]

    with console.status("[cyan]Analyzing statistics...[/cyan]"):
        stats_result = analyze_stats(iter(filtered), time_bucket_minutes=time_bucket, top_n=top_n)
        slow_apis = find_slow_apis(filtered, threshold_ms=slow_threshold, limit=top_slow)
        errors = find_error_entries(filtered)

    print_stats(stats_result, top_n=top_n)

    if group_by:
        from .analyzer import analyze_group_stats
        with console.status(f"[cyan]Analyzing group by {group_by}...[/cyan]"):
            group_stats = analyze_group_stats(filtered, group_by=group_by, time_bucket_minutes=time_bucket)
        print_group_stats(group_stats, group_by, top_n=top_n)

    if slow_apis:
        console.print()
        console.print(f"[bold magenta]Top {len(slow_apis)} Slow APIs (>= {slow_threshold}ms):[/bold magenta]")
        for entry in slow_apis:
            duration = entry.duration_ms or 0
            console.print(f"  [yellow]{duration:>8.0f}ms[/yellow] {entry.api_path} - {entry.message[:80]}")

    if errors:
        console.print()
        console.print(f"[bold red]Found {len(errors)} error entries[/bold red]")


@main.command()
@click.argument("path", type=click.Path(exists=True))
@click.argument("request_id")
@click.option("--recursive/--no-recursive", "-r/-R", default=True, help="Recurse into subdirectories")
@click.option("--merge/--no-merge", default=True, help="Merge entries from multiple files")
@click.option("--format", "-f", "format_type", type=click.Choice(["table", "raw", "compact"]), default="table", help="Output format")
@click.option("--show-stack/--no-stack-trace", default=True, help="Show/hide stack traces")
def trace(path, request_id, recursive, merge, format_type, show_stack):
    """Trace request flow by request ID, showing time deltas between entries."""
    with console.status("[cyan]Parsing logs...[/cyan]"):
        files, all_entries = collect_entries(path, recursive, merge)

    if not all_entries:
        console.print("[yellow]No entries found[/yellow]")
        return

    with console.status(f"[cyan]Tracing request {request_id}...[/cyan]"):
        traced = trace_request_flow(all_entries, request_id)

    if not traced:
        console.print(f"[yellow]No entries found for request_id: {request_id}[/yellow]")
        return

    if format_type == "table":
        print_trace_flow(traced, request_id)
    else:
        print_log_entries(traced, show_stack=show_stack, format_type=format_type)

    if show_stack:
        entries_with_stack = [e for e in traced if e.stack_trace and len(e.stack_trace) > 0]
        if entries_with_stack:
            console.print()
            console.print("[bold red]Stack Traces in this request:[/bold red]")
            for entry in entries_with_stack:
                console.print(f"\n[dim]{entry.timestamp}[/dim] [red]{entry.level}[/red] {entry.message}")
                for line in entry.stack_trace:
                    console.print(f"  [red]{line}[/red]")


@main.command()
@click.argument("path", type=click.Path(exists=True))
@click.option("--recursive/--no-recursive", "-r/-R", default=True, help="Recurse into subdirectories")
@click.option("--level", "-l", "levels", multiple=True, help="Filter by log level")
@click.option("--keyword", "-k", "keywords", multiple=True, help="Filter by keyword")
@click.option("--exclude", "-x", multiple=True, help="Exclude entries containing keyword")
@click.option("--request-id", help="Filter by request/trace ID")
@click.option("--api-path", help="Filter by API path")
@click.option("--has-stack/--no-stack", default=None, help="Filter entries with/without stack trace")
@click.option("--min-duration", type=float, help="Filter entries with duration >= N ms")
@click.option("--format", "-f", "format_type", type=click.Choice(["raw", "compact"]), default="compact", help="Output format")
@click.option("--show-stack/--no-stack-trace", default=True, help="Show/hide stack traces")
@click.option("--interval", type=float, default=0.5, help="Poll interval in seconds")
@click.option("--from-start", is_flag=True, help="Start reading from the beginning of the file")
def watch(path, recursive, levels, keywords, exclude, request_id, api_path, has_stack, min_duration, format_type, show_stack, interval, from_start):
    """Watch and tail log files in real-time with filtering support."""
    options = build_filter_options(
        None, None, None, None,
        list(levels) if levels else None,
        list(keywords) if keywords else None,
        list(exclude) if exclude else None,
        request_id, api_path, has_stack, min_duration
    )

    from .watcher import watch_logs as watch_fn

    watch_fn(
        path=path,
        recursive=recursive,
        filter_options=options,
        format_type=format_type,
        show_stack=show_stack,
        poll_interval=interval,
        start_from_end=not from_start,
    )


@main.command()
@click.argument("path", type=click.Path(exists=True))
@click.argument("output", type=click.Path(), required=False)
@click.option("--recursive/--no-recursive", "-r/-R", default=True, help="Recurse into subdirectories")
@click.option("--merge/--no-merge", default=True, help="Merge entries from multiple files")
@click.option("--sort", type=click.Choice(["timestamp", "level", "file", "duration"]), default="timestamp", help="Sort order")
@click.option("--start-time", callback=parse_time_range, help="Filter entries after this time")
@click.option("--end-time", callback=parse_time_range, help="Filter entries before this time")
@click.option("--since", help="Relative start time (e.g., '1h', '30m')")
@click.option("--until", help="Relative end time")
@click.option("--level", "-l", "levels", multiple=True, help="Filter by log level")
@click.option("--keyword", "-k", "keywords", multiple=True, help="Filter by keyword")
@click.option("--exclude", "-x", multiple=True, help="Exclude entries containing keyword")
@click.option("--request-id", help="Filter by request/trace ID")
@click.option("--api-path", help="Filter by API path")
@click.option("--has-stack/--no-stack", default=None, help="Filter entries with/without stack trace")
@click.option("--min-duration", type=float, help="Filter entries with duration >= N ms")
@click.option("--format", "-f", "format_type", type=click.Choice(["markdown", "text"]), default="markdown", help="Report format")
@click.option("--title", default="Log Analysis Report", help="Report title")
@click.option("--samples", type=int, default=5, help="Number of sample entries to include")
@click.option("--time-bucket", type=int, default=5, help="Time bucket in minutes for trend analysis")
@click.option("--print", "print_only", is_flag=True, help="Print report to console instead of writing to file")
def report(path, output, recursive, merge, sort, start_time, end_time, since, until,
           levels, keywords, exclude, request_id, api_path, has_stack, min_duration,
           format_type, title, samples, time_bucket, print_only):
    """Generate a troubleshooting report from log analysis results."""
    from .analyzer import analyze_stats

    time_bucket = validate_time_bucket(time_bucket)

    options = build_filter_options(
        start_time, end_time, since, until, list(levels) if levels else None,
        list(keywords) if keywords else None, list(exclude) if exclude else None,
        request_id, api_path, has_stack, min_duration
    )

    with console.status("[cyan]Parsing logs...[/cyan]"):
        files, all_entries = collect_entries(path, recursive, merge, sort_by=sort)

    if not all_entries:
        console.print("[yellow]No entries found[/yellow]")
        if not print_only and output:
            stats_result = analyze_stats(iter([]), time_bucket_minutes=time_bucket)
            report_data = build_report([], stats_result, options, title=title, include_samples=samples)
            content = format_report_markdown(report_data) if format_type == "markdown" else format_report_text(report_data)
            with open(output, "w", encoding="utf-8") as f:
                f.write(content)
            console.print(f"[green]Empty report written to {output}[/green]")
        return

    with console.status("[cyan]Filtering entries...[/cyan]"):
        filtered = list(filter_entries(iter(all_entries), options))

    console.print(f"[dim]Found {len(filtered)} matching entries out of {len(all_entries)} total[/dim]")

    with console.status("[cyan]Generating report...[/cyan]"):
        stats_result = analyze_stats(iter(filtered), time_bucket_minutes=time_bucket)
        report_data = build_report(filtered, stats_result, options, title=title, include_samples=samples)

        if format_type == "markdown":
            content = format_report_markdown(report_data, use_emoji=not print_only)
        else:
            content = format_report_text(report_data, use_emoji=not print_only)

    if print_only:
        print(content)
        return

    if not output:
        default_ext = ".md" if format_type == "markdown" else ".txt"
        safe_title = "".join(c if c.isalnum() or c in "_-" else "_" for c in title)
        output = f"{safe_title}{default_ext}"

    with open(output, "w", encoding="utf-8") as f:
        f.write(content)

    console.print(f"[green]Report written to {output} ({format_type.upper()})[/green]")
    console.print(f"[dim]{len(filtered)} entries analyzed, {len(stats_result.api_stats)} APIs, {len(stats_result.exception_counts)} exception types[/dim]")


@main.command()
@click.argument("path", type=click.Path(exists=True))
@click.argument("output", type=click.Path())
@click.option("--recursive/--no-recursive", "-r/-R", default=True, help="Recurse into subdirectories")
@click.option("--merge/--no-merge", default=True, help="Merge entries from multiple files")
@click.option("--sort", type=click.Choice(["timestamp", "level", "file", "duration"]), default="timestamp", help="Sort order")
@click.option("--start-time", callback=parse_time_range, help="Filter entries after this time")
@click.option("--end-time", callback=parse_time_range, help="Filter entries before this time")
@click.option("--since", help="Relative start time (e.g., '1h', '30m')")
@click.option("--until", help="Relative end time")
@click.option("--level", "-l", "levels", multiple=True, help="Filter by log level")
@click.option("--keyword", "-k", "keywords", multiple=True, help="Filter by keyword")
@click.option("--exclude", "-x", multiple=True, help="Exclude entries containing keyword")
@click.option("--request-id", help="Filter by request/trace ID")
@click.option("--has-stack/--no-stack", default=None, help="Filter entries with/without stack trace")
@click.option("--format", "-f", "format_type", type=click.Choice(["json", "csv", "text", "log"]), help="Output format (auto-detected by extension)")
@click.option("--pretty/--compact", default=True, help="Pretty print JSON output")
@click.option("--show-stack/--no-stack-trace", default=True, help="Include stack traces in text output")
def export(path, output, recursive, merge, sort, start_time, end_time, since, until,
           levels, keywords, exclude, request_id, has_stack, format_type, pretty, show_stack):
    """Export filtered log entries to a file (JSON, CSV, or text)."""
    options = build_filter_options(
        start_time, end_time, since, until, list(levels) if levels else None,
        list(keywords) if keywords else None, list(exclude) if exclude else None,
        request_id, None, has_stack, None
    )

    if not format_type:
        format_type = auto_detect_format(output)

    with console.status("[cyan]Parsing logs...[/cyan]"):
        files, all_entries = collect_entries(path, recursive, merge, sort_by=sort)

    if not all_entries:
        console.print("[yellow]No entries found[/yellow]")
        return

    with console.status("[cyan]Filtering entries...[/cyan]"):
        filtered = list(filter_entries(iter(all_entries), options))

    filtered = sort_entries(filtered, by=sort)

    with console.status(f"[cyan]Exporting {len(filtered)} entries to {output}...[/cyan]"):
        export_entries(
            filtered,
            output,
            format_type=format_type,
            pretty=pretty,
            show_stack=show_stack,
        )

    console.print(f"[green]Successfully exported {len(filtered)} entries to {output} ({format_type.upper()})[/green]")


@main.group()
def queries():
    """Manage saved queries."""
    pass


@queries.command("list")
def list_saved_queries():
    """List all saved queries with usage info."""
    from .config import list_queries as list_saved
    saved = list_saved()
    if not saved:
        console.print("[yellow]No saved queries[/yellow]")
        return

    from rich.table import Table
    from rich import box

    table = Table(show_header=True, header_style="bold magenta", box=box.SIMPLE)
    table.add_column("Name", style="bold")
    table.add_column("Command")
    table.add_column("Uses", justify="right")
    table.add_column("Last Used", style="dim")
    table.add_column("Created", style="dim")

    for q in saved:
        last_used = q.last_used_at.strftime("%Y-%m-%d %H:%M") if q.last_used_at else "-"
        table.add_row(
            q.name,
            q.command,
            str(q.uses_count),
            last_used,
            q.created_at.strftime("%Y-%m-%d %H:%M"),
        )

    console.print(table)


@queries.command("delete")
@click.argument("name")
def delete_saved_query(name):
    """Delete a saved query."""
    if delete_query(name):
        console.print(f"[green]Deleted query '{name}'[/green]")
    else:
        console.print(f"[yellow]Query '{name}' not found[/yellow]")


@queries.command("show")
@click.argument("name")
def show_saved_query(name):
    """Show details of a saved query with equivalent command."""
    from .config import get_query as get_saved_query, build_command_from_query

    q = get_saved_query(name)
    if not q:
        console.print(f"[yellow]Query '{name}' not found[/yellow]")
        return

    import json
    from rich.panel import Panel

    console.print(f"[bold]Name:[/bold] {q.name}")
    console.print(f"[bold]Description:[/bold] {q.description}")
    console.print(f"[bold]Command:[/bold] {q.command}")
    console.print(f"[bold]Uses:[/bold] {q.uses_count}")
    console.print(f"[bold]Created:[/bold] {q.created_at.strftime('%Y-%m-%d %H:%M')}")
    if q.last_used_at:
        console.print(f"[bold]Last Used:[/bold] {q.last_used_at.strftime('%Y-%m-%d %H:%M')}")

    console.print()
    console.print(Panel(f"[bold green]Equivalent Command:[/bold green]\n[dim]{build_command_from_query(q)}[/dim]", border_style="green"))

    console.print()
    console.print(f"[bold]Options:[/bold]")
    console.print(json.dumps(q.options, indent=2, ensure_ascii=False))


@queries.command("run")
@click.argument("name")
@click.argument("path", required=False, type=click.Path(exists=True))
@click.option("--recursive/--no-recursive", "-r/-R", default=None, help="Override recursive flag")
@click.option("--merge/--no-merge", default=None, help="Override merge flag")
@click.option("--sort", type=click.Choice(["timestamp", "level", "file", "duration"]), help="Override sort order")
@click.option("--reverse", is_flag=True, default=None, help="Override reverse sort flag")
@click.option("--since", help="Override relative start time")
@click.option("--until", help="Override relative end time")
@click.option("--level", "-l", "levels", multiple=True, help="Override log levels filter")
@click.option("--keyword", "-k", "keywords", multiple=True, help="Override keywords filter")
@click.option("--exclude", "-x", multiple=True, help="Override exclude keywords")
@click.option("--request-id", help="Override request ID filter")
@click.option("--api-path", help="Override API path filter")
@click.option("--has-stack/--no-stack", "has_stack", default=None, help="Override stack trace filter")
@click.option("--min-duration", type=float, help="Override min duration filter")
@click.option("--limit", "-n", type=int, help="Override result limit")
@click.option("--format", "-f", "format_type", type=click.Choice(["table", "raw", "compact"]), help="Override output format")
@click.option("--context", "-C", type=int, help="Override context lines")
def run_query(name, path, recursive, merge, sort, reverse, since, until, levels, keywords, exclude, request_id, api_path, has_stack, min_duration, limit, format_type, context):
    """Run a saved query with optional parameter overrides."""
    from .config import get_query as get_saved_query, mark_query_used

    q = get_saved_query(name)
    if not q:
        console.print(f"[yellow]Query '{name}' not found[/yellow]")
        console.print("Use 'logalyzer queries list' to see available queries.")
        return

    mark_query_used(name)
    console.print(f"[dim]Running saved query '{name}' (used {q.uses_count + 1} times)[/dim]")

    opts = q.options or {}

    final_path = path or opts.get("path")
    if not final_path:
        console.print("[red]Error: No path specified. Provide PATH argument or ensure query has path saved.[/red]")
        return

    final_levels = list(levels) if levels else opts.get("levels")
    final_keywords = list(keywords) if keywords else opts.get("keywords")
    final_exclude = list(exclude) if exclude else opts.get("exclude")
    final_request_id = request_id if request_id is not None else opts.get("request_id")
    final_api_path = api_path if api_path is not None else opts.get("api_path")
    final_has_stack = has_stack if has_stack is not None else opts.get("has_stack")
    final_min_duration = min_duration if min_duration is not None else opts.get("min_duration")
    final_context = context if context is not None else opts.get("context")
    final_limit = validate_limit(limit) if limit is not None else opts.get("limit")
    final_format = format_type or opts.get("format", "table")
    final_recursive = recursive if recursive is not None else opts.get("recursive", True)
    final_merge = merge if merge is not None else opts.get("merge", True)
    final_sort = sort or opts.get("sort", "timestamp")
    final_reverse = reverse if reverse is not None else opts.get("reverse", False)

    final_since = since or opts.get("since")
    final_until = until or opts.get("until")

    filter_options = build_filter_options(
        None, None, final_since, final_until,
        final_levels, final_keywords, final_exclude,
        final_request_id, final_api_path, final_has_stack, final_min_duration
    )

    with console.status("[cyan]Parsing logs...[/cyan]"):
        files, all_entries = collect_entries(final_path, final_recursive, final_merge, sort_by=final_sort)

    if not all_entries:
        console.print("[yellow]No entries found[/yellow]")
        return

    with console.status("[cyan]Filtering entries...[/cyan]"):
        filtered = list(filter_entries(iter(all_entries), filter_options))

    if final_reverse:
        filtered = list(reversed(filtered))
    else:
        filtered = sort_entries(filtered, by=final_sort)

    if final_context and final_context > 0:
        result = []
        seen = set()
        for entry in filtered:
            ctx_entries = get_context_entries(all_entries, entry, before=final_context, after=final_context)
            for ctx in ctx_entries:
                key = (ctx.source_file, ctx.line_number)
                if key not in seen:
                    seen.add(key)
                    result.append(ctx)
        filtered = sort_entries(result, by=final_sort)

    console.print(f"[dim]Found {len(filtered)} matching entries out of {len(all_entries)} total[/dim]")
    print_log_entries(filtered, show_stack=True, limit=final_limit, format_type=final_format)


if __name__ == "__main__":
    main()
