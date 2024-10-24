import sys
import os
import json
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from main import app

client = TestClient(app)

with open(os.path.join(os.path.dirname(__file__), 'kobo_data.json'), 'r') as file:
    kobo_data = json.load(file)

with open(os.path.join(os.path.dirname(__file__), 'kobo_headers.json'), 'r') as file:
    kobo_headers = json.load(file)

kobo_data['referenceid'] = "test121"

def test_kobo_to_121_payload():

    response = client.post(
        "/kobo-update-121?test_mode=true",
        headers=kobo_headers,
        json=kobo_data
    )

    response_data = response.json()
    print(response_data)

    assert response.status_code == 200
    assert "payload" in response_data
    assert response_data == {'payload': {'data': {'bankaccountnumber': '12345678'}, 'reason': 'Validated during field validation'}}
