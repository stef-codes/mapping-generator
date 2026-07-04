# Sample data for pilot testing

Generated files live in `sample_data/`:

| File | Description |
|---|---|
| `mapping_spec.csv` / `.xlsx` | 200-row facility mapping doc (large-scale test) |
| `source_report.csv` | 500-row facility source with 78 columns |
| `training_mapping_spec.csv` | **13-row training migration target schema** (vertical layout) |
| `training_mapping_spec_wide.csv` | Same 13 fields in **wide layout** (`RowType` label column + field names as headers) |
| `training_source_report.csv` | 500-row source with columns for training mapping |

## Training schema (quick demo)

Target fields in `training_mapping_spec.csv`:

`item_id`, `item_title`, `item_type`, `start_datetime`, `end_datetime`, `facility_id`, `facility_name`, `training_contact_id`, `instructor_user_id`, `max_enrollments`, `status`, `external_key`, `migration_notes`

**Quick test:**

1. Upload `sample_data/training_mapping_spec.csv`
2. Upload `sample_data/training_source_report.csv`
3. Click **Generate suggestions**
4. Transformed preview should show **13 columns** (mapping doc targets), not source column names

## Regenerate facility sample data

```powershell
cd C:\Users\Davis\code\work\mapping-generator
.venv\Scripts\Activate.ps1
python scripts/generate_sample_data.py
```
