#!/usr/bin/env python3
"""Format Jama item data into various output formats."""

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class ItemData:
    """Normalized item data for formatting."""

    doc_key: str
    name: str
    fields: dict[str, Any]
    path: str | None = None
    url: str | None = None


class Formatter(ABC):
    """Base class for item formatters."""

    @abstractmethod
    def format_item(self, item: ItemData, indent: int = 0) -> list[str]:
        """Format a single item."""
        pass

    @abstractmethod
    def format_container(self, name: str, doc_key: str, indent: int) -> list[str]:
        """Format a container/header."""
        pass


class TreeFormatter(Formatter):
    """ASCII tree format."""

    def format_item(self, item: ItemData, indent: int = 0) -> list[str]:
        """Format item in ASCII tree style."""
        lines = [f"{'  ' * indent}└── {item.doc_key}: {item.name}"]
        for field_name, field_value in item.fields.items():
            lines.append(f"{'  ' * (indent + 1)}    {field_name}: {str(field_value)[:80]}")
        return lines

    def format_container(self, name: str, doc_key: str, indent: int) -> list[str]:
        """Format container in ASCII tree style."""
        prefix = "├── " if indent > 0 else ""
        return [f"{'  ' * indent}{prefix}[{doc_key}] {name}"]


class PathFormatter(Formatter):
    """Path prefix format."""

    def format_item(self, item: ItemData, indent: int = 0) -> list[str]:
        """Format item with path prefix."""
        path_prefix = f"[{item.path}] " if item.path else ""
        lines = [f"{path_prefix}{item.doc_key}: {item.name}"]
        for field_name, field_value in item.fields.items():
            field_value_str = str(field_value).replace("\n", " ")
            lines.append(f"@{field_name}: {field_value_str}")
        lines.append("")
        return lines

    def format_container(self, name: str, doc_key: str, indent: int) -> list[str]:
        """Containers are not shown in path format."""
        return []


class NestedFormatter(Formatter):
    """Markdown nested sections format."""

    def format_item(self, item: ItemData, indent: int = 0) -> list[str]:
        """Format item as nested Markdown sections."""
        level = indent + 2
        lines = [f"{'#' * level} {item.doc_key}: {item.name}"]
        if item.path:
            lines.append(f"Path: {item.path}")
        lines.append("")
        for field_name, field_value in item.fields.items():
            lines.append(f"{'#' * (level + 1)} {field_name}")
            lines.append(f"{field_value}")
            lines.append("")
        if item.url:
            lines.append(f"{'#' * (level + 1)} URL")
            lines.append(f"{item.url}")
            lines.append("")
        return lines

    def format_container(self, name: str, doc_key: str, indent: int) -> list[str]:
        """Format container as Markdown header."""
        return [f"{'#' * (indent + 2)} {doc_key}: {name}", ""]


class JsonFormatter(Formatter):
    """JSON structured format."""

    def format_item(self, item: ItemData, indent: int = 0) -> list[str]:
        """Format item as JSON."""
        data = {
            "doc_key": item.doc_key,
            "name": item.name,
        }
        data.update(item.fields)
        if item.path:
            data["path"] = item.path
        if item.url:
            data["url"] = item.url
        return [json.dumps(data, ensure_ascii=False, indent=2)]

    def format_container(self, name: str, doc_key: str, indent: int) -> list[str]:
        """Containers are not shown in JSON format."""
        return []


class FlatFormatter(Formatter):
    """Flat document format with separators."""

    def format_item(self, item: ItemData, indent: int = 0) -> list[str]:
        """Format item as flat document."""
        lines = [f"# {item.doc_key}: {item.name}"]
        if item.path:
            lines.append(f"Path: {item.path}")
        for field_name, field_value in item.fields.items():
            lines.append(f"## {field_name}")
            lines.append(f"{field_value}")
            lines.append("")
        lines.append("-" * 60)
        return lines

    def format_container(self, name: str, doc_key: str, indent: int) -> list[str]:
        """Containers are not shown in flat format."""
        return []


def get_formatter(format_type: str) -> Formatter:
    """Get a formatter instance by type name."""
    formatters = {
        "tree": TreeFormatter(),
        "path": PathFormatter(),
        "nested": NestedFormatter(),
        "json": JsonFormatter(),
        "flat": FlatFormatter(),
    }
    return formatters.get(format_type, PathFormatter())
