import os
import yaml
from datetime import datetime
from typing import List, Optional, Dict, Any

from .models import SavedQuery
from .constants import CONFIG_DIR, SAVED_QUERIES_FILE


def get_config_dir() -> str:
    home = os.path.expanduser("~")
    config_path = os.path.join(home, CONFIG_DIR)
    os.makedirs(config_path, exist_ok=True)
    return config_path


def get_queries_file() -> str:
    return os.path.join(get_config_dir(), SAVED_QUERIES_FILE)


def _parse_dt(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except (ValueError, TypeError):
            return None
    return value


def _serialize_dt(dt: Optional[datetime]) -> Optional[str]:
    return dt.isoformat() if dt else None


def load_saved_queries() -> Dict[str, SavedQuery]:
    queries_file = get_queries_file()
    if not os.path.exists(queries_file):
        return {}

    with open(queries_file, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    queries = {}
    for name, item in data.items():
        queries[name] = SavedQuery(
            name=name,
            description=item.get("description", ""),
            command=item.get("command", ""),
            options=item.get("options", {}),
            created_at=_parse_dt(item.get("created_at")) or datetime.now(),
            last_used_at=_parse_dt(item.get("last_used_at")),
            uses_count=item.get("uses_count", 0),
        )
    return queries


def _save_all(queries: Dict[str, SavedQuery]) -> None:
    data = {}
    for name, q in queries.items():
        data[name] = {
            "description": q.description,
            "command": q.command,
            "options": q.options,
            "created_at": _serialize_dt(q.created_at),
            "last_used_at": _serialize_dt(q.last_used_at),
            "uses_count": q.uses_count,
        }

    with open(get_queries_file(), "w", encoding="utf-8") as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True)


def save_query(query: SavedQuery) -> None:
    queries = load_saved_queries()
    queries[query.name] = query
    _save_all(queries)


def mark_query_used(name: str) -> Optional[SavedQuery]:
    queries = load_saved_queries()
    if name in queries:
        q = queries[name]
        q.last_used_at = datetime.now()
        q.uses_count += 1
        _save_all(queries)
        return q
    return None


def delete_query(name: str) -> bool:
    queries = load_saved_queries()
    if name in queries:
        del queries[name]
        _save_all(queries)
        return True
    return False


def list_queries() -> List[SavedQuery]:
    queries = load_saved_queries()
    return sorted(queries.values(), key=lambda q: q.last_used_at or q.created_at, reverse=True)


def get_query(name: str) -> Optional[SavedQuery]:
    queries = load_saved_queries()
    return queries.get(name)


def build_command_from_query(query: SavedQuery) -> str:
    parts = ["logalyzer", query.command]
    opts = query.options or {}

    if "path" in opts and opts["path"]:
        parts.append(opts["path"])

    if "levels" in opts and opts["levels"]:
        for lvl in opts["levels"]:
            parts.extend(["-l", lvl])

    if "keywords" in opts and opts["keywords"]:
        for kw in opts["keywords"]:
            parts.extend(["-k", f"'{kw}'"])

    if "exclude" in opts and opts["exclude"]:
        for ex in opts["exclude"]:
            parts.extend(["-x", f"'{ex}'"])

    if "request_id" in opts and opts["request_id"]:
        parts.extend(["--request-id", opts["request_id"]])

    if "min_duration" in opts and opts["min_duration"] is not None:
        parts.extend(["--min-duration", str(opts["min_duration"])])

    return " ".join(parts)
