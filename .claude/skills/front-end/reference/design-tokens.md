# Design tokens and the global stylesheet

Read before writing any CSS, choosing a color, or styling a Vuetify component. Part of the `front-end` skill; the rules summary is in `../SKILL.md`.

## Styling system

This app uses **Cognitive Companion Design System v2**: warm editorial calm. Warm cream paper background, grounded sage green primary, terracotta accent, deep warm ink text. No frosted glass, no blue/purple tech palette, no animated gradients. Calm motion. Senior-legible type.

### Brand in one sentence

Three feelings: **calm**, **dignity**, **trust**. Surfaces are warm paper. Type is humanist serif (headings) + humanist sans (body) + monospace (data). Semantic colors are muted, never alarming.

### Fonts

| Token | Face | Role |
|---|---|---|
| `--cc-font` | Hanken Grotesk | All UI body text, labels, buttons |
| `--cc-font-display` | Newsreader | Page headings, card titles, brand name, tender moments |
| `--cc-font-mono` | IBM Plex Mono | Timestamps, IDs, data values |

Vuetify's `$body-font-family` maps to `--cc-font`, `$heading-font-family` maps to `--cc-font-display`. Don't override these per-component.

### Design tokens (`frontend/src/styles/theme.css`)

All custom CSS properties are prefixed `--cc-` and live in two blocks:

- `:root`: DS v2 primitive scales (stone/sage/terra), invariant spatial tokens, fonts, radii
- `.v-theme--ccWarm`: all surface, text, border, shadow, and brand tokens for the single warm theme

Marauders parchment tokens live in `marauders.css` only (overrides a subset of `--cc-*` on `.v-theme--ccMarauders`). Never add per-theme rules to component scoped styles.

**Always use these variables** instead of hardcoded colors:

```css
/* Surfaces */
--cc-bg               /* #FBF8F3 warm cream page background */
--cc-bg-elevated      /* #FFFDF9 dialog / elevated card */
--cc-surface          /* #FFFDF9 card surface */
--cc-surface-2        /* #F4EDE2 tonal / table header / inset section */
--cc-surface-3        /* #F4EDE2 input field background */

/* Text */
--cc-text-1           /* #1D1A14 primary -- warm near-black */
--cc-text-2           /* #5F5544 secondary / medium-emphasis */
--cc-text-3           /* #877960 tertiary / disabled / section headers */

/* Brand */
--cc-brand            /* #3F6B52 sage-500 -- primary action color */
--cc-brand-strong     /* #305340 sage-600 -- hover state */
--cc-brand-soft       /* rgba(63,107,82,0.12) -- tonal chip / highlight */
--cc-brand-softer     /* rgba(63,107,82,0.06) -- active nav item tint */

/* Semantic */
--cc-success          /* #2F8F5B green-care */
--cc-warning          /* #C98A2E gold-notice */
--cc-error            /* #BC5740 brick-alert (muted, never alarm-red) */
--cc-info             /* #4E7A8C blue-info */

/* Borders */
--cc-divider          /* #E8DDCC hairline warm neutral */
--cc-divider-strong   /* #D6C7AF slightly stronger */
--cc-glass-border     /* #E8DDCC card border (same as divider) */
--cc-glass-border-strong /* #D6C7AF dialog border */

/* Shadows -- warm ink, soft daylight */
--cc-shadow-xs / --cc-shadow-sm / --cc-shadow-md / --cc-shadow-lg
--cc-shadow-glass     /* same as --cc-shadow-sm */
--cc-shadow-glass-hover /* same as --cc-shadow-md */
--cc-shadow-inset     /* inset 0 1px 2px -- soft depth for input fields */

/* Focus -- DS signature terracotta ring */
--cc-focus-ring       /* terra-300 #DC8D6B */
--cc-shadow-focus     /* 0 0 0 3px var(--cc-focus-ring) -- keyboard focus ring */

/* Radii */
--cc-radius-xs: 6px; --cc-radius-sm: 10px; --cc-radius-md: 14px;
--cc-radius-lg: 20px; --cc-radius-xl: 28px; --cc-radius-pill: 999px;
```

### What the global stylesheet handles automatically

The global `theme.css` rules apply to the Vuetify components below. **Never add a background-color, border, or shadow to these elements directly** -- the global rules own them and your inline styles will conflict or break on theme switch to ccMarauders.

- `v-app-bar`: `--cc-app-bar-glass` background, `--cc-divider` bottom border
- `v-navigation-drawer`: `--cc-drawer-glass` background, `--cc-divider` border
- Elevated `v-card` (non-outlined, non-tonal, non-flat): `--cc-surface` background, `--cc-glass-border` border, `--cc-shadow-glass` shadow, `--cc-radius-lg` (20px) corners. Overlay cards inside `.v-overlay__content` (menus) stay tight at `--cc-radius-sm`.
- `v-card.v-card--variant-tonal`: `--cc-surface-2` background
- Dialog cards: `--cc-bg-elevated` background, `--cc-shadow-lg`, `--cc-radius-xl` (28px)
- `v-field--variant-outlined` inputs: `--cc-surface` background, `--cc-radius-md` corners, soft `--cc-shadow-inset`, `--cc-divider-strong` border; on focus a sage border plus a soft terracotta `--cc-shadow-focus` ring
- **Outlined field labels render ABOVE the field, not floating in the border (DS Input/Select).** The global rule moves the `label` out of Vuetify's notch to a static line above the field, keeps the top border solid (no notch cut), and fixes the field box at 48px. Any field with a `label` (any density) gets a 24px label band reserved as **`padding-top`** on the input wrapper -- real height that never collapses with the previous field's margin, so the label can't be clipped by the field on the line above. Hint/error stay below. Do not fight this with per-field CSS or floating-label hacks.
- Field background: enabled `--cc-surface` (DS surface-card #FFFDF9, solid -- no gradient); disabled `--cc-surface-2` (DS surface-sunk).
- **The field box stays vertically centered in the input.** A `hide-details` labeled field has no bottom slot to balance the top label band, so the global rule mirrors the band (`--cc-field-label-band`) as `padding-bottom` on it. This keeps the box centered, which means buttons/toggles/checkboxes placed next to a field in an `align-items: center` row line up with the field box **automatically** -- no per-row class. (Fields that show a hint/error already have a balancing bottom slot and are excluded.)
- **Invariant for mixed rows:** a row that puts a labeled field next to a switch/checkbox/pill/button MUST use `align-items: center` (the standard header pattern `d-flex align-center` already does; for a `v-row`/`v-col` grid use `align="center"`). That is what keeps the control aligned with the field box. A bare `d-flex` (defaults to `stretch`) or `align="start"` will drop the control to the top -- add `align-center`.
- Focus (keyboard): `.v-btn`, links, and `[tabindex]` elements get the terracotta `--cc-shadow-focus` ring via `:focus-visible`. Do not add custom focus outlines.

### Utility classes (defined in `theme.css`)

| Class | Use |
|---|---|
| `.glass-card` | Warm paper card with hairline border and hover lift. Use on non-Vuetify wrappers and explicit card wrappers. |
| `.cc-card-soft` | DS Card "soft" tone -- sage-tinted panel for gentle emphasis. Add alongside a card class. |
| `.cc-card-accent` | DS Card "accent" tone -- terracotta-tinted panel for warm, human moments. Add alongside a card class. |
| `.cc-badge` + `.cc-badge--{good,notice,alert,info,brand}` | DS Badge: calm pill status label with hand-tuned tone pairs. Add `<span class="cc-badge__dot" />` inside for the leading dot. For one-off status labels; existing semantic `v-chip`s keep their `statusColor()` mapping. |
| `.stat-card` | Dashboard metric panel. Hover lift + sage border accent. |
| `.cc-inset-section` | Grouped sub-section within dialogs. Uses `--cc-surface-2`. |
| `.cc-gradient-text` | Newsreader brand text in sage. Used for the app name in the nav. |
| `.cc-eyebrow` | Small-caps tracked label in terracotta (`--terra-500`) -- the warm spark accent. Use above section titles. |
| `.cc-code` | Inline monospace code chip in sage tint. |
| `.cc-main-container` | `max-width: 1440px` centered container. |
| `.tracking-tight` | `letter-spacing: -0.014em`. Use on all page titles (`text-h4`). |

### Vuetify theme

There is a single product theme: `ccWarm`. The Marauders Easter-egg uses `ccMarauders` (separate parchment palette in `marauders.css`).

- The `defaultTheme` in `main.js` is `ccWarm` (unless localStorage says `ccMarauders`).
- There is no dark mode toggle. Do not add a theme switcher for ccDark/ccLight -- those themes were removed.
- Vuetify `color="primary"` resolves to sage-500 (`#3F6B52`). `color="secondary"` resolves to terra-400 (`#C8704F`).
- `VSwitch`, `VCheckbox`, and `VRadioGroup` default to `color="primary"` in `main.js`, so selection controls read **sage when on** (never neutral grey). `VSwitch` also defaults to `inset`. Do not redundantly set `color="primary"` on these -- it is already the default.
- Chart palettes derive from `--cc-*` tokens via `useChartTheme()` -- charts adapt automatically.

### DS v2 color philosophy

- Page backgrounds are warm paper, never cold white or dark.
- Cards are off-white warm paper (`--cc-surface`), not translucent glass.
- Borders are hairline warm stone, not deep or glowing.
- Shadows are warm-ink-tinted (rgba(45,38,26,...)), not blue-tinted.
- The "notice" level (yellow/amber) is used for gentle attention; `--cc-error` (brick-alert) is used for things needing awareness, never alarm-red neon.
- Avoid blue. The closest blue in the palette is `--cc-info` (#4E7A8C), used for neutral informational contexts only.
