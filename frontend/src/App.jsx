import { useState, useRef, useEffect, useCallback, useMemo } from "react"
import ES from "country-flag-icons/react/3x2/ES"
import FR from "country-flag-icons/react/3x2/FR"
import DE from "country-flag-icons/react/3x2/DE"
import SA from "country-flag-icons/react/3x2/SA"
import CN from "country-flag-icons/react/3x2/CN"
import JP from "country-flag-icons/react/3x2/JP"
import BR from "country-flag-icons/react/3x2/BR"
import IN from "country-flag-icons/react/3x2/IN"
import KR from "country-flag-icons/react/3x2/KR"
import IT from "country-flag-icons/react/3x2/IT"

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000"
const GREEN = "#62DE61"

const LANGUAGES = [
  { code: "es", label: "Spanish",    Flag: ES },
  { code: "fr", label: "French",     Flag: FR },
  { code: "de", label: "German",     Flag: DE },
  { code: "ar", label: "Arabic",     Flag: SA },
  { code: "zh", label: "Mandarin",   Flag: CN },
  { code: "ja", label: "Japanese",   Flag: JP },
  { code: "pt", label: "Portuguese", Flag: BR },
  { code: "hi", label: "Hindi",      Flag: IN },
  { code: "ko", label: "Korean",     Flag: KR },
  { code: "it", label: "Italian",    Flag: IT },
]

const PIPELINE_STEPS = [
  { key: "chunking",     label: "Chunk",      icon: "scissors" },
  { key: "diarizing",   label: "Diarize",    icon: "users"    },
  { key: "transcribing",label: "Transcribe", icon: "mic"      },
  { key: "translating", label: "Translate",  icon: "globe"    },
  { key: "synthesizing",label: "Synthesize", icon: "waveform" },
  { key: "quality",     label: "Quality",    icon: "check"    },
  { key: "compositing", label: "Composite",  icon: "film"     },
]

const SPEAKER_COLORS = [GREEN, "#60a5fa", "#f472b6", "#fb923c", "#a78bfa", "#34d399", "#fbbf24"]

/* ── Boot Sequence ── */
const BOOT_LINES = [
  "SYNCR AI DUBBING STUDIO  ·  v2.6.0",
  "",
  ">  NEURAL CORE ................................ INIT",
  ">  GPU CLUSTER (×40 containers) ............... ONLINE",
  ">  SELF-HOSTED WHISPER TRANSCRIBER ............ READY",
  ">  ELEVENLABS VOICE SYNTHESIS ................. ACTIVE",
  ">  GPT-4o LANGUAGE MODELS .................... LOADED",
  ">  MODAL ORCHESTRATION LAYER .................. UP",
  "",
  "   ✓  ALL SYSTEMS OPERATIONAL",
]

function BootSequence() {
  const [lines, setLines] = useState([])
  const [phase, setPhase] = useState("booting")

  useEffect(() => {
    let i = 0
    const iv = setInterval(() => {
      if (i < BOOT_LINES.length) {
        setLines(prev => [...prev, BOOT_LINES[i]])
        i++
      } else {
        clearInterval(iv)
        setTimeout(() => setPhase("fading"), 700)
        setTimeout(() => setPhase("done"),   1500)
      }
    }, 130)
    return () => clearInterval(iv)
  }, [])

  if (phase === "done") return null

  return (
    <div
      className="fixed inset-0 z-[500] flex items-center justify-center bg-black"
      style={{ opacity: phase === "fading" ? 0 : 1, transition: "opacity 0.8s ease-out", pointerEvents: phase === "fading" ? "none" : "all" }}
    >
      <div
        className="font-mono text-sm max-w-xl w-full px-4 py-6 sm:px-10 sm:py-8 rounded-xl"
        style={{ background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.08)" }}
      >
        <div className="text-white/25 text-[10px] mb-5 tracking-[0.4em] uppercase">System Init</div>
        {lines.map((line, i) => (
          <div
            key={i}
            className={line === "" ? "h-3" : "mb-[3px] leading-snug"}
            style={{
              color:      line.startsWith("   ✓") ? GREEN
                        : line.startsWith("SYNCR") ? "rgba(255,255,255,0.85)"
                        : "rgba(255,255,255,0.4)",
              fontWeight: line.startsWith("   ✓") || line.startsWith("SYNCR") ? "600" : "400",
              animation:  "fadeIn 0.15s ease-out",
            }}
          >{line}</div>
        ))}
        {phase === "booting" && <span style={{ color: GREEN, opacity: 0.5, animation: "blink-cursor 1s step-end infinite" }}>▌</span>}
      </div>
    </div>
  )
}

/* ── Typewriter ── */
function TypewriterText({ text }) {
  const [shown, setShown] = useState("")
  const prev = useRef("")

  useEffect(() => {
    if (!text || text === prev.current) return
    prev.current = text
    setShown("")
    let i = 0
    const t = setInterval(() => { i++; setShown(text.slice(0, i)); if (i >= text.length) clearInterval(t) }, 22)
    return () => clearInterval(t)
  }, [text])

  return (
    <span className="font-mono text-sm text-white/70">
      {shown}
      <span className="text-white/30 ml-0.5" style={{ animation: "blink-cursor 1s step-end infinite" }}>▌</span>
    </span>
  )
}

/* ── Sonar Rings Background ── */
function SonarRings() {
  const rings = useMemo(() => [
    { delay: 0,   duration: 8  },
    { delay: 1.6, duration: 8  },
    { delay: 3.2, duration: 8  },
    { delay: 4.8, duration: 8  },
    { delay: 6.4, duration: 8  },
  ], [])

  return (
    <div className="fixed inset-0 z-[1] pointer-events-none overflow-hidden">
      <div className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2" style={{ width: "min(80vw, 80vh)", height: "min(80vw, 80vh)" }}>
        {rings.map((r, i) => (
          <div
            key={i}
            className="absolute inset-0 rounded-full"
            style={{
              border: `1px solid ${GREEN}`,
              opacity: 0,
              animation: `sonar-expand ${r.duration}s linear ${r.delay}s infinite backwards`,
            }}
          />
        ))}
      </div>
    </div>
  )
}

/* ── Waveform ── */
function WaveformBars({ active }) {
  const bars = useMemo(() =>
    Array.from({ length: 36 }, (_, i) => ({
      id: i,
      delay:    i * 35 + Math.floor(Math.random() * 80),
      duration: 380 + Math.floor(Math.random() * 500),
      base:     0.12 + (Math.sin(i * 0.5) * 0.5 + 0.5) * 0.65,
    })), [])

  return (
    <div className="flex items-end justify-center gap-[3px] h-9 px-2 overflow-hidden">
      {bars.map((b) => (
        <div
          key={b.id}
          className="w-[3px] rounded-full flex-shrink-0"
          style={{
            height: "100%",
            background: active ? GREEN : "rgba(255,255,255,0.06)",
            transformOrigin: "bottom",
            transform: active ? `scaleY(${b.base})` : "scaleY(0.1)",
            animation: active ? `wave-bar ${b.duration}ms ease-in-out ${b.delay}ms infinite alternate` : "none",
            transition: "transform 0.4s ease, background 0.4s ease",
            opacity: active ? 0.65 : 0.2,
          }}
        />
      ))}
    </div>
  )
}

/* ── Helpers ── */
function getStepStatus(step, currentStep, progress) {
  const kws = {
    chunking:     ["Analyzing","chunk","Chunking"],
    diarizing:    ["Diariz","speaker","Identifying"],
    transcribing: ["Transcrib","speech","Whisper"],
    translating:  ["Translat","dialogue"],
    synthesizing: ["Clon","voice","synth"],
    quality:      ["Quality","Verif","Re-process"],
    compositing:  ["Composit","Saving","merg","Done"],
  }
  const mine   = kws[step.key] || []
  const active = mine.some(k => currentStep?.toLowerCase().includes(k.toLowerCase()))
  const myIdx  = PIPELINE_STEPS.findIndex(s => s.key === step.key)
  const actIdx = PIPELINE_STEPS.findIndex(s => (kws[s.key] || []).some(k => currentStep?.toLowerCase().includes(k.toLowerCase())))
  if (progress >= 100) return "done"
  if (active)          return "active"
  if (actIdx >= 0 && myIdx < actIdx) return "done"
  return "pending"
}

function formatTime(s) {
  const m = Math.floor(s / 60)
  return `${m}:${String(Math.floor(s % 60)).padStart(2, "0")}`
}

/* ── Step Icons ── */
function StepIcon({ icon }) {
  const paths = {
    scissors: "M7.5 8.25l-2.5 2.5m0 0l-2.5-2.5M5 10.75v-8.5m7-1l2.5 2.5m0 0l2.5-2.5M14.5 3.75v8.5M3.5 16.5a2 2 0 104 0 2 2 0 00-4 0zm9 0a2 2 0 104 0 2 2 0 00-4 0z",
    users:    "M15 19.128a9.38 9.38 0 002.625.372 9.337 9.337 0 004.121-.952 4.125 4.125 0 00-7.533-2.493M15 19.128v-.003c0-1.113-.285-2.16-.786-3.07M15 19.128v.106A12.318 12.318 0 018.624 21c-2.331 0-4.512-.645-6.374-1.766l-.001-.109a6.375 6.375 0 0111.964-3.07M12 6.375a3.375 3.375 0 11-6.75 0 3.375 3.375 0 016.75 0zm8.25 2.25a2.625 2.625 0 11-5.25 0 2.625 2.625 0 015.25 0z",
    mic:      "M12 18.75a6 6 0 006-6v-1.5m-6 7.5a6 6 0 01-6-6v-1.5m6 7.5v3.75m-3.75 0h7.5M12 15.75a3 3 0 01-3-3V4.5a3 3 0 116 0v8.25a3 3 0 01-3 3z",
    globe:    "M12 21a9.004 9.004 0 008.716-6.747M12 21a9.004 9.004 0 01-8.716-6.747M12 21c2.485 0 4.5-4.03 4.5-9S14.485 3 12 3m0 18c-2.485 0-4.5-4.03-4.5-9S9.515 3 12 3m0 0a8.997 8.997 0 017.843 4.582M12 3a8.997 8.997 0 00-7.843 4.582m15.686 0A11.953 11.953 0 0112 10.5c-2.998 0-5.74-1.1-7.843-2.918m15.686 0A8.959 8.959 0 0121 12c0 .778-.099 1.533-.284 2.253m0 0A17.919 17.919 0 0112 16.5a17.92 17.92 0 01-8.716-2.247m0 0A9.015 9.015 0 013 12c0-1.605.42-3.113 1.157-4.418",
    waveform: "M9.348 14.651a3.75 3.75 0 010-5.303m5.304 0a3.75 3.75 0 010 5.303m-7.425 2.122a6.75 6.75 0 010-9.546m9.546 0a6.75 6.75 0 010 9.546M5.106 18.894c-3.808-3.808-3.808-9.98 0-13.789m13.788 0c3.808 3.808 3.808 9.981 0 13.79M12 12h.008v.007H12V12zm.375 0a.375.375 0 11-.75 0 .375.375 0 01.75 0z",
    check:    "M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z",
    film:     "M3.375 19.5h17.25m-17.25 0a1.125 1.125 0 01-1.125-1.125M3.375 19.5h1.5C5.496 19.5 6 18.996 6 18.375m-2.625 0V5.625m0 12.75v-1.5c0-.621.504-1.125 1.125-1.125m18.375 2.625V5.625m0 12.75c0 .621-.504 1.125-1.125 1.125m1.125-1.125v-1.5c0-.621-.504-1.125-1.125-1.125m0 3.75h-1.5A1.125 1.125 0 0118 18.375M20.625 4.5H3.375m17.25 0c.621 0 1.125.504 1.125 1.125M20.625 4.5h-1.5C18.504 4.5 18 5.004 18 5.625m3.75 0v1.5c0 .621-.504 1.125-1.125 1.125M3.375 4.5c-.621 0-1.125.504-1.125 1.125M3.375 4.5h1.5C5.496 4.5 6 5.004 6 5.625m-3.75 0v1.5c0 .621.504 1.125 1.125 1.125m0 0h1.5m-1.5 0c-.621 0-1.125.504-1.125 1.125v1.5c0 .621.504 1.125 1.125 1.125m1.5-3.75C5.496 8.25 6 7.746 6 7.125v-1.5M4.875 8.25C5.496 8.25 6 8.754 6 9.375v1.5",
  }
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" className="w-4 h-4">
      <path strokeLinecap="round" strokeLinejoin="round" d={paths[icon]} />
    </svg>
  )
}

/* ── Pipeline Node ── */
function PipelineNode({ step, status, index }) {
  return (
    <div
      className="flex flex-col items-center gap-2 px-2 min-w-[64px] transition-all duration-300"
      style={{ animation: "fadeIn 0.35s ease-out both", animationDelay: `${index * 55}ms` }}
    >
      <div className="relative">
        {status === "active" && (
          <div className="absolute inset-0 rounded-lg animate-pulse-ring" style={{ background: `${GREEN}20` }} />
        )}
        <div
          className="relative w-10 h-10 rounded-lg flex items-center justify-center transition-all duration-300"
          style={{
            background: status === "done"   ? `${GREEN}12`
                      : status === "active" ? `${GREEN}0d`
                      : "rgba(255,255,255,0.03)",
            border: status === "done"   ? `1px solid ${GREEN}50`
                  : status === "active" ? `1px solid ${GREEN}60`
                  : "1px solid rgba(255,255,255,0.07)",
            color: status === "pending" ? "rgba(255,255,255,0.18)" : GREEN,
          }}
        >
          {status === "done"
            ? <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.5} className="w-4 h-4"><path strokeLinecap="round" strokeLinejoin="round" d="M4.5 12.75l6 6 9-13.5" /></svg>
            : <StepIcon icon={step.icon} />}
        </div>
      </div>
      <span
        className="text-[9px] font-mono uppercase tracking-wider text-center"
        style={{ color: status === "pending" ? "rgba(255,255,255,0.2)" : status === "active" ? "rgba(255,255,255,0.85)" : `${GREEN}cc` }}
      >{step.label}</span>
    </div>
  )
}

/* ── Pipeline Connector ── */
function PipelineConnector({ lit, active }) {
  return (
    <div className="relative h-px w-8 flex-shrink-0 mt-[-26px] overflow-hidden">
      <div className="absolute inset-0 transition-all duration-500" style={{ background: lit ? `${GREEN}45` : "rgba(255,255,255,0.06)" }} />
      {active && (
        <div className="absolute top-0 h-full w-1/3 bg-gradient-to-r from-transparent via-white/50 to-transparent"
          style={{ animation: "beam 1.2s ease-in-out infinite" }} />
      )}
    </div>
  )
}

/* ── Metric Pill ── */
function MetricPill({ label, value }) {
  if (value == null) return null
  return (
    <div
      className="flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-mono"
      style={{ background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.07)", animation: "fadeIn 0.3s ease-out forwards" }}
    >
      <span className="font-semibold" style={{ color: GREEN }}>{value}</span>
      <span className="text-white/30">{label}</span>
    </div>
  )
}

/* ── Transcript Panel ── */
function TranscriptPanel({ segments }) {
  if (!segments?.length) return null
  const speakers = [...new Set(segments.map(s => s.speaker))]
  const colorMap = {}
  speakers.forEach((s, i) => { colorMap[s] = SPEAKER_COLORS[i % SPEAKER_COLORS.length] })

  return (
    <div
      className="p-3 sm:p-5 max-h-60 overflow-y-auto rounded-xl"
      style={{ background: "rgba(255,255,255,0.02)", border: "1px solid rgba(255,255,255,0.07)" }}
    >
      <div className="text-[9px] font-mono uppercase tracking-[0.25em] text-white/20 mb-4">Transcript</div>
      <div className="space-y-3">
        {segments.map((seg, i) => (
          <div key={i} style={{ animation: "fadeIn 0.3s ease-out both", animationDelay: `${i * 40}ms` }}>
            <div className="flex items-center gap-2 mb-1">
              <div className="w-1 h-1 rounded-full flex-shrink-0" style={{ background: colorMap[seg.speaker] }} />
              <span className="text-[10px] font-mono font-semibold" style={{ color: colorMap[seg.speaker] }}>{seg.speaker}</span>
              <span className="text-[10px] font-mono text-white/20">{formatTime(seg.start)}–{formatTime(seg.end)}</span>
            </div>
            {seg.text            && <p className="text-xs text-white/40 ml-3 leading-relaxed">{seg.text}</p>}
            {seg.translated_text && <p className="text-xs ml-3 leading-relaxed" style={{ color: colorMap[seg.speaker] + "80" }}>→ {seg.translated_text}</p>}
          </div>
        ))}
      </div>
    </div>
  )
}

/* ── Synced Player ── */
function SyncedPlayer({ originalUrl, dubbedUrl, language }) {
  const origRef = useRef(null)
  const dubRef  = useRef(null)
  const [playing, setPlaying] = useState(false)
  const [current, setCurrent] = useState(0)
  const [dur,     setDur]     = useState(0)

  const syncPlay  = () => { origRef.current?.play();  dubRef.current?.play();  setPlaying(true)  }
  const syncPause = () => { origRef.current?.pause(); dubRef.current?.pause(); setPlaying(false) }

  const onTime = useCallback(() => {
    const t = origRef.current?.currentTime || 0
    setCurrent(t)
    if (dubRef.current && Math.abs(dubRef.current.currentTime - t) > 0.3) dubRef.current.currentTime = t
  }, [])

  const scrub = (e) => {
    const t = parseFloat(e.target.value)
    if (origRef.current) origRef.current.currentTime = t
    if (dubRef.current)  dubRef.current.currentTime  = t
    setCurrent(t)
  }

  const langLabel = LANGUAGES.find(l => l.code === language)?.label || language

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {[
          { ref: origRef, label: "Original",          muted: true,  onTime, onMeta: () => setDur(origRef.current?.duration || 0) },
          { ref: dubRef,  label: `Dubbed · ${langLabel}`, muted: false, onTime: undefined, onMeta: undefined },
        ].map((v, i) => (
          <div key={i} className="rounded-xl overflow-hidden" style={{ border: "1px solid rgba(255,255,255,0.08)" }}>
            <div className="relative bg-black">
              <div
                className="absolute top-2.5 left-2.5 z-10 px-2 py-1 rounded-md text-[11px] font-mono font-medium"
                style={{ background: "rgba(0,0,0,0.75)", border: "1px solid rgba(255,255,255,0.09)", color: i === 1 ? GREEN : "rgba(255,255,255,0.6)" }}
              >{v.label}</div>
              <video
                ref={v.ref}
                src={i === 0 ? originalUrl : dubbedUrl}
                muted={v.muted}
                onTimeUpdate={v.onTime}
                onLoadedMetadata={v.onMeta}
                className="w-full"
              />
            </div>
          </div>
        ))}
      </div>
      <div className="flex items-center gap-3 sm:gap-4">
        <button
          onClick={playing ? syncPause : syncPlay}
          className="w-9 h-9 rounded-full flex items-center justify-center flex-shrink-0 transition-all hover:opacity-80 active:scale-95"
          style={{ background: GREEN }}
        >
          {playing
            ? <svg fill="black" viewBox="0 0 24 24" className="w-3.5 h-3.5"><path d="M6 4h4v16H6zM14 4h4v16h-4z"/></svg>
            : <svg fill="black" viewBox="0 0 24 24" className="w-3.5 h-3.5 ml-0.5"><path d="M8 5v14l11-7z"/></svg>
          }
        </button>
        <input type="range" min={0} max={dur || 1} step={0.1} value={current} onChange={scrub} className="flex-1" />
        <span className="text-xs font-mono text-white/25 flex-shrink-0 tabular-nums">{formatTime(current)} / {formatTime(dur)}</span>
      </div>
    </div>
  )
}

/* ── Main App ── */
export default function App() {
  const [file,        setFile]        = useState(null)
  const [language,    setLanguage]    = useState("es")
  const [jobId,       setJobId]       = useState(null)
  const [status,      setStatus]      = useState(null)
  const [originalUrl, setOriginalUrl] = useState(null)
  const [dubbedUrl,   setDubbedUrl]   = useState(null)
  const [isDragging,  setIsDragging]  = useState(false)
  const [isUploading, setIsUploading] = useState(false)
  const pollRef = useRef(null)
  const fileRef = useRef(null)

  const handleFile = (f) => {
    if (!f) return
    setFile(f)
    setOriginalUrl(URL.createObjectURL(f))
    setJobId(null); setStatus(null); setDubbedUrl(null)
  }

  const startJob = async () => {
    if (!file) return
    setIsUploading(true)
    const form = new FormData()
    form.append("file", file)
    form.append("target_language", language)
    const res  = await fetch(`${API_BASE}/dub`, { method: "POST", body: form })
    const data = await res.json()
    setIsUploading(false)
    setJobId(data.job_id)
    setStatus({ status: "queued", step: "Queued", progress: 0 })
    pollRef.current = setInterval(() => pollStatus(data.job_id), 1500)
  }

  const pollStatus = async (id) => {
    try {
      const data = await fetch(`${API_BASE}/status/${id}`).then(r => r.json())
      setStatus(data)
      if (data.status === "done")  { clearInterval(pollRef.current); setDubbedUrl(`${API_BASE}/download/${id}`) }
      if (data.status === "error") { clearInterval(pollRef.current) }
    } catch {}
  }

  useEffect(() => () => { if (pollRef.current) clearInterval(pollRef.current) }, [])

  const isRunning = status?.status === "running" || status?.status === "queued"
  const isDone    = status?.status === "done"
  const isError   = status?.status === "error"

  const reset = () => { setJobId(null); setStatus(null); setFile(null); setOriginalUrl(null); setDubbedUrl(null) }

  return (
    <div className="min-h-screen bg-black text-white font-sans">
      {!jobId && <SonarRings />}
      {/* ── Header ── */}
      <header
        className="sticky top-0 z-50 px-4 sm:px-8 flex items-center justify-between backdrop-blur-xl"
        style={{ height: "56px", background: "rgba(0,0,0,0.92)", borderBottom: "1px solid rgba(255,255,255,0.06)", animation: "fadeIn 0.5s ease-out both" }}
      >
        <div className="flex items-center gap-3.5">
          <svg viewBox="0 0 24 24" className="w-8 h-8 flex-shrink-0" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M4 12L7 9L11 15L14 9L17 12" stroke={GREEN} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
            <path d="M7 15L10 18L14 12L17 18L20 15" stroke={GREEN} strokeWidth="2" strokeOpacity="0.5" strokeLinecap="round" strokeLinejoin="round"/>
          </svg>
          <span className="text-base font-semibold tracking-tight">Syncr</span>
          <span className="text-white/15 select-none hidden sm:inline">·</span>
          <span className="text-[11px] font-mono text-white/30 uppercase tracking-wider hidden sm:inline">AI Dubbing Studio</span>
        </div>
        <div className="hidden sm:flex items-center gap-2 text-[11px] font-mono text-white/35">
          <span className="w-1.5 h-1.5 rounded-full flex-shrink-0 animate-pulse" style={{ background: GREEN }} />
          GPU Ready
        </div>
      </header>

      <main className="relative max-w-6xl mx-auto px-4 sm:px-8 flex flex-col md:h-[calc(100vh-56px)] overflow-y-auto">

        {/* ══ LANDING ══ */}
        {!jobId && (
          <div className="md:flex-1 grid grid-cols-1 md:grid-cols-2 gap-6 md:gap-12 items-center py-6 md:py-0">

            {/* Left: Hero */}
            <div className="relative flex flex-col justify-center min-w-0">
              <div
                className="inline-flex items-center gap-2 px-2.5 py-1 rounded-md text-[10px] font-mono text-white/35 tracking-widest uppercase mb-6 w-fit"
                style={{ background: "rgba(255,255,255,0.04)", border: "1px solid rgba(255,255,255,0.08)", animation: "slideUp 0.5s ease-out both" }}
              >
                <span className="w-1 h-1 rounded-full animate-pulse flex-shrink-0" style={{ background: GREEN }} />
                HackIllinois 2026
              </div>

              <h1 className="text-3xl sm:text-4xl md:text-[3.2rem] font-bold tracking-tight leading-[1.1] mb-5" style={{ animation: "slideUp 0.5s ease-out 0.1s both" }}>
                Any voice.<br />
                <span style={{ color: GREEN }}>Any language.</span>
              </h1>

              <p className="text-white/40 text-[0.95rem] leading-relaxed mb-8" style={{ animation: "slideUp 0.5s ease-out 0.2s both" }}>
                Upload a video — every actor speaks your target language in their own cloned voice, orchestrated across parallel GPU containers.
              </p>

              <div className="flex gap-2 sm:gap-3" style={{ animation: "slideUp 0.5s ease-out 0.35s both" }}>
                {[
                  { value: "40+", label: "GPU Containers" },
                  { value: "∞",   label: "Any Length"     },
                  { value: "10",  label: "Languages"      },
                ].map(s => (
                  <div
                    key={s.label}
                    className="flex-1 py-3 px-3 rounded-xl text-center"
                    style={{ background: "rgba(255,255,255,0.02)", border: "1px solid rgba(255,255,255,0.07)" }}
                  >
                    <div className="text-lg sm:text-xl font-bold font-mono" style={{ color: GREEN }}>{s.value}</div>
                    <div className="text-[9px] text-white/25 mt-0.5 uppercase tracking-wider font-mono">{s.label}</div>
                  </div>
                ))}
              </div>
            </div>

            {/* Right: Upload card */}
            <div className="flex flex-col gap-3 justify-center min-w-0" style={{ animation: "slideUp 0.45s ease-out 0.1s both" }}>
              {/* Drop zone */}
              <div
                onDragOver={(e) => { e.preventDefault(); setIsDragging(true) }}
                onDragLeave={() => setIsDragging(false)}
                onDrop={(e) => { e.preventDefault(); setIsDragging(false); handleFile(e.dataTransfer.files[0]) }}
                onClick={() => fileRef.current?.click()}
                className="relative rounded-xl p-4 sm:p-5 text-center cursor-pointer transition-all duration-200"
                style={{
                  background: isDragging ? `${GREEN}08` : "rgba(255,255,255,0.02)",
                  border: isDragging ? `1px solid ${GREEN}55` : file ? `1px solid ${GREEN}35` : "1px solid rgba(255,255,255,0.08)",
                }}
              >
                <input ref={fileRef} type="file" accept="video/*" className="hidden" onChange={(e) => handleFile(e.target.files[0])} />

                {file ? (
                  <>
                    <div className="w-10 h-10 rounded-lg flex items-center justify-center mx-auto mb-3" style={{ background: `${GREEN}15`, border: `1px solid ${GREEN}30` }}>
                      <svg viewBox="0 0 24 24" fill="none" stroke={GREEN} strokeWidth={1.5} className="w-5 h-5">
                        <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                      </svg>
                    </div>
                    <p className="font-medium text-sm text-white truncate max-w-[200px] mx-auto">{file.name}</p>
                    <p className="text-xs text-white/30 mt-1 font-mono">{(file.size / 1e6).toFixed(1)} MB · click to change</p>
                  </>
                ) : (
                  <>
                    <div
                      className="w-10 h-10 rounded-lg flex items-center justify-center mx-auto mb-3 transition-all duration-200"
                      style={{ background: isDragging ? `${GREEN}15` : "rgba(255,255,255,0.04)", border: "1px solid rgba(255,255,255,0.08)" }}
                    >
                      <svg viewBox="0 0 24 24" fill="none" stroke="rgba(255,255,255,0.35)" strokeWidth={1.5} className="w-5 h-5">
                        <path strokeLinecap="round" strokeLinejoin="round" d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5m-13.5-9L12 3m0 0l4.5 4.5M12 3v13.5" />
                      </svg>
                    </div>
                    <p className="text-sm text-white/55 font-medium">Drop your video here</p>
                    <p className="text-xs text-white/25 mt-1 font-mono">MP4 · MOV · AVI — any length</p>
                  </>
                )}
              </div>

              {/* Language grid */}
              <div className="grid grid-cols-3 sm:grid-cols-5 gap-1.5">
                {LANGUAGES.map((lang) => (
                  <button
                    key={lang.code}
                    onClick={() => setLanguage(lang.code)}
                    className="py-2 px-1 rounded-lg text-xs transition-all duration-150 flex flex-col items-center gap-0.5"
                    style={{
                      background: language === lang.code ? `${GREEN}10` : "rgba(255,255,255,0.02)",
                      border:     language === lang.code ? `1px solid ${GREEN}40` : "1px solid rgba(255,255,255,0.06)",
                      color:      language === lang.code ? "rgba(255,255,255,0.85)" : "rgba(255,255,255,0.3)",
                    }}
                  >
                    <lang.Flag className="w-5 h-auto rounded-sm" />
                    <span className="text-[10px] sm:text-[8px] leading-none font-mono mt-0.5 w-full text-center truncate px-0.5">{lang.label}</span>
                  </button>
                ))}
              </div>

              {/* Submit */}
              <button
                onClick={startJob}
                disabled={!file || isUploading}
                className="w-full py-3 rounded-xl font-semibold text-sm tracking-wide transition-all duration-150 disabled:opacity-20 disabled:cursor-not-allowed hover:opacity-90 active:scale-[0.99]"
                style={{ background: GREEN, color: "#000" }}
              >
                {isUploading ? (
                  <span className="flex items-center justify-center gap-2">
                    <svg className="w-4 h-4" style={{ animation: "spin 0.8s linear infinite" }} viewBox="0 0 24 24" fill="none">
                      <circle cx="12" cy="12" r="10" stroke="black" strokeWidth="3" opacity="0.2" />
                      <path d="M12 2a10 10 0 0110 10" stroke="black" strokeWidth="3" strokeLinecap="round" />
                    </svg>
                    Uploading...
                  </span>
                ) : "Dub this video →"}
              </button>
            </div>
          </div>
        )}

        {/* ══ PIPELINE DASHBOARD ══ */}
        {isRunning && (
          <div className="flex-1 flex flex-col justify-center overflow-y-auto py-6 space-y-3" style={{ animation: "slideUp 0.4s ease-out forwards" }}>
            <div
              className="p-4 sm:p-6 rounded-xl"
              style={{ background: "rgba(255,255,255,0.02)", border: "1px solid rgba(255,255,255,0.07)" }}
            >
              {/* Status row */}
              <div className="flex items-center justify-between mb-5">
                <div className="flex items-center gap-2.5">
                  <div className="w-1.5 h-1.5 rounded-full flex-shrink-0 animate-pulse" style={{ background: GREEN }} />
                  <TypewriterText text={status?.step || ""} />
                </div>
                <span className="font-mono text-sm font-semibold" style={{ color: GREEN }}>{status?.progress}%</span>
              </div>

              {/* Progress bar */}
              <div className="w-full h-1 rounded-full mb-7 overflow-hidden" style={{ background: "rgba(255,255,255,0.06)" }}>
                <div
                  className="progress-bar h-full rounded-full transition-all duration-700 ease-out"
                  style={{ width: `${status?.progress}%`, background: GREEN }}
                />
              </div>

              {/* Steps */}
              <div className="relative z-10 flex items-start justify-center overflow-x-auto pb-1 pt-6">
                {PIPELINE_STEPS.map((step, i) => {
                  const s = getStepStatus(step, status?.step, status?.progress || 0)
                  return (
                    <div key={step.key} className="flex items-start">
                      {i > 0 && <PipelineConnector lit={s === "done" || s === "active"} active={s === "active"} />}
                      <PipelineNode step={step} status={s} index={i} />
                    </div>
                  )
                })}
              </div>

              {/* Waveform */}
              <div className="mt-5 pt-5 border-t border-white/[0.05]">
                <WaveformBars active={isRunning} />
              </div>
            </div>

            {/* Metrics */}
            <div className="flex flex-wrap gap-2">
              <MetricPill label="chunks"     value={status?.total_chunks && `${status?.completed_chunks || 0}/${status?.total_chunks}`} />
              <MetricPill label="speakers"   value={status?.speakers_found} />
              <MetricPill label="segments"   value={status?.segments_found} />
              <MetricPill label="containers" value={status?.containers_total} />
            </div>

            <TranscriptPanel segments={status?.transcript_preview} />
          </div>
        )}

        {/* ══ ERROR ══ */}
        {isError && (
          <div className="flex-1 flex items-center justify-center" style={{ animation: "fadeIn 0.3s ease-out forwards" }}>
            <div
              className="max-w-md w-full p-6 rounded-xl"
              style={{ background: "rgba(239,68,68,0.04)", border: "1px solid rgba(239,68,68,0.12)" }}
            >
              <div className="flex items-start gap-3">
                <div className="w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0" style={{ background: "rgba(239,68,68,0.1)" }}>
                  <svg viewBox="0 0 24 24" fill="none" stroke="#f87171" strokeWidth={2} className="w-4 h-4">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m9-.75a9 9 0 11-18 0 9 9 0 0118 0zm-9 3.75h.008v.008H12v-.008z" />
                  </svg>
                </div>
                <div>
                  <p className="font-semibold text-red-400 text-sm">Pipeline error</p>
                  <p className="text-red-400/50 text-xs mt-1 font-mono leading-relaxed">{status?.error}</p>
                </div>
              </div>
              <button onClick={reset} className="mt-4 text-xs font-mono text-white/25 hover:text-white/50 transition-colors">← Try again</button>
            </div>
          </div>
        )}

        {/* ══ RESULT ══ */}
        {isDone && originalUrl && dubbedUrl && (
          <div className="flex-1 overflow-y-auto py-6 space-y-5" style={{ animation: "slideUp 0.4s ease-out forwards" }}>
            <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
              <div>
                <h2 className="text-xl sm:text-2xl font-bold">Dubbing complete</h2>
                <p className="text-white/35 text-sm mt-0.5 font-mono">Your video is ready</p>
              </div>
              <a
                href={dubbedUrl}
                download="syncr_dubbed.mp4"
                className="px-5 py-2.5 rounded-xl font-semibold text-sm transition-all hover:opacity-90 active:scale-95 flex-shrink-0"
                style={{ background: GREEN, color: "#000" }}
              >Download ↓</a>
            </div>

            <SyncedPlayer originalUrl={originalUrl} dubbedUrl={dubbedUrl} language={language} />
            <TranscriptPanel segments={status?.transcript_preview} />

            <button onClick={reset} className="text-xs font-mono text-white/25 hover:text-white/50 transition-colors">
              ← Dub another video
            </button>
          </div>
        )}

      </main>
    </div>
  )
}
