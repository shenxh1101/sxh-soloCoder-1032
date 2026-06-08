import os
import time
from typing import Dict, List, Optional, Callable, Iterator, Set
from datetime import datetime

from .models import LogEntry, FilterOptions
from .parser import find_log_files, parse_log_line, detect_encoding
from .filters import matches_filter
from .output import print_log_entries, console


class LogFileTracker:
    def __init__(self, file_path: str, start_from_end: bool = True):
        self.file_path = file_path
        self.encoding = detect_encoding(file_path)
        if start_from_end:
            self.position = self._get_file_size()
        else:
            self.position = 0
        self.current_entry: Optional[LogEntry] = None
        self.last_checked = datetime.now()
        self.last_stack_time: Optional[datetime] = None
        self._in_stack_trace = False

    def _get_file_size(self) -> int:
        try:
            return os.path.getsize(self.file_path)
        except (OSError, FileNotFoundError):
            return 0

    def read_new_lines(self) -> List[str]:
        lines = []
        try:
            current_size = self._get_file_size()
            if current_size < self.position:
                self.position = 0

            if current_size > self.position:
                with open(self.file_path, "r", encoding=self.encoding, errors="replace") as f:
                    f.seek(self.position)
                    new_content = f.read(current_size - self.position)
                    lines = new_content.splitlines(keepends=False)
                    self.position = current_size
        except (OSError, FileNotFoundError):
            pass
        return lines

    def process_new_lines(self, lines: List[str]) -> List[LogEntry]:
        entries: List[LogEntry] = []

        for line in lines:
            if not line.strip():
                continue

            from .parser import is_stack_trace_line

            if is_stack_trace_line(line):
                self._in_stack_trace = True
                self.last_stack_time = datetime.now()
                if self.current_entry is not None:
                    if self.current_entry.stack_trace is None:
                        self.current_entry.stack_trace = []
                    self.current_entry.stack_trace.append(line)
                continue

            self._in_stack_trace = False

            if self.current_entry is not None:
                entries.append(self.current_entry)

            self.current_entry = parse_log_line(line)
            if self.current_entry is not None:
                self.current_entry.source_file = self.file_path

        return entries

    def has_pending_stack(self, max_wait_seconds: float = 0.5) -> bool:
        if not self._in_stack_trace or self.current_entry is None:
            return False
        if self.last_stack_time is None:
            return False
        elapsed = (datetime.now() - self.last_stack_time).total_seconds()
        return elapsed < max_wait_seconds

    def flush(self) -> Optional[LogEntry]:
        entry = self.current_entry
        self.current_entry = None
        self._in_stack_trace = False
        return entry


class LogWatcher:
    def __init__(
        self,
        path: str,
        recursive: bool = True,
        filter_options: Optional[FilterOptions] = None,
        poll_interval: float = 0.5,
        start_from_end: bool = True,
    ):
        self.path = path
        self.recursive = recursive
        self.filter_options = filter_options or FilterOptions()
        self.poll_interval = max(poll_interval, 0.1)
        self.trackers: Dict[str, LogFileTracker] = {}
        self.start_from_end = start_from_end
        self._discover_files()

    def _discover_files(self) -> None:
        current_files: Set[str] = set()

        files = find_log_files(self.path, recursive=self.recursive)
        for file_path in files:
            current_files.add(file_path)
            if file_path not in self.trackers:
                self.trackers[file_path] = LogFileTracker(file_path, start_from_end=self.start_from_end)

        for file_path in list(self.trackers.keys()):
            if file_path not in current_files:
                del self.trackers[file_path]

    def poll(self) -> List[LogEntry]:
        self._discover_files()

        all_entries: List[LogEntry] = []

        for tracker in self.trackers.values():
            lines = tracker.read_new_lines()
            if lines:
                entries = tracker.process_new_lines(lines)
                for entry in entries:
                    if matches_filter(entry, self.filter_options):
                        all_entries.append(entry)

            if tracker.current_entry is not None:
                if not tracker.has_pending_stack():
                    entry = tracker.flush()
                    if entry and matches_filter(entry, self.filter_options):
                        all_entries.append(entry)

        return all_entries

    def watch(
        self,
        callback: Optional[Callable[[List[LogEntry]], None]] = None,
        stop_condition: Optional[Callable[[], bool]] = None,
    ) -> None:
        console.print("[cyan]Starting log watcher... (Press Ctrl+C to stop)[/cyan]")
        console.print(f"[dim]Watching: {self.path}[/dim]")
        console.print(f"[dim]Poll interval: {self.poll_interval}s[/dim]")
        if self.filter_options.keywords:
            console.print(f"[dim]Keywords: {', '.join(self.filter_options.keywords)}[/dim]")
        if self.filter_options.levels:
            console.print(f"[dim]Levels: {', '.join(self.filter_options.levels)}[/dim]")
        if self.filter_options.request_id:
            console.print(f"[dim]Request ID: {self.filter_options.request_id}[/dim]")

        try:
            while True:
                if stop_condition and stop_condition():
                    break

                entries = self.poll()
                if entries and callback:
                    callback(entries)

                time.sleep(self.poll_interval)
        except KeyboardInterrupt:
            for tracker in self.trackers.values():
                entry = tracker.flush()
                if entry and callback and matches_filter(entry, self.filter_options):
                    callback([entry])
            console.print("\n[yellow]Watcher stopped by user[/yellow]")


def watch_logs(
    path: str,
    recursive: bool = True,
    filter_options: Optional[FilterOptions] = None,
    format_type: str = "compact",
    show_stack: bool = True,
    poll_interval: float = 0.5,
    start_from_end: bool = True,
) -> None:
    watcher = LogWatcher(
        path,
        recursive=recursive,
        filter_options=filter_options,
        poll_interval=poll_interval,
        start_from_end=start_from_end,
    )

    def print_entries(entries: List[LogEntry]) -> None:
        print_log_entries(entries, show_stack=show_stack, format_type=format_type)

    watcher.watch(callback=print_entries)
