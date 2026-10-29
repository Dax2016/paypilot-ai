import pytest
from fastapi.testclient import TestClient

import main


@pytest.fixture
def client():
    return TestClient(main.app)


def test_offers_defaults_to_south_africa(client):
    response = client.get("/api/paypal/offers")

    assert response.status_code == 200
    data = response.json()
    assert data["country_code"] == "ZA"
    assert data["status"] == "no_verified_offers"
    assert data["offers"] == []
    assert data["count"] == 0
    assert data["live_feed_configured"] is False


def test_offers_accepts_two_letter_country_code(client):
    response = client.get("/api/paypal/offers?country_code=US")

    assert response.status_code == 200
    assert response.json()["country_code"] == "US"


@pytest.mark.parametrize("country_code", ["INVALID", "Z", "12", ""])
def test_offers_rejects_invalid_country_code(client, country_code):
    response = client.get(
        "/api/paypal/offers",
        params={"country_code": country_code},
    )
    assert response.status_code == 422


def test_offers_returns_south_africa_official_links(client):
    data = client.get("/api/paypal/offers").json()
    links = data["official_links"]

    assert links["account"] == "https://www.paypal.com/za/webapps/mpp/account-selection"
    assert links["business"] == "https://www.paypal.com/za/business/open-business-account"
    assert links["sign_in"] == "https://www.paypal.com/signin"


def test_other_country_does_not_receive_south_africa_registration_links(client):
    response = client.get("/api/paypal/offers?country_code=US")

    assert response.status_code == 200
    links = response.json()["official_links"]
    assert links["account"] == "https://www.paypal.com/"
    assert links["business"] == "https://www.paypal.com/"
    assert links["sign_in"] == "https://www.paypal.com/signin"
from datetime import datetime, timezone

def test_unverified_offer_is_not_reported_as_confirmed(client, monkeypatch):
    offer = main.PayPalOffer(
        id="za-check",
        title="Offer to check",
        description="Unconfirmed test record.",
        country_codes=["ZA"],
        status="check_official_page",
        source_url="https://www.paypal.com/za/",
        eligibility_notes="Check official terms.",
    )
    monkeypatch.setattr(main, "PAYPAL_OFFERS", [offer])

    data = client.get("/api/paypal/offers?country_code=ZA").json()

    assert data["status"] == "offers_require_verification"
    assert data["verified_count"] == 0
    assert data["unverified_count"] == 1
    assert "not confirmed active promotions" in data["message"]
    assert data["offers"][0]["status"] == "check_official_page"


def test_verified_offer_is_reported_separately(client, monkeypatch):
    now = datetime.now(timezone.utc)
    offer = main.PayPalOffer(
        id="za-verified-test",
        title="Verified test offer",
        description="Synthetic test record; not a real promotion.",
        country_codes=["ZA"],
        status="verified_active",
        source_url="https://www.paypal.com/za/",
        last_verified_at=now,
        eligibility_notes="Test eligibility.",
        discount_claim="Test claim only.",
    )
    monkeypatch.setattr(main, "PAYPAL_OFFERS", [offer])

    data = client.get("/api/paypal/offers?country_code=ZA").json()

    assert data["status"] == "offers_available"
    assert data["verified_count"] == 1
    assert data["unverified_count"] == 0
    assert data["offers"][0]["status"] == "verified_active"
