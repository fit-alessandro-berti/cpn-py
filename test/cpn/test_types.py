from cpnpy.cpn.cpn_imp import *
from cpnpy.simulation.simu import simulate_until_deadlock


def test_record_timed():
    cs_definitions = """
    colset RECORD = record id:int * name:string * balance:real timed;
    """

    parser = ColorSetParser()
    colorsets = parser.parse_definitions(cs_definitions)

    record_set = colorsets["RECORD"]

    # Create the CPN structure
    p_record = Place("P_Record", record_set)  # timed place
    p_output = Place("P_Output", record_set)

    # action can mutate input record or create new onw
    def action(input, output):
        r = input.r
        if r["name"] == 'Alice':
            r["balance"] += 50.0
        else:
            r["balance"] += 25.0
        r["name"] += " UPDATED"
        output.r = r

    t = Transition("T", variables=["r"], action=action, transition_delay=3)


    cpn = CPN()
    cpn.add_place(p_record)
    cpn.add_place(p_output)
    cpn.add_transition(t)
    cpn.add_arc(Arc(p_record, t, "r"))
    cpn.add_arc(Arc(t, p_output, "r @+2"))

    # Create a marking
    marking = Marking()
    marking.set_tokens("P_Record", [
        {'id': 1, 'name': 'Alice', 'balance': 100.0},
        {'id': 2, 'name': 'Bob', 'balance': 150.5},
    ], timestamps=[0, 5])

    # Check tokens in place
    assert marking.get_multiset("P_Record").tokens == [
        Token({'id': 1, 'name': 'Alice', 'balance': 100.0}, timestamp=0),
        Token({'id': 2, 'name': 'Bob', 'balance': 150.5}, timestamp=5),
    ]

    simulate_until_deadlock(cpn, marking, EvaluationContext())

    # Check tokens in output place
    print(marking.get_multiset("P_Output"))
    assert marking.get_multiset("P_Output").tokens == [
        Token({'id': 1, 'name': 'Alice UPDATED', 'balance': 150.0}, timestamp=5),  # 0 + 3 + 2
        Token({'id': 2, 'name': 'Bob UPDATED', 'balance': 175.5}, timestamp=10),   # 5 + 3 + 2
    ]

    # from cpnpy.visualization.visualizer import CPNGraphViz
    # builder = CPNGraphViz()
    # builder.apply(cpn, marking)
    # builder.view()

def test_record():
    cs_definitions = """
    colset RECORD = record id:int * name:string * balance:real;
    """

    parser = ColorSetParser()
    colorsets = parser.parse_definitions(cs_definitions)

    record_set = colorsets["RECORD"]

    # Create the CPN structure
    p_record = Place("P_Record", record_set)  # untimed place
    p_output = Place("P_Output", record_set)

    # action can mutate input record or create new onw
    def action(input, output):
        r = input.r
        if r["name"] == 'Alice':
            r["balance"] += 50.0
        else:
            r["balance"] += 25.0
        r["name"] += " UPDATED"
        output.r = r

    t = Transition("T", variables=["r"], action=action)


    cpn = CPN()
    cpn.add_place(p_record)
    cpn.add_place(p_output)
    cpn.add_transition(t)
    cpn.add_arc(Arc(p_record, t, "r"))
    cpn.add_arc(Arc(t, p_output, "r"))

    # Create a marking
    marking = Marking()
    marking.set_tokens("P_Record", [
        {'id': 1, 'name': 'Alice', 'balance': 100.0},
        {'id': 2, 'name': 'Bob', 'balance': 150.5},
    ])

    simulate_until_deadlock(cpn, marking, EvaluationContext())

    # Check tokens in output place
    print(marking.get_multiset("P_Output"))
    assert marking.get_multiset("P_Output").tokens == [
        Token({'id': 1, 'name': 'Alice UPDATED', 'balance': 150.0}),
        Token({'id': 2, 'name': 'Bob UPDATED', 'balance': 175.5}),
    ]

    # from cpnpy.visualization.visualizer import CPNGraphViz
    # builder = CPNGraphViz()
    # builder.apply(cpn, marking)
    # builder.view()



if __name__ == '__main__':
    test_record_timed()
    test_record()