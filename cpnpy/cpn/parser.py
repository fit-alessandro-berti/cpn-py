import re
from dataclasses import dataclass
from typing import Optional

@dataclass
class ParsedArc:
    variable: str
    count: int = 1
    
    @property
    def is_multiset(self) -> bool:
        return self.count > 1

class InputArcParser:
    def parse(self, expression: str) -> ParsedArc:
        expr = expression.strip()
        
        # 1. Simple variable: "x"
        if re.fullmatch(r"^[a-zA-Z_][a-zA-Z0-9_]*$", expr):
            return ParsedArc(variable=expr, count=1)
            
        # 2. Bracketed variable: "[x]"
        match_bracket = re.fullmatch(r"^\[([a-zA-Z_][a-zA-Z0-9_]*)\]$", expr)
        if match_bracket:
            return ParsedArc(variable=match_bracket.group(1), count=1)
            
        # 3. Multiset syntax: "3`x" or "3 ` x"
        match_multiset = re.fullmatch(r"^(\d+)\s*`\s*([a-zA-Z_][a-zA-Z0-9_]*)$", expr)
        if match_multiset:
            count = int(match_multiset.group(1))
            var = match_multiset.group(2)
            # count determines is_multiset property
            return ParsedArc(variable=var, count=count)

        raise ValueError(f"Input arc expression '{expression}' is not supported by the whitelist parser. Supported formats: 'var', '[var]', 'N`var'.")
