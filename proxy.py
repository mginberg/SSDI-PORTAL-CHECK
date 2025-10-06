from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import requests

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

API_ENDPOINT = "https://tabakattorneys.lawruler.com/api-legalcrmapp.aspx"
API_KEY = "8A2A55F85D784406B7F79DC286745"

@app.get("/lead_status")
def lead_status(lead_id: str):
    params = {
        "Key": API_KEY,
        "Operation": "GetStatus",
        "ReturnXML": "True",
        "LeadId": lead_id
    }
    resp = requests.get(API_ENDPOINT, params=params, timeout=20)
    return {"status_code": resp.status_code, "result": resp.text, "api_url": resp.url}
