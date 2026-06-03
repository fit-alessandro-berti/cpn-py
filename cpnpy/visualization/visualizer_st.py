import copy
import time
from typing import Callable

import streamlit as st

from cpnpy.cpn.cpn_imp import CPN, Marking, EvaluationContext
from cpnpy.simulation.simu import get_enabled_transitions
from cpnpy.visualization.cpn_graph_component import cpn_graph
from cpnpy.visualization.visualizer_st_helpers import (
    ANIMATION_START_BUFFER_MS,
    BATCH_TERMINAL,
    DEFAULT_TRANSITION_ANIMATION_MS,
    FAST_BATCH_MAX_ITERATIONS,
    MAX_ADVANCES_PER_RUN,
    MAX_TRANSITION_ANIMATION_MS,
    MIN_TRANSITION_ANIMATION_MS,
    STOP_POLL_MS,
    animation_wait_ms,
    batch_status_level,
    batch_step_logic,
    compute_animation_timings,
    get_action_source,
)


class CPNStreamlitVisualizer:
    """
    Interactive Streamlit visualizer for Coloured Petri Nets using vis-network.

    Features:
    - Places and transitions with external labels; click for detail overlay.
    - Simulation step counter and configurable animation duration (default 500 ms).
    - Manual fire or batch simulation (Steps / Time modes, optional animation).
    - Two-phase firing animation: input arcs, then output arcs.
    - Physics disabled after layout; positions persist in localStorage.

    Batch state machine (batch_phase):
      idle    — no batch running
      fast    — atomic multi-step loop (no animation, no per-step rerun)
      advance — fire/advance one macro-step per cycle until a transition fires
      show    — display firing animation, then return to advance
    """

    def __init__(self, cpn: CPN, marking: Marking,
                 context: EvaluationContext | None = None,
                 session_key: str = "cpn_marking"):
        self.cpn = cpn
        self.context = context or EvaluationContext()
        self.session_key = session_key
        if self.session_key not in st.session_state:
            st.session_state[self.session_key] = marking
        self.marking = st.session_state[self.session_key]
        initial_key = f"{self.session_key}_initial"
        if initial_key not in st.session_state:
            st.session_state[initial_key] = copy.deepcopy(self.marking)
        self._init_session_defaults()
        self._has_timed_places = any(
            place.colorset.timed for place in self.cpn.places
        )

    def _k(self, suffix: str) -> str:
        return f"{self.session_key}_{suffix}"

    _STATUS_LEVEL_ORDER = ("error", "warning", "success", "info")

    def _notify(
        self,
        message: str,
        *,
        level: str = "info",
        dedup_id: str | None = None,
    ) -> None:
        """Persist a status line for the sidebar (survives reruns until cleared)."""
        store = st.session_state.setdefault(self._k("status_messages"), {})
        key = dedup_id or f"_{len(store)}"
        entry = {"message": message, "level": level}
        if store.get(key) == entry:
            return
        store[key] = entry

    def _clear_status_slot(self, dedup_id: str) -> None:
        store = st.session_state.get(self._k("status_messages"))
        if store:
            store.pop(dedup_id, None)

    def _clear_notifications(self) -> None:
        st.session_state.pop(self._k("status_messages"), None)
        prefix = self._k("toast_")
        for key in list(st.session_state.keys()):
            if isinstance(key, str) and key.startswith(prefix):
                st.session_state.pop(key, None)

    def _sync_derived_status_messages(self, *, batch_running: bool) -> None:
        """Refresh slots driven by session flags (not set inline in panels)."""
        if batch_running:
            self._clear_status_slot("step_idle")
            self._clear_status_slot("step_timed")

        error = st.session_state.get(self._k("sim_error"))
        if error:
            self._notify(
                f"Simulation error: {error}",
                level="error",
                dedup_id="sim_error",
            )
        else:
            self._clear_status_slot("sim_error")

        if (
            not batch_running
            and self._active_sidebar_panel(batch_running) == "manual"
            and st.session_state.get(self._k("manual_deadlock"))
        ):
            self._notify(
                f"Deadlock at time {self.marking.global_clock}",
                level="warning",
                dedup_id="deadlock",
            )
        else:
            self._clear_status_slot("deadlock")

        batch_status = st.session_state.get(self._k("batch_status"), "Idle")
        if not batch_running and batch_status not in ("Idle", "Running"):
            self._notify(
                batch_status,
                level=batch_status_level(batch_status),
                dedup_id="batch_status",
            )
        else:
            self._clear_status_slot("batch_status")

    def _render_status_messages(self) -> None:
        store = st.session_state.get(self._k("status_messages"))
        if not store:
            return
        st.markdown("**Status**")
        by_level = {level: [] for level in self._STATUS_LEVEL_ORDER}
        for item in store.values():
            level = item.get("level", "info")
            if level not in by_level:
                level = "info"
            by_level[level].append(item["message"])
        for level in self._STATUS_LEVEL_ORDER:
            widget = {
                "error": st.error,
                "warning": st.warning,
                "success": st.success,
                "info": st.info,
            }.get(level, st.info)
            for message in by_level.get(level, []):
                widget(message)

    def _init_session_defaults(self):
        if self._k("step_count") not in st.session_state:
            st.session_state[self._k("step_count")] = 0
        if self._k("anim_ms") not in st.session_state:
            st.session_state[self._k("anim_ms")] = DEFAULT_TRANSITION_ANIMATION_MS
        if self._k("batch_status") not in st.session_state:
            st.session_state[self._k("batch_status")] = "Idle"
        if self._k("batch_phase") not in st.session_state:
            st.session_state[self._k("batch_phase")] = "idle"
        if self._k("manual_auto_advance") not in st.session_state:
            st.session_state[self._k("manual_auto_advance")] = True
        if self._k("batch_running") not in st.session_state:
            st.session_state[self._k("batch_running")] = False
        if self._k("batch_ui_mode") not in st.session_state:
            st.session_state[self._k("batch_ui_mode")] = "steps"
        if self._k("sidebar_panel") not in st.session_state:
            st.session_state[self._k("sidebar_panel")] = "manual"

    def _active_sidebar_panel(self, batch_running: bool) -> str:
        if batch_running:
            return "batch"
        panel = st.session_state.get(self._k("sidebar_panel"), "manual")
        return panel if panel in ("manual", "batch") else "manual"

    def _select_sidebar_panel(self, panel: str) -> None:
        st.session_state[self._k("sidebar_panel")] = panel

    def _render_sidebar_panel_switch(self, batch_running: bool) -> None:
        panel = self._active_sidebar_panel(batch_running)
        col_manual, col_batch = st.columns(2)
        with col_manual:
            st.button(
                "Step",
                key=self._k("sidebar_panel_manual"),
                on_click=self._select_sidebar_panel,
                args=("manual",),
                disabled=batch_running,
                use_container_width=True,
                type="primary" if panel == "manual" else "secondary",
                help="Fire one transition at a time.",
            )
        with col_batch:
            st.button(
                "Batch",
                key=self._k("sidebar_panel_batch"),
                on_click=self._select_sidebar_panel,
                args=("batch",),
                use_container_width=True,
                type="primary" if panel == "batch" else "secondary",
                help="Automated run with Start / Stop batch.",
            )

    def _repair_batch_session(self) -> None:
        """Clear stale batch-running flags left by interrupted reruns or old sessions."""
        phase = st.session_state.get(self._k("batch_phase"), "idle")
        if phase != "idle":
            return
        if st.session_state.get(self._k("batch_running")):
            st.session_state[self._k("batch_running")] = False
        if st.session_state.get(self._k("batch_status")) == "Running":
            st.session_state[self._k("batch_status")] = "Idle"

    def _apply_graph_transition_pick(self, enabled_names: list[str]) -> None:
        """Apply transition chosen on the graph before the selectbox is drawn."""
        picked = st.session_state.pop(self._k("graph_pick_pending"), None)
        if (
            picked
            and self._active_sidebar_panel(self._batch_running()) == "manual"
            and picked in enabled_names
        ):
            st.session_state[self._k("select")] = picked

    def _handle_graph_component_pick(
        self, picked: str | None, enabled_names: list[str],
    ) -> None:
        """Store graph click for the next run (component renders after sidebar)."""
        if not picked:
            return
        if self._active_sidebar_panel(self._batch_running()) != "manual":
            return
        if picked not in enabled_names:
            return
        if st.session_state.get(self._k("select")) == picked:
            return
        st.session_state[self._k("graph_pick_pending")] = picked
        self._request_rerun()

    def _refresh_deadlock_flags(self, enabled_names: list[str]) -> None:
        if not enabled_names:
            return
        st.session_state.pop(self._k("manual_deadlock"), None)
        status = st.session_state.get(self._k("batch_status"), "")
        if isinstance(status, str) and status.startswith("Deadlock"):
            st.session_state[self._k("batch_status")] = "Idle"

    def _batch_running(self) -> bool:
        return bool(st.session_state.get(self._k("batch_running"), False))

    def _simulation_at_deadlock(self, enabled_names: list[str]) -> bool:
        if enabled_names:
            return False
        return bool(st.session_state.get(self._k("manual_deadlock")))

    def _render_batch_run_button(
        self,
        *,
        mode_key: str,
        max_steps: int,
        target_time: int,
        batch_animate: bool,
        auto_advance: bool,
        anim_ms: int,
        enabled_names: list[str],
    ) -> None:
        """One Streamlit widget key for Start and Stop so they never stack in the UI."""
        control_key = self._k("batch_control")
        if self._batch_running():
            animated = bool(st.session_state.get(self._k("batch_animate")))
            st.button(
                "Stop batch",
                key=control_key,
                on_click=self._request_batch_stop,
                disabled=not animated,
                use_container_width=True,
                type="primary",
                help=(
                    "Halts after the current firing animation completes "
                    "(checked about every 50 ms)."
                    if animated
                    else "Fast batch cannot be stopped mid-run. Wait for completion or refresh."
                ),
            )
            return

        at_deadlock = self._simulation_at_deadlock(enabled_names)
        start_disabled = (
            at_deadlock
            or (
                mode_key == "time"
                and target_time <= self.marking.global_clock
            )
        )
        start_help = "Disabled while a batch is running."
        if at_deadlock:
            start_help = (
                "Simulation is in deadlock (no enabled transitions and time cannot advance). "
                "Use Reset to initial state."
            )
        elif mode_key == "time" and target_time <= self.marking.global_clock:
            start_help = "Target time must be greater than the current global clock."
        if st.button(
            "Start batch",
            key=control_key,
            disabled=start_disabled,
            use_container_width=True,
            type="primary",
            help=start_help,
        ):
            if (
                not batch_animate
                and mode_key == "steps"
                and max_steps == 0
            ):
                self._notify(
                    "Unlimited fast batch may run long (10k iteration cap).",
                    level="warning",
                    dedup_id="batch_hint",
                )
            self._start_batch(
                mode_key, max_steps, target_time,
                batch_animate, auto_advance, int(anim_ms),
            )

    def _effective_anim_ms(self) -> int:
        if self._batch_running() and st.session_state.get(self._k("batch_animate")):
            return int(st.session_state.get(self._k("batch_anim_ms"), DEFAULT_TRANSITION_ANIMATION_MS))
        return int(st.session_state.get(self._k("anim_ms"), DEFAULT_TRANSITION_ANIMATION_MS))

    def _place_node(self, place, now: int) -> dict:
        ms = self.marking.get_multiset(place.name)
        avail = sum(1 for t in ms.tokens if t.timestamp <= now)
        future = sum(1 for t in ms.tokens if t.timestamp > now)
        is_timed = place.colorset.timed
        return {
            "id": place.name,
            "label": f"<b>{place.name}</b>",
            "type": "place",
            "shape": "circle",
            "size": 35,
            "font": {"multi": "html", "size": 14},
            "color": {
                "background": "#dce3ff",
                "border": "#5d78ff",
                "highlight": {"background": "#cbd5ff", "border": "#3b59ff"},
            },
            "corner_tr": place.colorset.name or "",
            "token_avail": avail,
            "token_future": future,
            "is_timed": is_timed,
            "colorset_name": place.colorset.name,
            "full_tokens": [
                {"value": repr(t.value), "timestamp": t.timestamp,
                 "is_avail": t.timestamp <= now}
                for t in ms.tokens
            ],
        }

    def _transition_node(
        self, trans, enabled_names: list[str], animating_transition: str | None,
    ) -> dict:
        enabled = (
            trans.name in enabled_names
            or trans.name == animating_transition
        )
        has_action = trans.action is not None
        label = f"<b>{trans.name}</b>\n" + ("<code>action</code>" if has_action else " ")
        delay = getattr(trans, "transition_delay", 0)
        guard = trans.guard_expr or ""
        return {
            "id": trans.name,
            "label": label,
            "type": "transition",
            "shape": "box",
            "size": 25,
            "font": {"multi": "html", "size": 14},
            "color": {
                "background": "#c8f7c5" if enabled else "#f8f9fa",
                "border": "#2ecc71" if enabled else "#adb5bd",
                "highlight": {
                    "background": "#a8e7a5" if enabled else "#e9ecef",
                    "border": "#27ae60" if enabled else "#6c757d",
                },
            },
            "external_top": guard,
            "external_bottom": f"@+ {delay}" if delay > 0 else "",
            "external_bl": str(trans.priority),
            "guard": guard,
            "delay": delay,
            "priority": trans.priority,
            "action_code": get_action_source(trans.action),
            "colorset_name": None,
            "full_tokens": None,
        }

    @staticmethod
    def _arc_edge(arc, connections: set[tuple[str, str]]) -> dict:
        src, tgt = arc.source.name, arc.target.name
        is_bi = (tgt, src) in connections
        return {
            "id": f"{src}|{tgt}",
            "from": src,
            "to": tgt,
            "label": str(arc.expression),
            "arrows": "to",
            "font": {"size": 12, "align": "top"},
            "color": {"color": "#999999", "inherit": False},
            "smooth": {"enabled": True, "type": "curvedCW", "roundness": 0.2} if is_bi else False,
            "is_curved": is_bi,
        }

    def _prepare_data(self, enabled_names: list[str],
                      animate_in: list[dict] | None = None,
                      animate_out: list[dict] | None = None,
                      animation_timings: dict[str, int] | None = None,
                      animating_transition: str | None = None):
        animate_in = animate_in or []
        animate_out = animate_out or []
        now = self.marking.global_clock
        nodes = [
            self._place_node(place, now)
            for place in self.cpn.places
        ]
        nodes.extend(
            self._transition_node(trans, enabled_names, animating_transition)
            for trans in self.cpn.transitions
        )

        connections = {(a.source.name, a.target.name) for a in self.cpn.arcs}
        edges = [self._arc_edge(arc, connections) for arc in self.cpn.arcs]

        timings = dict(
            animation_timings or compute_animation_timings(self._effective_anim_ms())
        )
        if animate_in or animate_out:
            timings["total_duration_ms"] = animation_wait_ms(
                {"in": animate_in, "out": animate_out}, timings,
            )
        return {
            "nodes": nodes,
            "edges": edges,
            "animate_in": animate_in,
            "animate_out": animate_out,
            "animation": timings,
            "enabled_names": enabled_names,
            "animating_transition": animating_transition,
            "sync_graph_select": (
                self._active_sidebar_panel(self._batch_running()) == "manual"
                and bool(enabled_names)
            ),
        }

    def fire(self, transition_name: str) -> dict:
        """Fire a transition; increment step_count on success."""
        st.session_state[self._k("sim_error")] = None
        try:
            trans = self.cpn.get_transition_by_name(transition_name)
            info = self.cpn.fire_transition(trans, self.marking, self.context)
            info["transition"] = transition_name
            st.session_state[self._k("step_count")] = st.session_state.get(self._k("step_count"), 0) + 1
            st.session_state[self._k("last_fired_name")] = transition_name
            st.session_state.pop(self._k("manual_deadlock"), None)
            return info
        except Exception as e:
            st.session_state[self._k("sim_error")] = str(e)
            return {"in": [], "out": []}

    def _advance_global_clock_once(self) -> bool:
        """Advance global clock once. Returns True if the clock moved."""
        st.session_state[self._k("sim_error")] = None
        try:
            before = self.marking.global_clock
            self.cpn.advance_global_clock(self.marking)
            return self.marking.global_clock != before
        except Exception as e:
            st.session_state[self._k("sim_error")] = str(e)
            return False

    def _coalesce_manual_time_advance(
        self, *, transitions_enabled: bool | None = None,
    ) -> None:
        if self._batch_running():
            return
        if not st.session_state.get(self._k("manual_auto_advance"), True):
            return
        if transitions_enabled is None:
            transitions_enabled = bool(
                get_enabled_transitions(self.cpn, self.marking, self.context)
            )
        if transitions_enabled:
            return

        for _ in range(MAX_ADVANCES_PER_RUN):
            if not self._advance_global_clock_once():
                st.session_state[self._k("manual_deadlock")] = True
                return
            if get_enabled_transitions(self.cpn, self.marking, self.context):
                st.session_state.pop(self._k("manual_deadlock"), None)
                return

        self._request_rerun()

    def _batch_step(self) -> tuple[str, dict]:
        enabled = get_enabled_transitions(self.cpn, self.marking, self.context)
        enabled_name = enabled[0].name if enabled else None
        mode = st.session_state.get(self._k("batch_mode"), "steps")
        auto = True if mode == "time" else st.session_state.get(self._k("batch_auto_advance"), True)

        result = batch_step_logic(
            batch_mode=mode,
            batch_max_steps=int(st.session_state.get(self._k("batch_max_steps"), 0)),
            batch_target_time=int(st.session_state.get(self._k("batch_target_time"), 0)),
            batch_auto_advance=auto,
            batch_stop_requested=bool(st.session_state.get(self._k("batch_stop_requested"), False)),
            batch_firings=int(st.session_state.get(self._k("batch_firings"), 0)),
            global_clock=self.marking.global_clock,
            enabled_name=enabled_name,
        )

        if result == "fired" and enabled_name:
            info = self.fire(enabled_name)
            if st.session_state.get(self._k("sim_error")):
                return "error", {}
            st.session_state[self._k("batch_firings")] = st.session_state.get(self._k("batch_firings"), 0) + 1
            return "fired", info

        if result == "need_advance":
            if not self._advance_global_clock_once():
                return "deadlock", {}
            return "advanced", {}

        return result, {}

    def _status_message(self, result: str) -> str:
        if result == "stopped":
            return "Stopped"
        if result == "error":
            err = st.session_state.get(self._k("sim_error"), "unknown")
            return f"Error: {err}"
        if result == "deadlock":
            return f"Deadlock at time {self.marking.global_clock}"
        if result == "idle":
            return f"Finished (idle at time {self.marking.global_clock})"
        if result == "done":
            mode = st.session_state.get(self._k("batch_mode"), "steps")
            if mode == "time":
                return f"Finished (time target @ {self.marking.global_clock})"
            n = st.session_state.get(self._k("batch_firings"), 0)
            return f"Finished ({n} transitions)"
        return "Finished"

    def _request_rerun(self) -> None:
        """Schedule a rerun; always pair with _flush_rerun before drawing widgets."""
        st.session_state[self._k("needs_rerun")] = True

    def _flush_rerun(self) -> None:
        """Rerun immediately if requested. Call only before sidebar or after graph-only pass."""
        if st.session_state.pop(self._k("needs_rerun"), False):
            st.rerun()

    def _request_batch_stop(self) -> None:
        st.session_state[self._k("batch_stop_requested")] = True

    def _abort_batch_if_stop_requested(self) -> bool:
        if st.session_state.get(self._k("batch_stop_requested")):
            st.session_state.pop(self._k("last_fired"), None)
            self._end_batch("Stopped", rerun=True)
            return True
        return False

    def _needs_show_animation_wait(self) -> bool:
        return (
            self._batch_running()
            and st.session_state.get(self._k("batch_animate"))
            and st.session_state.get(self._k("batch_phase")) == "show"
            and not st.session_state.get(self._k("show_sleep_complete"))
        )

    def _render_simulation_metrics(self, step_count: int, n_enabled: int) -> None:
        """Prominent global clock, firing count, and enabled transitions (core CPN state)."""
        clock_col, steps_col, enabled_col = st.columns(3)
        with clock_col:
            st.metric(
                "Clock",
                self.marking.global_clock,
                help="Global simulation time (@). Advances when timed tokens become ready or auto-advance runs.",
            )
        with steps_col:
            st.metric(
                "Firings",
                step_count,
                help="Successful transition firings since the last reset.",
            )
        with enabled_col:
            st.metric(
                "Enabled",
                n_enabled,
                help="Transitions that can fire at the current clock.",
            )

    def _render_batch_running_summary(self) -> None:
        mode_key = st.session_state.get(self._k("batch_mode"), "steps")
        max_steps = int(st.session_state.get(self._k("batch_max_steps"), 0))
        target_time = int(st.session_state.get(self._k("batch_target_time"), 0))
        auto_advance = bool(st.session_state.get(self._k("batch_auto_advance"), True))
        batch_animate = bool(st.session_state.get(self._k("batch_animate"), False))
        firings = int(st.session_state.get(self._k("batch_firings"), 0))
        clock = self.marking.global_clock
        anim = "on" if batch_animate else "off"

        if mode_key == "steps":
            if max_steps > 0:
                progress = f"{firings}/{max_steps} firings"
            else:
                progress = f"{firings} firings, clock {clock}"
            limit = str(max_steps) if max_steps > 0 else "unlimited"
            auto = "on" if auto_advance else "off"
            st.caption(
                f"**Running** · Steps · {progress} · max {limit} · "
                f"auto-advance {auto} · animate {anim}"
            )
        else:
            st.caption(
                f"**Running** · Time · {firings} firings · clock {clock} / "
                f"target {target_time} · animate {anim}"
            )

    def _render_batch_config(self, batch_running: bool) -> dict:
        """Batch mode and inputs (widgets disabled while running)."""
        saved_mode = st.session_state.get(self._k("batch_mode"), "steps")
        batch_mode = st.radio(
            "Mode",
            options=["Steps", "Time"],
            horizontal=True,
            key=self._k("batch_mode_ui"),
            disabled=batch_running,
        )

        max_steps = 0
        auto_advance = True
        target_time = self.marking.global_clock
        batch_animate = False

        if batch_running:
            mode_key = saved_mode
            max_steps = int(st.session_state.get(self._k("batch_max_steps"), 0))
            target_time = int(st.session_state.get(self._k("batch_target_time"), 0))
            auto_advance = bool(st.session_state.get(self._k("batch_auto_advance"), True))
            batch_animate = bool(st.session_state.get(self._k("batch_animate"), False))
        else:
            mode_key = "steps" if batch_mode == "Steps" else "time"
            prev_mode = st.session_state.get(self._k("batch_ui_mode"))
            if prev_mode and prev_mode != mode_key:
                self._clear_opposite_batch_widgets(mode_key)
            st.session_state[self._k("batch_ui_mode")] = mode_key

            if mode_key == "steps":
                max_steps = int(st.number_input(
                    "Max transitions (0 = unlimited)",
                    min_value=0,
                    value=10,
                    step=1,
                    key=self._k("batch_max_steps_ui"),
                ))
                auto_advance = st.checkbox(
                    "Advance clock when idle (batch)",
                    value=True,
                    key=self._k("batch_auto_advance_ui"),
                    help="During batch Steps mode, advance global time when no transition is enabled.",
                )
            else:
                ui_key = self._k("batch_target_ui")
                clock = self.marking.global_clock
                self._apply_batch_target_ui_refresh()
                if st.session_state.get(ui_key, 0) <= clock:
                    st.session_state[ui_key] = clock + 1
                target_time = int(st.number_input(
                    "Target time",
                    min_value=clock,
                    step=1,
                    key=ui_key,
                    help=(
                        "Run until global clock >= target (stops before firing at "
                        "exact target if already there)."
                    ),
                ))

            batch_animate = st.checkbox(
                "Animate each step",
                value=False,
                key=self._k("batch_animate_ui"),
            )

        return {
            "mode_key": mode_key,
            "max_steps": max_steps,
            "target_time": target_time,
            "batch_animate": batch_animate,
            "auto_advance": auto_advance,
        }

    def _run_show_animation_wait_after_graph(self, last_fired: dict) -> bool:
        """Paint graph once, then block for animation (iframe must stay mounted)."""
        if not self._needs_show_animation_wait():
            return False

        paint_key = self._k("show_frame_painted")
        if not st.session_state.get(paint_key):
            st.session_state[paint_key] = True
            self._request_rerun()
            return True

        st.session_state.pop(paint_key, None)

        if st.session_state.get(self._k("batch_stop_requested")):
            self._request_rerun()
            return True

        in_arcs = last_fired.get("in") or []
        out_arcs = last_fired.get("out") or []
        if in_arcs or out_arcs:
            timings = self._last_animation_timings
            wait_ms = animation_wait_ms(last_fired, timings) + ANIMATION_START_BUFFER_MS
            self._polled_sleep(wait_ms)

        if st.session_state.get(self._k("batch_stop_requested")):
            self._request_rerun()
            return True

        st.session_state[self._k("show_sleep_complete")] = True
        st.session_state.pop(self._k("last_fired"), None)
        self._request_rerun()
        return True

    def _polled_sleep(self, total_ms: int) -> None:
        elapsed = 0
        while elapsed < total_ms:
            if st.session_state.get(self._k("batch_stop_requested")):
                break
            time.sleep(STOP_POLL_MS / 1000)
            elapsed += STOP_POLL_MS

    def _end_batch(self, status: str, *, rerun: bool = False):
        mode = st.session_state.get(self._k("batch_mode"), "steps")
        st.session_state[self._k("batch_running")] = False
        st.session_state[self._k("batch_status")] = status
        st.session_state[self._k("batch_phase")] = "idle"
        st.session_state[self._k("batch_stop_requested")] = False
        st.session_state.pop(self._k("show_sleep_complete"), None)
        st.session_state.pop(self._k("show_frame_painted"), None)
        st.session_state[self._k("batch_ui_mode")] = mode
        if "Deadlock" in status:
            st.session_state[self._k("manual_deadlock")] = True
        if mode == "time":
            # Defer target-time widget update until before the widget is drawn.
            st.session_state[self._k("batch_target_ui_pending")] = True
        if rerun:
            self._request_rerun()
        if status not in ("Running", "Idle"):
            self._notify(
                status,
                level=batch_status_level(status),
                dedup_id="batch_status",
            )

    def _apply_batch_target_ui_refresh(self) -> None:
        """Apply a deferred target-time refresh (must run before number_input)."""
        if not st.session_state.pop(self._k("batch_target_ui_pending"), False):
            return
        ui_key = self._k("batch_target_ui")
        st.session_state[ui_key] = self.marking.global_clock + 1

    def _clear_batch_session(self):
        for suffix in (
            "batch_running", "batch_stop_requested", "batch_mode", "batch_max_steps",
            "batch_target_time", "batch_animate", "batch_auto_advance", "batch_firings",
            "batch_anim_ms", "batch_phase", "batch_fast_iterations",
        ):
            st.session_state.pop(self._k(suffix), None)
        st.session_state[self._k("batch_phase")] = "idle"
        st.session_state[self._k("batch_status")] = "Idle"

    def _reset_batch_ui_to_steps(self) -> None:
        """Align batch widgets with Steps mode after simulation reset."""
        st.session_state[self._k("batch_ui_mode")] = "steps"
        st.session_state.pop(self._k("batch_mode_ui"), None)
        st.session_state.pop(self._k("batch_target_ui"), None)
        st.session_state.pop(self._k("batch_target_ui_pending"), None)
        st.session_state.pop(self._k("batch_max_steps_ui"), None)
        st.session_state.pop(self._k("batch_auto_advance_ui"), None)
        st.session_state.pop(self._k("batch_animate_ui"), None)

    def _reset_simulation(self):
        st.session_state[self.session_key] = copy.deepcopy(
            st.session_state[f"{self.session_key}_initial"]
        )
        self.marking = st.session_state[self.session_key]
        st.session_state[self._k("step_count")] = 0
        st.session_state[self._k("anim_ms")] = DEFAULT_TRANSITION_ANIMATION_MS
        st.session_state.pop(self._k("sim_error"), None)
        st.session_state.pop(self._k("last_fired"), None)
        st.session_state.pop(self._k("last_fired_name"), None)
        st.session_state.pop(self._k("manual_auto_advance"), None)
        st.session_state.pop(self._k("select"), None)
        st.session_state.pop(self._k("anim_input"), None)
        st.session_state.pop(self._k("manual_deadlock"), None)
        self._end_batch("Idle")
        self._clear_batch_session()
        self._reset_batch_ui_to_steps()
        st.session_state.pop(self._k("needs_rerun"), None)
        st.session_state.pop(self._k("show_sleep_complete"), None)
        st.session_state.pop(self._k("show_frame_painted"), None)
        st.session_state.pop(self._k("run_drivers_after_sidebar"), None)
        st.session_state.pop(self._k("graph_pick_pending"), None)
        st.session_state[self._k("sidebar_panel")] = "manual"
        self._clear_notifications()

    def _fire_selected_transition(self) -> None:
        """Run before sidebar widgets on Fire click (on_click), like Stop batch."""
        name = st.session_state.get(self._k("select"))
        if not name:
            return
        st.session_state[self._k("last_fired")] = self.fire(name)

    def _render_manual_step_panel(
        self,
        *,
        enabled: bool,
        enabled_names: list[str],
    ) -> None:
        with st.container(border=True):
            st.markdown("**Step**")
            manual_auto_advance = st.checkbox(
                "Advance clock when idle",
                key=self._k("manual_auto_advance"),
                help="When nothing is enabled, advance global clock until a transition can fire.",
            )
            if not enabled:
                if not manual_auto_advance:
                    self._notify(
                        "No transitions enabled. Enable auto-advance or wait for timed tokens.",
                        level="info",
                        dedup_id="step_idle",
                    )
                elif self._has_timed_places:
                    self._notify(
                        "Timed tokens may need the clock to advance before firing.",
                        level="info",
                        dedup_id="step_timed",
                    )
                else:
                    self._notify(
                        "No transitions enabled at the current time.",
                        level="info",
                        dedup_id="step_idle",
                    )
            else:
                self._clear_status_slot("step_idle")
                self._clear_status_slot("step_timed")
                selected = st.selectbox(
                    "Enabled transitions",
                    options=enabled_names,
                    key=self._k("select"),
                )
                st.button(
                    "Fire selected transition",
                    key=self._k("fire"),
                    on_click=self._fire_selected_transition,
                    use_container_width=True,
                    type="primary",
                )

    def _render_batch_simulation_panel(
        self,
        *,
        batch_running: bool,
        anim_ms: int,
        enabled_names: list[str],
    ) -> None:
        with st.container(border=True):
            st.markdown("**Batch**")
            if batch_running:
                self._render_batch_running_summary()
            batch_params = self._render_batch_config(batch_running)
            self._render_batch_run_button(
                anim_ms=anim_ms,
                enabled_names=enabled_names,
                **batch_params,
            )
    def _sync_batch_mode_ui(self) -> None:
        """While batch is running, align the disabled mode radio with snapshotted batch_mode."""
        if not self._batch_running():
            return
        saved = st.session_state.get(self._k("batch_mode"), "steps")
        label = "Steps" if saved == "steps" else "Time"
        st.session_state[self._k("batch_mode_ui")] = label

    def _start_batch(self, mode: str, max_steps: int, target_time: int,
                     animate: bool, auto_advance: bool, anim_ms: int):
        st.session_state.pop(self._k("last_fired"), None)
        st.session_state.pop(self._k("sim_error"), None)
        self._clear_status_slot("batch_status")
        self._clear_status_slot("batch_validation")
        st.session_state.pop(self._k("show_sleep_complete"), None)
        st.session_state.pop(self._k("show_frame_painted"), None)
        st.session_state[self._k("batch_mode")] = mode
        st.session_state[self._k("batch_ui_mode")] = mode
        st.session_state[self._k("batch_max_steps")] = max_steps
        st.session_state[self._k("batch_target_time")] = target_time
        st.session_state[self._k("batch_animate")] = animate
        st.session_state[self._k("batch_auto_advance")] = auto_advance
        st.session_state[self._k("batch_anim_ms")] = anim_ms
        st.session_state[self._k("batch_firings")] = 0
        st.session_state[self._k("batch_fast_iterations")] = 0
        st.session_state[self._k("batch_stop_requested")] = False
        st.session_state[self._k("batch_running")] = True
        st.session_state[self._k("batch_status")] = "Running"
        st.session_state[self._k("sidebar_panel")] = "batch"

        if animate:
            st.session_state[self._k("batch_phase")] = "advance"
        else:
            st.session_state[self._k("batch_phase")] = "fast"
        st.session_state[self._k("run_drivers_after_sidebar")] = True

    def _clear_opposite_batch_widgets(self, mode_key: str) -> None:
        if mode_key == "steps":
            st.session_state.pop(self._k("batch_target_ui"), None)
            st.session_state.pop(self._k("batch_target_ui_pending"), None)
        else:
            st.session_state.pop(self._k("batch_max_steps_ui"), None)
            st.session_state.pop(self._k("batch_auto_advance_ui"), None)

    def _on_animated_batch_fired(self, info: dict) -> None:
        st.session_state[self._k("last_fired")] = info
        st.session_state[self._k("batch_phase")] = "show"
        st.session_state.pop(self._k("show_sleep_complete"), None)
        st.session_state.pop(self._k("show_frame_painted"), None)
        self._request_rerun()

    def _run_batch_advance_loop(
        self,
        *,
        expected_phase: str,
        require_animate: bool,
        on_fired: Callable[[dict], None] | None = None,
        track_iterations: bool = False,
    ) -> None:
        if not self._batch_running():
            return
        if bool(st.session_state.get(self._k("batch_animate"))) != require_animate:
            return
        if st.session_state.get(self._k("batch_phase")) != expected_phase:
            return

        if st.session_state.get(self._k("batch_stop_requested")):
            self._end_batch("Stopped", rerun=True)
            return

        iterations = (
            int(st.session_state.get(self._k("batch_fast_iterations"), 0))
            if track_iterations else 0
        )

        for _ in range(MAX_ADVANCES_PER_RUN):
            if require_animate and st.session_state.get(self._k("batch_stop_requested")):
                self._end_batch("Stopped", rerun=True)
                return
            if track_iterations and iterations >= FAST_BATCH_MAX_ITERATIONS:
                self._end_batch("Finished (iteration cap — partial)", rerun=True)
                return

            result, info = self._batch_step()

            if track_iterations:
                iterations += 1

            if result == "fired" and on_fired is not None:
                on_fired(info)
                return

            if result in BATCH_TERMINAL or result == "stopped":
                self._end_batch(self._status_message(result), rerun=True)
                return

        if track_iterations:
            st.session_state[self._k("batch_fast_iterations")] = iterations
        if self._batch_running():
            self._request_rerun()

    def _run_fast_batch_phase(self) -> None:
        self._run_batch_advance_loop(
            expected_phase="fast",
            require_animate=False,
            track_iterations=True,
        )

    def _run_animated_advance_phase(self) -> None:
        self._run_batch_advance_loop(
            expected_phase="advance",
            require_animate=True,
            on_fired=self._on_animated_batch_fired,
        )

    def _run_show_continuation_pre_sidebar(self) -> None:
        """After animation wait, finish show phase before widgets are drawn."""
        if not self._batch_running():
            return
        if not st.session_state.get(self._k("batch_animate")):
            return
        if st.session_state.get(self._k("batch_phase")) != "show":
            return
        if not st.session_state.get(self._k("show_sleep_complete")):
            return

        st.session_state.pop(self._k("show_sleep_complete"), None)

        if st.session_state.get(self._k("batch_stop_requested")):
            self._end_batch("Stopped", rerun=True)
            return

        mode = st.session_state.get(self._k("batch_mode"), "steps")
        max_steps = int(st.session_state.get(self._k("batch_max_steps"), 0))
        firings = int(st.session_state.get(self._k("batch_firings"), 0))
        target_time = int(st.session_state.get(self._k("batch_target_time"), 0))
        steps_done = mode == "steps" and max_steps > 0 and firings >= max_steps
        time_done = mode == "time" and self.marking.global_clock >= target_time
        if steps_done or time_done:
            self._end_batch(self._status_message("done"), rerun=True)
            return

        st.session_state[self._k("batch_phase")] = "advance"
        self._request_rerun()

    def _run_pre_sidebar_drivers(
        self, *, transitions_enabled: bool | None = None,
    ) -> None:
        """Advance simulation state; may set needs_rerun (flush before sidebar in render)."""
        if self._abort_batch_if_stop_requested():
            return
        self._coalesce_manual_time_advance(
            transitions_enabled=transitions_enabled,
        )
        for step in (
            self._run_fast_batch_phase,
            self._run_animated_advance_phase,
            self._run_show_continuation_pre_sidebar,
        ):
            step()

    def _render_graph_panel(
        self, height: int, enabled_names: list[str], last_fired: dict,
    ) -> None:
        timings = compute_animation_timings(self._effective_anim_ms())
        self._last_animation_timings = timings
        animating_transition = None
        if last_fired.get("in") or last_fired.get("out"):
            animating_transition = last_fired.get("transition")
        data = self._prepare_data(
            enabled_names,
            last_fired.get("in", []),
            last_fired.get("out", []),
            animation_timings=timings,
            animating_transition=animating_transition,
        )
        frame_height = height + 20
        picked = cpn_graph(data, height=frame_height, key=self._k("graph"))
        self._handle_graph_component_pick(picked, enabled_names)

    def _show_animation_paint_pass(self) -> bool:
        """First show-phase run: mount graph iframe only, then rerun before sidebar."""
        return (
            self._needs_show_animation_wait()
            and not st.session_state.get(self._k("show_frame_painted"))
        )

    def render(self, height: int = 800):
        """
        Streamlit run order (avoids stacked sidebar widgets from mid-run reruns):

        1. Repair session, sync batch UI, flush pending rerun from last run
        2. Run batch/manual drivers (may request rerun; flush before any widgets)
        3. Sidebar (skipped on animation paint pass — graph iframe only)
        4. Graph; optional animation wait then flush (sidebar not redrawn on that run)
        """
        self._repair_batch_session()
        self._sync_batch_mode_ui()
        self._flush_rerun()

        enabled = get_enabled_transitions(self.cpn, self.marking, self.context)
        enabled_names = [t.name for t in enabled]
        self._apply_graph_transition_pick(enabled_names)

        self._run_pre_sidebar_drivers(transitions_enabled=bool(enabled))
        self._flush_rerun()

        self._refresh_deadlock_flags(enabled_names)

        batch_running = self._batch_running()
        panel = self._active_sidebar_panel(batch_running)
        step_count = st.session_state.get(self._k("step_count"), 0)
        paint_pass = self._show_animation_paint_pass()

        if not paint_pass:
            with st.sidebar:
                self._render_simulation_metrics(step_count, len(enabled_names))
                last_fired = st.session_state.get(self._k("last_fired_name"))
                if last_fired:
                    st.caption(f"Last fired: **{last_fired}**")

                anim_ms = st.number_input(
                    "Animation duration (ms)",
                    min_value=MIN_TRANSITION_ANIMATION_MS,
                    max_value=MAX_TRANSITION_ANIMATION_MS,
                    value=int(st.session_state.get(
                        self._k("anim_ms"), DEFAULT_TRANSITION_ANIMATION_MS,
                    )),
                    step=25,
                    key=self._k("anim_input"),
                    disabled=batch_running,
                    help="Wall-clock time per firing (input phase, gap, output phase).",
                )
                anim_ms_int = int(anim_ms)
                if st.session_state.get(self._k("anim_ms")) != anim_ms_int:
                    st.session_state[self._k("anim_ms")] = anim_ms_int

                self._render_sidebar_panel_switch(batch_running)
                if panel == "batch":
                    self._render_batch_simulation_panel(
                        batch_running=batch_running,
                        anim_ms=int(anim_ms),
                        enabled_names=enabled_names,
                    )
                else:
                    self._render_manual_step_panel(
                        enabled=bool(enabled),
                        enabled_names=enabled_names,
                    )

                st.button(
                    "Reset to initial state",
                    key=self._k("reset"),
                    on_click=self._reset_simulation,
                    disabled=batch_running,
                    use_container_width=True,
                    help="Disabled while a batch is running.",
                )

                self._sync_derived_status_messages(batch_running=batch_running)
                self._render_status_messages()

                with st.expander("Tips", expanded=False):
                    st.markdown(
                        "- Use **Step** or **Batch** above to switch modes; "
                        "only one panel is active at a time.\n"
                        "- **Green** boxes = enabled transitions; click one in **Step** mode "
                        "to select it for firing.\n"
                        "- **Advance clock when idle** moves global time when nothing can fire "
                        "(Step and batch Steps).\n"
                        "- **Click** a place or transition on the graph for tokens, guard, "
                        "and action details."
                    )

        if st.session_state.pop(self._k("run_drivers_after_sidebar"), False):
            self._run_pre_sidebar_drivers()
            self._flush_rerun()

        if self._needs_show_animation_wait():
            last_fired = st.session_state.get(self._k("last_fired"), {})
        else:
            last_fired = st.session_state.pop(self._k("last_fired"), {})

        self._render_graph_panel(height, enabled_names, last_fired)
        self._flush_rerun()
        if self._run_show_animation_wait_after_graph(last_fired):
            self._flush_rerun()
