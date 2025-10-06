import streamlit as st
import pandas as pd
import requests
import re

def extract_lead_id(text):
    ids = re.findall(r'(\d{5,8})', str(text))
    return ids[-1] if ids else None

def extract_phone(val):
    try: return int(float(val))
    except: return None

LAW_RULER_API = "https://tabakattorneys.lawruler.com/api-legalcrmapp.aspx"
API_KEY = "8A2A55F85D784406B7F79DC286745"

st.title("Law Ruler API Dashboard")

call_file = st.file_uploader("Upload Call Log CSV")
zap_file = st.file_uploader("Upload Zap History CSV")

if call_file and zap_file:
    calls = pd.read_csv(call_file)
    zaps = pd.read_csv(zap_file)
    calls["phone"] = calls["Caller ID"].apply(extract_phone)
    zaps["phone"] = zaps["input__323618010__data__CellPhone"].apply(extract_phone)
    merged = pd.merge(calls, zaps, on="phone")
    merged["LeadID"] = merged["output__323618010__text"].apply(extract_lead_id)
    st.write(merged[["Date", "First", "Last", "Caller ID", "Duration", "LeadID"]])
    lead_ids = merged["LeadID"].dropna().unique()
    
    if st.button("Fetch Law Ruler Statuses"):
        results = []
        for i, row in merged.iterrows():
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
                    result = resp.text[:500]
                except Exception as e:
                    result = f"Error: {e}"
                results.append({
                    "First Name": row["First"],
                    "Last Name": row["Last"],
                    "Phone": row["Caller ID"],
                    "Call Duration": row["Duration"],
                    "Call Date": row["Date"],
                    "LeadID": lid,
                    "Law Ruler Status XML": result
                })
        st.write(pd.DataFrame(results))
else:
    st.info("Upload both Call Log and Zap History files to view matches and check statuses.")
