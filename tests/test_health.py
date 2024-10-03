from tests.initclient import client

def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"kobo-connect": 200,"kobo.ifrc.org": 200}
    