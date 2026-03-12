import networkx as nx
from typing import Tuple, Set, Callable, Any, Dict
from collections import deque
from cpnpy.cpn.cpn_imp import *


def make_hashable(obj: Any) -> Any:
    """
    Recursively convert lists, sets, and dicts into tuples/frozensets so that
    the resulting object is hashable. Strings, ints, and other hashable types
    are left as is.
    """
    if isinstance(obj, list):
        return tuple(make_hashable(e) for e in obj)
    elif isinstance(obj, set):
        return frozenset(make_hashable(e) for e in obj)
    elif isinstance(obj, dict):
        return tuple(sorted((make_hashable(k), make_hashable(v)) for k, v in obj.items()))
    else:
        return obj


def equiv_marking_to_key(marking: Marking) -> Tuple[int, Tuple[Tuple[str, Tuple[Any, ...]], ...]]:
    """
    Convert a Marking object into a canonical representative of its equivalence class.
    """
    place_entries = []
    for place_name, ms in sorted(marking._marking.items(), key=lambda x: x[0]):
        if not ms.tokens:
            continue
        # Convert tokens to a sorted tuple of (value, timestamp), ensuring both are hashable
        token_list = tuple(
            sorted((make_hashable(t.value), make_hashable(t.timestamp)) for t in ms.tokens)
        )
        place_entries.append((place_name, token_list))
    return (marking.global_clock, tuple(place_entries))


def equiv_binding(binding: Dict[str, Any]) -> Tuple[Tuple[str, Any], ...]:
    """
    Convert a binding dictionary into a canonical representative of its equivalence class.
    """
    # Ensure binding values are hashable
    return tuple(sorted((k, make_hashable(v)) for k, v in binding.items()))


def copy_marking(original: Marking) -> Marking:
    """
    Create a deep copy of a marking.
    """
    new_marking = Marking()
    new_marking.global_clock = original.global_clock
    for place_name, ms in original._marking.items():
        tokens_copy = [Token(t.value, t.timestamp) for t in ms.tokens]
        new_marking._marking[place_name] = Multiset(tokens_copy)
    return new_marking


def build_reachability_graph(
        cpn: CPN,
        initial_marking: Marking,
        context: EvaluationContext,
        marking_equiv_func: Callable[[Marking], Any] = equiv_marking_to_key,
        binding_equiv_func: Callable[[Dict[str, Any]], Any] = equiv_binding
) -> nx.DiGraph:
    """
    Build the reachability graph of the given CPN starting from initial_marking.
    """
    RG = nx.DiGraph()
    visited: Set[Any] = set()
    queue = deque()

    init_key = marking_equiv_func(initial_marking)
    RG.add_node(init_key, marking=copy_marking(initial_marking))
    visited.add(init_key)
    queue.append(init_key)

    while queue:
        current_key = queue.popleft()
        current_marking = RG.nodes[current_key]['marking']

        # Find all enabled transitions and their bindings
        enabled_transitions = []
        for t in cpn.transitions:
            bindings = cpn._find_all_bindings(t, current_marking, context)
            for b in bindings:
                enabled_transitions.append((t, b))

        # If no transitions are enabled, attempt to advance the global clock
        if not enabled_transitions:
            old_clock = current_marking.global_clock
            cpn.advance_global_clock(current_marking)
            if current_marking.global_clock > old_clock:
                # Check if transitions are now enabled
                new_enabled_transitions = []
                for t in cpn.transitions:
                    bindings = cpn._find_all_bindings(t, current_marking, context)
                    for b in bindings:
                        new_enabled_transitions.append((t, b))
                enabled_transitions = new_enabled_transitions

        # For each enabled transition and binding, generate successor marking
        for (trans, binding) in enabled_transitions:
            successor_marking = copy_marking(current_marking)
            # Fire transition
            cpn.fire_transition(trans, successor_marking, context, binding)

            succ_key = marking_equiv_func(successor_marking)
            if succ_key not in visited:
                RG.add_node(succ_key, marking=successor_marking)
                visited.add(succ_key)
                queue.append(succ_key)

            canonical_binding = binding_equiv_func(binding)
            RG.add_edge(current_key, succ_key, transition=trans.name, binding=canonical_binding)

    return RG


# Example usage (place this in a separate script if needed):
if __name__ == "__main__":
    # Example: A simple CPN and initial marking
    cs_definitions = """
    colset INT = int;
    """
    parser = ColorSetParser()
    colorsets = parser.parse_definitions(cs_definitions)

    int_set = colorsets["INT"]
    p1 = Place("P1", int_set)
    p2 = Place("P2", int_set)

    t = Transition("T", guard="x < 5", variables=["x"])
    cpn = CPN()
    cpn.add_place(p1)
    cpn.add_place(p2)
    cpn.add_transition(t)
    cpn.add_arc(Arc(p1, t, "x"))
    cpn.add_arc(Arc(t, p2, "x+1"))

    initial_marking = Marking()
    initial_marking.set_tokens("P1", [0, 1, 2, 3, 4])

    context = EvaluationContext()

    # Build the reachability graph with equivalence
    RG = build_reachability_graph(cpn, initial_marking, context)

    # Print the reachability graph
    print("Nodes (Equivalence Classes):")
    for n in RG.nodes(data=True):
        print(n)

    print("\nEdges (With Equivalence Classes):")
    for e in RG.edges(data=True):
        print(e)
