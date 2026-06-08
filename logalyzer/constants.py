from typing import List, Pattern
import re


LOG_LEVELS = ["TRACE", "DEBUG", "INFO", "WARN", "WARNING", "ERROR", "FATAL", "CRITICAL"]

LOG_LEVEL_PRIORITY = {
    "TRACE": 0,
    "DEBUG": 1,
    "INFO": 2,
    "WARN": 3,
    "WARNING": 3,
    "ERROR": 4,
    "FATAL": 5,
    "CRITICAL": 5,
}

TIMESTAMP_PATTERNS: List[Pattern] = [
    re.compile(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:[.,]\d{1,9})?(?:Z|[+-]\d{2}:?\d{2})?"),
    re.compile(r"\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2}(?:[.,]\d{1,9})?"),
    re.compile(r"\d{2}-\d{2}-\d{4} \d{2}:\d{2}:\d{2}(?:[.,]\d{1,9})?"),
    re.compile(r"\[?\d{2}/\w{3}/\d{4}:\d{2}:\d{2}:\d{2}[+-]\d{4}\]?"),
    re.compile(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}"),
]

LEVEL_PATTERN = re.compile(r"\b(TRACE|DEBUG|INFO|WARN(?:ING)?|ERROR|FATAL|CRITICAL)\b", re.IGNORECASE)

REQUEST_ID_PATTERNS: List[Pattern] = [
    re.compile(r"[Rr]equest[_-]?[Ii][Dd][:=]\s*([a-zA-Z0-9\-]+)"),
    re.compile(r"[Tt]race[_-]?[Ii][Dd][:=]\s*([a-zA-Z0-9\-]+)"),
    re.compile(r"[Xx]-[Rr]equest-[Ii][Dd][:=]\s*([a-zA-Z0-9\-]+)"),
    re.compile(r"[Xx]-[Cc]orrelation-[Ii][Dd][:=]\s*([a-zA-Z0-9\-]+)"),
    re.compile(r"\b([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\b", re.IGNORECASE),
]

API_PATH_PATTERNS: List[Pattern] = [
    re.compile(r'"(?:GET|POST|PUT|DELETE|PATCH|HEAD|OPTIONS)\s+([^\s"]+)\s+HTTP/\d+\.\d+"'),
    re.compile(r"(?:GET|POST|PUT|DELETE|PATCH|HEAD|OPTIONS)\s+(/[^\s]+)"),
    re.compile(r"path[=:]\s*(/[^\s,]+)"),
    re.compile(r"uri[=:]\s*(/[^\s,]+)"),
]

DURATION_PATTERNS: List[Pattern] = [
    re.compile(r"(\d+(?:\.\d+)?)\s*(?:ms|milliseconds?)", re.IGNORECASE),
    re.compile(r"took[=:\s]\s*(\d+(?:\.\d+)?)", re.IGNORECASE),
    re.compile(r"duration[=:\s]\s*(\d+(?:\.\d+)?)", re.IGNORECASE),
    re.compile(r"elapsed[=:\s]\s*(\d+(?:\.\d+)?)", re.IGNORECASE),
    re.compile(r"cost[=:\s]\s*(\d+(?:\.\d+)?)", re.IGNORECASE),
    re.compile(r"耗时[=:\s]\s*(\d+(?:\.\d+)?)", re.IGNORECASE),
]

EXCEPTION_PATTERN = re.compile(r"([a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*)*(?:Exception|Error)):")

STACK_TRACE_LINE_PATTERN = re.compile(r"^(?:\s+(?:at\s+|\.{3}\s*\d+\s+more)|Caused by:)")

LOG_LINE_PATTERNS: List[Pattern] = [
    re.compile(
        r"^(?P<timestamp>\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}[.,\d]*)\s+"
        r"(?P<level>TRACE|DEBUG|INFO|WARN(?:ING)?|ERROR|FATAL|CRITICAL)\s+"
        r"(?P<logger>[^\s]+)\s*:\s*"
        r"(?P<message>.*)$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^(?P<timestamp>\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}[.,\d]*)\s+"
        r"\[(?P<thread>[^\]]+)\]\s+"
        r"(?P<level>TRACE|DEBUG|INFO|WARN(?:ING)?|ERROR|FATAL|CRITICAL)\s+"
        r"(?P<logger>[^\s]+)\s*-\s*"
        r"(?P<message>.*)$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^\[(?P<timestamp>\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}[.,\d]*)\]\s+"
        r"\[(?P<level>TRACE|DEBUG|INFO|WARN(?:ING)?|ERROR|FATAL|CRITICAL)\]\s*"
        r"(?P<message>.*)$",
        re.IGNORECASE,
    ),
]

DEFAULT_ENCODINGS = ["utf-8", "gbk", "latin-1", "utf-16"]

CONFIG_DIR = ".logalyzer"
SAVED_QUERIES_FILE = "queries.yaml"
