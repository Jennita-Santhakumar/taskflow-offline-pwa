def test_register_and_login(client):
    resp = client.post("/auth/register", json={"email": "a@example.com", "password": "password123"})
    assert resp.status_code == 201
    body = resp.json()
    assert "access_token" in body and "refresh_token" in body

    resp = client.post("/auth/login", json={"email": "a@example.com", "password": "password123"})
    assert resp.status_code == 200

    resp = client.post("/auth/login", json={"email": "a@example.com", "password": "wrong"})
    assert resp.status_code == 401


def test_register_duplicate_email_conflicts(client):
    client.post("/auth/register", json={"email": "dup@example.com", "password": "password123"})
    resp = client.post("/auth/register", json={"email": "dup@example.com", "password": "password123"})
    assert resp.status_code == 409


def test_me_requires_auth(client):
    assert client.get("/auth/me").status_code == 401


def test_me_with_valid_token(client, auth_headers):
    resp = client.get("/auth/me", headers=auth_headers)
    assert resp.status_code == 200
    assert "email" in resp.json()


def test_refresh_rotates_token_and_old_one_stops_working(client):
    reg = client.post("/auth/register", json={"email": "rot@example.com", "password": "password123"})
    tokens = reg.json()

    resp = client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert resp.status_code == 200
    new_tokens = resp.json()
    assert new_tokens["access_token"] != tokens["access_token"]

    # the original refresh token was revoked on use
    resp2 = client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert resp2.status_code == 401
