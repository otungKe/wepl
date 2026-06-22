# Card Lifecycle Management (90-Day Destruction Rule)

This folder is self-contained and unrelated to the rest of the WEPL backend — it was added
on request to satisfy an Excel/VBA card-register specification.

---

## ⭐ Application-grade dashboard for the I&M card register

Built around your real register and the three-stage cycle:
**① RECORD** (a card is logged on arrival) → **② LIFECYCLE** (Days in Branch ages it under
the 90-day rule: New / Normal / Warning / Due) → **③ REMIND** (collection & destruction
reminders fire from your existing Outlook macros).

| File | What it is |
|------|------------|
| `CardOps_Dashboard.xlsx` | A **working preview** built from your actual 49 records, so you can see the design immediately (status donut, ageing distribution, recording-trend line, branch-health bar, KPI tiles, cycle pipeline, alert ribbon, oldest-in-branch action queue). |
| `CardOps_Dashboard.bas` | A **native VBA generator** that paints the same dashboard into your real `.xlsm` as a new `Dashboard` sheet, with buttons wired to `RecordNewCard`, your `SendCardEmails`, and `GenerateDestructionRegister`. |
| `build_dashboard_app.py` | Regenerates `CardOps_Dashboard.xlsx` from the source register. |

**Why a generator instead of editing your file directly?** Your register relies on x14
conditional formatting, the Status dropdown, cell-control checkboxes and a full VBA project.
Saving it through a Python library would silently strip several of those. The `.bas` runs
*inside* Excel, so it adds the `Dashboard` sheet with **zero loss** — it never touches
`Dashboard_2026`, the Card Register data, your formatting, or your other macros.

**To apply it to your register:** open the `.xlsm` → `Alt+F11` → *File ▸ Import File…* →
`CardOps_Dashboard.bas` → back in Excel run macro **`BuildDashboard`**. Re-run any time (the
Refresh button does this); `RecordNewCard` handles stage-1 intake.

> Notes on your current file: `cards_type` is empty, so the Card Type `XLOOKUP` returns
> `#N/A` — fill in the BIN→name map to light up card-type breakdowns. This copy also has no
> `Held` cards (all Issued/Destroyed/Pend), so the destruction KPIs read 0 until cards are
> held; the ageing distribution uses *days in branch* so it stays meaningful regardless.

---

## Standalone template (generic, not tied to your register)

The files below are an earlier **self-contained** workbook implementing the same 90-day rule
from scratch — useful as a clean reference or starting point.

## Files

| File | What it is |
|------|------------|
| `CardLifecycle.xlsx` | The workbook. Fully functional with **formulas only** — no macros required. |
| `CardLifecycle_Macros.bas` | Optional VBA module: audit logging, "mark for destruction", pop-up alert. |
| `build_workbook.py` | Generator that produces `CardLifecycle.xlsx` (re-run to regenerate). |

## The core rule

`Card Age = TODAY() − Date Received`, recomputed live every time the file opens.

| Card Age | Status | Colour |
|----------|--------|--------|
| 0–59 days | **NORMAL** | 🟩 Green |
| 60–89 days | **WARNING (Nearing Expiry)** | 🟨 Amber |
| 90+ days | **DUE FOR DESTRUCTION** | 🟥 Red |

The 90 / 60 / 85 thresholds and the red-alert count live on the **Config** sheet (as the
named ranges `DestructionDays`, `WarningDays`, `EscalateDays`, `RedAlertThreshold`); every
other sheet reads from there, so the rule is defined in exactly one place.

## Sheets

- **Dashboard** — green/amber/red KPI tiles, "Approaching Expiry (60–89)" and "Due for
  Destruction (90+)" counters, a high-risk (85+) counter, an aging-distribution chart, and a
  banner that turns red when the destruction backlog exceeds the threshold.
- **Card_Master** — the data table with auto-calculated **Card Age**, **Age Category**,
  **Destruction Flag**, **Days to 90-Day Limit** and **Days Overdue**. Whole rows are
  conditionally formatted green/amber/red.
- **Destruction_Due_Report** — only 90+ cards, **most overdue at the top**, with Days Overdue
  (`Card Age − 90`) for operational destruction processing.
- **Search** — type a card number; returns Age, Age Category, Destruction Status (Yes/No) and
  days remaining / overdue, with a colour-coded category.
- **Audit_Log** — append-only trail of 60 / 85 / 90-day transitions and destruction actions
  (seeded with examples; the VBA module appends to it automatically).
- **Config** — the business constants.

## Using it

Just open `CardLifecycle.xlsx` and replace the 25 sample rows with real cards (keep the
formula columns F–J — they fill down automatically inside the table). Everything recalculates.

### Excel version note
The **Destruction_Due_Report** uses dynamic-array functions (`FILTER`, `SORT`, `HSTACK`) and
needs **Excel 365 / 2021**. On older Excel, AutoFilter `Card_Master` on
`Age Category = "Due for Destruction"` and sort `Days Overdue` descending instead — the rest
of the workbook works on any modern Excel.

### Enabling the macros (optional)
1. Open `CardLifecycle.xlsx`, press **Alt+F11**, then **File → Import File…** and choose
   `CardLifecycle_Macros.bas`.
2. Paste the `Workbook_Open` snippet (bottom of the .bas) into the **ThisWorkbook** object.
3. **Save As → Excel Macro-Enabled Workbook (.xlsm)**.

`RefreshLifecycle` then runs on open: it recalculates ages, writes audit entries for any new
60/85/90-day transitions, and pops an alert if the red backlog exceeds the threshold.

## Regenerating

```bash
pip install openpyxl
python build_workbook.py
```
