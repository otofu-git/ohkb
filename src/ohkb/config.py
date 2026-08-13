"""Configuration and path management."""

from __future__ import annotations

import os
from pathlib import Path

from ohkb.pathutil import confined_path

ENV_DATA_DIR = "OHKB_DIR"
DEFAULT_DIR_NAME = ".ohkb"


def get_data_dir() -> Path:
    """Return the canonical ohkb data directory, creating it if needed."""
    if env := os.environ.get(ENV_DATA_DIR):
        configured = Path(env).expanduser()
    else:
        configured = Path.home() / DEFAULT_DIR_NAME
    configured.mkdir(parents=True, exist_ok=True)
    return configured.resolve()


def _get_subdir(name: str) -> Path:
    directory = confined_path(get_data_dir(), name)
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def get_wiki_dir() -> Path:
    """Return the confined wiki directory."""
    return _get_subdir("wiki")


def get_archive_dir() -> Path:
    """Return the confined archive directory."""
    return _get_subdir("archive")


def get_sources_dir() -> Path:
    """Return the confined immutable raw sources directory."""
    return _get_subdir("sources")


def get_db_path() -> Path:
    """Return the confined SQLite database path."""
    return confined_path(get_data_dir(), "_meta.db")


def get_log_path() -> Path:
    """Return the confined append-only activity log path."""
    return confined_path(get_data_dir(), "log.md")


def get_agent_schema_path() -> Path:
    """Return the confined agent workflow hint path."""
    return confined_path(get_data_dir(), "AGENTS.ohkb.md")
