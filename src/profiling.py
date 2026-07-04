"""Source column profiling."""

from __future__ import annotations

import pandas as pd


def profile_source_columns(
    source_df: pd.DataFrame, sample_size: int = 5, max_rows: int = 10_000
) -> pd.DataFrame:
    row_count = len(source_df)
    work_df = source_df
    if row_count > max_rows:
        work_df = source_df.sample(n=max_rows, random_state=0)
    profiles = []

    for col in work_df.columns:
        series = work_df[col]
        null_count = int(series.isna().sum()) + int((series.astype(str).str.strip() == "").sum())
        null_pct = round((null_count / len(work_df) * 100) if len(work_df) else 0.0, 2)
        non_null = series.dropna().astype(str).str.strip()
        non_null = non_null[non_null != ""]
        unique_count = int(non_null.nunique())
        samples = non_null.head(sample_size).tolist()
        sample_str = ", ".join(samples[:sample_size])
        if len(sample_str) > 120:
            sample_str = sample_str[:117] + "..."

        profiles.append(
            {
                "column": col,
                "dtype": str(source_df[col].dtype),
                "null_pct": null_pct,
                "unique_count": unique_count,
                "sample_values": sample_str,
            }
        )

    return pd.DataFrame(profiles)
