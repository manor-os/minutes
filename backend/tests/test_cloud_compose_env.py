from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
CLOUD_COMPOSE = REPOSITORY_ROOT / "docker-compose.cloud.yml"
ENV_EXAMPLE = REPOSITORY_ROOT / ".env.example"


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
