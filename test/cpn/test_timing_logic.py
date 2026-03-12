import pytest
from cpnpy.cpn.cpn_imp import CPN, Place, Transition, Arc, Marking, EvaluationContext, Token
from cpnpy.cpn.colorsets import IntegerColorSet
from cpnpy.simulation.simu import simulate_until_deadlock

def test_global_clock_advancement():
    """Verify that global clock advances when no transitions are enabled at current time."""
    cpn = CPN()
    p1 = Place("P1", IntegerColorSet(timed=True)) # Timed
    t1 = Transition("T1", variables=["x"])
    
    cpn.add_place(p1)
    cpn.add_transition(t1)
    cpn.add_arc(Arc(p1, t1, "x"))
    
    marking = Marking()
    # Token available at time 10
    marking.add_tokens("P1", [1], timestamp=10)
    
    context = EvaluationContext()
    
    # At time 0, nothing enabled
    assert cpn.is_enabled(t1, marking, context) == False
    
    # Advance clock
    cpn.advance_global_clock(marking)
    assert marking.global_clock == 10
    
    # Now enabled
    assert cpn.is_enabled(t1, marking, context) == True

def test_token_availability_mixed_timestamps():
    """Verify transition waits for the LATEST required token."""
    cpn = CPN()
    p1 = Place("P1", IntegerColorSet(timed=True))
    p2 = Place("P2", IntegerColorSet(timed=True))
    t1 = Transition("T1", variables=["x", "y"])
    
    cpn.add_place(p1)
    cpn.add_place(p2)
    cpn.add_transition(t1)
    cpn.add_arc(Arc(p1, t1, "x"))
    cpn.add_arc(Arc(p2, t1, "y"))
    
    marking = Marking()
    marking.add_tokens("P1", [1], timestamp=5)
    marking.add_tokens("P2", [2], timestamp=10)
    
    context = EvaluationContext()
    
    # Time 0: Not enabled
    assert cpn.is_enabled(t1, marking, context) == False
    
    # Advance clock -> Should go to 5 first? Or 10?
    # advance_global_clock looks at ALL future tokens. min(future_ts)
    # So it should go to 5.
    cpn.advance_global_clock(marking)
    assert marking.global_clock == 5
    
    # Time 5: Still not enabled (P2 needs 10)
    assert cpn.is_enabled(t1, marking, context) == False
    
    # Advance clock -> 10
    cpn.advance_global_clock(marking)
    assert marking.global_clock == 10
    
    # Time 10: Enabled
    assert cpn.is_enabled(t1, marking, context) == True

def test_delay_accumulation():
    """Verify outcome timestamp = global_clock + transition_delay + arc_delay."""
    cpn = CPN()
    p1 = Place("P1", IntegerColorSet(timed=True)) # Source
    p2 = Place("P2", IntegerColorSet(timed=True)) # Target
    
    # Transition delay = 3
    t1 = Transition("T1", variables=["x"], transition_delay=3)
    
    cpn.add_place(p1)
    cpn.add_place(p2)
    cpn.add_transition(t1)
    cpn.add_arc(Arc(p1, t1, "x"))
    # Output arc delay = 2
    cpn.add_arc(Arc(t1, p2, "x @+ 2"))
    
    marking = Marking()
    marking.add_tokens("P1", [1], timestamp=10)
    marking.global_clock = 10 # Manual set for test
    
    context = EvaluationContext()
    
    # Fire
    cpn.fire_transition(t1, marking, context)
    
    # Expected timestamp: 10 + 3 + 2 = 15
    tokens = marking.get_multiset("P2").tokens
    assert len(tokens) == 1
    assert tokens[0].timestamp == 15

def test_concurrent_transitions():
    """Verify correct handling of multiple transitions with different timestamps."""
    cpn = CPN()
    p1 = Place("P1", IntegerColorSet(timed=True))
    p2 = Place("P2", IntegerColorSet(timed=True))
    
    t1 = Transition("T1", variables=["x"]) # Uses P1
    t2 = Transition("T2", variables=["y"]) # Uses P2
    
    cpn.add_place(p1)
    cpn.add_place(p2)
    cpn.add_transition(t1)
    cpn.add_transition(t2)
    cpn.add_arc(Arc(p1, t1, "x"))
    cpn.add_arc(Arc(p2, t2, "y"))
    
    marking = Marking()
    marking.add_tokens("P1", [1], timestamp=5)
    marking.add_tokens("P2", [2], timestamp=3)
    
    context = EvaluationContext()
    
    # Advance to 3 (first event)
    cpn.advance_global_clock(marking)
    assert marking.global_clock == 3
    
    # Only T2 enabled
    assert cpn.is_enabled(t1, marking, context) == False
    assert cpn.is_enabled(t2, marking, context) == True
    
    # Fire T2
    cpn.fire_transition(t2, marking, context)
    
    # Advance to 5
    cpn.advance_global_clock(marking)
    assert marking.global_clock == 5
    
    # Now T1 enabled
    assert cpn.is_enabled(t1, marking, context) == True

if __name__ == "__main__":
    test_global_clock_advancement()
    test_token_availability_mixed_timestamps()
    test_delay_accumulation()
    test_concurrent_transitions()
    print("All timing tests passed!")
