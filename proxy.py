from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import requests

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"]
)

API_ENDPOINT = "https://tabakattorneys.lawruler.com/api-legalcrmapp.aspx"
API_KEY = "8A2A55F85D784406B7F79DC286745"

@app.get("/lead_status")
def get_status(lead_id: str):
    url = API_ENDPOINT
    params = {
        "Key": API_KEY,
        "Operation": "GetStatus",
        "ReturnXML": "True",
        "LeadId": lead_id
    }
    resp = requests.get(url, params=params, timeout=15)
    return {"status_code": resp.status_code, "api_url": resp.url, "result": resp.text}

