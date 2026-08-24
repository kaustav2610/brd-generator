# Givaudan — Repository Intelligence Console

A minimal, dark-and-gold frontend for the FastAPI `/api/analyze` endpoint.
Lets someone paste a GitHub repo, optionally steer it with module hints,
watch it generate, and download the resulting `BRD.pdf`.

## Run it

```bash
npm install
cp .env.example .env   # then edit VITE_API_BASE_URL if not localhost:8000
npm run dev
```

Opens at `http://localhost:5173`. Make sure your FastAPI service is running
and that CORS allows this origin (your snippet already allows `*`).

## What the form sends

Matches `AnalyzeRequest` exactly:

```json
{
  "repo_url": "https://github.com/org/repo",
  "branch": "main",
  "module_hints": [],
  "upload_source": false
}
```

- **Repository URL** — required.
- **Branch** — defaults to `main`, editable.
- **Module hints** — optional chip list; type and press Enter/comma to add,
  Backspace to remove the last one. Sent as `[]` when empty.
- **Uploaded source** — toggle, off by default, maps to `upload_source`.

## The "Create BRD" flow

Clicking **Create BRD** does a single `POST /api/analyze` and waits for the
response — your endpoint is synchronous, so the UI shows a progress gauge
(a filling vial) with rotating stage labels for the ~3–4 minute wait rather
than polling. When the response lands, it moves straight to the results
screen with the run's stats and a **Download BRD.pdf** button.

## About the download button — please read

Your `/api/analyze` response returns S3 URIs (`s3://...`), which a browser
cannot fetch directly. This frontend assumes a companion **download route**
on your FastAPI service — a reasonable bet since your snippet already
imports `FileResponse` but doesn't use it in `/api/analyze`. The frontend
calls:

```
GET {VITE_API_BASE_URL}/api/download/{run_id}
```

and streams whatever comes back as `Givaudan_BRD_{run_id}.pdf`. If that
route doesn't exist yet, add something like this to your FastAPI app:

```python
from pathlib import Path
from fastapi.responses import FileResponse

@app.get("/api/download/{run_id}")
def download_brd(run_id: str):
    path = Path(f"./outputs/{run_id}/BRD.pdf")  # match wherever you write it locally
    if not path.exists():
        raise HTTPException(status_code=404, detail="BRD not found for this run")
    return FileResponse(path, media_type="application/pdf", filename="BRD.pdf")
```

If your download route lives at a different path, change the one line in
`src/api.js` — `buildDownloadUrl(runId)`.

## Structure

```
src/
  App.jsx      form, progress, and results states
  App.css      the Givaudan visual identity (tokens at the top)
  api.js       fetch calls + the download-route assumption above
  main.jsx     entry point
```

## Build for production

```bash
npm run build
```

Outputs static files to `dist/` — serve them from anywhere (S3 + CloudFront,
nginx, FastAPI's own `StaticFiles`, etc).
