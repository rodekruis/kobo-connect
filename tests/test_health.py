import sys
import os
from fastapi.testclient import TestClient
from unittest.mock import Mock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from main import app

client = TestClient(app)


@patch("main.requests.get")
def test_health(requests_get):
    mock_response = Mock()
    mock_response.status_code = 200
    requests_get.return_value = mock_response

    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"kobo-connect": 200, "kobo.ifrc.org": 200}
