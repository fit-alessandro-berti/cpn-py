from cpnpy.cpn.cpn_imp import *
from cpnpy.simulation.simu import simulate_until_deadlock


def test_priority():
    cs_definitions = """
    colset INT = int timed;
    colset PAIR = product(INT, STRING) timed;
    """

    user_code = """
def double(n):
    return n*2

def tripple(n):
    return n*3    
"""
    context = EvaluationContext(user_code=user_code)

    parser = ColorSetParser()
    colorsets = parser.parse_definitions(cs_definitions)

    int_set = colorsets["INT"]
    pair_set = colorsets["PAIR"]

    # Create the CPN structure
    p_int = Place("P_Int", int_set)  # timed place
    p_pair1 = Place("P_Pair1", pair_set)  # timed place
    p_pair2 = Place("P_Pair2", pair_set)  # timed place

    t1 = Transition("T1", guard="x > 3", variables=["x"],
                    transition_delay=4, priority=1)
    t2 = Transition("T2", variables=["x"],
                    transition_delay=2, priority=2)

    cpn = CPN()
    cpn.add_place(p_int)
    cpn.add_place(p_pair1)
    cpn.add_place(p_pair2)

    cpn.add_transition(t1)
    cpn.add_arc(Arc(p_int, t1, "x"))
    cpn.add_arc(Arc(t1, p_pair1, "(double(x), 'byt1') @+5"))

    cpn.add_transition(t2)
    cpn.add_arc(Arc(p_int, t2, "x"))
    cpn.add_arc(Arc(t2, p_pair2, "(tripple(x), 'byt2') @+3"))

    # Create a marking
    marking = Marking()
    marking.set_tokens("P_Int", [1, 2, 3, 4, 5])

    simulate_until_deadlock(cpn, marking, context)

    # print(marking.get_multiset("P_Pair1"))
    # print(marking.get_multiset("P_Pair2"))
    assert marking.get_multiset("P_Pair1").tokens == [
        Token((8, 'byt1'), timestamp=9),
        Token((10, 'byt1'), timestamp=9),
    ]
    assert marking.get_multiset("P_Pair2").tokens == [
        Token((3,'byt2'), timestamp=5),
        Token((6,'byt2'), timestamp=5),
        Token((9,'byt2'), timestamp=5)
    ]
    # from cpnpy.visualization.visualizer import CPNGraphViz
    # builder = CPNGraphViz()
    # builder.apply(cpn, marking)
    # builder.view()


if __name__ == '__main__':
    test_priority()
