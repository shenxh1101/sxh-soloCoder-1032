from typing import List, Optional
from datetime import datetime
from rich.console import Console
from rich.table import Table
from rich.text import Text
from rich.panel import Panel
from rich import box

from .models import LogEntry, LogFile, StatsResult

console = Console()


LEVEL_COLORS = {
    "TRACE": "grey50",
    "DEBUG": "cyan",
    "INFO": "green",
    "WARN": "yellow",
    "WARNING": "yellow",
    "ERROR": "red",
    "FATAL": "bold red",
    "CRITICAL": "bold red",
}


def format_timestamp(ts: Optional[datetime]) -> str:
    if ts is None:
        return "-"
    return ts.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


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


def colored_level(level: Optional[str]) -> Text:
    if level is None:
        return Text("-", style="grey50")
    color = LEVEL_COLORS.get(level.upper(), "white")
    return Text(level.upper(), style=color)


def print_log_entries(
    entries: List[LogEntry],
    show_stack: bool = True,
    limit: Optional[int] = None,
    format_type: str = "table",
) -> None:
    if not entries:
        console.print("[yellow]No matching entries found[/yellow]")
        return

    if limit:
        entries = entries[:limit]

    if format_type == "table":
        table = Table(show_header=True, header_style="bold magenta", box=box.SIMPLE)
        table.add_column("Time", style="dim", no_wrap=True)
        table.add_column("Level", no_wrap=True)
        table.add_column("File:Line", style="dim", no_wrap=True)
        table.add_column("Message", overflow="fold")

        for entry in entries:
            file_info = f"{entry.source_file.split('/')[-1].split('\\')[-1]}:{entry.line_number}"
            table.add_row(
                format_timestamp(entry.timestamp),
                colored_level(entry.level),
                file_info,
                entry.message or entry.raw[:200],
            )

        console.print(table)

    elif format_type == "raw":
        for entry in entries:
            console.print(entry.raw)
            if show_stack and entry.stack_trace:
                for line in entry.stack_trace:
                    console.print(f"  [red]{line}[/red]")

    elif format_type == "compact":
        for entry in entries:
            ts = format_timestamp(entry.timestamp)
            lvl = colored_level(entry.level)
            msg = (entry.message or entry.raw)[:150]
            console.print(f"[dim]{ts}[/dim] {lvl} {msg}")

    if show_stack and format_type in ("table", "compact"):
        entries_with_stack = [e for e in entries if e.stack_trace and len(e.stack_trace) > 0]
        if entries_with_stack:
            console.print()
            console.print(Panel("[bold red]Stack Traces[/bold red]", border_style="red"))
            for entry in entries_with_stack:
                console.print()
                console.print(f"[dim]{format_timestamp(entry.timestamp)}[/dim] {colored_level(entry.level)} [bold]{entry.message}[/bold]")
                for line in entry.stack_trace:
                    console.print(f"  [red]{line}[/red]")


def print_scan_results(log_files: List[LogFile]) -> None:
    if not log_files:
        console.print("[yellow]No log files found[/yellow]")
        return

    table = Table(show_header=True, header_style="bold magenta", box=box.SIMPLE)
    table.add_column("File", style="bold")
    table.add_column("Size", justify="right")
    table.add_column("Lines", justify="right")
    table.add_column("Modified", style="dim")
    table.add_column("Encoding")
    table.add_column("Time Range")
    table.add_column("Levels")

    for lf in log_files:
        time_range = "-"
        if lf.time_range:
            start = lf.time_range[0].strftime("%m-%d %H:%M")
            end = lf.time_range[1].strftime("%m-%d %H:%M")
            time_range = f"{start} → {end}"

        level_info = ", ".join([f"{k}:{v}" for k, v in sorted(lf.level_counts.items())]) or "-"

        table.add_row(
            lf.path,
            format_size(lf.size),
            str(lf.line_count),
            lf.modified.strftime("%Y-%m-%d %H:%M"),
            lf.encoding,
            time_range,
            level_info,
        )

    console.print(table)

    total_size = sum(lf.size for lf in log_files)
    total_lines = sum(lf.line_count for lf in log_files)
    console.print(f"\n[dim]Total: {len(log_files)} files, {format_size(total_size)}, {total_lines} lines[/dim]")


def print_stats(stats: StatsResult) -> None:
    console.print()
    console.print(Panel("[bold cyan]Log Statistics[/bold cyan]", border_style="cyan"))

    table = Table(show_header=False, box=None)
    table.add_row("[bold]Total entries:", str(stats.total_entries))
    console.print(table)

    console.print()
    console.print("[bold magenta]Level Distribution:[/bold magenta]")
    for level in ["TRACE", "DEBUG", "INFO", "WARNING", "ERROR", "FATAL", "CRITICAL"]:
        count = stats.level_counts.get(level, 0)
        if count > 0:
            bar_len = min(50, int(count / max(stats.level_counts.values()) * 50)) if stats.level_counts else 0
            bar = "█" * bar_len
            color = LEVEL_COLORS.get(level, "white")
            console.print(f"  [{color}]{level.upper():<10}[/{color}] {count:>6} [{color}]{bar}[/{color}]")

    if stats.api_stats:
        console.print()
        console.print("[bold magenta]API Performance:[/bold magenta]")
        table = Table(show_header=True, header_style="bold", box=box.SIMPLE)
        table.add_column("API Path")
        table.add_column("Count", justify="right")
        table.add_column("Avg(ms)", justify="right")
        table.add_column("Min(ms)", justify="right")
        table.add_column("Max(ms)", justify="right")
        table.add_column("Errors", justify="right")

        sorted_apis = sorted(stats.api_stats.values(), key=lambda x: x.avg_time, reverse=True)
        for api in sorted_apis[:15]:
            err_style = "red" if api.error_count > 0 else "default"
            table.add_row(
                api.path,
                str(api.count),
                f"{api.avg_time:.1f}",
                f"{api.min_time:.1f}",
                f"{api.max_time:.1f}",
                f"[{err_style}]{api.error_count}[/{err_style}]",
            )
        console.print(table)

    if stats.exception_counts:
        console.print()
        console.print("[bold magenta]Exception Types:[/bold magenta]")
        for exc, count in sorted(stats.exception_counts.items(), key=lambda x: x[1], reverse=True):
            console.print(f"  [red]{exc:<50}[/red] {count:>4} times")

    if stats.top_errors:
        console.print()
        console.print("[bold magenta]Top Error Messages:[/bold magenta]")
        for i, (msg, count) in enumerate(stats.top_errors, 1):
            console.print(f"  [yellow]{i:>2}.[/yellow] {count:>4}x {msg[:100]}...")

    if stats.time_distribution:
        console.print()
        console.print("[bold magenta]Time Distribution:[/bold magenta]")
        table = Table(show_header=True, header_style="bold", box=box.SIMPLE)
        table.add_column("Hour")
        table.add_column("Count", justify="right")
        table.add_column("Chart")

        max_count = max(stats.time_distribution.values())
        for hour in sorted(stats.time_distribution.keys()):
            count = stats.time_distribution[hour]
            bar_len = min(40, int(count / max_count * 40)) if max_count else 0
            bar = "█" * bar_len
            table.add_row(hour, str(count), f"[cyan]{bar}[/cyan]")
        console.print(table)


def print_trace_flow(entries: List[LogEntry], request_id: str) -> None:
    if not entries:
        console.print(f"[yellow]No entries found for request_id: {request_id}[/yellow]")
        return

    console.print()
    console.print(Panel(f"[bold cyan]Request Flow Trace: {request_id}[/bold cyan]", border_style="cyan"))

    table = Table(show_header=True, header_style="bold magenta", box=box.SIMPLE)
    table.add_column("#", justify="right")
    table.add_column("Time", style="dim", no_wrap=True)
    table.add_column("Delta", justify="right", style="dim")
    table.add_column("Level", no_wrap=True)
    table.add_column("Message", overflow="fold")

    first_ts = entries[0].timestamp
    for i, entry in enumerate(entries, 1):
        delta = "-"
        if entry.timestamp and first_ts:
            delta_ms = (entry.timestamp - first_ts).total_seconds() * 1000
            delta = f"{delta_ms:+.0f}ms"
        table.add_row(
            str(i),
            format_timestamp(entry.timestamp),
            delta,
            colored_level(entry.level),
            entry.message or entry.raw[:200],
        )

    console.print(table)

    if first_ts and entries[-1].timestamp:
        total_ms = (entries[-1].timestamp - first_ts).total_seconds() * 1000
        console.print(f"\n[dim]Total duration: {total_ms:.0f}ms, {len(entries)} entries[/dim]")
