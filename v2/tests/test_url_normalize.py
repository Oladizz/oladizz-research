from urllib.parse import urlparse, urlunparse, parse_qs, urlencode

def normalize_url(url: str) -> str:
    parsed = urlparse(url)
    
    # Lowercase domain and strip www
    netloc = parsed.netloc.lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]
        
    # Strip trailing slash from path
    path = parsed.path
    if path.endswith("/") and len(path) > 1:
        path = path[:-1]
        
    # Strip utm parameters
    query = parse_qs(parsed.query)
    clean_query = {k: v for k, v in query.items() if not k.startswith("utm_")}
    
    # Rebuild query string
    new_query = urlencode(clean_query, doseq=True)
    
    # Strip fragment
    fragment = ""
    
    # Reconstruct
    clean_url = urlunparse((parsed.scheme, netloc, path, parsed.params, new_query, fragment))
    return clean_url

def test_strip_utm_params():
    url = "http://example.com?utm_source=google&id=5"
    assert normalize_url(url) == "http://example.com?id=5"

def test_strip_fragment():
    url = "http://example.com#section1"
    assert normalize_url(url) == "http://example.com"

def test_strip_trailing_slash():
    url = "http://example.com/page/"
    assert normalize_url(url) == "http://example.com/page"

def test_lowercase_domain():
    url = "http://EXAMPLE.COM/Page"
    assert normalize_url(url) == "http://example.com/Page"

def test_strip_www():
    url = "http://www.example.com"
    assert normalize_url(url) == "http://example.com"

def test_preserve_path():
    url = "http://example.com/blog/post-1"
    assert normalize_url(url) == "http://example.com/blog/post-1"
