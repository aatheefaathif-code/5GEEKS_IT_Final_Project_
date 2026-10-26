from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)


def test_coloring_activity_lists_only_verified_grade_one_pages():
    response = client.get(
        "/api/v1/learning/coloring-pages",
        params={
            "grade": 1,
            "medium": "English",
            "subject": "English Language",
        },
    )

    assert response.status_code == 200
    activities = response.json()
    assert activities
    matching = next(
        activity
        for activity in activities
        if activity["textbook_id"] == "tb-f69545b60850661d"
        and activity["exercise_page"] == 3
    )
    assert matching["reference_page"] == 2
    assert matching["grade"] == 1
    assert matching["medium"] == "English"
    assert matching["subject"] == "English Language"


def test_coloring_activity_rejects_unlisted_or_unverified_pages():
    response = client.get(
        "/api/v1/learning/coloring-pages/tb-f69545b60850661d/4.png",
        params={"kind": "exercise"},
    )

    assert response.status_code == 404


def test_coloring_activity_renders_real_verified_textbook_page():
    response = client.get(
        "/api/v1/learning/coloring-pages/tb-f69545b60850661d/3.png",
        params={"kind": "reference"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert response.content.startswith(b"\x89PNG\r\n\x1a\n")
