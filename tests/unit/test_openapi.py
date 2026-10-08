

# OpenAPI docs

def test_openapi_spec_is_valid(client):
    from openapi_spec_validator import validate

    resp = client.get("/openapi.json")

    assert resp.status_code == 200
    validate(resp.get_json())


def test_openapi_documents_every_route(app, client):
    documented = set()
    for path, item in client.get("/openapi.json").get_json()["paths"].items():
        for method in item:
            if method != "parameters":
                documented.add((path.replace("{user_id}", "<int:user_id>"), method.upper()))

    actual = {
        (rule.rule, method)
        for rule in app.url_map.iter_rules()
        for method in rule.methods - {"HEAD", "OPTIONS"}
        if rule.endpoint not in ("static", "docs.openapi_spec", "docs.docs")
    }

    assert documented == actual


def test_docs_page_points_at_the_spec(client):
    resp = client.get("/docs")

    assert resp.status_code == 200
    assert b"/openapi.json" in resp.data
