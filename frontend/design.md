# Design — Intel Monitor Frontend

A locked design system for the Intel Monitor web console. Every page-level
redesign reads this file before emitting code. Do not regenerate per page —
extend or amend this file when the system needs to grow.

## Genre

modern-minimal, dark, data-dense console.

The product is an operational monitoring tool, not a marketing site.
Clarity, scanability, and information density outrank decoration.

## Macrostructure family

- Cockpit (home): Workbench — dense panels, live metrics, signal feed.
- List pages (social accounts / websites / tasks): tabular or list-first
  layouts with a compact toolbar; avoid decorative card waterfalls.
- Detail pages: Long Document / workbench detail — one primary column,
  supporting facts in a rail.
- Settings: single-column document layout. One card per concern, no nested
  cards.
- Login / setup: split or top-aligned layout; not a full-viewport centred
  hero.

## Theme

Tokens live in `src/global.css` `:root`. Components must reference tokens by
name, never inline hex or OKLCH values.

```css
--accent: #22C55E;
--accent-strong: #16A34A;
--accent-light: rgba(34,197,94,0.12);

--bg: #050B14;
--surface-0: #0B1120;
--surface-1: #111827;
--surface-2: #1A2332;
--surface-3: #0F172A;

--text-primary: #F8FAFC;
--text-secondary: #CBD5E1;
--text-muted: #94A3B8;
--text-dim: #8494A8;

--border: rgba(248,250,252,0.08);
--border-strong: rgba(248,250,252,0.14);
```

Rules:

- Accent footprint ≤ 5 % per viewport. Accent marks status, selection, and
  primary actions only.
- No decorative radial blooms, floating orbs, or mesh gradients.
- No thick side-stripe cards. Use a hairline border or a small square mark
  beside the heading.
- No gradient button fills. Primary buttons use `--accent`, hover uses
  `--accent-strong`.
- Dark-surface elevation is expressed with lightness, not glows.
  At most one live-status dot may pulse.

## Typography

Three functional families only:

- Display: DM Serif Display (`--font-display`). Page titles only. Always
  roman; no italic headers.
- Body: Inter (`--font-body`).
- Mono: JetBrains Mono (`--font-mono`). Labels, numerals, status text.

Chinese fallbacks: Noto Sans SC / Noto Serif SC. Orbitron is removed.

Rules:

- Headings are roman. Emphasis comes from weight, accent colour, or a drawn
  underline — never italic display text.
- Numbers in columns use `font-variant-numeric: tabular-nums`.
- One font stack per role. Do not introduce a fourth family.

## Spacing

4-point scale, multiples of 4 px. Use named tokens where available; raw
values must sit on the scale.

## Motion

- One entrance animation per page: the page title only
  (`animate-fade-in-up`). Lists and cards render statically.
- State changes use 150–250 ms exponential ease-out
  (`cubic-bezier(0.22, 1, 0.36, 1)`).
- Never use `transition: all`. List the animated properties explicitly.
- No hover lift + shadow + glow combinations. Pick one signal per element.
- No infinite breathing except the single system-live indicator.
- `prefers-reduced-motion` must neutralise all animation.

## Microinteractions stance

- Silent success for visible results. Toasts are for failures and invisible
  async effects.
- Hover affordances must have a focus or persistent equivalent.
- Focus rings appear instantly via `:focus-visible`:
  `outline: 2px solid var(--accent); outline-offset: 2px`.
- Custom clickable elements must expose `role`, `tabIndex`, keyboard
  activation, and the relevant `aria-*` state.

## CTA voice

- Primary CTA: solid `--accent` fill, radius 10, 44 px height, roman
  Inter 600.
- Secondary CTA: outline or text button with `--border`.
- Clickable labels must stay on one line; never wrap to two lines.

## Icon language

- One library: `@ant-design/icons`.
- No emoji as feature icons. No mixed icon sets.

## Content honesty

- Metrics and status values come from APIs only. If a value is missing,
  render `—`, not an invented number.
- No fabricated testimonials, logos, or uptime claims.

## Responsiveness

- `html, body { overflow-x: clip; }`.
- Verify 320 / 375 / 414 / 768 px: no horizontal scroll, no wrapped CTA
  text, image-bearing grid tracks use `minmax(0, 1fr)`.
- Table-heavy pages may scroll inside their own container, never the root.

## Accessibility floor

- Small text (under 24 px regular / 18 px bold) must reach 4.5:1 against
  its computed background. Current minimum approved tokens:
  `--text-dim: #8494A8` and `--text-muted: #94A3B8` on surface colours.
- Interactive controls ship all relevant states: default, hover,
  focus-visible, active, disabled, loading, error, success.
- Every icon-only control has an accessible name.

## Page allowances

- Cockpit may use mono labels and compact panels, but no HUD glow layer.
- Marketing pages do not exist in this product. If one is added later,
  amend this file with a marketing macrostructure family first.

## Hallmark stamp

New or redesigned pages stamp the top of their stylesheet:

```css
/* Hallmark · genre: modern-minimal · macrostructure: <name> ·
   design-system: design.md · designed-as-app */
```
