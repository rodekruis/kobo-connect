import sys
import os
import json
from fastapi.testclient import TestClient
from dotenv import load_dotenv

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from main import app

client = TestClient(app)

# load environment variables
load_dotenv()
kobotoken = os.environ["TEST_KOBO_TOKEN"]
koboassetid = os.environ["TEST_KOBO_ASSETID"]

with open(os.path.join(os.path.dirname(__file__), 'program121.json'), 'r') as file:
    program121 = json.load(file)

def test_121_program():
    headers = {"kobotoken": kobotoken, "koboasset": koboassetid}
    response = client.get("/121-program?test_mode=true", headers=headers)
    assert response.status_code == 200

    response_data = response.json()
    assert response_data == program121