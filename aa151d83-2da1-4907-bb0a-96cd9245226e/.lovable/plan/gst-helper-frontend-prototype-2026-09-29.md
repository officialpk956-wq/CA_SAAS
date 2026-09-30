# GST Helper frontend prototype

## Goal
Build a dense, fully clickable monthly GST work console using only synthetic local data and in-memory React state. The visual direction combines a ruled paper ledger with a split-flap departures board, across light and dark themes.

## What will be built
- A shared responsive shell with leather-spine navigation, mobile drawer, top period control, theme control, and the demo-data notice on every screen.
- Eight working views: Board, Clients, Client workspace, Reconciliation, Sales, Tax Worksheet, Categories, and History & Audit.
- The Board will include animated status tiles, needs-attention ticket stubs, delayed notices, and a simulated status update.
- Workspace and review screens will include mock uploads, validation expansion, commit acknowledgement, reconciliation runs, searchable/filterable tables, and evidence/detail drawers.
- The Tax Worksheet will implement the five requested stages, claim rules, note-gated actions, adjustments and voiding, live figures, draft snapshots, approval/reopen/filed stamp states, and draft history.
- Category decisions, client mappings, sales review states, and audit filters will all update locally and remain clickable during the session.

## Visual system
- Add the six requested Google font families and assign them by job: display, interface, figures, labels, board, stamp, and handwritten notes.
- Define semantic paper, ink, brass, ledger-line, margin-red, and status tokens for Day Ledger and Night Ledger.
- Add subtle paper grain, ruled ledger surfaces, receipt tears, folder tabs, ticket perforations, focus styles, responsive overflow, and reduced-motion fallbacks.

## Technical details
- Place every business record and seed value in `src/mock/data.ts`; components will not contain business mock literals.
- Keep reusable presentation pieces under `src/components/gst/`, with the route acting as the local state coordinator.
- Use existing shadcn controls and icons; no services, persistence, authentication, or network requests.
- Keep the requested screens inside the console as local views so interactions remain immediate and frontend-only.
- Add app-specific metadata, record the frontend-only architecture decision, and verify the main flows at desktop and phone sizes.

## Assumptions
- “Period workspace” opens from a client card and is represented as a first-class console view, while the seven named sidebar items remain unchanged.
- File selection and drag/drop are simulated previews; selected files never leave the browser.
- Export produces a local text-based demo workbook download rather than a filing-ready spreadsheet.
