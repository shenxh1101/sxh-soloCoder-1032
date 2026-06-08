import json
import csv
import os
from typing import List, Optional
from datetime import datetime

from .models import LogEntry


def format_timestamp(ts: Optional[datetime]) -> str:
    if ts is None:
        return ""
    return ts.isoformat()


def export_to_json(entries: List[LogEntry], output_path: str, pretty: bool = True) -> None:
    data = []
    for entry in entries:
        data.append({
            "timestamp": format_timestamp(entry.timestamp),
            "level": entry.level,
            "message": entry.message,
            "logger": entry.logger,
            "thread": entry.thread,
            "request_id": entry.request_id,
            "trace_id": entry.trace_id,
            "stack_trace": entry.stack_trace,
            "duration_ms": entry.duration_ms,
            "api_path": entry.api_path,
            "source_file": entry.source_file,
            "line_number": entry.line_number,
            "raw": entry.raw,
        })

    with open(output_path, "w", encoding="utf-8") as f:
        if pretty:
            json.dump(data, f, indent=2, ensure_ascii=False)
        else:
            json.dump(data, f, ensure_ascii=False)


def export_to_csv(entries: List[LogEntry], output_path: str) -> None:
    with open(output_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow([
            "timestamp",
            "level",
            "message",
            "logger",
            "thread",
            "request_id",
            "api_path",
            "duration_ms",
            "source_file",
            "line_number",
        ])
        for entry in entries:
            writer.writerow([
                format_timestamp(entry.timestamp),
                entry.level or "",
                (entry.message or "").replace("\n", " "),
                entry.logger or "",
                entry.thread or "",
                entry.request_id or "",
                entry.api_path or "",
                entry.duration_ms or "",
                entry.source_file,
                entry.line_number,
            ])


def export_to_text(entries: List[LogEntry], output_path: str, show_stack: bool = True) -> None:
    with open(output_path, "w", encoding="utf-8") as f:
        for entry in entries:
            f.write(entry.raw + "\n")
            if show_stack and entry.stack_trace:
                for line in entry.stack_trace:
                    f.write(line + "\n")


def export_entries(
    entries: List[LogEntry],
    output_path: str,
    format_type: str = "json",
    **kwargs,
) -> None:
    if format_type == "json":
        export_to_json(entries, output_path, pretty=kwargs.get("pretty", True))
    elif format_type == "csv":
        export_to_csv(entries, output_path)
    elif format_type in ("txt", "text", "log"):
        export_to_text(entries, output_path, show_stack=kwargs.get("show_stack", True))
    else:
        raise ValueError(f"Unsupported export format: {format_type}")


def auto_detect_format(output_path: str) -> str:
    ext = os.path.splitext(output_path)[1].lower()
    if ext == ".json":
        return "json"
    elif ext == ".csv":
        return "csv"
    elif ext in (".txt", ".log", ".text"):
        return "text"
    return "json"
