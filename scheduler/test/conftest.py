import pytest
import requests


@pytest.fixture(scope="module")
def root() -> str:
    return "https://api.cardshop.hotspot.kiwix.org"


@pytest.fixture(scope="class")
def authorize(root):
    response = requests.post(
        url=root + "/auth/authorize",
        headers={"username": "admin", "password": "admin_pass"},
    )
    return response.json()


@pytest.fixture(scope="class")
def access_token(authorize):
    return authorize["access_token"]


@pytest.fixture(scope="class")
def refresh_token(authorize):
    return authorize["refresh_token"]
