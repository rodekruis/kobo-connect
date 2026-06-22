import sys
import os
import json
from unittest.mock import patch
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from main import app

client = TestClient(app)

with open(os.path.join(os.path.dirname(__file__), "kobo_data.json"), "r") as file:
    kobo_data = json.load(file)

with open(os.path.join(os.path.dirname(__file__), "kobo_headers.json"), "r") as file:
    kobo_headers = json.load(file)

kobo_data["referenceid"] = "test121"


def test_kobo_to_121_payload():

    response = client.post(
        "/kobo-update-121?test_mode=true", headers=kobo_headers, json=kobo_data
    )

    response_data = response.json()
    print(response_data)

    assert response.status_code == 200
    assert "payload" in response_data
    assert response_data == {
        "payload": {
            "data": {"bankaccountnumber": "12345678"},
            "reason": "Validated during field validation",
        }
    }


@patch("routes.routes121.login121")
@patch("routes.routes121.requests.patch")
def test_kobo_update_121_skip_validation(mock_patch, mock_login):
    """Test that skipvalidation=1 skips the validation status PATCH call."""
    mock_login.return_value = "fake_token"

    mock_response = mock_patch.return_value
    mock_response.status_code = 200
    mock_response.content = b'{"message": "updated"}'

    kobo_data_with_skip = kobo_data.copy()
    kobo_data_with_skip["skipvalidation"] = "1"

    response = client.post(
        "/kobo-update-121", headers=kobo_headers, json=kobo_data_with_skip
    )

    assert response.status_code == 200
    assert response.json() == {"message": "Skipping validation status update"}

    # Verify status endpoint was never called
    for call in mock_patch.call_args_list:
        url = call[0][0] if call[0] else call[1].get("url", "")
        assert "registrations/status" not in url
