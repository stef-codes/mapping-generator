"""AI-Assisted Mapping Generator — Streamlit pilot app."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Streamlit re-runs app.py without reloading cached `src.*` modules.
for _module_name in list(sys.modules):
    if _module_name == "src" or _module_name.startswith("src."):
        del sys.modules[_module_name]

from src.column_mapping import guess_mapping_columns
from src.config import CATEGORIES, DEFAULT_ROW_LIMIT, MAX_ROW_LIMIT
from src.ai_fallback import is_ai_available
from src.database import (
    get_connection_string,
    list_tables,
    load_table,
    run_custom_query,
    test_connection,
)
from src.export import (
    build_validation_report,
    dataframe_to_csv_bytes,
    generate_transform_script,
    generate_transformed_data_csv,
)
from src.ingestion import build_mapping_rows, load_mapping_document, load_source_csv
from src.matching import generate_suggestions
from src.profiling import profile_source_columns

st.set_page_config(
    page_title="Mapping Generator",
    page_icon="🗺️",
    layout="wide",
)

st.title("AI-Assisted Mapping Generator")
st.caption(
    "First-pass draft assistant — every suggestion requires human review before export."
)


def _init_state() -> None:
    defaults = {
        "mapping_raw": None,
        "mapping_filename": "",
        "mapping_rows": None,
        "source_df": None,
        "source_filename": "",
        "source_profile": None,
        "suggestions": None,
        "reviewed_ready": False,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


_init_state()

with st.sidebar:
    st.header("Settings")
    gemini_configured = is_ai_available()
    if gemini_configured:
        st.success("Gemini API key configured")
    else:
        st.warning("Add `GEMINI_API_KEY` to `.env` to enable AI suggestions.")
    use_gemini = st.checkbox(
        "Use Gemini for missing fields",
        value=gemini_configured,
        disabled=not gemini_configured,
        help="After rule-based matching, send unresolved rows to Gemini in batches.",
    )


# --- Step 1: Mapping document ---
st.header("1. Upload mapping document")
mapping_file = st.file_uploader(
    "Mapping spec (.xlsx or .csv)",
    type=["xlsx", "xls", "csv"],
    key="mapping_upload",
)

if mapping_file:
    if (
        st.session_state.mapping_filename != mapping_file.name
        or st.session_state.mapping_raw is None
    ):
        st.session_state.mapping_raw = load_mapping_document(
            mapping_file, mapping_file.name
        )
        st.session_state.mapping_filename = mapping_file.name
        st.session_state.suggestions = None
        st.session_state.reviewed_ready = False

    raw_df = st.session_state.mapping_raw
    st.success(f"Loaded **{len(raw_df):,}** rows from `{mapping_file.name}`")

    try:
        column_mapping = guess_mapping_columns(raw_df)
        mapping_rows = build_mapping_rows(
            raw_df,
            column_mapping.target_col,
            column_mapping.required_col,
            column_mapping.dtype_col,
            column_mapping.notes_col,
        )
        if mapping_rows.empty:
            raise ValueError(
                f"No target fields found in column `{column_mapping.target_col}`."
            )
        st.session_state.mapping_rows = mapping_rows
        st.caption(f"Detected columns: {column_mapping.summary()}")
        st.info(f"**{len(mapping_rows):,}** target fields identified.")
    except ValueError as exc:
        st.session_state.mapping_rows = None
        st.error(str(exc))


# --- Step 2: Source report ---
st.header("2. Connect to source report")
source_tab_csv, source_tab_db = st.tabs(["CSV upload", "Live database"])

with source_tab_csv:
    source_file = st.file_uploader("Source report CSV", type=["csv"], key="source_csv")
    if source_file:
        if (
            st.session_state.source_filename != source_file.name
            or st.session_state.source_df is None
        ):
            st.session_state.source_df = load_source_csv(source_file)
            st.session_state.source_filename = source_file.name
            st.session_state.suggestions = None
            st.session_state.reviewed_ready = False
        st.success(
            f"Loaded **{len(st.session_state.source_df):,}** rows, "
            f"**{len(st.session_state.source_df.columns)}** columns."
        )

with source_tab_db:
    env = st.selectbox("Environment", ["DEV", "QA"], key="db_env")
    if st.button("Test connection", key="test_conn"):
        ok, msg = test_connection(env)
        st.success(msg) if ok else st.error(msg)

    db_mode = st.radio(
        "Load mode",
        ["Browse tables", "Custom SQL"],
        horizontal=True,
        key="db_mode",
    )
    row_limit = st.number_input(
        "Row limit",
        min_value=1,
        max_value=MAX_ROW_LIMIT,
        value=DEFAULT_ROW_LIMIT,
        key="db_row_limit",
    )

    if db_mode == "Browse tables":
        if st.button("List tables", key="list_tables"):
            try:
                st.session_state.db_tables = list_tables(env)
            except Exception as exc:
                st.error(str(exc))

        tables = st.session_state.get("db_tables", [])
        if tables:
            selected = st.selectbox("Select table", tables, key="db_table")
            if st.button("Load table", key="load_table"):
                try:
                    st.session_state.source_df = load_table(env, selected, row_limit)
                    st.session_state.suggestions = None
                    st.session_state.reviewed_ready = False
                    st.success(
                        f"Loaded **{len(st.session_state.source_df):,}** rows from `{selected}`."
                    )
                except Exception as exc:
                    st.error(str(exc))
    else:
        custom_sql = st.text_area(
            "Custom SQL",
            height=120,
            placeholder="SELECT * FROM dbo.MyReport WHERE ...",
            key="custom_sql",
        )
        st.caption(
            f"A `TOP {row_limit}` safeguard is auto-injected if no row limit is present."
        )
        if st.button("Run query", key="run_query"):
            if not custom_sql.strip():
                st.warning("Enter a SQL query first.")
            else:
                try:
                    st.session_state.source_df = run_custom_query(
                        env, custom_sql, row_limit
                    )
                    st.session_state.suggestions = None
                    st.session_state.reviewed_ready = False
                    st.success(
                        f"Query returned **{len(st.session_state.source_df):,}** rows."
                    )
                except Exception as exc:
                    st.error(str(exc))


# --- Step 3: Source profile ---
if st.session_state.source_df is not None:
    st.header("3. Source column profile")
    st.session_state.source_profile = profile_source_columns(st.session_state.source_df)
    st.dataframe(st.session_state.source_profile, use_container_width=True, height=300)


# --- Step 4: Generate suggestions ---
if (
    st.session_state.mapping_rows is not None
    and st.session_state.source_df is not None
):
    st.header("4. Generate mapping suggestions")

    if st.button("Generate suggestions", type="primary", key="generate"):
        source_cols = list(st.session_state.source_df.columns)
        total_rows = len(st.session_state.mapping_rows)
        with st.status(
            "Generating mapping suggestions"
            + (" (rules + Gemini)…" if use_gemini and gemini_configured else "…"),
            expanded=True,
        ) as status:
            progress = st.progress(0, text=f"Matching fields… 0/{total_rows:,}")

            def on_progress(pct: float) -> None:
                matched = min(int(pct * total_rows), total_rows)
                label = "Matching fields"
                if pct >= 0.9 and use_gemini and gemini_configured:
                    label = "Calling Gemini for unresolved fields"
                progress.progress(pct, text=f"{label}… {matched:,}/{total_rows:,}")

            try:
                st.session_state.suggestions = generate_suggestions(
                    st.session_state.mapping_rows,
                    source_cols,
                    progress_callback=on_progress,
                    use_ai=use_gemini and gemini_configured,
                )
                st.session_state.reviewed_ready = False
                progress.progress(1.0, text=f"Done — {total_rows:,} fields matched.")
                status.update(
                    label=f"Generated suggestions for {total_rows:,} fields",
                    state="complete",
                )
            except Exception as exc:
                status.update(label="Generation failed", state="error")
                st.error(str(exc))

    if st.session_state.suggestions is not None:
        sugg = st.session_state.suggestions
        counts = sugg["category"].value_counts()
        m1, m2, m3, m4, m5, m6 = st.columns(6)
        m1.metric("Direct", counts.get("direct", 0))
        m2.metric("Derived", counts.get("derived", 0))
        m3.metric("Hardcode", counts.get("hardcode", 0))
        m4.metric("Conditional", counts.get("conditional", 0))
        m5.metric("Lookup", counts.get("lookup", 0))
        m6.metric("Missing", counts.get("missing", 0))

        gemini_count = int(
            sugg["match_reason"]
            .astype(str)
            .str.contains("Gemini", case=False, na=False)
            .sum()
        )
        if gemini_count:
            st.caption(f"**{gemini_count:,}** rows include Gemini-assisted suggestions.")

        # --- Step 5: Review & edit ---
        st.header("5. Review and edit")
        st.caption("Edit any row inline before approving for export.")

        source_col_options = [""] + list(st.session_state.source_df.columns)

        edited = st.data_editor(
            sugg,
            use_container_width=True,
            num_rows="fixed",
            height=min(600, 35 * len(sugg) + 38),
            column_config={
                "category": st.column_config.SelectboxColumn(
                    "Category", options=list(CATEGORIES)
                ),
                "source_column": st.column_config.SelectboxColumn(
                    "Source column", options=source_col_options
                ),
                "required": st.column_config.CheckboxColumn("Required"),
                "confidence": st.column_config.NumberColumn(
                    "Confidence", format="%.4f", disabled=True
                ),
                "match_reason": st.column_config.TextColumn(
                    "Match reason", disabled=True
                ),
                "detail": st.column_config.TextColumn("Detail"),
                "spec": st.column_config.TextColumn(
                    "Spec (JSON)", help="Structured spec driving code generation"
                ),
            },
            disabled=["target_field", "confidence", "match_reason"],
            key="suggestions_editor",
        )
        st.session_state.suggestions = edited

        validation = build_validation_report(edited)
        if not validation.empty:
            st.subheader("Validation flags")
            st.dataframe(validation, use_container_width=True)

        # --- Step 6: Export ---
        st.header("6. Export")
        st.session_state.reviewed_ready = st.checkbox(
            "Reviewed and ready for export",
            value=st.session_state.reviewed_ready,
            key="reviewed_checkbox",
        )

        if st.session_state.reviewed_ready:
            export_cols = [
                "target_field",
                "required",
                "data_type",
                "category",
                "source_column",
                "hardcode_value",
                "confidence",
                "detail",
                "spec",
                "notes",
                "match_reason",
            ]
            mapping_export = edited[[c for c in export_cols if c in edited.columns]]

            d1, d2, d3, d4 = st.columns(4)
            with d1:
                st.download_button(
                    "Download transformed data CSV",
                    data=generate_transformed_data_csv(
                        st.session_state.source_df, edited
                    ),
                    file_name="transformed_data.csv",
                    mime="text/csv",
                    type="primary",
                )
            with d2:
                st.download_button(
                    "Download mapping CSV",
                    data=dataframe_to_csv_bytes(mapping_export),
                    file_name="mapping_draft.csv",
                    mime="text/csv",
                )
            with d3:
                st.download_button(
                    "Download validation report",
                    data=dataframe_to_csv_bytes(validation),
                    file_name="validation_report.csv",
                    mime="text/csv",
                )
            with d4:
                st.download_button(
                    "Download transform.py",
                    data=generate_transform_script(edited).encode("utf-8"),
                    file_name="transform.py",
                    mime="text/x-python",
                )
        else:
            st.info("Check **Reviewed and ready** to enable exports.")

elif st.session_state.mapping_rows is None:
    st.info("Upload a mapping document to continue.")
elif st.session_state.source_df is None:
    st.info("Connect to a source report (CSV or database) to continue.")
