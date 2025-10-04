
import re, json, pandas as pd
import datetime as dt
import requests
from pathlib import Path

def norm_phone(x):
    if pd.isna(x): 
        return ""
    s = re.sub(r"\D", "", str(x))
    if not s: 
        return ""
    if len(s) == 11 and s.startswith("1"):
        return f"+{s}"
    if len(s) == 10:
        return f"+1{s}"
    return f"+{s}"

def extract_lead_id(text):
    if pd.isna(text): 
        return ""
    m = re.search(r'Lead ID.*?(\d+)', str(text), flags=re.I|re.S)
    if m:
        return m.group(1)
    m2 = re.search(r'Success\s+Lead\s+#\s*(\d+)', str(text), flags=re.I)
    return m2.group(1) if m2 else ""

def parse_zap_export(zap_csv_path):
    df = pd.read_csv(zap_csv_path, dtype=str)
    # heuristics: look for a column that contains "output__" and "__text"
    out_cols = [c for c in df.columns if c.startswith("output__") and c.endswith("__text")]
    if not out_cols:
        raise RuntimeError("Could not find a Zap export output text column")
    out_col = out_cols[-1]
    df['crm_lead_id'] = df[out_col].apply(extract_lead_id)

    # find phoneish columns (input data or querystring)
    phone_cols = [c for c in df.columns if c.lower().endswith('__data__cellphone') or c.lower().endswith('__querystring__cellphone') or c.lower().endswith('__data__phone') or c.lower().endswith('__querystring__phone')]
    df['raw_phone'] = ''
    for col in phone_cols:
        df['raw_phone'] = df['raw_phone'].where(df['raw_phone']!='', df[col].fillna(''))

    df['phone_e164'] = df['raw_phone'].apply(norm_phone)
    df['zap_ts'] = pd.to_datetime(df['date'], errors='coerce')
    df['zap_date'] = df['zap_ts'].dt.date.astype('string')
    return df

def merge_call_log_with_leadids(call_log_csv, zap_csv, out_csv, 
                                call_phone_col='phone', call_time_col='call_started_at', call_transferid_col='transfer_id'):
    calls = pd.read_csv(call_log_csv, dtype=str)
    z = parse_zap_export(zap_csv)
    # build reduced map
    lead_map = z[['phone_e164','zap_date','crm_lead_id']].copy()
    lead_map = lead_map[lead_map['crm_lead_id'].astype(str).str.len()>0]
    # normalize phones in call log
    if call_phone_col not in calls.columns:
        # try a few common variants
        for cand in ['phone_e164','Phone','CellPhone','CallerPhone','ANI','phone']:
            if cand in calls.columns:
                call_phone_col = cand
                break
    calls['phone_e164'] = calls[call_phone_col].map(norm_phone)
    # compute call_date from call_time_col
    if call_time_col in calls.columns:
        calls['call_date'] = pd.to_datetime(calls[call_time_col], errors='coerce').dt.date.astype('string')
    else:
        calls['call_date'] = None

    # primary join: phone + date
    merged = calls.merge(lead_map, left_on=['phone_e164','call_date'], right_on=['phone_e164','zap_date'], how='left')
    merged.drop(columns=['zap_date'], inplace=True, errors='ignore')

    # if transfer_id present in both sources, attempt a secondary more exact join
    if call_transferid_col in calls.columns:
        # if zap export had transfer ids in inputs, you can add code to parse here if available
        pass

    merged.to_csv(out_csv, index=False)
    return merged

def load_vendor_configs(vendors_json_path):
    with open(vendors_json_path, 'r', encoding='utf-8') as f:
        return json.load(f)

def normalize_status(raw, status_map):
    s = str(raw or '').upper()
    return status_map.get(s, 'OPEN')

def compute_billable(status, billable_list=None):
    bl = set(billable_list or ['SIGNED','QUALIFIED','APPT_SET'])
    if status in bl:
        return 'Y'
    if status in ['DUPLICATE','BAD_NUMBER','NQ']:
        return 'N'
    return ''

def fetch_status_for_row(row, vendor_cfg):
    lead_id = row.get('crm_lead_id') or row.get('crm_lead_id_canonical')
    if not lead_id:
        return None
    method = vendor_cfg.get('method','GET').upper()
    url = vendor_cfg.get('url','')
    id_param = vendor_cfg.get('id_param','leadId')
    headers = vendor_cfg.get('auth_header',{})
    extra = vendor_cfg.get('extra_headers',{})
    headers.update(extra)

    req_url = url
    data = None
    if '{id}' in req_url:
        req_url = req_url.replace('{id}', requests.utils.quote(str(lead_id)))
    elif method == 'GET':
        sep = '&' if '?' in req_url else '?'
        req_url = f"{req_url}{sep}{id_param}={requests.utils.quote(str(lead_id))}"
    else:
        data = {id_param: lead_id}

    resp = requests.request(method, req_url, headers=headers, json=data if data and method!='GET' else None, timeout=30)
    resp.raise_for_status()
    try:
        js = resp.json()
    except Exception:
        js = {'raw': resp.text}

    raw_status = js.get(vendor_cfg.get('status_field','status'))
    sub = js.get(vendor_cfg.get('substatus_field','subStatus'))
    ts_field = vendor_cfg.get('status_time_field','statusTime')
    stime = js.get(ts_field)
    canonical = js.get(vendor_cfg.get('canonical_id_field','canonicalLeadId'))

    status = normalize_status(raw_status, vendor_cfg.get('status_map',{}))
    billable = compute_billable(status, vendor_cfg.get('billable_statuses',['SIGNED','QUALIFIED','APPT_SET']))
    return {'status': status, 'substatus': sub, 'status_time': stime, 'canonical': canonical, 'billable_flag': billable, 'raw': js}

def update_statuses(merged_csv_in, vendors_json, out_csv=None):
    df = pd.read_csv(merged_csv_in, dtype=str)
    cfgs = load_vendor_configs(vendors_json)
    # Expect a 'vendor_code' column to choose which config to use; else use single vendor in cfgs
    single_vendor = None
    if len(cfgs)==1:
        single_vendor = list(cfgs.keys())[0]
    statuses = []
    for i, row in df.iterrows():
        vcode = row.get('vendor_code') or single_vendor
        if not vcode or vcode not in cfgs:
            statuses.append({})
            continue
        try:
            res = fetch_status_for_row(row, cfgs[vcode])
        except Exception as e:
            res = {'status':'OPEN','substatus':f'ERR {e}','status_time':None,'canonical':None,'billable_flag':''}
        statuses.append(res or {})
    stat_df = pd.DataFrame(statuses)
    out = pd.concat([df.reset_index(drop=True), stat_df], axis=1)
    if out_csv:
        out.to_csv(out_csv, index=False)
    return out

if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Transfer Bot: merge Zap export with call logs, then fetch statuses.")
    ap.add_argument("--call_log", help="Path to call log CSV", required=True)
    ap.add_argument("--zap_export", help="Path to Zapier export CSV", required=True)
    ap.add_argument("--vendors", help="Path to vendors.json for status API", required=False)
    ap.add_argument("--out_merged", help="Output merged CSV path", default="merged_with_leadids.csv")
    ap.add_argument("--out_status", help="Output status CSV path (after calling APIs)", default="merged_with_status.csv")
    ap.add_argument("--call_phone_col", default="phone", help="Phone column name in call log")
    ap.add_argument("--call_time_col", default="call_started_at", help="Timestamp column in call log")
    ap.add_argument("--call_transferid_col", default="transfer_id", help="Transfer ID column in call log")
    args = ap.parse_args()

    merged = merge_call_log_with_leadids(args.call_log, args.zap_export, args.out_merged,
                                         call_phone_col=args.call_phone_col,
                                         call_time_col=args.call_time_col,
                                         call_transferid_col=args.call_transferid_col)
    print(f"Merged saved to {args.out_merged} with {len(merged)} rows.")
    if args.vendors:
        out = update_statuses(args.out_merged, args.vendors, args.out_status)
        print(f"Statuses saved to {args.out_status} ({len(out)} rows).")
    else:
        print("No vendors.json provided; skipping status fetch.")
