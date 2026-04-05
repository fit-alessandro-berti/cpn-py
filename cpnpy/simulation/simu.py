import random
from typing import Optional

from cpnpy.cpn.colorsets import ColorSetParser
from cpnpy.cpn.cpn_imp import CPN, Marking, EvaluationContext, Arc, Transition, Place


def get_enabled_transitions(
    cpn: CPN,
    marking: Marking,
    context: EvaluationContext,
    only_best_priority: bool = True
) -> list[Transition]:
    """
    Get all transitions currently enabled at the marking's global_clock.
    If only_best_priority=True (default), only return transitions with the highest priority (lowest numeric value).
    """
    enabled = [
        t for t in cpn.transitions
        if cpn.is_enabled(t, marking, context)
    ]

    if not enabled or not only_best_priority:
        return enabled

    # Lower priority value means higher priority.
    best_pri = min(getattr(t, "priority", 0) for t in enabled)
    return [t for t in enabled if getattr(t, "priority", 0) == best_pri]


def simulate_until_deadlock(
    cpn: CPN,
    marking: Marking,
    context: EvaluationContext,
    visualizer=None,
    max_steps: int = 1000,
    max_time: Optional[int] = None,
):
    """
    Run the CPN simulation until no more transitions are enabled and time cannot advance,
    or until limits (max_steps, max_time) are reached.
    """
    step = 0

    while step < max_steps:
        # Check time limit
        if max_time is not None and marking.global_clock >= max_time:
            print(f"Reached max_time={max_time}, stopping simulation.")
            break

        # 1) Fire all transitions enabled at the current time (respecting priorities)
        while True:
            enabled = get_enabled_transitions(cpn, marking, context)
            if not enabled:
                break

            # Safety check for max_time before firing
            if max_time is not None and marking.global_clock > max_time:
                print(f"Global time {marking.global_clock} > max_time={max_time}, stopping.")
                return marking

            # Choose a random transition among those with the best priority
            t = random.choice(enabled)
            step += 1

            print(f"[step {step}] Firing {t.name} at time {marking.global_clock}")
            cpn.fire_transition(t, marking, context)

            if visualizer is not None:
                # Note: This is a placeholder for older-style visualizers.
                # The streamlit visualizer doesn't use this callback.
                pass

            if step >= max_steps:
                print("Reached max_steps, stopping simulation.")
                return marking

        # 2) Advance the clock after exhausting current events
        before = marking.global_clock
        if max_time is not None and before >= max_time:
            break

        cpn.advance_global_clock(marking)
        after = marking.global_clock
        print(f"Advancing time: {before} -> {after}")

        if after == before:
            print("No more enabled transitions and time cannot advance. Deadlock.")
            break

        if max_time is not None and after > max_time:
            print(f"Time advanced past max_time={max_time} (now {after}), stopping.")
            break

    return marking




if __name__ == "__main__":
    from cpnpy.visualization.visualizer import CPNGraphViz
    builder = CPNGraphViz()

    cs_definitions = """
    colset INT = int timed;
    colset STRING = string;
    colset PAIR = product(INT, STRING) timed;
    """

    parser = ColorSetParser()
    colorsets = parser.parse_definitions(cs_definitions)

    int_set = colorsets["INT"]
    pair_set = colorsets["PAIR"]

    p_int = Place("P_Int", int_set)  # timed place
    p_pair = Place("P_Pair", pair_set)  # timed place
    t = Transition("T", guard="x > 10", variables=["x"], transition_delay=2)

    cpn = CPN()
    cpn.add_place(p_int)
    cpn.add_place(p_pair)
    cpn.add_transition(t)
    cpn.add_arc(Arc(p_int, t, "x"))
    cpn.add_arc(Arc(t, p_pair, "(x, 'hello') @+5"))

    marking = Marking()
    marking.set_tokens("P_Int", [5, 30, 13, 14, 12])

    # Visualize final state
    builder.apply(cpn, marking)
    builder.view()

    user_code = """
def double(n):
    return n*2
"""
    context = EvaluationContext(user_code=user_code)

    # run full simulation
    final_marking = simulate_until_deadlock(cpn, marking, context, visualizer=builder, max_time=4)

    print("Final marking:", final_marking)
    print("Final global clock:", final_marking.global_clock)

    # Visualize final state
    builder.apply(cpn, final_marking)
    builder.view()
