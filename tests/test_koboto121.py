import sys
import os
import json
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from main import app

client = TestClient(app)

with open(os.path.join(os.path.dirname(__file__), "kobo_data.json"), "r") as file:
    kobo_data = json.load(file)

with open(os.path.join(os.path.dirname(__file__), "kobo_headers.json"), "r") as file:
    kobo_headers = json.load(file)


def test_kobo_to_121_payload():

    response = client.post(
        "/kobo-to-121?test_mode=true", headers=kobo_headers, json=kobo_data
    )

    response_data = response.json()

    assert response.status_code == 200
    assert "payload" in response_data

    payload = response_data["payload"]

    assert payload["bankaccountnumber"] == "12345678"
    assert payload["birthYear"] == "1600"
    assert payload["date"] == "2024-04-16"
    assert payload["deputyMain"] == "Beneficiary"
    assert payload["programFspConfigurationName"] == "Excel"
    assert payload["fullName"] == "asdf"
    assert payload["maxPayments"] == 5
    assert payload["NRC"] == "12345"
    assert (
        payload["NRCpicture"]
        == "https://kc.ifrc.org/media/large?media_file=user%2Fattachments%2F118047ed44ed4896b3e6c443736442c6%2F7e7b954f-83e6-406f-9335-368ae153f1aa%2FOrka-14_36_18.jpg"
    )
    assert payload["phoneNumber"] == "0612345678"
    assert payload["preferredLanguage"] == "en"
    assert payload["selectionCriteria"] == "Disabled"
    assert payload["sex"] == "Female"
    assert payload["wardName"] == "Sinazongwe"
    assert payload["zrcsName"] == "adsf"
    assert payload["referenceId"] == "7e7b954f-83easdfadsfasdfadsfad"


def test_kobo_to_121_skipconnect():
    payload = kobo_data.copy()
    payload["skipconnect"] = "1"
    headers = kobo_headers.copy()
    headers["skipconnect"] = "skipconnect"

    response = client.post("/kobo-to-121", headers=headers, json=payload)

    assert response.status_code == 200
    assert response.json() == {"message": "Skipping connection to 121"}
