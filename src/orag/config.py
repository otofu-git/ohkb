"""Configuration and path management."""

from __future__ import annotations

import os
from pathlib import Path

# Environment variable to override default data directory
ENV_DATA_DIR = "ORAG_DIR"

# Default directory name
DEFAULT_DIR_NAME = ".orag"


def get_data_dir() -> Path:
    """Return the orag data directory, creating it if needed."""
    if env := os.environ.get(ENV_DATA_DIR):
        data_dir = Path(env)
    else:
        data_dir = Path.home() / DEFAULT_DIR_NAME

    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


def get_wiki_dir() -> Path:
    """Return the wiki directory."""
    wiki_dir = get_data_dir() / "wiki"
    wiki_dir.mkdir(parents=True, exist_ok=True)
    return wiki_dir


def get_archive_dir() -> Path:
    """Return the archive directory."""
    archive_dir = get_data_dir() / "archive"
    archive_dir.mkdir(parents=True, exist_ok=True)
    return archive_dir


def get_db_path() -> Path:
    """Return the path to the SQLite database."""
    return get_data_dir() / "_meta.db"
