from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine

from tests.conftest import add_user


def test_me_requires_a_valid_bearer_token(client: TestClient, sync_engine: Engine) -> None:
    token = add_user(sync_engine, name="Pedro")
    assert client.get("/me").status_code == 401
    assert client.get("/me", headers={"Authorization": "Bearer nope"}).status_code == 401
    response = client.get("/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json()["name"] == "Pedro"
    assert response.json()["target_lang"] == "pl-PL"
