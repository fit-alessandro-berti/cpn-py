"""Pure helpers for the Streamlit CPN visualizer (no Streamlit dependency)."""

import inspect

DEFAULT_TRANSITION_ANIMATION_MS = 500
MIN_TRANSITION_ANIMATION_MS = 50
MAX_TRANSITION_ANIMATION_MS = 5000
FAST_BATCH_MAX_ITERATIONS = 10_000
MIN_PHASE_MS = 20
DEFAULT_PHASE_GAP_RATIO = 25 / 425
DEFAULT_STAGGER_RATIO = 0.1
ANIMATION_START_BUFFER_MS = 75
MAX_ADVANCES_PER_RUN = 50
STOP_POLL_MS = 50

BATCH_TERMINAL = frozenset({"stopped", "done", "deadlock", "idle", "error"})


def batch_status_level(status: str) -> str:
    """Map batch status text to Streamlit notification level."""
    if status == "Stopped":
        return "warning"
    if "Deadlock" in status or status.startswith("Error"):
        return "error"
    if status.startswith("Finished"):
        return "success"
    return "info"


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


def _arc_phase_end(arcs: list[dict], phase_start: int, phase_ms: int, stagger_ms: int) -> int:
    end = phase_start
    for entry in arcs:
        count = max(1, entry.get("count") or 1)
        end = max(end, phase_start + phase_ms + (count - 1) * stagger_ms)
    return end


def animation_wait_ms(firing_info: dict, timings: dict[str, int]) -> int:
    """Mirror JS totalDuration for in/out arc animation."""
    in_arcs = firing_info.get("in") or []
    out_arcs = firing_info.get("out") or []
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
