# UI/UX design system

## Direction
A restrained professional operations tool for lab staff. Optimize for scanability, useful tables, clear status, and quick workflows. Avoid generic AI-generated dashboard styling: no decorative gradients/blobs, glassmorphism, glowing borders, giant hero art, or meaningless charts.

## Tokens
- Background `#F8FAFC`
- Surface `#FFFFFF`
- Foreground `#0F172A`
- Muted text `#64748B`
- Border `#E2E8F0`
- Primary navy `#0A192F`
- Accent orange `#F97316` (sparingly)
- Success `#15803D`
- Warning `#B45309`
- Danger `#B91C1C`
- Info `#0369A1`
Use CSS variables. Check contrast. Never communicate status by color alone.

## Typography
Use Inter or system sans-serif. Prefer a locally available/bundled font if the deployment may be offline.
- Page title 24–30px, weight 600.
- Section title 15–18px, weight 600.
- Body 14–15px, line-height 1.45–1.6.
- Table 13–14px.
- Metadata 12–13px but readable.
Use tabular numerals for metric values. Limit font sizes and all-caps labels.

## Layout
- Desktop content max width around 1440px.
- Sidebar 224–248px; collapsible on smaller screens.
- Top bar 56–64px.
- 4px spacing base; common gaps 8/12/16/20/24/32px.
- Page padding 24px desktop, 16px mobile.
- Subtle 1px borders; shadows rare; radius 8–10px.
- Don't use a card for every field.

## Navigation
Overview, Devices, Alerts, Incidents, Reports, Settings (admin only). Compact icon+label sidebar with active state. Use Lucide consistently, not emoji.

## Overview
Header with title, last refresh, refresh action. Four compact summaries: Reporting, Delayed, Not reporting, Open alerts. Then actionable device table and recent alerts. Do not let decorative charts displace the table.

## Device list/detail
Search hostname/display name; filter lab/status/active; server-side pagination; deterministic sort. Device detail shows lab, status, platform, last seen, CPU/RAM/disk, bounded history charts, recent alerts/incidents. Never imply history exists if there are no samples.

## States and interaction
Every page needs loading, empty, error, populated, and filtered-empty states. Keep prior data visible during background refresh when sensible. Debounce search and ignore stale responses. Use field-level validation, keyboard support, visible focus, accessible labels, and clear action feedback. Confirm consequential changes.

## Responsive
Test 1440px, 1024px, 390px. Collapse sidebar; make tables scroll or become a concise list; filters wrap or move to a drawer; charts must not clip. Keep status and critical alerts visible.

## Done checklist
API-backed values or visibly labelled demo data; keyboard-only flow; readable contrast; no dead buttons; no unused charts/decorations; loading/empty/error states; responsive layout.
