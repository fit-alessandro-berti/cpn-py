import pytest
import networkx as nx
from cpnpy.cpn.cpn_imp import CPN, Place, Transition, Arc, Marking, EvaluationContext
from cpnpy.cpn.colorsets import IntegerColorSet
from cpnpy.analysis.reachability import build_reachability_graph, equiv_marking_to_key

def test_reachability_linear_net():
    """Test reachability on a simple linear net P1 -> T -> P2."""
    cpn = CPN()
    p1 = Place("P1", IntegerColorSet())
    p2 = Place("P2", IntegerColorSet())
    t = Transition("T", variables=["x"])
    
    cpn.add_place(p1)
    cpn.add_place(p2)
    cpn.add_transition(t)
    cpn.add_arc(Arc(p1, t, "x"))
    cpn.add_arc(Arc(t, p2, "x + 1"))
    
    marking = Marking()
    marking.add_tokens("P1", [10])
    
    context = EvaluationContext()
    
    RG = build_reachability_graph(cpn, marking, context)
    
    # Initial state + Successor state = 2 nodes
    assert len(RG.nodes) == 2
    assert len(RG.edges) == 1
    
    # Check that p2 has 11 in one of the nodes
    found = False
    for node in RG.nodes:
        m = RG.nodes[node]['marking']
        tokens = m.get_multiset("P2").tokens
        if len(tokens) == 1 and tokens[0].value == 11:
            found = True
            break
    assert found

def test_reachability_cycle():
    """Test reachability on a net with a cycle: P1 -> T1 -> P2, P2 -> T2 -> P1."""
    cpn = CPN()
    p1 = Place("P1", IntegerColorSet())
    p2 = Place("P2", IntegerColorSet())
    t1 = Transition("T1", variables=["x"])
    t2 = Transition("T2", variables=["y"])
    
    cpn.add_place(p1)
    cpn.add_place(p2)
    cpn.add_transition(t1)
    cpn.add_transition(t2)
    
    cpn.add_arc(Arc(p1, t1, "x"))
    cpn.add_arc(Arc(t1, p2, "x"))
    cpn.add_arc(Arc(p2, t2, "y"))
    cpn.add_arc(Arc(t2, p1, "y"))
    
    marking = Marking()
    marking.add_tokens("P1", [42])
    
    context = EvaluationContext()
    
    RG = build_reachability_graph(cpn, marking, context)
    
    # Should be two states: P1:{42} and P2:{42}
    assert len(RG.nodes) == 2
    assert len(RG.edges) == 2

def test_reachability_timed_advancement():
    """Test reachability where global clock must advance to enable transitions."""
    cpn = CPN()
    p1 = Place("P1", IntegerColorSet(timed=True))
    t1 = Transition("T1", variables=["x"])
    
    cpn.add_place(p1)
    cpn.add_transition(t1)
    cpn.add_arc(Arc(p1, t1, "x"))
    
    marking = Marking()
    marking.add_tokens("P1", [1], timestamp=10)
    marking.global_clock = 0
    
    context = EvaluationContext()
    
    RG = build_reachability_graph(cpn, marking, context)
    
    # Step 1: Clock advances to 10 (State 1)
    # Step 2: Transition fires (State 2)
    # Total nodes might be complex depending on how build_reachability_graph handles clock advancement.
    # Looking at reachability.py: if no transitions enabled, it advances clock and continues.
    
    # Initial state (clock 0) -> No transitions enabled -> advance to 10 -> Enabled -> Fire -> Deadlock
    # The current implementation of build_reachability_graph advances clock IN-PLACE on current_marking?
    # No, it modifies current_marking? Let's check.
    
    # Actually, if it finishes, it should have consumed the token.
    found_fired = False
    for node in RG.nodes:
        m = RG.nodes[node]['marking']
        if len(m.get_multiset("P1").tokens) == 0:
            found_fired = True
    assert found_fired

def test_equiv_marking_to_key():
    """Verify that equivalent markings produce the same key."""
    m1 = Marking()
    m1.add_tokens("P1", [1, 2])
    m1.global_clock = 5
    
    m2 = Marking()
    m2.add_tokens("P1", [2, 1]) # Order different
    m2.global_clock = 5
    
    assert equiv_marking_to_key(m1) == equiv_marking_to_key(m2)
    
    m3 = Marking()
    m3.add_tokens("P1", [1, 2])
    m3.global_clock = 6
    assert equiv_marking_to_key(m1) != equiv_marking_to_key(m3)

if __name__ == "__main__":
    pytest.main([__file__])
