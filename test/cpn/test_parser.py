import pytest
from cpnpy.cpn.parser import InputArcParser, ParsedArc

def test_parse_simple_var():
    parser = InputArcParser()
    parsed = parser.parse("x")
    assert parsed.variable == "x"
    assert parsed.count == 1
    assert parsed.is_multiset == False

def test_parse_bracketed_var():
    parser = InputArcParser()
    parsed = parser.parse("[x]")
    assert parsed.variable == "x"
    assert parsed.count == 1
    assert parsed.is_multiset == False

def test_parse_multiset_syntax():
    parser = InputArcParser()
    parsed = parser.parse("3`x")
    assert parsed.variable == "x"
    assert parsed.count == 3
    assert parsed.is_multiset == True

def test_parse_multiset_syntax_single():
    # 1`x should be parsed as count=1, is_multiset=False (scalar binding)
    parser = InputArcParser()
    parsed = parser.parse("1`x")
    assert parsed.variable == "x"
    assert parsed.count == 1
    assert parsed.is_multiset == False

def test_parse_multiset_syntax_inverted():
    parser = InputArcParser()
    # Assuming standard CPN Tools syntax: 3`x. "x`3" should raise ValueError.
    with pytest.raises(ValueError):
        parser.parse("x`3")

def test_parse_invalid_syntax():
    parser = InputArcParser()
    with pytest.raises(ValueError):
        parser.parse("x+1")
    with pytest.raises(ValueError):
        parser.parse("[x, x]")
    with pytest.raises(ValueError):
        parser.parse("1`x + 2`y") # Complex expressions not supported yet for binding

def test_whitespace_handling():
    parser = InputArcParser()
    parsed = parser.parse("  3 ` x  ")
    assert parsed.variable == "x"
    assert parsed.count == 3
    assert parsed.is_multiset == True

if __name__ == "__main__":
    test_parse_simple_var()
    test_parse_bracketed_var()
    test_parse_multiset_syntax()
    test_parse_multiset_syntax_single()
    test_parse_invalid_syntax()
    test_whitespace_handling()
