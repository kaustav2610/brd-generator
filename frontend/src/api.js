// ---------------------------------------------------------------------------
// API configuration
// ---------------------------------------------------------------------------
// Point this at your FastAPI service. Override at build time with
// VITE_API_BASE_URL (create a .env file — see README.md).
export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'

/**
 * Kicks off an analysis run.
 * Mirrors AnalyzeRequest: { repo_url, branch, module_hints, upload_source }
 */
export async function analyzeRepository(payload) {
  const res = await fetch(`${API_BASE_URL}/api/analyze`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })

  if (!res.ok) {
    let detail = `Request failed with status ${res.status}`
    try {
      const body = await res.json()
      detail = body.detail || detail
    } catch {
      // response wasn't JSON — keep the generic message
    }
    throw new Error(detail)
  }

  return res.json()
}

/**
 * Downloads the generated BRD.pdf for a completed run.
 *
 * NOTE: the /api/analyze endpoint you shared returns S3 URIs
 * (s3://...), which a browser can't fetch directly. This assumes a
 * companion download route on your FastAPI service — a natural fit
 * given it already imports `FileResponse`. If that route doesn't
 * exist yet, add something like:
 *
 *   @app.get("/api/download/{run_id}")
 *   def download_brd(run_id: str):
 *       path = Path(f"./outputs/{run_id}/BRD.pdf")
 *       if not path.exists():
 *           raise HTTPException(status_code=404, detail="BRD not found")
 *       return FileResponse(path, media_type="application/pdf", filename="BRD.pdf")
 *
 * Adjust DOWNLOAD_PATH below to match whatever route you expose.
 */
export function buildDownloadUrl(runId) {
  return `${API_BASE_URL}/api/download/${runId}`
}

export async function downloadBrd(runId) {
  const url = buildDownloadUrl(runId)
  const res = await fetch(url)
  if (!res.ok) {
    throw new Error(`Could not fetch BRD.pdf (status ${res.status}). Check that your backend exposes ${url}.`)
  }
  const blob = await res.blob()
  const link = document.createElement('a')
  link.href = window.URL.createObjectURL(blob)
  link.download = `Givaudan_BRD_${runId}.pdf`
  document.body.appendChild(link)
  link.click()
  link.remove()
}
