"""Source column profiling."""

from __future__ import annotations

import pandas as pd


def profile_source_columns(source_df: pd.DataFrame, sample_size: int = 5) -> pd.DataFrame:
    row_count = len(source_df)
    profiles = []

    for col in source_df.columns:
        series = source_df[col]
        null_count = int(series.isna().sum()) + int((series.astype(str).str.strip() == "").sum())
        null_pct = round((null_count / row_count * 100) if row_count else 0.0, 2)
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
                "dtype": str(series.dtype),
                "null_pct": null_pct,
                "unique_count": unique_count,
                "sample_values": sample_str,
            }
        )

    return pd.DataFrame(profiles)
