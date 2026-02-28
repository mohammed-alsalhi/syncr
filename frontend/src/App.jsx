import { useState, useRef, useEffect, useCallback, useMemo } from "react"

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000"

const LANGUAGES = [
  { code: "es", label: "Spanish", flag: "🇪🇸" },
  { code: "fr", label: "French", flag: "🇫🇷" },
  { code: "de", label: "German", flag: "🇩🇪" },
  { code: "ar", label: "Arabic", flag: "🇸🇦" },
  { code: "zh", label: "Mandarin", flag: "🇨🇳" },
  { code: "ja", label: "Japanese", flag: "🇯🇵" },
  { code: "pt", label: "Portuguese", flag: "🇧🇷" },
  { code: "hi", label: "Hindi", flag: "🇮🇳" },
  { code: "ko", label: "Korean", flag: "🇰🇷" },
  { code: "it", label: "Italian", flag: "🇮🇹" },
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

// ─── Background Effects ────────────────────────────────────────────

function AuroraBackground() {
  return (
    <div className="fixed inset-0 overflow-hidden pointer-events-none z-0">
      <div className="absolute -top-1/2 -left-1/4 w-[800px] h-[800px] bg-violet-600/[0.15] rounded-full blur-[150px] animate-aurora-1" />
      <div className="absolute -bottom-1/3 -right-1/4 w-[700px] h-[700px] bg-fuchsia-600/[0.12] rounded-full blur-[140px] animate-aurora-2" />
      <div className="absolute top-1/4 left-1/3 w-[600px] h-[600px] bg-cyan-600/[0.08] rounded-full blur-[130px] animate-aurora-3" />
    </div>
  )
}

function FloatingParticles() {
  const particles = useMemo(() =>
    Array.from({ length: 30 }, (_, i) => ({
      id: i,
      left: Math.random() * 100,
      delay: Math.random() * 25,
      duration: 18 + Math.random() * 22,
      size: 1 + Math.random() * 2.5,
      opacity: 0.15 + Math.random() * 0.35,
    })), [])

  return (
    <div className="fixed inset-0 pointer-events-none z-[1] overflow-hidden">
      {particles.map(p => (
        <div
          key={p.id}
          className="absolute rounded-full bg-violet-400"
          style={{
            left: `${p.left}%`,
            bottom: '-10px',
            width: `${p.size}px`,
            height: `${p.size}px`,
            opacity: p.opacity,
            animation: `float ${p.duration}s linear ${p.delay}s infinite`,
          }}
        />
      ))}
    </div>
  )
}

function MouseGlow() {
  const [pos, setPos] = useState({ x: -500, y: -500 })

  useEffect(() => {
    const handler = (e) => setPos({ x: e.clientX, y: e.clientY })
    window.addEventListener('mousemove', handler)
    return () => window.removeEventListener('mousemove', handler)
  }, [])

  return (
    <div
      className="fixed w-[600px] h-[600px] rounded-full pointer-events-none z-[2]"
      style={{
        background: 'radial-gradient(circle, rgba(139, 92, 246, 0.07) 0%, rgba(217, 70, 239, 0.03) 40%, transparent 70%)',
        transform: `translate(${pos.x - 300}px, ${pos.y - 300}px)`,
        transition: 'transform 0.15s ease-out',
      }}
    />
  )
}

function GridOverlay() {
  return (
    <div
      className="fixed inset-0 pointer-events-none z-[1] opacity-[0.03]"
      style={{
        backgroundImage: `
          linear-gradient(rgba(139, 92, 246, 0.5) 1px, transparent 1px),
          linear-gradient(90deg, rgba(139, 92, 246, 0.5) 1px, transparent 1px)
        `,
        backgroundSize: '60px 60px',
      }}
    />
  )
}

// ─── Animated Border Wrapper ───────────────────────────────────────

function AnimatedBorder({ children, innerClass = "", className = "" }) {
  return (
    <div className={`animated-border ${className}`}>
      <div className={`card-inner ${innerClass}`}>
        {children}
      </div>
    </div>
  )
}

// ─── Helpers ───────────────────────────────────────────────────────

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

function formatTime(seconds) {
  const m = Math.floor(seconds / 60)
  const s = Math.floor(seconds % 60)
  return `${m}:${String(s).padStart(2, "0")}`
}

// ─── Icons ─────────────────────────────────────────────────────────

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

// ─── Pipeline Components ───────────────────────────────────────────

function PipelineNode({ step, status, index }) {
  return (
    <div
      className={`flex flex-col items-center gap-1.5 px-2 min-w-[72px] transition-all duration-500
        ${status === "active" ? "scale-110" : ""}
      `}
      style={{
        animation: 'stagger-in 0.5s ease-out backwards',
        animationDelay: `${index * 80}ms`,
      }}
    >
      <div className="relative">
        {/* Pulse ring for active step */}
        {status === "active" && (
          <div className="absolute inset-0 rounded-xl bg-violet-500/30 animate-pulse-ring" />
        )}
        <div className={`relative w-11 h-11 rounded-xl flex items-center justify-center transition-all duration-500
          ${status === "done" ? "bg-violet-500/30 text-violet-300 ring-1 ring-violet-500/50 shadow-lg shadow-violet-500/20" : ""}
          ${status === "active" ? "bg-violet-500/20 text-violet-200 ring-2 ring-violet-400 animate-glow" : ""}
          ${status === "pending" ? "bg-white/[0.03] text-white/15" : ""}
        `}>
          {status === "done" ? (
            <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={2.5} stroke="currentColor" className="w-4 h-4 text-violet-400">
              <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 12.75l6 6 9-13.5" />
            </svg>
          ) : (
            <StepIcon icon={step.icon} />
          )}
        </div>
      </div>
      <span className={`text-[10px] font-semibold text-center leading-tight transition-colors tracking-wide uppercase
        ${status === "done" ? "text-violet-400" : ""}
        ${status === "active" ? "text-white" : ""}
        ${status === "pending" ? "text-white/20" : ""}
      `}>{step.label}</span>
    </div>
  )
}

function PipelineConnector({ done, active }) {
  return (
    <div className="relative h-0.5 w-8 flex-shrink-0 mt-[-18px] overflow-hidden rounded-full">
      <div className={`absolute inset-0 transition-all duration-700 ${done || active ? 'bg-violet-500/50' : 'bg-white/[0.06]'}`} />
      {active && (
        <div
          className="absolute inset-0 w-1/3 bg-gradient-to-r from-transparent via-white/70 to-transparent rounded-full"
          style={{ animation: 'beam 1.2s ease-in-out infinite' }}
        />
      )}
    </div>
  )
}

function MetricPill({ label, value }) {
  if (value == null) return null
  return (
    <div className="flex items-center gap-2 px-4 py-2 rounded-full bg-white/[0.04] border border-white/[0.08] text-xs font-mono animate-fade-in animate-metric-glow backdrop-blur-sm">
      <span className="text-violet-400 font-bold">{value}</span>
      <span className="text-white/35">{label}</span>
    </div>
  )
}

function TranscriptPanel({ segments }) {
  if (!segments || segments.length === 0) return null
  const speakers = [...new Set(segments.map(s => s.speaker))]
  const colorMap = {}
  speakers.forEach((s, i) => { colorMap[s] = SPEAKER_COLORS[i % SPEAKER_COLORS.length] })

  return (
    <AnimatedBorder innerClass="p-5 max-h-64 overflow-y-auto">
      <div className="text-[10px] font-bold text-white/25 uppercase tracking-[0.2em] mb-3">Transcript</div>
      <div className="space-y-3">
        {segments.map((seg, i) => (
          <div
            key={i}
            style={{
              animation: 'stagger-in 0.4s ease-out backwards',
              animationDelay: `${i * 60}ms`,
            }}
          >
            <div className="flex items-center gap-2 mb-0.5">
              <div className="w-2 h-2 rounded-full flex-shrink-0 shadow-lg" style={{ backgroundColor: colorMap[seg.speaker], boxShadow: `0 0 8px ${colorMap[seg.speaker]}40` }} />
              <span className="text-[10px] font-mono font-semibold" style={{ color: colorMap[seg.speaker] }}>{seg.speaker}</span>
              <span className="text-[10px] text-white/15 font-mono">{formatTime(seg.start)} — {formatTime(seg.end)}</span>
            </div>
            {seg.text && <p className="text-xs text-white/50 ml-4 leading-relaxed">{seg.text}</p>}
            {seg.translated_text && <p className="text-xs text-violet-300/60 ml-4 leading-relaxed">→ {seg.translated_text}</p>}
          </div>
        ))}
      </div>
    </AnimatedBorder>
  )
}

// ─── Synced Player ─────────────────────────────────────────────────

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
      <div className="grid grid-cols-2 gap-4">
        <AnimatedBorder innerClass="overflow-hidden">
          <div className="relative">
            <div className="absolute top-3 left-3 z-10 px-3 py-1 rounded-lg bg-black/60 backdrop-blur-md text-[11px] font-semibold text-white/70 border border-white/10">Original</div>
            <video ref={origRef} src={originalUrl} muted onTimeUpdate={handleTimeUpdate} onLoadedMetadata={() => setDuration(origRef.current?.duration || 0)} className="w-full" />
          </div>
        </AnimatedBorder>
        <AnimatedBorder innerClass="overflow-hidden">
          <div className="relative">
            <div className="absolute top-3 left-3 z-10 px-3 py-1 rounded-lg bg-gradient-to-r from-violet-600/80 to-fuchsia-600/80 backdrop-blur-md text-[11px] font-semibold border border-violet-400/20">
              Dubbed — {langLabel}
            </div>
            <video ref={dubRef} src={dubbedUrl} className="w-full" />
          </div>
        </AnimatedBorder>
      </div>
      <div className="flex items-center gap-4">
        <button
          onClick={isPlaying ? syncPause : syncPlay}
          className="w-11 h-11 rounded-full bg-gradient-to-br from-violet-600 to-fuchsia-600 hover:from-violet-500 hover:to-fuchsia-500 flex items-center justify-center transition-all flex-shrink-0 shadow-lg shadow-violet-600/30 hover:shadow-violet-500/50 hover:scale-105 active:scale-95"
        >
          {isPlaying ? (
            <svg xmlns="http://www.w3.org/2000/svg" fill="currentColor" viewBox="0 0 24 24" className="w-4 h-4"><path d="M6 4h4v16H6zM14 4h4v16h-4z" /></svg>
          ) : (
            <svg xmlns="http://www.w3.org/2000/svg" fill="currentColor" viewBox="0 0 24 24" className="w-4 h-4 ml-0.5"><path d="M8 5v14l11-7z" /></svg>
          )}
        </button>
        <input type="range" min={0} max={duration || 1} step={0.1} value={currentTime} onChange={handleScrub} className="flex-1 h-1" />
        <span className="text-xs font-mono text-white/25 flex-shrink-0">{formatTime(currentTime)} / {formatTime(duration)}</span>
      </div>
    </div>
  )
}

// ─── Main App ──────────────────────────────────────────────────────

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
    <div className="min-h-screen bg-[#050508] text-white font-sans relative scanline-overlay">
      {/* Background layers */}
      <AuroraBackground />
      <FloatingParticles />
      <MouseGlow />
      <GridOverlay />

      {/* Content */}
      <div className="relative z-10">
        {/* Header */}
        <header className="sticky top-0 z-50 border-b border-white/[0.06] px-8 py-4 flex items-center justify-between backdrop-blur-2xl bg-[#050508]/70">
          <div className="flex items-center gap-3">
            <div
              className="w-9 h-9 bg-gradient-to-br from-violet-500 via-fuchsia-500 to-cyan-400 flex items-center justify-center text-sm font-black animate-logo-morph shadow-lg shadow-violet-500/30"
            >
              S
            </div>
            <span className="text-xl font-bold tracking-tight">Syncr</span>
            <span className="text-[10px] text-white/20 font-mono ml-1 tracking-wider uppercase">AI Dubbing Studio</span>
          </div>
          <a href="https://github.com" className="text-xs text-white/30 hover:text-white/60 transition-colors font-mono tracking-wide">GitHub</a>
        </header>

        <main className="max-w-5xl mx-auto px-6 py-20">
          {/* Hero */}
          <div
            className="text-center mb-16"
            style={{ animation: 'fadeIn 0.8s ease-out, hero-glitch 10s linear 3s infinite' }}
          >
            <h1
              className="text-6xl font-black tracking-tight mb-5 leading-[1.1]"
              style={{
                background: 'linear-gradient(90deg, #fff 0%, #c4b5fd 20%, #d946ef 40%, #06b6d4 60%, #c4b5fd 80%, #fff 100%)',
                backgroundSize: '200% auto',
                WebkitBackgroundClip: 'text',
                WebkitTextFillColor: 'transparent',
                backgroundClip: 'text',
                animation: 'text-shine 6s ease-in-out infinite',
              }}
            >
              Any voice. Any language.
            </h1>
            <p className="text-white/40 text-lg max-w-2xl mx-auto leading-relaxed">
              Upload a video and every actor speaks your target language — in their own cloned voice — powered by
              <span className="text-violet-400/60"> intelligent multi-container GPU orchestration</span>.
            </p>
          </div>

          {/* Upload + Config */}
          {!jobId && (
            <div className="space-y-6 max-w-3xl mx-auto animate-fade-in">
              {/* Drop zone */}
              <div
                onDragOver={(e) => { e.preventDefault(); setIsDragging(true) }}
                onDragLeave={() => setIsDragging(false)}
                onDrop={handleDrop}
                onClick={() => fileInputRef.current?.click()}
                className={`relative rounded-2xl p-14 text-center cursor-pointer transition-all duration-500 border overflow-hidden group
                  ${isDragging
                    ? "border-violet-400/60 bg-violet-500/[0.12] scale-[1.02] shadow-[0_0_80px_rgba(139,92,246,0.25)]"
                    : file
                      ? "border-violet-500/30 bg-violet-500/[0.04]"
                      : "border-white/[0.08] hover:border-violet-500/30 hover:bg-white/[0.02]"
                  }
                `}
                style={file && !isDragging ? { animation: 'drop-glow 3s ease-in-out infinite' } : {}}
              >
                <input ref={fileInputRef} type="file" accept="video/*" className="hidden" onChange={(e) => handleFile(e.target.files[0])} />

                {/* Ambient glow inside drop zone */}
                <div className={`absolute inset-0 transition-opacity duration-500 ${isDragging ? 'opacity-100' : 'opacity-0'}`}>
                  <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-64 h-64 bg-violet-500/20 rounded-full blur-[80px]" />
                </div>

                <div className="relative z-10">
                  {file ? (
                    <div>
                      <div className="text-5xl mb-4">🎬</div>
                      <p className="font-semibold text-lg">{file.name}</p>
                      <p className="text-sm text-white/30 mt-1.5 font-mono">{(file.size / 1e6).toFixed(1)} MB — click to change</p>
                    </div>
                  ) : (
                    <div>
                      <div className={`text-5xl mb-4 inline-block ${isDragging ? 'animate-upload-pulse' : 'group-hover:animate-upload-pulse'}`}>⬆️</div>
                      <p className="font-semibold text-lg">Drop a video file here</p>
                      <p className="text-sm text-white/25 mt-1.5">MP4, MOV, AVI — clips to full movies</p>
                    </div>
                  )}
                </div>
              </div>

              {/* Language selector */}
              <div className="flex gap-2.5 flex-wrap justify-center">
                {LANGUAGES.map((lang, i) => (
                  <button
                    key={lang.code}
                    onClick={() => setLanguage(lang.code)}
                    className={`px-4 py-2 rounded-full text-sm font-medium transition-all duration-300
                      ${language === lang.code
                        ? "bg-gradient-to-r from-violet-600 to-fuchsia-600 text-white scale-105 shadow-lg shadow-violet-500/30 ring-1 ring-violet-400/30"
                        : "bg-white/[0.04] text-white/40 hover:bg-white/[0.08] hover:text-white/70 hover:scale-105 border border-white/[0.06] hover:border-violet-500/20"
                      }`}
                    style={{
                      animation: 'stagger-in 0.4s ease-out backwards',
                      animationDelay: `${i * 40}ms`,
                    }}
                  >
                    <span className="mr-1.5">{lang.flag}</span>
                    {lang.label}
                  </button>
                ))}
              </div>

              {/* Start button */}
              <button
                onClick={startJob}
                disabled={!file || isUploading}
                className="btn-shimmer w-full py-4 rounded-xl font-bold text-lg
                  bg-gradient-to-r from-violet-600 via-fuchsia-600 to-violet-600 bg-[length:200%_100%]
                  hover:shadow-[0_0_40px_rgba(139,92,246,0.3)] hover:scale-[1.015] active:scale-[0.985]
                  disabled:opacity-20 disabled:cursor-not-allowed disabled:hover:scale-100 disabled:hover:shadow-none
                  transition-all duration-300 shadow-lg shadow-violet-600/20"
              >
                {isUploading ? (
                  <span className="flex items-center justify-center gap-3">
                    <svg className="animate-spin h-5 w-5" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" /><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" /></svg>
                    Uploading...
                  </span>
                ) : (
                  "Dub this video →"
                )}
              </button>
            </div>
          )}

          {/* Pipeline Dashboard */}
          {isRunning && (
            <div className="space-y-6 animate-slide-up">
              {/* Current step + progress */}
              <AnimatedBorder innerClass="p-6">
                <div className="flex items-center justify-between mb-4">
                  <div className="flex items-center gap-3">
                    <div className="w-2 h-2 rounded-full bg-violet-400 animate-pulse shadow-lg shadow-violet-400/50" />
                    <span className="font-semibold text-sm">{status?.step}</span>
                  </div>
                  <span className="text-white/30 font-mono text-sm font-bold">{status?.progress}%</span>
                </div>

                {/* Progress bar */}
                <div className="w-full bg-white/[0.06] rounded-full h-2 mb-8 overflow-hidden">
                  <div
                    className="progress-bar bg-gradient-to-r from-violet-500 via-fuchsia-500 to-cyan-400 h-2 rounded-full transition-all duration-700 ease-out"
                    style={{ width: `${status?.progress}%` }}
                  />
                </div>

                {/* Pipeline step nodes */}
                <div className="flex items-start justify-center gap-0 overflow-x-auto pb-2">
                  {PIPELINE_STEPS.map((step, i) => {
                    const stepStatus = getStepStatus(step, status?.step, status?.progress || 0)
                    const nextStatus = i < PIPELINE_STEPS.length - 1
                      ? getStepStatus(PIPELINE_STEPS[i + 1], status?.step, status?.progress || 0)
                      : "pending"
                    return (
                      <div key={step.key} className="flex items-start">
                        {i > 0 && (
                          <PipelineConnector
                            done={stepStatus === "done" || stepStatus === "active"}
                            active={stepStatus === "active"}
                          />
                        )}
                        <PipelineNode step={step} status={stepStatus} index={i} />
                      </div>
                    )
                  })}
                </div>
              </AnimatedBorder>

              {/* Metrics */}
              <div className="flex flex-wrap gap-3 justify-center">
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
            <div className="animate-shake max-w-3xl mx-auto">
              <AnimatedBorder innerClass="p-6">
                <div className="flex items-start gap-3">
                  <div className="w-10 h-10 rounded-xl bg-red-500/20 flex items-center justify-center flex-shrink-0">
                    <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor" className="w-5 h-5 text-red-400">
                      <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m9-.75a9 9 0 11-18 0 9 9 0 0118 0zm-9 3.75h.008v.008H12v-.008z" />
                    </svg>
                  </div>
                  <div>
                    <p className="text-red-400 font-semibold">Pipeline failed</p>
                    <p className="text-red-400/50 text-sm mt-1 font-mono">{status?.error}</p>
                  </div>
                </div>
                <button onClick={reset} className="mt-5 text-sm text-white/30 hover:text-white/60 transition-colors font-medium">
                  ← Try again
                </button>
              </AnimatedBorder>
            </div>
          )}

          {/* Result — synced player */}
          {isDone && originalUrl && dubbedUrl && (
            <div className="space-y-6 animate-slide-up">
              <div className="flex items-center justify-between">
                <h2 className="text-2xl font-bold">
                  <span
                    style={{
                      background: 'linear-gradient(90deg, #fff, #c4b5fd, #d946ef)',
                      WebkitBackgroundClip: 'text',
                      WebkitTextFillColor: 'transparent',
                      backgroundClip: 'text',
                    }}
                  >
                    Your dubbed video is ready
                  </span>
                </h2>
                <a
                  href={dubbedUrl}
                  download="syncr_dubbed.mp4"
                  className="btn-shimmer px-6 py-2.5 rounded-xl bg-gradient-to-r from-violet-600 to-fuchsia-600 hover:from-violet-500 hover:to-fuchsia-500 text-sm font-semibold transition-all shadow-lg shadow-violet-600/20 hover:shadow-violet-500/40 hover:scale-105 active:scale-95"
                >
                  Download ↓
                </a>
              </div>

              <SyncedPlayer originalUrl={originalUrl} dubbedUrl={dubbedUrl} language={language} />

              {/* Final transcript */}
              <TranscriptPanel segments={status?.transcript_preview} />

              <button onClick={reset} className="text-sm text-white/25 hover:text-white/50 transition-all font-medium hover:translate-x-[-4px]">
                ← Dub another video
              </button>
            </div>
          )}
        </main>
      </div>
    </div>
  )
}
