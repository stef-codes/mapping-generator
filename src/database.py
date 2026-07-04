"""Database connectivity via pyodbc (Windows trusted auth)."""

from __future__ import annotations

import os
import re
from pathlib import Path

import pandas as pd
import pyodbc
from dotenv import load_dotenv

from src.config import DEFAULT_ROW_LIMIT, MAX_ROW_LIMIT

ENV_KEYS = {
    "DEV": "DB_DEV_CONNECTION_STRING",
    "QA": "DB_QA_CONNECTION_STRING",
}


def load_env() -> None:
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")


def get_connection_string(environment: str) -> str:
    load_env()
    key = ENV_KEYS.get(environment.upper())
    if not key:
        raise ValueError(f"Unknown environment: {environment}")
    conn_str = os.getenv(key, "").strip()
    if not conn_str:
        raise ValueError(
            f"No connection string configured for {environment}. "
            f"Set {key} in .env (see .env.example)."
        )
    return conn_str


def test_connection(environment: str) -> tuple[bool, str]:
    try:
        conn_str = get_connection_string(environment)
        with pyodbc.connect(conn_str, timeout=10) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            cursor.fetchone()
        return True, f"Connected to {environment} successfully."
    except Exception as exc:
        return False, str(exc)


def list_tables(environment: str) -> list[str]:
    conn_str = get_connection_string(environment)
    query = """
        SELECT TABLE_SCHEMA, TABLE_NAME
        FROM INFORMATION_SCHEMA.TABLES
        WHERE TABLE_TYPE = 'BASE TABLE'
        ORDER BY TABLE_SCHEMA, TABLE_NAME
    """
    with pyodbc.connect(conn_str, timeout=30) as conn:
        df = pd.read_sql(query, conn)
    return [f"{r.TABLE_SCHEMA}.{r.TABLE_NAME}" for r in df.itertuples(index=False)]


def _clamp_limit(row_limit: int) -> int:
    return max(1, min(row_limit, MAX_ROW_LIMIT))


def load_table(
    environment: str, table_name: str, row_limit: int = DEFAULT_ROW_LIMIT
) -> pd.DataFrame:
    limit = _clamp_limit(row_limit)
    if "." in table_name:
        schema, table = table_name.split(".", 1)
        qualified = f"[{schema}].[{table}]"
    else:
        qualified = f"[{table_name}]"

    query = f"SELECT TOP {limit} * FROM {qualified}"
    conn_str = get_connection_string(environment)
    with pyodbc.connect(conn_str, timeout=60) as conn:
        return pd.read_sql(query, conn)


_HAS_ROW_LIMIT = re.compile(
    r"\b(TOP\s+\d+|FETCH\s+FIRST\s+\d+\s+ROWS\s+ONLY|LIMIT\s+\d+|OFFSET\s+\d+\s+ROWS)\b",
    re.IGNORECASE,
)


def inject_row_limit(sql: str, row_limit: int = DEFAULT_ROW_LIMIT) -> str:
    """Inject TOP N safeguard if the query has no existing row limit."""
    stripped = sql.strip().rstrip(";")
    if _HAS_ROW_LIMIT.search(stripped):
        return stripped

    limit = _clamp_limit(row_limit)
    match = re.match(r"^(\s*SELECT\s+(?:DISTINCT\s+)?)", stripped, re.IGNORECASE)
    if match:
        prefix = match.group(1)
        rest = stripped[match.end() :]
        return f"{prefix}TOP {limit} {rest}"

    return stripped


def run_custom_query(
    environment: str, sql: str, row_limit: int = DEFAULT_ROW_LIMIT
) -> pd.DataFrame:
    safe_sql = inject_row_limit(sql, row_limit)
    conn_str = get_connection_string(environment)
    with pyodbc.connect(conn_str, timeout=120) as conn:
        return pd.read_sql(safe_sql, conn)
