# <<EXPORTER MODIFIED>>
import json
import os
from collections import Counter, OrderedDict # Using OrderedDict for explicit order guarantee (safe for older Python)
from typing import Any, Dict, List, Optional, Set, Union

# Import the CPN classes from your existing cpnpy structure
from cpnpy.cpn.cpn_imp import (
    Marking,
    CPN,
    Place,
    Transition,
    Arc,
    Token,
    Multiset,
    EvaluationContext,
)

# Import all color set classes and the parser from colorsets.py
from cpnpy.cpn.colorsets import (
    ColorSet,
    IntegerColorSet,
    RealColorSet,
    StringColorSet,
    BoolColorSet,
    UnitColorSet,
    IntInfColorSet,
    TimeColorSet,
    EnumeratedColorSet,
    ProductColorSet,
    DictionaryColorSet,
    ListColorSet,
    ColorSetParser, RecordColorSet,
)

# -----------------------------------------------------------------------------------
# Helper function to find all unique colorsets recursively
# -----------------------------------------------------------------------------------
def find_all_colorsets(cpn: CPN) -> Set[ColorSet]:
    """ Gathers all unique ColorSet instances used in the CPN places, including constituents. """
    all_unique_colorsets = set()
    processed_in_this_call = set() # To avoid redundant processing within this function call

    initial_colorsets = {p.colorset for p in cpn.places}

    for initial_cs in initial_colorsets:
        stack = [initial_cs]
        while stack:
            cs = stack.pop()
            if cs in processed_in_this_call:
                continue
            processed_in_this_call.add(cs)
            all_unique_colorsets.add(cs)

            # Add constituents to the stack for processing
            if isinstance(cs, ProductColorSet):
                if cs.cs1 not in processed_in_this_call:
                    stack.append(cs.cs1)
                if cs.cs2 not in processed_in_this_call:
                    stack.append(cs.cs2)
            elif isinstance(cs, ListColorSet):
                if cs.element_cs not in processed_in_this_call:
                    stack.append(cs.element_cs)
            # Add other composite types here if they exist

    return all_unique_colorsets

# -----------------------------------------------------------------------------------
# Exporter functions (Modified)
# -----------------------------------------------------------------------------------

def generate_color_set_definitions(cpn: CPN):
    """
    Generate definitions for all distinct color sets used in the CPN, using the types
    from colorsets.py. Prioritizes original names and preserves logical dependency order.

    Returns a tuple (colorset_to_name_map, name_to_definition_map),
    where:
      - colorset_to_name_map: Dict[ColorSet, str] (mapping each ColorSet instance to its final name)
      - name_to_definition_map: OrderedDict[str, str] (mapping each final name to its 'colset' definition string,
                                                     preserving insertion order)
    """
    colorset_to_name = {}
    # Use OrderedDict to guarantee insertion order reflects dependency resolution
    name_to_def = OrderedDict()
    # Keep track of names used to prevent clashes if different objects have the same original name
    # or if a generated name clashes with an original one.
    used_definition_names = set()
    generated_name_counter = 0

    def get_unique_generated_name():
        nonlocal generated_name_counter
        while True:
            name = f"CS{generated_name_counter}"
            generated_name_counter += 1
            if name not in used_definition_names:
                return name

    def define_colorset(cs: ColorSet) -> str:
        nonlocal generated_name_counter
        # If this specific ColorSet instance is already defined, return its assigned name
        if cs in colorset_to_name:
            return colorset_to_name[cs]

        # --- Determine the name for this colorset ---
        assigned_name = None
        # Prefer original name if available and not already used for a *different* object
        if cs.name is not None and cs.name not in used_definition_names:
            assigned_name = cs.name
        else:
            # Either no original name, or the original name is already taken. Generate one.
            assigned_name = get_unique_generated_name()
            # If cs.name existed but clashed, we might want to log a warning here.

        # Mark this name as used for definitions and map the object to the name
        used_definition_names.add(assigned_name)
        colorset_to_name[cs] = assigned_name

        # --- Generate the definition string ---
        timed_str = " timed" if cs.timed else ""
        base_def = ""

        # Handle each known color set subclass
        if isinstance(cs, IntegerColorSet):
            base_def = f"colset {assigned_name} = int{timed_str};"
        elif isinstance(cs, RealColorSet):
            base_def = f"colset {assigned_name} = real{timed_str};"
        elif isinstance(cs, StringColorSet):
            base_def = f"colset {assigned_name} = string{timed_str};"
        elif isinstance(cs, BoolColorSet):
            base_def = f"colset {assigned_name} = bool{timed_str};"
        elif isinstance(cs, UnitColorSet):
            base_def = f"colset {assigned_name} = unit{timed_str};"
        elif isinstance(cs, IntInfColorSet):
            base_def = f"colset {assigned_name} = intinf{timed_str};"
        elif isinstance(cs, TimeColorSet):
            base_def = f"colset {assigned_name} = time{timed_str};"
        elif isinstance(cs, DictionaryColorSet):
            base_def = f"colset {assigned_name} = dict{timed_str};"
        elif isinstance(cs, EnumeratedColorSet):
            enumerations = ", ".join(f"'{v}'" for v in cs.values)
            base_def = f"colset {assigned_name} = {{ {enumerations} }}{timed_str};"
        elif isinstance(cs, ProductColorSet):
            # *** Recursive call ensures constituents are defined first ***
            cs1_name = define_colorset(cs.cs1)
            cs2_name = define_colorset(cs.cs2)
            base_def = f"colset {assigned_name} = product({cs1_name}, {cs2_name}){timed_str};"
        elif isinstance(cs, ListColorSet):
            # *** Recursive call ensures constituent is defined first ***
            sub_name = define_colorset(cs.element_cs)
            base_def = f"colset {assigned_name} = list {sub_name}{timed_str};"
        elif isinstance(cs, RecordColorSet):
            field_defs = []
            for field_name, field_cs in cs.field_types:
                field_cs_name = define_colorset(field_cs)
                field_defs.append(f"{field_name}: {field_cs_name}")
            fields_str = ", ".join(field_defs)
            base_def = f"colset {assigned_name} = record {{ {fields_str} }}{timed_str};"
        else:
            # Clean up potentially assigned name if we error out
            if assigned_name in used_definition_names:
                 used_definition_names.remove(assigned_name)
            if cs in colorset_to_name:
                 del colorset_to_name[cs]
            raise ValueError(f"Unknown ColorSet type during export: {type(cs)}")

        # Add the definition to the ordered dictionary *after* constituents are processed
        name_to_def[assigned_name] = base_def
        return assigned_name

    # --- Main part of generate_color_set_definitions ---
    # 1. Find all unique ColorSet objects (including constituents)
    all_cs_objects = find_all_colorsets(cpn)

    # 2. Define each unique colorset. The recursive calls in define_colorset
    #    will handle dependencies and ensure correct insertion order into name_to_def.
    for cs_obj in all_cs_objects:
        define_colorset(cs_obj) # Call ensures it and its dependencies are defined

    return colorset_to_name, name_to_def


def export_cpn_to_json(
    cpn: CPN,
    marking: Marking,
    context: Optional[EvaluationContext],
    output_json_path: str,
    output_py_path: Optional[str] = None
):
    """
    Exports a given CPN, Marking, and optional EvaluationContext to a JSON file.
    Preserves original ColorSet names and logical definition order.
    Also dumps user-provided Python code (if any) to output_py_path and references
    that file in the resulting JSON for future re-import or usage.
    """
    # Generate color set definitions (name_to_def is now an OrderedDict)
    cs_to_name, name_to_def = generate_color_set_definitions(cpn)

    # Places
    places_json = []
    for p in cpn.places:
        # Use the generated map to find the correct name (original or generated)
        cs_name = cs_to_name.get(p.colorset)
        if cs_name is None:
             # This should ideally not happen if find_all_colorsets worked correctly
             raise RuntimeError(f"Failed to find a mapped name for colorset of place {p.name}")
        places_json.append({
            "name": p.name,
            "colorSet": cs_name
        })

    # Transitions (also gather arcs here)
    transitions_json = []
    for t in cpn.transitions:
        in_arcs = []
        out_arcs = []
        # It's more efficient to iterate arcs once and check source/target type
        for arc in cpn.arcs:
            if arc.target == t and isinstance(arc.source, Place):
                in_arcs.append({
                    "place": arc.source.name,
                    "expression": arc.expression
                })
            elif arc.source == t and isinstance(arc.target, Place):
                out_arcs.append({
                    "place": arc.target.name,
                    "expression": arc.expression
                })

        t_json = {
            "name": t.name,
            "inArcs": in_arcs,
            "outArcs": out_arcs
        }
        if t.guard_expr is not None:
            t_json["guard"] = t.guard_expr
        # Ensure variables is only added if it's not empty
        if t.variables:
            t_json["variables"] = t.variables
        if t.transition_delay != 0:
            t_json["transitionDelay"] = t.transition_delay

        transitions_json.append(t_json)

    # Initial Marking
    initial_marking = {}
    for pname, ms in marking._marking.items():
        # Ensure place exists in the CPN model before adding marking
        place = cpn.get_place_by_name(pname)
        if not place:
            print(f"Warning: Marking found for place '{pname}' which is not in the CPN model. Skipping.")
            continue

        # Extract tokens and timestamps correctly from Multiset
        tokens = [tok.value for tok in ms.tokens]
        timestamps = [tok.timestamp for tok in ms.tokens]

        # Only include timestamps if the place's colorset is timed OR if any token has a non-zero timestamp
        include_timestamps = place.colorset.timed or any(ts != 0 for ts in timestamps)

        marking_data = {"tokens": tokens}
        if include_timestamps:
             marking_data["timestamps"] = timestamps

        initial_marking[pname] = marking_data


    # Get color set definitions in the correct order (from OrderedDict)
    # *** REMOVED SORTING LOGIC ***
    ordered_defs = list(name_to_def.values())

    # Evaluation Context handling (remains the same)
    evaluation_context_val = None
    if context is not None:
        # Assuming user code might be stored directly or referenced via a special key
        user_code = context.env.get('__original_user_code__', None) # Example key
        if isinstance(user_code, str) and user_code.strip():
            # If user_code looks like a file path and exists, store the path
            if os.path.sep in user_code and os.path.isfile(user_code):
                 evaluation_context_val = user_code
            else:
                # Otherwise, it's inline code. Write to a .py file if path specified.
                if output_py_path is None:
                    # Default filename if none provided
                    output_py_path = os.path.join(os.path.dirname(output_json_path), "user_code_exported.py")
                    print(f"Warning: output_py_path not specified for inline code. Writing to {output_py_path}")

                try:
                    # Ensure directory exists
                    #os.makedirs(os.path.dirname(output_py_path), exist_ok=True)
                    with open(output_py_path, "w") as f:
                        f.write(user_code)
                    evaluation_context_val = output_py_path
                except Exception as e:
                    print(f"Error writing user code to {output_py_path}: {e}")
                    evaluation_context_val = None # Indicate failure

    # Build the final JSON structure
    final_json = {
        # Use the correctly ordered list of definitions
        "colorSets": ordered_defs,
        "places": places_json,
        "transitions": transitions_json,
        "initialMarking": initial_marking,
        # Only include evaluationContext if it was successfully determined
        **({"evaluationContext": evaluation_context_val} if evaluation_context_val else {})
    }

    # Write to JSON file
    try:
         # Ensure directory exists
         #os.makedirs(os.path.dirname(output_json_path), exist_ok=True)
         with open(output_json_path, "w") as f:
             json.dump(final_json, f, indent=2)
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"Error writing CPN JSON to {output_json_path}: {e}")
        return None # Indicate failure

    return final_json


# -----------------------------------------------------------------------------------
# Example Usage (using the modified exporter)
# -----------------------------------------------------------------------------------
if __name__ == "__main__":
    # --- Define ColorSets using the parser ---
    # Make sure colorsets.py defines the ColorSetParser and ColorSet classes correctly
    cs_parser = ColorSetParser()
    try:
        cs_defs = cs_parser.parse_definitions("""\
colset INT = int timed;
colset STRING = string;
colset BASIC_ENUM = { 'A', 'B' };
colset PAIR = product(INT, STRING) timed;
colset LIST_ENUM = list BASIC_ENUM;
""")
        # --- Access parsed colorsets ---
        int_set = cs_defs["INT"]
        string_set = cs_defs["STRING"] # Needed for PAIR definition, parser handles this
        pair_set = cs_defs["PAIR"]
        basic_enum_set = cs_defs["BASIC_ENUM"]
        list_enum_set = cs_defs["LIST_ENUM"]

        # --- Create CPN elements ---
        p_int = Place("P_Int", int_set) # Uses INT
        p_pair = Place("P_Pair", pair_set) # Uses PAIR (depends on INT, STRING)
        p_list = Place("P_List", list_enum_set) # Uses LIST_ENUM (depends on BASIC_ENUM)

        # Create a place using an unnamed, programmatically defined colorset
        prog_enum_set = EnumeratedColorSet(['X', 'Y'], timed=True) # No 'name' attribute set here
        p_prog = Place("P_Prog", prog_enum_set)

        # Create a place reusing a base type directly
        p_str = Place("P_Str", string_set) # Uses STRING


        t1 = Transition("T1", guard="x > 10", variables=["x"], transition_delay=2)
        t2 = Transition("T2", variables=["l"])


        # --- Construct the net ---
        cpn = CPN()
        cpn.add_place(p_int)
        cpn.add_place(p_pair)
        cpn.add_place(p_list)
        cpn.add_place(p_prog) # Add place with programmatically defined CS
        cpn.add_place(p_str)  # Add place reusing STRING

        cpn.add_transition(t1)
        cpn.add_transition(t2)

        # Arcs for T1
        cpn.add_arc(Arc(p_int, t1, "x"))
        # Output includes timestamp delay
        cpn.add_arc(Arc(t1, p_pair, "(x, 'processed') @+ 5"))
        # Also output original value to string place (untimed)
        cpn.add_arc(Arc(t1, p_str, "'original was ' + str(x)"))

        # Arcs for T2
        cpn.add_arc(Arc(p_list, t2, "l"))
        # Output to the programmatically defined place
        cpn.add_arc(Arc(t2, p_prog, "['X'] @+ 1")) # Outputting a list, but place expects 'X' or 'Y'. Should error on simulation, but export is fine.


        # --- Initial Marking ---
        marking = Marking()
        # Add timed tokens to P_Int
        marking.set_tokens("P_Int", [5, 12], timestamps=[0, 2]) # Token 12 arrives at time 2
        # Add untimed tokens to P_List (even though ListColorSet itself wasn't marked timed)
        marking.set_tokens("P_List", [['A'], ['A', 'B']])
        # Add timed token to P_Prog
        marking.set_tokens("P_Prog", ['Y'], timestamps=[10])


        # --- Evaluation Context ---
        user_code = """
import math

def check_list(items):
    print(f"Checking list: {items}")
    return len(items) > 0
"""
        # Store the code string itself in the context for potential export
        context = EvaluationContext(user_code=user_code)
        context.env['__original_user_code__'] = user_code # Make it explicit

        # --- Export ---
        output_dir = "cpn_export_test"
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
        json_file = os.path.join(output_dir, "cpn_export_ordered.json")
        py_file = os.path.join(output_dir, "user_code_exported.py")

        print(f"Exporting CPN to {json_file}...")
        exported_data = export_cpn_to_json(
            cpn, marking, context,
            output_json_path=json_file,
            output_py_path=py_file # Explicitly provide path for user code
        )
        print(exported_data)

        if exported_data:
            print("\nExport successful. Resulting JSON structure:")
            # Print limited part of JSON for brevity
            print("{")
            print(f'  "colorSets": {json.dumps(exported_data["colorSets"], indent=4)},')
            print(f'  "places": {json.dumps(exported_data["places"], indent=4)},')
            print(f'  "transitions": [...],')
            print(f'  "initialMarking": {json.dumps(exported_data["initialMarking"], indent=4)},')
            print(f'  "evaluationContext": {json.dumps(exported_data.get("evaluationContext"))}')
            print("}")
            print(f"\nUser code saved to: {py_file}")
        else:
            print("\nExport failed.")

    except ImportError as e:
        print(f"\nError: Could not import necessary CPN or ColorSet modules.")
        print(f"Details: {e}")
        print("Please ensure cpnpy.cpn.cpn_imp and cpnpy.cpn.colorsets are accessible.")
    except ValueError as e:
        print(f"\nError during ColorSet parsing or CPN setup: {e}")
    except Exception as e:
        print(f"\nAn unexpected error occurred: {e}")
        import traceback
        traceback.print_exc()

# <<END OF EXPORTER MODIFIED>>