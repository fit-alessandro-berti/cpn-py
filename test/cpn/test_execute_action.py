from cpnpy.cpn.cpn_imp import *
from cpnpy.simulation.simu import simulate_until_deadlock


def test_execute_action():
    cs_definitions = """
    colset INT = int timed;
    colset STRING = string;
    colset PAIR = product(INT, STRING) timed;
    """

    user_code = """
def double(n):
    return n*2
"""
    context = EvaluationContext(user_code=user_code)

    parser = ColorSetParser()
    colorsets = parser.parse_definitions(cs_definitions)

    int_set = colorsets["INT"]
    pair_set = colorsets["PAIR"]

    p_int = Place("P_Int", int_set)
    p_pair = Place("P_Pair", pair_set)

    def action(input, output):
        x = input.x
        y = double(x)
        output.y = y

    t = Transition("T",
                   guard="x > 1",
                   action=action,
                   variables=["x"], transition_delay=2)

    cpn = CPN()
    cpn.add_place(p_int)
    cpn.add_place(p_pair)

    cpn.add_transition(t)
    cpn.add_arc(Arc(p_int, t, "x"))
    cpn.add_arc(Arc(t, p_pair, "(y, 'str') @+5"))

    # Create a marking
    marking = Marking()
    marking.set_tokens("P_Int", [1, 2, 3])  # all at timestamp 0

    simulate_until_deadlock(cpn, marking, context)

    # check tokens in output place
    assert marking.get_multiset("P_Int").tokens == [Token(1, timestamp=0)]
    assert marking.get_multiset("P_Pair").tokens == [Token((4, 'str'), timestamp=7), Token((6, 'str'), timestamp=7)]
    assert marking.global_clock == 7

    # from cpnpy.visualization.visualizer import CPNGraphViz
    # builder = CPNGraphViz()
    # builder.apply(cpn, marking)
    # builder.view()


if __name__ == '__main__':
    test_execute_action()
