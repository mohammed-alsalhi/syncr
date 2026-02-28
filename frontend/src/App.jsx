import { useState, useRef, useEffect, useCallback } from "react"

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

const PIPELINE_STEPS = [
  { key: "chunking", label: "Chunking", icon: "scissors" },
  { key: "diarizing", label: "Diarize", icon: "users" },
  { key: "transcribing", label: "Transcribe", icon: "mic" },
  { key: "translating", label: "Translate", icon: "globe" },
  { key: "synthesizing", label: "Synthesize", icon: "waveform" },
  { key: "quality", label: "Quality", icon: "check" },
  { key: "compositing", label: "Composite", icon: "film" },
]

const SPEAKER_COLORS = ["#818cf8", "#34d399", "#fb923c", "#f472b6", "#38bdf8", "#a78bfa", "#fbbf24"]

function getStepStatus(step, currentStep, progress) {
  const stepKeywords = {
    chunking: ["Analyzing", "chunk", "Chunking"],
    diarizing: ["Diariz", "speaker", "Identifying"],
    transcribing: ["Transcrib", "speech", "Whisper"],
    translating: ["Translat", "dialogue"],
    synthesizing: ["Clon", "voice", "synth"],
    quality: ["Quality", "Verif", "Re-process"],
    compositing: ["Composit", "Saving", "merg", "Done"],
  }
  const keywords = stepKeywords[step.key] || []
  const isActive = keywords.some(kw => currentStep?.toLowerCase().includes(kw.toLowerCase()))
  const stepOrder = PIPELINE_STEPS.findIndex(s => s.key === step.key)
  const activeIdx = PIPELINE_STEPS.findIndex(s => {
    const kws = stepKeywords[s.key] || []
    return kws.some(kw => currentStep?.toLowerCase().includes(kw.toLowerCase()))
  })
  if (progress >= 100) return "done"
  if (isActive) return "active"
  if (activeIdx >= 0 && stepOrder < activeIdx) return "done"
  return "pending"
}

function StepIcon({ icon, className = "" }) {
  const icons = {
    scissors: <path strokeLinecap="round" strokeLinejoin="round" d="M7.5 8.25l-2.5 2.5m0 0l-2.5-2.5M5 10.75v-8.5m7-1l2.5 2.5m0 0l2.5-2.5M14.5 3.75v8.5M3.5 16.5a2 2 0 104 0 2 2 0 00-4 0zm9 0a2 2 0 104 0 2 2 0 00-4 0z" />,
    users: <path strokeLinecap="round" strokeLinejoin="round" d="M15 19.128a9.38 9.38 0 002.625.372 9.337 9.337 0 004.121-.952 4.125 4.125 0 00-7.533-2.493M15 19.128v-.003c0-1.113-.285-2.16-.786-3.07M15 19.128v.106A12.318 12.318 0 018.624 21c-2.331 0-4.512-.645-6.374-1.766l-.001-.109a6.375 6.375 0 0111.964-3.07M12 6.375a3.375 3.375 0 11-6.75 0 3.375 3.375 0 016.75 0zm8.25 2.25a2.625 2.625 0 11-5.25 0 2.625 2.625 0 015.25 0z" />,
    mic: <path strokeLinecap="round" strokeLinejoin="round" d="M12 18.75a6 6 0 006-6v-1.5m-6 7.5a6 6 0 01-6-6v-1.5m6 7.5v3.75m-3.75 0h7.5M12 15.75a3 3 0 01-3-3V4.5a3 3 0 116 0v8.25a3 3 0 01-3 3z" />,
    globe: <path strokeLinecap="round" strokeLinejoin="round" d="M12 21a9.004 9.004 0 008.716-6.747M12 21a9.004 9.004 0 01-8.716-6.747M12 21c2.485 0 4.5-4.03 4.5-9S14.485 3 12 3m0 18c-2.485 0-4.5-4.03-4.5-9S9.515 3 12 3m0 0a8.997 8.997 0 017.843 4.582M12 3a8.997 8.997 0 00-7.843 4.582m15.686 0A11.953 11.953 0 0112 10.5c-2.998 0-5.74-1.1-7.843-2.918m15.686 0A8.959 8.959 0 0121 12c0 .778-.099 1.533-.284 2.253m0 0A17.919 17.919 0 0112 16.5a17.92 17.92 0 01-8.716-2.247m0 0A9.015 9.015 0 013 12c0-1.605.42-3.113 1.157-4.418" />,
    waveform: <path strokeLinecap="round" strokeLinejoin="round" d="M9.348 14.651a3.75 3.75 0 010-5.303m5.304 0a3.75 3.75 0 010 5.303m-7.425 2.122a6.75 6.75 0 010-9.546m9.546 0a6.75 6.75 0 010 9.546M5.106 18.894c-3.808-3.808-3.808-9.98 0-13.789m13.788 0c3.808 3.808 3.808 9.981 0 13.79M12 12h.008v.007H12V12zm.375 0a.375.375 0 11-.75 0 .375.375 0 01.75 0z" />,
    check: <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />,
    film: <path strokeLinecap="round" strokeLinejoin="round" d="M3.375 19.5h17.25m-17.25 0a1.125 1.125 0 01-1.125-1.125M3.375 19.5h1.5C5.496 19.5 6 18.996 6 18.375m-2.625 0V5.625m0 12.75v-1.5c0-.621.504-1.125 1.125-1.125m18.375 2.625V5.625m0 12.75c0 .621-.504 1.125-1.125 1.125m1.125-1.125v-1.5c0-.621-.504-1.125-1.125-1.125m0 3.75h-1.5A1.125 1.125 0 0118 18.375M20.625 4.5H3.375m17.25 0c.621 0 1.125.504 1.125 1.125M20.625 4.5h-1.5C18.504 4.5 18 5.004 18 5.625m3.75 0v1.5c0 .621-.504 1.125-1.125 1.125M3.375 4.5c-.621 0-1.125.504-1.125 1.125M3.375 4.5h1.5C5.496 4.5 6 5.004 6 5.625m-3.75 0v1.5c0 .621.504 1.125 1.125 1.125m0 0h1.5m-1.5 0c-.621 0-1.125.504-1.125 1.125v1.5c0 .621.504 1.125 1.125 1.125m1.5-3.75C5.496 8.25 6 7.746 6 7.125v-1.5M4.875 8.25C5.496 8.25 6 8.754 6 9.375v1.5m0-5.25v5.25m0-5.25C6 5.004 6.504 4.5 7.125 4.5h9.75c.621 0 1.125.504 1.125 1.125m1.125 2.625h1.5m-1.5 0A1.125 1.125 0 0118 7.125v-1.5m1.125 2.625c-.621 0-1.125.504-1.125 1.125v1.5m2.625-2.625c.621 0 1.125.504 1.125 1.125v1.5c0 .621-.504 1.125-1.125 1.125M18 5.625v5.25M7.125 12h9.75m-9.75 0A1.125 1.125 0 016 10.875M7.125 12C6.504 12 6 12.504 6 13.125m0-2.25C6 11.496 5.496 12 4.875 12M18 10.875c0 .621-.504 1.125-1.125 1.125M18 10.875c0 .621.504 1.125 1.125 1.125m-2.25 0c.621 0 1.125.504 1.125 1.125m-12 5.25v-5.25m0 5.25c0 .621.504 1.125 1.125 1.125h9.75c.621 0 1.125-.504 1.125-1.125m-12 0v-1.5c0-.621-.504-1.125-1.125-1.125M18 18.375v-5.25m0 5.25v-1.5c0-.621.504-1.125 1.125-1.125M18 13.125v1.5c0 .621.504 1.125 1.125 1.125M18 13.125c0-.621.504-1.125 1.125-1.125M6 13.125v1.5c0 .621-.504 1.125-1.125 1.125M6 13.125C6 12.504 5.496 12 4.875 12m-1.5 0h1.5m-1.5 0c-.621 0-1.125-.504-1.125-1.125v-1.5c0-.621.504-1.125 1.125-1.125m12.75 0h1.5m-1.5 0c-.621 0-1.125.504-1.125 1.125v1.5" />,
  }
  return (
    <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className={`w-4 h-4 ${className}`}>
      {icons[icon]}
    </svg>
  )
}

function PipelineNode({ step, status }) {
  return (
    <div className={`flex flex-col items-center gap-1.5 px-2 min-w-[72px] transition-all duration-500
      ${status === "active" ? "scale-110" : ""}
    `}>
      <div className={`w-10 h-10 rounded-xl flex items-center justify-center transition-all duration-500
        ${status === "done" ? "bg-violet-500/30 text-violet-300 ring-1 ring-violet-500/50" : ""}
        ${status === "active" ? "bg-violet-500/20 text-violet-300 ring-2 ring-violet-400 animate-glow" : ""}
        ${status === "pending" ? "bg-white/5 text-white/20" : ""}
      `}>
        {status === "done" ? (
          <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor" className="w-4 h-4 text-violet-400">
            <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 12.75l6 6 9-13.5" />
          </svg>
        ) : (
          <StepIcon icon={step.icon} />
        )}
      </div>
      <span className={`text-[10px] font-medium text-center leading-tight transition-colors
        ${status === "done" ? "text-violet-300" : ""}
        ${status === "active" ? "text-white" : ""}
        ${status === "pending" ? "text-white/25" : ""}
      `}>{step.label}</span>
    </div>
  )
}

function PipelineConnector({ done }) {
  return (
    <div className={`h-0.5 w-6 flex-shrink-0 mt-[-18px] transition-all duration-700
      ${done ? "bg-violet-500/60" : "bg-white/10"}
    `} />
  )
}

function MetricPill({ label, value }) {
  if (value == null) return null
  return (
    <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-white/5 border border-white/10 text-xs font-mono animate-fade-in">
      <span className="text-violet-400 font-semibold">{value}</span>
      <span className="text-white/40">{label}</span>
    </div>
  )
}

function TranscriptPanel({ segments }) {
  if (!segments || segments.length === 0) return null
  const speakers = [...new Set(segments.map(s => s.speaker))]
  const colorMap = {}
  speakers.forEach((s, i) => { colorMap[s] = SPEAKER_COLORS[i % SPEAKER_COLORS.length] })

  return (
    <div className="bg-white/[0.03] rounded-xl border border-white/10 p-4 max-h-64 overflow-y-auto">
      <div className="text-xs font-semibold text-white/30 uppercase tracking-wider mb-3">Transcript</div>
      <div className="space-y-2.5">
        {segments.map((seg, i) => (
          <div key={i} className="animate-fade-in" style={{ animationDelay: `${i * 50}ms` }}>
            <div className="flex items-center gap-2 mb-0.5">
              <div className="w-2 h-2 rounded-full flex-shrink-0" style={{ backgroundColor: colorMap[seg.speaker] }} />
              <span className="text-[10px] font-mono text-white/30" style={{ color: colorMap[seg.speaker] }}>{seg.speaker}</span>
              <span className="text-[10px] text-white/20">{formatTime(seg.start)} - {formatTime(seg.end)}</span>
            </div>
            {seg.text && <p className="text-xs text-white/60 ml-4">{seg.text}</p>}
            {seg.translated_text && <p className="text-xs text-violet-300/70 ml-4">→ {seg.translated_text}</p>}
          </div>
        ))}
      </div>
    </div>
  )
}

function formatTime(seconds) {
  const m = Math.floor(seconds / 60)
  const s = Math.floor(seconds % 60)
  return `${m}:${String(s).padStart(2, "0")}`
}

function SyncedPlayer({ originalUrl, dubbedUrl, language }) {
  const origRef = useRef(null)
  const dubRef = useRef(null)
  const [isPlaying, setIsPlaying] = useState(false)
  const [currentTime, setCurrentTime] = useState(0)
  const [duration, setDuration] = useState(0)

  const syncPlay = () => {
    origRef.current?.play()
    dubRef.current?.play()
    setIsPlaying(true)
  }

  const syncPause = () => {
    origRef.current?.pause()
    dubRef.current?.pause()
    setIsPlaying(false)
  }

  const handleTimeUpdate = useCallback(() => {
    const t = origRef.current?.currentTime || 0
    setCurrentTime(t)
    if (dubRef.current && Math.abs(dubRef.current.currentTime - t) > 0.3) {
      dubRef.current.currentTime = t
    }
  }, [])

  const handleScrub = (e) => {
    const t = parseFloat(e.target.value)
    if (origRef.current) origRef.current.currentTime = t
    if (dubRef.current) dubRef.current.currentTime = t
    setCurrentTime(t)
  }

  const langLabel = LANGUAGES.find(l => l.code === language)?.label || language

  return (
    <div className="space-y-4 animate-slide-up">
      <div className="grid grid-cols-2 gap-3">
        <div className="relative rounded-xl overflow-hidden bg-black border border-white/10">
          <div className="absolute top-3 left-3 z-10 px-2.5 py-1 rounded-md bg-black/60 backdrop-blur-sm text-xs font-medium text-white/70">Original</div>
          <video ref={origRef} src={originalUrl} muted onTimeUpdate={handleTimeUpdate} onLoadedMetadata={() => setDuration(origRef.current?.duration || 0)} className="w-full" />
        </div>
        <div className="relative rounded-xl overflow-hidden bg-black border border-white/10">
          <div className="absolute top-3 left-3 z-10 px-2.5 py-1 rounded-md bg-violet-600/80 backdrop-blur-sm text-xs font-medium">Dubbed — {langLabel}</div>
          <video ref={dubRef} src={dubbedUrl} className="w-full" />
        </div>
      </div>
      <div className="flex items-center gap-4">
        <button onClick={isPlaying ? syncPause : syncPlay} className="w-10 h-10 rounded-full bg-violet-600 hover:bg-violet-500 flex items-center justify-center transition-colors flex-shrink-0">
          {isPlaying ? (
            <svg xmlns="http://www.w3.org/2000/svg" fill="currentColor" viewBox="0 0 24 24" className="w-4 h-4"><path d="M6 4h4v16H6zM14 4h4v16h-4z" /></svg>
          ) : (
            <svg xmlns="http://www.w3.org/2000/svg" fill="currentColor" viewBox="0 0 24 24" className="w-4 h-4 ml-0.5"><path d="M8 5v14l11-7z" /></svg>
          )}
        </button>
        <input type="range" min={0} max={duration || 1} step={0.1} value={currentTime} onChange={handleScrub} className="flex-1 h-1 accent-violet-500" />
        <span className="text-xs font-mono text-white/30 flex-shrink-0">{formatTime(currentTime)} / {formatTime(duration)}</span>
      </div>
    </div>
  )
}

export default function App() {
  const [file, setFile] = useState(null)
  const [language, setLanguage] = useState("es")
  const [jobId, setJobId] = useState(null)
  const [status, setStatus] = useState(null)
  const [originalUrl, setOriginalUrl] = useState(null)
  const [dubbedUrl, setDubbedUrl] = useState(null)
  const [isDragging, setIsDragging] = useState(false)
  const [isUploading, setIsUploading] = useState(false)
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
    setIsUploading(true)
    const form = new FormData()
    form.append("file", file)
    form.append("target_language", language)

    const res = await fetch(`${API_BASE}/dub`, { method: "POST", body: form })
    const data = await res.json()
    setIsUploading(false)
    setJobId(data.job_id)
    setStatus({ status: "queued", step: "Queued", progress: 0 })
    pollRef.current = setInterval(() => pollStatus(data.job_id), 1500)
  }

  const pollStatus = async (id) => {
    try {
      const res = await fetch(`${API_BASE}/status/${id}`)
      const data = await res.json()
      setStatus(data)

      if (data.status === "done") {
        clearInterval(pollRef.current)
        setDubbedUrl(`${API_BASE}/download/${id}`)
      }
      if (data.status === "error") {
        clearInterval(pollRef.current)
      }
    } catch {
      // network error — keep polling
    }
  }

  useEffect(() => {
    return () => { if (pollRef.current) clearInterval(pollRef.current) }
  }, [])

  const isRunning = status?.status === "running" || status?.status === "queued"
  const isDone = status?.status === "done"
  const isError = status?.status === "error"

  const reset = () => {
    setJobId(null)
    setStatus(null)
    setFile(null)
    setOriginalUrl(null)
    setDubbedUrl(null)
  }

  return (
    <div className="min-h-screen bg-[#0a0a0f] text-white font-sans">
      {/* Header */}
      <header className="border-b border-white/10 px-8 py-5 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-violet-500 to-fuchsia-500 flex items-center justify-center text-sm font-bold">S</div>
          <span className="text-xl font-semibold tracking-tight">Syncr</span>
          <span className="text-xs text-white/30 font-mono ml-1">AI Dubbing Studio</span>
        </div>
        <a href="https://github.com" className="text-sm text-white/40 hover:text-white/70 transition-colors">GitHub</a>
      </header>

      <main className="max-w-5xl mx-auto px-6 py-16">
        {/* Hero */}
        <div className="text-center mb-14">
          <h1 className="text-5xl font-bold tracking-tight mb-4 bg-gradient-to-r from-white to-white/50 bg-clip-text text-transparent">
            Any voice. Any language.
          </h1>
          <p className="text-white/50 text-lg max-w-xl mx-auto">
            Upload a video and every actor speaks your target language — in their own voice — powered by intelligent multi-container orchestration.
          </p>
        </div>

        {/* Upload + Config */}
        {!jobId && (
          <div className="space-y-5 max-w-3xl mx-auto">
            {/* Drop zone */}
            <div
              onDragOver={(e) => { e.preventDefault(); setIsDragging(true) }}
              onDragLeave={() => setIsDragging(false)}
              onDrop={handleDrop}
              onClick={() => fileInputRef.current?.click()}
              className={`relative border-2 border-dashed rounded-2xl p-12 text-center cursor-pointer transition-all duration-300
                ${isDragging ? "border-violet-400 bg-violet-500/10 scale-[1.02]" : "border-white/10 hover:border-white/25 hover:bg-white/[0.02]"}
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
                  <p className="text-sm text-white/40 mt-1">MP4, MOV, AVI — clips to full movies</p>
                </div>
              )}
            </div>

            {/* Language selector */}
            <div className="flex gap-2.5 flex-wrap justify-center">
              {LANGUAGES.map((lang) => (
                <button
                  key={lang.code}
                  onClick={() => setLanguage(lang.code)}
                  className={`px-4 py-2 rounded-full text-sm font-medium transition-all duration-200
                    ${language === lang.code
                      ? "bg-violet-500 text-white scale-105 shadow-lg shadow-violet-500/25"
                      : "bg-white/5 text-white/50 hover:bg-white/10 hover:text-white hover:scale-105"
                    }`}
                >
                  {lang.label}
                </button>
              ))}
            </div>

            {/* Start button */}
            <button
              onClick={startJob}
              disabled={!file || isUploading}
              className="w-full py-4 rounded-xl font-semibold text-lg
                bg-gradient-to-r from-violet-600 to-fuchsia-600
                hover:from-violet-500 hover:to-fuchsia-500
                disabled:opacity-30 disabled:cursor-not-allowed
                transition-all duration-200"
            >
              {isUploading ? "Uploading..." : "Dub this video →"}
            </button>
          </div>
        )}

        {/* Pipeline Dashboard */}
        {isRunning && (
          <div className="space-y-6 animate-fade-in">
            {/* Current step + progress */}
            <div className="bg-white/5 rounded-2xl p-6 border border-white/10">
              <div className="flex items-center justify-between mb-4">
                <span className="font-semibold">{status?.step}</span>
                <span className="text-white/40 font-mono text-sm">{status?.progress}%</span>
              </div>
              <div className="w-full bg-white/10 rounded-full h-1.5 mb-6">
                <div
                  className="bg-gradient-to-r from-violet-500 to-fuchsia-500 h-1.5 rounded-full transition-all duration-700"
                  style={{ width: `${status?.progress}%` }}
                />
              </div>

              {/* Pipeline step nodes */}
              <div className="flex items-start justify-center gap-0 overflow-x-auto pb-2">
                {PIPELINE_STEPS.map((step, i) => {
                  const stepStatus = getStepStatus(step, status?.step, status?.progress || 0)
                  return (
                    <div key={step.key} className="flex items-start">
                      {i > 0 && <PipelineConnector done={stepStatus === "done" || stepStatus === "active"} />}
                      <PipelineNode step={step} status={stepStatus} />
                    </div>
                  )
                })}
              </div>
            </div>

            {/* Metrics */}
            <div className="flex flex-wrap gap-2.5 justify-center">
              <MetricPill label="chunks" value={status?.total_chunks && `${status?.completed_chunks || 0}/${status?.total_chunks}`} />
              <MetricPill label="speakers" value={status?.speakers_found} />
              <MetricPill label="segments" value={status?.segments_found} />
              <MetricPill label="containers" value={status?.containers_total} />
            </div>

            {/* Transcript preview */}
            <TranscriptPanel segments={status?.transcript_preview} />
          </div>
        )}

        {/* Error */}
        {isError && (
          <div className="bg-red-500/10 border border-red-500/30 rounded-2xl p-6 animate-shake max-w-3xl mx-auto">
            <p className="text-red-400 font-medium">Pipeline failed</p>
            <p className="text-red-400/70 text-sm mt-1">{status?.error}</p>
            <button onClick={reset} className="mt-4 text-sm text-white/50 hover:text-white">
              ← Try again
            </button>
          </div>
        )}

        {/* Result — synced player */}
        {isDone && originalUrl && dubbedUrl && (
          <div className="space-y-6 animate-slide-up">
            <div className="flex items-center justify-between">
              <h2 className="text-xl font-semibold">Your dubbed video is ready</h2>
              <a
                href={dubbedUrl}
                download="syncr_dubbed.mp4"
                className="px-5 py-2 rounded-lg bg-violet-600 hover:bg-violet-500 text-sm font-medium transition-colors"
              >
                Download
              </a>
            </div>

            <SyncedPlayer originalUrl={originalUrl} dubbedUrl={dubbedUrl} language={language} />

            {/* Final transcript */}
            <TranscriptPanel segments={status?.transcript_preview} />

            <button onClick={reset} className="text-sm text-white/30 hover:text-white/60 transition-colors">
              ← Dub another video
            </button>
          </div>
        )}
      </main>
    </div>
  )
}
