"""OpenAPI 3.0 description of the API, served at /openapi.json and rendered at /docs.

Hand-written to match app.py. test_app.py checks that every route is documented
and that the spec is valid, so it can't silently drift.
"""


def build_spec(default_page_size, max_page_size, phone_max_length, statuses):
    error_ref = {"$ref": "#/components/schemas/Error"}

    def error(description):
        return {"description": description, "content": {"application/json": {"schema": error_ref}}}

    def user_response(description):
        return {"description": description, "content": {"application/json": {"schema": {"$ref": "#/components/schemas/User"}}}}

    user_id = {"name": "user_id", "in": "path", "required": True, "schema": {"type": "integer"}}
    body = lambda schema: {"required": True, "content": {"application/json": {"schema": {"$ref": schema}}}}  # noqa: E731

    return {
        "openapi": "3.0.3",
        "info": {
            "title": "User API",
            "version": "1.0.0",
            "description": "A small Flask + PostgreSQL user API. Every error response is JSON: {\"error\": \"...\"}.",
        },
        "paths": {
            "/": {
                "get": {
                    "summary": "Greeting",
                    "responses": {"200": {"description": "Plain-text greeting", "content": {"text/plain": {"schema": {"type": "string"}}}}},
                }
            },
            "/health": {
                "get": {
                    "summary": "Health check (verifies the database is reachable)",
                    "responses": {
                        "200": {"description": "API and database are up", "content": {"application/json": {"schema": {"$ref": "#/components/schemas/Health"}}}},
                        "503": {"description": "Database unavailable", "content": {"application/json": {"schema": {"$ref": "#/components/schemas/Health"}}}},
                    },
                }
            },
            "/users": {
                "get": {
                    "summary": "List users, ordered by id",
                    "parameters": [
                        {"name": "limit", "in": "query", "schema": {"type": "integer", "minimum": 1, "maximum": max_page_size, "default": default_page_size}},
                        {"name": "offset", "in": "query", "schema": {"type": "integer", "minimum": 0, "default": 0}},
                    ],
                    "responses": {
                        "200": {"description": "One page of users", "content": {"application/json": {"schema": {"$ref": "#/components/schemas/UserPage"}}}},
                        "400": error("Invalid limit or offset"),
                    },
                },
                "post": {
                    "summary": "Create a user",
                    "requestBody": body("#/components/schemas/UserInput"),
                    "responses": {
                        "201": user_response("The created user"),
                        "400": error("Invalid payload"),
                        "409": error("Email already exists (case-insensitive)"),
                    },
                },
            },
            "/users/{user_id}": {
                "parameters": [user_id],
                "get": {
                    "summary": "Get a user",
                    "responses": {"200": user_response("The user"), "404": error("User not found")},
                },
                "patch": {
                    "summary": "Update selected fields of a user (also writes a user_updated audit row)",
                    "requestBody": body("#/components/schemas/UserUpdate"),
                    "responses": {
                        "200": user_response("The updated user"),
                        "400": error("Invalid payload"),
                        "404": error("User not found"),
                        "409": error("Email already exists (case-insensitive)"),
                        "500": error("Update or audit log write failed; nothing was changed"),
                    },
                },
                "delete": {
                    "summary": "Delete a user",
                    "responses": {
                        "200": {
                            "description": "The deleted user",
                            "content": {"application/json": {"schema": {
                                "type": "object",
                                "properties": {"message": {"type": "string"}, "user": {"$ref": "#/components/schemas/User"}},
                            }}},
                        },
                        "404": error("User not found"),
                    },
                },
            },
        },
        "components": {
            "schemas": {
                "Error": {"type": "object", "properties": {"error": {"type": "string"}}, "required": ["error"]},
                "Health": {
                    "type": "object",
                    "properties": {"status": {"type": "string", "enum": ["ok", "error"]}, "database": {"type": "string", "enum": ["ok", "unavailable"]}},
                },
                "User": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "integer"},
                        "name": {"type": "string"},
                        "email": {"type": "string", "format": "email"},
                        "status": {"type": "string", "enum": statuses},
                        "role": {"type": "string", "nullable": True},
                        "phone": {"type": "string", "nullable": True, "maxLength": phone_max_length},
                    },
                    "required": ["id", "name", "email", "status"],
                },
                "UserInput": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "minLength": 1},
                        "email": {"type": "string", "format": "email"},
                        "status": {"type": "string", "enum": statuses, "default": "active"},
                        "role": {"type": "string", "nullable": True},
                        "phone": {"type": "string", "nullable": True, "maxLength": phone_max_length},
                    },
                    "required": ["name", "email"],
                    "additionalProperties": False,
                    "example": {"name": "Ada Lovelace", "email": "ada@example.com", "role": "admin"},
                },
                "UserUpdate": {
                    "type": "object",
                    "description": "Any non-empty subset of the user fields.",
                    "minProperties": 1,
                    "properties": {
                        "name": {"type": "string", "minLength": 1},
                        "email": {"type": "string", "format": "email"},
                        "status": {"type": "string", "enum": statuses},
                        "role": {"type": "string", "nullable": True},
                        "phone": {"type": "string", "nullable": True, "maxLength": phone_max_length},
                    },
                    "additionalProperties": False,
                    "example": {"status": "inactive"},
                },
                "UserPage": {
                    "type": "object",
                    "properties": {
                        "total": {"type": "integer", "description": "Total users across all pages"},
                        "limit": {"type": "integer"},
                        "offset": {"type": "integer"},
                        "users": {"type": "array", "items": {"$ref": "#/components/schemas/User"}},
                    },
                },
            }
        },
    }


# Swagger UI is loaded from a CDN, so no extra dependency is needed in the image.
DOCS_HTML = """<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>User API docs</title>
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5.17.14/swagger-ui.css">
</head>
<body>
  <div id="swagger-ui"></div>
  <script src="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5.17.14/swagger-ui-bundle.js"></script>
  <script>SwaggerUIBundle({url: "/openapi.json", dom_id: "#swagger-ui"});</script>
</body>
</html>
"""
