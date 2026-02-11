from cpnpy.cpn.cpn_imp import *
from cpnpy.simulation.simu import simulate_until_deadlock


def test_timed_tokens():
    cs_definitions = """
        colset INT = int timed;
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

    # Create the CPN structure
    p_int = Place("P_Int", int_set)  # timed place
    p_pair = Place("P_Pair", pair_set)  # timed place

    t1 = Transition("T1", variables=["x"],
                    transition_delay=4, priority=1)

    cpn = CPN()
    cpn.add_place(p_int)
    cpn.add_place(p_pair)

    cpn.add_transition(t1)
    cpn.add_arc(Arc(p_int, t1, "x"))
    cpn.add_arc(Arc(t1, p_pair, "(double(x), 'abc') @+5"))


    # Create a marking
    marking = Marking()
    marking.set_tokens("P_Int", [1, 2, 3, 4], timestamps=[0, 1, 2, 10])

    simulate_until_deadlock(cpn, marking, context)

    # print(marking.get_multiset("P_Pair"))

    assert marking.get_multiset("P_Pair").tokens == [
        Token((2, 'abc'), timestamp=9), # 0 + 4 + 5
        Token((4, 'abc'), timestamp=10), # 1 + 4 + 5
        Token((6, 'abc'), timestamp=11), # 2 + 4 + 5
        Token((8, 'abc'), timestamp=19) # 10 + 4 + 5
    ]
    assert marking.global_clock == 19

    # from cpnpy.visualization.visualizer import CPNGraphViz
    # builder = CPNGraphViz()
    # builder.apply(cpn, marking)
    # builder.view()

if __name__ == '__main__':
    test_timed_tokens()