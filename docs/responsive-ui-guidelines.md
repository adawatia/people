# Responsive UI Guidelines: Desktop & Mobile UX System

This document outlines the responsive design rules, layout mechanics, and component conventions for our HRMS application built with **Nuxt 4 + Nuxt UI (v4.10)** and **Tailwind CSS v4**.

---

## 1. Core Philosophy: Dual-Intent Responsive UX

We do **not** simply shrink desktop layouts down to fit phone screens. 

* **Desktop Layouts ($\ge 1024\text{px}$)**:
  * **Intent**: High productivity, administrative efficiency, batch actions, deep auditability.
  * **Mechanics**: Persistent collapsible sidebar, multi-column forms (2–3 columns), dense data tables (`UTable`) with sortable headers, inline filter toolbars, dual-action header toolbars (`#navbar-title` and `#navbar-actions` teleports).
* **Tablet Layouts ($640\text{px} - 1024\text{px}$)**:
  * **Intent**: Flexible oversight, hybrid touch/trackpad navigation.
  * **Mechanics**: Collapsible slide-over drawer, 2-column forms, controlled horizontal scrolling on complex matrices, touch-friendly filter bars.
* **Mobile Layouts ($< 640\text{px}$)**:
  * **Intent**: Speed, focus, one-handed thumb interaction, zero clutter.
  * **Mechanics**: Compact header, bottom navigation bar (`MobileBottomNav.vue`), swipe-to-dismiss bottom sheets (`MobileBottomSheetMenu.vue`), single-column forms, **card-based list representations instead of wide tables**, sticky thumb-friendly action bars.

---

## 2. Breakpoints & Grid Matrix

| Viewport | Tailwind Breakpoint | Container Width | Primary Navigation | Table Strategy | Form Strategy | Filter Strategy |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Mobile** | `< 640px` (default) | `w-full px-3 sm:px-4` | Bottom Nav + Slide Sheet | **Touch Cards (`md:hidden`)** | Single Column (`space-y-4`) | Collapsible Drawer / Modal |
| **Tablet** | `640px - 1023px` (`sm`, `md`) | `w-full px-6` | Slide-over Sidebar | Scrollable Table or Cards | 2 Columns (`grid-cols-2`) | Horizontal Wrap Toolbar |
| **Desktop** | $\ge 1024px$ (`lg`, `xl`) | `max-w-7xl mx-auto px-8` | Persistent Sidebar | **Full Dense Table (`hidden md:block`)** | 2 to 3 Columns | Inline Multi-Filter Bar |

---

## 3. Touch Targets & Typography Rules

### A. Touch Targets (Mobile WCAG AA+)
* All clickable elements (buttons, inputs, menu triggers, switches) on mobile viewports must meet a **minimum touch target of $44\text{px} \times 44\text{px}$** (`min-h-[44px]` or `min-h-[48px]`).
* Never use tiny icon buttons (`size="xs"`, $20\text{px}-28\text{px}$) without labels on mobile. Group secondary actions inside a touch-friendly kebab menu (`⋮`) or expandable action sheet.

### B. Form Inputs on Mobile (iOS Safari Zoom Prevention)
* Inputs, selects, and textareas must maintain a font size of at least `16px` (`text-base sm:text-sm`) on mobile devices. Font sizes below 16px cause iOS Safari to auto-zoom the entire screen, breaking layout stability.

### C. Color & Contrast Rules (Soft UI Evolution)
* In light mode, **never use base pastel colors directly as body or label text**. Always use the `.ink` token variant:
  * Base Blue: `#87CEEB` (surfaces, focus rings) $\rightarrow$ Ink Blue: `#0B5F82` (text/icons, 5.1:1 on white).
  * Base Pink: `#FFB6C1` $\rightarrow$ Ink Pink: `#A13355` (text/badges, 4.9:1 on white).
  * Base Green: `#90EE90` $\rightarrow$ Ink Green: `#1F7A2E` (text/badges, 4.6:1 on white).
* Status badges must always display explicit text labels alongside colors (`Present`, `Absent`, `Pending`, `Approved`), never relying on color alone.

---

## 4. Component Implementation Pattern: Dual Presentation

Every major data-driven module (Employees, Attendance, Leaves, Shifts, Approvals) follows the **Single Data Source, Dual Presentation Pattern**:

```text
┌───────────────────────────────────────────────────────┐
│ Page State / Composable (e.g. useLeave(), useShifts())│
└──────────────────────────┬────────────────────────────┘
                           │
             ┌─────────────┴─────────────┐
             ▼                           ▼
    ┌─────────────────┐         ┌─────────────────┐
    │ Desktop View    │         │ Mobile View     │
    │ (hidden md:block│         │ (md:hidden)     │
    │  UTable Matrix) │         │  Cards List)    │
    └─────────────────┘         └─────────────────┘
```

### Example: Responsive Leaves Presentation
```vue
<!-- Desktop Table View -->
<div class="hidden md:block rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 overflow-hidden shadow-xs">
  <UTable :data="applications" :columns="columns" :loading="isLoading" />
</div>

<!-- Mobile Cards View -->
<div class="md:hidden space-y-3">
  <LeaveMobileCard
    v-for="app in applications"
    :key="app.id"
    :application="app"
    :can-approve="canApprove"
    @approve="handleApprove(app.id)"
    @reject="handleOpenReject(app)"
  />
</div>
```

---

## 5. Sticky Action Bars on Mobile

For long multi-section forms (e.g., `/employees/create`) and critical approval flows:
* On desktop, primary and secondary actions remain in the header toolbar (`#navbar-actions`) or at the bottom of the card.
* On mobile, actions should stick to the bottom of the viewport above the mobile nav clearance:
```vue
<div class="fixed bottom-0 inset-x-0 z-20 lg:hidden p-3 bg-white/95 dark:bg-slate-900/95 backdrop-blur-md border-t border-slate-200 dark:border-slate-800 flex items-center gap-3">
  <UButton label="Cancel" variant="ghost" color="neutral" class="flex-1 min-h-[48px]" to="/employees" />
  <UButton label="Save Employee" color="primary" class="flex-1 min-h-[48px]" type="submit" />
</div>
```

---

## 6. Testing Checklist for Responsive Quality

Before considering any page complete, verify:
- [ ] **Viewport 375px (iPhone SE / Mini)**: No horizontal scrolling, no overflowing badges, touch targets $\ge 44\text{px}$.
- [ ] **Viewport 390px / 414px (iPhone 14/15 Pro, Android Standard)**: Smooth card spacing, legible headers.
- [ ] **Viewport 768px (iPad Mini / Portrait)**: Proper drawer transitions, 2-column grids.
- [ ] **Viewport 1280px / 1440px / 1920px (Desktop)**: High information density, sidebar collapsible, centered `max-w-7xl` container.
- [ ] **Modal Responsiveness**: Modals on mobile fit within viewport without dual-scrollbar trapping.
