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
    st.write(merged[["Date", "First", "Last", "Caller ID", "LeadID"]])
    lead_ids = merged["LeadID"].dropna().unique()
    if st.button("Fetch Law Ruler Statuses"):
        results = []
        for lid in lead_ids:
            url = f"https://ssdi-app-check-y742cphgqxkh2cysfols8t.streamlit.app/lead_status?lead_id={lid}"
            try:
                resp = requests.get(url, timeout=20)
                out = resp.json()
                results.append({
                    "LeadID": lid,
                    "Status": out.get("result", "")[:200],
                    "API URL": url
                })
            except Exception as e:
                results.append({
                    "LeadID": lid,
                    "Status": f"Error: {e}",
                    "API URL": url
                })
        st.write(pd.DataFrame(results))
else:
    st.info("Upload both Call Log and Zap History files to view matches and check statuses.")

st.markdown("**Proxy URL:** Using `https://ssdi-app-check-y742cphgqxkh2cysfols8t.streamlit.app` for API calls.")
