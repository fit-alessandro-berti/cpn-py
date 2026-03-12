from cpnpy.cpn.cpn_imp import CPN, Place, Transition, Arc, Marking, EvaluationContext
from cpnpy.cpn.colorsets import IntegerColorSet

def test_multi_token_arc():
    cpn = CPN()
    p1 = Place("P1", IntegerColorSet())
    p2 = Place("P2", IntegerColorSet())

    # Transition with variable 'tokens'
    # Arc expression 2`tokens should consume two tokens and bind them as a list
    t = Transition("T", variables=["tokens"])

    cpn.add_place(p1)
    cpn.add_place(p2)
    cpn.add_transition(t)
    cpn.add_arc(Arc(p1, t, "2`tokens"))
    cpn.add_arc(Arc(t, p2, "sum(tokens)"))

    context = EvaluationContext()
    marking = Marking()
    marking.add_tokens("P1", [5, 6])

    print(f"Initial Marking: {marking}")
    bindings = cpn._find_all_bindings(t, marking, context)
    print(f"All Bindings: {bindings}")

    # Should find TWO bindings:
    # 1. {tokens: [5, 6]}
    # 2. {tokens: [6, 5]}

    if bindings:
        print("Firing binding 0...")
        cpn.fire_transition(t, marking, context, bindings[0])
        print(f"Marking after fire: {marking}")


if __name__ == '__main__':
    test_multi_token_arc()