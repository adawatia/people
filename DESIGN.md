---
name: People
description: Editorial violet authentication and compact Nuxt UI pages for operational work.
colors:
  color-brand-50: '#f5f3ff'
  color-brand-100: '#ede9fe'
  color-brand-200: '#ddd6fe'
  color-brand-300: '#c4b5fd'
  color-brand-400: '#a78bfa'
  color-brand-500: '#6c4df6'
  color-brand-600: '#6040dc'
  color-brand-700: '#5032bd'
  color-brand-800: '#422b98'
  color-brand-900: '#352473'
  color-brand-950: '#231a46'
  ui-primary: '#5637a5'
  ui-success: '#226747'
  ui-warning: '#805900'
  ui-error: '#a52b46'
  ui-info: '#345a96'
  people-canvas: '#faf8f4'
  people-surface: '#fffdfa'
  people-border: '#ded8e5'
  people-text: '#292335'
  people-muted: '#665e70'
  people-lavender: '#eee7f7'
  people-mint: '#e7f4ed'
  people-peach: '#f9eee4'
  people-blue: '#e8eff9'
  people-yellow: '#fff3d6'
  people-rose: '#fce9ed'
  people-blue-ink: '#345a96'
  people-mint-ink: '#226747'
  people-lavender-ink: '#5637a5'
  people-peach-ink: '#925025'
  people-yellow-ink: '#805900'
  people-rose-ink: '#a52b46'
  dark-ui-primary: '#c9b2ff'
  dark-ui-success: '#94d8b4'
  dark-ui-warning: '#efd184'
  dark-ui-error: '#f2acbd'
  dark-ui-info: '#abc9f5'
  dark-people-canvas: '#1c1923'
  dark-people-surface: '#25202e'
  dark-people-border: '#51465e'
  dark-people-text: '#f7f0e9'
  dark-people-muted: '#beb2ce'
  dark-people-lavender: '#30264b'
  dark-people-mint: '#19362c'
  dark-people-peach: '#382b22'
  dark-people-blue: '#22334e'
  dark-people-yellow: '#3b321c'
  dark-people-rose: '#3e2631'
  dark-people-blue-ink: '#abc9f5'
  dark-people-mint-ink: '#94d8b4'
  dark-people-lavender-ink: '#c4b5fd'
  dark-people-peach-ink: '#ebbb94'
  dark-people-yellow-ink: '#efd184'
  dark-people-rose-ink: '#f2acbd'
  auth-paper: '#faf8f4'
  auth-ink: '#292335'
  auth-muted: '#665e70'
  auth-violet: '#5637a5'
  auth-panel: '#eae3f4'
  auth-line: '#d8d0df'
  dark-auth-paper: '#1c1923'
  dark-auth-ink: '#f7f0e9'
  dark-auth-muted: '#beb2ce'
  dark-auth-violet: '#c9b2ff'
  dark-auth-panel: '#30283f'
  dark-auth-line: '#51465e'
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
    backgroundColor: '{colors.people-lavender}'
    textColor: '{colors.people-lavender-ink}'
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
    backgroundColor: '{colors.people-lavender}'
    textColor: '{colors.people-lavender-ink}'
  platform-sign-out-hover:
    backgroundColor: '{colors.people-surface}'
  people-card:
    backgroundColor: color-mix(in srgb, var(--people-surface) 96%, transparent)
    rounded: '{rounded.card}'
  auth-story:
    backgroundColor: '{colors.auth-panel}'
    textColor: '{colors.auth-violet}'
    rounded: '{rounded.auth-story}'
    padding: clamp(28px, 3vw, 48px)
  auth-input:
    backgroundColor: '{colors.auth-paper}'
  auth-link:
    textColor: '{colors.auth-violet}'
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

# Design System: People

## Overview

**Creative North Star: "Editorial violet, compact operations"**

People™ by Datlabs pairs warm paper and ink with violet selection and primary actions. Authentication retains the user-selected editorial violet direction, generous spacing and Newsreader display typography. The approved platform extension uses a clean, compact navigation frame and familiar system sans for frequent operational work.

This system records the approved frontend extension across every existing page: authentication, shared platform shell, responsive dashboards, lists, forms and Nuxt UI dialogs. Existing routes, APIs, permissions, calculations and actions remain the product boundary; presentation refinements do not add business capabilities. Existing People and Datlabs symbols and Lucide icons supply identity; the authentication HRMS diagram is native UI, with no new raster assets.

**Key Characteristics:**
- Warm paper/ink neutrals with adaptive light and dark appearance.
- Violet current selections and primary actions.
- Editorial authentication; compact operational navigation.
- Existing identity symbols, accessible controls and permission-aware workspaces.

## Colors

The frontmatter is normative and preserves the source CSS values. The `dark-` entries describe dark-mode overrides; the `auth-` entries remain scoped to authentication.

### Primary

Violet (`ui-primary`) marks primary actions and keyboard focus. The platform's selected navigation pairs lavender fill (`people-lavender`) with violet ink (`people-lavender-ink`); dark selection ink intentionally differs from dark primary. The existing `color-brand-50` through `color-brand-950` ramp is available to Nuxt UI.

### Neutral

Warm canvas, elevated paper, ink, muted copy and borders use `people-canvas`, `people-surface`, `people-text`, `people-muted` and `people-border`. Authentication retains its own paper, ink, muted, panel and line aliases instead of inheriting platform surface changes.

### Semantic

Success/mint, warning/yellow, error/rose and information/blue use the paired semantic fill and ink tokens. Peach supplies the existing work-arrangement category tone. These category colors remain available to page components; the shell navigation uses a single violet current-selection treatment.

**The Semantic Appearance Rule.** Read colors through the implemented CSS variables; do not bake light-mode colors into new controls.

## Typography

Authentication uses the locally hosted Newsreader face under `People Editorial` with Georgia/serif fallback. Controls and platform copy use the system sans stack in the frontmatter. Authentication headings are editorial; platform headings are concise operational labels.

Authentication display copy is capped at 10ch and story body at 34ch. The story body uses 16px/1.7; form description uses the auth-body role. Below a desktop height of 851px, the display becomes `clamp(40px, 3.6vw, 56px)` and story body 14px/1.5. Platform selected navigation increases from weight 500 to 600. The controls-only header has no workspace breadcrumb or page title. Its profile name is 13px/600, capped at 160px and truncated. The platform sidebar uses only the existing People symbol; authentication brand is 26px/650 with 16px superscript.

Page and dashboard titles share the page-title role. Table and request-feedback copy use the compact 13px/1.6 roles; table headers use 12px, normal case and no added letter spacing. Dashboard panels use 16px/600 headings, summary labels use 12px/1.5 and summary values use the dashboard-metric role with tabular numerals. Dashboard descriptions use 14px/1.6, capped at 64ch. Detail values use 15px/600; approval titles use 14px/600/1.5. These roles extend the system sans hierarchy without changing authentication typography.

## Layout

At 1024px and above, the fixed desktop sidebar is 256px expanded or 76px collapsed. The body offset follows that width. Sidebar navigation flexes and scrolls independently, leaving branding/workspace above and account actions below. The toggle sits at the far left of the desktop top bar and persists in `people_sidebar_collapsed` (one-year, SameSite lax cookie, initially expanded). The collapsed rail centers 44px navigation targets, hides group labels, retains accessible titles/labels and uses a workspace dropdown. It has no animated width transition. Workspace controls appear only for multiple available workspaces; static workspace titles and descriptions are omitted.

The solid sticky header is at least 72px tall, with 32px horizontal desktop padding. Its right group contains search, notifications, appearance and a profile link; desktop shows avatar/name, mobile avatar only. The sidebar shows the 40px People symbol without a wordmark or maker text. Content is capped at 1536px and padded 32px on desktop. Below 1024px the sidebar is replaced by the 32px brand symbol and four bottom destinations: Home, Workspace, the permitted workspace-specific primary destination, and More. The bottom bar honors safe-area inset; content has 104px bottom padding. Mobile content is otherwise padded 28px vertically and 20px horizontally; below 480px horizontal padding becomes 16px and header padding 12px. A bottom drawer is capped at 80dvh with a scrolling body and pinned sign-out footer in More. At 1280px the desktop search shortcut becomes visible; the desktop bordered search control is at least 180px wide.

Authentication has a shared masthead/footer, a two-column composition at 1024px and above, a story panel and a form capped at 440px within a 1600px outer maximum. Outer padding is `clamp(20px, 4vw, 72px)`. The masthead is at least 88px and footer 64px. Below 1024px the story is hidden, the form leads and the footer wraps/centers. Technical administration uses a centered single-column form without story panel or decorative animation; its heading identifies restricted access without repeated labels. Short desktop heights compact panel/form spacing. Desktop copyright and maker credits remain separate, aligned left and right.

Pages keep records and controls within their content width. Page headings and top-level flex content wrap below 768px. Tables use 52px desktop body rows, 60px rows below 768px, wrapping cell content and bounded horizontal containers. Existing employee, attendance and leave lists provide mobile record views below 768px; do not assume every table has a record alternative. Tab lists can scroll within their bounds. Mobile record links/articles have at least 60px height.

Dashboards use 24px section gaps and grouped summary strips, with two columns initially. At 1024px workforce summaries use four columns and technical/executive summaries three; at 1600px technical summaries use five and executive summaries six. Attendance places its status chart on the left and its four summary values in a two-column grid on the right at 1024px and above; below 1024px the summary leads and the chart follows. Dashboard panels use 24px padding, reduced to 20px below 768px; summary items use 20px, reduced to 16px. Details become two columns at 640px. Main panels become two columns at 1024px, with owner analytics using a 1.45:1 split. Owner filters use two columns with the unit spanning both until 1024px, then three columns in a 1:1:1.3 ratio. The 320px chart has a text data alternative. Comparison tables show at 768px and above, with a 720px minimum table width inside a focusable scrolling container; smaller widths use grouped records with two-column details. Headings and metadata stack/wrap on mobile.

## Elevation & Depth

The custom shell is flat: solid surfaces, 1px borders and tonal selection establish depth. The sidebar and bottom bar use z-index 40, sticky header 30 and focus-revealed skip link 100. No custom shell shadow tokens are defined. Shared page cards and dashboard panels are also flat: solid surface fill, 12px radius and no box shadow; dashboard panels and summary strips use 1px borders. Nuxt UI supplies modal, dropdown and drawer primitives; this document does not redefine their default elevation.

## Shapes

Small controls and navigation use the control radius; cards and icon containers use the card radius. Brand symbols use their own radius; the authentication story has a softer 16px corner. Authentication diagram nodes are 56px circles with a 1px current-color border. Shortcut badges use the smaller radius. Borders delineate workspace, account and header regions without nested navigation cards.

## Components

### Navigation and workspace controls

Navigation rows have 44px minimum height, 12px icon/text gap and 20px icons. Default rows use muted ink; hover uses canvas fill and main ink; current rows use lavender fill/violet ink and weight 600 with `aria-current`. The expanded workspace selector is native, at least 44px high, with a 1px border and trailing chevron. The collapsed rail uses the existing available-workspace dropdown. Mobile highlights both the current direct destination and the currently opened destination group; Workspace remains explicitly labeled. Route changes close drawer and search; changing to desktop closes the mobile drawer.

### Search, appearance and account

Search opens a keyboard-accessible modal from its trigger or Ctrl/Cmd+K, filters existing permitted page labels in the current workspace and opens the first result on Enter. Empty results provide a status message. Search result rows are at least 48px tall. Appearance follows system preference initially, persists the existing appearance cookie and mounts the color-mode button on the client with a reserved 44px placeholder. Its icon and accessible label reflect the resolved theme.

The profile link lives at the right end of the header, has a minimum 44px target and truncates long names. Sign-out has a 1px violet border, lavender fill and violet text/icon in both themes; hover uses the surface color and keyboard focus a 2px primary outline. Sign out is a dedicated labeled desktop action; it becomes a titled/accessible icon in the rail. Mobile More pins a 48px sign-out action in its footer. During sign-out the button shows loading and disables duplicate submission; failure announces an error toast and permits retry. Existing account/settings distinctions and permission filtering remain intact.

### Authentication fields and links

Authentication inputs and submit buttons are at least 48px tall. Password visibility and other non-submit controls have 44px minimum targets; password fields reserve 56px trailing padding. Links have 44px minimum height and underline on hover. Forms retain keyboard submission, pending/error states, password visibility and accessible announcements. Current MFA/recovery steps use violet and weight 600.

### Cards and native diagram

The existing people-card uses a 1px border, card radius and 96% surface color mix. The authentication diagram connects Attendance, Time off and Schedules through existing Lucide icons. With motion permitted, its connecting line draws over 1.8s using `cubic-bezier(.16, 1, .3, 1)`; 1.2s pulses start at 0s, .6s and 1.2s, ending within 2.4s. Reduced-motion users see a static diagram. Platform navigation/profile/sign-out color transitions use 160ms ease-out only when reduced motion is not requested.

### Page controls, filters and pagination

Use Nuxt UI buttons, inputs, selects and select menus with the configured 44px minimum control height. Shared page rules preserve 44px buttons, links used as controls, comboboxes and tabs; checkbox/radio native input geometry is exempt. Textareas have a 96px minimum. Keyboard controls keep the primary focus outline and 100px scroll margin to remain visible under the shell header.

List controls group a labeled Search field with optional filters and sorting. Search provides a 44px clear action only when populated, empties its model and restores input focus. An active-filter badge and Reset filters appear when filters are active; resetting emits the existing page clear action and closes advanced filters. Below 768px, advanced filters toggle through Filters/Hide with expanded state and controlled-panel ID; at 768px they remain visible in an auto-fit grid of at least 10rem columns. Controls use 16px internal padding, increasing to 20px at 640px. Remote selects retain their searchable paged Nuxt UI menu, 300ms search debounce, selected option label and option-error Retry. Clear is opt-in via `clearable`, appears only for nonzero selection and resets to zero; required selectors do not acquire blanket clearability.

Pagination announces the shown range, presents numbered Nuxt UI pagination at 640px and above and Previous/Page/Next below it. Loading disables paging and page-size controls; boundary buttons are disabled. The existing row-size options are 10, 25, 50 and 100, and changing size returns to page one.

### Request feedback and dialogs

The shared feedback component announces initial Loading results, Updating results with previous results visible, or last-successful-update data after refresh failure using a polite status region. Views retain successful data during refresh where integrated; the shared retained-data helper resets its remembered value on account, workspace or route-path changes. Error alerts retain explicit Retry and empty states remain distinct from unavailable data. Dashboard summaries show skeleton values only during initial pending/unavailable states; unavailable values use an em dash. Owner analytics retain the last successful response, report its stale status on error, validate date filters and expose refresh/reset actions; exception requests keep separate loading/error/empty states.

Use the existing Nuxt UI modal and drawer primitives. Global content is capped at 90dvh with scrolling bodies and modal close targets at least 44px square; specific shell drawers retain their 80dvh override, and owner exception bodies cap at 70dvh. Existing workflow dialogs preserve titles, descriptions, validation and business actions; owner exception dismissal restores its trigger focus. Do not turn these presentation patterns into new backend or workflow behavior.

**The Keyboard Visibility Rule.** Keep the 2px primary outline with 3px offset; retain the focus-revealed skip link. Search result rows retain their local 2px offset.

### Period and account support controls

Attendance and overtime can reset their selected period to the existing current-month default. Overtime and attendance charts use the same light/dark semantic ink colors as their status labels and remain static under reduced motion. Technical account support retains explicit Search submission; clearing search removes the submitted term while Reset filters restores the existing sorting defaults. Successful account rows remain visible during failed updates. Support dialogs use Nuxt UI structure, password visibility, inline request failures and disabled pending actions. Notifications expose a pending state for Mark all read and prevent duplicate actions.


### Dashboard patterns across pages

Attendance and overtime reuse the dashboard summary component, including their existing explanatory notes. Leave balances share a single divided surface while keeping allocations, usage, pending days and balance indicators. Page tabs use compact lavender selections and visible pressed states. Filters use quieter violet accents, tables use warm surfaces and row hover feedback, and notification unread rows use the same lavender selection tone. Employee details omit the empty decorative banner. Existing page features and semantic status meanings remain intact.

### Resilient operational states

Filtered empty states offer Reset filters and return focus to the page search field. Clearing optional selections returns focus to their trigger. Operational inputs and dialog fields use 16px text on mobile; wrapping names and forced-color focus outlines remain readable. Summary numbers use grouped Indian-locale formatting without changing calculations, and chart tooltips stay inside their chart. Security settings distinguish status loading and failure, expose retry, retain loaded sessions, show inline credential errors and block duplicate or competing requests. The project uses 44px controls and visible, unobscured focus as design conventions; conformance still requires verification.

Reference guidance: [WCAG target sizing](https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum.html) and [focus visibility](https://www.w3.org/WAI/WCAG22/Understanding/focus-not-obscured-minimum.html).

## Do's and Don'ts

### Do:
- Do use the existing Nuxt UI primitives and shared page patterns across existing pages.
- Do distinguish pending, empty, unavailable and stale results and preserve visible recovery actions.
- Do retain People™ by Datlabs and the supplied light/dark symbols.
- Do use semantic tokens so light and dark modes stay coherent.
- Do preserve the 44px shell controls, visible keyboard focus and independently scrolling navigation.
- Do retain accessible labels and titles when the desktop sidebar becomes an icon rail.
- Do preserve existing routes, workspace permissions, MFA, recovery and forced-password-change flows.

### Don't:
- Don't manufacture dashboard values, erase successful results during a supported refresh, or change ERP ownership boundaries.
- Don't apply the authentication display composition to the platform shell.
- Don't invent role choices, SSO, registration, session-persistence options, support/legal destinations or certification claims.
- Don't use hidden navigation as an authorization boundary; endpoints retain permission and row-scope enforcement.
- Don't introduce decorative platform motion or new raster identity assets.
