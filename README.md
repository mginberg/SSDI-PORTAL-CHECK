# SSDI Transfer Bot — Starter Pack

This bundle includes:
- `transfer_bot.py` — CLI tool to merge your daily Call Log with Zapier LeadIDs and (optionally) fetch statuses via buyer APIs.
- `vendors.template.json` — template for buyer status endpoints.
- `vendors.tabak.json` — prefilled config for Tabak (Law Ruler GetStatus).
- `leadid_mapping_from_zap.csv` — mapping extracted from your Zap export (phone/date → LeadID).
- `merged_with_leadids.csv` — your Call Details merged with LeadIDs.
- `merged_with_status_SAMPLE.csv` — sample of the final output shape with example statuses.
- `portal_app.py` — a **Streamlit portal** that lets you upload your Call Log + Zap export, performs the merge, and (optionally) pulls statuses.

## Quick Start (local)

1) Install Python 3.9+ and dependencies:
```
pip install pandas requests streamlit lxml
```

2) Merge Call Log + Zap Export:
```
python transfer_bot.py \
  --call_log "CallDetails_09-01-2025_10-04-2025.csv" \
  --zap_export "46f731c5-e62e-4ee4-9724-ab4b9896517e.csv" \
  --out_merged "merged_with_leadids.csv" \
  --call_phone_col "Caller ID" \
  --call_time_col "Date"
```

3) Pull Statuses (Tabak preconfigured):
```
python transfer_bot.py \
  --call_log "CallDetails_09-01-2025_10-04-2025.csv" \
  --zap_export "46f731c5-e62e-4ee4-9724-ab4b9896517e.csv" \
  --vendors "vendors.tabak.json" \
  --out_merged "merged_with_leadids.csv" \
  --out_status "merged_with_status.csv"
```

## Streamlit Portal

Run:
```
streamlit run portal_app.py
```

Use the UI to:
- pick a vendor (single or multiple supported),
- upload your **Call Log CSV** and **Zap export CSV**,
- click **Process** → it will show the merged table and let you download **merged_with_leadids.csv**.
- (Optional) provide a `vendors.json` file to also fetch statuses → download **merged_with_status.csv**.

### Vendors Config

- `vendors.tabak.json` has:
  - method: GET
  - url: https://tabakattorneys.lawruler.com/api-legalcrmapp.aspx?Operation=GetStatus&ReturnXML=True&Key=YOUR_KEY
  - id_param: LeadId
  - Accepts XML; bot parses <Status>, <SubStatus>, <StatusTime>.

To add more buyers, copy **vendors.template.json** to **vendors.json** and append entries.

## Notes

- Join logic defaults to **consumer phone (E.164) + date**. If you add a stable `transfer_id` to both files, we can switch to exact join.
- Billable statuses default to SIGNED/QUALIFIED/APPT_SET; override per vendor in `billable_statuses`.
- Keep your API keys safe if you share this bundle.

— Enjoy!