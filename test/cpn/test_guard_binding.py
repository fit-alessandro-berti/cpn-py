from cpnpy.cpn.cpn_imp import *
from cpnpy.simulation.simu import simulate_until_deadlock
import pytest

def test_guard_binding_bug():
    # Define color sets
    cs_definitions = """
    colset INT = int;
    colset STRING = string;
    """
    
    parser = ColorSetParser()
    colorsets = parser.parse_definitions(cs_definitions)
    
    int_set = colorsets["INT"]
    string_set = colorsets["STRING"]
    
    # Create Places
    p_int = Place("P_Int", int_set)
    p_str = Place("P_Str", string_set)
    p_out = Place("P_Out", int_set)
    
    # Create Transition with Guard
    # Guard checks x > 5. If x is bound to a string, this will fail.
    t = Transition("T", guard="x > 5", variables=["x", "y"])
    
    cpn = CPN()
    cpn.add_place(p_int)
    cpn.add_place(p_str)
    cpn.add_place(p_out)
    cpn.add_transition(t)
    
    # Add Arcs
    # x comes from P_Int, y comes from P_Str
    # Add P_Str arc first to ensure 'hello' is earlier in token_pool
    # and x gets bound to 'hello' first during backtracking.
    cpn.add_arc(Arc(p_str, t, "y"))
    cpn.add_arc(Arc(p_int, t, "x"))
    cpn.add_arc(Arc(t, p_out, "x"))
    
    # Create Marking
    marking = Marking()
    marking.set_tokens("P_Int", [10])
    marking.set_tokens("P_Str", ["hello"])
    
    # Simulation should succeed if the binding logic correctly handles types
    # or if the guard is evaluated after verifying the binding against input arcs.
    # Currently, it might try binding x="hello" and evaluate guard "hello" > 5 -> Crash
    context = EvaluationContext()
    # manual check enabled
    # We expect is_enabled to return True for correct binding and False for incorrect binding,
    # NOT raise TypeError.

    # If the bug exists, this might crash inside _find_binding or _check_enabled_with_binding
    enabled = cpn.is_enabled(t, marking, context)
    assert enabled == True

    # Fire
    cpn.fire_transition(t, marking, context)

    assert marking.get_multiset("P_Out").tokens == [Token(10)]
    assert marking.get_multiset("P_Str").tokens == []
    assert marking.get_multiset("P_Int").tokens == []

if __name__ == "__main__":
    test_guard_binding_bug()
