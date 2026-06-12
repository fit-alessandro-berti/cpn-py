"""Pure helpers for the Streamlit CPN visualizer (no Streamlit dependency)."""

import json
import inspect
import re
from dataclasses import dataclass
from typing import Callable, Literal

from cpnpy.cpn.cpn_imp import CPN, Marking, Place, Transition
from cpnpy.cpn.parser import InputArcParser

DEFAULT_TRANSITION_ANIMATION_MS = 500
MIN_TRANSITION_ANIMATION_MS = 50
MAX_TRANSITION_ANIMATION_MS = 5000
FAST_BATCH_MAX_ITERATIONS = 10_000
MIN_PHASE_MS = 20
DEFAULT_PHASE_GAP_RATIO = 25 / 425
DEFAULT_STAGGER_RATIO = 0.1
ANIMATION_START_BUFFER_MS = 75
MAX_ADVANCES_PER_RUN = 50
FAST_BATCH_ADVANCES_PER_RUN = 5
STOP_POLL_MS = 50
MAX_ANIMATED_TOKENS = 5
GUARD_EXTERNAL_MAX_LEN = 48
GUARD_EXTERNAL_MAX_LEN_LARGE = 32

BATCH_TERMINAL = frozenset({"stopped", "done", "deadlock", "idle", "error"})


@dataclass(frozen=True)
class MonitorSpec:
    name: str
    slug: str
    predicate: Callable
    before: bool
    transition_name: str | None
    default_enabled: bool


def slugify_monitor_name(name: str) -> str:
    slug = re.sub(r"[^\w]+", "_", name.strip().lower()).strip("_")
    return slug or "monitor"


def enabled_transition_names(transitions) -> frozenset[str]:
    return frozenset(t.name for t in transitions)


def evaluate_monitors(
    monitors,
    *,
    phase: Literal["before", "after"],
    cpn: CPN,
    marking: Marking,
    pending_transition: str | None,
    enabled_names: frozenset[str],
    enabled_slugs: frozenset[str],
) -> list[str]:
    want_before = phase == "before"
    triggered: list[str] = []
    for m in monitors:
        if m.before != want_before or m.slug not in enabled_slugs:
            continue
        if m.transition_name is not None:
            if want_before and m.transition_name not in enabled_names:
                continue
            if not want_before and m.transition_name != pending_transition:
                continue
        if m.predicate(cpn, marking):
            triggered.append(m.name)
    return triggered


def monitor_batch_status_message(names: list[str]) -> str:
    return f"Stopped (monitors: {', '.join(names)})"


def format_simulation_error(exc: BaseException) -> str:
    """Single-line simulation error for sidebar status (type + message)."""
    return f"{type(exc).__name__}: {exc}"


def format_simulation_metrics_row(clock: int, firings: int, enabled: int) -> str:
    """Monospace metrics block for sidebar: clock, firings, enabled count."""
    return (
        f"Clock:     {clock}\n"
        f"Firings:   {firings}\n"
        f"Enabled:   {enabled}"
    )


def validate_net_for_simulation(cpn: CPN, marking: Marking) -> list[str]:
    """
    Check CPN structure and marking before simulation.
    Returns a list of human-readable problems (empty when valid).
    """
    errors: list[str] = []
    place_names = [p.name for p in cpn.places]
    transition_names = [t.name for t in cpn.transitions]

    if len(place_names) != len(set(place_names)):
        errors.append("Duplicate place names detected.")
    if len(transition_names) != len(set(transition_names)):
        errors.append("Duplicate transition names detected.")

    place_by_name = {p.name: p for p in cpn.places}
    transition_by_name = {t.name: t for t in cpn.transitions}

    for pname in marking._marking:
        if pname not in place_by_name:
            errors.append(f"Marking references unknown place {pname!r}.")

    for place in cpn.places:
        for tok in marking.get_multiset(place.name).tokens:
            if not place.colorset.is_member(tok.value):
                errors.append(
                    f"Token {tok.value!r} in place {place.name!r} is not a member of "
                    f"{place.colorset}."
                )

    arc_parser = InputArcParser()
    for arc in cpn.arcs:
        src, tgt = arc.source, arc.target
        if isinstance(src, Place) and isinstance(tgt, Transition):
            if src.name not in place_by_name:
                errors.append(
                    f"In-arc {src.name!r} -> {tgt.name!r} references unknown place."
                )
            if tgt.name not in transition_by_name:
                errors.append(
                    f"In-arc {src.name!r} -> {tgt.name!r} references unknown transition."
                )
            try:
                arc_parser.parse(arc.expression)
            except ValueError as e:
                errors.append(
                    f"In-arc {src.name!r} -> {tgt.name!r} ({arc.expression!r}): {e}"
                )
        elif isinstance(src, Transition) and isinstance(tgt, Place):
            if src.name not in transition_by_name:
                errors.append(
                    f"Out-arc {src.name!r} -> {tgt.name!r} references unknown transition."
                )
            if tgt.name not in place_by_name:
                errors.append(
                    f"Out-arc {src.name!r} -> {tgt.name!r} references unknown place."
                )
        else:
            errors.append(
                f"Arc {src.name!r} -> {tgt.name!r} must connect place to transition "
                f"or transition to place."
            )

    for transition in cpn.transitions:
        input_vars: set[str] = set()
        for arc in cpn.get_input_arcs(transition):
            try:
                parsed = arc_parser.parse(arc.expression)
                input_vars.add(parsed.variable)
            except ValueError:
                continue
        for var in transition.variables:
            if var not in input_vars:
                errors.append(
                    f"Transition {transition.name!r} declares variable {var!r} "
                    f"but no input arc binds it."
                )

    return errors


def raise_if_invalid_net(cpn: CPN, marking: Marking) -> None:
    """Raise ValueError listing every net/marking problem."""
    errors = validate_net_for_simulation(cpn, marking)
    if errors:
        bullet_list = "\n".join(f"- {msg}" for msg in errors)
        raise ValueError(f"Invalid CPN setup:\n{bullet_list}")


def batch_status_level(status: str) -> str:
    """Map batch status text to Streamlit notification level."""
    if status.startswith("Stopped (monitors:"):
        return "success"
    if status == "Stopped":
        return "warning"
    if "Deadlock" in status or status.startswith("Error") or "Simulation error" in status:
        return "error"
    if status.startswith("Finished"):
        return "success"
    return "info"


def status_entry_fingerprint(message: str) -> str:
    """Normalize status text for dismiss fingerprint comparison."""
    return message.strip()


def is_status_dismissed(
    dedup_id: str,
    message: str,
    dismissed: dict[str, str],
) -> bool:
    return dismissed.get(dedup_id) == status_entry_fingerprint(message)


def apply_status_dismiss(
    dedup_id: str,
    message: str,
    dismissed: dict[str, str],
) -> dict[str, str]:
    updated = dict(dismissed)
    updated[dedup_id] = status_entry_fingerprint(message)
    return updated


def clear_status_dismiss(
    dedup_id: str,
    dismissed: dict[str, str],
) -> dict[str, str]:
    updated = dict(dismissed)
    updated.pop(dedup_id, None)
    return updated


LARGE_GRAPH_NODE_THRESHOLD = 50

LAYOUT_STRATEGY_FORCE = "force"
LAYOUT_STRATEGY_FLOW_LR = "flow_lr"
LAYOUT_STRATEGY_CLUSTER = "cluster"
LAYOUT_STRATEGY_LAYERED_LR = "layered_lr"
LAYOUT_STRATEGY_CHOICES = (
    LAYOUT_STRATEGY_FORCE,
    LAYOUT_STRATEGY_FLOW_LR,
    LAYOUT_STRATEGY_CLUSTER,
    LAYOUT_STRATEGY_LAYERED_LR,
)
DEFAULT_LAYOUT_STRATEGY = LAYOUT_STRATEGY_FORCE
DEFAULT_SPACING_PCT = 100
MIN_SPACING_PCT = 50
MAX_SPACING_PCT = 500
PLACE_LABEL_FONT_SIZE_PX = 14
PLACE_LABEL_MAX_WIDTH_PX = 280
PLACE_LABEL_CHAR_WIDTH_PX = 8
PLACE_LABEL_LINE_HEIGHT_PX = 18
PLACE_LABEL_PAD_X_PX = 16
PLACE_LABEL_PAD_Y_PX = 12
PLACE_ELLIPSE_HEIGHT_FACTOR = 3
BASE_SPREAD = 1.25
PLACE_NODE_SIZE = 35


def _dotted_name_lines(name: str) -> list[str]:
    """Split a dotted id into display lines; wrap long segments."""
    parts = [p for p in str(name).split(".") if p]
    if not parts:
        return [str(name)]
    max_chars = max(1, PLACE_LABEL_MAX_WIDTH_PX // PLACE_LABEL_CHAR_WIDTH_PX)
    lines: list[str] = []
    for part in parts:
        while len(part) > max_chars:
            lines.append(part[:max_chars])
            part = part[max_chars:]
        if part:
            lines.append(part)
    return lines


def format_place_graph_label(place_name: str) -> str:
    """HTML label for vis-network place ellipse (bold; \\n between lines)."""
    lines = _dotted_name_lines(place_name)
    if not lines:
        return f"<b>{place_name}</b>"
    # vis-network html multi-font only supports <b>/<i>/<code>; newlines use \\n.
    return "\n".join(f"<b>{line}</b>" for line in lines)


def format_transition_graph_label(trans_name: str, *, has_action: bool) -> str:
    """HTML label for transition box: dotted name lines, optional action line."""
    lines = _dotted_name_lines(trans_name)
    if not lines:
        name_part = f"<b>{trans_name}</b>"
    else:
        name_part = "\n".join(f"<b>{line}</b>" for line in lines)
    suffix = "<code>action</code>" if has_action else " "
    return name_part + "\n" + suffix


def estimate_place_ellipse_size(place_name: str) -> tuple[int, int]:
    """Full width/height in px for vis-network ellipse from label text."""
    lines = _dotted_name_lines(place_name)
    if not lines:
        lines = [""]
    max_line_len = max(len(line) for line in lines)
    text_w = min(
        PLACE_LABEL_MAX_WIDTH_PX,
        max_line_len * PLACE_LABEL_CHAR_WIDTH_PX,
    )
    text_h = len(lines) * PLACE_LABEL_LINE_HEIGHT_PX
    min_dim = PLACE_NODE_SIZE * 2
    width = max(min_dim, text_w + PLACE_LABEL_PAD_X_PX)
    height = max(min_dim, text_h + PLACE_LABEL_PAD_Y_PX) * PLACE_ELLIPSE_HEIGHT_FACTOR
    return width, height


def resolve_layout_strategy(user_choice: str) -> str:
    """Map sidebar choice to vis-network strategy."""
    key = (user_choice or "").strip().lower()
    if key in (
        LAYOUT_STRATEGY_FLOW_LR,
        LAYOUT_STRATEGY_CLUSTER,
        LAYOUT_STRATEGY_LAYERED_LR,
    ):
        return key
    if key == "grid":
        return LAYOUT_STRATEGY_CLUSTER
    return LAYOUT_STRATEGY_FORCE


def spacing_pct_to_spread_factor(spacing_pct: int) -> float:
    pct = max(MIN_SPACING_PCT, min(MAX_SPACING_PCT, int(spacing_pct)))
    return BASE_SPREAD * (pct / 100.0)


def arc_edge_id(source: str, target: str, arc_index: int) -> str:
    """Unique vis-network edge id; CPN nets may have parallel arcs on the same pair."""
    return f"{source}|{target}|{arc_index}"


def hcpn_cluster_key(node_id: str, *, depth: int | None = None) -> str:
    """HCPN module key for layout grouping (mirrored in cpn_graph_component/index.html)."""
    parts = [p for p in str(node_id).split(".") if p]
    if not parts:
        return str(node_id)
    if depth == 1:
        return parts[0]
    if depth is not None and depth > 0:
        return ".".join(parts[: min(depth, len(parts))])
    if len(parts) <= 1:
        return parts[0]
    return ".".join(parts[:-1])


def compute_graph_layout(
    node_count: int,
    edge_count: int,
    *,
    strategy: str = DEFAULT_LAYOUT_STRATEGY,
    spacing_pct: int = DEFAULT_SPACING_PCT,
) -> dict:
    """Layout hints for the vis-network component."""
    resolved = resolve_layout_strategy(strategy)
    spacing = max(MIN_SPACING_PCT, min(MAX_SPACING_PCT, int(spacing_pct)))
    spread_factor = spacing_pct_to_spread_factor(spacing)
    large = node_count >= LARGE_GRAPH_NODE_THRESHOLD
    module_cluster_depth = (
        1
        if large
        and resolved in (LAYOUT_STRATEGY_FLOW_LR, LAYOUT_STRATEGY_LAYERED_LR)
        else None
    )
    return {
        "strategy": resolved,
        "spacing_pct": spacing,
        "spread_factor": spread_factor,
        "large": large,
        "module_cluster_depth": module_cluster_depth,
        "suppress_external_guards": large,
        "stabilization_iterations": min(2000, max(300, node_count * 10)),
        "fit_on_stabilized": resolved == LAYOUT_STRATEGY_FORCE,
        "node_count": node_count,
        "edge_count": edge_count,
    }


def get_action_source(action) -> str:
    """Return displayable action source for a transition action."""
    if not action:
        return ""
    if isinstance(action, str):
        return action
    try:
        return inspect.getsource(action)
    except (OSError, TypeError):
        return str(action)


def animation_draw_count(raw_count: int) -> int:
    """Circles to animate on one arc (1 when badge mode, else up to MAX_ANIMATED_TOKENS)."""
    count = max(1, int(raw_count) if raw_count else 1)
    if count > MAX_ANIMATED_TOKENS:
        return 1
    return count


def normalize_animation_arcs(arcs: list[dict]) -> list[dict]:
    """Add draw_count / badge_count for graph animation; preserve actual count."""
    normalized: list[dict] = []
    for entry in arcs or []:
        arc = entry.get("arc") or ""
        count = max(1, int(entry.get("count") or 1))
        draw_count = animation_draw_count(count)
        item: dict = {"arc": arc, "count": count, "draw_count": draw_count}
        if count > MAX_ANIMATED_TOKENS:
            item["badge_count"] = count
        normalized.append(item)
    return normalized


def format_guard_external_label(guard_expr: str, *, max_len: int = GUARD_EXTERNAL_MAX_LEN) -> str:
    """One-line guard preview for transition overlay above the box."""
    if not guard_expr:
        return ""
    text = " ".join(str(guard_expr).split())
    if len(text) <= max_len:
        return text
    return text[:max_len] + "..."


def compute_animation_timings(transition_ms: int) -> dict[str, int]:
    gap = max(1, round(transition_ms * DEFAULT_PHASE_GAP_RATIO))
    phase = max(MIN_PHASE_MS, (transition_ms - gap) // 2)
    stagger = max(5, round(phase * DEFAULT_STAGGER_RATIO))
    return {
        "transition_ms": transition_ms,
        "phase_ms": phase,
        "gap_ms": gap,
        "stagger_ms": stagger,
    }


def _arc_draw_count(entry: dict) -> int:
    if "draw_count" in entry:
        return max(1, int(entry["draw_count"]))
    return animation_draw_count(entry.get("count") or 1)


def _arc_phase_end(arcs: list[dict], phase_start: int, phase_ms: int, stagger_ms: int) -> int:
    end = phase_start
    for entry in arcs:
        draw_count = _arc_draw_count(entry)
        end = max(end, phase_start + phase_ms + (draw_count - 1) * stagger_ms)
    return end


def animation_wait_ms(firing_info: dict, timings: dict[str, int]) -> int:
    """Mirror JS totalDuration for in/out arc animation."""
    in_arcs = normalize_animation_arcs(firing_info.get("in") or [])
    out_arcs = normalize_animation_arcs(firing_info.get("out") or [])
    if not in_arcs and not out_arcs:
        return 0
    phase_ms = timings["phase_ms"]
    gap_ms = timings["gap_ms"]
    stagger_ms = timings["stagger_ms"]
    in_end = _arc_phase_end(in_arcs, 0, phase_ms, stagger_ms)
    gap = gap_ms if (in_arcs and out_arcs) else 0
    out_start = in_end + gap
    return _arc_phase_end(out_arcs, out_start, phase_ms, stagger_ms)


def batch_step_logic(
    *,
    batch_mode: str,
    batch_max_steps: int,
    batch_target_time: int,
    batch_auto_advance: bool,
    batch_stop_requested: bool,
    batch_firings: int,
    global_clock: int,
    enabled_name: str | None,
) -> str:
    """Pure decision for one batch macro-step (advance/deadlock handled by caller)."""
    if batch_stop_requested:
        return "stopped"
    if batch_mode == "time" and global_clock >= batch_target_time:
        return "done"
    if batch_mode == "steps" and batch_max_steps > 0 and batch_firings >= batch_max_steps:
        return "done"
    if enabled_name is not None:
        return "fired"
    if batch_mode == "time" or batch_auto_advance:
        return "need_advance"
    return "idle"


LAYOUT_FILE_VERSION = 1


def graph_layout_storage_key(node_ids: list[str]) -> str:
    """FNV-1a key for localStorage; sorted IDs (matches cpn_graph_component/index.html)."""
    joined = "\0".join(sorted(node_ids))
    h = 2166136261
    for ch in joined:
        h ^= ord(ch)
        h = (h * 16777619) & 0xFFFFFFFF
    return f"cpn_v4_{h:x}"


def build_layout_file_payload(positions: dict) -> dict:
    """Export JSON shape: version + positions only."""
    return {"version": LAYOUT_FILE_VERSION, "positions": positions}


def parse_layout_file_json(raw: str) -> dict[str, dict]:
    """Parse layout file; returns positions map. Raises ValueError on invalid input."""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("Layout file must be a JSON object.")
    if data.get("version") != LAYOUT_FILE_VERSION:
        raise ValueError(f"Unsupported layout version (expected {LAYOUT_FILE_VERSION}).")
    positions = data.get("positions")
    if not isinstance(positions, dict):
        raise ValueError("Layout file must include a positions object.")
    out: dict[str, dict] = {}
    for node_id, coords in positions.items():
        if not isinstance(node_id, str) or not isinstance(coords, dict):
            continue
        x, y = coords.get("x"), coords.get("y")
        if not isinstance(x, (int, float)) or not isinstance(y, (int, float)):
            continue
        out[node_id] = {"x": float(x), "y": float(y)}
    return out


def apply_imported_positions(
    node_ids: list[str],
    existing: dict | None,
    imported: dict,
) -> dict[str, dict]:
    """Merge imported coords for known ids; ignore unknown ids; keep others from existing."""
    merged = dict(existing or {})
    for node_id in node_ids:
        if node_id in imported:
            merged[node_id] = imported[node_id]
    return merged
