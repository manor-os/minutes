from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
CLOUD_COMPOSE = REPOSITORY_ROOT / "docker-compose.cloud.yml"
PROD_COMPOSE = REPOSITORY_ROOT / "docker-compose.prod.yml"
ENV_EXAMPLE = REPOSITORY_ROOT / ".env.example"
NGINX_CONFIG = REPOSITORY_ROOT / "nginx-minutes.conf"


def test_cloud_overlay_does_not_override_env_file_api_keys():
    """The base services load global API keys from .env via env_file."""
    cloud_compose = CLOUD_COMPOSE.read_text()

    assert "- OPENAI_API_KEY=${OPENAI_API_KEY}" not in cloud_compose
    assert "- OPENROUTER_API_KEY=${OPENROUTER_API_KEY}" not in cloud_compose


def test_env_example_uses_openai_variables_for_openrouter():
    env_example = ENV_EXAMPLE.read_text()

    assert "OPENROUTER_API_KEY=" not in env_example
    assert "OPENROUTER_BASE_URL=" not in env_example
    assert "OPENAI_BASE_URL=https://openrouter.ai/api/v1" in env_example


def test_cloud_overlay_allows_only_the_minutes_browser_origin():
    cloud_compose = CLOUD_COMPOSE.read_text()

    assert "- CORS_ORIGINS=https://minutes.manorai.xyz" in cloud_compose
    assert "CORS_ORIGINS=https://minutes.manorai.xyz,http://localhost" not in cloud_compose
    assert "JWT_SECRET must be set for cloud deployment" in cloud_compose


def test_reverse_proxy_enforces_security_headers_without_wildcard_cors():
    nginx_config = NGINX_CONFIG.read_text()

    for header in (
        "Content-Security-Policy",
        "Strict-Transport-Security",
        "X-Content-Type-Options",
        "X-Frame-Options",
        "Referrer-Policy",
        "Permissions-Policy",
    ):
        assert f"add_header {header}" in nginx_config

    assert "Access-Control-Allow-Origin *" not in nginx_config


def test_production_frontend_uses_the_image_nginx_server():
    prod_compose = PROD_COMPOSE.read_text()

    assert "command: null" in prod_compose


def test_frontend_build_contract_never_accepts_admin_credentials():
    dockerfile = (REPOSITORY_ROOT / "phone-recorder" / "Dockerfile").read_text()
    login_component = (
        REPOSITORY_ROOT / "phone-recorder" / "src" / "components" / "Login.jsx"
    ).read_text()

    assert "VITE_DEFAULT_ADMIN_PASSWORD" not in dockerfile
    assert "VITE_DEFAULT_ADMIN_PASSWORD" not in login_component


def test_cloud_initialization_does_not_seed_a_default_admin(monkeypatch):
    from api.routers import auth

    calls = []
    monkeypatch.setattr(auth, "IS_COMMUNITY", False)
    monkeypatch.setattr(auth, "init_users_table", lambda: calls.append("init"))
    monkeypatch.setattr(auth, "seed_default_admin", lambda: calls.append("seed"))

    auth._initialize_local_auth()

    assert calls == ["init"]
