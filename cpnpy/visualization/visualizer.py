import graphviz
import html
import tempfile
import os
from cpnpy.cpn.cpn_imp import *
import inspect

def format_token(tok, token_max_len=200):
    """
    Produce a short, escaped summary of a single token (value + optional timestamp).
    """
    # Convert token value to string
    raw_value_str = str(tok.value)
    # Truncate if very long
    if len(raw_value_str) > token_max_len:
        raw_value_str = raw_value_str[:token_max_len] + "...(truncated)"

    # HTML-escape the truncated string
    escaped_value = html.escape(raw_value_str)
    # Escape backslashes and newlines
    #escaped_value = escaped_value.replace("\\", "\\\\").replace("\n", "\\n")

    # Append timestamp if present
    if tok.timestamp != 0:
        return f"{escaped_value}@{tok.timestamp}"
    else:
        return escaped_value


def summarize_label(full_label: str, max_len: int = 10000) -> str:
    """
    If the label is longer than max_len, truncate it safely.
    Also ensure it doesn't contain unescaped newlines/backslashes that
    might break Graphviz.
    """
    if len(full_label) > max_len:
        full_label = full_label[:max_len] + "...(truncated)"
    return full_label
    #.replace("\\", "\\\\").replace("\n", "\\n")


class CPNGraphViz:
    def __init__(self):
        self.graph = None
        self.format = "pdf"
        self.temp_dir = tempfile.mkdtemp()  # temporary directory for outputs

    def apply(self, cpn: CPN, marking: Marking, format: str = "pdf"):
        """
        Create a Graphviz Digraph from the given CPN and marking.

        :param cpn: The CPN object (with places, transitions, arcs)
        :param marking: The Marking object (with current tokens)
        :param format: The desired output format (e.g., 'pdf', 'png', 'svg')
        """
        self.format = format
        self.graph = graphviz.Digraph(format=self.format, directory=self.temp_dir)
        # global layout hints
        self.graph.attr(
            rankdir="LR",  # left->right
            splines="spline",  # nicer curves
            overlap="false",  # try to remove overlaps
            newrank="true",  # better handling with clusters
            pack="true",  # pack clusters more tightly
            packmode="clust",
        )

        # Add Places
        for place in cpn.places:
            ms = marking.get_multiset(place.name)
            token_str_list = []

            # Format each token in a safe, shortened way
            for tok in ms.tokens:
                token_str_list.append(format_token(tok))

            if token_str_list:
                label = f"{place.name}\\nTokens: {', '.join(token_str_list)}"
            else:
                label = f"{place.name}\\n(No tokens)"

            # Final summarize/truncation to prevent very long label
            label = summarize_label(label)

            self.graph.node(
                place.name,  # Node ID (not escaped)
                label=label,
                shape="ellipse",
                style="filled",
                fillcolor="#e0e0f0"
            )

        # Add Transitions
        for transition in cpn.transitions:
            lines = []

            # Transition name
            lines.append(transition.name)

            # Guard
            if transition.guard_expr:
                guard_escaped = summarize_label(transition.guard_expr, max_len=500)
                lines.append(f"Guard: {guard_escaped}")

            # Variables
            if transition.variables:
                # Short summary of variables
                vars_str = ", ".join(
                    summarize_label(v, max_len=100) for v in transition.variables
                )
                lines.append(f"Vars: {vars_str}")

            # Delay
            if transition.transition_delay > 0:
                lines.append(f"Delay: {transition.transition_delay}")

            if transition.priority != 0:
                lines.append(f"Priority: {transition.priority}")

            if transition.action is not None:

                # TODO, remove str fallback support
                if isinstance(transition.action, str):
                    function_code = transition.action
                else:
                    function_code = inspect.getsource(transition.action)
                lines.append("Action:")
                lines.append(function_code)

            # Combine into a single label
            raw_label = "\\n".join(lines)
            # Summarize/truncate if needed
            final_label = summarize_label(raw_label)

            self.graph.node(
                transition.name,
                label=final_label,
                shape="rectangle",
                style="rounded,filled",
                fillcolor="#ffe0e0"
            )

        # Add Arcs
        for arc in cpn.arcs:
            source_name = arc.source.name if hasattr(arc.source, 'name') else arc.source
            target_name = arc.target.name if hasattr(arc.target, 'name') else arc.target

            # Arc expression
            raw_expr = str(arc.expression)
            arc_label = summarize_label(raw_expr, max_len=500)

            self.graph.edge(source_name, target_name, label=arc_label)

        return self

    def view(self):
        """
        View the generated graph using the default system viewer.
        """
        if self.graph is None:
            raise RuntimeError("Graph not created. Call apply() first.")
        self.graph.view()

    from pyvis.network import Network

    def view_interactive(self):

        import pydot

        # --- compatibility patch for networkx.nx_pydot.from_pydot ---
        def _patch_pydot_get_strict():
            for cls in (pydot.Dot, pydot.Graph):
                if hasattr(cls, "get_strict"):
                    orig = cls.get_strict

                    def _wrapped(self, *args, **kwargs):
                        # ignore extra args networkx passes
                        return orig(self)

                    cls.get_strict = _wrapped

        _patch_pydot_get_strict()
        # -------------------------------------------------------------

        import networkx as nx
        from pyvis.network import Network

        # 1. Get DOT source from existing graphviz object
        dot_src = self.graph.source

        # 2. Parse DOT -> pydot -> networkx
        pydot_graphs = pydot.graph_from_dot_data(dot_src)
        pydot_graph = pydot_graphs[0]
        G = nx.nx_pydot.from_pydot(pydot_graph)

        # 3. Build interactive net
        net = Network(directed=True, height="600px", width="100%", notebook=False)
        net.barnes_hut()  # draggable physics layout
        net.show_buttons(["physics"])  # optional UI panel

        # --- nodes: transitions as boxes, places as ellipses ---
        for n, data in G.nodes(data=True):
            label = data.get("label", n)
            title = str(n)  # tooltip

            gv_shape = str(data.get("shape", "ellipse")).lower()
            if gv_shape in ("box", "rect", "rectangle"):
                shape = "box"  # transitions
            else:
                shape = "ellipse"  # places / default

            net.add_node(
                n,
                label=label,
                title=title,
                shape=shape,
                font={"size": 30},
            )

        # --- edges: show arc inscriptions + thicker lines ---
        for u, v, data in G.edges(data=True):
            label = data.get("label", "")  # arc inscription from DOT

            # try to reuse DOT penwidth if present, else default thicker edge
            try:
                width = float(data.get("penwidth", 2.5))
            except (TypeError, ValueError):
                width = 2.5

            net.add_edge(
                u,
                v,
                label=label,
                arrows="to",
                width=width,
                font={"size": 30, "align": "top"},
            )

        # 4. Export to HTML (script mode)
        net.show("cpn_net_interactive.html", notebook=False)

    def save(self, filename: str):
        """
        Save (render) the graph to a file.

        The file will be saved in the temporary directory.
        The 'filename' is a base name without path,
        the renderer will append the format and '-O' suffix.
        """
        if self.graph is None:
            raise RuntimeError("Graph not created. Call apply() first.")
        out_path = self.graph.render(filename=filename, cleanup=True)
        final_path = os.path.join(os.getcwd(), os.path.basename(out_path))
        if os.path.abspath(final_path) != os.path.abspath(out_path):
            os.rename(out_path, final_path)
        return final_path


# Example usage (modify as needed):
if __name__ == "__main__":
    cs_definitions = """
    colset INT = int timed;
    """
    parser = ColorSetParser()
    colorsets = parser.parse_definitions(cs_definitions)

    int_set = colorsets["INT"]

    p1 = Place("P1", int_set)
    p2 = Place("P2", int_set)
    t1 = Transition("T1", guard="x > 10", variables=["x"], transition_delay=2)

    cpn = CPN()
    cpn.add_place(p1)
    cpn.add_place(p2)
    cpn.add_transition(t1)
    cpn.add_arc(Arc(p1, t1, "x"))
    cpn.add_arc(Arc(t1, p2, "x @+3"))

    marking = Marking()
    marking.set_tokens("P1", [5, 12])

    viz = CPNGraphViz().apply(cpn, marking, format="png")
    # Uncomment to view:
    # viz.view()
    # Or save:
    # path = viz.save("example_cpn")
    # print("Saved to:", path)
