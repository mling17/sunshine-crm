---
name: legacy-order-import
description: Import historical Sunshine CRM order-form workbooks from a directory. Use when the user provides legacy .xlsx order tables and wants them validated, dry-run, imported, or triaged into an error folder.
---

# Legacy Order Import

Use `scripts/legacy_order_import.py`; do not recreate parsing or write business tables ad hoc.

## Non-negotiable rules

- Read only `.xlsx` files. Default is top-level only; use `--recursive` when the user says to include subdirectories.
- Use only the first worksheet. `A1` is the product title. It must normalize to exactly one non-deleted product name; zero or multiple matches go to the error folder.
- Do not modify the product table while importing.
- Every imported order is created as `completed` and fully paid. This is an explicit user decision even when the source says deposit or unpaid.
- Do not write an order note. Tag the linked deal with `历史订单导入`.
- Reuse an existing customer by normalized phone. Duplicate phone customers abort the whole batch. Multiple orders for the same phone reuse the same customer.
- Keep the original workbook as the quote-item form and as the order confirmation attachment using the same storage key.
- Default to dry-run. Use `--commit` only after reviewing the dry-run summary.
- Never overwrite source files. Problem files are copied under the run error directory.

## Safe workflow

From the repository root:

1. Run a dry-run against the current configured database:

```powershell
py -3 scripts\legacy_order_import.py --source "<directory>" --recursive
```

2. Review the JSON output and `run-*/summary.json` / `errors.csv` under
   `C:\Users\P0182449\Desktop\import_error`.

3. For first-time validation, copy the SQLite database and uploads to an isolated directory, then commit there:

```powershell
Copy-Item .local\data\crm.db .local\legacy-import-sandbox\crm.db
New-Item -ItemType Directory .local\legacy-import-sandbox\uploads -Force
py -3 scripts\legacy_order_import.py --source "<directory>" --recursive --commit `
  --db .local\legacy-import-sandbox\crm.db `
  --uploads .local\legacy-import-sandbox\uploads `
  --error-dir .local\legacy-import-sandbox\errors `
  --manifest .local\legacy-import-sandbox\manifest.json
```

4. Verify counts and invariants in the isolated database before touching the live database.
5. Back up the live database, then commit with explicit `--db` and `--uploads`.
6. Restart the backend after code changes. Reopen the CRM and verify an imported order, its quote form, order confirmation attachment, tag, completed status, paid amount, and no note.

## Live local defaults

- Running SQLite DB: `.local/data/crm.db`
- Running uploads: `.local/data/uploads`
- Error root: `C:\Users\P0182449\Desktop\import_error`
- Manifest: `C:\Users\P0182449\Desktop\legacy_order_import_manifest.json`

For MySQL, pass `--env-file .local\crm.env` and also set `CRM_UPLOADS` to the real upload root.

## Expected source behavior

- Sheet1 `A1` is the product title. Do not infer the product from the filename or line-item names.
- Header and field positions vary. The importer detects labels such as 收货人/收货单位, 收货地址/收货信息, 下单日期, 出货日期/生产周期, 数量, 金额, 合计.
- A valid import may aggregate multiple numbered product rows into one order item because the user defines the product at `A1`; the original workbook remains the complete detail source.
- Excel lock files beginning with `~$` are processed and reported as unreadable problem files, not silently ignored.

## Error handling

- Unmatched/ambiguous product, unreadable workbook, missing receiver/phone/address/date/amount, duplicate SHA-256, and duplicate customer phones are problems.
- Do not infer a product from similar text. Do not auto-select among same-name products.
- If duplicate existing customer phones are found, stop the batch and fix the system data before importing.
