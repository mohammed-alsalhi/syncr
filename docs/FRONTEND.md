# Syncr — Frontend Design Document

> Tracks design philosophy, component inventory, animation system, layout decisions, and ongoing goals.

---

## Design Philosophy

**"Matrix Terminal meets AI Cinema"** — the UI should feel like a professional AI control room where every element has purpose. Dark, cinematic, and alive with subtle motion. The vibe: a hacker's dubbing studio from the future.

### Principles
1. **No dead space** — every pixel either shows data, sets atmosphere, or guides the user.
2. **Layered depth** — background effects (aurora, matrix rain, geometry) recede behind glassy foreground cards.
3. **Progressive reveal** — boot sequence → hero landing → upload flow → pipeline dashboard → result player. Each phase earns the next.
4. **Zero scroll on landing** — the entire upload experience lives in one viewport frame (laptop/PC). Pipeline and result views allow internal scroll within a fixed-height container.
5. **Subtle > flashy** — animations enhance without distracting. Rain is atmospheric, not aggressive.

---

## Color & Typography Tokens

### Colors
| Token | Value | Usage |
|-------|-------|-------|
| Background | `#020408` | Body base |
| Card surface | `rgba(5,5,12,0.75)` | Dropzone, glassmorphism cards |
| Emerald primary | `#10b981` | Accents, glows, selected states |
| Emerald light | `#34d399` / `#4ade80` | Highlights, decode-active text |
| Cyan accent | `#06b6d4` / `#22d3ee` | Secondary glow, chromatic aberration |
| Violet accent | `rgba(167,139,250,…)` | Matrix rain tertiary color mode |
| Text primary | `#f0fdf4` | Headings, body copy |
| Text muted | `rgba(255,255,255,0.45)` | Labels, subtitles |

### Fonts
| Family | Weight | Usage |
|--------|--------|-------|
| Space Grotesk | 300–700 | Body, UI labels, buttons |
| JetBrains Mono | 400–700 | Titles (MatrixDecodeTitle), code, terminal output |

---

## Layout Architecture

### Viewport Strategy
```
┌─────────────────────────────────────────┐  ← 100vh
│  <nav> (fixed ~57px)                    │
├─────────────────────────────────────────┤
│  <main> height: calc(100vh - 57px)      │
│  flex flex-col                          │
│                                         │
│  LANDING (grid grid-cols-[1fr,1fr])     │
│  ┌──────────────┬──────────────────┐    │
│  │  Hero / Left │  Upload / Right  │    │
│  │  - Eyebrow   │  - Dropzone      │    │
│  │  - Title     │  - Languages     │    │
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

### Background Layer (`z-0` to `z-10`)

| Component | Description |
|-----------|-------------|
| `MatrixRain` | Canvas-based katakana/symbol column rain. Uses `requestAnimationFrame`. Three color modes per column: emerald, cyan, violet. Head has subtle glow via `ctx.shadowBlur`. Trail fades fast (alpha 0.12) to keep it atmospheric, not dominant. |
| `AuroraBackground` | Three large radial blobs animated with `aurora1/2/3` keyframes (20–26s, ease-in-out). Emerald + cyan color stops. Absolute positioned, `blur-3xl`, `opacity-30`. |
| `PerspectiveGrid` | Static SVG vanishing-point grid, `opacity-[0.035]`. Adds depth to the dark background. |
| `FloatingGeometry` | Scattered SVG shapes (circles, rectangles, triangles) drifting slowly. `opacity-[0.04]`. Pure atmosphere. |
| `FloatingParticles` | 18 tiny white dots floating upward with `float` keyframe animation. Staggered delays, vary in size. |
| `MouseGlow` | Tracks cursor position via `mousemove`. Renders a 700px radial gradient orb that follows the mouse. `opacity-[0.08]`. |
| `ScanlineOverlay` | Fixed div with `repeating-linear-gradient` CRT horizontal scan effect. `opacity-[0.025]`, `z-[101]`. |

### Foreground Components

| Component | Props | Description |
|-----------|-------|-------------|
| `MatrixDecodeTitle` | `lines: [{text, gradient?}]`, `className` | Char-by-char matrix decode → final gradient text. Chars cycle through `DECODE_CHARS` (katakana + symbols) at 45ms, stagger by 72ms per char position. Three phases per char: `idle` (dim), `active` (bright green), `locked` (gradient shine). Uses `lockCountRef` to avoid spurious re-renders. |
| `ChromaticText` | `children`, `className` | Text with R/B channel shift layers via `::before`/`::after` pseudo-elements. `chroma-r` / `chroma-b` keyframes fire at ~95% intervals for glitch bursts. |
| `TypewriterText` | `text`, `delay` | Types characters one-by-one with blinking cursor. Used in subtitles. |
| `TiltCard` | `children`, `className` | 3D tilt on mousemove using CSS `perspective` + `rotateX/Y`. Max ±12° tilt. |
| `AnimatedBorder` | `children`, `className`, `electric?` | Wraps content in a 1px rotating conic-gradient border (emerald→cyan). Electric variant has sparser sparks. Inner content sits on `.card-inner` with dark glass background. |
| `WaveformBars` | — | 5 animated bars with `wave-bar` keyframe + staggered `animation-delay`. Used in pipeline active state. |
| `CelebrationBurst` | — | 12 radial particles that burst outward on job completion. |
| `BootSequence` | — | Terminal cold-boot overlay. Renders on first mount, types `BOOT_LINES` at 155ms/line, fades at 650ms after last line, unmounts at 1450ms. Has its own nested `MatrixRain` behind the terminal card. Phases: `"booting"` → `"fading"` → `"done"` (unmounts). |

### Pipeline / Result Views

| Component | Description |
|-----------|-------------|
| `PipelineNode` | Single step card with status icon, progress ring, timing. |
| `PipelineConnector` | Vertical connector line between steps, fills emerald when active. |
| `MetricPill` | Small stat badge (label + value). |
| `TranscriptPanel` | Scrollable list of transcript segments with speaker color coding. |
| `SyncedPlayer` | Side-by-side original + dubbed video players that stay in sync. |
| `StepIcon` | Returns appropriate Lucide icon per pipeline step. |

---

## Animation System

### Keyframes (defined in `index.css`)

| Name | Duration | Usage |
|------|----------|-------|
| `fadeIn` | 0.55s | Section enters, cards appearing |
| `slideUp` | 0.75s | Subtitle, pipeline section entry |
| `stagger-in` | 0.5s | Repeated list items |
| `shake` | 0.6s | Error state |
| `glow` | 2.5s ∞ | Emerald glow pulse on elements |
| `neon-pulse` | 2s ∞ | Drop-shadow pulse on icons |
| `aurora1/2/3` | 20–26s ∞ | Aurora blob drift |
| `float` | varies ∞ | Particle upward float |
| `geo-drift/spin` | varies ∞ | Background geometry motion |
| `text-shine` | 4–5s ∞ | Gradient text shimmer (decode-locked chars) |
| `chroma-r/b` | ∞ | Chromatic aberration glitch bursts |
| `hero-glitch` | 9s ∞ | Full hero section glitch skew/hue |
| `blink-cursor` | 1s ∞ | Typewriter cursor blink |
| `shimmer` | 0.6–1.8s | Button hover + progress bar shine |
| `pulse-ring` | 2s ∞ | Expanding ring on active elements |
| `beam` | varies | Scan beam across dropzone on drag |
| `spin` | 2–3s ∞ | Animated border conic rotation |
| `gradient-shift` | 4s ∞ | Gradient background pan |
| `wave-bar` | varies ∞ | Pipeline waveform bars |
| `drop-glow` | 3s ∞ | Dropzone idle glow |
| `logo-morph` | 7s ∞ | Logo border-radius morphing |
| `upload-bounce` | 2s ∞ | Upload icon bounce |
| `decode-glow` | 1.2s fwd | One-shot title reveal glow |

### Decode Char States (CSS Classes)

```css
.decode-idle   { color: rgba(16,185,129,0.08); }              /* barely visible */
.decode-active { color: #4ade80; text-shadow: 0 0 14px …; }   /* bright cycling */
.decode-locked { gradient text + text-shine animation; }       /* final state */
```

---

## Changelog

### Session 1 (2026-02-28)

#### MatrixRain — Complete Rewrite
- **Before**: `setInterval`-based, single green color, uniform speed
- **After**: `requestAnimationFrame`, three color modes (emerald/cyan/violet), variable speed (`stepMax` 2–5 frames), head glow via `ctx.shadowBlur=5`, reduced aggression (trail opacity 0.13, fade alpha 0.12)

#### New: MatrixDecodeTitle
- Character-by-character matrix decode animation
- Chars cycle through katakana + symbols (`DECODE_CHARS`) before locking into final letter
- Three visual phases per char: idle → active → locked
- Staggered start times (72ms per char position)
- Uses `lockCountRef` (ref, not state) for lock counting to avoid re-renders
- Fires `animate-decode-glow` when all chars lock

#### New: ScanlineOverlay
- Subtle CRT horizontal scanlines via `repeating-linear-gradient`
- Fixed, full-screen, pointer-events-none

#### New: BootSequence
- Terminal-style cold boot that plays on first load
- Types system status lines at 155ms/line
- Fades and unmounts automatically (1.45s after completion)
- MatrixRain runs behind it for depth

#### Layout: Two-Column No-Scroll
- Completely restructured `<main>` to `height: calc(100vh - 57px)` with flexbox
- Landing: `grid grid-cols-[1fr,1fr] gap-14 items-center`
- `body { overflow: hidden }` prevents scroll on landing
- Pipeline/result views use `flex-1 overflow-y-auto`

#### Dropzone Redesign
- Compact (`p-8` vs old `p-16`)
- SVG icons replacing emoji
- Animated corner brackets that expand on hover/drag
- Scanning beam animation on active drag
- Glassmorphism background: `rgba(5,5,12,0.75)`

#### Language Grid Redesign
- `grid grid-cols-5 gap-1.5` (5×2 fixed layout, was flex-wrap)
- Flag emoji + small text label per slot
- Neon emerald glow + shimmer on selected state

#### Hero Stats Row
- Three data pills: "40+ GPU Containers", "∞ Any Film Length", "10 Languages"
- Emerald→cyan gradient text

---

## Design Goals & Roadmap

### Completed
- [x] Matrix rain atmospheric (not dominant)
- [x] Terminal boot sequence on load
- [x] Matrix decode title animation
- [x] CRT scanline overlay
- [x] No-scroll single-frame landing layout
- [x] Compact dropzone with animated corners + beam
- [x] Language grid (5×2)
- [x] Hero stats row

### Planned / Ideas
- [ ] **Responsive design** — mobile/tablet layout (currently laptop/PC optimized)
- [ ] **Dark mode variations** — consider a "synthwave" purple variant toggle
- [ ] **Pipeline visualization** — animated chunk map (grid of chunk cards with live status)
- [ ] **Speaker color coding** — consistent color per speaker across transcript, waveform, player
- [ ] **Video player polish** — custom controls matching the dark theme, sync indicator
- [ ] **Drag-to-reorder languages** — allow ranking preferred target language
- [ ] **Micro-interactions** — button press ripples, card hover lift effects
- [ ] **Progress granularity** — per-chunk progress bars in pipeline view
- [ ] **Download screen** — celebratory result screen with stats (containers used, time saved, languages)
- [ ] **Error recovery UX** — specific error messages with suggested fixes (e.g., file too large, unsupported format)
- [ ] **Accessibility** — keyboard navigation, `prefers-reduced-motion` support, ARIA labels
- [ ] **Performance audit** — profile canvas renders, check for unnecessary re-renders in pipeline polling

### Known Issues / Tech Debt
- `MatrixDecodeTitle` uses many `setInterval` instances (one per char); consider batching into a single RAF loop for large titles
- `BootSequence` timer cleanup — verify all `setTimeout`/`setInterval` refs are cleared on unmount
- `body { overflow: hidden }` may conflict on very small screens — needs media query guard
- Language grid is hardcoded to 10 languages — should derive from a config array
