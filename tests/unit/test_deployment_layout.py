from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_production_overlay_exists_and_qa_overlay_is_gone():
    assert (ROOT / "infra" / "docker-compose.prod.yml").exists()
    assert not (ROOT / "infra" / "docker-compose.qa.yml").exists()


def test_base_compose_is_core_stack_without_local_only_access_agent():
    compose_text = (ROOT / "infra" / "docker-compose.yml").read_text()

    assert "access-agent:" not in compose_text
    assert 'ports:\n      - "5432:5432"' not in compose_text
    assert 'ports:\n      - "6379:6379"' not in compose_text


def test_dev_overlay_carries_local_ports_and_access_agent():
    compose_text = (ROOT / "infra" / "docker-compose.dev.yml").read_text()

    assert "access-agent:" in compose_text
    assert '"5432:5432"' in compose_text
    assert '"6379:6379"' in compose_text
    assert '"8000:8000"' in compose_text


def test_docs_reference_production_overlay_not_qa_overlay():
    readme = (ROOT / "README.md").read_text()
    hosting = (ROOT / "docs" / "qa-hosting.md").read_text()

    assert "docker-compose.prod.yml" in readme
    assert "docker-compose.prod.yml" in hosting
    assert "docker-compose.qa.yml" not in readme


def test_prod_env_example_mentions_everyorg_and_payment_return_urls():
    env_example = (ROOT / "infra" / "prod.env.example").read_text()

    assert "EVERYORG_API_KEY=" in env_example
    assert "EVERYORG_WEBHOOK_TOKEN=" in env_example
    assert "FRONTEND_SUCCESS_URL=https://members.example.org/payments/success" in env_example
    assert "FRONTEND_CANCEL_URL=https://members.example.org/payments/cancel" in env_example
