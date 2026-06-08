---
name: "Risograph Press"
description: "Two-color spot print, halftone vibes. Fluorescent pink + ink-black on cream paper, 3px misregistration outlines, hand-cut chunky type."
tags: [print, playful, editorial, maximalist]
colors:
  primary:   "#1A1815"
  secondary: "#6B665C"
  tertiary:  "#FF4F8B"
  neutral:   "#F4EFE3"
  surface:   "#FBF7EC"
typography:
  display: Fraunces
  body:    Inter
  mono:    "Space Mono"
  scale:
    hero: "5.5rem / 0.95 / 600 / -0.04em"
    h1:   "3rem / 1 / 500 / -0.03em"
    h2:   "1.5rem / 1.2 / 600 / -0.01em"
    body: "1.0625rem / 1.55 / 400 / 0"
radius:
  sm: 2px
  md: 3px
  lg: 4px
shadows:
  card:   "3px 3px 0 #1A1815"
  button: "2px 2px 0 #1A1815"
borders:
  card:    "2px solid #1A1815"
  divider: "2px solid #1A1815"
buttons:
  primary:
    background: #FF4F8B
    color: #1A1815
    border: 2px solid #1A1815
    shape: rounded
    padding: 12px 20px
    font: display / 600 / 0.9375rem / 0.04em
    uppercase: true
    shadow: 3px 3px 0 #1A1815
  secondary:
    background: #FBF7EC
    color: #1A1815
    border: 2px solid #1A1815
    shape: rounded
    padding: 12px 20px
    font: display / 600 / 0.9375rem / 0.04em
    uppercase: true
    shadow: 3px 3px 0 #FF4F8B
  outline:
    background: transparent
    color: #1A1815
    border: 2px dashed #1A1815
    shape: rounded
    padding: 11px 20px
    font: mono / 700 / 0.875rem / 0.06em
    uppercase: true
  ghost:
    background: transparent
    color: #FF4F8B
    border: none
    shape: sharp
    padding: 10px 4px
    font: mono / 700 / 0.875rem / 0.06em
    uppercase: true
    hover: underline
charts:
  variant: bars
  gridlines: false
  bar_radius: 0
  bar_gap: 8px
  highlight: all
  axis_color: "#1A1815"
  palette: ["#FF4F8B", "#1A1815", "#FF4F8B", "#1A1815", "#FF4F8B"]
fonts_url: "https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,500;9..144,600&family=Inter:wght@400;500;700&family=Space+Mono:wght@400;700&display=swap"
dependencies: ["lucide-react"]
---

# Risograph Press

## AI Build Instructions

> **Read this section before writing any code.** The rules below
> are non-negotiable. Every value used in the UI must come from this
> file's frontmatter — never substitute, approximate, or invent new
> colors, fonts, radii, or shadows. If a value is missing, ask the
> user before adding one.

### 1 · Your role

You are building UI for a project that has adopted **Risograph Press** as its
design system. Treat `DESIGN.md` as the single source of truth.
Your job is to translate the user's product requirements into
components and pages that look like they were designed by the same
person who authored this file.

### 2 · Token compliance

- Pull every color, font family, radius, shadow, and spacing value
  from the frontmatter at the top of this file.
- Use semantic roles (e.g. `primary`, `accent`, `muted`) — never
  hard-code hex values that bypass the system.
- When a token can be expressed as a CSS variable, declare it once
  in your global stylesheet and reference it everywhere downstream.
- The Google Fonts `<link>` is provided in the Typography section.
  Add it to `<head>` before any component renders.

### 3 · Component recipes

Use these recipes verbatim when building the corresponding component.

#### Buttons

Four variants are defined. Pick one — never blend variants or invent a fifth.

- **Primary** — rounded shape, bg `#FF4F8B`, text `#1A1815`, border `2px solid #1A1815`, padding `12px 20px`, weight `600`, uppercased, shadow `3px 3px 0 #1A1815`.
- **Secondary** — rounded shape, bg `#FBF7EC`, text `#1A1815`, border `2px solid #1A1815`, padding `12px 20px`, weight `600`, uppercased, shadow `3px 3px 0 #FF4F8B`.
- **Outline** — rounded shape, text `#1A1815`, border `2px dashed #1A1815`, padding `11px 20px`, weight `700`, uppercased.
- **Ghost** — sharp shape, text `#FF4F8B`, padding `10px 4px`, weight `700`, uppercased.

Reach for **primary** as the single dominant CTA per screen.
**Secondary** for the supporting action. **Outline** for tertiary
actions in toolbars. **Ghost** for inline links and table actions.

#### Cards

- Background: `#FBF7EC`
- Border: `2px solid #1A1815`
- Shadow: `3px 3px 0 #1A1815`
- Radius: `radius.lg` (`4px`)
- Internal padding: `20px` for compact cards, `24–28px` for content cards.

#### Tabs

Variant: `brutalist`. Hard rectangular tabs with thick borders. Active tab is fully filled in the primary color.
Tabs are uppercased with `0.08em` tracking.

#### Charts

- Bar/line variant: `bars`
- Bar radius: `0`
- No gridlines — let the bars/lines carry the data.
- Highlight strategy: `all` — emphasize a single bar/point per chart.
- Use the declared palette in order: `#FF4F8B`, `#1A1815`, `#FF4F8B`, `#1A1815`, `#FF4F8B`.

#### Typography pairings

- **Display (`Fraunces`)** — h1, h2, hero headlines, brand wordmarks.
- **Body (`Inter`)** — paragraphs, labels, button text, form inputs.
- **Mono (`Space Mono`)** — code, eyebrows, metadata, numerals in tables.

### 4 · Hard constraints

Never do any of the following without explicit instruction from the user:

- Introduce a new color, font, radius, or shadow that isn't declared above.
- Mix this system with another (e.g. don't paste in Material or Bootstrap defaults).
- Use generic gradient defaults (purple→blue, peach→pink) — they break the system's voice.
- Reach for emoji icons. Use a consistent icon library and size icons in line with body type.
- Add motion that exceeds the system's restraint — keep transitions short (≤200ms) and subtle.

### 5 · Before you finish — verify

Run through this checklist for every screen you produce:

- [ ] Every color used appears in the Colors table above.
- [ ] Headlines use the display font; body copy uses the body font.
- [ ] Buttons match one of the declared variants exactly (shape, padding, weight).
- [ ] Border-radius values come from `radius.sm` / `radius.md` / `radius.lg` / `radius.pill`.
- [ ] Cards and dividers use the declared border + shadow tokens.
- [ ] No values were invented; if you needed something missing, you stopped and asked.

---

## Overview
Risograph Press is a love letter to the spot-color print era. Two inks — fluorescent pink and warm black — on cream uncoated paper. A 3px ink-offset shadow on every card mimics the slight misregistration of a real Riso pass. Borders are 2px solid ink, hand-cut. Display type is editorial Fraunces; body is Inter; captions are typewriter Space Mono.

The system is loud where it wants to be (pink CTAs with chunky offset shadows) and quiet everywhere else (cream surfaces, ink-only meta).

## Material
- **Page** is **cream #F4EFE3**, never white. The warmth matters — pure white kills the Riso illusion.
- **Cards** sit on **stock #FBF7EC**, one shade lighter, with a **2px solid ink** border and a **3px 3px 0** ink-offset shadow. The shadow is the signature.
- **Pink #FF4F8B** is the spot color. It appears on primary CTAs, accents, and as a misregistration shadow under secondary buttons. Never as body text.

## Typography
- **Display: Fraunces** at hero (5.5rem / 600 / -0.04em). Editorial, optical-size, with a soft serif terminal that pairs with the cream paper.
- **Body: Inter** at 1.0625rem for comfortable read on cream.
- **Mono: Space Mono** for chunky uppercase labels and outline-button text — it reads like a typewriter ribbon.

| Role | Font | Size | Weight | Tracking |
|------|------|------|--------|----------|
| Hero | Display | 5.5rem | 600 | -0.04em |
| H1 | Display | 3rem | 500 | -0.03em |
| H2 | Body | 1.5rem | 600 | -0.01em |
| Body | Body | 1.0625rem | 400 | 0 |
| Label | Mono | 0.875rem | 700 | +0.06em UPPER |

## Buttons (the centerpiece)
Four variants, all uppercase, all chunky.

- **Primary** — pink fill, 2px ink border, **3px 3px 0** ink shadow. Display font, +0.04em tracking. The shadow is non-negotiable.
- **Secondary** — cream tile, 2px ink border, **3px 3px 0 PINK** shadow. Inverted ink relationship, same chunkiness.
- **Outline** — dashed 2px ink, mono label. Reads like a paper cut-line.
- **Ghost** — pink mono label with hover underline. Used inside cards only.

## Charts & Data
Bar charts alternate pink and ink — the spot-color rhythm of a Riso print. **No gridlines, no rounded bars, no shadows on chart elements.** The chart's energy comes from contrast between the two passes.

## Do's and Don'ts
- ✅ Always include the 3px ink-offset shadow on cards and primary CTAs.
- ✅ Mix pink and ink — the system needs both passes to read as Riso.
- ✅ Use cream backgrounds. Pure white breaks the print metaphor.
- ✅ Let display Fraunces breathe at -3% to -4% tracking on hero sizes.
- ❌ No drop-shadow blur. Riso shadows are crisp solid offsets.
- ❌ No third color. Two passes — pink and ink — only.
- ❌ No pill buttons. The brief is hand-cut, not pharmaceutical.
- ❌ No body text in pink. Ink only for prose.

---

## Tokens

> Generated from the same source the live preview renders from.
> Treat the values below as the contract — never substitute approximations.

### Colors

| Role      | Value |
|-----------|-------|
| primary   | `#1A1815` |
| secondary | `#6B665C` |
| tertiary  | `#FF4F8B` |
| neutral   | `#F4EFE3` |
| surface   | `#FBF7EC` |

### Typography

- **Display:** Fraunces
- **Body:** Inter
- **Mono:** Space Mono

| Role | size / leading / weight / tracking |
|------|------------------------------------|
| Hero | 5.5rem / 0.95 / 600 / -0.04em |
| H1   | 3rem / 1 / 500 / -0.03em |
| H2   | 1.5rem / 1.2 / 600 / -0.01em |
| Body | 1.0625rem / 1.55 / 400 / 0 |

### Radius

- sm: `2px`
- md: `3px`
- lg: `4px`

### Shadows

- **card:** `3px 3px 0 #1A1815`
- **button:** `2px 2px 0 #1A1815`

### Borders

- **card:** `2px solid #1A1815`
- **divider:** `2px solid #1A1815`

### Buttons

Four variants, each fully tokenized. The preview renders from these exact values.

#### Primary

| Property | Value |
|----------|-------|
| shape | `rounded` |
| background | `#FF4F8B` |
| color | `#1A1815` |
| border | `2px solid #1A1815` |
| padding | `12px 20px` |
| fontFamily | `display` |
| fontWeight | `600` |
| fontSize | `0.9375rem` |
| tracking | `0.04em` |
| uppercase | `true` |
| shadow | `3px 3px 0 #1A1815` |

#### Secondary

| Property | Value |
|----------|-------|
| shape | `rounded` |
| background | `#FBF7EC` |
| color | `#1A1815` |
| border | `2px solid #1A1815` |
| padding | `12px 20px` |
| fontFamily | `display` |
| fontWeight | `600` |
| fontSize | `0.9375rem` |
| tracking | `0.04em` |
| uppercase | `true` |
| shadow | `3px 3px 0 #FF4F8B` |

#### Outline

| Property | Value |
|----------|-------|
| shape | `rounded` |
| background | `transparent` |
| color | `#1A1815` |
| border | `2px dashed #1A1815` |
| padding | `11px 20px` |
| fontFamily | `mono` |
| fontWeight | `700` |
| fontSize | `0.875rem` |
| tracking | `0.06em` |
| uppercase | `true` |

#### Ghost

| Property | Value |
|----------|-------|
| shape | `sharp` |
| background | `transparent` |
| color | `#FF4F8B` |
| border | `none` |
| padding | `10px 4px` |
| fontFamily | `mono` |
| fontWeight | `700` |
| fontSize | `0.875rem` |
| tracking | `0.06em` |
| uppercase | `true` |
| hoverHint | `underline` |

### Charts

| Property | Value |
|----------|-------|
| variant | `bars` |
| gridlines | `false` |
| barRadius | `0` |
| barGap | `8px` |
| highlight | `all` |
| axisColor | `#1A1815` |
| palette | `#FF4F8B`, `#1A1815`, `#FF4F8B`, `#1A1815`, `#FF4F8B` |

---

## Pro tokens

> Production-fidelity tokens. States, density, motion, elevation,
> content rules and a measured WCAG contract — derived from the
> resting tokens unless explicitly authored.

### States

#### Button

- **hover** — bg: `rgba(255, 79, 139, 0.92)`, shadow: `0 4px 20px -8px rgba(255, 79, 139, 0.4)`
- **focus** — outline: `1.5px solid #FF4F8B`, outline-offset: `4px`
- **active** — transform: `translateY(1px)`, filter: `brightness(0.95)`
- **disabled** — opacity: `0.45`
- **loading** — opacity: `0.7`
- **selected** — bg: `#1A1815`, color: `#FBF7EC`

#### Input

- **hover** — border: `1px solid #1A1815`
- **focus** — border: `1px solid #FF4F8B`, shadow: `0 1px 0 0 #FF4F8B`
- **disabled** — opacity: `0.45`
- **error** — border: `1px solid #991B1B`, shadow: `0 1px 0 0 #991B1B`

#### Card

- **hover** — shadow: `0 8px 24px -12px rgba(15,23,42,0.14)`, transform: `translateY(-1px)`
- **selected** — border: `1px solid #1A1815`

#### Tab

- **hover** — color: `#1A1815`
- **focus** — outline: `1.5px solid #FF4F8B`, outline-offset: `3px`
- **selected** — color: `#FF4F8B`, border: `0 0 2px 0 solid #FF4F8B`

### Density

| Mode | padding × | row × | body | radius × | Use for |
|------|-----------|-------|------|----------|---------|
| compact | 0.72 | 0.78 | 0.8125rem | 0.85 | Information-dense — tables, IDEs, dashboards |
| comfortable | 1 | 1 | 0.9375rem | — | Default — most product UI |
| spacious | 1.35 | 1.3 | 1rem | 1.15 | Editorial — marketing, long-form, settings |

### Motion

**Signature — Page turn.** Deliberate, measured motion — like turning a magazine page. Never jerky, never overdone.

```css
transition: all 320ms cubic-bezier(0.25, 0.46, 0.45, 0.94);
```

| Token | Value |
|-------|-------|
| duration.instant | `80ms` |
| duration.fast | `180ms` |
| duration.base | `320ms` |
| duration.slow | `500ms` |
| easing.standard | `cubic-bezier(0.25, 0.46, 0.45, 0.94)` |
| easing.decelerate | `cubic-bezier(0.0, 0, 0.2, 1)` |
| easing.accelerate | `cubic-bezier(0.4, 0, 1, 1)` |
| easing.spring | `cubic-bezier(0.5, 1.2, 0.6, 1)` |

### Elevation

Five-level scale, system-specific recipe.

| Level | Shadow | Recipe |
|-------|--------|--------|
| level0 | `none` | Hairline only — typical editorial resting state. |
| level1 | `0 1px 2px rgba(15,23,42,0.04)` | Barely visible — list rows, dividers. |
| level2 | `0 8px 24px -12px rgba(15,23,42,0.12)` | Pull-quote, sidebar — soft lift. |
| level3 | `0 16px 40px -16px rgba(15,23,42,0.18)` | Cover story card — clear lift. |
| level4 | `0 32px 80px -24px rgba(15,23,42,0.28)` | Modal — overlays the layout, with scrim. |

### Content

- **measure:** `60ch` (max line length for body prose)
- **paragraph spacing:** `1.5em`
- **list indent:** `1.75em`
- **list gap:** `0.55em`
- **link:** color `#FF4F8B`, underline `always`
- **blockquote:** border `4px solid #FF4F8B`, padding `0.4em 0 0.4em 1.5em`
- **code:** background `rgba(26, 24, 21, 0.06)`, color `#1A1815`

### Accessibility (WCAG 2.1)

**Overall:** FAIL

| Pair | Ratio | Required | Grade | Suggested fix |
|------|-------|----------|-------|---------------|
| Body text on surface | 16.55:1 | AA | AAA | — |
| Body text on canvas | 15.44:1 | AA | AAA | — |
| Muted text on surface | 5.33:1 | AA | AA | — |
| Accent on surface | 2.91:1 | AA-Large | FAIL | `#de004c` → 4.66:1 (AA) |
| Accent on canvas | 2.71:1 | AA-Large | FAIL | `#d40048` → 4.7:1 (AA) |
