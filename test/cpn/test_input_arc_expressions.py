from cpnpy.cpn.cpn_imp import *
from cpnpy.simulation.simu import simulate_until_deadlock
from cpnpy.cpn.colorsets import IntegerColorSet
import pytest

def test_whitelist_binding():
    # 1. Setup
    cpn = CPN()
    p1 = Place("P1", IntegerColorSet())
    p2 = Place("P2", IntegerColorSet())
    p3 = Place("P3", IntegerColorSet())
    p_out = Place("P_Out", IntegerColorSet())
    
    t = Transition("T1", variables=["x", "y", "z"])
    
    cpn.add_place(p1)
    cpn.add_place(p2)
    cpn.add_place(p3)
    cpn.add_place(p_out)
    cpn.add_transition(t)
    
    # 2. Add Input Arcs with different syntaxes
    # x: 'var' syntax -> single value
    cpn.add_arc(Arc(p1, t, "x"))
    
    # y: '[var]' syntax -> single value
    cpn.add_arc(Arc(p2, t, "[y]"))
    
    # z: 'N`var' syntax -> list of values
    cpn.add_arc(Arc(p3, t, "2`z"))
    
    # Output arc uses variables
    # We expect x and y to be single values (int)
    # We expect z to be a list of ints
    # We output sum of x + y + sum(z)
    cpn.add_arc(Arc(t, p_out, "x + y + sum(z)"))
    
    # 3. Marking
    marking = Marking()
    marking.add_tokens("P1", [10])
    marking.add_tokens("P2", [20])
    marking.add_tokens("P3", [1, 2, 3]) # Need 2 tokens for z
    
    context = EvaluationContext()
    
    # 4. Check Bindings
    bindings = cpn._find_all_bindings(t, marking, context)
    print(f"Bindings: {bindings}")
    
    # We expect multiple bindings because z picks 2 from [1, 2, 3] -> (1,2), (1,3), (2,3)
    # x=10, y=20 fixed.
    
    assert len(bindings) > 0
    for b in bindings:
        assert b['x'] == 10
        assert b['y'] == 20
        assert isinstance(b['z'], list)
        assert len(b['z']) == 2
        assert set(b['z']).issubset({1, 2, 3})

    # 5. Fire one binding
    cpn.fire_transition(t, marking, context, bindings[0])
    
    # Check output
    # If binding was z=[1, 2], output = 10 + 20 + 3 = 33
    out_tokens = marking.get_multiset("P_Out").tokens
    assert len(out_tokens) == 1
    val = out_tokens[0].value
    
    # We don't know exact z choice, but we can verify logic
    # x=10, y=20. z sum is either 3, 4, or 5.
    # Output should be 33, 34, or 35.
    assert val in [33, 34, 35]

def test_invalid_syntax_ignored():
    cpn = CPN()
    p1 = Place("P1", IntegerColorSet())
    t = Transition("T1", variables=["x"]) # x is needed
    cpn.add_place(p1)
    cpn.add_transition(t)
    
    # Add INVALID input arc expression
    # This should be ignored by parser, so x receives no candidate source.
    cpn.add_arc(Arc(p1, t, "x + 1")) 
    
    marking = Marking()
    marking.add_tokens("P1", [10])
    context = EvaluationContext()
    
    with pytest.raises(ValueError, match="is not supported by the whitelist parser"):
        bindings = cpn._find_all_bindings(t, marking, context)

if __name__ == "__main__":
    test_whitelist_binding()
    test_invalid_syntax_ignored()
