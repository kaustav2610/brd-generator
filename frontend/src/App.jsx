import { useEffect, useRef, useState } from 'react'
import { analyzeRepository, downloadBrd } from './api'
import './App.css'

const STAGES = [
  { at: 0, label: 'Cloning repository' },
  { at: 12, label: 'Reading source files' },
  { at: 32, label: 'Extracting business rules' },
  { at: 58, label: 'Mapping workflows' },
  { at: 80, label: 'Composing BRD.pdf' },
  { at: 94, label: 'Finalizing artifacts' },
]

// Rough expected duration, used only to drive the progress gauge.
// The real run finishes whenever the API responds — this never blocks that.
const EXPECTED_SECONDS = 220

function formatTime(totalSeconds) {
  const m = Math.floor(totalSeconds / 60)
  const s = Math.floor(totalSeconds % 60)
  return `${m}:${String(s).padStart(2, '0')}`
}

function ScentGauge({ progress }) {
  // A minimal atomizer/vial silhouette. The gold liquid rises with `progress` (0-100).
  const fillHeight = 177 * (progress / 100)
  const fillY = 195 - fillHeight
  return (
    <svg className="gauge" viewBox="0 0 80 200" fill="none" xmlns="http://www.w3.org/2000/svg">
      <defs>
        <clipPath id="vialClip">
          <path d="M28 18H52V44C52 48 56 50 60 54C66 60 68 68 68 80V182C68 189 62 195 55 195H25C18 195 12 189 12 182V80C12 68 14 60 20 54C24 50 28 48 28 44V18Z" />
        </clipPath>
        <linearGradient id="goldFill" x1="0" y1="1" x2="0" y2="0">
          <stop offset="0%" stopColor="#C9A227" />
          <stop offset="100%" stopColor="#EBD48A" />
        </linearGradient>
      </defs>

      <rect x="24" y="8" width="32" height="10" rx="1.5" className="gauge-cap" />

      <path
        d="M28 18H52V44C52 48 56 50 60 54C66 60 68 68 68 80V182C68 189 62 195 55 195H25C18 195 12 189 12 182V80C12 68 14 60 20 54C24 50 28 48 28 44V18Z"
        className="gauge-outline"
      />

      <g clipPath="url(#vialClip)">
        <rect x="8" y={fillY} width="64" height="177" fill="url(#goldFill)" className="gauge-liquid" />
        <rect x="8" y={fillY - 2} width="64" height="3" fill="#F4E4A8" opacity="0.8" />
      </g>
    </svg>
  )
}

function ModuleHintsInput({ hints, setHints }) {
  const [draft, setDraft] = useState('')

  const commit = () => {
    const value = draft.trim()
    if (value && !hints.includes(value)) {
      setHints([...hints, value])
    }
    setDraft('')
  }

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' || e.key === ',') {
      e.preventDefault()
      commit()
    } else if (e.key === 'Backspace' && draft === '' && hints.length > 0) {
      setHints(hints.slice(0, -1))
    }
  }

  return (
    <div className="hint-field">
      {hints.map((h) => (
        <span className="chip" key={h}>
          {h}
          <button
            type="button"
            className="chip-remove"
            aria-label={`Remove ${h}`}
            onClick={() => setHints(hints.filter((x) => x !== h))}
          >
            ×
          </button>
        </span>
      ))}
      <input
        type="text"
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={handleKeyDown}
        onBlur={commit}
        placeholder={hints.length === 0 ? 'e.g. inventory management — press Enter to add' : 'Add another…'}
      />
    </div>
  )
}

export default function App() {
  const [phase, setPhase] = useState('form') // form | running | done | error
  const [repoUrl, setRepoUrl] = useState('')
  const [branch, setBranch] = useState('main')
  const [hints, setHints] = useState([])
  const [uploadSource, setUploadSource] = useState(false)

  const [elapsed, setElapsed] = useState(0)
  const [result, setResult] = useState(null)
  const [errorMsg, setErrorMsg] = useState('')
  const [downloadState, setDownloadState] = useState('idle') // idle | working | error

  const timerRef = useRef(null)

  useEffect(() => {
    if (phase !== 'running') return
    setElapsed(0)
    timerRef.current = setInterval(() => setElapsed((t) => t + 1), 1000)
    return () => clearInterval(timerRef.current)
  }, [phase])

  const progress = Math.min(97, (elapsed / EXPECTED_SECONDS) * 100)
  const stageLabel = [...STAGES].reverse().find((s) => progress >= s.at)?.label ?? STAGES[0].label

  const isValid = repoUrl.trim().length > 0

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!isValid || phase === 'running') return

    setErrorMsg('')
    setResult(null)
    setPhase('running')

    try {
      const payload = {
        repo_url: repoUrl.trim(),
        branch: branch.trim() || 'main',
        module_hints: hints,
        upload_source: uploadSource,
      }
      const data = await analyzeRepository(payload)
      setResult(data)
      setPhase('done')
    } catch (err) {
      setErrorMsg(err.message || 'Something went wrong while generating the BRD.')
      setPhase('error')
    }
  }

  const handleReset = () => {
    setPhase('form')
    setResult(null)
    setErrorMsg('')
    setDownloadState('idle')
  }

  const handleDownload = async () => {
    if (!result?.run_id) return
    setDownloadState('working')
    try {
      await downloadBrd(result.run_id)
      setDownloadState('idle')
    } catch (err) {
      setDownloadState('error')
      setErrorMsg(err.message)
    }
  }

  return (
    <div className="stage">
      <div className="backdrop" aria-hidden="true">
        <svg className="ripple" viewBox="0 0 800 800" fill="none">
          <circle cx="400" cy="400" r="120" />
          <circle cx="400" cy="400" r="220" />
          <circle cx="400" cy="400" r="320" />
        </svg>
      </div>

      <header className="mark">
        <span className="mark-word">GIVAUDAN</span>
        <span className="mark-rule" />
        <span className="mark-sub">Repository Intelligence</span>
      </header>

      <main className="panel-wrap">
        {phase === 'form' || phase === 'error' ? (
          <form className="panel" onSubmit={handleSubmit}>
            <p className="eyebrow">New analysis</p>
            <h1>Draft a BRD from a codebase.</h1>
            <p className="lede">
              Point this at a repository and receive a business requirements document,
              distilled from the code by hand — an AI-read hand, held to Givaudan's standard.
            </p>

            <label className="field">
              <span className="field-label">Repository URL</span>
              <input
                type="url"
                required
                value={repoUrl}
                onChange={(e) => setRepoUrl(e.target.value)}
                placeholder="https://github.com/organization/repository"
                className="input"
              />
            </label>

            <div className="field-row">
              <label className="field field-branch">
                <span className="field-label">Branch</span>
                <input
                  type="text"
                  value={branch}
                  onChange={(e) => setBranch(e.target.value)}
                  placeholder="main"
                  className="input"
                />
              </label>

              <label className="field field-toggle">
                <span className="field-label">Uploaded source</span>
                <button
                  type="button"
                  role="switch"
                  aria-checked={uploadSource}
                  className={`switch ${uploadSource ? 'on' : ''}`}
                  onClick={() => setUploadSource((v) => !v)}
                >
                  <span className="switch-knob" />
                </button>
              </label>
            </div>
            <p className="hint-text hint-text--tight">
              {uploadSource
                ? 'Analyzing previously uploaded source rather than cloning from GitHub.'
                : 'Off by default — source is cloned directly from the repository URL above.'}
            </p>

            <label className="field">
              <span className="field-label">
                Module hints <span className="optional">optional</span>
              </span>
              <ModuleHintsInput hints={hints} setHints={setHints} />
              <p className="hint-text">Guide the analysis toward specific modules, or leave blank to let it survey the whole repository.</p>
            </label>

            {phase === 'error' && (
              <div className="banner banner-error">
                <span>{errorMsg}</span>
              </div>
            )}

            <button type="submit" className="btn-primary" disabled={!isValid}>
              Create BRD
            </button>
          </form>
        ) : null}

        {phase === 'running' ? (
          <div className="panel panel-running">
            <p className="eyebrow">Thinking, then creating</p>
            <ScentGauge progress={progress} />
            <h2 className="stage-label">{stageLabel}</h2>
            <p className="repo-echo">{repoUrl}</p>
            <div className="progress-track">
              <div className="progress-fill" style={{ width: `${progress}%` }} />
            </div>
            <p className="timer">{formatTime(elapsed)} elapsed · usually 3–15 minutes</p>
          </div>
        ) : null}

        {phase === 'done' && result ? (
          <div className="panel panel-done">
            <p className="eyebrow">Analysis complete</p>
            <h1>The BRD is ready.</h1>
            <p className="lede">
              {result.summary?.repository} <span className="dim">on</span> {result.summary?.branch}
            </p>

            <div className="stat-grid">
              <div className="stat">
                <span className="stat-value">{result.summary?.duration_seconds != null ? `${Math.round(result.summary.duration_seconds)}s` : '—'}</span>
                <span className="stat-label">Duration</span>
              </div>
              <div className="stat">
                <span className="stat-value">{result.summary?.files_analyzed ?? '—'}</span>
                <span className="stat-label">Files analyzed</span>
              </div>
              <div className="stat">
                <span className="stat-value">{result.summary?.chunks_analyzed ?? '—'}</span>
                <span className="stat-label">Chunks analyzed</span>
              </div>
              <div className="stat">
                <span className="stat-value">{result.summary?.business_rules ?? '—'}</span>
                <span className="stat-label">Business rules</span>
              </div>
              <div className="stat">
                <span className="stat-value">{result.summary?.workflows ?? '—'}</span>
                <span className="stat-label">Workflows</span>
              </div>
              <div className="stat">
                <span className="stat-value">{result.summary?.entities ?? '—'}</span>
                <span className="stat-label">Entities</span>
              </div>
            </div>

            {result.summary?.languages && Object.keys(result.summary.languages).length > 0 && (
              <div className="lang-row">
                {Object.entries(result.summary.languages).map(([lang, count]) => (
                  <span className="lang-chip" key={lang}>
                    {lang} <span className="dim">· {count}</span>
                  </span>
                ))}
              </div>
            )}

            {result.summary?.potential_secret_files?.length > 0 && (
              <div className="banner banner-warn">
                <span>{result.summary.potential_secret_files.length} file(s) flagged for potential secrets — review before sharing.</span>
              </div>
            )}

            {downloadState === 'error' && (
              <div className="banner banner-error">
                <span>{errorMsg}</span>
              </div>
            )}

            <div className="run-id">
              Run <span className="mono">{result.run_id}</span> · {result.artifacts?.length ?? 0} artifacts generated
            </div>

            <div className="btn-row">
              <button type="button" className="btn-primary" onClick={handleDownload} disabled={downloadState === 'working'}>
                {downloadState === 'working' ? 'Preparing download…' : 'Download BRD.pdf'}
              </button>
              <button type="button" className="btn-ghost" onClick={handleReset}>
                Start new analysis
              </button>
            </div>
          </div>
        ) : null}
      </main>

      <footer className="foot">
        <span>Bedrock-assisted analysis · artifacts stored per run</span>
      </footer>
    </div>
  )
}
