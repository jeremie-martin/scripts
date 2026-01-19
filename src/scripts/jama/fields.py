#!/usr/bin/env python3
"""Field name resolution and value formatting utilities for Jama items."""

from typing import Any

FIELD_ALIASES = {
    "name": ["name", "title"],
    "description": ["description", "desc"],
    "rationale": ["rationale", "rationale$171"],
    "acceptance_criteria": ["acceptance_criteria", "acceptance_criteria$171", "ac", "AC"],
    "status": ["status"],
    "di_classification": ["di_classification", "di_classification$171", "di", "classification"],
    "no_downstream_di_required": ["no_downstream_di_required", "no_downstream_di_required$171", "no_di_required"],
    "globalId": ["globalId", "gid"],
    "createdDate": ["createdDate", "created"],
    "test_inputs": ["test_inputs", "inputs"],
    "initial_conditions": ["initial_conditions", "preconditions"],
    "test_outputs": ["test_outputs", "outputs"],
    "assumptions__constraints": ["assumptions__constraints", "assumptions"],
    "data_collection_actions": ["data_collection_actions", "actions"],
}


def get_field_aliases_help() -> str:
    """Generate help text for field aliases."""
    lines = ["Field aliases (can use actual Jama keys or these aliases):"]
    for canonical, aliases in FIELD_ALIASES.items():
        alias_str = ", ".join(aliases)
        lines.append(f"  {canonical}: {alias_str}")
    return "\n".join(lines)


def resolve_field_value(value: Any, field_info: dict) -> str:
    """Resolve a field value, converting enum IDs to human-readable names."""
    if value is None:
        return ""

    if isinstance(value, bool):
        return "True" if value else "False"

    if isinstance(value, list):
        enum_values = field_info.get("enum_values", {})
        if enum_values:
            resolved = []
            for item in value:
                if isinstance(item, int):
                    str_item = str(item)
                    resolved.append(enum_values.get(str_item, str_item))
                else:
                    resolved.append(str(item))
            return ", ".join(resolved)
        return ", ".join(str(v) for v in value)

    if isinstance(value, int):
        enum_values = field_info.get("enum_values", {})
        if enum_values:
            str_value = str(value)
            if str_value in enum_values:
                return enum_values[str_value]

    return str(value)


def resolve_field_name(field_input: str, item_fields: dict) -> str | None:
    """Resolve a field input to an actual Jama field name."""
    field_input_lower = field_input.lower()

    for canonical_name, aliases in FIELD_ALIASES.items():
        if field_input_lower in [a.lower() for a in aliases]:
            for actual_field_name, field_info in item_fields.items():
                if field_info.get("base_name") == canonical_name:
                    return actual_field_name

    for actual_field_name, field_info in item_fields.items():
        base_name = field_info.get("base_name", actual_field_name)
        if base_name.lower() == field_input_lower or actual_field_name.lower() == field_input_lower:
            return actual_field_name

    return None
