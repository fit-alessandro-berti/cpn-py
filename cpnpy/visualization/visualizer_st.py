import streamlit as st
import streamlit.components.v1 as components
import json
import inspect
from typing import List, Optional, Any
from cpnpy.cpn.cpn_imp import CPN, Marking, EvaluationContext
from cpnpy.simulation.simu import get_enabled_transitions

class CPNStreamlitVisualizer:
    """
    Interactive Streamlit visualizer for Coloured Petri Nets using vis-network.

    Features:
    - Circles for places (name inside, colorset outside bottom-right).
    - Rectangles for transitions (name, guard, delay displayed).
    - Click any node for a detail overlay (action code / full token list).
    - Enabled transitions highlighted in green; sidebar button fires them.
    - 300 ms particle animation on firing arcs.
    - Physics disabled – nodes stay where dragged.
    """

    def __init__(self, cpn: CPN, marking: Marking,
                 context: EvaluationContext | None = None,
                 session_key: str = "cpn_marking"):
        self.cpn = cpn
        self.context = context or EvaluationContext()
        self.session_key = session_key

        # Store a mutable copy of the marking in session state so firings persist.
        if self.session_key not in st.session_state:
            st.session_state[self.session_key] = marking
        self.marking = st.session_state[self.session_key]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_token_display(self, ms, max_tokens: int = 5) -> str:
        display = ms.tokens[:max_tokens]
        lines = []
        for tok in display:
            val_str = str(tok.value)
            if len(val_str) > 20:
                val_str = val_str[:17] + "…"
            ts_str = f"@{tok.timestamp}" if tok.timestamp != 0 else ""
            lines.append(f"• {val_str}{ts_str}")
        if len(ms.tokens) > max_tokens:
            lines.append(f"… (+{len(ms.tokens) - max_tokens} more)")
        return "\n".join(lines) if lines else "(No tokens)"

    def _enabled_transitions(self, only_best_priority: bool = True):
        """Use centralized logic from simu.py for enabled transitions."""
        return get_enabled_transitions(self.cpn, self.marking, self.context, only_best_priority)

    def _arc_ids_for_transition(self, trans):
        """Return (input_arc_ids, output_arc_ids) as "from|to" strings."""
        inp = [f"{a.source.name}|{a.target.name}"
               for a in self.cpn.get_input_arcs(trans)]
        out = [f"{a.source.name}|{a.target.name}"
               for a in self.cpn.get_output_arcs(trans)]
        return inp, out

    def _it_nodes(self):
        """Generator yielding (name, colorset_name, tokens_summ, full_tokens, pos)."""
        # Note: We rely on JS persistence now, so session_state pos is fallback
        nodes_pos = st.session_state.get(f"{self.session_key}_nodes_pos", {})
        now = self.marking.global_clock
        for place in self.cpn.places:
            ms = self.marking.get_multiset(place.name)
            summ = self._get_token_display(ms)
            full = [{"value": repr(t.value), "timestamp": t.timestamp, "is_avail": (t.timestamp <= now)} for t in ms.tokens]
            pos = nodes_pos.get(place.name)
            yield (place.name, place.colorset.name, summ, full, pos)
        for trans in self.cpn.transitions:
            pos = nodes_pos.get(trans.name)
            yield (trans.name, None, None, None, pos)

    def _prepare_data(self, enabled_names: List[str], animate_in: List[str] = None, animate_out: List[str] = None):
        """Build node/edge dictionaries for vis-network."""
        nodes = []
        edges = []
        animate_in = animate_in or []
        animate_out = animate_out or []
        
        now = self.marking.global_clock
        for name, colorset_name, tokens_summ, full_tokens, pos in self._it_nodes():
            is_place = any(p.name == name for p in self.cpn.places)
            enabled = (name in enabled_names)
            node_obj = self.cpn.get_place_by_name(name) if is_place else self.cpn.get_transition_by_name(name)
            
            # --- Inside Shape Label ---
            if is_place:
                label_parts = [f"<b>{name}</b>"]
            else:
                # Transition internal label:
                # 1. Name (bold)
                label_parts = [f"<b>{name}</b>"]
                # 2. Action indicator line (always present)
                has_action = getattr(node_obj, 'action', None) or getattr(node_obj, 'action_code', None)
                label_parts.append("<code>action</code>" if has_action else " ")
            
            node = {
                "id": name,
                "label": "\n".join(label_parts),
                "type": 'place' if is_place else 'transition',
                "shape": "circle" if is_place else "box",
                "size": 35 if is_place else 25,
                "font": {"multi": "html", "size": 14},
                "color": {
                    "background": "#dce3ff" if is_place else ("#c8f7c5" if enabled else "#f8f9fa"),
                    "border": "#5d78ff" if is_place else ("#2ecc71" if enabled else "#adb5bd"),
                    "highlight": {"background": "#cbd5ff" if is_place else ("#a8e7a5" if enabled else "#e9ecef"),
                                  "border": "#3b59ff" if is_place else ("#27ae60" if enabled else "#6c757d")},
                }
            }
            
            # Sub-indicators & Corners
            if is_place:
                ms = self.marking.get_multiset(name)
                avail = sum(1 for t in ms.tokens if t.timestamp <= now)
                future = sum(1 for t in ms.tokens if t.timestamp > now)
                is_timed = node_obj.colorset.timed
                node["corner_tr"] = colorset_name or ""
                if is_timed:
                    parts = []
                    if avail > 0: parts.append(f"{avail}@")
                    if future > 0: parts.append(f"{future}@")
                    node["corner_br"] = ", ".join(parts)
                else:
                    node["corner_br"] = str(avail) if avail > 0 else ""
                node["token_avail"] = avail
                node["token_future"] = future
                node["is_timed"] = is_timed
            else:
                # External labels for transitions
                delay = getattr(node_obj, 'transition_delay', 0)
                # Swapped: Top=Guard, Bottom=Delay
                node["external_top"] = node_obj.guard_expr if (hasattr(node_obj, 'guard_expr') and node_obj.guard_expr) else ""
                node["external_bottom"] = f"@+ {delay}" if delay > 0 else ""
                # Priority always visible at corner
                node["external_bl"] = str(node_obj.priority)
                # Full data for overlay
                node["guard"] = node_obj.guard_expr or ""
                node["delay"] = delay
                node["priority"] = node_obj.priority

            # Action code extraction
            if not is_place:
                if hasattr(node_obj, 'action_code') and node_obj.action_code:
                    node["action_code"] = node_obj.action_code
                elif hasattr(node_obj, 'action') and node_obj.action:
                    try:
                        import inspect
                        node["action_code"] = inspect.getsource(node_obj.action)
                    except:
                        node["action_code"] = str(node_obj.action)
                else:
                    node["action_code"] = ""

            node["colorset_name"] = colorset_name
            node["full_tokens"] = full_tokens
            if pos:
                node["x"], node["y"] = pos
            nodes.append(node)

        # ---- Arcs ----
        # Pre-detect bidirectional connections to decide on smoothing
        connections = set((a.source.name, a.target.name) for a in self.cpn.arcs)
        
        for arc in self.cpn.arcs:
            src = arc.source.name
            tgt = arc.target.name
            arc_id = f"{src}|{tgt}"
            
            is_bi = (tgt, src) in connections
            
            edge = {
                "id": arc_id,
                "from": src,
                "to": tgt,
                "label": str(arc.expression),
                "arrows": "to",
                "font": {"size": 12, "align": "top"},
                "color": {"color": "#999999", "inherit": False},
                "smooth": {"enabled": True, "type": "curvedCW", "roundness": 0.2} if is_bi else False,
                "is_curved": is_bi
            }
            edges.append(edge)

        return {"nodes": nodes, "edges": edges, "animate_in": animate_in, "animate_out": animate_out}


    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def fire(self, transition_name: str):
        """Fire a named transition, update session-state marking, return firing info."""
        st.session_state[f"{self.session_key}_sim_error"] = None # Clear previous error
        try:
            trans = self.cpn.get_transition_by_name(transition_name)
            # Use the return value from the newly updated fire_transition
            firing_info = self.cpn.fire_transition(trans, self.marking, self.context)
            return firing_info
        except Exception as e:
            st.session_state[f"{self.session_key}_sim_error"] = str(e)
            return {"in": [], "out": []}

    def render(self, height: int = 800):
        # ---------------- Sidebar simulation controls ----------------
        with st.sidebar:
            error = st.session_state.get(f"{self.session_key}_sim_error")
            if error:
                st.error(f"**Simulation Error:**\n{error}")

            st.markdown(f"### Global Clock: `{self.marking.global_clock}`")
            
            enabled = self._enabled_transitions()
            enabled_names = [t.name for t in enabled]
            
            st.markdown("### Fire a Transition")
            if not enabled:
                st.info("No transitions enabled at the current time.")
                if st.button("Advance Time ⏩", key=f"{self.session_key}_advance"):
                    st.session_state[f"{self.session_key}_sim_error"] = None
                    try:
                        self.cpn.advance_global_clock(self.marking)
                    except Exception as e:
                        st.session_state[f"{self.session_key}_sim_error"] = str(e)
                    st.rerun()
            else:
                selected = st.selectbox(
                    "Enabled transitions",
                    options=enabled_names,
                    key=f"{self.session_key}_select",
                )
                if st.button("Fire", key=f"{self.session_key}_fire"):
                    firing_info = self.fire(selected)
                    st.session_state[f"{self.session_key}_last_fired"] = firing_info
                    st.rerun()

        # Retrieve and clear last fired arcs for animation
        last_fired = st.session_state.pop(f"{self.session_key}_last_fired", {})
        animate_in = last_fired.get("in", [])
        animate_out = last_fired.get("out", [])

        # ---------------- Render vis-network component ---------
        data = self._prepare_data(enabled_names, animate_in=animate_in, animate_out=animate_out)
        vis_js_url = "https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"

        html_code = f"""
        <html>
        <head>
            <script src="{vis_js_url}"></script>
        <style>
                body {{ margin: 0; overflow: hidden; }}
                #mynetwork {{
                    width: 100%;
                    height: {height}px;
                    border: 1px solid #ddd;
                    background: #fafafa;
                }}
                #labels-container {{
                    position: absolute; top: 0; left: 0;
                    pointer-events: none;
                }}
                .corner-label {{
                    position: absolute;
                    font: 11px Arial;
                    white-space: nowrap;
                    pointer-events: none;
                }}
                .colorset-label {{
                    font: italic 11px Arial;
                    color: #555;
                }}
                .token-label {{
                    font: bold 11px Arial;
                    color: #333;
                }}
                .trans-ext-label {{
                    position: absolute;
                    font: 11px Arial;
                    white-space: nowrap;
                    pointer-events: none;
                    text-align: center;
                }}
                .trans-top-label {{ color: black; }}
                .trans-bottom-label {{ color: black; }}
                .trans-bl-label {{ color: black; font-size: 11px; }}
                #overlay {{
                    position: absolute; top: 10px; right: 10px;
                    width: 320px; max-height: 80%;
                    background: rgba(255,255,255,0.97);
                    border: 1px solid #ccc; border-radius: 8px;
                    padding: 14px; display: none; overflow-y: auto;
                    box-shadow: 0 4px 12px rgba(0,0,0,0.12);
                    font-family: sans-serif; font-size: 13px;
                    z-index: 100;
                }}
                .overlay-header {{
                    font-weight: bold; border-bottom: 1px solid #eee;
                    padding-bottom: 6px; margin-bottom: 10px;
                    display: flex; justify-content: space-between;
                }}
                .close-btn {{ cursor: pointer; color: #aaa; }}
                pre {{ background: #f4f4f4; padding: 8px; border-radius: 4px;
                       font-size: 11px; overflow-x: auto; white-space: pre-wrap; }}
                .token-row {{
                    padding: 2px 0;
                }}
            </style>
        </head>
        <body>
            <div id="mynetwork"></div>
            <div id="labels-container"></div>
            <div id="overlay">
                <div class="overlay-header">
                    <span id="overlay-title">Details</span>
                    <span class="close-btn" onclick="hideOverlay()">✖</span>
            </div>
                <div id="overlay-content"></div>
          </div>

        <script>
                const graphData = {json.dumps(data)};
                const container = document.getElementById('mynetwork');
                // ---------- Persistence ----------
                const STORAGE_KEY = "cpn_v1_" + btoa(graphData.nodes.map(n => n.id).join(",")).slice(0, 16);
                const VIEW_KEY = STORAGE_KEY + "_v";
                const SEL_KEY  = STORAGE_KEY + "_s";

                // Restore Positions BEFORE creating DataSet to avoid flashing
                const savedPos = localStorage.getItem(STORAGE_KEY);
                if (savedPos) {{
                    try {{
                        const posMap = JSON.parse(savedPos);
                        graphData.nodes.forEach(n => {{
                            if (posMap[n.id]) {{ n.x = posMap[n.id].x; n.y = posMap[n.id].y; }}
                        }});
                    }} catch (e) {{}}
                }}

                const options = {{
                    nodes: {{ font: {{ face: 'Arial' }}, margin: 10 }},
                    edges: {{
                        smooth: false, 
                        color: {{ inherit: 'from' }},
                        arrows: {{ to: {{ enabled: true }} }}
                    }},
                    physics: {{ 
                        enabled: !savedPos,
                        solver: 'forceAtlas2Based',
                        forceAtlas2Based: {{
                            gravitationalConstant: -100,
                            centralGravity: 0.01,
                            springLength: 100,
                            springConstant: 0.08,
                            nodeDistance: 180
                        }},
                        stabilization: {{ iterations: 200 }}
                    }},
                    interaction: {{ hover: true, navigationButtons: false, keyboard: true }}
                }};

                function saveState() {{
                    localStorage.setItem(STORAGE_KEY, JSON.stringify(network.getPositions()));
                    localStorage.setItem(VIEW_KEY, JSON.stringify({{
                        pos: network.getViewPosition(),
                        scale: network.getScale()
                    }}));
                }}

                // Build datasets
                const nodesDS = new vis.DataSet(graphData.nodes);
                const edgesDS = new vis.DataSet(graphData.edges);
                const network = new vis.Network(container, {{ nodes: nodesDS, edges: edgesDS }}, options);

                network.on("dragEnd", saveState);
                network.on("zoom", saveState);
                
                // Save initial state if none exists
                network.once("afterDrawing", () => {{
                    if (!localStorage.getItem(STORAGE_KEY)) saveState();
                }});

                // Restore View early
                const savedView = localStorage.getItem(VIEW_KEY);
                if (savedView) {{
                    try {{
                        const v = JSON.parse(savedView);
                        network.moveTo({{ position: v.pos, scale: v.scale, animation: false }});
                    }} catch (e) {{}}
                }}

                // ---------- Multi-label Corner indicators ----------
                const labelsContainer = document.getElementById('labels-container');
                const placeNodes = graphData.nodes.filter(n => n.type === 'place');
                const transNodes = graphData.nodes.filter(n => n.type === 'transition');
                const labelEls = {{}};
                const transLabelEls = {{}};
                placeNodes.forEach(node => {{
                    const tr = document.createElement('div');
                    tr.className = 'corner-label colorset-label';
                    tr.innerText = node.corner_tr || '';
                    labelsContainer.appendChild(tr);

                    const br = document.createElement('div');
                    br.className = 'corner-label token-label';
                    if (node.corner_br) {{
                        let html = '';
                        if (node.is_timed) {{
                            const parts = [];
                            if (node.token_avail > 0) parts.push(`<span style="color:#27ae60">${{node.token_avail}}@</span>`);
                            if (node.token_future > 0) parts.push(`<span style="color:black">${{node.token_future}}@</span>`);
                            html = parts.join(', ');
                        }} else if (node.token_avail > 0) {{
                            html = `<span style="color:#27ae60">${{node.token_avail}}</span>`;
                        }}
                        br.innerHTML = html;
                    }}
                    labelsContainer.appendChild(br);
                    labelEls[node.id] = {{ tr, br }};
                }});

                transNodes.forEach(node => {{
                    const top = document.createElement('div');
                    top.className = 'trans-ext-label trans-top-label';
                    top.innerText = node.external_top || '';
                    labelsContainer.appendChild(top);

                    const bottom = document.createElement('div');
                    bottom.className = 'trans-ext-label trans-bottom-label';
                    bottom.innerText = node.external_bottom || '';
                    labelsContainer.appendChild(bottom);

                    const bl = document.createElement('div');
                    bl.className = 'trans-ext-label trans-bl-label';
                    bl.innerText = node.external_bl || '';
                    labelsContainer.appendChild(bl);

                    transLabelEls[node.id] = {{ top, bottom, bl }};
                }});

                function updateCornerLabels() {{
                    placeNodes.forEach(node => {{
                        const els = labelEls[node.id];
                        if (!els) return;
                        try {{
                            const box = network.getBoundingBox(node.id);
                            const rDom = network.canvasToDOM({{x: box.right, y: 0}}).x;
                            const tDom = network.canvasToDOM({{x: 0, y: box.top}}).y;
                            const bDom = network.canvasToDOM({{x: 0, y: box.bottom}}).y;
                            
                            els.tr.style.left = (rDom + 2) + 'px';
                            els.tr.style.top  = (tDom - 5) + 'px';

                            els.br.style.left = (rDom + 2) + 'px';
                            els.br.style.top  = (bDom - 10) + 'px';
                        }} catch(e) {{}}
                    }});

                    transNodes.forEach(node => {{
                        const els = transLabelEls[node.id];
                        if (!els) return;
                        try {{
                            const box = network.getBoundingBox(node.id);
                            const tDom = network.canvasToDOM({{x: 0, y: box.top}}).y;
                            const bDom = network.canvasToDOM({{x: 0, y: box.bottom}}).y;
                            const hMid = network.canvasToDOM({{x: (box.left + box.right)/2, y: 0}}).x;
                            
                            els.top.style.left = hMid + 'px';
                            els.top.style.top  = (tDom - 15) + 'px';
                            els.top.style.transform = 'translateX(-50%)';

                            els.bottom.style.left = hMid + 'px';
                            els.bottom.style.top  = (bDom + 1) + 'px';
                            els.bottom.style.transform = 'translateX(-50%)';

                            const lDom = network.canvasToDOM({{x: box.left, y: 0}}).x;
                            els.bl.style.left = (lDom - 4) + 'px';
                            els.bl.style.top  = (bDom - 12) + 'px';
                            els.bl.style.transform = 'translateX(-100%)';
                        }} catch(e) {{}}
                    }});
                }}

                network.on("stabilized", () => {{
                    saveState();
                    network.setOptions({{ physics: {{ enabled: false }} }});
                    updateCornerLabels(); // Final position after stabilization
                }});
                network.on('afterDrawing', updateCornerLabels);

                // ---------- Simultaneous Animation ----------
                const TOKEN_DURATION = 400; // ms per token
                const inArcs = graphData.animate_in || [];
                const outArcs = graphData.animate_out || [];

                if (inArcs.length > 0 || outArcs.length > 0) {{
                    container.style.position = 'relative'; 
                    const canvas = document.createElement('canvas');
                    canvas.style.cssText = 'position:absolute;top:0;left:0;pointer-events:none;width:100%;height:100%;z-index:99;';
                    container.appendChild(canvas);

                    const resize = () => {{
                        const r = container.getBoundingClientRect();
                        canvas.width = r.width;
                        canvas.height = r.height;
                    }};
                    resize();
                    window.addEventListener('resize', resize);

                    const start = performance.now();
                    const animFrame = (ts) => {{
                        const elapsed = ts - start;
                        const ctx = canvas.getContext('2d');
                        if (!ctx) return;
                        ctx.clearRect(0, 0, canvas.width, canvas.height);

                        let anyRunning = false;

                        [...inArcs, ...outArcs].forEach(entry => {{
                            if (entry.count <= 0) return;
                            const [fromId, toId] = entry.arc.split('|');
                            let sPos, ePos;
                            try {{
                                sPos = network.canvasToDOM(network.getPosition(fromId));
                                ePos = network.canvasToDOM(network.getPosition(toId));
                            }} catch(e) {{ return; }}

                            const t = Math.min(1.0, elapsed / TOKEN_DURATION);
                            if (t < 1.0) anyRunning = true;

                            const edge = edgesDS.get(entry.arc);
                            const isCurved = edge && edge.is_curved;

                            let x, y;
                            if (isCurved) {{
                                const r = 0.2;
                                const midX = (sPos.x + ePos.x) / 2;
                                const midY = (sPos.y + ePos.y) / 2;
                                const dx = ePos.x - sPos.x;
                                const dy = ePos.y - sPos.y;
                                // Clockwise rotation in y-down: (dx, dy) -> (-dy, dx)
                                const cpX = midX - dy * r;
                                const cpY = midY + dx * r;
                                x = (1-t)*(1-t)*sPos.x + 2*(1-t)*t*cpX + t*t*ePos.x;
                                y = (1-t)*(1-t)*sPos.y + 2*(1-t)*t*cpY + t*t*ePos.y;
                            }} else {{
                                x = sPos.x + (ePos.x - sPos.x) * t;
                                y = sPos.y + (ePos.y - sPos.y) * t;
                            }}

                            ctx.beginPath();
                            ctx.arc(x, y, 7, 0, 2 * Math.PI);
                            ctx.fillStyle = '#27ae60';
                            ctx.fill();
                            ctx.strokeStyle = 'white';
                            ctx.lineWidth = 2;
                            ctx.stroke();
                        }});

                        if (anyRunning) {{
                            requestAnimationFrame(animFrame);
                        }} else {{
                            window.removeEventListener('resize', resize);
                            setTimeout(() => {{ if (canvas.parentNode) container.removeChild(canvas); }}, 50);
                        }}
                    }};
                    requestAnimationFrame(animFrame);
                }}

                // ---------- Click handler ----------
                network.on("click", params => {{
                    if (params.nodes.length > 0) {{
                        const nodeId = params.nodes[0];
                        localStorage.setItem(SEL_KEY, nodeId);
                        showOverlay(graphData.nodes.find(n => n.id === nodeId));
                    }} else {{
                        hideOverlay();
                    }}
                }});

                // Restore Overlay
                const lastSel = localStorage.getItem(SEL_KEY);
                if (lastSel) {{
                    const node = graphData.nodes.find(n => n.id === lastSel);
                    if (node) showOverlay(node);
                }}

                function showOverlay(node) {{
                    const overlay = document.getElementById('overlay');
                    const title   = document.getElementById('overlay-title');
                    const content = document.getElementById('overlay-content');
                    overlay.style.display = 'block';

                    if (node.type === 'transition') {{
                        title.innerHTML = '<b>' + node.id + '</b>';
                        
                        let html = '<div style="margin-top:10px">';
                        
                        // 1. Priority
                        html += '<b>Priority:</b><pre>' + node.priority + '</pre>';

                        // 2. Guard
                        if (node.guard) {{
                            html += '<b>Guard:</b><pre>' + esc(node.guard) + '</pre>';
                        }} else {{
                            html += '<b>Guard:</b> <span style="font-weight:normal">none</span><br><br>';
                        }}

                        // 3. Delay
                        if (node.delay > 0) {{
                            html += '<b>Delay:</b><pre>@+ ' + node.delay + '</pre>';
                        }} else {{
                            html += '<b>Delay:</b> <span style="font-weight:normal">none</span><br><br>';
                        }}

                        // 4. Action
                        if (node.action_code) {{
                            html += '<b>Action:</b><pre>' + esc(node.action_code) + '</pre>';
                        }} else {{
                            html += '<b>Action:</b> <span style="font-weight:normal">none</span><br>';
                        }}

                        html += '</div>';
                        content.innerHTML = html;
          }} else {{
                        title.innerHTML = '<b>' + node.id + '</b>: <i style="font-weight:normal">' + esc(node.colorset_name) + '</i>';
                        let summary = node.is_timed ? '<b><span style="color:#27ae60">' + (node.token_avail || 0) + '@</span>, ' + (node.token_future || 0) + '@ tokens</b>' : '<b><span style="color:#27ae60">' + (node.token_avail || 0) + '</span> tokens</b>';
                        let html = '<div style="margin-top:10px">' + summary + '</div><div style="margin-top:10px">';
                        node.full_tokens.forEach(t => {{
                            const color = t.is_avail ? '#27ae60' : 'black';
                            const ts = t.timestamp ? ' @' + t.timestamp : '';
                            html += `<div class="token-row" style="color:${{color}}">${{esc(t.value)}}${{ts}}</div>`;
            }});
                        if (!node.full_tokens.length) html += '<i>No tokens</i>';
                        html += '</div>';
                        content.innerHTML = html;
        }}
                }}

                function hideOverlay() {{
                    document.getElementById('overlay').style.display = 'none';
                    localStorage.removeItem(SEL_KEY);
                }}

                function esc(text) {{
                    const d = document.createElement('div');
                    d.textContent = String(text);
                    return d.innerHTML;
                }}
        </script>
        </body>
        </html>
        """
        components.html(html_code, height=height + 20, scrolling=False)
