import pytest

from cpnpy.visualization.visualizer_st_helpers import (
    DEFAULT_TRANSITION_ANIMATION_MS,
    MAX_TRANSITION_ANIMATION_MS,
    MIN_TRANSITION_ANIMATION_MS,
    animation_wait_ms,
    batch_status_level,
    batch_step_logic,
    compute_animation_timings,
    get_action_source,
)


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
        ("Error: boom", "error"),
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
