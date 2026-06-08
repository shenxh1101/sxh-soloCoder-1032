from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Dict, Any


@dataclass
class LogEntry:
    raw: str
    timestamp: Optional[datetime] = None
    level: Optional[str] = None
    message: Optional[str] = None
    logger: Optional[str] = None
    thread: Optional[str] = None
    request_id: Optional[str] = None
    trace_id: Optional[str] = None
    stack_trace: Optional[List[str]] = None
    duration_ms: Optional[float] = None
    api_path: Optional[str] = None
    source_file: str = ""
    line_number: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class LogFile:
    path: str
    size: int
    modified: datetime
    encoding: str = "utf-8"
    line_count: int = 0
    raw_line_count: int = 0
    level_counts: Dict[str, int] = field(default_factory=dict)
    time_range: Optional[tuple] = None


@dataclass
class FilterOptions:
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    levels: Optional[List[str]] = None
    keywords: Optional[List[str]] = None
    exclude_keywords: Optional[List[str]] = None
    request_id: Optional[str] = None
    api_path: Optional[str] = None
    has_stack_trace: Optional[bool] = None
    min_duration_ms: Optional[float] = None


@dataclass
class ApiStats:
    path: str
    count: int = 0
    total_time: float = 0
    avg_time: float = 0
    max_time: float = 0
    min_time: float = float("inf")
    error_count: int = 0
    durations: List[float] = field(default_factory=list)
    p50: float = 0
    p90: float = 0
    p95: float = 0


@dataclass
class StatsResult:
    total_entries: int = 0
    level_counts: Dict[str, int] = field(default_factory=dict)
    api_stats: Dict[str, ApiStats] = field(default_factory=dict)
    exception_counts: Dict[str, int] = field(default_factory=dict)
    exception_groups: Dict[str, int] = field(default_factory=dict)
    top_errors: List[tuple] = field(default_factory=list)
    time_distribution: Dict[str, int] = field(default_factory=dict)
    error_trend: Dict[str, int] = field(default_factory=dict)
    slowest_apis: List[tuple] = field(default_factory=list)
    most_frequent_exceptions: List[tuple] = field(default_factory=list)


@dataclass
class SavedQuery:
    name: str
    description: str = ""
    command: str = ""
    options: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    last_used_at: Optional[datetime] = None
    uses_count: int = 0
