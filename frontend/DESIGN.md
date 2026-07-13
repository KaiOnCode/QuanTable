# Agentic-Quant Frontend Design System

## 1. Atmosphere & Identity

An operational quantitative-research dashboard: compact, neutral, and evidence-first. The signature is dense financial information organized through quiet monochrome surfaces, with semantic color reserved for status and performance.

## 2. Color

The existing tokens in `app/globals.css` are authoritative: `background`/`foreground`, `card`, `popover`, `primary`, `secondary`, `muted`, `accent`, `destructive`, `border`, `input`, `ring`, five `chart-*` tones, and the matching sidebar tokens. Light and dark values remain the existing OKLCH definitions. Product UI uses Tailwind semantic classes such as `bg-card`, `text-muted-foreground`, `border-input`, and `text-destructive`; no raw colors are introduced. Green is an existing performance-only convention and is not a general accent.

## 3. Typography

Geist Sans is the body and heading family through `--font-geist-sans`; Geist Mono is used for tickers, numeric metrics, and machine-shaped identifiers. Existing scale: page titles `text-xl`, section titles `text-base`/`text-lg`, body and labels `text-sm`, descriptions and metadata `text-xs`. Existing weights are `font-medium`, `font-semibold`, and `font-bold`.

## 4. Spacing & Layout

The existing Tailwind 4px spacing scale is authoritative. Strategy forms use a centered `max-w-2xl` column, `p-4 sm:p-6`, `space-y-6` page rhythm, `space-y-4` card bodies, and `space-y-2` field groups. Responsive changes use existing `sm` and `md` breakpoints; controls become full-width on mobile and compact where space permits.

## 5. Components

### Card

- **Structure:** shared `Card`, `CardHeader`, `CardTitle`, `CardDescription`, `CardContent`.
- **States:** static section surface; validation belongs to contained fields, not the card border.
- **Accessibility:** headings describe each grouped configuration section.

### Form Field

- **Structure:** `Label` linked by `htmlFor`, shared `Input` or `Select`, persistent description, then a live validation error.
- **States:** default, focus-visible ring, disabled/pending, and `aria-invalid` error styling already supplied by shared primitives.
- **Strategy quant states:** type selection reveals exactly one supported rule (`momentum` or `sma_crossover`); changing rule restores that rule's last valid draft; invalid numeric syntax or range blocks submission and exposes a field-specific message.
- **Accessibility:** descriptions/errors are connected with `aria-describedby`; the first invalid field receives focus on submit.

### Button

- **Structure:** shared `Button` and `buttonVariants` only.
- **States:** existing default, outline, ghost, disabled, and pending spinner states.
- **Accessibility:** native button semantics; icon-only controls require an accessible name.

### Quant Policy Summary

- **Structure:** read-only definition list inside the existing Settings card.
- **States:** shown only for quant strategies with a supported typed rule; malformed legacy data is described as unavailable, never presented as executable.
- **Accessibility:** text labels include units and do not rely on color.

### Backtest Error Notice

- **Structure:** a dedicated semantic-status surface between Configuration and job/results, using the existing destructive color ramp, border, and card radius.
- **States:** hidden when no blocking/request error exists; visible for local eligibility, validation, strategy-load, or server preflight failures.
- **Accessibility:** `role="alert"`, an icon plus explicit heading and message, and the existing strategy-configuration link when remediation belongs there.

## 6. Motion & Interaction

Use only existing shared transitions and the existing loading spinner. Conditional quant fields appear without decorative motion. Focus remains visible, keyboard submission is supported, and reduced-motion preferences are not overridden.

## 7. Depth & Surface

Mixed tonal shift and borders: page background, card surfaces, `border-input` controls, and the shared popover `shadow-md` are the established hierarchy. Strategy policy fields add no new elevation or decorative effects.

## 8. Accessibility Constraints & Accepted Debt

Target WCAG 2.2 AA: every input has a programmatic label, descriptions and errors are associated, all actions are keyboard reachable, focus is visible, and error text is not color-only. Accepted debt: the existing detail Settings tab is read-only and has no general edit architecture; Todo 2 therefore exposes the persisted quant policy truthfully there instead of inventing an unrelated full-strategy editor.
