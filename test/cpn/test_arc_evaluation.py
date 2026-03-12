import pytest
from cpnpy.cpn.cpn_imp import CPN, Place, Transition, Arc, Marking, EvaluationContext
from cpnpy.cpn.colorsets import IntegerColorSet, StringColorSet, ProductColorSet

def test_evaluate_input_arc_no_delay_parsing():
    """Verify that input arcs do NOT parse @+ as delay."""
    cpn = CPN()
    p1 = Place("P1", IntegerColorSet())
    t = Transition("T1", variables=["x"])
    cpn.add_place(p1)
    cpn.add_transition(t)
    
    # Input arc with delay syntax should be treated as literal expression "x @+ 5"
    # This will likely fail parsing because "x @+ 5" is not a whitelisted variable name.
    # We expect ValueError from Parser.
    arc_expr = "x @+ 5" 
    
    context = EvaluationContext()
    binding = {"x": 10}
    
    # Normally binding generation handles parsing, but here we test evaluate_input_arc directly
    # parser.parse("x @+ 5") should fail.
    
    with pytest.raises(ValueError):
        context.evaluate_input_arc(arc_expr, binding)

def test_evaluate_output_arc_delay():
    """Verify that output arcs correctly parse delays."""
    context = EvaluationContext()
    binding = {"x": 10}
    
    # Output arc with delay: "x @+ 5"
    # evaluate_output_arc returns (values, delay)
    values, delay = context.evaluate_output_arc("x @+ 5", binding)
    
    assert values == [10]
    assert delay == 5

def test_evaluate_output_arc_complex_expression():
    """Verify complex output expressions (tuple, function call)."""
    context = EvaluationContext()
    binding = {"x": 10, "y": 20}
    
    # Expression: "(x, y)" -> tuple
    values, delay = context.evaluate_output_arc("(x, y)", binding)
    assert values == [(10, 20)]
    assert delay == 0
    
    # Expression: "[x, y]" -> list
    # evaluate_output_arc returns list as-is if result is list
    values, delay = context.evaluate_output_arc("[x, y]", binding)
    assert values == [10, 20] # List of 2 tokens
    assert delay == 0

def test_evaluate_output_arc_function_call():
    """Verify function calls in output expressions."""
    user_code = """
def add(a, b):
    return a + b
"""
    context = EvaluationContext(user_code=user_code)
    binding = {"x": 10, "y": 20}
    
    # Expression: "add(x, y)"
    values, delay = context.evaluate_output_arc("add(x, y)", binding)
    assert values == [30]
    assert delay == 0

if __name__ == "__main__":
    test_evaluate_input_arc_no_delay_parsing()
    test_evaluate_output_arc_delay()
    test_evaluate_output_arc_complex_expression()
    test_evaluate_output_arc_function_call()
