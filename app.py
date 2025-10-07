import streamlit as st
import pandas as pd
import requests
import xml.etree.ElementTree as ET

def extract_lead_id(text):
    import re
    ids = re.findall(r'(\d{5,8})', str(text))
    return ids[-1] if ids else None

def extract_phone(val):
    try: return str(int(float(val)))
    except: return str(val)

def extract_xml_fields(xml_str):
    try:
        root = ET.fromstring(xml_str)
        status = root.findtext(".//Status") or ""
        lead_provider = root.findtext(".//LeadProvider") or root.findtext('.//Source') or ""
        return status, lead_provider
    except Exception as e:
        return f"XML Parse Error: {e}", ""

LAW_RULER_API = "https://tabakattorneys.lawruler.com/api-legalcrmapp.aspx"
API_KEY = "8A2A55F85D784406B7F79DC286745"

st.title("Law Ruler Lead Status Dashboard")

st.header("Option 1: Call Log + Zap History Match")
call_file = st.file_uploader("Upload Call Log CSV", key="call")
zap_file = st.file_uploader("Upload Zap History CSV", key="zap")
sales_file = st.file_uploader("Upload SALES SHEET CSV (optional, checks missing)", key="sales")

final_df = None

if call_file and zap_file:
    calls = pd.read_csv(call_file)
    zaps = pd.read_csv(zap_file)
    calls["phone"] = calls["Caller ID"].apply(extract_phone)
    zaps["phone"] = zaps["input__323618010__data__CellPhone"].apply(extract_phone)
    merged = pd.merge(calls, zaps, on="phone")
    merged["LeadID"] = merged["output__323618010__text"].apply(extract_lead_id)
    merged_unique = merged.drop_duplicates(subset=["LeadID"], keep="first")
    st.write(merged_unique[["Date", "First", "Last", "Caller ID", "Duration", "LeadID"]])
    lead_ids = merged_unique["LeadID"].dropna().unique()
    if st.button("Fetch Law Ruler Statuses", key="fetch_status_1"):
        results = []
        for i, row in merged_unique.iterrows():
            lid = row["LeadID"]
            if pd.notna(lid):
                params = {
                    "Key": API_KEY,
                    "Operation": "GetStatus",
                    "ReturnXML": "True",
                    "LeadId": lid
                }
                try:
                    resp = requests.get(LAW_RULER_API, params=params, timeout=20)
                    status, provider = extract_xml_fields(resp.text)
                except Exception as e:
                    status, provider = f"Error: {e}", ""
                results.append({
                    "First Name": row["First"],
                    "Last Name": row["Last"],
                    "Phone": str(row["Caller ID"]),
                    "Call Duration": row["Duration"],
                    "Call Date": row["Date"],
                    "LeadID": lid,
                    "LawRuler Status": status,
                    "LawRuler Provider": provider
                })
        result_df = pd.DataFrame(results)
        final_df = result_df
        st.write(result_df)
        st.download_button("Download Results as CSV", result_df.to_csv(index=False), "lead_status_results.csv")

if final_df is not None and sales_file is not None:
    sales = pd.read_csv(sales_file)
    sales["phone_clean"] = sales["PHONE NUMBER"].apply(extract_phone)
    final_df["phone_clean"] = final_df["Phone"].apply(extract_phone)
    sales["name_clean"] = sales["CX NAME"].str.strip().str.lower()
    final_df["name_clean"] = (final_df["First Name"].astype(str) + " " + final_df["Last Name"].astype(str)).str.strip().str.lower()
    phone_match = sales[~sales["phone_clean"].isin(final_df["phone_clean"])]
    name_match = sales[~sales["name_clean"].isin(final_df["name_clean"])]
    missing = sales[sales.index.isin(phone_match.index) & sales.index.isin(name_match.index)]
    st.write("**Customers present in SALES SHEET but missing from status results (unmatched by phone and name):**")
    st.write(missing)
    st.download_button("Download Missing Customers as CSV", missing.to_csv(index=False), "missing_customers.csv")

st.header("Option 3: Export Sheet (LeadIDs in column A, fetch statuses)")
export_file = st.file_uploader("Upload Export Sheet (.csv or .xlsx; LeadIDs in column A)", type=["csv", "xlsx"], key="export")
if export_file:
    try:
        if export_file.name.lower().endswith(".xlsx"):
            xls = pd.ExcelFile(export_file)
            df_export = xls.parse(xls.sheet_names[0])
        else:
            df_export = pd.read_csv(export_file)
        lead_ids = df_export.iloc[:,0].dropna().unique().astype(str).tolist()
        st.write(f"Found {len(lead_ids)} unique Lead IDs in first column.")
        if st.button("Fetch LawRuler Statuses for Export Sheet", key="fetch_status_3"):
            results = []
            for lid in lead_ids:
                params = {
                    "Key": API_KEY,
                    "Operation": "GetStatus",
                    "ReturnXML": "True",
                    "LeadId": lid
                }
                try:
                    resp = requests.get(LAW_RULER_API, params=params, timeout=20)
                    status, provider = extract_xml_fields(resp.text)
                except Exception as e:
                    status, provider = f"Error: {e}", ""
                # get all other columns in row if present
                row = df_export[df_export.iloc[:,0].astype(str) == lid]
                if not row.empty:
                    row = row.iloc[0]
                    data = {col: row.get(col, "") for col in df_export.columns}
                else:
                    data = {}
                results.append({
                    "Lead ID": lid,
                    "LawRuler Status": status,
                    "LawRuler Provider": provider,
                    **data
                })
            res_df = pd.DataFrame(results)
            st.write(res_df)
            st.download_button("Download Export Sheet Statuses", res_df.to_csv(index=False), "leadid_export_status_results.csv")
    except Exception as e:
        st.error(f"Error processing export file: {e}")

st.markdown("""
**Instructions:**

- Option 1: Upload call log + zap history, fetch statuses, download full match sheet.
- Option 2: Upload sales sheet to see missing customers after status results.
- Option 3: Upload export file (.csv or .xlsx) with LeadIDs in the first column. Fetch and download latest LawRuler status for each.
""")
