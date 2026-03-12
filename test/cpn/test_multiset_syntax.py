import pytest
from cpnpy.cpn.cpn_imp import CPN, Place, Transition, Arc, Marking, EvaluationContext
from cpnpy.cpn.colorsets import IntegerColorSet

def test_exact_consumption():
    print("Starting exact consumption test...", flush=True)
    cpn = CPN()
    p1 = Place("P1", IntegerColorSet())
    p2 = Place("P2", IntegerColorSet())

    # Transition consumes 3 tokens from P1 and binds them to 'tokens'
    # Guard ensures sum is sufficient (just a dummy check here really)
    t = Transition("T", variables=["tokens"], guard="sum(tokens) > 2")
    cpn.add_place(p1)
    cpn.add_place(p2)
    cpn.add_transition(t)
    
    # Arc consumes exactly 3 tokens
    cpn.add_arc(Arc(p1, t, "3`tokens"))
    cpn.add_arc(Arc(t, p2, "tokens"))

    context = EvaluationContext()
    marking = Marking()
    # P1 has exactly 3 tokens: 1, 2, 3
    marking.add_tokens("P1", [1, 2, 3])

    bindings = cpn._find_all_bindings(t, marking, context)
    # Should have exactly 1 binding: tokens=[1, 2, 3] (order might vary in set, but list is [1, 2, 3])
    assert len(bindings) == 1
    binding_val = bindings[0]['tokens']
    assert len(binding_val) == 3
    assert sorted(binding_val) == [1, 2, 3]

    cpn.fire_transition(t, marking, context, bindings[0])
    
    # P1 should be empty
    assert len(marking.get_multiset("P1").tokens) == 0
    # P2 should have tokens 1, 2, 3
    p2_tokens = sorted([t.value for t in marking.get_multiset("P2").tokens])
    assert p2_tokens == [1, 2, 3]

def test_multiple_bindings_combinations():
    print("Starting multiple bindings test...", flush=True)
    cpn = CPN()
    p1 = Place("P1", IntegerColorSet())
    t = Transition("T", variables=["tokens"])
    cpn.add_place(p1)
    cpn.add_transition(t)
    
    # Arc consumes 2 tokens
    cpn.add_arc(Arc(p1, t, "2`tokens"))

    context = EvaluationContext()
    marking = Marking()
    # P1 has 3 tokens: 10, 20, 30
    marking.add_tokens("P1", [10, 20, 30])

    bindings = cpn._find_all_bindings(t, marking, context)
    
    # We expect Combinations(3, 2) = 3 bindings:
    # {10, 20}, {10, 30}, {20, 30}
    assert len(bindings) == 3
    
    expected_combinations = [
        [10, 20],
        [10, 30],
        [20, 30]
    ]
    
    found_combinations = []
    for b in bindings:
        found_combinations.append(sorted(b['tokens']))
    
    # Sort to compare list of lists
    found_combinations.sort()
    assert found_combinations == expected_combinations

def test_insufficient_tokens():
    print("Starting insufficient tokens test...", flush=True)
    cpn = CPN()
    p1 = Place("P1", IntegerColorSet())
    t = Transition("T", variables=["tokens"])
    cpn.add_place(p1)
    cpn.add_transition(t)
    
    # Arc requires 3 tokens
    cpn.add_arc(Arc(p1, t, "3`tokens"))

    context = EvaluationContext()
    marking = Marking()
    # P1 has only 2 tokens
    marking.add_tokens("P1", [1, 2])

    bindings = cpn._find_all_bindings(t, marking, context)
    
    # Should find 0 bindings
    assert len(bindings) == 0

if __name__ == '__main__':
    test_exact_consumption()
    test_multiple_bindings_combinations()
    test_insufficient_tokens()
