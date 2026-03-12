import pytest
from cpnpy.cpn.cpn_imp import CPN, Place, Transition, Arc, Marking, EvaluationContext
from cpnpy.cpn.colorsets import IntegerColorSet
from cpnpy.analysis.analyzer import StateSpaceAnalyzer

def test_analyzer_basic_properties():
    """Verify statistics, boundedness, and liveness on a simple producer-consumer."""
    cpn = CPN()
    p1 = Place("P1", IntegerColorSet())
    p2 = Place("P2", IntegerColorSet())
    t1 = Transition("T1", variables=["x"])
    
    cpn.add_place(p1)
    cpn.add_place(p2)
    cpn.add_transition(t1)
    cpn.add_arc(Arc(p1, t1, "x"))
    cpn.add_arc(Arc(t1, p2, "x"))
    
    marking = Marking()
    marking.add_tokens("P1", [10, 20])
    
    analyzer = StateSpaceAnalyzer(cpn, marking)
    stats = analyzer.get_statistics()
    
    # Initial: {P1:[10,20], P2:[]}
    # Step 1: {P1:[10], P2:[20]} or {P1:[20], P2:[10]} (but since tokens are same type, might collapse if keys allow)
    # Step 2: {P1:[], P2:[10, 20]}
    # Total nodes might vary depending on whether markings are equivalent.
    
    assert stats["RG_nodes"] > 1
    
    # Boundedness
    bounds = analyzer.get_place_bounds()
    assert bounds["P1"] == (0, 2)
    assert bounds["P2"] == (0, 2)
    
    # Liveness
    dead_markings = analyzer.list_dead_markings()
    assert len(dead_markings) == 1 # Final marking is dead
    
    dead_transitions = analyzer.list_dead_transitions()
    assert len(dead_transitions) == 0 # T1 fired

def test_analyzer_dead_transition():
    """Verify dead transition detection."""
    cpn = CPN()
    p1 = Place("P1", IntegerColorSet())
    t1 = Transition("T1", variables=["x"], guard="x < 0") # Never fires on positive tokens
    
    cpn.add_place(p1)
    cpn.add_transition(t1)
    cpn.add_arc(Arc(p1, t1, "x"))
    
    marking = Marking()
    marking.add_tokens("P1", [10])
    
    analyzer = StateSpaceAnalyzer(cpn, marking)
    assert "T1" in analyzer.list_dead_transitions()

def test_analyzer_home_marking():
    """Verify home marking detection in a cyclic net."""
    cpn = CPN()
    p1 = Place("P1", IntegerColorSet())
    t1 = Transition("T1", variables=["x"])
    cpn.add_place(p1)
    cpn.add_transition(t1)
    cpn.add_arc(Arc(p1, t1, "x"))
    cpn.add_arc(Arc(t1, p1, "x")) # Self loop
    
    marking = Marking()
    marking.add_tokens("P1", [42])
    
    analyzer = StateSpaceAnalyzer(cpn, marking)
    home_markings = analyzer.list_home_markings()
    
    assert len(home_markings) > 0 # At least one home marking (the state itself)

def test_analyzer_summarize():
    """Verify that summarize() returns all expected keys."""
    cpn = CPN()
    p1 = Place("P1", IntegerColorSet())
    marking = Marking()
    marking.add_tokens("P1", [1])
    
    analyzer = StateSpaceAnalyzer(cpn, marking)
    report = analyzer.summarize()
    
    expected_keys = {
        "statistics", "place_bounds", "dead_markings", 
        "dead_transitions", "live_transitions", 
        "impartial_transitions", "home_markings"
    }
    assert all(k in report for k in expected_keys)

if __name__ == "__main__":
    pytest.main([__file__])
