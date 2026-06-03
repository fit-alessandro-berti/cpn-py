import streamlit as st
from cpnpy.cpn.cpn_imp import (
    CPN, Place, Transition, Arc, Marking, EvaluationContext,
    ColorSetParser,
)
from cpnpy.visualization.visualizer_st import CPNStreamlitVisualizer


def build_cpn():
    """
    Build a more complex demo CPN with:
    1. integer flow
    2. string source/destination places
    3. boolean places for even/odd classification
    4. untimed and timed transitions
    """
    parser = ColorSetParser()
    colorsets = parser.parse_definitions("""
        colset INT = int;
        colset TINT = int timed;
        colset STR = string;
        colset TSTR = string timed;
        colset BOOL = bool;
    colset DICT = dict;
    colset RECORD_TYPE = record id:INT * val:STR;
    colset INT_LIST = list INT;
    """)

    int_set = colorsets["INT"]
    tint_set = colorsets["TINT"]
    str_set = colorsets["STR"]
    tstr_set = colorsets["TSTR"]
    bool_set = colorsets["BOOL"]
    dict_set = colorsets["DICT"]
    record_set = colorsets["RECORD_TYPE"]
    list_set = colorsets["INT_LIST"]

    # Places
    p_numbers = Place("P_Numbers", int_set)
    p_buffer = Place("P_Buffer", tint_set)          # timed integer place
    p_even = Place("P_Even", bool_set)
    p_odd = Place("P_Odd", bool_set)

    p_source = Place("P_Source", str_set)
    p_dest = Place("P_Dest", str_set)
    p_in_transit = Place("P_InTransit", tstr_set)   # timed string place

    p_dicts = Place("P_Dicts", dict_set)
    p_records = Place("P_Records", record_set)
    p_collected = Place("P_Collected", list_set)

    # Transitions
    # Untimed transition: increment integer before sending to timed buffer
    t_inc = Transition("T_Increment", guard="x < 5", variables=["x"], transition_delay=2, priority=2)

    # Untimed transitions: classify parity
    t_even = Transition("T_IsEven", guard="x % 2 == 0", variables=["x"], priority=2)
    t_odd = Transition("T_IsOdd", guard="x % 2 == 1", variables=["x"], priority=3)

    # Timed behavior: route string token from source to in-transit with delay
    t_send = Transition("T_Send", variables=["s"], transition_delay=1, priority=10)

    # Untimed delivery from timed place to destination
    t_deliver = Transition("T_Deliver", variables=["s"], action="log_deliver(s)", priority=5)

    # Complex Type Transitions (using Action Blocks)
    t_to_dict = Transition("T_ToDict", variables=["x"], 
                         action="output['d'] = {'id': x, 'val': 'd_' + str(x)}", 
                         priority=2)
    
    t_to_record = Transition("T_ToRecord", variables=["x"], 
                           action="output['r'] = {'id': x, 'val': 'r_' + str(x)}", 
                           priority=2)
    
    t_accumulate = Transition("T_Accumulate", variables=["x", "l"], 
                            action="output['new_l'] = l + [x]", 
                            priority=2)

    # Build CPN
    cpn = CPN()

    for place in [
        p_numbers, p_buffer, p_even, p_odd,
        p_source, p_dest, p_in_transit,
        p_dicts, p_records, p_collected
    ]:
        cpn.add_place(place)

    for transition in [t_inc, t_even, t_odd, t_send, t_deliver, t_to_dict, t_to_record, t_accumulate]:
        cpn.add_transition(transition)

    # ----- Integer flow -----

    # P_Numbers --(x)--> T_Increment --(x + 1 @+ 2)--> P_Buffer
    cpn.add_arc(Arc(p_numbers, t_inc, "x"))
    cpn.add_arc(Arc(t_inc, p_buffer, "x + 1 @+ 2"))

    # P_Buffer --(x)--> T_IsEven --(True)--> P_Even
    cpn.add_arc(Arc(p_buffer, t_even, "x"))
    cpn.add_arc(Arc(t_even, p_even, "True"))

    # P_Buffer --(x)--> T_IsOdd --(True)--> P_Odd
    cpn.add_arc(Arc(p_buffer, t_odd, "x"))
    cpn.add_arc(Arc(t_odd, p_odd, "True"))

    # ----- String flow -----

    # P_Source --(s)--> T_Send --(s @+ 3)--> P_InTransit
    cpn.add_arc(Arc(p_source, t_send, "s"))
    cpn.add_arc(Arc(t_send, p_in_transit, "s @+ 3"))

    # P_InTransit --(s)--> T_Deliver --(s)--> P_Dest
    cpn.add_arc(Arc(p_in_transit, t_deliver, "s"))
    cpn.add_arc(Arc(t_deliver, p_dest, "s"))

    # ----- Complex Record & List flow -----
    
    # P_Numbers --(x)--> T_ToDict --(d)--> P_Dicts
    cpn.add_arc(Arc(p_numbers, t_to_dict, "x"))
    cpn.add_arc(Arc(t_to_dict, p_dicts, "d"))

    # P_Numbers --(x)--> T_ToRecord --(r)--> P_Records
    cpn.add_arc(Arc(p_numbers, t_to_record, "x"))
    cpn.add_arc(Arc(t_to_record, p_records, "r"))

    # P_Numbers --(x)--> T_Accumulate
    # P_Collected --(l)--> T_Accumulate --(new_l)--> P_Collected
    cpn.add_arc(Arc(p_numbers, t_accumulate, "x"))
    cpn.add_arc(Arc(p_collected, t_accumulate, "l"))
    cpn.add_arc(Arc(t_accumulate, p_collected, "new_l"))

    # Initial marking
    marking = Marking()
    marking.set_tokens("P_Numbers", [0, 1, 2, 3, 4])
    marking.set_tokens("P_Source", ["node_A", "node_B"])
    marking.set_tokens("P_Collected", [[]])

    user_code = """
def log_deliver(s):
    print(f"Log: Delivering packet {s}")
"""
    context = EvaluationContext(user_code=user_code)

    return cpn, marking, context


def main():
    st.set_page_config(layout="wide", page_title="CPN-py Visualizer")
    st.title("CPN-py Interactive Visualizer")

    if "cpn_built" not in st.session_state:
        cpn, marking, context = build_cpn()
        st.session_state["demo_cpn"]     = cpn
        st.session_state["demo_marking"] = marking
        st.session_state["demo_context"] = context
        st.session_state["cpn_built"]    = True

    cpn     = st.session_state["demo_cpn"]
    context = st.session_state["demo_context"]

    viz = CPNStreamlitVisualizer(
        cpn,
        st.session_state["demo_marking"],
        context=context,
        session_key="demo_marking",
    )
    viz.render(height=800)


if __name__ == "__main__":
    main()
