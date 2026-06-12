# cpnpy

`cpnpy` is a Python-based library designed to simulate Colored Petri Nets (CPNs) with optional time semantics. It provides classes and functions to define places, transitions, arcs, and markings, along with color sets and evaluation contexts to express guards, arc expressions, and timed behavior.

**Key features include:**
- Defining color sets (including `int`, `real`, `string`, enumerated, record, list, dict, and product types) with optional timing.
- Creating places and transitions, each associated with a specific color set and optional guard conditions, **transition priority**, and **action blocks**.
- Specifying arcs with expressions and delays that determine how tokens move through the net.
- Managing tokens as multisets of timed or untimed values.
- Simulating CPN behavior: checking transition enabling, firing transitions, advancing time, and running until deadlock (`simulate_until_deadlock`).
- **Interactive Streamlit visualizer** — step/batch simulation, monitors, graph layout, and firing animation (`examples/streamlit_demo.py`).

**Documentation (newer features, user perspective):**

- [USER_GUIDE.md](USER_GUIDE.md) — priority, actions, record/list types, Streamlit UI, monitors, batch modes, graph layout (since commit `30528abf`)
- [Streamlit visualizer developer patterns](docs/solutions/architecture-patterns/streamlit-visualizer-simplification-patterns.md) — rerun semantics and refactoring notes for contributors
- [Domain vocabulary](CONCEPTS.md) — shared terms (marking, monitors, batch phases, etc.)

---

## Installation

You can install `cpnpy` from Pypi using the command:
```bash
pip install -U cnpy
```

You can install `cpnpy` directly from source:
```bash
pip install -e .
```

---

## Basic Concepts

### Color Sets

Color sets define the domain of values that tokens can take. They can be:
- **Integer, Real, and String sets**, optionally timed.
- **Enumerated sets**, like `{ 'red', 'green' }`.
- **Product sets**, such as `product(INT, STRING)`, optionally timed.

**Example:**
```python
from cpnpy.cpn.colorsets import ColorSetParser

cs_defs = """
colset INT = int timed;
colset STRING = string;
colset PAIR = product(INT, STRING) timed;
"""
parser = ColorSetParser()
colorsets = parser.parse_definitions(cs_defs)
int_set = colorsets["INT"]    # timed integer set
pair_set = colorsets["PAIR"]  # timed product of (INT, STRING)
```

### Places

A `Place` holds a multiset of tokens, each token conforming to the place's color set. If the color set is timed, the tokens will carry timestamps.

**Example:**
```python
from cpnpy.cpn.cpn_imp import Place

p_int = Place("P_Int", int_set)      # A place for timed integers
p_pair = Place("P_Pair", pair_set)   # A place for timed pairs (int, string)
```

### Markings

A `Marking` represents a state of the net, holding the current tokens in each place, as well as a global clock.

**Example:**
```python
from cpnpy.cpn.cpn_imp import Marking

marking = Marking()
marking.set_tokens("P_Int", [5, 12])  # Two integer tokens (5, 12) with timestamp = 0
print(marking)
# Marking (global_clock=0):
#   P_Int: {Token(5), Token(12)}
```

### Transitions and Guards

A `Transition` may have a guard expression and variables. When the transition fires, tokens are consumed from its input places and produced in its output places. Guards and arc expressions can refer to these variables.

**Example:**
```python
from cpnpy.cpn.cpn_imp import Transition

t = Transition("T",
               guard="x > 10",      # a Python expression evaluated with the binding {x: token_value}
               variables=["x"],
               transition_delay=2)  # delay after firing, affects token timestamps on output arcs
```

### Arcs and Expressions

Arcs connect places and transitions. Arc expressions determine which tokens are taken or produced. If timed arcs are used (e.g. `@+5`), produced tokens will have an additional delay.

**Example:**
```python
from cpnpy.cpn.cpn_imp import Arc

# Arc from place P_Int to transition T, consuming a token bound to variable x
arc_in = Arc(p_int, t, "x")

# Arc from transition T to place P_Pair, producing a token (x, 'hello') delayed by an additional 5 time units
arc_out = Arc(t, p_pair, "(x, 'hello') @+5")
```

### Putting It Together: The CPN

A `CPN` ties together places, transitions, and arcs.

**Example:**
```python
from cpnpy.cpn.cpn_imp import CPN, EvaluationContext

cpn = CPN()
cpn.add_place(p_int)
cpn.add_place(p_pair)
cpn.add_transition(t)
cpn.add_arc(arc_in)
cpn.add_arc(arc_out)

user_code = """
def double(n):
    return n * 2
"""
context = EvaluationContext(user_code=user_code)
```

---

## Simulation Steps

1. **Check if a Transition is Enabled**

   `is_enabled` checks if a transition can fire given the current marking and context. It tries to find a token binding that satisfies the guard and provides enough tokens.

   ```python
   print("Is T enabled with x=5?", cpn.is_enabled(t, marking, context, binding={"x": 5}))
   # False, since guard x > 10 fails for x=5
   print("Is T enabled with x=12?", cpn.is_enabled(t, marking, context, binding={"x": 12}))
   # True, since guard x > 10 succeeds for x=12
   ```

   If you don't provide a binding, `is_enabled` tries to find one automatically:
   ```python
   print("Is T enabled without explicit binding?", cpn.is_enabled(t, marking, context))
   # True (it finds x=12 as a suitable binding)
   ```

2. **Find All Possible Bindings**

   If multiple tokens can satisfy the guard and arc expressions, `_find_all_bindings` returns all valid bindings:
   
   ```python
   all_bindings = cpn._find_all_bindings(t, marking, context)
   print("All possible bindings for T:", all_bindings)
   # E.g. [{'x': 12}] if only the token 12 satisfies the guard.
   ```

3. **Firing a Transition**

   When a transition fires, it consumes tokens from input places and produces tokens in output places, updating their timestamps based on the transition and arc delays:
   
   ```python
   cpn.fire_transition(t, marking, context)
   print(marking)
   # Marking now has consumed the token 12 from P_Int and added a token to P_Pair with a proper timestamp.
   ```

4. **Advancing the Global Clock**

   The global clock in the marking can be advanced to the next available token timestamp. This models the passage of time:
   
   ```python
   cpn.advance_global_clock(marking)
   print("After advancing global clock:", marking.global_clock)
   # global_clock might now match the timestamp of the next future token.
   ```

5. **Run until deadlock (script)**

   For unattended simulation without the UI:

   ```python
   from cpnpy.simulation.simu import simulate_until_deadlock

   final_marking = simulate_until_deadlock(cpn, marking, context, max_steps=1000, max_time=100)
   ```

   See [USER_GUIDE.md](USER_GUIDE.md) for priority filtering and transition selection behavior.

---

## Minimal Example

```python
from cpnpy.cpn.cpn_imp import CPN, Place, Transition, Arc, Marking, EvaluationContext
from cpnpy.cpn.colorsets import ColorSetParser

# Define color sets
cs_defs = "colset INT = int timed;"
parser = ColorSetParser()
colorsets = parser.parse_definitions(cs_defs)
int_set = colorsets["INT"]

# Create places and a transition
p_in = Place("P_In", int_set)
p_out = Place("P_Out", int_set)
t = Transition("T", guard="x > 0", variables=["x"], transition_delay=1)

# Create arcs: consume 'x' from P_In, produce 'x+1' in P_Out after 2 time units
arc_in = Arc(p_in, t, "x")
arc_out = Arc(t, p_out, "double(x) @+2")

# Build the net
cpn = CPN()
cpn.add_place(p_in)
cpn.add_place(p_out)
cpn.add_transition(t)
cpn.add_arc(arc_in)
cpn.add_arc(arc_out)

# Create a marking
marking = Marking()
marking.set_tokens("P_In", [1, -1])  # both at time 0

# Evaluation context with a user-defined function
user_code = "def double(n): return n*2"
context = EvaluationContext(user_code=user_code)

print("Initial marking:")
print(marking)

# Check enabling
print("Is T enabled?", cpn.is_enabled(t, marking, context))
# True, because x=1 is a positive token.

# Fire the transition
cpn.fire_transition(t, marking, context)
print("After firing T:")
print(marking)
# Token (1) is consumed from P_In, token 2 (double(1)) is added to P_Out with timestamp = global_clock + 1 (transition_delay) + 2 (arc delay) = 3

# Advance time
cpn.advance_global_clock(marking)
print("After advancing clock:", marking.global_clock)
# global_clock = 3
```

---

## Importing a CPN from JSON

You can define your CPN in a JSON file and import it using `importer.py`. The JSON must follow the structure enforced by `files/validation.schema`.

**Example:**
```python
import json
from cpnpy.cpn.importer import import_cpn_from_json

with open("cpn_definition.json", "r") as f:
    data = json.load(f)

cpn, marking, context = import_cpn_from_json(data)

# Now 'cpn' is a CPN object, 'marking' is the initial marking, and 'context' is the evaluation context.
```

**Key Points:**
- The `colorSets` field in the JSON should be a list of color set definitions, each ending with a `;`.
- `places`, `transitions`, and `initialMarking` define the net structure and initial state.
- `evaluationContext` can specify a file path or inline code snippet for user-defined functions.

---

## Exporting a CPN to JSON

You can also export an existing CPN and marking to a JSON file that matches the schema. The `exporter.py` provides this functionality:

**Example:**
```python
from cpnpy.cpn.exporter import export_cpn_to_json

# Assuming you have a CPN, marking, and context objects as before
exported_json = export_cpn_to_json(cpn, marking, context, "cpn_exported.json", "user_code_exported.py")

# The exported_json dictionary will have all the data. 
# Additionally, the JSON will be written to "cpn_exported.json".
# If user code was embedded, it is exported to "user_code_exported.py".
```

---

## Validation Against the Schema

The JSON format is defined by `files/validation_schema.json`. You can use a JSON Schema validator (such as `jsonschema`) to ensure your input JSON is valid:

```bash
pip install jsonschema
```

**Example:**
```python
import json
import jsonschema

with open("cpn_definition.json") as f:
    data = json.load(f)
with open("files/validation_schema.json") as sf:
    schema = json.load(sf)

jsonschema.validate(instance=data, schema=schema)
print("JSON is valid!")
```

If the JSON is invalid, `jsonschema` will raise a `jsonschema.exceptions.ValidationError` with details.

---

## Simulation to an Object-Centric Event Log (OCEL)

In addition to simulating token movements and time advancements, `cpnpy` can also record the simulation trace in an object-centric event log (OCEL) format. This allows for a richer representation of process executions, where events are related to multiple objects of potentially different types, rather than just a single process instance.

The function below demonstrates how to simulate a given CPN from a specified initial marking and store each fired transition as an event in an OCEL object. Each event references the objects involved (i.e., tokens from input and output places) and their associated types, inferred from the places’ color sets. The resulting OCEL can then be analyzed using object-centric process mining techniques.

**Key points of the simulation:**
- The simulation runs until no transitions are enabled and no further advancement in time is possible.
- Each fired transition becomes an event in the OCEL.
- The tokens consumed and produced by firing a transition determine which objects the event references.
- Objects are typed according to the color sets of the places they originate from or go to.
- The simulation assigns timestamps and unique identifiers to events and objects.
- Finally, an `OCEL` object (from `pm4py`) is created, containing three main tables:
  - `events` with one row per fired transition.
  - `objects` listing the encountered objects and their types.
  - `relations` linking events to their related objects.

---

## Discovery from Event Logs with `cpnpy.discovery.traditional.apply(...)`

You can automatically create a Colored Petri Net (CPN) from a traditional event log by calling the `apply` function in `cpnpy.discovery.traditional`. This function:

1. Discovers an accepting Petri net (and its initial and final markings) from the provided event log.
2. Optionally applies decision mining to discover guard expressions on transitions.
3. Builds a CPN, associating each place with a color set and each transition with optional guards and stochastic timing.
4. Populates an initial marking with a configurable number of cases (tokens), optionally drawn from real cases in the original log to preserve their attributes.
5. Returns the resulting `CPN`, an initial `Marking`, and an `EvaluationContext` for handling stochastic distributions or custom Python functions.

**Function Signature**  
```python
cpn, marking, context = cpnpy.discovery.traditional.apply(log: EventLog, parameters: Optional[Dict[str, Any]] = None)
```

**Parameters**
- **log** (`pm4py.objects.log.obj.EventLog`): The input event log to be converted into a colored Petri net.
- **parameters** (`Dict[str, Any]`, *optional*): A dictionary of configuration parameters:
  - `num_simulated_cases` (`int`): Number of initial tokens (cases) placed in the initial marking (default: 1).
  - `pro_disc_alg` (`Callable`): The process discovery method used to derive the Petri net from the event log (default: `pm4py.discover_petri_net_inductive`).
  - `original_case_attributes` (`Set[str]`): A set of attributes that will be assigned to each token (e.g., `{"case:concept:name"}`).
  - `enable_guards_discovery` (`bool`): If `True`, decision mining is used to discover guard expressions that constrain transitions (default: `False`).
  - `original_log_cases_in_im` (`bool`): If `True`, real case attributes from the log are used to populate the initial marking. Otherwise, artificial cases are created (default: `True` if any guard is discovered, otherwise `False`).

**Returns**
- **cpn** (`cpnpy.cpn.cpn_imp.CPN`): The constructed Colored Petri Net with places, transitions, and arcs.
- **marking** (`cpnpy.cpn.cpn_imp.Marking`): The initial marking, containing the configured number of tokens (cases) with their attributes.
- **context** (`cpnpy.cpn.cpn_imp.EvaluationContext`): An evaluation context enabling stochastic distribution evaluation and custom Python functions.

**Example Usage**
```python
from pm4py.objects.log.importer.xes import importer as xes_importer
from cpnpy.discovery.traditional import apply
from cpnpy.cpn.cpn_imp import CPN, Marking, EvaluationContext

# Import an event log using PM4Py
log = xes_importer.apply("my_event_log.xes")

# Run discovery with guard mining enabled
cpn, marking, context = apply(log, parameters={
    "num_simulated_cases": 5,
    "enable_guards_discovery": True
})

print("Constructed CPN:", cpn)
print("Initial Marking:", marking)
print("Evaluation Context:", context)
```

By default, this approach uses the inductive miner algorithm (from `pm4py`) to discover a Petri net, optionally adds guards discovered via decision mining, and then constructs a CPN with an initial marking containing real or artificial case tokens.

---

## State Space Analysis with `StateSpaceAnalyzer`

`cpnpy` provides a built-in `StateSpaceAnalyzer` that can construct and analyze the *reachability graph (RG)* and *strongly connected components (SCC)* graph of a given CPN. It extracts valuable properties like min/max tokens in each place, dead markings, liveness of transitions, and more.

**Usage**

```python
from cpnpy.analysis.analyzer import StateSpaceAnalyzer
from cpnpy.cpn.cpn_imp import CPN, Marking, EvaluationContext

# Define a CPN and marking (possibly with timed places, transitions, etc.)
cpn = CPN()
# ... add places, transitions, arcs ...

marking = Marking()
# ... set initial tokens ...

# Create an evaluation context (optional, if you have custom functions or distributions)
context = EvaluationContext(user_code="""
def my_function(x):
    return x + 1
""")

# Build the analyzer
analyzer = StateSpaceAnalyzer(cpn, marking, context)

# Compute and retrieve summary statistics
report = analyzer.summarize()

print("=== State Space Report ===")
for key, val in report.items():
    print(f"{key}: {val}")
```

### Internally, the `StateSpaceAnalyzer` does the following:

1. **Reachability Graph Construction:**  
   Uses `build_reachability_graph` to explore all possible states (markings) from the initial marking, applying transitions and storing reached states as nodes in a directed graph.

2. **Strongly Connected Components (SCC) Graph:**  
   Once the RG is built, `build_scc_graph` is used to identify SCCs, which can reveal looping behaviors or terminal states.

3. **Properties and Methods:**
   - **`get_statistics()`**: Returns basic metrics about the RG (number of nodes, arcs) and the SCC graph.
   - **`is_reachable(from_node, to_node)`**: Checks if there is a path in the RG from one marking (node) to another.
   - **`get_place_bounds()`**: Provides the minimum and maximum token counts observed for each place across all reachable states.
   - **`get_place_multiset_bounds()`**: Tracks the min/max count of each distinct token value per place.
   - **`list_home_markings()`**: Identifies *home markings*, or states that appear in a unique terminal SCC.
   - **`list_dead_markings()`**: Lists markings with no enabled transitions.
   - **`list_dead_transitions()`**: Transitions that never enable in the entire state space.
   - **`list_live_transitions()`**: (Heuristic) Transitions that appear in all terminal SCCs, indicating they remain enabled in the “end” states.
   - **`list_impartial_transitions()`**: (Heuristic) Transitions that might occur infinitely often in all infinite occurrence sequences.
   - **`summarize()`**: Provides a combined dictionary of the above analyses.

### Example: Building and Analyzing a State Space

```python
from cpnpy.cpn.colorsets import ColorSetParser
from cpnpy.cpn.cpn_imp import CPN, Place, Transition, Arc, Marking, EvaluationContext
from cpnpy.analysis.analyzer import StateSpaceAnalyzer

# Define color sets
cs_definitions = """
colset INT = int timed;
colset STRING = string;
colset PAIR = product(INT, STRING) timed;
"""
parser = ColorSetParser()
colorsets = parser.parse_definitions(cs_definitions)
int_set = colorsets["INT"]
pair_set = colorsets["PAIR"]

# Create a simple CPN
p_int = Place("P_Int", int_set)
p_pair = Place("P_Pair", pair_set)
t = Transition("T", guard="x > 10", variables=["x"], transition_delay=2)

cpn = CPN()
cpn.add_place(p_int)
cpn.add_place(p_pair)
cpn.add_transition(t)
cpn.add_arc(Arc(p_int, t, "x"))
cpn.add_arc(Arc(t, p_pair, "(x, 'hello') @+5"))

# Create a marking
marking = Marking()
marking.set_tokens("P_Int", [5, 12])

# Define any custom logic if needed
user_code = """
def double(n):
    return n*2
"""
context = EvaluationContext(user_code=user_code)

# Analyze state space
analyzer = StateSpaceAnalyzer(cpn, marking, context)
report = analyzer.summarize()

print("=== State Space Analysis Report ===")
for key, val in report.items():
    print(f"{key}: {val}")
```

This approach helps you *exhaustively* understand your CPN’s behavior, including potential deadlocks, live transitions, and bounds on token populations.

---

## Interoperability with CPN Tools (CPN XML)

`cpnpy` offers **conversion** support for importing CPN Tools’ XML files into the library’s JSON-based format, as well as generating a **stub** CPN XML from `cpnpy` JSON. This two-way conversion enables you to leverage the original CPN Tools environment while working with `cpnpy`’s Python-based simulation framework:

1. **From CPN XML to JSON:**  
   - The XML structure (including places, transitions, and arcs) is mapped to the `cpnpy` JSON formalism. 
   - Since CPN Tools uses **Standard ML** for its guards and arc expressions, these expressions must be translated into **Python**. To assist with this, `cpnpy` can invoke a **Large Language Model** (via utility functions in `cpnpy.util.llm_json_fixing`) to attempt an automatic conversion of Standard ML snippets into Python code.  
   - **Example**: See [`examples/conversion/xml_to_json/importing_mynet.py`](examples/conversion/xml_to_json/importing_mynet.py) for a working script that demonstrates how to import an original CPN Tools XML file into a JSON definition suitable for `cpnpy`.

2. **From JSON to CPN XML (Stub):**  
   - You can also produce a minimal CPN Tools XML file from a `cpnpy` JSON definition. 
   - This is a “stub” XML that usually requires **further manual editing** if your workflow needs advanced, tool-specific CPN XML features that exceed the scope of the JSON schema.  
   - **Example**: See [`examples/conversion/json_to_xml/auto_discovery.py`](examples/conversion/json_to_xml/auto_discovery.py) for an end-to-end example of exporting `cpnpy` JSON to CPN XML.

---

## Graphical Interface (Streamlit visualizer)

`cpnpy` includes an interactive **Streamlit** visualizer for simulating CPNs in the browser: manual step firing, batch runs (Steps/Time modes), simulation monitors, graph layout strategies, and firing animation.

### Quick start

```bash
pip install streamlit   # if not already installed
streamlit run examples/streamlit_demo.py
```

See **[USER_GUIDE.md](USER_GUIDE.md)** for a full UI walkthrough, modeling features (priority, action blocks, record/list colorsets), and embedding `CPNStreamlitVisualizer` in your own app.

An older Streamlit editor (`cpnpy/home.py`) may still exist for JSON-based editing; the demo above is the recommended entry point for simulation and visualization.

---

### Hierarchical Petri Nets (HCPNs)

**Hierarchical Petri Nets** (or **Hierarchical Colored Petri Nets**, HCPNs) extend standard CPNs by allowing **substitution transitions**. A substitution transition in a “parent” module references another entire Petri net (the “child” or **submodule**), enabling multi-level, modular process modeling. 

1. **Modules:**  
   Each component or sub-process is defined as its own CPN, making the overall model more **scalable** and **reusable**.

2. **Substitution Transitions:**  
   Instead of firing tokens directly, these special transitions delegate token flow to another CPN. This allows nesting sub-processes inside higher-level transitions.

3. **Fusion Sets (Optional):**  
   Certain places across modules can be *fused* together, sharing the same marking. This mechanism simplifies situations where multiple modules must access the same data or resources.

4. **Visualization:**  
   HCPNs can be rendered with a specialized **Graphviz** visualizer, illustrating each module as a separate subgraph, highlighting substitution transitions and linking them to child modules with dashed edges.

To learn more about defining, structuring, and visualizing hierarchical nets in `cpnpy`, see **[docs_HCPN.md](docs_HCPN.md)** for a comprehensive guide.

---

## Additional Notes

- **Bindings and Guard Evaluation:** Guards and arc expressions are Python code snippets evaluated under a user-defined `EvaluationContext`. This allows integrating custom logic (functions, constants) into your CPN model.
- **Deep and Shallow Copying:** The classes implement `__copy__` and `__deepcopy__` to facilitate safe cloning of the CPN and marking states if needed.
- **Error Handling:** When tokens or bindings are insufficient to fire a transition, appropriate exceptions (e.g., `RuntimeError` or `ValueError`) are raised.

---

## Contributing and Feedback

Contributions, bug reports, and feature requests are welcome. Open an issue or submit a pull request to help improve `cpnpy`.
