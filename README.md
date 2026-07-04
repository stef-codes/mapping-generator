# AI-Assisted Mapping Generator (Pilot)

Streamlit tool that reads a mapping specification and a source report, then produces a **draft** field-level mapping and Python transform script for human review.

## Setup

```powershell
cd C:\Users\Davis\code\work\mapping-generator
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
# Edit .env with your DEV/QA ODBC connection strings and optional GEMINI_API_KEY
```

## Run

```powershell
streamlit run app.py
```

## Workflow

1. Upload mapping document (`.xlsx` / `.csv`)
2. Connect source report — CSV upload or live database via `pyodbc`
3. Mapping document columns are auto-detected from headers (target field, required, data type, notes)
4. Review the auto-generated source column profile
5. Generate suggestions — each target field is classified as:
   - **direct** — confident source column match
   - **derived** — concatenation or date-format logic parsed from notes
   - **hardcode** — constant value parsed from notes
   - **conditional** — if/then/else logic parsed from notes
   - **lookup** — notes indicate a join/reference table is needed
   - **missing** — nothing rule-based matched
6. Edit any row inline (including the `spec` JSON that drives code generation); the `detail` column summarizes what was parsed
7. Check **Reviewed and ready**, then export mapping CSV, validation report CSV, and draft `transform.py`

## Notes

- Hybrid rules-first matching — deterministic parsers for concat, conditional, date-format, hardcode, and lookup notes; optional Gemini fallback for unresolved rows (`GEMINI_API_KEY` in `.env`)
- Database access uses Windows trusted auth; custom SQL gets a `TOP N` safeguard
- Generated code is runnable for direct/derived/conditional/hardcode rows; lookup/missing rows export as `# TODO`
- No data is persisted between sessions

### Gemini AI suggestions

1. Get an API key from [Google AI Studio](https://aistudio.google.com/apikey)
2. Add to `.env`:
   ```
   GEMINI_API_KEY=your-key-here
   GEMINI_MODEL=gemini-2.0-flash
   ```
3. In the app sidebar, enable **Use Gemini for missing fields**
4. Generate suggestions — rules run first; unresolved rows are sent to Gemini in batches of 15

Gemini suggestions appear with match reason `Gemini-assisted suggestion (requires review)`.

## Tests

```powershell
.venv\Scripts\python.exe -m pytest tests/ -q
```
