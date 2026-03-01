# Syncr — Background Animation Ideas

> Candidates for a subtle, sound-inspired ambient background on the landing page.

---

## Rejected

### A. Equalizer Bars
48 vertical bars anchored to the bottom, breathing up and down at staggered speeds (3–8s). Green on black.

**Why rejected:** Too faint at low opacity, too distracting at higher opacity. Hard to tune.

```jsx
// Component
function AmbientEQ() {
  const bars = useMemo(() =>
    Array.from({ length: 48 }, (_, i) => ({
      id: i,
      height: 20 + Math.random() * 60,
      duration: 3 + Math.random() * 5,
      delay: Math.random() * 6,
    })), [])

  return (
    <div className="fixed inset-0 z-[1] flex items-end justify-center gap-[1vw] px-[3vw] pointer-events-none" style={{ opacity: 0.06 }}>
      {bars.map(b => (
        <div key={b.id} className="flex-1 rounded-t-sm"
          style={{
            height: `${b.height}%`,
            background: "#62DE61",
            transformOrigin: "bottom",
            animation: `eq-breathe ${b.duration}s ease-in-out ${b.delay}s infinite`,
          }}
        />
      ))}
    </div>
  )
}

// CSS keyframe
@keyframes eq-breathe {
  0%, 100% { transform: scaleY(0.15); }
  50%      { transform: scaleY(1); }
}
```

### B. Logo Watermark
Giant version of the dual waveform logo centered behind the page at low opacity.

**Why rejected:** SVG strokes too thin at large scale, looked distorted. Didn't add to the atmosphere.

---

## Candidates

### C. Floating Frequency Rings
Concentric circles that slowly pulse outward from the center of the screen, like sonar or a speaker cone. Each ring fades as it expands.

```
Visual:
         ╭───────╮
       ╭─┤       ├─╮
     ╭─┤ │   ·   │ ├─╮
       ╰─┤       ├─╯
         ╰───────╯
```

- 4–6 rings, staggered start
- Expand from 50px to 600px radius
- Fade from 8% to 0% opacity
- Duration: 6–10s per ring, infinite loop
- Green stroke, no fill

### D. Sine Wave Field
2–3 horizontal sine waves spanning the full viewport width, slowly drifting. Different amplitudes and frequencies give a layered feel, like audio frequencies.

```
Visual:
  ∿∿∿∿∿∿∿∿∿∿∿∿∿∿∿∿∿∿∿∿∿∿∿∿∿   (large, slow)
    ∿∿∿∿∿∿∿∿∿∿∿∿∿∿∿∿∿∿∿∿∿∿∿   (medium)
      ∿∿∿∿∿∿∿∿∿∿∿∿∿∿∿∿∿∿∿∿∿   (small, fast)
```

- SVG `<path>` with animated `d` attribute or CSS `translateX` for drift
- Each wave at different opacity (3%, 5%, 7%)
- Vertical position: centered or slightly below center
- Slow horizontal scroll (30–60s per full cycle)

### E. Particle Drift
Tiny dots (1–3px) floating slowly upward across the screen, like dust particles or audio bits in the air.

- 20–30 particles, randomized positions
- Very slow upward drift (15–25s to cross the screen)
- Green at 4–8% opacity
- Fade in at bottom, fade out at top
- No interaction, pure atmosphere

### F. Grid Pulse
A dot grid covering the background. Dots near the center slowly pulse brighter then dim, creating a radial breathing effect.

```
Visual:
  · · · · · · · · · ·
  · · · · · · · · · ·
  · · · ○ ○ ○ · · · ·
  · · · ○ ● ○ · · · ·
  · · · ○ ○ ○ · · · ·
  · · · · · · · · · ·
```

- CSS grid of small dots
- Radial gradient mask for the pulse zone
- 4–6s breathing cycle
- Dots at 3–5% opacity, pulse zone reaches 8–10%

### G. Horizontal Scan Line
A single faint green line that slowly sweeps from top to bottom of the viewport, like a CRT refresh or audio scanner.

- 1px height, full width, green at 5% opacity
- Slow sweep: 8–12s top to bottom
- Slight glow/blur (2px)
- Loops infinitely with a pause at the bottom before restarting

---

## Requirements
- Must be **subtle** — atmospheric, not distracting
- Green (`#62DE61`) on black (`#000`)
- `pointer-events-none`, `z-[1]` or similar (behind content)
- Lightweight — no canvas if CSS/SVG can handle it
- Should feel **sound/audio inspired**
