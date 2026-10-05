# GST Helper — local synthetic GST demo (formerly GST Copilot)

Working directory: `I:\Ca automation`.

## Current capabilities
Create clients/periods; upload and preview CSV records; acknowledge invalid rows with a note; select committed versions; reconcile; inspect source evidence and differences; save/reopen review decisions; export an eight-sheet Excel workbook. Data and results persist in PostgreSQL. This is a local demo, not tax advice or a filing system.

## Prerequisites
Python (verified with 3.14), Node/npm (Next.js 16.3.5 lockfile), and PostgreSQL reachable on localhost:5432. This environment used PostgreSQL in WSL. No Docker dependency is required if PostgreSQL is already available.

Install Python dependencies in your project virtual environment with `python -m pip install -r requirements.txt`. In `frontend`, run `npm ci`. Actual credentials belong in `.env`, never documentation. The example credentials are local demo defaults only.

## Database setup
Create three separate databases using your PostgreSQL administrator: `gst_copilot_dev`, `gst_copilot_test`, and `gst_copilot_e2e_test`. SQL, run outside a transaction and only when the database does not already exist:

```sql
CREATE DATABASE gst_copilot_dev;
CREATE DATABASE gst_copilot_test;
CREATE DATABASE gst_copilot_e2e_test;
```

From the project root in PowerShell:

```powershell
$env:DATABASE_URL='postgresql+asyncpg://postgres:postgres@localhost:5432/gst_copilot_dev'
python -m alembic upgrade head
python backend/gst_copilot/cli/seed.py
python -m uvicorn backend.gst_copilot.api.main:app --host 127.0.0.1 --port 8000
```

Apply migrations through `c4b001` before running the updated API. Seeding is explicit and idempotent. The demo identity resolves the `admin@demo.com` user on the server; it is not production authentication. Do not expose this API publicly.

In a second PowerShell terminal, from `frontend`:

```powershell
$env:NEXT_PUBLIC_API_URL='http://127.0.0.1:8000'
npm run dev -- --hostname 127.0.0.1 --port 3000
```

Open http://127.0.0.1:3000. API documentation: http://127.0.0.1:8000/docs. Restart an older API process after migration; do not run two services on the same port.

## Demo journey
1. Create a fictional client and a DEMO registration reference; create period 2026-08.
2. Upload `sample_data/v1/purchase_register.csv` and `sample_data/v1/gstr2b_demo.csv`.
3. Expand source-row previews. Acknowledge invalid rows, enter a note, and commit each import.
4. Select both committed versions explicitly and run reconciliation.
5. Verify 7 matched pairs, 25 result groups, and 40 accounted source rows for these fixtures.
6. Filter findings; inspect duplicate, invalid, and mismatch evidence. Record a decision and reopen it without erasing history.
7. Refresh the page, then export the workbook. Narrow screens use a horizontally scrollable results table.

## Verification
From the root:

```powershell
python -m pytest tests/ -q
python -m backend.gst_copilot.cli --help
```

Integration tests reset only the explicitly guarded `gst_copilot_test` schema. Never point them at a development or real database. From `frontend`:

```powershell
npm run lint
npx tsc --noEmit
npm run build
npx playwright test
```

The Playwright config starts its own real API on 8002 and frontend on 3100, using only `gst_copilot_e2e_test`. It migrates and seeds but never resets that database. Each journey creates a fresh synthetic client. Ensure both ports are free and install Chromium with `npx playwright install chromium` if needed. Browser screenshots/workbook/trace outputs are in `frontend/test-results`; they are not source files. Build and browser tests should run sequentially because they share `.next`.

## Data and limits
Original uploads are private under `storage/` (or STORAGE_DIR); E2E uploads use `storage/e2e`. Exports stream from memory. CSV upload limit: 5 MiB and 10,000 rows. Amounts must have two decimal places and at most 12 integer digits to fit the database without rounding. Dates must be YYYY-MM-DD. Reconciliation results and original rows remain immutable; review events are separate. Excel source text is protected against formula execution; amounts are serialized as text to preserve precision.

## Remaining boundaries
No trained SLM, real GST-export compatibility, external CA validation, live filing, production authentication, set-off/cash-payable calculation, or period closing. Periods are always open in this demo; Phase 5A adds draft approval snapshots (below). Result filtering/paging is currently client-side over the bounded run; import rows are paged by the API. Demo suppliers come from the documented synthetic supplier file. Concurrency hardening, deployment recovery/backups, and production-scale performance remain separate work. This workspace currently has no Git repository; no commit claims are made.

## Project documents
- [Rules](AGENTS.md)
- [PRD](Mind/PRD.md)
- [Roadmap](Mind/roadmap.md)
- [Current state](memory/current-state.md)
- [Change log](memory/change-log.md)
- [Recovery report](doc/phase-reports/2026-09-14-phase3b-recovery-v2.md)

## Purchase category review (Phase 4A)
After committing a purchase import, select its version in the workspace and open **Review purchase categories**. Review a valid row, request a suggestion, and accept/reject it with a note or choose a category manually. Optionally approve a reusable mapping for the exact supplier and description, starting from an explicit invoice date. Mappings belong to that client only and can be deactivated. Historical decisions remain visible after refresh. Rejected suggestions preserve the last approved category.

The mock deliberately abstains on the original Scenario descriptions. It is not a trained SLM. Every mapping suggestion still requires review. Categories have no effect on reconciliation amounts, GST rates, or ITC eligibility. Category decisions are visible in their own screen/API and are not included in the existing reconciliation workbook. Sales preparation is implemented in Phase 4B; real model inference remains future work.

[Teammate adapter contract](doc/2026-09-14-slm-category-contract-v1.md) · [Phase 4A plan](doc/plans/2026-09-14-phase4a-categorization-v1.md)


## Sales preparation (Phase 4B)
Open a period workspace and choose **Sales preparation**. Download the header template or upload [the synthetic sales sample](sample_data/sales_v1/sales_register.csv). This is a separate demo format; it is not a portal export or a filing return.

1. Upload and inspect every source row, including validation issues. The sample has 19 rows: 5 ready, 8 invalid, 4 duplicate candidates, and 2 unsupported.
2. Acknowledge blocked rows with a note before committing. Acknowledgement does not bypass validation.
3. Review ready rows to include supplied amounts. Exclude other rows with a reason, or leave them pending. Reopen any review without erasing history. Only reviewed ready rows contribute to the displayed totals.
4. Select one import version explicitly. Identical uploads reopen the existing version; corrected files create a new one with separate reviews. Totals never combine versions.
5. Export the five-sheet sales working paper. It includes source rows, issues, counts, included totals, full review history, file hash and review cutoff, even when pending rows remain.

For the independent reference, reviewing all five ready sample rows gives taxable value 1750.00, CGST 112.50, SGST 112.50, IGST 90.00, cess 0.00, invoice total 2065.00. Before reviews, included totals are zero. These are supplied synthetic amounts, not validated tax liabilities.

Sales sources are stored transactionally as exact decoded UTF-8 in PostgreSQL (including BOM), alongside their byte hash, uploader and contract version. The adapter requires fictional DEMO customer references and supplied place-of-supply text. It does not infer or validate customer registration, place of supply, rates, ITC or statutory classifications. Credit/debit notes, exports, SEZ and other scopes remain unsupported. Correct blocked records through a new upload; exclusion never makes a duplicate counterpart valid.

[Sales contract and implementation plan](doc/plans/2026-09-14-phase4b-sales-v1.md) · [Synthetic scenarios](sample_data/sales_v1/README.md)

The development and E2E databases were migrated through c4b001 during Phase 4B. Restart an already-running older API to load new routes. New installations should follow the migration and startup commands above. The sales API is bounded for demo use; production-scale pagination, real authentication and CA validation remain future work.

## Tax worksheet and approval (Phase 5A)
Apply migrations through `c5a001` and restart the API. From a period workspace choose **Tax worksheet and approval**:
1. Select a committed sales version and a succeeded reconciliation run.
2. Record ITC decisions with a note. Only exact matches can be claimed; every other result must be marked not claimed or deferred.
3. Add adjustments (reverse-charge liability, other liability, ITC reversal, other credit) with a note; void mistakes with a reason.
4. Check the live per-head worksheet and blockers, save a draft snapshot, and approve it with a note.
5. Any later change to reviews, decisions or adjustments shows the approval as out of date; the snapshot and its export stay unchanged. Reopen with a reason, then draft and approve again. Filing references can be recorded as user-reported.

Reference: with the sales sample fully reviewed, only PUR-001 claimed, a CGST reverse-charge adjustment of 5.00 and one voided adjustment, net is IGST 90.00, CGST 27.50, SGST 22.50, cess 0.00 (see `tests/fixtures/calc_v1/cases.json`). No set-off, rounding or cash payable is computed. **History & audit** (`/history`) lists recorded actions per organization or period.

## Interface (2026-09-30)
Warm-neutral theme with dark mode (header toggle; follows the system setting by default). Sidebar: **The Board** (`/`), **Clients** (`/clients`), **History & Audit**, plus links for the open period. The Board shows, per client and period, Sales, Purchases & ITC and Tax worksheet status computed from saved records (`GET /board`), with a "Needs you now" lane for items waiting on a person.

## Interface: GST Helper design (2026-09-30)
Ported from the Lovable prototype ("The Ledger & The Departure Board"): ledger-spine sidebar, split-flap Board, folder-card clients, ledger-style tax worksheet with rubber stamps and margin notes, receipt-roll history, Day/Night Ledger themes. Typefaces by role: Fraunces (titles), Instrument Sans (interface), JetBrains Mono (figures and IDs), Space Grotesk (labels), Chivo Mono (board tiles), Special Elite (stamps), Caveat (notes); loaded from Google Fonts, with system fallbacks offline. The original export is kept in `aa151d83-2da1-4907-bb0a-96cd9245226e/` as a design reference only.

## Assistants (2026-09-30)
Deterministic helpers — no AI model, every output traceable, nothing recorded without a person clicking:
- **Board:** morning brief and savings-finder total.
- **Worksheet:** ITC pre-fill suggestions (accept with a note), client rules to apply, savings finder, and **Ask the ledger** (six question types answered from this period's records, with sources).
- **Reconciliation review:** exception investigator inside each finding, and supplier follow-up drafts to copy.
- **Uploads:** if headers don't match, the column mapper proposes a mapping for Tally/Zoho-style files; try `sample_data/demo_v1/tally_style_purchase_register.csv`.
- **Knowledge** (sidebar): write a client quirk as a note, confirm the drafted rule, then apply it per period.
Apply migrations through `c6a001`. Details: [assistants report](doc/phase-reports/2026-09-30-assistants-v1.md).
- **Legal rule register** (Knowledge screen): enter your firm's confirmed values for claim deadline, blocked-credit words, interest and late fee, with a source. Nothing ships pre-filled; each check turns on only after confirmation. Reminder rules ("confirm challan paid before filing") must be ticked off before approval. Apply migrations through `c7a001`.

## Login (2026-09-30)
The portal now requires signing in. All demo data belongs to one CA firm, **GST Helper Demo CA Firm**, whose login is **admin@demo.com**. "Test Org" is a separate organisation kept for testing only; its data is invisible to the firm's login.

Set the password yourself (the prompt hides what you type; nothing is echoed, stored in files, or passed on the command line):
```powershell
$env:DATABASE_URL='postgresql+asyncpg://postgres:postgres@localhost:5432/gst_copilot_dev'
python scripts/firm_admin.py set-password admin@demo.com
```
Other commands: `rename-firm <email> "<name>"`, `disable <email>` (blocks login and ends sessions). Apply migrations through `c8a001` and restart the API.

How it works: passwords are hashed with scrypt; a login creates a server-side session (only a hash of the token is stored) and sets an HttpOnly, SameSite=Strict cookie. Sessions last 12 hours; logout ends them immediately; 5 wrong passwords lock that email for 15 minutes. Every API route except health checks and login requires a session. The browser reaches the API through the app's own `/api` proxy (`API_URL` in the frontend environment points it at FastAPI), so no CORS is needed; signed-out visitors are redirected to `/login`. Logins and logouts appear in History. `scripts/seed_demo_data.py` now signs in (password prompt or `GSTH_PASSWORD`).

Not yet production-ready: no HTTPS configuration (set `COOKIE_SECURE=true` behind HTTPS), no password reset or self-service accounts, no multi-factor login, one role per firm, and the lockout counter is per API process.

## Hosting: Supabase + Render + Vercel (synthetic demo)
Supabase holds the database, Render runs the FastAPI backend (`render.yaml`) and Vercel serves the Next.js frontend. The browser only talks to Vercel; Vercel forwards `/api/*` to Render, so the login cookie stays same-site. Only synthetic data belongs here unless the firm authorises real client data and accepts Supabase's data-processing terms.

1. **Supabase**: create a project in region *South Asia (Mumbai)*. Keep the database password private. Open **Connect** and copy the **Session pooler** URI (port 5432). Do not use the transaction pooler (port 6543), which breaks asyncpg, or the direct connection (IPv6-only; Render cannot reach it). URL-encode special characters in the password (`@`→`%40`, `#`→`%23`).
2. **Render**: choose **New → Blueprint** and pick this GitHub repository; `render.yaml` creates `gst-helper-api`. When asked, paste the Supabase URI as `DATABASE_URL`. Each start runs `alembic upgrade head`. Migration `c9a001` turns on row-level security on every table and removes Supabase's `anon`/`authenticated` access, so the Supabase Data API cannot read them. Check `https://<render-app>.onrender.com/health/ready`.
3. **Firm login** (once, from your machine, with the same URI; values stay in your shell):
   ```bash
   DATABASE_URL='<supabase session-pooler URI>' DATABASE_SSL=true python backend/gst_copilot/cli/seed.py
   DATABASE_URL='<supabase session-pooler URI>' DATABASE_SSL=true python scripts/firm_admin.py set-password admin@demo.com
   ```
4. **Vercel**: create a project from the repository with **Root Directory** `frontend`. Set the environment variable `API_URL=https://<render-app>.onrender.com` (no trailing slash; it is read at build time, so redeploy after changing it).
5. **Optional synthetic demo data**: `python scripts/seed_demo_data.py --api https://<render-app>.onrender.com` (it prompts for the password).

Free-plan behaviour: Render sleeps after 15 idle minutes, so the first request can take about 50 s and may time out once while it wakes. Supabase pauses a free project after a week without activity. Uploaded CSVs are written to Render's temporary disk only while they are parsed; the parsed rows live in the database. The login throttle is in-process, so run one Render instance.

## Set-off and cash payable (Phase 5B)
Under **Knowledge → Legal rules**, a CA confirms two values with a source: the **credit utilisation order** (one `CREDIT>LIABILITY` step per line, applied top to bottom) and **rounding of cash payable** (multiple and direction). GST Helper ships neither. Until the order is confirmed, the worksheet shows "Set-off not computed". Afterwards, steps 4–5 show cash payable per head, rounding and credit carried forward, and the draft workbook gains a Set-off sheet. Enter last period's closing credit as an **Opening credit balance (user-reported)** adjustment. Confirming or changing these rules makes earlier approvals out of date.

## Monthly cycle and firm features (2026-10-05)
- **Carry-forward:** worksheet step 3 offers last month's closing credit (from a current approval with computed set-off) as opening credit.
- **Due dates:** shown on the Board after a CA confirms *Return due dates* under Knowledge.
- **Firm & team:** owner / reviewer / preparer roles, an optional "separate approver" policy, and period assignment ("Only my work" on the Board).
- **IMS inbox** (per period): accept, reject or keep pending each supplier invoice. Rejected and pending invoices cannot be claimed.
- **GSTR-3B view:** on the draft, and as a workbook sheet.
- **GSTR-2B JSON:** import it on the Imports screen, which shows a conversion report.
- **GSTR-1:** download sales template v2 (GSTIN, state code, rate, HSN, unit, quantity), then **Export GSTR-1 draft (JSON)**. Not validated against the portal: open it in the GSTN offline tool and have a CA review it.
- **Client requests** (Imports screen): create expiring upload links (clients upload at `/u/<token>` without logging in; files arrive as previews), or draft a reminder that opens in your own email or WhatsApp. Save client contact details on the client page.
