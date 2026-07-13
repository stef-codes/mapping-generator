# AI-Assisted Mapping Generator (Pilot)

Streamlit tool that reads a mapping specification and a source report, then produces a **draft** field-level mapping and Python transform script for human review.

[![Demo video](https://img.youtube.com/vi/gKp7X6h45-c/maxresdefault.jpg)](https://youtu.be/gKp7X6h45-c)

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
5. Generate suggestions — Gemini maps each target field to a source column (`direct`, `hardcode`, or `missing`)
6. Edit any row inline (including the `spec` JSON that drives code generation); the `detail` column summarizes what was parsed
7. Check **Reviewed and ready**, then export mapping CSV, validation report CSV, and draft `transform.py`

## Notes

- Hybrid Gemini mapping — every target field is mapped via Gemini (`GEMINI_API_KEY` in `.env`); rules-based parsers remain for optional codegen of derived/conditional specs if you edit rows manually
- Database access uses Windows trusted auth; custom SQL gets a `TOP N` safeguard
- Generated code is runnable for direct/derived/conditional/hardcode rows; lookup/missing rows export as `# TODO`
- No data is persisted between sessions

### Gemini mapping

1. Get an API key from [Google AI Studio](https://aistudio.google.com/apikey)
2. Add to `.env`:
   ```
   GEMINI_API_KEY=your-key-here
   GEMINI_MODEL=gemini-2.5-flash
   ```
3. Upload mapping doc + source report, then click **Generate suggestions** — Gemini maps every target field to a source column (batched, 15 fields per API call by default)

## Tests

```powershell
.venv\Scripts\python.exe -m pytest tests/ -q
```

## Deploy

See **[DEPLOY.md](DEPLOY.md)** for Streamlit Cloud, Docker, and internal Windows server options.
