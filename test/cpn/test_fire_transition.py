import pytest
from cpnpy.cpn.cpn_imp import CPN, Place, Transition, Arc, Marking, EvaluationContext, Token
from cpnpy.cpn.colorsets import IntegerColorSet

def test_fire_multiple_input_arcs_distinct_vars():
    """Verify that multiple input arcs with distinct variables consume distinct tokens."""
    cpn = CPN()
    p1 = Place("P1", IntegerColorSet(timed=True))
    p2 = Place("P2", IntegerColorSet(timed=True))
    t1 = Transition("T1", variables=["x", "y"])
    
    cpn.add_place(p1)
    cpn.add_place(p2)
    cpn.add_transition(t1)
    cpn.add_arc(Arc(p1, t1, "x"))
    cpn.add_arc(Arc(p1, t1, "y"))
    cpn.add_arc(Arc(t1, p2, "x + y"))
    
    marking = Marking()
    marking.add_tokens("P1", [10, 20])
    context = EvaluationContext()
    
    # Should find two bindings: {x:10, y:20} and {x:20, y:10}
    bindings = cpn._find_all_bindings(t1, marking, context)
    assert len(bindings) == 2
    
    cpn.fire_transition(t1, marking, context, bindings[0])
    
    assert len(marking.get_multiset("P1").tokens) == 0
    p2_tokens = marking.get_multiset("P2").tokens
    assert len(p2_tokens) == 1
    assert p2_tokens[0].value == 30

def test_fire_equality_via_guard():
    """Verify equality check via guard when variables are distinct."""
    cpn = CPN()
    p1 = Place("P1", IntegerColorSet(timed=True))
    p2 = Place("P2", IntegerColorSet(timed=True))
    # Two tokens of same value needed
    t1 = Transition("T1", variables=["x", "y"], guard="x == y")
    
    cpn.add_place(p1)
    cpn.add_place(p2)
    cpn.add_transition(t1)
    cpn.add_arc(Arc(p1, t1, "x"))
    cpn.add_arc(Arc(p1, t1, "y"))
    cpn.add_arc(Arc(t1, p2, "x"))
    
    marking = Marking()
    marking.add_tokens("P1", [10, 20, 10]) # Two 10s, one 20
    context = EvaluationContext()
    
    # Possible bindings where x==y: {x:10, y:10} (picking different physical tokens)
    bindings = cpn._find_all_bindings(t1, marking, context)
    assert len(bindings) > 0
    for b in bindings:
        assert b['x'] == 10
        assert b['y'] == 10
    
    cpn.fire_transition(t1, marking, context, bindings[0])
    
    # P1 should have [20] left
    p1_tokens = marking.get_multiset("P1").tokens
    assert len(p1_tokens) == 1
    assert p1_tokens[0].value == 20

def test_fire_multiset_consumption():
    """Verify multiset arc (N`var) consumes correct tokens."""
    cpn = CPN()
    p1 = Place("P1", IntegerColorSet(timed=True))
    p2 = Place("P2", IntegerColorSet(timed=True))
    t1 = Transition("T1", variables=["tokens"])
    
    cpn.add_place(p1)
    cpn.add_place(p2)
    cpn.add_transition(t1)
    cpn.add_arc(Arc(p1, t1, "3`tokens"))
    cpn.add_arc(Arc(t1, p2, "sum(tokens)"))
    
    marking = Marking()
    marking.add_tokens("P1", [1, 2, 3, 4])
    context = EvaluationContext()
    
    bindings = cpn._find_all_bindings(t1, marking, context)
    # Combinations(4, 3) = 4 bindings
    assert len(bindings) == 4
    
    cpn.fire_transition(t1, marking, context, bindings[0])
    
    assert len(marking.get_multiset("P1").tokens) == 1
    p2_tokens = marking.get_multiset("P2").tokens
    assert len(p2_tokens) == 1
    assert p2_tokens[0].value == sum(bindings[0]['tokens'])

def test_fire_generator_and_sink():
    """Verify transitions with no inputs (generator) or no outputs (sink)."""
    cpn = CPN()
    p1 = Place("P1", IntegerColorSet(timed=True))
    t_gen = Transition("T_Gen")
    t_sink = Transition("T_Sink", variables=["x"])
    
    cpn.add_place(p1)
    cpn.add_transition(t_gen)
    cpn.add_transition(t_sink)
    
    cpn.add_arc(Arc(t_gen, p1, "42"))
    cpn.add_arc(Arc(p1, t_sink, "x"))
    
    marking = Marking()
    context = EvaluationContext()
    
    # 1. Fire Generator
    cpn.fire_transition(t_gen, marking, context)
    assert marking.get_multiset("P1").tokens[0].value == 42
    
    # 2. Fire Sink
    cpn.fire_transition(t_sink, marking, context)
    assert len(marking.get_multiset("P1").tokens) == 0

def test_fire_action_logic():
    """Verify that interaction between Transition.action and OutputScope works."""
    cpn = CPN()
    p1 = Place("P1", IntegerColorSet(timed=True))
    p2 = Place("P2", IntegerColorSet(timed=True))
    
    def my_action(inp, out):
        out.res = inp.x * 2
        
    t1 = Transition("T1", variables=["x"], action=my_action)
    
    cpn.add_place(p1)
    cpn.add_place(p2)
    cpn.add_transition(t1)
    cpn.add_arc(Arc(p1, t1, "x"))
    cpn.add_arc(Arc(t1, p2, "res")) # 'res' comes from OutputScope
    
    marking = Marking()
    marking.add_tokens("P1", [10])
    context = EvaluationContext()
    
    cpn.fire_transition(t1, marking, context)
    
    p2_tokens = marking.get_multiset("P2").tokens
    assert len(p2_tokens) == 1
    assert p2_tokens[0].value == 20

def test_fire_delays_accumulation():
    """Verify accumulation of transition delay and arc delay."""
    cpn = CPN()
    p1 = Place("P1", IntegerColorSet(timed=True))
    p2 = Place("P2", IntegerColorSet(timed=True))
    
    # transition delay = 5
    t1 = Transition("T1", variables=["x"], transition_delay=5)
    
    cpn.add_place(p1)
    cpn.add_place(p2)
    cpn.add_transition(t1)
    cpn.add_arc(Arc(p1, t1, "x"))
    # arc delay = 10
    cpn.add_arc(Arc(t1, p2, "x @+ 10"))
    
    marking = Marking()
    marking.add_tokens("P1", [1])
    marking.global_clock = 100
    context = EvaluationContext()
    
    cpn.fire_transition(t1, marking, context)
    
    # 100 + 5 + 10 = 115
    assert marking.get_multiset("P2").tokens[0].timestamp == 115

def test_fire_error_handling():
    """Verify RuntimeError on invalid firing attempts."""
    cpn = CPN()
    p1 = Place("P1", IntegerColorSet(timed=True))
    t1 = Transition("T1", variables=["x"])
    cpn.add_place(p1)
    cpn.add_transition(t1)
    cpn.add_arc(Arc(p1, t1, "x"))
    
    marking = Marking() # Empty
    context = EvaluationContext()
    
    # 1. No binding found
    with pytest.raises(RuntimeError, match="No valid binding found"):
        cpn.fire_transition(t1, marking, context)
        
    # 2. Binding provided but not enabled (e.g. tokens missing at runtime)
    # This shouldn't happen if we use _find_binding, but fire_transition allows passing a binding.
    marking.add_tokens("P1", [10], timestamp=1000) # Token not ready
    marking.global_clock = 0
    with pytest.raises(RuntimeError, match="not enabled under the found binding"):
        cpn.fire_transition(t1, marking, context, binding={"x": 10})

if __name__ == "__main__":
    pytest.main([__file__])
