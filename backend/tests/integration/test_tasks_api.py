def test_create_list_update_delete_task(client, auth_headers):
    resp = client.post(
        "/tasks",
        headers=auth_headers,
        json={"title": "Write README", "priority": "high", "category": "work", "estimated_minutes": 45},
    )
    assert resp.status_code == 201
    task = resp.json()
    assert task["status"] == "pending"
    assert task["sync_version"] >= 1

    resp = client.get("/tasks", headers=auth_headers)
    assert resp.status_code == 200
    assert any(t["id"] == task["id"] for t in resp.json())

    resp = client.patch(f"/tasks/{task['id']}", headers=auth_headers, json={"status": "completed"})
    assert resp.status_code == 200
    updated = resp.json()
    assert updated["status"] == "completed"
    assert updated["completed_at"] is not None
    assert updated["sync_version"] > task["sync_version"]

    resp = client.delete(f"/tasks/{updated['id']}", headers=auth_headers)
    assert resp.status_code == 204

    resp = client.get(f"/tasks/{updated['id']}", headers=auth_headers)
    assert resp.status_code == 404


def test_task_visibility_is_scoped_to_owner(client):
    reg_a = client.post("/auth/register", json={"email": "owner-a@example.com", "password": "password123"})
    reg_b = client.post("/auth/register", json={"email": "owner-b@example.com", "password": "password123"})
    headers_a = {"Authorization": f"Bearer {reg_a.json()['access_token']}"}
    headers_b = {"Authorization": f"Bearer {reg_b.json()['access_token']}"}

    created = client.post("/tasks", headers=headers_a, json={"title": "A's task"}).json()

    resp = client.get(f"/tasks/{created['id']}", headers=headers_b)
    assert resp.status_code == 404

    resp = client.get("/tasks", headers=headers_b)
    assert resp.json() == []
