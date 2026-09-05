import numpy as np
import pytest

@pytest.fixture
def sample_claims():
    return [
        {"claim": "Revenue grew 45% in 2024", "subject": "Revenue", "numbers": ["45%", "2024"], "source_domain": "example.com", "source_url": "http://example.com"},
        {"claim": "The company raised $5 million", "subject": "Funding", "numbers": ["$5 million"], "source_domain": "news.com", "source_url": "http://news.com/1"},
        {"claim": "Over 10,000 active users", "subject": "Users", "numbers": ["10,000"], "source_domain": "blog.com", "source_url": "http://blog.com/post"},
        {"claim": "Revenue grew 45% in 2024", "subject": "Revenue", "numbers": ["45%", "2024"], "source_domain": "finance.com", "source_url": "http://finance.com/report"},
        {"claim": "Sales increased by 30%", "subject": "Sales", "numbers": ["30%"], "source_domain": "example.org", "source_url": "http://example.org"},
        {"claim": "The CEO resigned", "subject": "Management", "numbers": [], "source_domain": "news.com", "source_url": "http://news.com/2"},
        {"claim": "Product X was launched in 2023", "subject": "Product", "numbers": ["2023"], "source_domain": "tech.com", "source_url": "http://tech.com"},
        {"claim": "Revenue decreased by 10%", "subject": "Revenue", "numbers": ["10%"], "source_domain": "badnews.com", "source_url": "http://badnews.com"},
        {"claim": "Cost of goods sold is $2M", "subject": "Cost", "numbers": ["$2M"], "source_domain": "finance.com", "source_url": "http://finance.com/cost"},
        {"claim": "Profit margin is 15%", "subject": "Profit", "numbers": ["15%"], "source_domain": "invest.com", "source_url": "http://invest.com"},
    ]

@pytest.fixture
def sample_texts():
    return [
        "In 2024, the company saw unprecedented growth. Revenue grew 45% year over year, reaching new heights.",
        "The startup ecosystem is booming. Yesterday, the company raised $5 million in a Series A funding round led by top investors.",
        "We are proud to announce that our platform now has over 10,000 active users. This milestone is huge for us.",
        "A recent financial report indicated that revenue grew 45% in 2024, confirming earlier projections.",
        "Despite market challenges, sales increased by 30% in Q3, outperforming competitors in the same sector."
    ]

@pytest.fixture
def sample_urls():
    return [
        "http://example.com",
        "https://example.com/page",
        "http://news.com/article?id=123&utm_source=google",
        "https://www.example.org/",
        "http://blog.com/post#comments",
        "https://sub.domain.com/path/",
        "http://finance.com/report?utm_campaign=spring",
        "https://test.com/about",
        "http://WWW.EXAMPLE.COM/Page",
        "https://news.com/latest",
        "http://tech.com/review",
        "https://invest.com/data",
        "http://badnews.com/story",
        "https://example.com/blog/post-1",
        "http://example.org/team",
        "https://blog.com/about",
        "http://tech.com/news?v=1",
        "https://news.com/2024/01/01/story",
        "http://finance.com/stocks",
        "https://invest.com/market"
    ]

@pytest.fixture
def sample_topic():
    return "website must have features"
