from datetime import datetime, timedelta, timezone


def test_push_new_task_then_pull_incremental(client, auth_headers):
    now = datetime.now(timezone.utc).isoformat()
    resp = client.post(
        "/sync/push",
        headers=auth_headers,
        json={
            "device_id": "device-a",
            "items": [
                {
                    "client_id": "local-1",
                    "op": "upsert",
                    "title": "Offline created task",
                    "priority": "urgent",
                    "category": "work",
                    "status": "pending",
                    "updated_at": now,
                }
            ],
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["results"][0]["status"] == "applied"
    server_id = body["results"][0]["server_id"]

    pull = client.get("/sync/pull", headers=auth_headers, params={"device_id": "device-a", "since": 0})
    assert pull.status_code == 200
    pulled = pull.json()
    assert any(t["id"] == server_id for t in pulled["tasks"])

    # a second pull with the returned cursor should come back empty (nothing new since)
    pull2 = client.get(
        "/sync/pull", headers=auth_headers, params={"device_id": "device-a", "since": pulled["sync_version"]}
    )
    assert pull2.json()["tasks"] == []


def test_push_conflict_last_write_wins(client, auth_headers):
    now = datetime.now(timezone.utc)
    created = client.post("/tasks", headers=auth_headers, json={"title": "Original title"}).json()

    # simulate an offline device pushing a STALE edit (updated_at before the server's current
    # updated_at) -- the server's newer state must win, not the stale offline edit.
    stale_time = (now - timedelta(hours=1)).isoformat()
    resp = client.post(
        "/sync/push",
        headers=auth_headers,
        json={
            "device_id": "device-b",
            "items": [
                {
                    "client_id": "local-stale",
                    "op": "upsert",
                    "id": created["id"],
                    "title": "Stale offline edit",
                    "updated_at": stale_time,
                }
            ],
        },
    )
    assert resp.status_code == 200
    result = resp.json()["results"][0]
    assert result["status"] == "conflict_resolved_remote_wins"

    current = client.get(f"/tasks/{created['id']}", headers=auth_headers).json()
    assert current["title"] == "Original title"

    # a genuinely newer offline edit DOES win
    newer_time = (now + timedelta(hours=1)).isoformat()
    resp2 = client.post(
        "/sync/push",
        headers=auth_headers,
        json={
            "device_id": "device-b",
            "items": [
                {
                    "client_id": "local-fresh",
                    "op": "upsert",
                    "id": created["id"],
                    "title": "Fresher offline edit",
                    "updated_at": newer_time,
                }
            ],
        },
    )
    assert resp2.json()["results"][0]["status"] == "applied"
    current2 = client.get(f"/tasks/{created['id']}", headers=auth_headers).json()
    assert current2["title"] == "Fresher offline edit"


def test_push_delete(client, auth_headers):
    created = client.post("/tasks", headers=auth_headers, json={"title": "To be deleted offline"}).json()
    now = datetime.now(timezone.utc).isoformat()
    resp = client.post(
        "/sync/push",
        headers=auth_headers,
        json={"device_id": "device-c", "items": [{"client_id": "x", "op": "delete", "id": created["id"], "updated_at": now}]},
    )
    assert resp.json()["results"][0]["status"] == "applied"
    assert client.get(f"/tasks/{created['id']}", headers=auth_headers).status_code == 404
