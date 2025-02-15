import streamlit as st
import json

# Use your existing importer/exporter from cpnpy.cpn
from cpnpy.cpn.importer import import_cpn_from_json
from cpnpy.cpn.exporter import export_cpn_to_json
from cpnpy.cpn.colorsets import ColorSetParser


def import_cpn_ui():
    """
    Displays a file uploader for importing a CPN from JSON.
    On success, updates:
      - st.session_state["cpn"]
      - st.session_state["marking"]
      - st.session_state["context"]
      - st.session_state["colorsets"] (parsed from the JSON's "colorSets")
      - st.session_state["imported_user_code"] (if the JSON's context had user code)
    We do NOT overwrite any existing text-area widgets in the UI. Instead, we just
    store these imported objects in session_state so the main_app can display them.
    """
    st.subheader("Import CPN from JSON")

    uploaded_file = st.file_uploader("Choose a CPN JSON file", type=["json"])
    if uploaded_file is not None:
        try:
            file_content = uploaded_file.read().decode("utf-8")
            data = json.loads(file_content)

            # 1) Parse colorSets from JSON (if present)
            color_set_defs = data.get("colorSets", [])
            color_definitions_text = "\n".join(color_set_defs)

            parser = ColorSetParser()
            if color_definitions_text.strip():
                parsed_colorsets = parser.parse_definitions(color_definitions_text)
            else:
                parsed_colorsets = {}

            # 2) Import the net, marking, context using your original importer
            cpn, marking, context = import_cpn_from_json(data)

            # 3) Store results in session_state
            st.session_state["cpn"] = cpn
            st.session_state["marking"] = marking
            st.session_state["context"] = context
            st.session_state["colorsets"] = parsed_colorsets

            # If user code was present, store it in a separate key
            imported_code = context.env.get("__original_user_code__", "")
            if imported_code:
                st.session_state["imported_user_code"] = imported_code

            st.success("CPN imported successfully!")
        except Exception as e:
            st.error(f"Failed to import CPN: {e}")


def export_cpn_ui():
    """
    Displays a button to export the current CPN+Marking+Context to JSON.
    Offers a download button for the resulting JSON file.
    """
    st.subheader("Export CPN to JSON")

    cpn = st.session_state.get("cpn", None)
    marking = st.session_state.get("marking", None)
    context = st.session_state.get("context", None)

    if not cpn or not marking:
        st.info("No CPN or marking found in session state.")
        return

    # Let the user specify a filename
    filename = st.text_input("Export JSON filename", value="exported_cpn.json")

    if st.button("Export and Download CPN"):
        try:
            # exporter returns a dict representing the JSON structure
            exported_json = export_cpn_to_json(
                cpn=cpn,
                marking=marking,
                context=context,
                output_json_path=filename,  # not actually writing to disk except for references
                output_py_path=None         # or "exported_user_code.py", etc.
            )
            exported_str = json.dumps(exported_json, indent=2)

            # Provide a download button
            st.download_button(
                label="Download CPN JSON",
                data=exported_str,
                file_name=filename,
                mime="application/json"
            )
            st.success(f"CPN exported as '{filename}'.")
        except Exception as e:
            st.error(f"Error exporting CPN: {e}")
