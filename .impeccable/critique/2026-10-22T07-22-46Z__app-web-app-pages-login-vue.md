---
target: the login pages
total_score: 28
max_score: 40
na_heuristics: 
p0_count: 0
p1_count: 2
target_identity: "file:D:\\Projects\\people\\app\\web\\app\\pages\\login.vue"
target_fingerprint: "sha256:5fc8c08230cf51419df42d9e3b72c9c649aadc575d6c0c7b211ac95f375fe124"
target_path: "D:\\Projects\\people\\app\\web\\app\\pages\\login.vue"
timestamp: 2026-10-22T07-22-46Z
slug: app-web-app-pages-login-vue
---
Method: dual-agent (A: cc3cf2e7-2dce-4c36-93b0-f00921e09025 · B: 65f44062-2c55-433a-bf40-5be79d28b7d9)

#### Design Health Score

| # | Heuristic | Score | Key Issue |
|---|-----------|:-----:|-----------|
| 1 | Visibility of System Status | 3 | Button shows loading spinner, but HTTP 429 lockout lacks a live countdown timer and MFA lacks progress feedback beyond text. |
| 2 | Match System / Real World | 4 | Natural human labels ("Mobile number or username", "Employee sign-in", "Technical administration"). No technical error leaks. |
| 3 | User Control and Freedom | 3 | MFA challenge offers clear cancellation back to sign-in. Clicking brand logo on `/admin/login` unexpectedly boots admin back to `/login`. |
| 4 | Consistency and Standards | 3 | Standard autocomplete and touch targets. "Forgot your password?" floats ambiguously with 24px margin between password and submit. |
| 5 | Error Prevention | 3 | Preemptive client detection of misplaced `@` email and phone numbers. Autocorrect disabled. Password fields lack Caps Lock detection. |
| 6 | Recognition Rather Than Recall | 2 | No "Remember username" or device memory. Shift employees must recall and re-type their 10-digit mobile number on every mobile session. |
| 7 | Flexibility and Efficiency | 2 | No accelerators for daily high-frequency punch-in rituals: no WebAuthn / Passkeys, no biometric unlock prompt on mobile. |
| 8 | Aesthetic and Minimalist Design | 3 | Restful botanical green and paper neutrals. Error states over-signal with redundant red alerts and cause layout shifts. |
| 9 | Error Recovery | 3 | Plain language error banners with cross-door routing buttons. Bad credentials trigger duplicate error messages across both inputs. |
| 10 | Help and Documentation | 2 | No link to HR support, IT helpdesk, or employee recovery assistance for forgotten usernames or changed phone numbers. |
| **Total** | | **28/40** | **Good (70%)** |

#### Design Specificity Verdict

**LLM assessment**: Grounded and distinctive in its architectural framing, but diluted on mobile and during error states. The calm botanical palette (`--color-brand-700: #1d613a`, `--ui-primary: #287448`, paper canvas `#f7f9f7`, dark canvas `#111a14`) and Newsreader editorial serif (`People Editorial`) give Emploi an unhurried, dignified quality rarely found in enterprise HR tools. The physical "separate doors" model strictly separates everyday workforce operations from technical administration. However, on mobile viewports (<1024px) `.auth-story` is hidden completely, collapsing the interface into a generic auth box for frontline shift employees. Furthermore, the desktop story panel omits the 34ch narrative body defined in `DESIGN.md`.

**Deterministic scan**: The deterministic detector scanned `app/web/app/pages/login.vue` and `app/web/app/pages/admin/login.vue` (exit code `0`, `0` primary findings, `0` advisory findings). No forbidden hardcoded hex colors, arbitrary inline styles, or non-standard font sizes were found. Both files strictly use Nuxt UI v4 primitives and system tokens.

**Visual overlays**: Skipped (`browser_automation_unavailable`). No browser automation or live overlay was injected; static AST and design review performed.

#### Overall Impression

Emploi's sign-in architecture successfully delivers on its promise of "HR made calm" at rest, featuring handsome botanical green tokens, serene paper backgrounds, and clean architectural door separation. However, this calm composure shatters under friction: error states over-signal with chaotic red alerts that push the submit button down, rate limits leave users staring at a static lockout message with no timer, and daily shift workers get zero credential memory on mobile. The single biggest opportunity is transforming authentication from an obstacle course into an effortless, reassuring two-second daily ritual.

#### What's Working

1. **Architecturally Grounded Separate Doors with Smart Cross-Door Routing**: Daily workforce users (`/login`) and technical superadmins (`/admin/login`) have dedicated, purposeful entrances. If a technical admin enters credentials at `/login`, the backend 403 error is intercepted into a clear, actionable bridge button ("Go to technical sign-in"), and vice versa.
2. **Distinctive Botanical Identity & High Accessibility**: Forest green branding and tranquil paper neutrals feel restorative rather than punitive. Meets WCAG AA/AAA contrast ratios (>11:1 on text), enforces strict 44–48px touch targets, and provides prominent 2px focus outlines.
3. **Preemptive Input Sanitization**: Proactively catches common user errors before network submission, warning users who type email addresses on `/login` or phone numbers on `/admin/login`.

#### Priority Issues

- **[P1] Redundant Dual Error Signaling Induces Panic and Layout Shift (CLS)**
  - **Why it matters**: Violates "HR made calm". On failed login, both input borders turn red, two field error messages appear simultaneously, and a red `UAlert` banner is injected above the submit button. This triple alarm creates acute anxiety and pushes the submit button downward.
  - **Fix**: Consolidate error feedback into a single, elegant `UAlert` banner with a stable layout reservation, and highlight input borders neutrally without redundant contradictory field text.
  - **Suggested command**: `$impeccable clarify app/web/app/pages/login.vue`

- **[P1] Static Rate-Limit (429) Lockout Lacks Live Countdown Timer**
  - **Why it matters**: Frontline shift employees rushing to punch in see a static string: *"Too many failed login attempts. Try again in 30 seconds."* Users cannot tell when the lockout expires; tapping prematurely risks resetting or extending the lockout window.
  - **Fix**: Implement a reactive 30-second countdown timer inside the banner (e.g., *"Try again in 22s..."*) that automatically clears the alert and re-enables the submit button at zero.
  - **Suggested command**: `$impeccable harden app/web/app/pages/login.vue`

- **[P2] High Daily Friction: Absence of "Remember Username" or Daily Ritual Accelerators**
  - **Why it matters**: Emploi is used multiple times daily for quick rituals. Forcing employees to type a 10-digit mobile number or employee code every morning on mobile increases friction and typo rates.
  - **Fix**: Introduce an accessible, secure "Remember username" toggle that stores the identity string locally, pre-populates it on return visits, and auto-focuses the password input.
  - **Suggested command**: `$impeccable distill app/web/app/pages/login.vue`

- **[P2] Brand Personality Disappears on Mobile Viewports**
  - **Why it matters**: At `< 1024px`, `.auth-story` is completely hidden (`display: none;`), leaving mobile users with a plain, unbranded form. The majority of workforce employees clock in via mobile devices.
  - **Fix**: Add a compact, warm 1-line brand tagline/motif above the form on mobile viewports, and populate the missing 34ch editorial narrative body in desktop's `.auth-story-copy`.
  - **Suggested command**: `$impeccable typeset app/web/app/layouts/auth.vue`

- **[P3] Admin Door Brand Link Hijacks Technical Context**
  - **Why it matters**: In `AuthBrand.vue`, clicking the Emploi logo always navigates to `/login`, even from `/admin/login`. A Super Admin who clicks the logo to refresh is inadvertently booted out to the workforce portal.
  - **Fix**: Make `<AuthBrand>` aware of the current route; link to `/admin/login` or render as a static badge when already within the `/admin` route tree.
  - **Suggested command**: `$impeccable polish app/web/app/components/AuthBrand.vue`

#### Persona Red Flags

- **Maya (Shift Employee on mobile, rushing to clock in at 7:58 AM)**:
  - Must manually type her full 10-digit mobile number on a cold morning with zero device memory.
  - The calm botanical story is completely stripped on mobile (`display: none`), reducing her app to a cold utility box.
  - A single typo followed by a hurried second attempt triggers a 429 lockout with a static "Try again in 30 seconds" message, leaving her with no countdown before her 8:00 AM tardiness threshold.

- **David (Department Manager on desktop, approving shift requests)**:
  - "Forgot your password?" floats in an awkward 24px vertical gap between the password field and submit button rather than being tucked near the password label.
  - Identity placeholder is ambiguous ("mobile number or username")—he doesn't know whether to enter his corporate email or employee ID until a post-submission error tells him emails are invalid.
  - Zero help escalation: if his account is locked, there is no IT helpdesk link or HR support contact on the page.

- **Alex (Technical Administrator, 2:30 AM emergency outage triage)**:
  - Clicking the top-left Emploi logo on `/admin/login` unexpectedly kicks him back to workforce `/login`.
  - No Caps Lock warning indicator on password input during high-stress credential entry.
  - MFA enrollment displays recovery codes in a plain text grid without a 1-click "Copy all" or "Download TXT" button.

#### Minor Observations

1. **Missing Caps Lock Warning**: Password fields lack an active Caps Lock indicator, leading to preventable failed login attempts.
2. **Formatting Ambiguity on Identity**: Placeholder reads `"Enter mobile number or username"` without indicating format (e.g., with or without country code / hyphens).
3. **Verbose CTA on Admin Page**: The button text `"Sign in to administration"` is unnecessarily verbose on small viewports compared to `"Sign in"`.
4. **Unused CSS Class**: `.auth-brand-maker` is defined in `auth.css` but unused in `AuthBrand.vue`.
5. **Recovery Code Export**: `<AuthMfaChallenge>` displays recovery codes during enrollment but does not offer a 1-click clipboard copy or text download.

#### Questions to Consider

1. **What if workforce authentication embraced the "badge tap" ritual instead of an enterprise form?** Could Emploi support WebAuthn / Passkeys or biometric device unlock on mobile, allowing employees to authenticate in one tap and clock in within two seconds?
2. **Does a credential mismatch ever justify painting both input fields red and adding an alert banner?** What if Emploi embodied true calm by showing a single, graceful banner near the submit button without aggressively coloring both input borders?
3. **What if the rate-limit cooldown was an interactive, calming countdown rather than an anxiety-inducing dead end?** What if the submit button transformed into a subtle radial timer (*"Re-enabling in 24s..."*) that immediately lets the user proceed the instant the cooldown expires?
