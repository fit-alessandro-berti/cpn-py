import copy
import types
from collections import Counter
from dataclasses import dataclass, field
from types import ModuleType
from cpnpy.cpn.colorsets import *
from collections import defaultdict
from typing import Any, Dict, List, Optional, Set, Union, Callable
from cpnpy.cpn.parser import InputArcParser

class InputView:
    def __init__(self, data: dict):
        self._data = data

    def __getattr__(self, name: str):
        if name in self._data:
            return self._data[name]
        raise AttributeError(name)

    def get(self, name: str, default=None):
        return self._data.get(name, default)


class OutputScope:
    def __init__(self):
        self._data = {}

    def __getattr__(self, name: str):
        if name in self._data:
            return self._data[name]
        raise AttributeError(name)

    def __setattr__(self, name: str, value):
        if name == "_data":
            super().__setattr__(name, value)
        else:
            self._data[name] = value

    def as_dict(self) -> dict:
        return dict(self._data)


TransitionAction = Callable[[InputView, OutputScope], None]


# -----------------------------------------------------------------------------------
# Token with Time
# -----------------------------------------------------------------------------------
@dataclass(frozen=True)
class Token:
    value: Any
    timestamp: int = 0 # For timed tokens

    def __repr__(self):
        if self.timestamp != 0:
            return f"Token({self.value}, timestamp={self.timestamp})"
        return f"Token({self.value})"


    def __copy__(self):
        # Shallow copy: values assumed to be immutable or just referenced
        return self  # immutable

    def __deepcopy__(self, memo):
        # Deepcopy value (in case it's a complex object)
        return Token(copy.deepcopy(self.value, memo), self.timestamp)


@dataclass
class Multiset:
    tokens: List[Token] = field(default_factory=list)

    def add(self, token_value: Any, timestamp: int = 0, count: int = 1):
        for _ in range(count):
            self.tokens.append(Token(token_value, timestamp))

    def remove(self, token_value: Any, count: int = 1):
        # Removing tokens that match token_value, preferring the ones with largest timestamp first
        matching = [t for t in self.tokens if t.value == token_value]
        if len(matching) < count:
            raise ValueError("Not enough tokens to remove.")
        matching.sort(key=lambda x: x.timestamp, reverse=True)
        to_remove = matching[:count]
        for tr in to_remove:
            self.tokens.remove(tr)

    def count_value(self, token_value: Any) -> int:
        return sum(1 for t in self.tokens if t.value == token_value)

    def __le__(self, other: 'Multiset') -> bool:
        self_counts = Counter(t.value for t in self.tokens)
        other_counts = Counter(t.value for t in other.tokens)
        for val, cnt in self_counts.items():
            if other_counts[val] < cnt:
                return False
        return True

    def __add__(self, other: 'Multiset') -> 'Multiset':
        return Multiset(self.tokens + other.tokens)

    def __sub__(self, other: 'Multiset') -> 'Multiset':
        result = Multiset(self.tokens[:])
        for t in other.tokens:
            result.remove(t.value, 1)
        return result

    def __repr__(self):
        items_str = ", ".join(str(t) for t in self.tokens)
        return f"{{{items_str}}}"

    def __copy__(self):
        cls = self.__class__
        result = cls.__new__(cls)
        # Shallow copy tokens list (but Token objects are referenced)
        result.tokens = self.tokens[:]
        return result

    def __deepcopy__(self, memo):
        cls = self.__class__
        result = cls.__new__(cls)
        memo[id(self)] = result
        # Deepcopy tokens
        result.tokens = [copy.deepcopy(t, memo) for t in self.tokens]
        return result


# -----------------------------------------------------------------------------------
# Marking with Global Clock
# -----------------------------------------------------------------------------------
class Marking:
    def __init__(self):
        self._marking: Dict[str, Multiset] = {}
        self.global_clock = 0  # Time support

    def set_tokens(self, place_name: str, tokens: List[Any], timestamps: Optional[List[int]] = None):
        if timestamps is None:
            timestamps = [0] * len(tokens)
        self._marking[place_name] = Multiset([Token(v, ts) for v, ts in zip(tokens, timestamps)])

    def add_tokens(self, place_name: str, token_values: List[Any], timestamp: int = 0):
        ms = self._marking.get(place_name, Multiset())
        for v in token_values:
            ms.add(v, timestamp=timestamp)
        self._marking[place_name] = ms

    def remove_tokens(self, place_name: str, token_values: List[Any]):
        ms = self._marking.get(place_name, Multiset())
        for v in token_values:
            ms.remove(v)
        self._marking[place_name] = ms

    def get_multiset(self, place_name: str) -> Multiset:
        return self._marking.get(place_name, Multiset())

    def __repr__(self):
        lines = [f"Marking (global_clock={self.global_clock}):"]
        for place, ms in self._marking.items():
            lines.append(f"  {place}: {ms}")
        if len(lines) == 1:
            lines.append("  (empty)")
        return "\n".join(lines)

    def __copy__(self):
        cls = self.__class__
        result = cls.__new__(cls)
        result.global_clock = self.global_clock
        # Shallow copy of marking dict and multiset references
        result._marking = {k: copy.copy(v) for k, v in self._marking.items()}
        return result

    def __deepcopy__(self, memo):
        cls = self.__class__
        result = cls.__new__(cls)
        memo[id(self)] = result
        result.global_clock = self.global_clock
        # Deepcopy marking dict and multisets
        result._marking = {k: copy.deepcopy(v, memo) for k, v in self._marking.items()}
        return result


# -----------------------------------------------------------------------------------
# EvaluationContext
# -----------------------------------------------------------------------------------
class EvaluationContext:
    def __init__(self, user_code: Optional[Union[str, ModuleType]] = None):
        self.env = {}
        if user_code is not None:
            if isinstance(user_code, str):
                exec(user_code, self.env)
            elif isinstance(user_code, ModuleType):
                self.env.update(user_code.__dict__)

    def evaluate_guard(self, guard_expr: Optional[str], binding: Dict[str, Any]) -> bool:
        if guard_expr is None:
            return True
        return bool(eval(guard_expr, self.env, binding))

    def _parse_expr_and_delay(self, arc_expr: str, binding: Dict[str, Any]) -> (str, int):
        delay = 0
        expr_part = arc_expr
        if "@+" in arc_expr:
            parts = arc_expr.split('@+')
            expr_part = parts[0].strip()
            delay_part = parts[1].strip()
            # Delay is usually a simple expression or number
            delay = eval(delay_part, self.env, binding)
        return expr_part, delay

    def evaluate_input_arc(self, arc_expr: str, binding: Dict[str, Any]) -> (List[Any], int):
        expr_part = arc_expr
        delay = 0

        from cpnpy.cpn.parser import InputArcParser
        parser = InputArcParser()
        
        parsed = parser.parse(expr_part)

        val = binding[parsed.variable]

        if parsed.is_multiset:
            return val, delay
        else:
            return [val], delay


    def evaluate_output_arc(self, arc_expr: str, binding: Dict[str, Any]) -> (List[Any], int):
        expr_part, delay = self._parse_expr_and_delay(arc_expr, binding)
        val = eval(expr_part, self.env, binding)

        if isinstance(val, list):
            return val, delay
        return [val], delay

    def evaluate_action(
        self,
        action: TransitionAction,
        binding: Dict[str, Any]
    ):
        inp = InputView(binding)
        out = OutputScope()

        # --- rebind function so its globals == self.env ---
        action_with_env = types.FunctionType(
            action.__code__,
            self.env,
            name=action.__name__,
            argdefs=action.__defaults__,
            closure=action.__closure__,
        )

        action_with_env(inp, out)

        return out

    def __copy__(self):
        cls = self.__class__
        result = cls.__new__(cls)
        # Shallow copy environment
        result.env = self.env.copy()
        return result

    def __deepcopy__(self, memo):
        cls = self.__class__
        result = cls.__new__(cls)
        memo[id(self)] = result
        # Deepcopy environment
        result.env = copy.deepcopy(self.env, memo)
        return result


# -----------------------------------------------------------------------------------
# Place, Transition, Arc, CPN with Time
# -----------------------------------------------------------------------------------
class Place:
    def __init__(self, name: str, colorset: ColorSet):
        self.name = name
        self.colorset = colorset

    def __repr__(self):
        return f"Place(name='{self.name}', colorset={repr(self.colorset)})"

    def __copy__(self):
        cls = self.__class__
        result = cls.__new__(cls)
        result.name = self.name
        # Shallow copy the colorset (assuming ColorSet is immutable or already handles deepcopy)
        result.colorset = self.colorset
        return result

    def __deepcopy__(self, memo):
        cls = self.__class__
        result = cls.__new__(cls)
        memo[id(self)] = result
        result.name = copy.deepcopy(self.name, memo)
        # Deepcopy colorset
        result.colorset = copy.deepcopy(self.colorset, memo)
        return result



# -------------------------
# Transition
# -------------------------
class Transition:
    def __init__(
        self,
        name: str,
        guard: Optional[str] = None,
        variables: Optional[List[str]] = None,
        action: Optional[TransitionAction] = None,
        transition_delay: int = 0,
        priority: int = 0,  # lower value => higher priority
    ):
        self.name = name
        self.guard_expr = guard
        self.variables = variables if variables else []
        self.action = action
        self.transition_delay = transition_delay
        self.priority = int(priority)

    def __repr__(self):
        guard_str = repr(self.guard_expr) if self.guard_expr is not None else "None"
        vars_str = f'[' + ", ".join(map(lambda v: "'" + v + "'", self.variables)) + ']' if self.variables else "None"
        action_str = repr(self.action) if self.action is not None else "None"
        return f"Transition(name='{self.name}', guard={guard_str}, variables={vars_str}, action={action_str}, transition_delay={self.transition_delay}, priority={self.priority})"

    def __copy__(self):
        cls = self.__class__
        result = cls.__new__(cls)
        result.name = self.name
        result.guard_expr = self.guard_expr
        result.variables = self.variables[:]
        result.action = self.action
        result.transition_delay = self.transition_delay
        result.priority = self.priority
        return result

    def __deepcopy__(self, memo):
        cls = self.__class__
        result = cls.__new__(cls)
        memo[id(self)] = result
        result.name = copy.deepcopy(self.name, memo)
        result.guard_expr = copy.deepcopy(self.guard_expr, memo)
        result.variables = copy.deepcopy(self.variables, memo)
        result.action = copy.deepcopy(self.action, memo)
        result.transition_delay = self.transition_delay
        result.priority = copy.deepcopy(self.priority, memo)
        return result


class Arc:
    def __init__(self, source: Union['Place', 'Transition'], target: Union['Place', 'Transition'], expression: str):
        self.source = source
        self.target = target
        self.expression = expression

    def __repr__(self):
        src_name = self.source.name if isinstance(self.source, Place) else self.source.name
        tgt_name = self.target.name if isinstance(self.target, Place) else self.target.name
        return f"Arc(source='{src_name}', target='{tgt_name}', expression='{self.expression}')"

    def __copy__(self):
        cls = self.__class__
        result = cls.__new__(cls)
        result.source = self.source  # shallow ref
        result.target = self.target  # shallow ref
        result.expression = self.expression
        return result

    def __deepcopy__(self, memo):
        cls = self.__class__
        result = cls.__new__(cls)
        memo[id(self)] = result
        result.source = copy.deepcopy(self.source, memo)
        result.target = copy.deepcopy(self.target, memo)
        result.expression = copy.deepcopy(self.expression, memo)
        return result


class CPN:
    def __init__(self):
        self.places: List[Place] = []
        self.transitions: List[Transition] = []
        self.arcs: List[Arc] = []

    def add_place(self, place: Place):
        self.places.append(place)

    def add_transition(self, transition: Transition):
        self.transitions.append(transition)

    def add_arc(self, arc: Arc):
        self.arcs.append(arc)

    def get_place_by_name(self, name: str) -> Optional[Place]:
        for p in self.places:
            if p.name == name:
                return p
        return None

    def get_transition_by_name(self, name: str) -> Optional[Transition]:
        for t in self.transitions:
            if t.name == name:
                return t
        return None

    def get_input_arcs(self, t: Transition) -> List[Arc]:
        return [a for a in self.arcs if isinstance(a.source, Place) and a.target == t]

    def get_output_arcs(self, t: Transition) -> List[Arc]:
        return [a for a in self.arcs if a.source == t and isinstance(a.target, Place)]

    def is_enabled(self, t: Transition, marking: Marking, context: EvaluationContext,
                   binding: Optional[Dict[str, Any]] = None) -> bool:
        if binding is None:
            binding = self._find_binding(t, marking, context)
            if binding is None:
                return False
        return self._check_enabled_with_binding(t, marking, context, binding)

    def fire_transition(self, t: Transition, marking: Marking, context: EvaluationContext,
                        binding: Optional[Dict[str, Any]] = None):
        if binding is None:
            binding = self._find_binding(t, marking, context)
            if binding is None:
                raise RuntimeError(f"No valid binding found for transition {t.name}.")
        if not self._check_enabled_with_binding(t, marking, context, binding):
            raise RuntimeError(f"Transition {t.name} is not enabled under the found binding.")

        # Remove tokens
        for arc in self.get_input_arcs(t):
            values, _ = context.evaluate_input_arc(arc.expression, binding)
            marking.remove_tokens(arc.source.name, values)

        # Execute action if any
        out = None
        if t.action is not None:
            out = context.evaluate_action(t.action, binding)

        # Add tokens with proper timestamps
        locals_after_action = {}
        locals_after_action.update(binding)
        if out is not None:
            locals_after_action.update(out.as_dict())
        for arc in self.get_output_arcs(t):
            values, arc_delay = context.evaluate_output_arc(arc.expression, locals_after_action)
            for v in values:
                place = arc.target

                # validate token value against place colorset
                if not place.colorset.is_member(v):
                    raise Exception(f"Token value {v} is not a member of colorset {place.colorset} for place {place.name}")

                new_timestamp = marking.global_clock + t.transition_delay + arc_delay
                if place.colorset.timed:
                    marking.add_tokens(place.name, [v], timestamp=new_timestamp)
                else:
                    marking.add_tokens(place.name, [v], timestamp=0)

    def _check_enabled_with_binding(self, t: Transition, marking: Marking, context: EvaluationContext,
                                    binding: Dict[str, Any]) -> bool:
        if t.guard_expr:
            if not context.evaluate_guard(t.guard_expr, binding):
                return False
        # Check input arcs and timestamps
        for arc in self.get_input_arcs(t):
            values, _ = context.evaluate_input_arc(arc.expression, binding)
            place_marking = marking.get_multiset(arc.source.name)
            # Check if we have enough ready tokens (timestamp <= global_clock)
            for val in values:
                ready_tokens = [tok for tok in place_marking.tokens if
                                tok.value == val and tok.timestamp <= marking.global_clock]
                if len(ready_tokens) < values.count(val):
                    return False
        return True

    def _find_binding(self, t: Transition, marking: Marking, context: EvaluationContext) -> Optional[Dict[str, Any]]:
        parser = InputArcParser()
        
        # 1. Parse all input arcs to determine where variables come from
        # Map: variable_name -> list of (place_name, count, is_multiset)
        var_sources = defaultdict(list)
        input_arcs = self.get_input_arcs(t)
        
        for arc in input_arcs:
            parsed = parser.parse(arc.expression)
            var_sources[parsed.variable].append({
                'place': arc.source.name,
                'count': parsed.count,
                'is_multiset': parsed.is_multiset
            })

        # We will backtrack over variables
        return self._backtrack_binding_v2(t.variables, var_sources, marking, context, t, {}, {})

    def _backtrack_binding_v2(self, variables: List[str], var_sources: Dict[str, List[dict]], 
                              marking: Marking, context: EvaluationContext, t: Transition, 
                              partial_binding: Dict[str, Any], used_tokens_map: Dict[str, Set[int]]) -> Optional[Dict[str, Any]]:
        if not variables:
            if self._check_enabled_with_binding(t, marking, context, partial_binding):
                return partial_binding
            return None
            
        var = variables[0]
        sources = var_sources.get(var)
        
        if not sources:
            # Variable not found in any input arc (maybe only in guard/output? but needs binding)
            # Cannot proceed.
            return None
            
        # For now, assume a variable appears in exactly one input arc for binding purposes 
        # (or if multiple, they must match, which is complex).
        # Let's take the first source for generating candidates.
        source = sources[0]
        place_name = source['place']
        count = source['count']
        is_multiset = source['is_multiset']
        
        place_tokens = marking.get_multiset(place_name).tokens
        valid_tokens = [(i, tok) for i, tok in enumerate(place_tokens) 
                        if tok.timestamp <= marking.global_clock and i not in used_tokens_map.get(place_name, set())]
        
        # If multiset binding (binding to a list of values)
        if is_multiset:
            # We need to pick 'count' tokens from valid_tokens
            import itertools
            # combinations returns tuples of (index, token)
            for combo in itertools.combinations(valid_tokens, count):
                indices = {x[0] for x in combo}
                values = [x[1].value for x in combo]
                
                new_binding = dict(partial_binding)
                new_binding[var] = values # Bind to LIST of values
                
                # Update used tokens
                new_used = {k: v.copy() for k, v in used_tokens_map.items()}
                if place_name not in new_used: new_used[place_name] = set()
                new_used[place_name].update(indices)
                
                res = self._backtrack_binding_v2(variables[1:], var_sources, marking, context, t, new_binding, new_used)
                if res: return res
        else:
            # Single value binding
            # We need to pick ONE value 'v' such that there are 'count' occurrences of it?
            # Or does the parser count imply we need to consume 'count' tokens of that value?
            # Standard CPN: "3`x" -> x is single value, consume 3 tokens of value x.
            # BUT user requirement: "N`var - Binds N tokens to var (where var becomes a list)".
            # AND "var" or "[var]" -> single token.
            
            # Implementation for count=1 (standard)
            # Try each available token
            seen_values = set()
            seen_unhashable = []
            for idx, tok in valid_tokens:
                val = tok.value
                is_hashable = False
                try:
                    hash(val)
                    is_hashable = True
                except TypeError:
                    pass

                if is_hashable:
                    if val in seen_values:
                        continue
                    seen_values.add(val)
                else:
                    if val in seen_unhashable:
                        continue
                    seen_unhashable.append(val)
                
                new_binding = dict(partial_binding)
                new_binding[var] = val
                
                new_used = {k: v.copy() for k, v in used_tokens_map.items()}
                if place_name not in new_used: new_used[place_name] = set()
                new_used[place_name].add(idx)
                
                res = self._backtrack_binding_v2(variables[1:], var_sources, marking, context, t, new_binding, new_used)
                if res: return res
                
        return None

    def _find_all_bindings(self, t: Transition, marking: Marking, context: EvaluationContext) -> List[Dict[str, Any]]:
        from cpnpy.cpn.parser import InputArcParser
        parser = InputArcParser()
        var_sources = defaultdict(list)
        input_arcs = self.get_input_arcs(t)
        for arc in input_arcs:
            parsed = parser.parse(arc.expression)
            var_sources[parsed.variable].append({
                'place': arc.source.name, 
                'count': parsed.count, 
                'is_multiset': parsed.is_multiset
            })

        solutions = []
        self._backtrack_all_bindings(t.variables, var_sources, marking, context, t, {}, {}, solutions)
        return solutions

    def _backtrack_all_bindings(self, variables: List[str], var_sources: Dict[str, List[dict]],
                                marking: Marking, context: EvaluationContext, t: Transition,
                                partial_binding: Dict[str, Any], used_tokens_map: Dict[str, Set[int]],
                                solutions: List[Dict[str, Any]]):
        if not variables:
            if self._check_enabled_with_binding(t, marking, context, partial_binding):
                solutions.append(dict(partial_binding))
            return

        var = variables[0]
        sources = var_sources.get(var)
        if not sources: return 
        
        source = sources[0]
        place_name = source['place']
        count = source['count']
        is_multiset = source['is_multiset']
        
        place_tokens = marking.get_multiset(place_name).tokens
        valid_tokens = [(i, tok) for i, tok in enumerate(place_tokens) 
                        if tok.timestamp <= marking.global_clock and i not in used_tokens_map.get(place_name, set())]

        if is_multiset:
            import itertools
            for combo in itertools.combinations(valid_tokens, count):
                indices = {x[0] for x in combo}
                values = [x[1].value for x in combo]
                
                new_binding = dict(partial_binding)
                new_binding[var] = values
                
                new_used = {k: v.copy() for k, v in used_tokens_map.items()}
                if place_name not in new_used: new_used[place_name] = set()
                new_used[place_name].update(indices)
                
                self._backtrack_all_bindings(variables[1:], var_sources, marking, context, t, new_binding, new_used, solutions)
        else:
            # Single value binding
            seen_values = set()
            seen_unhashable = []
            for idx, tok in valid_tokens:
                val = tok.value
                is_hashable = False
                try:
                    hash(val)
                    is_hashable = True
                except TypeError:
                    pass

                if is_hashable:
                    if val in seen_values:
                        continue
                    seen_values.add(val)
                else:
                    if val in seen_unhashable:
                        continue
                    seen_unhashable.append(val)
                
                new_binding = dict(partial_binding)
                new_binding[var] = val
                
                new_used = {k: v.copy() for k, v in used_tokens_map.items()}
                if place_name not in new_used: new_used[place_name] = set()
                new_used[place_name].add(idx)
                
                self._backtrack_all_bindings(variables[1:], var_sources, marking, context, t, new_binding, new_used, solutions)

    def advance_global_clock(self, marking: Marking):
        future_ts = []
        for ms in marking._marking.values():
            for tok in ms.tokens:
                if tok.timestamp > marking.global_clock:
                    future_ts.append(tok.timestamp)
        if future_ts:
            marking.global_clock = min(future_ts)

    def __repr__(self):
        places_str = "\n    ".join(repr(p) for p in self.places)
        transitions_str = "\n    ".join(repr(t) for t in self.transitions)
        arcs_str = "\n    ".join(repr(a) for a in self.arcs)
        return (f"CPN(\n  Places:\n    {places_str}\n\n"
                f"  Transitions:\n    {transitions_str}\n\n"
                f"  Arcs:\n    {arcs_str}\n)")

    def __copy__(self):
        cls = self.__class__
        result = cls.__new__(cls)
        # Shallow copy: references to the same place/transition/arc objects
        result.places = self.places[:]
        result.transitions = self.transitions[:]
        result.arcs = self.arcs[:]
        return result

    def __deepcopy__(self, memo):
        cls = self.__class__
        result = cls.__new__(cls)
        memo[id(self)] = result
        result.places = copy.deepcopy(self.places, memo)
        result.transitions = copy.deepcopy(self.transitions, memo)
        result.arcs = copy.deepcopy(self.arcs, memo)
        return result


# -----------------------------------------------------------------------------------
# Example Usage (Timed)
# -----------------------------------------------------------------------------------
if __name__ == "__main__":
    # Example with timed color sets
    cs_definitions = """
    colset INT = int timed;
    colset STRING = string;
    colset PAIR = product(INT, STRING) timed;
    """

    parser = ColorSetParser()
    colorsets = parser.parse_definitions(cs_definitions)

    int_set = colorsets["INT"]
    pair_set = colorsets["PAIR"]

    p_int = Place("P_Int", int_set)  # timed place
    p_pair = Place("P_Pair", pair_set)  # timed place
    t = Transition("T", guard="x > 10", variables=["x"], transition_delay=2)

    cpn = CPN()
    cpn.add_place(p_int)
    cpn.add_place(p_pair)
    cpn.add_transition(t)
    cpn.add_arc(Arc(p_int, t, "x"))
    cpn.add_arc(Arc(t, p_pair, "(x, 'hello') @+5"))

    marking = Marking()
    marking.set_tokens("P_Int", [5, 12])  # both at timestamp 0
    print(cpn)
    print(marking)

    user_code = """
def double(n):
    return n*2
"""
    context = EvaluationContext(user_code=user_code)

    # Check enabling with explicit binding
    print("Is T enabled with x=5?", cpn.is_enabled(t, marking, context, binding={"x": 5}))
    print("Is T enabled with x=12?", cpn.is_enabled(t, marking, context, binding={"x": 12}))

    # Check enabled without providing a binding
    print("Is T enabled without explicit binding?", cpn.is_enabled(t, marking, context))

    # Find all possible bindings
    all_bindings = cpn._find_all_bindings(t, marking, context)
    print("All possible bindings for T:", all_bindings)

    # Fire the transition (this should consume the token with value 12)
    cpn.fire_transition(t, marking, context)
    print(marking)

    # Advance global clock
    cpn.advance_global_clock(marking)
    print("After advancing global clock:", marking.global_clock)
