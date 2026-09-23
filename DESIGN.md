---
version: alpha
name: Sentri-Inspired-design-analysis
description: An inspired interpretation of Sentri's design language — a developer-tools brand built on a deep purple-violet midnight canvas, electric lime accents, and a slightly subversive illustrated personality.

colors:
  primary: "#150f23"
  ink-deep: "#1f1633"
  on-primary: "#ffffff"
  accent-lime: "#c2ef4e"
  accent-pink: "#fa7faa"
  accent-violet: "#6a5fc1"
  accent-violet-deep: "#422082"
  accent-violet-mid: "#79628c"
  surface-canvas-dark: "#1f1633"
  surface-canvas-light: "#ffffff"
  surface-night: "#150f23"
  surface-press-light: "#f0f0f0"
  surface-press-stronger: "#efefef"
  hairline-violet: "#362d59"
  hairline-cool: "#cfcfdb"
  hairline-cloud: "#e5e7eb"
  ink: "#1f1633"
  ink-press: "#1a1a1a"
  on-dark-muted: "#bdb8c0"
  on-dark-faint: "#3f3849"
  ring-focus: "#9dc1f5"

typography:
  display-hero:
    fontFamily: "Space Grotesk, Rubik, system-ui, sans-serif"
    fontSize: 88px
    fontWeight: 700
    lineHeight: 1.2
    letterSpacing: 0
  display-large:
    fontFamily: "Space Grotesk, Rubik, system-ui, sans-serif"
    fontSize: 60px
    fontWeight: 500
    lineHeight: 1.1
    letterSpacing: 0
  heading-xl:
    fontFamily: "Rubik, -apple-system, system-ui, Segoe UI, Helvetica, Arial, sans-serif"
    fontSize: 30px
    fontWeight: 500
    lineHeight: 1.2
    letterSpacing: 0
  heading-lg:
    fontFamily: "Rubik, -apple-system, system-ui, Segoe UI, Helvetica, Arial, sans-serif"
    fontSize: 27px
    fontWeight: 500
    lineHeight: 1.25
    letterSpacing: 0
  heading-md:
    fontFamily: "Rubik, -apple-system, system-ui, Segoe UI, Helvetica, Arial, sans-serif"
    fontSize: 24px
    fontWeight: 500
    lineHeight: 1.25
    letterSpacing: 0
  heading-sm:
    fontFamily: "Rubik, -apple-system, system-ui, Segoe UI, Helvetica, Arial, sans-serif"
    fontSize: 20px
    fontWeight: 600
    lineHeight: 1.25
    letterSpacing: 0
  body-lg:
    fontFamily: "Rubik, -apple-system, system-ui, Segoe UI, Helvetica, Arial, sans-serif"
    fontSize: 16px
    fontWeight: 400
    lineHeight: 2.0
    letterSpacing: 0
  body-strong:
    fontFamily: "Rubik, -apple-system, system-ui, Segoe UI, Helvetica, Arial, sans-serif"
    fontSize: 16px
    fontWeight: 600
    lineHeight: 1.5
    letterSpacing: 0
  body-md:
    fontFamily: "Rubik, -apple-system, system-ui, Segoe UI, Helvetica, Arial, sans-serif"
    fontSize: 16px
    fontWeight: 500
    lineHeight: 1.5
    letterSpacing: 0
  eyebrow:
    fontFamily: "Rubik, -apple-system, system-ui, Segoe UI, Helvetica, Arial, sans-serif"
    fontSize: 15px
    fontWeight: 500
    lineHeight: 1.4
    letterSpacing: 0
  button-cap:
    fontFamily: "Rubik, -apple-system, system-ui, Segoe UI, Helvetica, Arial, sans-serif"
    fontSize: 14px
    fontWeight: 700
    lineHeight: 1.14
    letterSpacing: 0.2px
  button-cap-light:
    fontFamily: "Rubik, -apple-system, system-ui, Segoe UI, Helvetica, Arial, sans-serif"
    fontSize: 14px
    fontWeight: 500
    lineHeight: 1.29
    letterSpacing: 0.2px
  caption:
    fontFamily: "Rubik, -apple-system, system-ui, Segoe UI, Helvetica, Arial, sans-serif"
    fontSize: 14px
    fontWeight: 400
    lineHeight: 1.43
    letterSpacing: 0
  micro-cap:
    fontFamily: "Rubik, -apple-system, system-ui, Segoe UI, Helvetica, Arial, sans-serif"
    fontSize: 10px
    fontWeight: 600
    lineHeight: 1.8
    letterSpacing: 0.25px
  code:
    fontFamily: "Monaco, Menlo, Ubuntu Mono, monospace"
    fontSize: 16px
    fontWeight: 400
    lineHeight: 1.5
    letterSpacing: 0
  code-strong:
    fontFamily: "Monaco, Menlo, Ubuntu Mono, monospace"
    fontSize: 16px
    fontWeight: 700
    lineHeight: 1.5
    letterSpacing: 0

rounded:
  xs: 4px
  sm: 6px
  md: 8px
  lg: 10px
  xl: 12px
  xxl: 18px
  full: 9999px

spacing:
  xxs: 2px
  xs: 4px
  sm: 8px
  md: 12px
  lg: 16px
  xl: 24px
  xxl: 32px
  section: 96px

components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.on-primary}"
    typography: "{typography.button-cap}"
    rounded: "{rounded.md}"
    padding: 12px 16px
  button-primary-pressed:
    backgroundColor: "{colors.surface-press-stronger}"
    textColor: "{colors.ink-press}"
    typography: "{typography.button-cap}"
    rounded: "{rounded.md}"
    padding: 12px 16px
  button-inverted:
    backgroundColor: "{colors.on-primary}"
    textColor: "{colors.ink-deep}"
    typography: "{typography.button-cap}"
    rounded: "{rounded.md}"
    padding: 12px 16px
  button-ghost-on-dark:
    backgroundColor: "{colors.on-dark-faint}"
    textColor: "{colors.on-primary}"
    typography: "{typography.button-cap}"
    rounded: "{rounded.xl}"
    padding: 8px
  button-violet-token:
    backgroundColor: "{colors.accent-violet-mid}"
    textColor: "{colors.on-primary}"
    typography: "{typography.button-cap-light}"
    rounded: "{rounded.xl}"
    padding: 8px 16px
  button-disabled:
    backgroundColor: "{colors.hairline-cloud}"
    textColor: "{colors.on-dark-muted}"
    typography: "{typography.button-cap}"
    rounded: "{rounded.md}"
    padding: 12px 16px
  pill-neutral-dark:
    backgroundColor: "{colors.surface-night}"
    textColor: "{colors.on-primary}"
    typography: "{typography.caption}"
    rounded: "{rounded.xs}"
    padding: 4px 8px
  text-input:
    backgroundColor: "{colors.surface-canvas-light}"
    textColor: "{colors.ink-deep}"
    typography: "{typography.body-md}"
    rounded: "{rounded.sm}"
    padding: 8px 12px
  text-input-focused:
    backgroundColor: "{colors.surface-canvas-light}"
    textColor: "{colors.ink-deep}"
    typography: "{typography.body-md}"
    rounded: "{rounded.sm}"
    padding: 8px 12px
  card-feature-dark:
    backgroundColor: "{colors.ink-deep}"
    textColor: "{colors.on-primary}"
    typography: "{typography.body-lg}"
    rounded: "{rounded.xxl}"
    padding: 32px
  card-spotlight-violet:
    backgroundColor: "{colors.accent-violet-deep}"
    textColor: "{colors.on-primary}"
    typography: "{typography.body-lg}"
    rounded: "{rounded.xxl}"
    padding: 32px
  code-block:
    backgroundColor: "{colors.surface-night}"
    textColor: "{colors.on-primary}"
    typography: "{typography.code}"
    rounded: "{rounded.md}"
    padding: 16px
  link-on-dark:
    backgroundColor: "{colors.surface-canvas-dark}"
    textColor: "{colors.on-primary}"
    typography: "{typography.body-md}"
    rounded: "{rounded.xs}"
    padding: 0px
  link-on-light:
    backgroundColor: "{colors.surface-canvas-light}"
    textColor: "{colors.ink-deep}"
    typography: "{typography.body-md}"
    rounded: "{rounded.xs}"
    padding: 0px
  nav-bar-light:
    backgroundColor: "{colors.surface-canvas-light}"
    textColor: "{colors.ink-deep}"
    typography: "{typography.body-md}"
    rounded: "{rounded.xs}"
    padding: 16px 24px
  footer-light:
    backgroundColor: "{colors.surface-canvas-light}"
    textColor: "{colors.ink-deep}"
    typography: "{typography.caption}"
    rounded: "{rounded.xs}"
    padding: 32px 24px
---

## Overview

Sentri's design language reads like a debugging console wearing a leather jacket. Deep purple-violet midnight canvas, electric lime accents, and a developer-console cadence. Two-polarity canvas system: deep violet midnight for hero and product pages, white for pricing and dense reference content.

**Key Characteristics:**
- Two-polarity canvas: deep violet midnight (`{colors.surface-canvas-dark}`) for hero/product, white for transactional
- Lime keyword highlight (`{colors.accent-lime}`) as a typographic device, not a color swatch
- Uppercase eyebrow + button caps in `{typography.button-cap}` with 0.2px tracking lift
- Single-primary CTA hierarchy: one filled button per section
- Card surfaces follow the canvas: dark sections nest dark cards, light sections nest white cards
- Body line-height 2.0 on marketing, 1.5 on functional UI

## Colors

### Brand & Accent
- **Midnight Violet** (`{colors.primary}` — `#150f23`): Primary action color, deepest surface tone, filled primary buttons
- **Ink Violet** (`{colors.ink-deep}` — `#1f1633`): Marketing hero canvas, default body text color on light
- **Electric Lime** (`{colors.accent-lime}` — `#c2ef4e`): Signature highlight, keyword chips, footer squiggle
- **Hot Pink** (`{colors.accent-pink}` — `#fa7faa`): Secondary punctuation, sticker outlines, chart points
- **Violet Link** (`{colors.accent-violet}` — `#6a5fc1`): Inline link emphasis
- **Deep Violet** (`{colors.accent-violet-deep}` — `#422082`): Spotlight cards, select dropdowns
- **Mid Violet** (`{colors.accent-violet-mid}` — `#79628c`): Tag-chip fill, faint accent on dark

### Surface
- **Dark Canvas** (`{colors.surface-canvas-dark}` — `#1f1633`): Hero, product, feature-page background
- **Night** (`{colors.surface-night}` — `#150f23`): Cards on dark canvas, code blocks, featured tier
- **Light Canvas** (`{colors.surface-canvas-light}` — `#ffffff`): Pricing, contact, reference pages
- **Hairline Violet** (`{colors.hairline-violet}` — `#362d59`): 1px borders on dark cards
- **Hairline Cloud** (`{colors.hairline-cloud}` — `#e5e7eb`): Borders on light canvas

### Text
- **On Primary** (`{colors.on-primary}` — `#ffffff`): All text on dark canvas
- **On Dark Muted** (`{colors.on-dark-muted}` — `#bdb8c0`): Secondary text, captions on dark
- **On Dark Faint** (`{colors.on-dark-faint}` — `#3f3849`): Translucent surface, ghost buttons

## Typography

### Font Family
- Display: **Space Grotesk** (open-source substitute for proprietary display sans)
- UI: **Rubik** (Google Fonts), fallback to system-ui
- Code: **Monaco**, Menlo, Ubuntu Mono

### Principles
- **Two leading worlds.** Marketing copy uses 2.0 line-height. Functional UI uses 1.5.
- **Caps with tracking.** All button labels and eyebrows uppercase with 0.2px tracking.
- **Headlines as syntax.** Lime chip wraps single keywords inside display headlines.

## Layout

### Spacing System
- Base unit: 8px
- Tokens: 2px, 4px, 8px, 12px, 16px, 24px, 32px, 96px
- Section padding: 96px desktop, 32-48px mobile
- Card internal padding: 32px on feature cards, 24px on compact

## Elevation & Depth

| Level | Treatment | Use |
|---|---|---|
| 0 | Flat, no shadow | Default surface |
| 1 | `box-shadow: rgba(0,0,0,0.08) 0 2px 8px 0` | Inverted buttons on dark canvas |
| 2 | `box-shadow: rgba(0,0,0,0.1) 0 10px 15px -3px, rgba(0,0,0,0.1) 0 4px 6px -4px` | Floating cards on light canvas |
| 3 | `box-shadow: rgb(21,15,35) 0 0 8px 6px` | Glow halo around primary CTA on dark hero |

## Shapes (Border Radius)

| Token | Value | Use |
|---|---|---|
| `{rounded.xs}` | 4px | Badges, status pills, lime keyword chips |
| `{rounded.sm}` | 6px | Text inputs, search boxes |
| `{rounded.md}` | 8px | Primary buttons, code blocks, selects |
| `{rounded.lg}` | 10px | Generic containers |
| `{rounded.xl}` | 12px | Pricing cards, feature cards, nav pill |
| `{rounded.xxl}` | 18px | Image containers, hero illustrations |
| `{rounded.full}` | 9999px | Avatars, circular icon buttons |

## Components

### Buttons
- **`button-primary`**: bg `{colors.primary}`, text white, uppercase 14px/700, padding 12px 16px, radius 8px
- **`button-inverted`**: bg white, text `{colors.ink-deep}`, same geometry
- **`button-ghost-on-dark`**: translucent `{colors.on-dark-faint}`, text white, radius 12px
- **`button-violet-token`**: bg `{colors.accent-violet-mid}`, text white, pill shape

### Cards
- **`card-feature-dark`**: bg `{colors.ink-deep}`, text white, padding 32px, radius 18px
- **`card-spotlight-violet`**: bg `{colors.accent-violet-deep}`, text white, radius 18px
- **`code-block`**: bg `{colors.surface-night}`, text white, Monaco 16px, radius 8px

### Inputs
- **`text-input`**: bg white, text `{colors.ink-deep}`, padding 8px 12px, radius 6px, border `{colors.hairline-cool}`
- Focus: inset shadow `rgba(0,0,0,0.15) 0 2px 10px inset`

### Navigation
- Dark variant on hero, light variant on transactional pages
- Logo left, nav center, primary CTA right
- Mobile: hamburger below 768px

## Do's and Don'ts

### Do
- Reserve `{colors.accent-lime}` for keyword-highlight chips — never as button background
- Pair every button with uppercase 14px/700, 0.2px tracking
- Treat dark and light canvas as two complete worlds
- Use `card-pricing-featured` (dark inverted) instead of accent-bordered light card
- Default body line-height to 1.5 on functional UI, 2.0 on marketing

### Don't
- Don't introduce colors beyond lime and pink — dilutes the violet-and-lime signature
- Don't apply drop shadows to cards on dark canvas — depth comes from texture
- Don't use `{colors.accent-lime}` for body text — breaks contrast
- Don't soften the `{colors.primary}` button to brand-violet — near-black is the point

## Responsive Behavior

### Breakpoints
| Name | Width | Key Changes |
|---|---|---|
| 4K/Wide | >= 1440px | Full content, hero illustration at scale |
| Desktop | 1152-1440px | Default max-width 1152px |
| Laptop | 992-1151px | Pricing 2-up, nav horizontal |
| Tablet | 768-991px | Feature grids 1-up, nav compresses |
| Mobile Large | 640-767px | Hamburger nav, hero 88px -> 56px |
| Mobile | 576-639px | Single-column, section padding 32-48px |

### Touch Targets
- Primary buttons minimum 44x44px on mobile
- Form fields minimum 44px height on mobile

## Iteration Guide

1. Focus on ONE component at a time
2. Reference component names and tokens directly
3. Default to `{typography.body-md}` for UI, `{typography.body-lg}` for marketing
4. Keep `{colors.accent-lime}` scarce — one lime element per viewport
5. When polarizing a surface, choose one canvas and commit to it
