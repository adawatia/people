# UI Responsive Audit: Desktop & Mobile UX Analysis

This document audits the responsive behavior of our Nuxt.js + Nuxt UI HRMS frontend (`apps/web`), comparing current desktop and mobile interactions against **Frappe HR (`hrms-16.18.1`)** as our primary UX reference and the **Soft UI Evolution** design system tokens (`design.md`).

---

## 1. Executive Summary & Tech Stack Audit

* **Nuxt Version**: `^4.5.2`
* **Nuxt UI Version**: `^4.10.0`
* **CSS Framework**: Tailwind CSS `^4.3.3` with CSS theme variables (`--ui-text-highlighted`, `--ui-text-muted`, soft neumorphic box shadows).
* **Breakpoints Strategy**:
  * **Mobile**: `< 640px` (`sm`) — Single-column, thumb-zone actions, touch targets $\ge 44\text{px}\times 44\text{px}$, bottom sheets, cards instead of wide tables.
  * **Tablet**: `640px – 1024px` (`sm` to `lg`) — Hybrid 2-column forms, scrollable tables, collapsible navigation drawer.
  * **Desktop**: $\ge 1024px$ (`lg`) — Persistent collapsible sidebar, multi-column forms, high-density data tables, inline filter bars, dual-action header toolbars.

---

## 2. Component & Screen Level Audit Table

| Component / Screen | Current Behavior | Desktop Problem | Mobile Problem | Frappe HR Reference | Recommended Change |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Global App Layout (`default.vue`)** | `UDashboardGroup` + `UDashboardSidebar` + `MobileBottomNav` + `MobileBottomSheetMenu`. | Excessive bottom spacer on desktop if not carefully guarded; sidebar icon mode tooltip positioning. | Sidebar takes over screen if opened; bottom navigation has 5 items including Profile and Menu, but lacks direct employee self-service shortcuts (Attendance, Leaves). | Frappe Desk uses a persistent left workspace sidebar on desktop; on mobile, it transitions to a top-left hamburger opening a full-height off-canvas drawer (`standard_navbar.html`). | Refine `MobileBottomNav.vue` for the top 5 daily worker workflows (`Home`, `Attendance`, `Leaves`, `Shifts`, `Menu`); open `MobileBottomSheetMenu` for secondary admin links. Maintain calibrated bottom spacer (`h-20 lg:hidden`). |
| **Leave Management (`leaves/index.vue`)** | High-density page with `LeaveBalanceCards`, horizontal filter grid (`grid-cols-4`), and full `UTable`. | Good information density; actions are right-aligned. | **No mobile card view!** Renders a 6-column `UTable` that overflows or gets severely squeezed on `< 640px`. Filter inputs take up over 350px of vertical height before any data is visible. | Frappe HR Mobile app shows quota chips/pills at the top, a floating "Apply Leave" action, and a vertical list of application cards with direct status pills (`Pending`, `Approved`). | 1. Implement dual-view pattern: `hidden md:block` for `UTable` and `md:hidden` for `LeaveMobileCard.vue`.<br>2. Collapse filters into an accordion or filter drawer button (`UButton icon="i-lucide-filter"`) on mobile.<br>3. Stacked/Thumb-friendly approve/reject buttons ($\ge 44\text{px}$) for supervisors. |
| **Shift Management (`shifts/index.vue`)** | Master table with 7 columns (`Working Hours`, `Grace & Margins`, `Auto Attendance`, etc.). | High information density, easy management on desktop. | **No mobile representation!** Renders a 7-column `UTable` requiring horizontal scroll; grace margin details wrap awkwardly. | Frappe `Shift Type` list on mobile shows Shift Name, Time Range (`09:00 - 18:00`), Day/Night badge, and active status switch in a compact card. | 1. Add `ShiftMobileCard.vue` (`md:hidden`) showing shift code, time range, overnight badge, and 1-tap "Assign" button.<br>2. Hide raw minutes on mobile cards behind an expandable "Details" tap. |
| **Attendance Management (`attendance/index.vue`)** | `CheckinWidget` on top followed by 8-column `UTable` (`Date`, `Employee`, `Punch In`, `Punch Out`, `Worked`, `OT`, `Status`, `Actions`). | Excellent layout for HR admins to inspect multiple workers. | Renders full 8-column table on phones. Workers checking their own attendance have to pan horizontally to see their Worked Hours and Status. | Frappe HR mobile punch view displays live digital clock, prominent Punch IN/OUT pill buttons, and a clean chronological list of day cards (`Date | In - Out | Total Hrs | Status`). | 1. Implement `AttendanceMobileCard.vue` showing Date, Shift In/Out times, Worked Hours, and Status badge.<br>2. Keep `CheckinWidget` sticky or top-prominent with full-width thumb-friendly buttons (`min-h-[48px]`). |
| **Punch Regularisations (`attendance/corrections.vue`)** | Table with Request ID, Record ID, Requested In, Requested Out, Reason, Status, Approve/Reject. | Clean administrative desk view. | Actions (Approve/Reject) in a table column are tiny (`size="xs"`) and difficult to tap on mobile touchscreens without misclicking. | Frappe HR approval queue shows request cards with employee name, missed punch timestamp, reason text, and large full-width or side-by-side action buttons (`Reject` \| `Approve`). | 1. Render `CorrectionMobileCard.vue` with dedicated supervisor approval bar.<br>2. Touch targets $\ge 44\text{px}$ with confirmation prompts. |
| **Employee Directory (`employees/index.vue`)** | Dual-view already implemented (`md:hidden` Cards, `hidden md:block` Table). | Clean, responsive filter bar. | Filter bar has 5 select inputs that stack into a massive vertical block on small screens, pushing all cards below the fold. | Frappe HR uses a search bar with a "Filters" toggle button that pops out a modal/drawer. | Convert the 5 inline filters on mobile into a collapsible filter sheet or popover, keeping only the search input visible by default. |
| **Employee Onboarding Form (`employees/create.vue`)** | 3 large `UCard` sections with `grid-cols-1 sm:grid-cols-2 md:grid-cols-3`. | Efficient use of space on widescreen monitors. | Bottom submit buttons (`Cancel`, `Create Employee Record`) are scrolled all the way to the bottom and can be missed on long mobile pages. | Frappe DocType forms on mobile maintain a sticky bottom action bar or top-right save button. | Introduce a sticky bottom action bar on mobile viewports (`sticky bottom-0 bg-white/95 backdrop-blur`) so the primary action "Save" is always within thumb reach. |
| **Modal Dialogs (`LeaveApplicationModal`, `ShiftFormModal`, `AttendanceProcessModal`)** | Centered `UModal` with default widths. | Clean floating modal with backdrop blur. | On small mobile viewports (`< 400px`), centered modals can feel cramped or cause double scrollbars (modal body vs page body). | Frappe HR opens complex forms as full-screen drawers or bottom sheets on mobile. | Ensure `UModal` handles mobile fluidly (`w-full sm:max-w-lg m-0 sm:m-auto rounded-b-none sm:rounded-2xl`) or acts as a bottom sheet. |

---

## 3. Frappe HR Responsive Interaction Patterns

Studying `hrms-16.18.1`:
1. **Adaptive Navigation**:
   * Desktop: Permanent tree sidebar + top breadcrumb bar + page action buttons (`New`, `Save`, `Actions`).
   * Mobile: Persistent compact navbar with hamburger menu $\rightarrow$ sliding drawer.
2. **List vs Card Inversion**:
   * Desktop: Multi-column grid with configurable column widths and inline sorting.
   * Mobile: Single-column cards prioritizing:
     * **Title** (Employee Name / Request Subject)
     * **Key Metric** (Dates, Shift, Hours, or Balance)
     * **Status Badge** (Top-right pill)
     * **Primary Action** (Bottom right)
3. **Approval Velocity**:
   * Frappe HR mobile focuses heavily on manager approval velocity: a manager can swipe or 1-tap Approve/Reject directly from the list card without entering the detail view.
4. **Form Sections**:
   * Desktop forms use 2-column or 3-column field grids.
   * Mobile forms strictly collapse to a single column with minimum input heights of 44px–48px (preventing iOS auto-zoom by maintaining $\ge 16\text{px}$ font sizes).

---

## 4. Prioritized Action Plan

1. **Phase 1: Navigation & Mobile Bottom Bar Refinement**
   * Align `MobileBottomNav.vue` with core employee workflows (`Dashboard`, `Attendance`, `Leaves`, `Shifts`, `Menu`).
2. **Phase 2: Common Mobile Card & Filter Primitives**
   * Build `ResponsiveFilterDrawer.vue` to hide massive multi-select rows behind a compact filter button on `< 768px`.
   * Ensure `CommonStatusBadge` and `ConfirmDialog` adhere to touch-safe targets ($\ge 44\text{px}$).
3. **Phase 3: Module-Specific Mobile Card Implementations**
   * **Leaves (`/leaves`)**: Add `LeaveMobileCard.vue` and mobile-friendly balance carousel.
   * **Attendance (`/attendance`)**: Add `AttendanceMobileCard.vue` and touch-optimized punch widgets.
   * **Corrections (`/attendance/corrections`)**: Mobile approval card with 1-touch Approve/Reject.
   * **Shifts (`/shifts`)**: Add `ShiftMobileCard.vue` with quick assign triggers.
4. **Phase 4: Mobile Sticky Form Actions**
   * Add sticky thumb-friendly action bars to `/employees/create`, `/leaves/apply`, and `/shifts/assignments`.
