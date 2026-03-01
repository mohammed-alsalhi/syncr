# Syncr — Brand & Logo Guide

> Reference sheet for designing the Syncr logo. The logo will replace the current placeholder in the header.

---

## Current Placeholder (to be replaced)

```jsx
<div
  className="w-6 h-6 rounded flex items-center justify-center text-[10px] font-black font-mono"
  style={{ background: "#62DE61", color: "#000" }}
>S</div>
```

A 24×24px rounded green square with a black "S" in JetBrains Mono Black. This is the element the new logo will replace.

---

## Logo Specifications

### Size & Space
| Property | Value | Notes |
|----------|-------|-------|
| Container | 24×24px (`w-6 h-6`) | Current slot in the header |
| Max recommended | 28×28px | Can bump up slightly if needed |
| Header height | 56px | Logo must sit comfortably within this |
| Spacing | 12px gap to "Syncr" text | Set by `gap-3` in the flex container |
| Alignment | Vertically centered (`self-center`) | Independent of text baseline alignment |

### Required Formats
| Format | Purpose |
|--------|---------|
| **SVG** | Primary — used inline in the React component |
| **PNG @2x** | 48×48px or 56×56px — fallback, favicon source |
| **PNG @4x** | 96×96px or 112×112px — high-DPI, README, docs |
| **Favicon** | 32×32 `.ico` or `.png` — browser tab |

### Color Specifications

The logo must work on a **pure black (`#000`) background**. Two color modes:

#### Primary (color on dark)
| Element | Color | Hex |
|---------|-------|-----|
| Logo mark | Green | `#62DE61` |
| Background | None (transparent) or Black | `#000000` |

#### Monochrome (single color)
| Variant | Color | Use case |
|---------|-------|----------|
| White | `rgba(255,255,255,0.85)` | Light text contexts, watermarks |
| Black | `#000000` | Print, light backgrounds |
| Green | `#62DE61` | On dark backgrounds (same as primary) |

### Typography Context

The logo sits next to these text elements in the header:

```
[LOGO] Syncr · AI DUBBING STUDIO
```

| Element | Font | Size | Weight | Style |
|---------|------|------|--------|-------|
| "Syncr" | Space Grotesk | 14px (`text-sm`) | 600 (semibold) | `tracking-tight` |
| "AI Dubbing Studio" | JetBrains Mono | 10px (`text-[10px]`) | 400 | uppercase, `tracking-wider` |

The logo should feel cohesive with **Space Grotesk** (geometric, clean, slightly rounded) — not clash with it.

---

## Brand Essence

### What Syncr Does
AI dubbing studio — upload a video, every actor speaks a target language in their own cloned voice, orchestrated across parallel GPU containers. Scales from clips to full-length movies.

### Name Origin
**Syncr** = Sync + r. Voice synchronization. Keeping dubbed voices in sync with the original timing, pacing, and lip movement.

### Personality
| Trait | Meaning |
|-------|---------|
| **Technical** | Built for GPU clusters, containers, AI models — not a toy |
| **Clean** | Minimal UI, no decoration, every element has purpose |
| **Precise** | Timing-aware, quality-verified, per-segment volume matching |
| **Fast** | Parallel processing, 40+ containers, scales with content |

### Logo Should Feel Like
- A tool mark, not a mascot
- Something you'd see in a terminal header or a CLI banner
- Geometric and clean — matches the Space Grotesk typeface vibe
- Recognizable at 24px (tiny) and at 200px (docs/README)

### Logo Should NOT Feel Like
- Playful or cartoonish
- Overly complex or detailed (won't read at 24px)
- Generic audio/video icon
- Skeuomorphic

---

## Concepts

### A. Sync Signal (current)
Two curved arcs (top opening up, bottom opening down) with a center dot. Represents sync/signal — two waveforms mirroring around a center point.

```svg
<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
  <path d="M18 8C18 8 16 5 12 5C8 5 6 8 6 8" stroke="#62DE61" stroke-width="2" stroke-linecap="round"/>
  <path d="M6 16C6 16 8 19 12 19C16 19 18 16 18 16" stroke="#62DE61" stroke-width="2" stroke-linecap="round"/>
  <circle cx="12" cy="12" r="2" fill="#62DE61"/>
</svg>
```

### B. Play + Echo (current)
A large play triangle, a vertical bar (pause/separator), and a smaller forward-facing triangle at 60% opacity. Represents playback → dubbing output — the original voice echoed into a new language.

```svg
<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
  <path d="M5 5L11 9V15L5 19V5Z" fill="#62DE61"/>
  <rect x="13" y="5" width="2" height="14" rx="1" fill="#62DE61"/>
  <path d="M17 9L21 12L17 15V9Z" fill="#62DE61" fill-opacity="0.6"/>
</svg>
```

### C. Zigzag S (current)
A continuous zigzag stroke forming a geometric S-shape with sharp miter joins and square caps. Represents signal flow / data transformation.

```svg
<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
  <path d="M17 7H7L4 10V11L7 14H17L20 17V18L17 21H7" stroke="#62DE61" stroke-width="2.5" stroke-linecap="square" stroke-linejoin="miter"/>
</svg>
```

### D. Dual Waveform (current)
Two zigzag waveforms offset and overlapping — the top one full opacity, the bottom one at 50%. Represents original audio and its dubbed echo, synced but shifted.

```svg
<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
  <path d="M4 12L7 9L11 15L14 9L17 12" stroke="#62DE61" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
  <path d="M7 15L10 18L14 12L17 18L20 15" stroke="#62DE61" stroke-width="2" stroke-opacity="0.5" stroke-linecap="round" stroke-linejoin="round"/>
</svg>
```

---

## Implementation

Once the logo SVG is ready, it replaces the placeholder in `App.jsx` (line 414–417):

```jsx
{/* Before (placeholder) */}
<div className="w-6 h-6 rounded ..." style={{ background: "#62DE61", color: "#000" }}>S</div>

{/* After (inline SVG) */}
<svg viewBox="0 0 24 24" className="w-6 h-6 flex-shrink-0 self-center" fill="none">
  {/* logo paths here */}
</svg>
```

### File Locations
```
frontend/
  public/
    favicon.ico          ← browser tab icon
    logo.svg             ← full-size vector
  src/
    assets/
      logo.svg           ← importable for React (or inline directly)
```

---

## Quick Reference

```
Primary Green:   #62DE61
Background:      #000000
Body Font:       Space Grotesk
Mono Font:       JetBrains Mono
Logo Size:       24×24px (header), scalable SVG
Logo Style:      Geometric, minimal, tool-like
```
