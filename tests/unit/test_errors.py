import pytest  # noqa: F401


# JSON errors

def test_unknown_route_returns_json(client):
    resp = client.get("/nope")

    assert resp.status_code == 404
    assert resp.get_json() == {"error": "Not Found"}


def test_wrong_method_returns_json(client):
    resp = client.put("/users/1")

    assert resp.status_code == 405
    assert resp.get_json() == {"error": "Method Not Allowed"}


def test_unexpected_error_returns_json(client, db):
    connect, _, _ = db
    connect.side_effect = RuntimeError("boom")

    resp = client.get("/users")

    assert resp.status_code == 500
    assert resp.get_json() == {"error": "Internal server error"}
