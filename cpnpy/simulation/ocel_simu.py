from cpnpy.cpn.cpn_imp import *
import copy
import pandas as pd
import random
from pm4py.objects.ocel.obj import OCEL


def simulate_cpn_to_ocel(cpn: CPN, initial_marking: Marking, context: EvaluationContext) -> OCEL:
    """
    Simulate the given CPN starting from the given initial marking, and return an OCEL object.
    Each fired transition is recorded as an event.
    Input and output tokens for each event are considered as related objects.
    The object type is derived from the place's color set.
    """
    marking = copy.deepcopy(initial_marking)

    # Data structures to build the OCEL
    event_list = []
    object_set = set()
    relation_list = []

    event_counter = 1

    # Helper to safely get object ID as a hashable value (stringify if necessary)
    def make_object_id(value):
        return str(value)

    # Helper to determine object type from a place's color set
    def get_object_type_from_colorset(place):
        return place.colorset.name

    # Run simulation until no transition is enabled
    while True:
        enabled_transitions = []
        # Check which transitions are enabled
        transitions = list(cpn.transitions)
        random.shuffle(transitions)
        for t in transitions:
            if cpn.is_enabled(t, marking, context):
                enabled_transitions.append(t)

        if not enabled_transitions:
            # No transitions enabled, try to advance time
            old_clock = marking.global_clock
            cpn.advance_global_clock(marking)
            if marking.global_clock == old_clock:
                # No advancement in time means we are done
                break
            else:
                # After advancing clock, check again
                continue

        # Lower value => higher priority. Only choose among best-priority transitions.
        best_pri = min(getattr(t, "priority", 0) for t in enabled_transitions)
        best = [t for t in enabled_transitions if getattr(t, "priority", 0) == best_pri]

        # choose one (random among ties to avoid bias)
        t = random.choice(best)

        binding = cpn._find_binding(t, marking, context)
        if binding is None:
            # If no binding found, skip (should be rare)
            break

        # Add a minuscule increment (1 microsecond per event) to the event timestamp
        event_timestamp = pd.to_datetime(marking.global_clock, unit='s', utc=True) + pd.to_timedelta(event_counter,
                                                                                                     unit='us')

        # The activity is the transition name
        activity = t.name

        # Identify related objects from input and output arcs
        related_objects = set()

        # For input arcs
        for arc in cpn.get_input_arcs(t):
            values, _ = context.evaluate_input_arc(arc.expression, binding)
            otype = get_object_type_from_colorset(arc.source)  # derive from source place's color set
            for v in values:
                obj_id = make_object_id(v)
                related_objects.add((obj_id, otype))

        # Fire transition (this will modify the marking)
        cpn.fire_transition(t, marking, context, binding)

        # For output arcs
        for arc in cpn.get_output_arcs(t):
            values, _ = context.evaluate_output_arc(arc.expression, binding)
            otype = get_object_type_from_colorset(arc.target)  # derive from target place's color set
            for v in values:
                obj_id = make_object_id(v)
                related_objects.add((obj_id, otype))

        # Event ID
        eid = f"e_{event_counter}"
        event_counter += 1

        # Add event to event_list
        event_list.append({
            "ocel:eid": eid,
            "ocel:activity": activity,
            "ocel:timestamp": event_timestamp
        })

        # Add objects and relations
        for (oid, otype) in related_objects:
            object_set.add((oid, otype))
            relation_list.append({
                "ocel:eid": eid,
                "ocel:activity": activity,
                "ocel:timestamp": event_timestamp,
                "ocel:oid": oid,
                "ocel:type": otype,
                "ocel:qualifier": None
            })

    # Create dataframes
    events_df = pd.DataFrame(event_list)
    objects_df = pd.DataFrame([
        {"ocel:oid": oid, "ocel:type": otype}
        for (oid, otype) in object_set
    ])
    relations_df = pd.DataFrame(relation_list)

    # Create OCEL object
    ocel = OCEL(
        events=events_df,
        objects=objects_df,
        relations=relations_df
    )

    return ocel
