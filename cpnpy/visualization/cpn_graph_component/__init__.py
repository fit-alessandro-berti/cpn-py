"""Streamlit custom component: interactive CPN graph (vis-network)."""

from __future__ import annotations

import json
from pathlib import Path

import streamlit.components.v1 as components

_COMPONENT_DIR = Path(__file__).resolve().parent

_cpn_graph = components.declare_component(
    "cpn_graph",
    path=str(_COMPONENT_DIR),
)


def cpn_graph(
    graph_data: dict,
    *,
    height: int = 800,
    key: str | None = None,
) -> str | None:
    """
    Render the CPN graph. Returns a transition name when the user clicks an
    enabled (green) transition in Step sync mode, otherwise None.
    """
    value = _cpn_graph(
        graph_data_json=json.dumps(graph_data),
        height=int(height),
        key=key,
        default=None,
    )
    if value is None or value == "":
        return None
    return str(value)
