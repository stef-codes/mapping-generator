# Deployment guide

This app is a **Streamlit** pilot. Pick an option based on who needs access and whether you need **live SQL Server** (Windows auth) or **CSV upload only**.

| Option | Best for | Live DB tab | Effort |
|---|---|---|---|
| [Streamlit Community Cloud](#1-streamlit-community-cloud) | Quick share, CSV-only pilot | No* | Low |
| [Docker / Azure / AWS](#2-docker-container) | Team-hosted, scalable | Optional** | Medium |
| [Windows VM or server](#3-windows-server-internal) | Corporate network + SQL Server | Yes | Medium |

\* ODBC + Windows trusted auth does not work on Streamlit Cloud. Use CSV upload.  
\** Requires ODBC Driver 18 in the container and SQL auth (not Windows trusted auth).

---

## Prerequisites (all options)

1. Code pushed to GitHub (`https://github.com/stef-codes/mapping-generator`)
2. Secrets configured on the host (never commit `.env`):

| Variable | Required | Notes |
|---|---|---|
| `GEMINI_API_KEY` | Yes | From [Google AI Studio](https://aistudio.google.com/apikey) |
| `GEMINI_MODEL` | No | Default `gemini-2.5-flash` |
| `AI_BATCH_SIZE` | No | Default `15` |
| `PREVIEW_ROW_LIMIT` | No | Default `500` |
| `DB_DEV_CONNECTION_STRING` | Only for DB tab | Windows trusted auth |
| `DB_QA_CONNECTION_STRING` | Only for DB tab | Windows trusted auth |

---

## 1. Streamlit Community Cloud

Easiest path for a **CSV-only pilot** with colleagues.

1. Go to [share.streamlit.io](https://share.streamlit.io) and sign in with GitHub.
2. **New app** → select repo `stef-codes/mapping-generator`, branch `main`, main file **`app.py`**.
3. Open **Advanced settings → Secrets** and paste **valid TOML** (see `.streamlit/secrets.toml.example`):

   ```toml
   GEMINI_API_KEY = "paste-your-gemini-api-key-here"
   GEMINI_MODEL = "gemini-2.5-flash"
   AI_BATCH_SIZE = "15"
   PREVIEW_ROW_LIMIT = "500"
   ```

   **Not valid** (this is `.env` syntax — Streamlit will reject it):

   ```
   GEMINI_API_KEY=AIzaSy...
   GEMINI_MODEL=gemini-2.5-flash
   ```

   Rules: use `KEY = "value"` (spaces around `=`, double quotes on strings). No `# Copy to .env` header lines unless commented with `#`.

   Streamlit reads these via `st.secrets` (the app merges them into config automatically).

4. Deploy. The app URL will look like `https://your-app.streamlit.app`.

**Limits:** Free tier has resource caps; large CSVs (10k+ rows) may feel slow in the browser preview (export still works). No persistent storage between sessions.

**Important:** Keep `requirements.txt` free of `pyodbc` and Gemini SDKs (`google-generativeai` / `google-genai`). Those native packages often cause **segmentation faults** on Streamlit Cloud. This app calls Gemini over HTTPS REST instead. Use CSV upload in the cloud; install `pyodbc` only on Windows for the Live database tab.

---

## 2. Docker container

Build and run locally or push to Azure Container Apps, AWS App Runner, Google Cloud Run, etc.

```powershell
cd C:\Users\Davis\code\work\mapping-generator
docker build -t mapping-generator .
docker run --rm -p 8501:8501 ^
  -e GEMINI_API_KEY=your-key-here ^
  -e GEMINI_MODEL=gemini-2.5-flash ^
  mapping-generator
```

Open `http://localhost:8501`.

### Azure Container Apps (sketch)

1. Push image to Azure Container Registry.
2. Create a Container App with port **8501**, ingress **external**.
3. Set environment variables in the Container App configuration (same as above).
4. Optional: enable Azure AD auth on the ingress for internal users only.

### SQL Server from Docker (advanced)

The default Dockerfile does **not** install Microsoft ODBC Driver 18. For SQL auth connections, extend the image per [Microsoft's Linux ODBC docs](https://learn.microsoft.com/en-us/sql/connect/odbc/linux-mac/installing-the-microsoft-odbc-driver-for-sql-server) and use a connection string with `UID`/`PWD` instead of `Trusted_Connection=yes`.

---

## 3. Windows server (internal)

Best when users need **live database** access on the corporate network with **Windows trusted authentication**.

### Option A — Run directly (pilot / small team)

On a Windows VM or app server:

```powershell
cd C:\apps\mapping-generator
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
# Edit .env with GEMINI_API_KEY and DB connection strings
streamlit run app.py --server.port 8501 --server.address 0.0.0.0
```

Share `http://<server-name>:8501` on the internal network. Restrict firewall to your VLAN.

### Option B — Windows service (always on)

Use [NSSM](https://nssm.cc/) or a scheduled task at logon to run:

```
C:\apps\mapping-generator\.venv\Scripts\streamlit.exe run C:\apps\mapping-generator\app.py --server.port 8501 --server.address 0.0.0.0
```

Place `.env` next to `app.py` on the server.

### Option C — IIS reverse proxy

Put IIS in front with URL rewrite + HTTPS and optional Windows authentication. Streamlit still runs on localhost:8501; IIS proxies external traffic.

---

## Security checklist

- [ ] `.env` is gitignored and secrets live only on the host / cloud secrets manager
- [ ] Rotate `GEMINI_API_KEY` if it was ever exposed in chat, logs, or commits
- [ ] Restrict network access (VPN, internal IP, or SSO) — the app has no built-in login
- [ ] Treat uploaded CSVs as sensitive; data is held in memory only (not persisted)
- [ ] Review Gemini data handling policy if source reports contain PII

---

## Verify after deploy

1. Sidebar shows **Gemini API key configured** and model name.
2. Upload `sample_data/training_mapping_spec.csv` + `training_source_report.csv`.
3. **Generate suggestions** completes without API errors.
4. **Download transformed data CSV** returns 13 target columns with data.

---

## Troubleshooting

| Issue | Fix |
|---|---|
| Gemini 404 model errors | Set `GEMINI_MODEL=gemini-2.5-flash` |
| DB connection fails on Linux/cloud | Use CSV upload, or deploy on Windows with ODBC Driver 17 |
| App slow with large files | Raise `AI_BATCH_SIZE`; previews capped by `PREVIEW_ROW_LIMIT` |
| Streamlit Cloud build fails | Confirm `requirements.txt` and `app.py` are at repo root |
