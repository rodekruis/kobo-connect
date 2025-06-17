import sys
import os
import json
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from main import app

client = TestClient(app)

with open(os.path.join(os.path.dirname(__file__), "kobo_data_espo.json"), "r") as file:
    kobo_data = json.load(file)

with open(
    os.path.join(os.path.dirname(__file__), "kobo_headers_espo.json"), "r"
) as file:
    kobo_headers = json.load(file)
kobo_headers["targeturl"] = os.environ["TEST_ESPOCRM_URL"]
kobo_headers["targetkey"] = os.environ["TEST_ESPOCRM_KEY"]


def test_kobo_to_espo_payload():

    response = client.post("/kobo-to-espocrm", headers=kobo_headers, json=kobo_data)

    assert response.status_code == 200
