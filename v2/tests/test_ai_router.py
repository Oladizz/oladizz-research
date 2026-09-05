import numpy as np
import pytest
from unittest.mock import patch, MagicMock
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'utils')))
from ai_router import AIRouter


def test_provider_detection_none():
    router = AIRouter(openai_key="", anthropic_key="", gemini_key="", preferred_provider="")
    assert router.provider == "none"


def test_provider_detection_openai():
    router = AIRouter(openai_key="sk-test-openai", anthropic_key="", gemini_key="")
    assert router.provider == "openai"


def test_provider_detection_anthropic():
    router = AIRouter(openai_key="", anthropic_key="sk-ant-test", gemini_key="")
    assert router.provider == "anthropic"


def test_provider_detection_gemini():
    router = AIRouter(openai_key="", anthropic_key="", gemini_key="AIzaSy-test")
    assert router.provider == "gemini"


def test_preferred_provider_override():
    router = AIRouter(
        openai_key="sk-openai",
        anthropic_key="sk-claude",
        gemini_key="AIza-gemini",
        preferred_provider="claude"
    )
    assert router.provider == "anthropic"

    router_openai = AIRouter(
        openai_key="sk-openai",
        anthropic_key="sk-claude",
        gemini_key="AIza-gemini",
        preferred_provider="chatgpt"
    )
    assert router_openai.provider == "openai"


def test_fallback_to_spacy_when_no_ai():
    router = AIRouter(openai_key="", anthropic_key="", gemini_key="")
    text = "In 2026, Microsoft reported revenue growth of 18% reaching $60 billion in cloud sales."
    claims = router.extract_claims(text, source_url="https://example.com/test", source_domain="example.com")
    assert isinstance(claims, list)
    assert len(claims) >= 1
    assert "Microsoft" in claims[0]["claim"] or "18%" in str(claims[0]["numbers"])


@patch("requests.post")
def test_openai_claim_extraction(mock_post):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [
            {
                "message": {
                    "content": '{"claims": [{"claim": "Company raised $10M in Series A", "subject": "Company", "numbers": ["$10M"]}]}'
                }
            }
        ]
    }
    mock_post.return_value = mock_response

    router = AIRouter(openai_key="sk-mock-key")
    assert router.provider == "openai"

    claims = router.extract_claims("Company raised $10M in Series A", "https://example.com", "example.com")
    assert len(claims) == 1
    assert claims[0]["claim"] == "Company raised $10M in Series A"
    assert claims[0]["numbers"] == ["$10M"]


@patch("requests.post")
def test_claude_claim_extraction(mock_post):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "content": [
            {
                "text": '```json\n{"claims": [{"claim": "Tesla delivered 1.8M vehicles in 2024", "subject": "Tesla", "numbers": ["1.8M", "2024"]}]}\n```'
            }
        ]
    }
    mock_post.return_value = mock_response

    router = AIRouter(anthropic_key="sk-ant-mock-key")
    assert router.provider == "anthropic"

    claims = router.extract_claims("Tesla delivered 1.8M vehicles in 2024", "https://tesla.com", "tesla.com")
    assert len(claims) == 1
    assert "Tesla" in claims[0]["subject"]
    assert "1.8M" in claims[0]["numbers"]


def test_rule_based_contradiction_fallback():
    router = AIRouter(openai_key="", anthropic_key="", gemini_key="")
    claims = [
        {"claim": "Company revenue grew 25%", "subject": "Company", "numbers": ["25%"]},
        {"claim": "Company revenue decreased 10%", "subject": "Company", "numbers": ["10%"]}
    ]
    result = router.check_contradiction(claims)
    assert result["has_contradiction"] is True


def test_provider_labels():
    assert "Zero-AI" in AIRouter().provider_label
    assert "ChatGPT" in AIRouter(openai_key="sk-test").provider_label
    assert "Claude" in AIRouter(anthropic_key="sk-test").provider_label
    assert "Gemini" in AIRouter(gemini_key="AIzaSy-test").provider_label


def test_expand_topic_zero_ai():
    router = AIRouter(openai_key="", anthropic_key="", gemini_key="")
    queries = router.expand_topic("website must have features", count=5)
    assert isinstance(queries, list)
    assert len(queries) >= 1
    assert any("features" in q.lower() or "website" in q.lower() for q in queries)


@patch("requests.post")
def test_expand_topic_openai(mock_post):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "choices": [
            {
                "message": {
                    "content": '{"queries": ["quantum computing roadmap 2026", "fault tolerant qubits progress"]}'
                }
            }
        ]
    }
    mock_post.return_value = mock_resp

    router = AIRouter(openai_key="sk-openai-key")
    queries = router.expand_topic("quantum computing", count=2)
    assert len(queries) == 2
    assert "quantum computing roadmap 2026" in queries


@patch("requests.post")
def test_claude_contradiction_detection(mock_post):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "content": [
            {
                "text": '```json\n{"same_fact": false, "has_contradiction": true, "explanation": "One source says revenue was $5M while another says $3M"}\n```'
            }
        ]
    }
    mock_post.return_value = mock_resp

    router = AIRouter(anthropic_key="sk-ant-key")
    claims = [
        {"claim": "revenue was $5M", "source_domain": "a.com"},
        {"claim": "revenue was $3M", "source_domain": "b.com"}
    ]
    result = router.check_contradiction(claims)
    assert result["has_contradiction"] is True
    assert "One source says revenue" in result["explanation"]

