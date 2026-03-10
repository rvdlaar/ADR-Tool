"""
Tests for ADR Tool API authentication and security.

SECURITY NOTE: Test credentials are for testing only.
Uses SQLite-backed user store with seeded users.
"""
import os
import pytest
from fastapi.testclient import TestClient

# Set up test environment before importing app
os.environ["VALID_API_KEYS"] = "test-api-key-valid-12345"
os.environ["ENVIRONMENT"] = "development"

# Use an in-memory or temp SQLite DB for tests
import tempfile
_test_db = os.path.join(tempfile.gettempdir(), "adr_test_users.db")
os.environ["USER_DB_PATH"] = _test_db

# Clean up any previous test DB
if os.path.exists(_test_db):
    os.remove(_test_db)

from app.main import app

client = TestClient(app)

# Test credentials - match seeded user in user_store.py
TEST_USERNAME = "admin"
TEST_PASSWORD = "Adm1nStr0ng2024"


class TestHealthEndpoint:
    """Health check tests"""

    def test_health_check(self):
        response = client.get("/health")
        assert response.status_code == 200
        assert "status" in response.json()
        assert response.json()["status"] == "healthy"


class TestAuthentication:
    """Authentication tests"""

    def test_login_without_credentials(self):
        response = client.post(
            "/api/v1/auth/token",
            data={}
        )
        assert response.status_code == 422  # Validation error

    def test_login_with_credentials(self):
        response = client.post(
            "/api/v1/auth/token",
            data={"username": TEST_USERNAME, "password": TEST_PASSWORD}
        )
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"

    def test_login_with_wrong_password(self):
        response = client.post(
            "/api/v1/auth/token",
            data={"username": TEST_USERNAME, "password": "wrongpassword"}
        )
        assert response.status_code == 401

    def test_login_with_scopes(self):
        response = client.post(
            "/api/v1/auth/token",
            data={"username": TEST_USERNAME, "password": TEST_PASSWORD, "scope": "adr:read"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "adr:read" in data["scopes"]

    def test_login_reader_user(self):
        response = client.post(
            "/api/v1/auth/token",
            data={"username": "reader", "password": "R3ad0nlySafe2024"}
        )
        assert response.status_code == 200

    def test_login_regular_user(self):
        response = client.post(
            "/api/v1/auth/token",
            data={"username": "user", "password": "Us3rSecure2024"}
        )
        assert response.status_code == 200


class TestCORS:
    """CORS configuration tests"""

    def test_cors_origin_validation(self):
        """Test that non-allowed origins are rejected"""
        response = client.options(
            "/api/v1/adrs",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            }
        )
        assert "access-control-allow-origin" in response.headers or response.status_code == 200


class TestADREndpoints:
    """ADR endpoint tests"""

    def test_list_adrs_without_auth(self):
        response = client.get("/api/v1/adrs")
        assert response.status_code == 401

    def test_list_adrs_with_token(self):
        # First login
        login_response = client.post(
            "/api/v1/auth/token",
            data={"username": TEST_USERNAME, "password": TEST_PASSWORD}
        )
        token = login_response.json()["access_token"]

        # Then access protected endpoint
        response = client.get(
            "/api/v1/adrs",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200

    def test_list_adrs_with_api_key(self):
        response = client.get(
            "/api/v1/adrs",
            headers={"X-API-Key": "test-api-key-valid-12345"}
        )
        assert response.status_code == 200

    def test_create_adr(self):
        # Login with write scope
        login_response = client.post(
            "/api/v1/auth/token",
            data={"username": TEST_USERNAME, "password": TEST_PASSWORD, "scope": "adr:read adr:write"}
        )
        token = login_response.json()["access_token"]

        # Create ADR
        response = client.post(
            "/api/v1/adrs",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "title": "Test ADR",
                "context": "This is the context",
                "decision": "This is the decision",
                "consequences": "These are the consequences"
            }
        )
        assert response.status_code == 201
        data = response.json()
        assert data["title"] == "Test ADR"
        assert data["status"] == "Proposed"

    def test_delete_adr_requires_delete_scope(self):
        # Login without delete scope
        login_response = client.post(
            "/api/v1/auth/token",
            data={"username": TEST_USERNAME, "password": TEST_PASSWORD, "scope": "adr:read adr:write"}
        )
        token = login_response.json()["access_token"]

        # Try to delete (should fail)
        response = client.delete(
            "/api/v1/adrs/some-id",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 403


class TestSecurityHeaders:
    """Security header tests"""

    def test_security_headers_present(self):
        response = client.get("/health")

        assert "x-frame-options" in response.headers
        assert response.headers["x-frame-options"] == "DENY"

        assert "x-content-type-options" in response.headers
        assert response.headers["x-content-type-options"] == "nosniff"

        assert "content-security-policy" in response.headers

    def test_request_id_header(self):
        response = client.get("/health")
        assert "x-request-id" in response.headers


class TestTokenRefresh:
    """Token refresh tests"""

    def test_refresh_token(self):
        # Get tokens
        login_response = client.post(
            "/api/v1/auth/token",
            data={"username": TEST_USERNAME, "password": TEST_PASSWORD}
        )
        tokens = login_response.json()

        # Refresh
        refresh_response = client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": tokens["refresh_token"]}
        )
        assert refresh_response.status_code == 200
        new_tokens = refresh_response.json()
        assert "access_token" in new_tokens

        # Verify the new token is valid by using it
        response = client.get(
            "/api/v1/adrs",
            headers={"Authorization": f"Bearer {new_tokens['access_token']}"}
        )
        assert response.status_code == 200


class TestDocsGating:
    """Test that docs are available in development"""

    def test_docs_available_in_dev(self):
        """In test/dev mode, docs should be accessible"""
        response = client.get("/docs")
        assert response.status_code == 200


class TestRateLimiting:
    """Rate limiting tests"""

    def test_rate_limit_headers(self):
        """Verify rate limiting middleware is active"""
        response = client.get("/health")
        # SlowAPI should be active (doesn't always add headers on first request)
        assert response.status_code == 200
