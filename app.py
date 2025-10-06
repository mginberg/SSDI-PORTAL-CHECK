import streamlit as st
import pandas as pd
import requests
import re
import xml.etree.ElementTree as ET

def extract_lead_id(text):
    ids = re.findall(r'(\d{5,8})', str(text))
    return ids[-1] if ids else None

def extract_phone(val):
    try:
        n = int(float(val))
        return str(n)
    except:
        return str(val)

def extract_xml_fields(xml_str):
    try:
        root = ET.fromstring(xml_str)
        status = root.findtext(".//Status") or ""
        lead_provider = root.findtext(".//LeadProvider") or ""
        return status, lead_provider
    except Exception as e:
        return f"XML Parse Error: {e}", ""

LAW_RULER_API = "https://tabakattorneys.lawruler.com/api-legalcrmapp.aspx"
API_KEY = "8A2A55F85D784406B7F79DC286745"

st.title("Law Ruler Lead Status Dashboard")

call_file = st.file_uploader("Upload Call Log CSV")
zap_file = st.file_uploader("Upload Zap History CSV")
sales_file = st.file_uploader("Upload SALES SHEET CSV (optional, to check missing)", key="sales")

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

    if st.button("Fetch Law Ruler Statuses"):
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
                    status, lead_provider = extract_xml_fields(resp.text)
                except Exception as e:
                    status, lead_provider = f"Error: {e}", ""
                results.append({
                    "First Name": row["First"],
                    "Last Name": row["Last"],
                    "Phone": str(row["Caller ID"]),
                    "Call Duration": row["Duration"],
                    "Call Date": row["Date"],
                    "LeadID": lid,
                    "Law Ruler Status": status,
                    "Lead Provider": lead_provider
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

st.markdown("""
**Instructions:**
- Upload Call Log, Zap History, and (optionally) your sales sheet.
- Click 'Fetch Law Ruler Statuses' then download your results.
- You'll see/download a list of missing sales customers if you upload your sales sheet.
""")
