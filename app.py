"""AI-Assisted Mapping Generator — Streamlit pilot app."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.config import AI_BATCH_SIZE, CATEGORIES, DEFAULT_ROW_LIMIT, GEMINI_MODEL, MAX_ROW_LIMIT, PREVIEW_ROW_LIMIT
from src.ai_fallback import is_ai_available
from src.database import (
    is_database_available,
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
from src.codegen import apply_transform, transform_column_warnings
from src.ingestion import build_mapping_rows_auto, load_mapping_document, load_source_csv
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
        "source_profile_key": "",
        "suggestions": None,
        "reviewed_ready": False,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


_init_state()


def _source_fingerprint(df: pd.DataFrame, filename: str = "") -> str:
    return f"{filename}:{len(df)}:{len(df.columns)}"


def _ensure_source_profile() -> None:
    df = st.session_state.source_df
    if df is None:
        return
    key = _source_fingerprint(df, st.session_state.source_filename)
    if (
        st.session_state.get("source_profile_key") != key
        or st.session_state.source_profile is None
    ):
        st.session_state.source_profile = profile_source_columns(df)
        st.session_state.source_profile_key = key


with st.sidebar:
    st.header("Settings")
    if is_ai_available():
        st.success("Gemini API key configured")
        st.caption(f"Model: `{GEMINI_MODEL}`")
        st.caption(f"Batch size: {AI_BATCH_SIZE}")
    else:
        st.error("Add `GEMINI_API_KEY` to `.env` to run this app.")
        st.caption(f"Model (from `.env`): `{GEMINI_MODEL}`")
    st.divider()
    st.caption(
        f"CSV uploads: no row cap. DB loads capped at **{MAX_ROW_LIMIT:,}** rows. "
        f"Previews show up to **{PREVIEW_ROW_LIMIT:,}** rows; exports include all loaded rows."
    )
    st.caption(
        "Gemini speed depends on **mapping target field count**, not source row count."
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
        mapping_rows, column_mapping = build_mapping_rows_auto(raw_df)
        st.session_state.mapping_rows = mapping_rows
        st.caption(f"Detected columns: {column_mapping.summary()}")
        with st.expander("Target fields from mapping document", expanded=True):
            st.code(", ".join(mapping_rows["target_field"].tolist()), language=None)
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
    if not is_database_available():
        st.info(
            "Live database is unavailable in this environment (no `pyodbc` / ODBC driver). "
            "Use **CSV upload** on Streamlit Cloud. On Windows, install with "
            '`pip install "pyodbc>=5.0.0"`.'
        )
    else:
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
    _ensure_source_profile()
    row_count = len(st.session_state.source_df)
    if row_count > 10_000:
        st.caption(
            f"Profile stats sampled from 10,000 of **{row_count:,}** loaded rows."
        )
    st.dataframe(st.session_state.source_profile, width="stretch", height=300)


# --- Step 4: Generate suggestions ---
if (
    st.session_state.mapping_rows is not None
    and st.session_state.source_df is not None
):
    st.header("4. Generate source → target mapping")
    st.caption(
        "Uses Gemini to guess which source column maps to each target field in your mapping document."
    )

    if not is_ai_available():
        st.warning("Configure `GEMINI_API_KEY` in `.env` before generating suggestions.")

    if st.button(
        "Generate suggestions",
        type="primary",
        key="generate",
        disabled=not is_ai_available(),
    ):
        source_cols = list(st.session_state.source_df.columns)
        total_rows = len(st.session_state.mapping_rows)
        with st.status("Calling Gemini to map fields…", expanded=True) as status:
            progress = st.progress(0, text=f"Gemini mapping… 0/{total_rows:,}")

            def on_progress(pct: float) -> None:
                matched = min(int(pct * total_rows), total_rows)
                progress.progress(pct, text=f"Gemini mapping… {matched:,}/{total_rows:,}")

            try:
                st.session_state.suggestions = generate_suggestions(
                    st.session_state.mapping_rows,
                    source_cols,
                    progress_callback=on_progress,
                )
                st.session_state.reviewed_ready = False
                errors = st.session_state.suggestions.attrs.get("gemini_errors", [])
                if errors:
                    st.warning("Some Gemini batches had errors (local name matching used as backup): "
                                 + errors[0])
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
        m1, m2, m3 = st.columns(3)
        m1.metric("Direct", counts.get("direct", 0))
        m2.metric("Hardcode", counts.get("hardcode", 0))
        m3.metric("Missing", counts.get("missing", 0))

        source_col_options = [""] + list(st.session_state.source_df.columns)

        # --- Review & edit ---
        st.header("5. Review and edit mappings")

        edited = st.data_editor(
            sugg,
            width="stretch",
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

        transformed = apply_transform(
            st.session_state.source_df,
            st.session_state.mapping_rows,
            edited,
        )
        for warning in transform_column_warnings(
            transformed,
            st.session_state.mapping_rows,
            st.session_state.source_df,
        ):
            st.error(warning)
        st.caption(f"Output columns: `{', '.join(transformed.columns.tolist())}`")
        populated = int(transformed.notna().any(axis=0).sum())
        total_rows = len(transformed)
        preview_rows = min(total_rows, PREVIEW_ROW_LIMIT)
        st.header("6. Transformed data preview")
        st.caption(
            f"**{total_rows:,}** rows × **{len(transformed.columns):,}** mapping-doc target columns "
            f"({populated:,} populated). Showing first **{preview_rows:,}** rows; "
            f"download includes all **{total_rows:,}**."
        )
        st.dataframe(
            transformed.head(PREVIEW_ROW_LIMIT),
            width="stretch",
            height=min(400, 35 * min(preview_rows, 25) + 38),
        )
        st.download_button(
            "Download transformed data CSV",
            data=generate_transformed_data_csv(
                st.session_state.source_df,
                st.session_state.mapping_rows,
                edited,
            ),
            file_name="transformed_data.csv",
            mime="text/csv",
            type="primary",
            key="download_transformed_preview",
        )

        validation = build_validation_report(edited)
        if not validation.empty:
            st.subheader("Validation flags")
            st.dataframe(validation, width="stretch")

        # --- Step 7: Export ---
        st.header("7. Export")
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

            d1, d2, d3 = st.columns(3)
            with d1:
                st.download_button(
                    "Download mapping CSV",
                    data=dataframe_to_csv_bytes(mapping_export),
                    file_name="mapping_draft.csv",
                    mime="text/csv",
                )
            with d2:
                st.download_button(
                    "Download validation report",
                    data=dataframe_to_csv_bytes(validation),
                    file_name="validation_report.csv",
                    mime="text/csv",
                )
            with d3:
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
