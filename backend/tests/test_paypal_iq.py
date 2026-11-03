import pytest
from fastapi.testclient import TestClient
import main


@pytest.fixture
def client(tmp_path, monkeypatch):
    test_db = tmp_path / "test_paypal_iq.db"
    monkeypatch.setattr(main, "DATABASE_PATH", test_db)
    main.init_database()

    with main._login_attempts_lock:
        main._login_attempts.clear()

    with TestClient(main.app) as test_client:
        yield test_client


@pytest.mark.parametrize(
    ("method", "url", "body"),
    [
        ("GET", "/api/paypal-iq/daily", None),
        ("GET", "/api/paypal-iq/facts", None),
        ("GET", "/api/paypal-iq/facts/test-fact", None),
        ("GET", "/api/paypal-iq/quiz", None),
        ("POST", "/api/paypal-iq/quiz/submit", {
            "question_id": "test-question",
            "selected_option": "A",
        }),
        ("GET", "/api/paypal-iq/progress", None),
        ("GET", "/api/paypal-iq/categories", None),
    ],
)
def test_paypal_iq_endpoints_require_authentication(client, method, url, body):
    response = client.request(method, url, json=body)
    assert response.status_code == 401

def create_customer(client):
    response = client.post(
        "/api/auth/signup",
        json={
            "email": "iq-learner@example.com",
            "password": "StrongPassword123!",
        },
    )
    assert response.status_code == 201
    return {
        "Authorization": f"Bearer {response.json()['access_token']}"
    }


def insert_fact(
    fact_code,
    country_scope="GLOBAL",
    country_code=None,
    status="PUBLISHED",
):
    with main.database_connection() as connection:
        fact_id = f"fact-{fact_code}"
        connection.execute(
            """
            INSERT INTO paypal_iq_facts (
                id, fact_code, title, fact_text, explanation,
                category, country_scope, country_code,
                source_url, source_title, source_type,
                source_excerpt, difficulty, status,
                verified_at, review_at, fact_version,
                created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                fact_id, fact_code, f"Title {fact_code}",
                f"Verified fact text for {fact_code}.",
                f"Explanation for {fact_code}.",
                "PAYMENTS", country_scope, country_code,
                "https://example.com/source",
                "Official source", "OFFICIAL",
                "Verified source excerpt", "BEGINNER", status,
                "2026-10-01", "2026-11-01", 1,
                "2026-10-01T00:00:00+00:00",
                "2026-10-01T00:00:00+00:00",
            ),
        )
    return fact_id


def insert_question(fact_id, question_id="question-1"):
    with main.database_connection() as connection:
        connection.execute(
            """
            INSERT INTO paypal_iq_questions (
                id, fact_id, question, options_json,
                correct_option, explanation, difficulty,
                status, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                question_id, fact_id,
                "Which option is the correct answer?",
                '["A", "B", "C", "D"]',
                "B", "This is the verified explanation.",
                "BEGINNER", "PUBLISHED",
                "2026-10-01T00:00:00+00:00",
                "2026-10-01T00:00:00+00:00",
            ),
        )


def test_daily_fact_is_awarded_only_once(client, monkeypatch):
    headers = create_customer(client)
    monkeypatch.setattr(main, "paypal_iq_local_date", lambda: "2026-11-03")
    insert_fact("DAILY")

    first = client.get("/api/paypal-iq/daily", headers=headers)
    second = client.get("/api/paypal-iq/daily", headers=headers)

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["fact"]["id"] == second.json()["fact"]["id"]
    assert first.json()["progress"]["total_points"] == 2
    assert second.json()["progress"]["total_points"] == 2
    assert second.json()["progress"]["facts_viewed"] == 1


def test_facts_only_include_global_and_south_african_published(
    client,
):
    headers = create_customer(client)
    insert_fact("GLOBAL")
    insert_fact("ZA", "COUNTRY", "ZA")
    insert_fact("US", "COUNTRY", "US")
    insert_fact("DRAFT", status="DRAFT")

    response = client.get("/api/paypal-iq/facts", headers=headers)

    assert response.status_code == 200
    codes = {item["fact_code"] for item in response.json()["items"]}
    assert codes == {"GLOBAL", "ZA"}


def test_fact_detail_hides_unavailable_country_fact(client):
    headers = create_customer(client)
    foreign_id = insert_fact("FOREIGN", "COUNTRY", "US")

    response = client.get(
        f"/api/paypal-iq/facts/{foreign_id}",
        headers=headers,
    )

    assert response.status_code == 404


def test_quiz_does_not_expose_answers_before_submission(client):
    headers = create_customer(client)
    fact_id = insert_fact("QUIZ")
    insert_question(fact_id)

    response = client.get("/api/paypal-iq/quiz", headers=headers)

    assert response.status_code == 200
    question = response.json()["questions"][0]
    assert question["id"] == "question-1"
    assert question["options"] == ["A", "B", "C", "D"]
    assert "correct_option" not in question
    assert "explanation" not in question


def test_quiz_submission_awards_points_and_prevents_duplicate(
    client, monkeypatch
):
    headers = create_customer(client)
    monkeypatch.setattr(main, "paypal_iq_local_date", lambda: "2026-11-03")
    fact_id = insert_fact("SCORE")
    insert_question(fact_id)

    submitted = client.post(
        "/api/paypal-iq/quiz/submit",
        headers=headers,
        json={"question_id": "question-1", "selected_option": "B"},
    )

    assert submitted.status_code == 200
    result = submitted.json()
    assert result["is_correct"] is True
    assert result["points_awarded"] == 10
    assert result["correct_option"] == "B"
    assert result["explanation"] == "This is the verified explanation."
    assert result["progress"]["total_points"] == 10

    duplicate = client.post(
        "/api/paypal-iq/quiz/submit",
        headers=headers,
        json={"question_id": "question-1", "selected_option": "B"},
    )
    assert duplicate.status_code == 409


def test_invalid_quiz_option_is_rejected(client):
    headers = create_customer(client)
    fact_id = insert_fact("INVALID")
    insert_question(fact_id)

    response = client.post(
        "/api/paypal-iq/quiz/submit",
        headers=headers,
        json={"question_id": "question-1", "selected_option": "Z"},
    )

    assert response.status_code == 400


def test_progress_starts_at_zero(client):
    headers = create_customer(client)

    response = client.get("/api/paypal-iq/progress", headers=headers)

    assert response.status_code == 200
    assert response.json()["progress"]["total_points"] == 0
    assert response.json()["progress"]["facts_viewed"] == 0
    assert response.json()["progress"]["current_streak"] == 0


def test_categories_only_include_published_eligible_facts(client):
    headers = create_customer(client)
    insert_fact("CAT-GLOBAL")
    insert_fact("CAT-ZA", "COUNTRY", "ZA")
    insert_fact("CAT-US", "COUNTRY", "US")

    response = client.get(
        "/api/paypal-iq/categories",
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["categories"] == ["PAYMENTS"]
