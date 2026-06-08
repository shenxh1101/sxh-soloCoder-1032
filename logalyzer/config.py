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


def load_saved_queries() -> Dict[str, SavedQuery]:
    queries_file = get_queries_file()
    if not os.path.exists(queries_file):
        return {}

    with open(queries_file, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    queries = {}
    for name, item in data.items():
        created_at = item.get("created_at")
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)

        queries[name] = SavedQuery(
            name=name,
            description=item.get("description", ""),
            command=item.get("command", ""),
            options=item.get("options", {}),
            created_at=created_at or datetime.now(),
        )
    return queries


def save_query(query: SavedQuery) -> None:
    queries = load_saved_queries()
    queries[query.name] = query

    data = {}
    for name, q in queries.items():
        data[name] = {
            "description": q.description,
            "command": q.command,
            "options": q.options,
            "created_at": q.created_at.isoformat(),
        }

    with open(get_queries_file(), "w", encoding="utf-8") as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True)


def delete_query(name: str) -> bool:
    queries = load_saved_queries()
    if name in queries:
        del queries[name]

        data = {}
        for n, q in queries.items():
            data[n] = {
                "description": q.description,
                "command": q.command,
                "options": q.options,
                "created_at": q.created_at.isoformat(),
            }

        with open(get_queries_file(), "w", encoding="utf-8") as f:
            yaml.dump(data, f, default_flow_style=False, allow_unicode=True)
        return True
    return False


def list_queries() -> List[SavedQuery]:
    queries = load_saved_queries()
    return sorted(queries.values(), key=lambda q: q.created_at, reverse=True)


def get_query(name: str) -> Optional[SavedQuery]:
    queries = load_saved_queries()
    return queries.get(name)
