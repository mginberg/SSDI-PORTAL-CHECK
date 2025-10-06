import streamlit as st
import pandas as pd
import requests
import io

st.title("Law Ruler API Dashboard")

st.write("Upload your Call Log and Zap History CSV files.")

call_file = st.file_uploader("Call Log CSV")
zap_file = st.file_uploader("Zap History CSV")

def extract_phone(val):
    try:
        return int(float(val))
    except:
        return None

def extract_last_lead_id(text):
    import re
    ids = re.findall(r'(\\d{5,8})', str(text))
    if ids:
        return ids[-1]
    return None

if call_file is not None and zap_file is not None:
    call_df = pd.read_csv(call_file)
    zap_df = pd.read_csv(zap_file)

    call_df["caller_id_int"] = call_df["Caller ID"].apply(extract_phone)
    zap_df["cell_int"] = zap_df["input__323618010__data__CellPhone"].apply(extract_phone)

    merged = pd.merge(call_df, zap_df, left_on="caller_id_int", right_on="cell_int", suffixes=('_call', '_zap'))
    merged["LeadID"] = merged["output__323618010__text"].apply(extract_last_lead_id)

    st.write("### Matched records")
    st.write(merged[["Date_call", "First_call", "Last_call", "caller_id_int", "LeadID"]])

    leadids = merged["LeadID"].dropna().unique()
    st.write("Found lead IDs for API lookup:", leadids)
    st.write("You can fetch status for leads below:")

    if st.button("Fetch Statuses for All Lead IDs"):
        st.write("Fetching statuses...")
        results = []
        for leadid in leadids:
            api_url = f"https://lawruler-proxy.onrender.com/lead_status?lead_id={leadid}"
            try:
                resp = requests.get(api_url, timeout=15)
                results.append({"LeadID": leadid, "API URL": api_url, "Result": resp.text})
            except Exception as e:
                results.append({"LeadID": leadid, "API URL": api_url, "Result": f"Request failed: {str(e)}"})
        st.write(pd.DataFrame(results))

