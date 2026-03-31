"use client";

import { useEffect, useRef, useState } from "react";

const CUSTOM_API_BASE = process.env.NEXT_PUBLIC_CUSTOM_API_BASE ?? "http://localhost:8001";
const LLAMA_API_BASE = process.env.NEXT_PUBLIC_LLAMA_API_BASE ?? "http://localhost:8000";

interface Source {
  jurisdiction?: string;
  source?: string;
  section?: string;
  subsection?: string;
  title?: string;
  page?: number;
  score?: number;
  url?: string;
}

interface Accuracy {
  score: number;
  label: string;
  reason: string;
}

interface JurisdictionOption {
  name: string;
  chunks: number;
}

interface RAGResult {
  answer: string;
  sources?: Source[];
  accuracy?: Accuracy;
  error?: boolean;
  duration?: number;
}

export default function Home() {
  const [query, setQuery] = useState("");
  const [llamaResult, setLlamaResult] = useState<RAGResult | null>(null);
  const [customResult, setCustomResult] = useState<RAGResult | null>(null);
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadMessage, setUploadMessage] = useState<string | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [jurisdictions, setJurisdictions] = useState<JurisdictionOption[]>([]);
  const [jurisdictionFilter, setJurisdictionFilter] = useState("");
  const [loadingLlama, setLoadingLlama] = useState(false);
  const [loadingCustom, setLoadingCustom] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    fetch(`${CUSTOM_API_BASE}/jurisdictions`)
      .then((r) => r.json())
      .then((data) => {
        setJurisdictions(Array.isArray(data.jurisdictions) ? data.jurisdictions : []);
      })
      .catch(() => {
        setJurisdictions([]);
      });
  }, []);

  const runQuery = async () => {
    if (!query.trim() || loadingLlama || loadingCustom) return;

    setSubmitted(true);
    setLlamaResult(null);
    setCustomResult(null);
    setLoadingLlama(true);
    setLoadingCustom(true);

    const llamaStart = Date.now();
    const customStart = Date.now();
    const queryParams = new URLSearchParams({ q: query });
    if (jurisdictionFilter) {
      queryParams.set("jurisdiction", jurisdictionFilter);
    }

    const llamaPromise = fetch(
      `${LLAMA_API_BASE}/query?${queryParams.toString()}`
    )
      .then((r) => r.json())
      .then((data) => ({ answer: data.answer, duration: Date.now() - llamaStart }))
      .catch(() => ({
        answer: "Failed to reach the LlamaIndex backend (port 8000).",
        error: true,
        duration: Date.now() - llamaStart,
      }));

    const customPromise = fetch(
      `${CUSTOM_API_BASE}/query?${queryParams.toString()}`
    )
      .then((r) => r.json())
      .then((data) => ({
        answer: data.answer,
        sources: data.sources,
        accuracy: data.accuracy,
        duration: Date.now() - customStart,
      }))
      .catch(() => ({
        answer: "Failed to reach the Custom RAG backend (port 8001).",
        error: true,
        duration: Date.now() - customStart,
      }));

    llamaPromise.then((result) => { setLlamaResult(result); setLoadingLlama(false); });
    customPromise.then((result) => { setCustomResult(result); setLoadingCustom(false); });
  };

  const uploadPdf = async () => {
    if (!uploadFile || uploading) return;

    const formData = new FormData();
    formData.append("file", uploadFile);

    setUploading(true);
    setUploadMessage(null);
    setUploadError(null);

    try {
      const response = await fetch(`${CUSTOM_API_BASE}/upload-pdf`, {
        method: "POST",
        body: formData,
      });

      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.detail || "Upload failed.");
      }

      setUploadMessage(`Saved ${data.filename} to the ordinance PDF folder.`);
      setUploadFile(null);
      fetch(`${CUSTOM_API_BASE}/jurisdictions`)
        .then((r) => r.json())
        .then((data) => {
          setJurisdictions(Array.isArray(data.jurisdictions) ? data.jurisdictions : []);
        })
        .catch(() => {});
    } catch (error) {
      const message = error instanceof Error ? error.message : "Upload failed.";
      setUploadError(message);
    } finally {
      setUploading(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) runQuery();
  };

  const handleClear = () => {
    setQuery("");
    setLlamaResult(null);
    setCustomResult(null);
    setSubmitted(false);
    textareaRef.current?.focus();
  };

  const bothDone = !loadingLlama && !loadingCustom && submitted;

  return (
    <>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Instrument+Serif:ital@0;1&family=IBM+Plex+Mono:wght@300;400;500&display=swap');
        *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
        :root {
          --bg: #0d0f0e;
          --surface: #141716;
          --surface-2: #1c1f1d;
          --border: rgba(255,255,255,0.08);
          --border-strong: rgba(255,255,255,0.15);
          --text: #e8ebe8;
          --text-dim: #7a8478;
          --text-faint: #3d4440;
          --llama-accent: #4ade80;
          --llama-glow: rgba(74,222,128,0.10);
          --llama-dim: rgba(74,222,128,0.30);
          --custom-accent: #60a5fa;
          --custom-glow: rgba(96,165,250,0.10);
          --custom-dim: rgba(96,165,250,0.30);
          --amber: #fbbf24;
          --serif: 'Instrument Serif', Georgia, serif;
          --mono: 'IBM Plex Mono', 'Courier New', monospace;
        }
        html, body { background: var(--bg); }
        .page {
          min-height: 100vh;
          background: var(--bg);
          color: var(--text);
          font-family: var(--mono);
          padding: 40px 24px 80px;
          display: flex;
          flex-direction: column;
          align-items: center;
        }
        .inner { position: relative; z-index: 1; width: 100%; max-width: 1120px; }

        /* HEADER */
        .header {
          display: flex;
          align-items: flex-start;
          justify-content: space-between;
          padding-bottom: 24px;
          border-bottom: 1px solid var(--border);
          margin-bottom: 36px;
          flex-wrap: wrap;
          gap: 16px;
        }
        .eyebrow { font-size: 9px; letter-spacing: 0.25em; text-transform: uppercase; color: var(--text-dim); margin-bottom: 6px; }
        h1 { font-family: var(--serif); font-size: clamp(22px, 3vw, 36px); font-weight: 400; line-height: 1; color: var(--text); }
        h1 span { color: var(--amber); font-style: italic; }
        .badge-row { display: flex; gap: 8px; flex-wrap: wrap; padding-top: 4px; }
        .badge { padding: 4px 10px; border-radius: 2px; font-size: 9px; letter-spacing: 0.15em; text-transform: uppercase; font-weight: 500; border: 1px solid; }
        .badge-llama { background: var(--llama-glow); border-color: var(--llama-dim); color: var(--llama-accent); }
        .badge-custom { background: var(--custom-glow); border-color: var(--custom-dim); color: var(--custom-accent); }

        /* QUERY */
        .query-label { font-size: 9px; letter-spacing: 0.2em; text-transform: uppercase; color: var(--text-dim); margin-bottom: 8px; display: block; }
        .filter-row {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 12px;
          margin-bottom: 12px;
          flex-wrap: wrap;
        }
        .filter-copy { font-size: 10px; letter-spacing: 0.12em; text-transform: uppercase; color: var(--text-dim); }
        .filter-select {
          min-width: 240px;
          padding: 10px 12px;
          border-radius: 2px;
          border: 1px solid var(--border-strong);
          background: var(--surface);
          color: var(--text);
          font-family: var(--mono);
          font-size: 11px;
          letter-spacing: 0.04em;
        }
        .textarea-wrap {
          border: 1px solid var(--border-strong); border-radius: 3px;
          background: var(--surface); overflow: hidden; transition: border-color 0.2s; margin-bottom: 32px;
        }
        .textarea-wrap:focus-within { border-color: rgba(251,191,36,0.4); }
        textarea {
          width: 100%; min-height: 100px; padding: 16px 18px;
          background: transparent; border: none; outline: none; resize: none;
          font-family: var(--mono); font-size: 13px; line-height: 1.75; color: var(--text);
        }
        textarea::placeholder { color: var(--text-faint); }
        .query-footer {
          display: flex; align-items: center; justify-content: space-between;
          padding: 10px 14px; border-top: 1px solid var(--border); background: var(--surface-2);
        }
        .hint { font-size: 10px; color: var(--text-faint); letter-spacing: 0.05em; }
        .btn-row { display: flex; gap: 8px; }
        .btn { padding: 8px 18px; font-family: var(--mono); font-size: 10px; font-weight: 500; letter-spacing: 0.15em; text-transform: uppercase; border-radius: 2px; cursor: pointer; border: 1px solid; transition: all 0.15s; }
        .btn-ghost { background: transparent; border-color: var(--border-strong); color: var(--text-dim); }
        .btn-ghost:hover { border-color: var(--text-dim); color: var(--text); }
        .btn-primary { background: var(--amber); border-color: var(--amber); color: #0d0f0e; }
        .btn-primary:hover:not(:disabled) { background: #fcd34d; }
        .btn-primary:disabled { opacity: 0.4; cursor: not-allowed; }
        .btn-upload { background: transparent; border-color: var(--custom-dim); color: var(--custom-accent); }
        .btn-upload:hover:not(:disabled) { border-color: var(--custom-accent); color: #bfdbfe; }

        /* GRID */
        .compare-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; opacity: 0; transform: translateY(10px); transition: opacity 0.35s, transform 0.35s; }
        .compare-grid.visible { opacity: 1; transform: none; }
        @media (max-width: 720px) { .compare-grid { grid-template-columns: 1fr; } }

        /* UPLOAD */
        .upload-panel {
          margin-bottom: 28px;
          border: 1px solid var(--border);
          border-radius: 3px;
          background: linear-gradient(180deg, rgba(96,165,250,0.05), rgba(20,23,22,0.95));
          padding: 16px;
        }
        .upload-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; margin-bottom: 14px; flex-wrap: wrap; }
        .upload-title { font-size: 10px; letter-spacing: 0.18em; text-transform: uppercase; color: var(--custom-accent); margin-bottom: 6px; }
        .upload-copy { font-size: 12px; line-height: 1.7; color: var(--text-dim); max-width: 700px; }
        .upload-controls { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
        .file-input {
          color: var(--text-dim);
          font-family: var(--mono);
          font-size: 11px;
          max-width: 100%;
        }
        .upload-feedback { margin-top: 10px; font-size: 11px; line-height: 1.6; }
        .upload-feedback.success { color: var(--custom-accent); }
        .upload-feedback.error { color: #f87171; }

        /* CARD */
        .result-card { border: 1px solid var(--border); border-radius: 3px; background: var(--surface); overflow: hidden; display: flex; flex-direction: column; }
        .result-card.llama { border-top: 2px solid var(--llama-accent); }
        .result-card.custom { border-top: 2px solid var(--custom-accent); }
        .card-header { display: flex; align-items: center; justify-content: space-between; padding: 12px 16px; border-bottom: 1px solid var(--border); background: var(--surface-2); }
        .card-title { display: flex; align-items: center; gap: 10px; }
        .card-dot { width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0; }
        .llama .card-dot { background: var(--llama-accent); box-shadow: 0 0 8px var(--llama-dim); }
        .custom .card-dot { background: var(--custom-accent); box-shadow: 0 0 8px var(--custom-dim); }
        .card-name { font-size: 10px; font-weight: 500; letter-spacing: 0.18em; text-transform: uppercase; color: var(--text); }
        .card-sub { font-size: 9px; color: var(--text-dim); letter-spacing: 0.08em; margin-top: 2px; }
        .duration-tag { font-size: 9px; letter-spacing: 0.08em; padding: 2px 7px; border-radius: 2px; border: 1px solid var(--border); color: var(--text-dim); white-space: nowrap; }
        .card-body { padding: 20px; font-size: 13px; line-height: 1.85; color: #c2c9c2; white-space: pre-wrap; flex: 1; min-height: 180px; }
        .card-body.error { color: #f87171; }
        .card-body.faint { color: var(--text-faint); font-style: italic; }

        /* LOADING */
        .loading-state { display: flex; align-items: center; gap: 12px; padding: 20px; min-height: 180px; color: var(--text-faint); font-size: 12px; letter-spacing: 0.08em; }
        .spinner { width: 13px; height: 13px; border-radius: 50%; border: 2px solid var(--border-strong); flex-shrink: 0; animation: spin 0.7s linear infinite; }
        .llama .spinner { border-top-color: var(--llama-accent); }
        .custom .spinner { border-top-color: var(--custom-accent); }
        @keyframes spin { to { transform: rotate(360deg); } }

        /* SOURCES */
        .sources-footer { padding: 12px 16px; border-top: 1px solid var(--border); background: var(--surface-2); }
        .sources-label { font-size: 9px; letter-spacing: 0.18em; text-transform: uppercase; color: var(--text-dim); margin-bottom: 8px; }
        .sources-list { display: flex; flex-wrap: wrap; gap: 6px; }
        .source-chip { padding: 3px 9px; border: 1px solid var(--custom-dim); border-radius: 2px; font-size: 10px; color: var(--custom-accent); letter-spacing: 0.05em; background: var(--custom-glow); text-decoration: none; transition: border-color 0.15s, transform 0.15s; display: inline-flex; align-items: center; }
        .source-chip:hover { border-color: var(--custom-accent); transform: translateY(-1px); }
        .accuracy-wrap { padding: 12px 16px; border-top: 1px solid var(--border); background: rgba(96,165,250,0.04); }
        .accuracy-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 8px; }
        .accuracy-label { font-size: 9px; letter-spacing: 0.18em; text-transform: uppercase; color: var(--text-dim); }
        .accuracy-score { font-size: 11px; color: var(--custom-accent); letter-spacing: 0.1em; text-transform: uppercase; }
        .accuracy-bar { height: 6px; border-radius: 999px; background: rgba(255,255,255,0.06); overflow: hidden; margin-bottom: 8px; }
        .accuracy-fill { height: 100%; background: linear-gradient(90deg, #38bdf8 0%, #60a5fa 100%); }
        .accuracy-reason { font-size: 11px; line-height: 1.6; color: var(--text-dim); }

        /* DIFF BAR */
        .diff-bar { margin-top: 16px; padding: 12px 18px; border: 1px solid var(--border); border-radius: 3px; background: var(--surface); display: flex; align-items: center; gap: 10px; font-size: 11px; color: var(--text-dim); letter-spacing: 0.05em; opacity: 0; transition: opacity 0.4s 0.2s; }
        .diff-bar.visible { opacity: 1; }
        .diff-winner { font-weight: 500; letter-spacing: 0.12em; }
        .diff-winner.llama { color: var(--llama-accent); }
        .diff-winner.custom { color: var(--custom-accent); }
        .diff-winner.tie { color: var(--amber); }

        .page-foot { margin-top: 52px; font-size: 9px; letter-spacing: 0.18em; text-transform: uppercase; color: var(--text-faint); text-align: center; }
      `}</style>

      <div className="page">
        <div className="inner">
          <header className="header">
            <div>
              <p className="eyebrow">Municipal Intelligence · RAG Evaluation</p>
              <h1>Civil <span>AI</span> — System Compare</h1>
            </div>
            <div className="badge-row">
              <span className="badge badge-llama">LlamaIndex · :8000</span>
              <span className="badge badge-custom">Custom RAG · :8001</span>
            </div>
          </header>

          <div className="upload-panel">
            <div className="upload-head">
              <div>
                <div className="upload-title">Upload Ordinance PDF</div>
                <div className="upload-copy">
                  Add a municipal ordinance PDF to the shared source folder. Uploaded files are saved into the backend
                  `Data/PDF` directory, parsed automatically, and made available to both RAG systems.
                </div>
              </div>
              <div className="upload-controls">
                <input
                  className="file-input"
                  type="file"
                  accept="application/pdf,.pdf"
                  onChange={(e) => {
                    const nextFile = e.target.files?.[0] ?? null;
                    setUploadFile(nextFile);
                    setUploadMessage(null);
                    setUploadError(null);
                  }}
                />
                <button
                  className="btn btn-upload"
                  onClick={uploadPdf}
                  disabled={!uploadFile || uploading}
                >
                  {uploading ? "Uploading…" : "Upload PDF"}
                </button>
              </div>
            </div>
            {uploadMessage && <div className="upload-feedback success">{uploadMessage}</div>}
            {uploadError && <div className="upload-feedback error">{uploadError}</div>}
          </div>

          <div className="filter-row">
            <span className="filter-copy">Code Focus</span>
            <select
              className="filter-select"
              value={jurisdictionFilter}
              onChange={(e) => setJurisdictionFilter(e.target.value)}
            >
              <option value="">All indexed codes</option>
              {jurisdictions.map((jurisdiction) => (
                <option key={jurisdiction.name} value={jurisdiction.name}>
                  {jurisdiction.name}
                </option>
              ))}
            </select>
          </div>

          <span className="query-label">Query</span>
          <div className="textarea-wrap">
            <textarea
              ref={textareaRef}
              placeholder="Ask about zoning regulations, building permits, setback requirements, municipal codes…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={handleKeyDown}
            />
            <div className="query-footer">
              <span className="hint">⌘ + Enter to run both systems</span>
              <div className="btn-row">
                {submitted && (
                  <button className="btn btn-ghost" onClick={handleClear}>Clear</button>
                )}
                <button
                  className="btn btn-primary"
                  onClick={runQuery}
                  disabled={!query.trim() || loadingLlama || loadingCustom}
                >
                  {loadingLlama || loadingCustom ? "Running…" : "Run Comparison →"}
                </button>
              </div>
            </div>
          </div>

          <div className={`compare-grid ${submitted ? "visible" : ""}`}>
            {/* LlamaIndex */}
            <div className="result-card llama">
              <div className="card-header">
                <div className="card-title">
                  <div className="card-dot" />
                    <div>
                      <div className="card-name">LlamaIndex RAG</div>
                      <div className="card-sub">
                        VectorStoreIndex · all-MiniLM-L6-v2 · DeepSeek V3
                        {jurisdictionFilter ? ` · filtered to ${jurisdictionFilter}` : ""}
                      </div>
                    </div>
                  </div>
                {llamaResult?.duration !== undefined && (
                  <span className="duration-tag">{(llamaResult.duration / 1000).toFixed(2)}s</span>
                )}
              </div>
              {loadingLlama ? (
                <div className="loading-state">
                  <div className="spinner" />
                  Querying LlamaIndex index…
                </div>
              ) : llamaResult ? (
                <div className={`card-body ${llamaResult.error ? "error" : ""}`}>
                  {llamaResult.answer}
                </div>
              ) : (
                <div className="card-body faint">Awaiting query…</div>
              )}
            </div>

            {/* Custom RAG */}
            <div className="result-card custom">
              <div className="card-header">
                <div className="card-title">
                  <div className="card-dot" />
                    <div>
                      <div className="card-name">Custom RAG</div>
                      <div className="card-sub">
                        Hybrid Search · top_k=5
                        {jurisdictionFilter ? ` · filtered to ${jurisdictionFilter}` : ""}
                      </div>
                    </div>
                  </div>
                {customResult?.duration !== undefined && (
                  <span className="duration-tag">{(customResult.duration / 1000).toFixed(2)}s</span>
                )}
              </div>
              {loadingCustom ? (
                <div className="loading-state">
                  <div className="spinner" />
                  Running hybrid retrieval…
                </div>
              ) : customResult ? (
                <>
                  <div className={`card-body ${customResult.error ? "error" : ""}`}>
                    {customResult.answer}
                  </div>
                  {customResult.accuracy && !customResult.error && (
                    <div className="accuracy-wrap">
                      <div className="accuracy-head">
                        <div className="accuracy-label">Accuracy Estimate</div>
                        <div className="accuracy-score">
                          {customResult.accuracy.score}% · {customResult.accuracy.label}
                        </div>
                      </div>
                      <div className="accuracy-bar">
                        <div
                          className="accuracy-fill"
                          style={{ width: `${customResult.accuracy.score}%` }}
                        />
                      </div>
                      <div className="accuracy-reason">{customResult.accuracy.reason}</div>
                    </div>
                  )}
                  {customResult.sources && customResult.sources.filter(s => s.section || s.subsection).length > 0 && (
                    <div className="sources-footer">
                      <div className="sources-label">Retrieved Sources For This Query</div>
                      <div className="sources-list">
                        {customResult.sources
                          .filter(s => s.section || s.subsection)
                          .map((s, i) => (
                            <a
                              key={i}
                              className="source-chip"
                              href={s.url ?? "#"}
                              target="_blank"
                              rel="noreferrer"
                              title={[
                                s.jurisdiction,
                                s.source,
                                s.title,
                                s.page ? `Page ${s.page}` : undefined,
                              ].filter(Boolean).join(" · ")}
                            >
                              {[s.section, s.subsection].filter(Boolean).join(" › ")}
                              {s.page ? ` · p.${s.page}` : ""}
                            </a>
                          ))}
                      </div>
                    </div>
                  )}
                </>
              ) : (
                <div className="card-body faint">Awaiting query…</div>
              )}
            </div>
          </div>

          {/* Speed diff */}
          {bothDone && llamaResult && customResult && !llamaResult.error && !customResult.error && (
            <div className="diff-bar visible">
              ⚡&nbsp;
              {(() => {
                const lDur = llamaResult.duration ?? 0;
                const cDur = customResult.duration ?? 0;
                const diff = Math.abs(lDur - cDur);
                if (diff < 100) return <><span className="diff-winner tie">Tie</span>&nbsp;— both responded in roughly the same time</>;
                const faster = lDur < cDur ? "llama" : "custom";
                const label = faster === "llama" ? "LlamaIndex" : "Custom RAG";
                return <><span className={`diff-winner ${faster}`}>{label}</span>&nbsp;responded {(diff / 1000).toFixed(2)}s faster</>;
              })()}
            </div>
          )}

          <footer className="page-foot">Civil AI · Municipal Knowledge Engine · RAG Eval Mode</footer>
        </div>
      </div>
    </>
  );
}
