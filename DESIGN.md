---
name: Emploi
description: Calm botanical forest green workspace and compact Nuxt UI pages for operational work.
colors:
  color-brand-50: '#f0f7f2'
  color-brand-100: '#dceee1'
  color-brand-200: '#bdddc5'
  color-brand-300: '#93c9a2'
  color-brand-400: '#65ad7b'
  color-brand-500: '#438f5e'
  color-brand-600: '#287448'
  color-brand-700: '#1d613a'
  color-brand-800: '#174d2f'
  color-brand-900: '#123f27'
  color-brand-950: '#092617'
  ui-primary: '#287448'
  ui-success: '#287448'
  ui-warning: '#a16207'
  ui-error: '#b42336'
  ui-info: '#336b83'
  people-canvas: '#f7f9f7'
  people-surface: '#ffffff'
  people-border: '#d7e0d9'
  people-text: '#1b2820'
  people-muted: '#617168'
  people-forest: '#e2f0e6'
  people-mint: '#e7f3e9'
  people-peach: '#fff1e6'
  people-blue: '#e8f1ee'
  people-yellow: '#fff7df'
  people-rose: '#fff0f2'
  people-forest-ink: '#1d613a'
  people-mint-ink: '#1d613a'
  people-peach-ink: '#9a4f0a'
  people-blue-ink: '#336b83'
  people-yellow-ink: '#925d07'
  people-rose-ink: '#b42336'
  dark-ui-primary: '#8ad5a4'
  dark-ui-success: '#8ad5a4'
  dark-ui-warning: '#fcd34d'
  dark-ui-error: '#fda4af'
  dark-ui-info: '#9bc9da'
  dark-people-canvas: '#111a14'
  dark-people-surface: '#18241b'
  dark-people-border: '#37483b'
  dark-people-text: '#edf5ee'
  dark-people-muted: '#afc0b3'
  dark-people-forest: '#1c3b28'
  dark-people-mint: '#1b4029'
  dark-people-peach: '#422d1a'
  dark-people-blue: '#1b3537'
  dark-people-yellow: '#3d3215'
  dark-people-rose: '#40212a'
  dark-people-forest-ink: '#8ad5a4'
  dark-people-mint-ink: '#8ad5a4'
  dark-people-peach-ink: '#fdba74'
  dark-people-blue-ink: '#9bc9da'
  dark-people-yellow-ink: '#fcd34d'
  dark-people-rose-ink: '#fda4af'
  auth-paper: '#f7f9f7'
  auth-ink: '#1b2820'
  auth-muted: '#617168'
  auth-primary: '#287448'
  auth-panel: '#edf5ef'
  auth-line: '#d7e0d9'
  dark-auth-paper: '#111a14'
  dark-auth-ink: '#edf5ee'
  dark-auth-muted: '#afc0b3'
  dark-auth-primary: '#8ad5a4'
  dark-auth-panel: '#1c3b28'
  dark-auth-line: '#37483b'
typography:
  auth-display:
    fontFamily: '"People Editorial", Georgia, serif'
    fontSize: clamp(48px, 4.3vw, 76px)
    fontWeight: 450
    lineHeight: 1.04
    letterSpacing: -.025em
  auth-title:
    fontFamily: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif
    fontSize: clamp(30px, 3vw, 38px)
    fontWeight: 600
    lineHeight: 1.15
    letterSpacing: -.025em
  auth-body:
    fontFamily: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif
    fontSize: 15px
    lineHeight: 1.7
  platform-nav:
    fontFamily: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif
    fontSize: 14px
    fontWeight: 500
    lineHeight: 1.4
  platform-label:
    fontFamily: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif
    fontSize: 12px
    fontWeight: 600
  page-title:
    fontFamily: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif
    fontSize: clamp(24px, 2.4vw, 32px)
    fontWeight: 600
    lineHeight: 1.2
    letterSpacing: -.025em
  page-table:
    fontFamily: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif
    fontSize: 13px
    lineHeight: 1.6
  page-feedback:
    fontFamily: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif
    fontSize: 13px
    lineHeight: 1.6
  dashboard-description:
    fontFamily: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif
    fontSize: 14px
    lineHeight: 1.6
  dashboard-panel-title:
    fontFamily: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif
    fontSize: 16px
    fontWeight: 600
    lineHeight: 1.4
  dashboard-metric:
    fontFamily: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif
    fontSize: clamp(24px, 2.5vw, 32px)
    fontWeight: 600
    lineHeight: 1.15
  dashboard-detail:
    fontFamily: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif
    fontSize: 15px
    fontWeight: 600
  dashboard-label:
    fontFamily: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif
    fontSize: 12px
    lineHeight: 1.5
rounded:
  shortcut: 4px
  control: 8px
  brand-symbol: 10px
  card: 12px
  auth-story: 16px
spacing:
  '4': 4px
  '8': 8px
  '10': 10px
  '12': 12px
  '16': 16px
  '20': 20px
  '24': 24px
  '28': 28px
  '32': 32px
  '44': 44px
  '48': 48px
  '52': 52px
  '60': 60px
  '96': 96px
components:
  platform-nav:
    backgroundColor: transparent
    textColor: '{colors.people-muted}'
    typography: '{typography.platform-nav}'
    rounded: '{rounded.control}'
    padding: 10px 12px
  platform-nav-hover:
    backgroundColor: '{colors.people-canvas}'
    textColor: '{colors.people-text}'
  platform-nav-current:
    backgroundColor: '{colors.people-forest}'
    textColor: '{colors.people-forest-ink}'
  workspace-select:
    backgroundColor: '{colors.people-canvas}'
    textColor: '{colors.people-text}'
    rounded: '{rounded.control}'
    padding: 10px 34px 10px 12px
  platform-search:
    backgroundColor: '{colors.people-canvas}'
    rounded: '{rounded.control}'
    padding: 0 12px
  platform-icon-button:
    width: 44px
    height: 44px
    padding: '0'
  platform-sign-out:
    backgroundColor: '{colors.people-forest}'
    textColor: '{colors.people-forest-ink}'
  platform-sign-out-hover:
    backgroundColor: '{colors.people-surface}'
  people-card:
    backgroundColor: color-mix(in srgb, var(--people-surface) 96%, transparent)
    rounded: '{rounded.card}'
  auth-story:
    backgroundColor: '{colors.auth-panel}'
    textColor: '{colors.auth-primary}'
    rounded: '{rounded.auth-story}'
    padding: clamp(28px, 3vw, 48px)
  auth-input:
    backgroundColor: '{colors.auth-paper}'
  auth-link:
    textColor: '{colors.auth-primary}'
    height: 44px
  page-card:
    backgroundColor: '{colors.people-surface}'
    rounded: '{rounded.card}'
  page-clear-button:
    width: 44px
    height: 44px
  page-table-row:
    typography: '{typography.page-table}'
    height: 52px
  page-table-row-mobile:
    typography: '{typography.page-table}'
    height: 60px
  dashboard-summary-item:
    backgroundColor: '{colors.people-surface}'
    padding: 20px
  dashboard-summary-item-mobile:
    padding: 16px
  dashboard-panel:
    backgroundColor: '{colors.people-surface}'
    rounded: '{rounded.card}'
    padding: 24px
  dashboard-panel-mobile:
    padding: 20px
  data-feedback:
    textColor: '{colors.people-muted}'
    typography: '{typography.page-feedback}'
---

# Design System: Emploi

## Overview

**Creative North Star: "The Calm Botanical Workspace"**

Emploi ("HR made calm") pairs quiet, organic forest greens with clean neutral surfaces to deliver an unhurried, reassuring environment for high-frequency workforce operations. Authentication couples warm paper and ink with editorial display typography and a balanced, informative story composition. The platform workspace uses a clean, compact navigation shell and familiar system sans for efficient daily operations.

This design system records the established frontend design across every existing surface: authentication, shared platform shell, responsive dashboards, lists, filters, forms, and Nuxt UI dialogs. Existing routes, APIs, role boundaries, and ERP master data rules remain authoritative; presentation refinements polish clarity without modifying business logic.

**Key Characteristics:**
- Muted forest green palette (`--color-brand-700: #1d613a`, `--ui-primary: #287448`) paired with tranquil paper/canvas neutrals.
- Strict door distinction: dedicated workforce entrance (`/login`) and isolated technical administration entrance (`/admin/login`).
- Editorial authenticity on sign-in surfaces; compact, highly scannable operational controls in the workspace.
- Flat & tonal elevation model: 1px borders, subtle tonal shifts, and restrained Nuxt UI components.

## Colors

The frontmatter is normative and reflects the implemented CSS variables in `main.css`, `auth.css`, and `platform.css`. The `dark-` entries describe dark-mode overrides; the `auth-` entries are scoped to authentication surfaces.

### Primary

Forest green (`ui-primary: #287448`, `--color-brand-700: #1d613a`) anchors primary actions, active indicators, and keyboard focus rings. Current navigation in the platform pairs subtle forest fill (`people-forest: #e2f0e6`) with deep forest ink (`people-forest-ink: #1d613a`). The full `color-brand-50` through `color-brand-950` ramp provides calibrated shades for Nuxt UI states.

### Neutral

Clean canvas, elevated surface, ink, muted text, and borders use `people-canvas (#f7f9f7)`, `people-surface (#ffffff)`, `people-text (#1b2820)`, `people-muted (#617168)`, and `people-border (#d7e0d9)`. Authentication surfaces alias these tokens cleanly as `auth-paper`, `auth-ink`, `auth-muted`, `auth-panel`, and `auth-line`.

### Semantic

Semantic status indicators use harmonized pastel fill and dark ink pairings:
- **Success / Present:** Mint (`people-mint: #e7f3e9` / `people-mint-ink: #1d613a`)
- **Warning / Pending:** Yellow (`people-yellow: #fff7df` / `people-yellow-ink: #925d07`)
- **Error / Absent:** Rose (`people-rose: #fff0f2` / `people-rose-ink: #b42336`)
- **Info / Regularization:** Blue (`people-blue: #e8f1ee` / `people-blue-ink: #336b83`)
- **Work Arrangement / Shift:** Peach (`people-peach: #fff1e6` / `people-peach-ink: #9a4f0a`)

**The Semantic Appearance Rule.** Always consume colors through implemented CSS custom properties (`var(--people-*)`, `var(--ui-*)`). Never hardcode hex values directly into component templates.

## Typography

Authentication surfaces use locally hosted Newsreader under `People Editorial` with Georgia/serif fallback for hero story displays. Platform workspace controls, navigation, and content use the high-performance system sans stack (`ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif`).

Authentication display headings are capped at 10ch and story body at 34ch (16px/1.7). On smaller desktop viewports (<851px height), display headings scale down to `clamp(40px, 3.6vw, 56px)` and story copy to 14px/1.5.

Platform page headings use the `page-title` role (`clamp(24px, 2.4vw, 32px)`, 600 weight). Tables and status feedback use compact 13px/1.6 typography. Dashboard summary metrics use tabular numerals with `dashboard-metric` (`clamp(24px, 2.5vw, 32px)`, 600 weight), and summary cards feature concise 12px/1.5 labels.

## Layout

At 1024px and above, the fixed desktop sidebar is 256px wide (collapsible to 76px icon rail). Sidebar navigation flexes and scrolls independently from main content. The collapse toggle sits at the far left of the top header and persists in the `people_sidebar_collapsed` cookie.

The sticky header is at least 72px tall with 32px horizontal padding on desktop. It houses the sidebar toggle, global command search, notifications, theme mode toggle, and profile menu. Content containers are capped at 1536px with 32px padding on desktop.

Below 1024px, the sidebar is replaced by a sticky 72px mobile header and a fixed bottom navigation bar (Home, Workspace, permitted role routes, and More). Content has 104px bottom padding to prevent overlap with the bottom navigation bar.

Authentication surfaces use a 1600px outer container with `clamp(20px, 4vw, 72px)` padding: a two-column layout on desktop (story panel on the left, form capped at 440px on the right). Below 1024px, the story panel hides cleanly and the form takes center focus. Technical admin login (`/admin/login`) uses a single-column focused form without decorative distraction.

## Elevation & Depth

**Flat & Tonal:** Surfaces are flat at rest. Depth is established through 1px solid borders (`var(--people-border)`), subtle background tonal shifts (canvas `#f7f9f7` vs surface `#ffffff`), and tinted selection fills (`var(--people-forest)`).

Elevation and box-shadows are strictly reserved for transient floating layers:
- Modals and dialogs
- Dropdown menus and popovers
- Toast notifications and tooltips

No heavy ambient shadows are placed on cards or table rows.

## Shapes

Controls and inputs use an 8px radius (`control`). Cards and dashboard panels use a 12px radius (`card`). Authentication story panels use a softer 16px corner (`auth-story`). Keyboard shortcuts and tags use 4px (`shortcut`).

Icon containers use the 12px card radius with centered grid alignment. Region borders clearly delineate workspace navigation, header, and content regions without nesting multiple heavy cards.

## Components

### Navigation and Workspace Controls

Sidebar navigation links have a minimum 44px target height, 12px icon-to-text gap, and 20px icons. Hover applies canvas background; active/current route applies forest pastel background (`people-forest`) and forest ink (`people-forest-ink`) at weight 600 with `aria-current="page"`.

### Search, Appearance and Profile

Global search triggers via `Ctrl/Cmd+K` or header trigger, opening a keyboard-navigable modal that filters permitted routes in the active workspace. The theme toggle toggles light/dark mode and persists the preference. The profile dropdown displays truncated user names and exposes settings and sign-out actions.

### Authentication Forms

Inputs and primary submit buttons are at least 48px tall. Password fields provide toggleable eye icons with 44px minimum touch targets. Immediate field-level error clearing and clear `<UAlert>` banners provide actionable, recoverable feedback.

### Tables and Lists

Data tables feature 52px desktop body rows (60px on mobile) with clear column headers. List controls include search input with a clear button, debounced remote selection, active filter count badges, and one-click filter reset. Numbered pagination displays at 640px and above, switching to compact Previous/Next on mobile.

### Request Feedback and Dialogs

Network and mutation states display through consistent feedback components: loading skeletons, updating indicators that preserve existing data during background fetch, and error banners with explicit Retry triggers. Dialogs use Nuxt UI modals with 90dvh maximum height and accessible close buttons.

## Do's and Don'ts

### Do:
- Do use implemented CSS variables (`var(--people-*)`, `var(--ui-*)`) for colors and tokens.
- Do keep 44px minimum clickable/tappable touch targets for all interactive controls.
- Do maintain visible keyboard focus outlines (`outline: 2px solid var(--ui-primary)`, `outline-offset: 2px`).
- Do distinguish between initial loading, background updating, empty states, and errors with actionable retry paths.
- Do respect the ERP boundary: HRMS handles operational workflows, while ERP remains authoritative for employee master data.
- Do preserve strict authentication door separation (`/login` for workforce, `/admin/login` for Super Admin).

### Don't:
- Don't hardcode hex colors or introduce arbitrary unscaled colors outside the design system.
- Don't apply heavy decorative shadows or gratuitous motion to operational workspace cards.
- Don't bypass the BFF cookie proxy or expose raw JWT tokens to the client.
- Don't invent unconfirmed workforce metrics, synthetic testimonials, or fake compliance logos.
