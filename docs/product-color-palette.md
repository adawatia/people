# People color palette

A restrained business palette for daily HR work: People violet for action and selection, slate for reading and structure, and distinct status colors. The existing logo remains the brand reference. This is a color refinement; layouts and workflows retain their current behavior.

| Role | Light | Dark | Usage |
|---|---|---|---|
| Primary violet | `#5032BD` | `#C4B5FD` | Actions, active navigation, focus |
| Canvas | `#F7F8FA` | `#111722` | Workspace background |
| Surface | `#FFFFFF` | `#192231` | Panels and menus |
| Text | `#202939` | `#EDF1F7` | Main content |
| Muted text | `#596579` | `#ACB8CA` | Supporting content |
| Border | `#D8DEE7` | `#344155` | Dividers and panel boundaries |
| Success | `#226747` | `#94D8B4` | Approved, active, complete |
| Warning | `#805900` | `#EFD184` | Pending, attention required |
| Error | `#A52B46` | `#F2ACBD` | Rejected, failed, destructive |
| Information | `#345A96` | `#ABC9F5` | Informational messages |

## Application

Nuxt UI primary uses the custom `brand` ramp in `main.css`, anchored to the existing logo violet `#6C4DF6`. Semantic foregrounds are explicitly composed for each theme. Existing `people-icon` utilities receive paired pale surfaces and readable inks; the legacy lavender utility now matches the violet brand. Keep decorative icon tiles subordinate to action colors. Retain labels and icons alongside status colors.

Use Nuxt UI semantic colors for controls and status messages, and the existing People tokens for icon tiles and surfaces. Do not use a pale tile background as text. Borders are separators, not the sole indicator of an interactive control. Existing chart category colors remain separately defined.

## Contrast verification

Calculated WCAG relative luminance for opaque token pairs; all listed body and icon pairs exceed 4.5:1. White on light primary is 8.29:1; dark solid-button foreground (`#111722`) on dark primary is 9.73:1.

| Theme | Pair | Contrast |
|---|---|---|
| Light | text / canvas | 13.75:1 |
| Light | muted / surface | 5.90:1 |
| Light | lavender-ink / lavender | 6.99:1 |
| Light | blue-ink / blue | 5.95:1 |
| Light | mint-ink / mint | 5.99:1 |
| Light | peach-ink / peach | 5.41:1 |
| Light | yellow-ink / yellow | 5.69:1 |
| Light | rose-ink / rose | 5.94:1 |
| Dark | text / canvas | 15.84:1 |
| Dark | muted / surface | 7.96:1 |
| Dark | lavender-ink / lavender | 7.56:1 |
| Dark | blue-ink / blue | 7.51:1 |
| Dark | mint-ink / mint | 7.94:1 |
| Dark | peach-ink / peach | 7.85:1 |
| Dark | yellow-ink / yellow | 8.51:1 |
| Dark | rose-ink / rose | 7.48:1 |
