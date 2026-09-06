import os
import sys
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'utils')))
from search_engine import MultiSearchEngine, normalize_url


def test_normalize_url():
    # Test tracking param stripping
    url1 = "https://www.example.com/article/?utm_source=twitter&utm_medium=social&fbclid=123"
    assert normalize_url(url1) == "https://example.com/article"

    # Test trailing slash and www removal
    url2 = "http://www.sub.example.org/path/to/page/"
    assert normalize_url(url2) == "http://sub.example.org/path/to/page"

    # Test fragment/anchor removal
    url3 = "https://example.com/docs#installation"
    assert normalize_url(url3) == "https://example.com/docs"

    # Test non-http / invalid
    assert normalize_url("javascript:void(0)") == ""
    assert normalize_url("") == ""


def test_search_google_no_keys():
    engine = MultiSearchEngine(google_api_key="", google_engine_id="")
    assert engine.search_google("quantum computing") == []


@patch("requests.get")
def test_search_google_success(mock_get):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "items": [
            {"link": "https://www.nature.com/articles/s41586-024-001?utm_source=google"},
            {"link": "https://arxiv.org/abs/2401.00001"}
        ]
    }
    mock_get.return_value = mock_resp

    engine = MultiSearchEngine(google_api_key="mock_key", google_engine_id="mock_cx")
    urls = engine.search_google("quantum computing", max_results=2)

    assert len(urls) == 2
    assert urls[0] == "https://nature.com/articles/s41586-024-001"
    assert urls[1] == "https://arxiv.org/abs/2401.00001"


@patch("requests.post")
def test_search_duckduckgo_fallback(mock_post):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = """
    <html>
        <body>
            <a class="result__url" href="//www.bbc.com/news/technology-12345">BBC</a>
            <a class="result__url" href="https://reuters.com/tech/chip-breakthrough/">Reuters</a>
        </body>
    </html>
    """
    mock_post.return_value = mock_resp

    engine = MultiSearchEngine()
    urls = engine.search_duckduckgo("chips", max_results=5)
    assert len(urls) == 2
    assert urls[0] == "https://bbc.com/news/technology-12345"
    assert urls[1] == "https://reuters.com/tech/chip-breakthrough"


@patch("requests.get")
def test_search_wikipedia_fallback(mock_get):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "query": {
            "search": [
                {"title": "Solid-state battery"},
                {"title": "Lithium-ion battery"}
            ]
        }
    }
    mock_get.return_value = mock_resp

    engine = MultiSearchEngine()
    urls = engine.search_wikipedia("solid state battery", max_results=2)
    assert len(urls) == 2
    assert urls[0] == "https://en.wikipedia.org/wiki/Solid-state_battery"
    assert urls[1] == "https://en.wikipedia.org/wiki/Lithium-ion_battery"


@patch("requests.get")
def test_search_arxiv_fallback(mock_get):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = """<?xml version="1.0" encoding="UTF-8"?>
    <feed xmlns="http://www.w3.org/2005/Atom">
        <entry>
            <id>http://arxiv.org/abs/2405.12345v1</id>
            <title>Advances in Solid State Physics</title>
        </entry>
    </feed>
    """
    mock_get.return_value = mock_resp

    engine = MultiSearchEngine()
    urls = engine.search_arxiv("solid state physics", max_results=1)
    assert len(urls) == 1
    assert "arxiv.org/abs/2405.12345v1" in urls[0]


@patch("requests.get")
def test_search_pubmed_fallback(mock_get):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "esearchresult": {
            "idlist": ["1234567", "7654321"]
        }
    }
    mock_get.return_value = mock_resp

    engine = MultiSearchEngine()
    urls = engine.search_pubmed("crispr gene therapy", max_results=2)
    assert len(urls) == 2
    assert urls[0] == "https://www.ncbi.nlm.nih.gov/pmc/articles/PMC1234567/"


@patch.object(MultiSearchEngine, "search_duckduckgo")
@patch.object(MultiSearchEngine, "search_wikipedia")
def test_multi_engine_discover(mock_wiki, mock_ddg):
    mock_ddg.return_value = ["https://example.com/post1"]
    mock_wiki.return_value = ["https://en.wikipedia.org/wiki/Post2"]

    engine = MultiSearchEngine(google_api_key="", google_engine_id="")
    discovered = engine.discover("sample query", target_count=2)

    assert len(discovered) == 2
    assert "https://example.com/post1" in discovered
    assert "https://en.wikipedia.org/wiki/Post2" in discovered
