"""Canonical layout of factory state inside a target repo."""

from pathlib import Path


def factory_root(repo):
    return Path(repo) / ".factory"


def items_dir(repo):
    return factory_root(repo) / "items"


def item_dir(repo, item_id):
    return items_dir(repo) / item_id


def ledgers_dir(repo):
    return factory_root(repo) / "ledgers"


def config_path(repo):
    return factory_root(repo) / "config.json"


def docs_root(repo):
    return Path(repo) / "docs" / "factory"
