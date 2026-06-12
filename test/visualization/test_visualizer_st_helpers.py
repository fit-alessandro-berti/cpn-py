import json

import pytest

from cpnpy.visualization.visualizer_st_helpers import (
    BASE_SPREAD,
    DEFAULT_TRANSITION_ANIMATION_MS,
    LARGE_GRAPH_NODE_THRESHOLD,
    LAYOUT_STRATEGY_FLOW_LR,
    LAYOUT_STRATEGY_FORCE,
    LAYOUT_STRATEGY_CLUSTER,
    LAYOUT_STRATEGY_LAYERED_LR,
    MAX_TRANSITION_ANIMATION_MS,
    MIN_TRANSITION_ANIMATION_MS,
    MonitorSpec,
    animation_wait_ms,
    batch_status_level,
    batch_step_logic,
    compute_animation_timings,
    compute_graph_layout,
    enabled_transition_names,
    evaluate_monitors,
    hcpn_cluster_key,
    arc_edge_id,
    estimate_place_ellipse_size,
    format_place_graph_label,
    format_transition_graph_label,
    format_guard_external_label,
    normalize_animation_arcs,
    animation_draw_count,
    format_simulation_error,
    format_simulation_metrics_row,
    get_action_source,
    raise_if_invalid_net,
    resolve_layout_strategy,
    spacing_pct_to_spread_factor,
    validate_net_for_simulation,
    apply_imported_positions,
    apply_status_dismiss,
    build_layout_file_payload,
    clear_status_dismiss,
    graph_layout_storage_key,
    is_status_dismissed,
    parse_layout_file_json,
    status_entry_fingerprint,
)
from cpnpy.cpn.cpn_imp import CPN, Place, Transition, Arc, Marking, EvaluationContext, ColorSetParser


def test_arc_edge_id_unique_for_parallel_arcs():
    assert arc_edge_id("main.ClientRequest", "main.MergeRequests", 0) != arc_edge_id(
        "main.ClientRequest", "main.MergeRequests", 1
    )


def test_format_place_graph_label_splits_on_dots():
    assert format_place_graph_label("a.b.c") == "<b>a</b>\n<b>b</b>\n<b>c</b>"
    assert format_place_graph_label("simple") == "<b>simple</b>"


def test_format_place_graph_label_empty_segments():
    assert format_place_graph_label("..") == "<b>..</b>"


def test_format_transition_graph_label_splits_on_dots_with_action():
    assert format_transition_graph_label("execute_route.Serve", has_action=True) == (
        "<b>execute_route</b>\n<b>Serve</b>\n<code>action</code>"
    )


def test_format_transition_graph_label_without_action():
    assert format_transition_graph_label("a.b", has_action=False) == (
        "<b>a</b>\n<b>b</b>\n "
    )


def test_estimate_place_ellipse_size_grows_with_lines():
    _, h1 = estimate_place_ellipse_size("a")
    _, h_many = estimate_place_ellipse_size("p1.p2.p3.p4.p5")
    assert h_many > h1


def test_estimate_place_ellipse_size_long_segment_wraps():
    long_name = "x" * 120
    _w, h = estimate_place_ellipse_size(long_name)
    _w2, h2 = estimate_place_ellipse_size("x" * 20)
    assert h > h2
    assert _w >= _w2


def test_resolve_layout_strategy_flow_grid_and_force():
    assert resolve_layout_strategy("flow_lr") == LAYOUT_STRATEGY_FLOW_LR
    assert resolve_layout_strategy("cluster") == LAYOUT_STRATEGY_CLUSTER
    assert resolve_layout_strategy("layered_lr") == LAYOUT_STRATEGY_LAYERED_LR
    assert resolve_layout_strategy("grid") == LAYOUT_STRATEGY_CLUSTER
    assert resolve_layout_strategy("force") == LAYOUT_STRATEGY_FORCE
    assert resolve_layout_strategy("auto") == LAYOUT_STRATEGY_FORCE
    assert resolve_layout_strategy("unknown") == LAYOUT_STRATEGY_FORCE


def test_spacing_pct_to_spread_factor():
    assert spacing_pct_to_spread_factor(100) == BASE_SPREAD
    assert spacing_pct_to_spread_factor(50) == pytest.approx(BASE_SPREAD * 0.5)
    assert spacing_pct_to_spread_factor(200) == pytest.approx(BASE_SPREAD * 2.0)
    assert spacing_pct_to_spread_factor(500) == pytest.approx(BASE_SPREAD * 5.0)
    assert spacing_pct_to_spread_factor(10) == pytest.approx(BASE_SPREAD * 0.5)
    assert spacing_pct_to_spread_factor(999) == pytest.approx(BASE_SPREAD * 5.0)


def test_compute_graph_layout_small_net():
    layout = compute_graph_layout(12, 20, strategy="force", spacing_pct=100)
    assert layout["strategy"] == LAYOUT_STRATEGY_FORCE
    assert layout["spacing_pct"] == 100
    assert layout["large"] is False
    assert layout["stabilization_iterations"] == 300
    assert layout["spread_factor"] == BASE_SPREAD
    assert layout["fit_on_stabilized"] is True


def test_compute_graph_layout_flow_lr_and_cluster():
    flow = compute_graph_layout(12, 20, strategy="flow_lr", spacing_pct=100)
    assert flow["strategy"] == LAYOUT_STRATEGY_FLOW_LR
    assert flow["module_cluster_depth"] is None
    assert flow["fit_on_stabilized"] is False
    cluster = compute_graph_layout(12, 20, strategy="cluster", spacing_pct=100)
    assert cluster["strategy"] == LAYOUT_STRATEGY_CLUSTER
    assert cluster["module_cluster_depth"] is None
    assert cluster["fit_on_stabilized"] is False


def test_compute_graph_layout_layered_lr_small_and_large():
    small = compute_graph_layout(12, 20, strategy="layered_lr", spacing_pct=100)
    assert small["strategy"] == LAYOUT_STRATEGY_LAYERED_LR
    assert small["module_cluster_depth"] is None
    assert small["fit_on_stabilized"] is False
    assert small["large"] is False
    large = compute_graph_layout(
        LARGE_GRAPH_NODE_THRESHOLD, 125, strategy="layered_lr", spacing_pct=100,
    )
    assert large["strategy"] == LAYOUT_STRATEGY_LAYERED_LR
    assert large["module_cluster_depth"] == 1
    assert large["large"] is True
    assert large["suppress_external_guards"] is True
    assert large["fit_on_stabilized"] is False


def test_hcpn_cluster_key_depth_and_parent_path():
    assert hcpn_cluster_key("a.b.c", depth=1) == "a"
    assert hcpn_cluster_key("a.b.c", depth=None) == "a.b"
    assert hcpn_cluster_key("solo", depth=None) == "solo"


def test_compute_graph_layout_large_flow_lr_coarse_modules():
    layout = compute_graph_layout(
        LARGE_GRAPH_NODE_THRESHOLD, 125, strategy="flow_lr", spacing_pct=100,
    )
    assert layout["large"] is True
    assert layout["module_cluster_depth"] == 1


def test_compute_graph_layout_large_layered_lr_coarse_modules():
    layout = compute_graph_layout(
        LARGE_GRAPH_NODE_THRESHOLD, 125, strategy="layered_lr", spacing_pct=100,
    )
    assert layout["strategy"] == LAYOUT_STRATEGY_LAYERED_LR
    assert layout["large"] is True
    assert layout["module_cluster_depth"] == 1


def test_compute_graph_layout_large_net():
    layout = compute_graph_layout(LARGE_GRAPH_NODE_THRESHOLD, 125, spacing_pct=100)
    assert layout["large"] is True
    assert layout["module_cluster_depth"] is None
    assert layout["suppress_external_guards"] is True
    assert layout["stabilization_iterations"] >= 500
    assert layout["spread_factor"] == BASE_SPREAD


def test_compute_animation_timings_default():
    t = compute_animation_timings(DEFAULT_TRANSITION_ANIMATION_MS)
    assert t["transition_ms"] == 500
    assert t["gap_ms"] == 29
    assert t["phase_ms"] == 235
    assert t["stagger_ms"] == 24


def test_compute_animation_timings_minimum():
    t = compute_animation_timings(50)
    assert t["phase_ms"] >= 20
    assert animation_wait_ms({"in": [{"arc": "a|b", "count": 1}],
                              "out": [{"arc": "b|c", "count": 1}]}, t) <= 200


def test_animation_wait_ms_single_token_in_out():
    timings = compute_animation_timings(425)
    firing = {
        "in": [{"arc": "P|T", "count": 1}],
        "out": [{"arc": "T|P", "count": 1}],
    }
    assert animation_wait_ms(firing, timings) == 425


def test_animation_wait_ms_multi_token_stagger():
    timings = compute_animation_timings(425)
    firing = {
        "in": [{"arc": "P|T", "count": 3}],
        "out": [{"arc": "T|P", "count": 1}],
    }
    # in phase: 200 + 2*20 = 240; gap 25; out: 240+25+200 = 465
    assert animation_wait_ms(firing, timings) == 465


def test_animation_wait_ms_empty():
    timings = compute_animation_timings(425)
    assert animation_wait_ms({"in": [], "out": []}, timings) == 0


def test_animation_wait_ms_in_only():
    timings = compute_animation_timings(425)
    firing = {"in": [{"arc": "P|T", "count": 1}], "out": []}
    assert animation_wait_ms(firing, timings) == 200


def test_animation_wait_ms_out_only():
    timings = compute_animation_timings(425)
    firing = {"in": [], "out": [{"arc": "T|P", "count": 1}]}
    assert animation_wait_ms(firing, timings) == 200


def test_animation_wait_ms_high_token_count():
    timings = compute_animation_timings(425)
    firing = {"in": [{"arc": "P|T", "count": 5}], "out": []}
    # 200 + 4*20 = 280
    assert animation_wait_ms(firing, timings) == 280


def test_animation_draw_count_caps_and_badge():
    assert animation_draw_count(3) == 3
    assert animation_draw_count(5) == 5
    assert animation_draw_count(12) == 1


def test_normalize_animation_arcs_small_and_large():
    small = normalize_animation_arcs([{"arc": "a|b", "count": 3}])
    assert small[0]["count"] == 3
    assert small[0]["draw_count"] == 3
    assert "badge_count" not in small[0]

    large = normalize_animation_arcs([{"arc": "a|b", "count": 20}])
    assert large[0]["count"] == 20
    assert large[0]["draw_count"] == 1
    assert large[0]["badge_count"] == 20


def test_animation_wait_ms_many_tokens_uses_badge_timing():
    timings = compute_animation_timings(425)
    firing = {"in": [{"arc": "P|T", "count": 100}], "out": []}
    assert animation_wait_ms(firing, timings) == 200


def test_format_guard_external_label_truncates():
    assert format_guard_external_label("x > 0") == "x > 0"
    assert format_guard_external_label("") == ""
    long_guard = "a" * 80
    assert format_guard_external_label(long_guard, max_len=48).endswith("...")
    assert len(format_guard_external_label(long_guard, max_len=48)) == 51


def test_batch_step_logic_stopped():
    assert batch_step_logic(
        batch_mode="steps", batch_max_steps=10, batch_target_time=5,
        batch_auto_advance=True, batch_stop_requested=True,
        batch_firings=0, global_clock=0, enabled_name="T1",
    ) == "stopped"


def test_batch_step_logic_steps_limit():
    assert batch_step_logic(
        batch_mode="steps", batch_max_steps=5, batch_target_time=0,
        batch_auto_advance=True, batch_stop_requested=False,
        batch_firings=5, global_clock=0, enabled_name="T1",
    ) == "done"


def test_batch_step_logic_time_target():
    assert batch_step_logic(
        batch_mode="time", batch_max_steps=0, batch_target_time=10,
        batch_auto_advance=True, batch_stop_requested=False,
        batch_firings=0, global_clock=10, enabled_name="T1",
    ) == "done"


def test_batch_step_logic_fired():
    assert batch_step_logic(
        batch_mode="steps", batch_max_steps=0, batch_target_time=0,
        batch_auto_advance=True, batch_stop_requested=False,
        batch_firings=0, global_clock=0, enabled_name="T1",
    ) == "fired"


def test_batch_step_logic_steps_unlimited_need_advance():
    assert batch_step_logic(
        batch_mode="steps", batch_max_steps=0, batch_target_time=0,
        batch_auto_advance=True, batch_stop_requested=False,
        batch_firings=0, global_clock=0, enabled_name=None,
    ) == "need_advance"


def test_batch_step_logic_idle_no_auto_advance():
    assert batch_step_logic(
        batch_mode="steps", batch_max_steps=0, batch_target_time=0,
        batch_auto_advance=False, batch_stop_requested=False,
        batch_firings=0, global_clock=0, enabled_name=None,
    ) == "idle"


def test_batch_step_logic_need_advance():
    assert batch_step_logic(
        batch_mode="time", batch_max_steps=0, batch_target_time=10,
        batch_auto_advance=True, batch_stop_requested=False,
        batch_firings=0, global_clock=0, enabled_name=None,
    ) == "need_advance"


def test_batch_step_logic_time_always_advances_when_idle():
    """Time mode always auto-advances when idle (see feature plan R4)."""
    assert batch_step_logic(
        batch_mode="time", batch_max_steps=0, batch_target_time=10,
        batch_auto_advance=False, batch_stop_requested=False,
        batch_firings=0, global_clock=0, enabled_name=None,
    ) == "need_advance"


def test_compute_animation_timings_at_min():
    t = compute_animation_timings(MIN_TRANSITION_ANIMATION_MS)
    assert t["phase_ms"] >= 20


def test_compute_animation_timings_at_max():
    t = compute_animation_timings(MAX_TRANSITION_ANIMATION_MS)
    assert t["transition_ms"] == MAX_TRANSITION_ANIMATION_MS
    assert t["phase_ms"] >= 20


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        ("Finished (3 transitions)", "success"),
        ("Finished (time target @ 10)", "success"),
        ("Stopped", "warning"),
        ("Deadlock at time 5", "error"),
        ("Error — boom", "error"),
        ("Simulation error — ValueError: bad", "error"),
        ("Running", "info"),
    ],
)
def test_batch_status_level(status, expected):
    assert batch_status_level(status) == expected


def test_get_action_source_string():
    assert get_action_source("x = 1") == "x = 1"


def test_get_action_source_none():
    assert get_action_source(None) == ""


def test_get_action_source_callable():
    def sample_action():
        return 1

    source = get_action_source(sample_action)
    assert "def sample_action" in source


def test_format_simulation_error():
    try:
        raise ValueError("bad token")
    except ValueError as e:
        assert format_simulation_error(e) == "ValueError: bad token"


def _build_minimal_valid_net():
    parser = ColorSetParser()
    int_set = parser.parse_definitions("colset INT = int;")["INT"]
    p = Place("P", int_set)
    t = Transition("T", variables=["x"])
    cpn = CPN()
    cpn.add_place(p)
    cpn.add_transition(t)
    cpn.add_arc(Arc(p, t, "x"))
    marking = Marking()
    marking.set_tokens("P", [1])
    return cpn, marking


def test_parallel_arc_edges_have_unique_ids():
    from cpnpy.visualization.visualizer_st import CPNStreamlitVisualizer

    parser = ColorSetParser()
    int_set = parser.parse_definitions("colset INT = int;")["INT"]
    p = Place("P", int_set)
    t = Transition("T", variables=["x", "y"])
    cpn = CPN()
    cpn.add_place(p)
    cpn.add_transition(t)
    cpn.add_arc(Arc(p, t, "x"))
    cpn.add_arc(Arc(p, t, "y"))
    connections = {(a.source.name, a.target.name) for a in cpn.arcs}
    edges = [
        CPNStreamlitVisualizer._arc_edge(arc, connections, i)
        for i, arc in enumerate(cpn.arcs)
    ]
    ids = [e["id"] for e in edges]
    assert len(ids) == len(set(ids))


def test_validate_net_for_simulation_valid():
    cpn, marking = _build_minimal_valid_net()
    assert validate_net_for_simulation(cpn, marking) == []


def test_validate_net_unknown_place_in_marking():
    cpn, marking = _build_minimal_valid_net()
    marking.set_tokens("Missing", [1])
    errors = validate_net_for_simulation(cpn, marking)
    assert any("unknown place" in e.lower() for e in errors)


def test_validate_net_invalid_token():
    cpn, marking = _build_minimal_valid_net()
    marking.set_tokens("P", ["not-an-int"])
    errors = validate_net_for_simulation(cpn, marking)
    assert any("not a member" in e for e in errors)


def test_raise_if_invalid_net():
    cpn, marking = _build_minimal_valid_net()
    raise_if_invalid_net(cpn, marking)


def test_raise_if_invalid_net_raises():
    cpn, marking = _build_minimal_valid_net()
    marking.set_tokens("Missing", [1])
    with pytest.raises(ValueError, match="Invalid CPN setup"):
        raise_if_invalid_net(cpn, marking)


def test_graph_layout_storage_key_order_invariant():
    ids_a = ["b.T", "a.P"]
    ids_b = ["a.P", "b.T"]
    assert graph_layout_storage_key(ids_a) == graph_layout_storage_key(ids_b)
    assert graph_layout_storage_key(ids_a).startswith("cpn_v4_")


def test_build_layout_file_payload_minimal():
    payload = build_layout_file_payload({"P": {"x": 1.0, "y": 2.0}})
    assert payload == {"version": 1, "positions": {"P": {"x": 1.0, "y": 2.0}}}


def test_parse_layout_file_json_valid():
    raw = json.dumps({"version": 1, "positions": {"P": {"x": 1, "y": 2}}})
    assert parse_layout_file_json(raw) == {"P": {"x": 1.0, "y": 2.0}}


def test_parse_layout_file_json_rejects_bad_version():
    with pytest.raises(ValueError, match="Unsupported layout version"):
        parse_layout_file_json('{"version": 2, "positions": {}}')


def test_parse_layout_file_json_rejects_missing_positions():
    with pytest.raises(ValueError, match="positions"):
        parse_layout_file_json('{"version": 1}')


def test_apply_imported_positions_partial():
    existing = {"P": {"x": 0.0, "y": 0.0}, "T": {"x": 5.0, "y": 5.0}}
    imported = {"P": {"x": 10.0, "y": 20.0}, "Unknown": {"x": 99.0, "y": 99.0}}
    merged = apply_imported_positions(["P", "T"], existing, imported)
    assert merged["P"] == {"x": 10.0, "y": 20.0}
    assert merged["T"] == {"x": 5.0, "y": 5.0}
    assert "Unknown" not in merged


def test_apply_imported_positions_empty_import_no_op():
    existing = {"P": {"x": 1.0, "y": 2.0}}
    assert apply_imported_positions(["P"], existing, {}) == existing


def test_format_simulation_metrics_row_shows_full_values():
    clock = 1780726596
    text = format_simulation_metrics_row(clock, 12345, 7)
    assert text == (
        f"Clock:     {clock}\n"
        "Firings:   12345\n"
        "Enabled:   7"
    )


def _drive_monitor(**kwargs):
    defaults = dict(
        name="Drive enabled",
        slug="drive_enabled",
        predicate=lambda cpn, m: True,
        before=True,
        transition_name="execute_route.Drive",
        default_enabled=True,
    )
    defaults.update(kwargs)
    return MonitorSpec(**defaults)


def test_evaluate_monitors_before_drive_enabled():
    monitors = [_drive_monitor()]
    names = evaluate_monitors(
        monitors,
        phase="before",
        cpn=None,
        marking=None,
        pending_transition="execute_route.StartRoute",
        enabled_names=frozenset({"execute_route.Drive", "execute_route.StartRoute"}),
        enabled_slugs=frozenset({"drive_enabled"}),
    )
    assert names == ["Drive enabled"]


def test_evaluate_monitors_before_drive_not_enabled():
    monitors = [_drive_monitor()]
    assert evaluate_monitors(
        monitors,
        phase="before",
        cpn=None,
        marking=None,
        pending_transition="execute_route.StartRoute",
        enabled_names=frozenset({"execute_route.StartRoute"}),
        enabled_slugs=frozenset({"drive_enabled"}),
    ) == []


def test_evaluate_monitors_respects_disabled_slug():
    monitors = [_drive_monitor()]
    assert evaluate_monitors(
        monitors,
        phase="before",
        cpn=None,
        marking=None,
        pending_transition="execute_route.Drive",
        enabled_names=frozenset({"execute_route.Drive"}),
        enabled_slugs=frozenset(),
    ) == []


def test_evaluate_monitors_after_transition_filter():
    monitors = [
        MonitorSpec(
            name="After Drive",
            slug="after_drive",
            predicate=lambda cpn, m: True,
            before=False,
            transition_name="execute_route.Drive",
            default_enabled=True,
        )
    ]
    assert evaluate_monitors(
        monitors,
        phase="after",
        cpn=None,
        marking=None,
        pending_transition="execute_route.Drive",
        enabled_names=frozenset(),
        enabled_slugs=frozenset({"after_drive"}),
    ) == ["After Drive"]
    assert evaluate_monitors(
        monitors,
        phase="after",
        cpn=None,
        marking=None,
        pending_transition="other",
        enabled_names=frozenset(),
        enabled_slugs=frozenset({"after_drive"}),
    ) == []


def test_batch_status_level_monitor_stop():
    assert batch_status_level("Stopped (monitors: Drive enabled)") == "success"


def test_status_entry_fingerprint_strips_whitespace():
    assert status_entry_fingerprint("  hello  ") == "hello"


def test_is_status_dismissed_not_dismissed():
    assert not is_status_dismissed("batch_status", "Stopped", {})


def test_is_status_dismissed_matching_fingerprint():
    dismissed = {"batch_status": "Stopped"}
    assert is_status_dismissed("batch_status", "Stopped", dismissed)


def test_is_status_dismissed_new_message_visible():
    dismissed = {"batch_status": "Stopped"}
    assert not is_status_dismissed(
        "batch_status", "Stopped (monitors: x)", dismissed,
    )


def test_apply_status_dismiss_records_fingerprint():
    result = apply_status_dismiss("sim_error", "  boom  ", {})
    assert result == {"sim_error": "boom"}


def test_clear_status_dismiss_removes_entry():
    dismissed = {"a": "one", "b": "two"}
    assert clear_status_dismiss("a", dismissed) == {"b": "two"}
    assert is_status_dismissed("a", "one", clear_status_dismiss("a", dismissed)) is False
