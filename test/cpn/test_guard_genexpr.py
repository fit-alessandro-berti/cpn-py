from cpnpy.cpn.cpn_imp import (
    Arc,
    CPN,
    EvaluationContext,
    Marking,
    Place,
    Transition,
)
from cpnpy.cpn.colorsets import ColorSetParser


def test_guard_genexpr_sees_binding_variables():
    """Generator-expression guards must see arc-bound variables (Python 3 scope)."""
    parser = ColorSetParser()
    colorsets = parser.parse_definitions("colset INT = int;\ncolset RECORD = product(INT, INT);")
    record_cs = colorsets["RECORD"]

    p_cr = Place("ClientRequest", record_cs)
    p_out = Place("Out", record_cs)

    t = Transition(
        "Metric",
        guard=(
            'all(not (m["c_id"] == cr["c_id"] and m["r_time"] >= cr["r_time"]) '
            "for m in metric_client_request_sensor)"
        ),
        variables=["cr"],
    )

    cpn = CPN()
    cpn.add_place(p_cr)
    cpn.add_place(p_out)
    cpn.add_transition(t)
    cpn.add_arc(Arc(p_cr, t, "cr"))
    cpn.add_arc(Arc(t, p_out, "cr"))

    marking = Marking()
    marking.set_tokens("ClientRequest", [{"c_id": 1, "r_time": 10}])

    context = EvaluationContext(
        user_code="metric_client_request_sensor = [{'c_id': 2, 'r_time': 5}]",
    )
    assert cpn.is_enabled(t, marking, context) is True

    context = EvaluationContext(
        user_code="metric_client_request_sensor = [{'c_id': 1, 'r_time': 12}]",
    )
    assert cpn.is_enabled(t, marking, context) is False
