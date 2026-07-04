# Sample data for pilot testing

Generated files live in `sample_data/`:

| File | Description |
|---|---|
| `mapping_spec.csv` / `.xlsx` | 200-row mapping doc with direct, hardcode, lookup, and missing fields |
| `source_report.csv` | 500-row source with 78 columns (70+ target-relevant + extras) |

## Regenerate

```powershell
cd C:\Users\Davis\code\work\mapping-generator
.venv\Scripts\Activate.ps1
python scripts/generate_sample_data.py
```

## Quick test in the app

1. Upload `sample_data/mapping_spec.xlsx`
2. Map columns: **Target Field** → target, **Required** → required, **Data Type** → dtype, **Transformation Notes** → notes
3. Upload `sample_data/source_report.csv` as the source
4. Generate suggestions and review the mix of categories

Expected highlights:
- `facility_id` → direct match to `facility_id`
- `square_footage` → **missing** (source column is `sqft`)
- Hardcode/lookup rows detected from notes text
