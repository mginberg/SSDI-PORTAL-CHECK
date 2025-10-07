import streamlit as st
import pandas as pd
import requests
import re
import xml.etree.ElementTree as ET

def extract_lead_id(text):
    ids = re.findall(r'(\\d{5,8})', str(text))
    return ids[-1] if ids else None

def extract_phone(val):
    try: return str(int(float(val)))
    except: return str(val)

def extract_xml_fields(xml_str):
    try:
        root = ET.fromstring(xml_str)
        status = root.findtext(".//Status") or ""
        lead_provider = root.findtext(".//LeadProvider") or root.findtext(".//Source") or ""
        return status, lead_provider
    except Exception as e:
        return f"XML Parse Error: {e}", ""

LAW_RULER_API = "https://tabakattorneys.lawruler.com/api-legalcrmapp.aspx"
API_KEY = "8A2A55F85D784406B7F79DC286745"

st.title("Law Ruler Lead Status Dashboard")

call_file = st.file_uploader("Upload Call Log CSV")
zap_file = st.file_uploader("Upload Zap History CSV")
export_file = st.file_uploader("Upload Export Sheet (Lead IDs)", type=["csv", "xlsx"], key="export")

final_df = None

if export_file:
    # Accept both Excel and CSV
    if export_file.name.lower().endswith("xlsx"):
        export_df = pd.read_excel(export_file)
    else:
        export_df = pd.read_csv(export_file)
    lead_ids = export_df["Lead ID"].dropna().unique()
    st.write(f"Found {len(lead_ids)} unique Lead IDs in Export Sheet")
    # Fetch Law Ruler Status for each Lead ID
    api_results = []
    for lid in lead_ids:
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
        row = export_df[export_df["Lead ID"] == lid].iloc[0]
        api_results.append({
            "Lead ID": lid,
            "First Name": row.get("First Name", ""),
            "Last Name": row.get("Last Name", ""),
            "Phone": row.get("Cell Phone", ""),
            "Source": row.get("Source", ""),
            "Law Ruler Status": status,
            "Law Ruler Provider": lead_provider
        })
    results_df = pd.DataFrame(api_results)
    st.write(results_df)
    st.download_button("Download Export Sheet Statuses", results_df.to_csv(index=False), "leadid_status_results.csv")

st.markdown("""
**Instructions:**
- Upload your Export Sheet (e.g., BenefitsZoom report) containing Lead IDs.
- The app fetches Law Ruler status for each unique Lead ID in your export and provides a downloadable sheet.
""")
