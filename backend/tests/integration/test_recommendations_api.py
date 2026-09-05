from datetime import datetime, timedelta, timezone


def test_recommendations_ranks_urgent_overdue_above_low_priority(client, auth_headers):
    now = datetime.now(timezone.utc)
    client.post(
        "/tasks",
        headers=auth_headers,
        json={
            "title": "Low priority, far due date",
            "priority": "low",
            "due_date": (now + timedelta(days=30)).isoformat(),
            "estimated_minutes": 30,
        },
    )
    urgent = client.post(
        "/tasks",
        headers=auth_headers,
        json={
            "title": "Urgent, overdue",
            "priority": "urgent",
            "due_date": (now - timedelta(days=1)).isoformat(),
            "estimated_minutes": 30,
        },
    ).json()

    resp = client.get("/recommendations/next-tasks", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["items"]) == 2
    assert body["items"][0]["task_id"] == urgent["id"]
    assert body["items"][0]["rank"] == 1


def test_recommendations_are_cached_until_task_state_changes(client, auth_headers):
    client.post("/tasks", headers=auth_headers, json={"title": "Some task"})

    first = client.get("/recommendations/next-tasks", headers=auth_headers).json()
    assert first["cached"] is False
    second = client.get("/recommendations/next-tasks", headers=auth_headers).json()
    assert second["cached"] is True

    client.post("/tasks", headers=auth_headers, json={"title": "Another task"})
    third = client.get("/recommendations/next-tasks", headers=auth_headers).json()
    assert third["cached"] is False


def test_recommendations_empty_when_no_open_tasks(client, auth_headers):
    resp = client.get("/recommendations/next-tasks", headers=auth_headers)
    assert resp.json()["items"] == []
