# Syncr — Frontend Design Document

> Tracks design philosophy, component inventory, animation system, layout decisions, and ongoing goals.

---

## Design Philosophy

**"Clean Dark Studio"** — the UI is a minimal, dark-themed control panel focused on clarity and function. No background effects, no visual noise — just content, data, and clean transitions. The vibe: a professional dubbing console that gets out of the way.

### Principles
1. **Content first** — every element shows data or guides the user. No decorative layers.
2. **Single accent color** — green (`#62DE61`) is the only color. Everything else is white at varying opacities on pure black.
3. **Progressive reveal** — boot sequence → hero landing → upload flow → pipeline dashboard → result player. Each phase earns the next.
4. **Zero scroll on landing** — the entire upload experience lives in one viewport frame (laptop/PC). Pipeline and result views allow internal scroll within a fixed-height container.
5. **Subtle > flashy** — animations are functional (fade-in, slide-up, pulse) not decorative.

---

## Color & Typography Tokens

### Colors
| Token | Value | Usage |
|-------|-------|-------|
| Background | `#000000` | Body base (pure black) |
| Green (primary accent) | `#62DE61` | Buttons, progress bars, active states, icons, highlights, "S" logo, slider thumbs, text selection |
| Header surface | `rgba(0,0,0,0.92)` | Sticky header with backdrop blur |
| Card surface | `rgba(255,255,255,0.02)` | Dropzone, stat pills, pipeline cards, transcript panel |
| Card border | `rgba(255,255,255,0.07–0.08)` | Subtle borders on all cards/surfaces |
| Text primary | `rgba(255,255,255,0.85)` | Headings, selected language labels |
| Text secondary | `rgba(255,255,255,0.40–0.55)` | Body copy, descriptions |
| Text muted | `rgba(255,255,255,0.20–0.30)` | Labels, timestamps, subtitles |
| Text faint | `rgba(255,255,255,0.15–0.06)` | Separators, disabled states, scrollbar |
| Error red | `#f87171` / `rgba(239,68,68,…)` | Error state text, icons, card borders |
| Speaker colors | `#62DE61`, `#60a5fa`, `#f472b6`, `#fb923c`, `#a78bfa`, `#34d399`, `#fbbf24` | Per-speaker transcript coloring (green, blue, pink, orange, purple, teal, amber) |

### Fonts
| Family | Tailwind Class | Weight | Usage |
|--------|---------------|--------|-------|
| Space Grotesk | `font-sans` (default) | 300–700 | Body text, headings, buttons, UI labels. Set globally on `<body>` with `-0.01em` letter-spacing. |
| JetBrains Mono | `font-mono` | 400–700 | Stats, metric pills, "AI Dubbing Studio" subtitle, timestamps, file sizes, pipeline labels, terminal boot text, "GPU Ready" indicator. |

Both loaded as web fonts with system fallbacks (`system-ui, sans-serif` and `ui-monospace, monospace`).

---

## Layout Architecture

### Viewport Strategy
```
┌─────────────────────────────────────────┐  ← 100vh
│  <header> (sticky, 56px)                │
│  backdrop-blur-xl, rgba(0,0,0,0.92)     │
├─────────────────────────────────────────┤
│  <main> height: calc(100vh - 56px)      │
│  max-w-6xl mx-auto, flex flex-col       │
│                                         │
│  LANDING (grid grid-cols-[1fr,1fr])     │
│  ┌──────────────┬──────────────────┐    │
│  │  Hero / Left │  Upload / Right  │    │
│  │  - Eyebrow   │  - Dropzone      │    │
│  │  - Title     │  - Language grid  │    │
│  │  - Subtitle  │  - Start btn     │    │
│  │  - Stats     │                  │    │
│  └──────────────┴──────────────────┘    │
│                                         │
│  PIPELINE: flex-1 overflow-y-auto       │
│  ERROR:    flex-1 flex items-center     │
│  RESULT:   flex-1 overflow-y-auto       │
└─────────────────────────────────────────┘
```

`body { overflow: hidden }` prevents any scroll bleed on the landing page. Internal scroll only activates in pipeline/result views.

---

## Component Inventory

### Boot & Utility Components

| Component | Description |
|-----------|-------------|
| `BootSequence` | Terminal-style cold boot overlay. Renders on first mount, types `BOOT_LINES` (system status messages) at 130ms/line on a dark card with `rgba(255,255,255,0.03)` background. Phases: `"booting"` (typing with blinking cursor) → `"fading"` (opacity transition out, 0.8s) → `"done"` (unmounts). Total duration ~2.2s. |
| `TypewriterText` | Types characters one-by-one at 22ms/char with blinking cursor. Used for the pipeline step label during processing. Resets and re-types when text prop changes. |
| `WaveformBars` | 36 animated bars with `wave-bar` keyframe + staggered delays. Bars have sinusoidal base heights for visual variety. Active state uses green, inactive uses `rgba(255,255,255,0.06)`. Displayed at the bottom of the pipeline card. |

### Pipeline Components

| Component | Description |
|-----------|-------------|
| `PipelineNode` | Single step card: 40×40 rounded-lg icon box + label underneath. Three states: `pending` (dim white), `active` (green with pulse-ring animation), `done` (green with checkmark). 7 steps: Chunk → Diarize → Transcribe → Translate → Synthesize → Quality → Composite. |
| `PipelineConnector` | Horizontal 32px line between pipeline steps. Fills green when lit, has a beam animation sweep when active. |
| `MetricPill` | Small stat badge (`label + value`). Shows chunks, speakers, segments, and container counts. Green value + muted label on a subtle card background. |
| `TranscriptPanel` | Scrollable list (max 240px) of transcript segments. Each segment shows speaker dot + name (color-coded), timestamps, original text, and translated text. Speaker colors assigned in order from `SPEAKER_COLORS` array. |
| `StepIcon` | Returns the appropriate SVG icon per pipeline step key. Icons: scissors, users, mic, globe, waveform, check, film. All rendered as 16×16 outline stroke SVGs. |

### Result Components

| Component | Description |
|-----------|-------------|
| `SyncedPlayer` | Side-by-side original + dubbed video players in a 2-column grid. Videos stay in sync via `onTimeUpdate` (re-syncs if drift > 0.3s). Shared play/pause button (green circle) and range scrubber. Dubbed label is green-colored for distinction. |

### Helper Functions

| Function | Description |
|----------|-------------|
| `getStepStatus(step, currentStep, progress)` | Maps the current status string to a pipeline step state (`pending`/`active`/`done`) using keyword matching. |
| `formatTime(s)` | Formats seconds as `M:SS`. |

---

## App Phases

### 1. Boot (BootSequence)
Full-screen black overlay → monospace terminal card types system init lines → fades out → unmounts.

### 2. Landing (no jobId)
Two-column grid. Left: eyebrow badge ("HackIllinois 2026" with pulse dot), hero title ("Any voice. / Any language."), description paragraph, three stat pills (40+ GPU Containers, ∞ Any Length, 10 Languages). Right: drag-and-drop zone (file upload), 5×2 language grid (10 languages with flag emoji), "Dub this video →" submit button.

### 3. Pipeline (running/queued status)
Rounded card with: status row (pulse dot + typewriter step label + progress %), full-width progress bar with shimmer, 7-step pipeline node chain with connectors, waveform visualizer. Below: metric pills row + transcript panel.

### 4. Error
Centered card with red styling. Error icon + "Pipeline error" heading + error message. "← Try again" link resets state.

### 5. Result (done status)
"Dubbing complete" heading + download button (green). Synced side-by-side video player. Transcript panel. "← Dub another video" link resets state.

---

## Animation System

### Keyframes (defined in `index.css`)

| Name | Duration | Usage |
|------|----------|-------|
| `fadeIn` | 0.45s | Section entries, cards appearing, pipeline nodes (staggered), transcript segments |
| `slideUp` | 0.45s | Hero subtitle, stats row, upload card, pipeline/result view entry |
| `shimmer` | 2s ∞ | Progress bar shine effect (pseudo-element sweeps across) |
| `spin` | 0.8s ∞ | Upload spinner |
| `wave-bar` | 380–880ms ∞ | Pipeline waveform bars (alternating, staggered delays) |
| `pulse-ring` | 1.8s ∞ | Expanding ring on active pipeline nodes |
| `beam` | 1.2s ∞ | Sweep across active pipeline connectors |
| `blink-cursor` | 1s ∞ | Typewriter cursor blink (boot sequence + pipeline status) |

### Tailwind Animations (via config)
- `animate-fade-in` → `fadeIn 0.45s ease-out forwards`
- `animate-slide-up` → `slideUp 0.45s ease-out forwards`
- `animate-pulse-ring` → `pulse-ring 1.8s ease-out infinite`
- `animate-pulse` (built-in) → used for status dots

---

## CSS Details (`index.css`)

- **Body**: `font-family: 'Space Grotesk'`, `background: #000`, `letter-spacing: -0.01em`, `overflow: hidden`
- **Progress bar shimmer**: `.progress-bar::after` — 40%-width gradient sweep via `shimmer` keyframe
- **Scrollbar**: 4px width, transparent track, `rgba(255,255,255,0.08)` thumb
- **Text selection**: `rgba(98,222,97,0.2)` background (green tint)
- **Range input**: Custom styled — 3px track, 14px green thumb, hover scale effect

---

## Data Configuration

### Languages (hardcoded array)
10 languages: Spanish, French, German, Arabic, Mandarin, Japanese, Portuguese, Hindi, Korean, Italian. Each with ISO code + flag emoji.

### Pipeline Steps (hardcoded array)
7 steps: `chunking` → `diarizing` → `transcribing` → `translating` → `synthesizing` → `quality` → `compositing`.

### Speaker Colors
7-color palette cycling: green, blue, pink, orange, purple, teal, amber.

---

## Design Goals & Roadmap

### Completed
- [x] Clean dark minimal UI (replaced matrix/aurora/effects design)
- [x] Terminal boot sequence on load
- [x] No-scroll single-frame landing layout
- [x] Compact dropzone with file state
- [x] Language grid (5×2)
- [x] Hero stats row
- [x] Pipeline dashboard with 7-step visualization
- [x] Waveform visualizer
- [x] Synced side-by-side video player
- [x] Transcript panel with speaker color coding
- [x] Metric pills (chunks, speakers, segments, containers)
- [x] Error state display

### Planned / Ideas
- [ ] **Responsive design** — mobile/tablet layout (currently laptop/PC optimized)
- [ ] **Pipeline visualization** — animated chunk map (grid of chunk cards with live status)
- [ ] **Video player polish** — custom controls matching the dark theme, sync indicator
- [ ] **Drag-to-reorder languages** — allow ranking preferred target language
- [ ] **Progress granularity** — per-chunk progress bars in pipeline view
- [ ] **Download screen** — celebratory result screen with stats (containers used, time saved, languages)
- [ ] **Error recovery UX** — specific error messages with suggested fixes (e.g., file too large, unsupported format)
- [ ] **Accessibility** — keyboard navigation, `prefers-reduced-motion` support, ARIA labels

### Known Issues / Tech Debt
- `body { overflow: hidden }` may conflict on very small screens — needs media query guard
- Language grid is hardcoded to 10 languages — should derive from a config array
- No loading skeleton for transcript panel — appears abruptly when data arrives
- Video player has no error handling for failed loads
