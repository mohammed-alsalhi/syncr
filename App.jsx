import { useState, useRef } from "react"

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000"

const LANGUAGES = [
  { code: "es", label: "Spanish" },
  { code: "fr", label: "French" },
  { code: "de", label: "German" },
  { code: "ar", label: "Arabic" },
  { code: "zh", label: "Mandarin" },
  { code: "ja", label: "Japanese" },
  { code: "pt", label: "Portuguese" },
  { code: "hi", label: "Hindi" },
  { code: "ko", label: "Korean" },
  { code: "it", label: "Italian" },
]

const STEPS = [
  { key: "queued",       label: "Queued",             pct: 0  },
  { key: "extracting",   label: "Extracting audio",   pct: 10 },
  { key: "diarizing",    label: "Identifying speakers", pct: 25 },
  { key: "transcribing", label: "Transcribing speech", pct: 40 },
  { key: "translating",  label: "Translating",         pct: 55 },
  { key: "synthesizing", label: "Cloning voices",      pct: 70 },
  { key: "compositing",  label: "Compositing video",   pct: 88 },
  { key: "done",         label: "Done!",               pct: 100 },
]

export default function App() {
  const [file, setFile] = useState(null)
  const [language, setLanguage] = useState("es")
  const [jobId, setJobId] = useState(null)
  const [status, setStatus] = useState(null)
  const [originalUrl, setOriginalUrl] = useState(null)
  const [dubbedUrl, setDubbedUrl] = useState(null)
  const [activePlayer, setActivePlayer] = useState("original")
  const [isDragging, setIsDragging] = useState(false)
  const pollRef = useRef(null)
  const fileInputRef = useRef(null)

  const handleFile = (f) => {
    if (!f) return
    setFile(f)
    setOriginalUrl(URL.createObjectURL(f))
    setJobId(null)
    setStatus(null)
    setDubbedUrl(null)
  }

  const handleDrop = (e) => {
    e.preventDefault()
    setIsDragging(false)
    handleFile(e.dataTransfer.files[0])
  }

  const startJob = async () => {
    if (!file) return
    const form = new FormData()
    form.append("file", file)
    form.append("target_language", language)

    const res = await fetch(`${API_BASE}/dub`, { method: "POST", body: form })
    const data = await res.json()
    setJobId(data.job_id)
    setStatus({ status: "queued", step: "Queued", progress: 0 })
    pollRef.current = setInterval(() => pollStatus(data.job_id), 2000)
  }

  const pollStatus = async (id) => {
    const res = await fetch(`${API_BASE}/status/${id}`)
    const data = await res.json()
    setStatus(data)

    if (data.status === "done") {
      clearInterval(pollRef.current)
      setDubbedUrl(`${API_BASE}/download/${id}`)
      setActivePlayer("dubbed")
    }
    if (data.status === "error") {
      clearInterval(pollRef.current)
    }
  }

  const isRunning = status?.status === "running" || status?.status === "queued"
  const isDone = status?.status === "done"
  const isError = status?.status === "error"

  return (
    <div className="min-h-screen bg-[#0a0a0f] text-white font-sans">
      {/* Header */}
      <header className="border-b border-white/10 px-8 py-5 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-violet-500 to-fuchsia-500 flex items-center justify-center text-sm font-bold">M</div>
          <span className="text-xl font-semibold tracking-tight">Mimic</span>
          <span className="text-xs text-white/30 font-mono ml-1">AI Dubbing Studio</span>
        </div>
        <a href="https://github.com" className="text-sm text-white/40 hover:text-white/70 transition-colors">GitHub</a>
      </header>

      <main className="max-w-4xl mx-auto px-6 py-16">
        {/* Hero */}
        <div className="text-center mb-14">
          <h1 className="text-5xl font-bold tracking-tight mb-4 bg-gradient-to-r from-white to-white/50 bg-clip-text text-transparent">
            Any voice. Any language.
          </h1>
          <p className="text-white/50 text-lg max-w-xl mx-auto">
            Upload a video and every actor speaks your target language — in their own voice — in minutes.
          </p>
        </div>

        {/* Upload + Config */}
        {!jobId && (
          <div className="space-y-5">
            {/* Drop zone */}
            <div
              onDragOver={(e) => { e.preventDefault(); setIsDragging(true) }}
              onDragLeave={() => setIsDragging(false)}
              onDrop={handleDrop}
              onClick={() => fileInputRef.current?.click()}
              className={`relative border-2 border-dashed rounded-2xl p-12 text-center cursor-pointer transition-all
                ${isDragging ? "border-violet-400 bg-violet-500/10" : "border-white/10 hover:border-white/25 hover:bg-white/[0.02]"}
                ${file ? "border-violet-500/50 bg-violet-500/5" : ""}`}
            >
              <input ref={fileInputRef} type="file" accept="video/*" className="hidden" onChange={(e) => handleFile(e.target.files[0])} />
              {file ? (
                <div>
                  <div className="text-4xl mb-3">🎬</div>
                  <p className="font-medium">{file.name}</p>
                  <p className="text-sm text-white/40 mt-1">{(file.size / 1e6).toFixed(1)} MB — click to change</p>
                </div>
              ) : (
                <div>
                  <div className="text-4xl mb-3">⬆️</div>
                  <p className="font-medium">Drop a video file here</p>
                  <p className="text-sm text-white/40 mt-1">MP4, MOV, AVI supported</p>
                </div>
              )}
            </div>

            {/* Language selector */}
            <div className="flex gap-3 flex-wrap">
              {LANGUAGES.map((lang) => (
                <button
                  key={lang.code}
                  onClick={() => setLanguage(lang.code)}
                  className={`px-4 py-2 rounded-full text-sm font-medium transition-all
                    ${language === lang.code
                      ? "bg-violet-500 text-white"
                      : "bg-white/5 text-white/50 hover:bg-white/10 hover:text-white"
                    }`}
                >
                  {lang.label}
                </button>
              ))}
            </div>

            {/* Start button */}
            <button
              onClick={startJob}
              disabled={!file}
              className="w-full py-4 rounded-xl font-semibold text-lg
                bg-gradient-to-r from-violet-600 to-fuchsia-600
                hover:from-violet-500 hover:to-fuchsia-500
                disabled:opacity-30 disabled:cursor-not-allowed
                transition-all"
            >
              Dub this video →
            </button>
          </div>
        )}

        {/* Progress */}
        {isRunning && (
          <div className="space-y-8">
            <div className="bg-white/5 rounded-2xl p-8 border border-white/10">
              <div className="flex items-center justify-between mb-6">
                <span className="font-semibold text-lg">{status?.step}</span>
                <span className="text-white/40 font-mono text-sm">{status?.progress}%</span>
              </div>

              {/* Progress bar */}
              <div className="w-full bg-white/10 rounded-full h-2 mb-8">
                <div
                  className="bg-gradient-to-r from-violet-500 to-fuchsia-500 h-2 rounded-full transition-all duration-700"
                  style={{ width: `${status?.progress}%` }}
                />
              </div>

              {/* Step indicators */}
              <div className="grid grid-cols-4 gap-3">
                {STEPS.filter(s => s.key !== "queued").map((step) => {
                  const done = status?.progress >= step.pct
                  const active = Math.abs(status?.progress - step.pct) < 15
                  return (
                    <div key={step.key} className={`text-xs rounded-lg p-2 text-center transition-all
                      ${done ? "bg-violet-500/20 text-violet-300" : "bg-white/5 text-white/30"}
                      ${active ? "ring-1 ring-violet-400" : ""}`}
                    >
                      {step.label}
                    </div>
                  )
                })}
              </div>
            </div>
          </div>
        )}

        {/* Error */}
        {isError && (
          <div className="bg-red-500/10 border border-red-500/30 rounded-2xl p-6">
            <p className="text-red-400 font-medium">Pipeline failed</p>
            <p className="text-red-400/70 text-sm mt-1">{status?.error}</p>
            <button onClick={() => { setJobId(null); setStatus(null) }} className="mt-4 text-sm text-white/50 hover:text-white">
              ← Try again
            </button>
          </div>
        )}

        {/* Before / After Player */}
        {isDone && originalUrl && dubbedUrl && (
          <div className="space-y-6">
            <div className="flex items-center justify-between">
              <h2 className="text-xl font-semibold">Your dubbed video is ready</h2>
              <a
                href={dubbedUrl}
                download="mimic_dubbed.mp4"
                className="px-5 py-2 rounded-lg bg-violet-600 hover:bg-violet-500 text-sm font-medium transition-colors"
              >
                Download
              </a>
            </div>

            {/* Toggle */}
            <div className="flex gap-1 bg-white/5 p-1 rounded-xl w-fit">
              {["original", "dubbed"].map((p) => (
                <button
                  key={p}
                  onClick={() => setActivePlayer(p)}
                  className={`px-5 py-2 rounded-lg text-sm font-medium capitalize transition-all
                    ${activePlayer === p ? "bg-violet-600 text-white" : "text-white/40 hover:text-white"}`}
                >
                  {p}
                </button>
              ))}
            </div>

            {/* Video player */}
            <div className="rounded-2xl overflow-hidden bg-black border border-white/10">
              <video
                key={activePlayer}
                src={activePlayer === "original" ? originalUrl : dubbedUrl}
                controls
                autoPlay
                className="w-full"
              />
            </div>

            <button
              onClick={() => { setJobId(null); setStatus(null); setFile(null); setOriginalUrl(null); setDubbedUrl(null) }}
              className="text-sm text-white/30 hover:text-white/60 transition-colors"
            >
              ← Dub another video
            </button>
          </div>
        )}
      </main>
    </div>
  )
}
