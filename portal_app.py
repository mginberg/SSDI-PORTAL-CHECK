import streamlit as st
import pandas as pd
import re, json, requests
from io import StringIO

st.set_page_config(page_title="SSDI Transfer Portal", layout="wide")
st.title("SSDI Transfer Portal")

def norm_phone(x):
    s = re.sub(r"\D", "", str(x or ""))
    if not s: return ""
    if len(s)==11 and s.startswith("1"): return f"+{s}"
    if len(s)==10: return f"+1{s}"
    return f"+{s}"

def extract_lead_id(text):
    if pd.isna(text): return ""
    m = re.search(r'Lead ID.*?(\d+)', str(text), flags=re.I|re.S)
    if m: return m.group(1)
    m2 = re.search(r'Success\s+Lead\s+#\s*(\d+)', str(text), flags=re.I)
    return m2.group(1) if m2 else ""

st.sidebar.header("Inputs")
vendor_code = st.sidebar.text_input("Vendor code (e.g., TABAK)", value="TABAK")
call_phone_col = st.sidebar.text_input("Call log phone column", value="Caller ID")
call_time_col = st.sidebar.text_input("Call log time column", value="Date")

call_csv = st.file_uploader("Upload Call Log CSV", type=["csv"])
zap_csv  = st.file_uploader("Upload Zap Export CSV", type=["csv"])
vendors_json = st.file_uploader("Upload vendors.json (optional, for statuses)", type=["json"])

process = st.button("Process")

if process:
    if not call_csv or not zap_csv:
        st.error("Please upload both Call Log and Zap Export CSVs.")
    else:
        calls = pd.read_csv(call_csv, dtype=str)
        zap = pd.read_csv(zap_csv, dtype=str)

        # prepare zap map
        out_cols = [c for c in zap.columns if c.startswith("output__") and c.endswith("__text")]
        if not out_cols:
            st.error("Could not find Zap output text column in export.")
            st.stop()
        zap['crm_lead_id'] = zap[out_cols[-1]].apply(extract_lead_id)

        phone_cols = [c for c in zap.columns if c.lower().endswith('__data__cellphone') or c.lower().endswith('__querystring__cellphone') or c.lower().endswith('__data__phone') or c.lower().endswith('__querystring__phone')]
        zap['raw_phone'] = ''
        for c in phone_cols:
            zap['raw_phone'] = zap['raw_phone'].where(zap['raw_phone']!='', zap[c].fillna(''))

        zap['phone_e164'] = zap['raw_phone'].map(norm_phone)
        zap['zap_date'] = pd.to_datetime(zap['date'], errors='coerce').dt.date.astype('string')
        lead_map = zap[['phone_e164','zap_date','crm_lead_id']].dropna().copy()

        # calls normalize
        calls['consumer_phone_e164'] = calls[call_phone_col].map(norm_phone)
        calls['call_date'] = pd.to_datetime(calls[call_time_col], errors='coerce').dt.date.astype('string')

        merged = calls.merge(lead_map, left_on=['consumer_phone_e164','call_date'], right_on=['phone_e164','zap_date'], how='left')
        merged.drop(columns=['phone_e164','zap_date'], inplace=True, errors='ignore')
        merged['vendor_code'] = vendor_code

        st.success("Merged Call Log with LeadIDs")
        st.dataframe(merged.head(50))
        st.download_button("Download merged_with_leadids.csv", merged.to_csv(index=False), file_name="merged_with_leadids.csv", mime="text/csv")

        if vendors_json is not None:
            cfgs = json.load(vendors_json)
            # choose vendor config
            if vendor_code not in cfgs and len(cfgs)==1:
                cfg = list(cfgs.values())[0]
            else:
                cfg = cfgs.get(vendor_code)
            if not cfg:
                st.error(f"Vendor {vendor_code} not found in vendors.json")
                st.stop()

            def fetch_status(lead_id, cfg):
                method = cfg.get('method','GET').upper()
                url = cfg.get('url','')
                id_param = cfg.get('id_param','leadId')
                headers = cfg.get('auth_header',{})
                extra = cfg.get('extra_headers',{})
                headers.update(extra)
                req_url = url
                payload = None
                if '{id}' in req_url:
                    req_url = req_url.replace('{id}', str(lead_id))
                elif method == 'GET':
                    sep='&' if '?' in req_url else '?'
                    req_url = f"{req_url}{sep}{id_param}={lead_id}"
                else:
                    payload = {id_param: lead_id}
                r = requests.request(method, req_url, headers=headers, json=payload if payload and method!='GET' else None, timeout=30)
                text = r.text
                try:
                    js = r.json()
                    raw_status = js.get(cfg.get('status_field','status'))
                    sub = js.get(cfg.get('substatus_field','subStatus'))
                    stime = js.get(cfg.get('status_time_field','statusTime'))
                except Exception:
                    # XML fallback
                    import xml.etree.ElementTree as ET
                    root = ET.fromstring(text)
                    def find(tag):
                        el = root.find(f'.//{tag}') or root.find(f'.//{tag.lower()}') or root.find(f'.//{tag.upper()}')
                        return el.text.strip() if el is not None and el.text else None
                    raw_status = find(cfg.get('status_field','Status'))
                    sub = find(cfg.get('substatus_field','SubStatus')) or find('Reason')
                    stime = find(cfg.get('status_time_field','StatusTime')) or find('UpdatedAt')
                s_map = cfg.get('status_map',{})
                status = s_map.get(str(raw_status or '').upper(), 'OPEN')
                billable = 'Y' if status in set(cfg.get('billable_statuses',['SIGNED','QUALIFIED','APPT_SET'])) else ('N' if status in ['DUPLICATE','BAD_NUMBER','NQ'] else '')
                return status, sub, stime, billable

            out = merged.copy()
            statuses = []
            for _, row in out.iterrows():
                lead_id = row.get('crm_lead_id')
                if not isinstance(lead_id, str) or not lead_id.strip():
                    statuses.append((None,None,None,''))
                    continue
                try:
                    s, sub, stime, bill = fetch_status(lead_id, cfg)
                except Exception as e:
                    s, sub, stime, bill = ('OPEN', f'ERR {e}', None, '')
                statuses.append((s, sub, stime, bill))
            s_df = pd.DataFrame(statuses, columns=['status','substatus','status_time','billable_flag'])
            final = pd.concat([out.reset_index(drop=True), s_df], axis=1)

            st.success("Fetched statuses from vendor API")
            st.dataframe(final.head(50))
            st.download_button("Download merged_with_status.csv", final.to_csv(index=False), file_name="merged_with_status.csv", mime="text/csv")

st.markdown("---")

st.markdown("---")
st.subheader("🔎 Test a Single LeadID (debug)")

leadid_test = st.text_input("Enter a LeadID to test the status API (e.g., 711551)", value="")
debug_cfg_json = st.text_area("Optional: override vendor config JSON for this test", value="", height=150)
do_test = st.button("Test Status Lookup")

def redact_url(u: str):
    import re
    return re.sub(r'(Key=)[^&]+', r'\1****', u)

if do_test:
    try:
        # Determine config (override > uploaded vendors.json > TABAK fallback)
        test_cfg = None
        if debug_cfg_json.strip():
            test_cfg = json.loads(debug_cfg_json)
        elif vendors_json is not None:
            cfgs_all = json.load(vendors_json)
            if vendor_code in cfgs_all:
                test_cfg = cfgs_all[vendor_code]
            elif len(cfgs_all) == 1:
                test_cfg = list(cfgs_all.values())[0]
        if test_cfg is None:
            test_cfg = {
                "method":"GET",
                "url":"https://tabakattorneys.lawruler.com/api-legalcrmapp.aspx?Operation=GetStatus&ReturnXML=True&Key=8A2A55F85D784406B7F79DC286745",
                "id_param":"LeadId",
                "auth_header":{},
                "extra_headers":{"Accept":"application/xml,application/json"},
                "status_field":"Status",
                "substatus_field":"SubStatus",
                "status_time_field":"StatusTime",
                "canonical_id_field":"canonicalLeadId",
                "status_map":{
                    "SIGNED":"SIGNED","RETAINED":"SIGNED","APPOINTMENT SET":"APPT_SET","QUALIFIED":"QUALIFIED",
                    "DUPLICATE":"DUPLICATE","NOT QUALIFIED":"NQ","NO ANSWER":"NO_ANSWER","BAD NUMBER":"BAD_NUMBER",
                    "IN PROGRESS":"OPEN","NEW":"OPEN"
                },
                "billable_statuses":["SIGNED","QUALIFIED","APPT_SET"]
            }
        if not leadid_test.strip():
            st.error("Enter a LeadID to test.")
        else:
            method = (test_cfg.get('method') or 'GET').upper()
            url = test_cfg.get('url') or ''
            id_param = test_cfg.get('id_param') or 'LeadId'
            headers = dict(test_cfg.get('auth_header') or {})
            headers.update(test_cfg.get('extra_headers') or {})
            req_url = url
            payload = None
            if '{id}' in req_url:
                req_url = req_url.replace('{id}', leadid_test.strip())
            elif method == 'GET':
                sep = '&' if '?' in req_url else '?'
                req_url = f"{req_url}{sep}{id_param}={leadid_test.strip()}"
            else:
                payload = {id_param: leadid_test.strip()}

            request_preview = "REQUEST:\\n"
            request_preview += f"{method} {redact_url(req_url)}\\n"
            request_preview += f"Headers: {headers}\\n"
            request_preview += f"Body: {payload if (payload and method != 'GET') else '(none)'}"
            st.code(request_preview, language="http")

            import requests, xml.etree.ElementTree as ET
            r = requests.request(method, req_url, headers=headers, json=payload if (payload and method != 'GET') else None, timeout=30)
            st.write("HTTP status:", r.status_code)
            preview = (r.text or "")[:1000]
            if len(r.text or "") > 1000:
                preview += "..."
            st.text_area("Raw response preview", preview, height=200)

            parsed = {}
            # Try JSON first
            try:
                js = r.json()
            except Exception:
                js = None

            if isinstance(js, dict):
                parsed['status'] = js.get(test_cfg.get('status_field','status'))
                parsed['substatus'] = js.get(test_cfg.get('substatus_field','subStatus'))
                parsed['status_time'] = js.get(test_cfg.get('status_time_field','statusTime'))
                parsed['canonical'] = js.get(test_cfg.get('canonical_id_field','canonicalLeadId'))
                parsed['source'] = 'json'
            else:
                try:
                    root = ET.fromstring(r.text)
                    def find(tag):
                        el = root.find(f'.//{tag}') or root.find(f'.//{tag.lower()}') or root.find(f'.//{tag.upper()}')
                        return (el.text or '').strip() if el is not None and el.text else None
                    parsed['status'] = find(test_cfg.get('status_field','Status'))
                    parsed['substatus'] = find(test_cfg.get('substatus_field','SubStatus')) or find('Reason')
                    parsed['status_time'] = find(test_cfg.get('status_time_field','StatusTime')) or find('UpdatedAt')
                    parsed['canonical'] = find(test_cfg.get('canonical_id_field','canonicalLeadId')) or find('CanonicalLeadId')
                    parsed['source'] = 'xml'
                except Exception as e:
                    parsed['error'] = f"Parse error: {e}"

            st.json(parsed)
    except Exception as e:
        st.error(f"Test failed: {e}")
