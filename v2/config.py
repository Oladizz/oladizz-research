"""
Truth-Filtering Research Pipeline v2 — Shared Configuration
All stages import from here. One place to change model names, thresholds, etc.
"""
import os

# ─── GCP Project ───────────────────────────────────────────
GCP_PROJECT = os.environ.get("GCP_PROJECT", "oladizz-research")
GCP_REGION = os.environ.get("GCP_REGION", "us-central1")

# ─── Gemini Models (2026-current) ──────────────────────────
MODEL_EXTRACT = "gemini-3.5-flash-lite"       # Cheap, high-volume extraction
MODEL_CLUSTER = "gemini-3.7-flash"            # Stronger reasoning for contradiction detection
MODEL_EMBEDDING = "models/gemini-embedding-2" # Current embedding model name

# ─── Firestore Collections ─────────────────────────────────
FS_DISCOVERED_URLS = "discovered_urls"        # Stage 1 output
FS_SEEN_HASHES = "seen_hashes"                # URL + content dedup (permanent)
FS_SCRAPED_PAGES = "scraped_pages"            # Stage 3 output (ephemeral per run)
FS_CLAIMS = "claims"                          # Stage 5 output (ephemeral per run, prefixed with run_id)
FS_CLUSTERS = "clusters"                      # Stage 6 output (ephemeral per run)
FS_CREDIBILITY = "domain_credibility"         # Permanent — survives across runs
FS_SCORED_CLAIMS = "scored_claims"            # Stage 8 output (ephemeral per run)

# ─── BigQuery ──────────────────────────────────────────────
BQ_DATASET = "research_history"
BQ_TABLE_PAGES = "pages"
BQ_TABLE_CLAIMS = "claims"
BQ_TABLE_RUNS = "runs"

# ─── Cloud Tasks ───────────────────────────────────────────
CT_LOCATION = GCP_REGION
CT_SCRAPER_SERVICE_URL = os.environ.get(
    "SCRAPER_SERVICE_URL",
    f"https://scraper-worker-{GCP_PROJECT}.{GCP_REGION}.run.app"
)
CT_MAX_CONCURRENT_PER_DOMAIN = 1              # THE key v2 design rule
CT_MAX_DOMAINS_PARALLEL = 100                 # Up to 100 domain queues dispatching at once
CT_RETRY_MAX_ATTEMPTS = 3
CT_RETRY_MIN_BACKOFF = "5s"
CT_RETRY_MAX_BACKOFF = "300s"

# ─── Search ────────────────────────────────────────────────
SEARCH_API_KEY = os.environ.get("GOOGLE_SEARCH_API_KEY", "")
SEARCH_ENGINE_ID = os.environ.get("GOOGLE_SEARCH_ENGINE_ID", "")
SEARCH_QUERIES_PER_TOPIC = 10                 # Number of query variants to generate
SEARCH_RESULTS_PER_QUERY = 10                 # Google returns max 10 per call
SEARCH_TARGET_URLS = 5000                     # Aspirational target

# ─── DuckDuckGo Fallback (when no Search API key) ─────────
DDG_URL = "https://html.duckduckgo.com/html/"
DDG_RESULTS_PER_QUERY = 10

# ─── Dedup Thresholds ─────────────────────────────────────
SIMHASH_DISTANCE_THRESHOLD = 3               # Hamming distance — ≤3 = near-duplicate
RELEVANCE_SIMILARITY_THRESHOLD = 0.35        # Min cosine similarity to topic to keep page
EMBEDDING_CLUSTER_THRESHOLD = 0.85           # Cosine similarity for claim grouping

# ─── Confidence Scoring ───────────────────────────────────
# Verifiability tier ceilings
TIER_CEILINGS = {
    "checkable_data": 1.0,       # Can be verified against real data (on-chain, official records)
    "corroboration": 0.80,       # Multiple independent credible sources agree
    "anecdotal": 0.40,           # Personal experience, unverifiable by nature
}

# Source count scaling: f(n) = min(1.0, 0.3 + 0.1 * n)
# 1 source = 0.4, 3 sources = 0.6, 7+ sources = 1.0
SOURCE_COUNT_BASE = 0.3
SOURCE_COUNT_STEP = 0.1

# Contradiction penalty per conflicting source
CONTRADICTION_PENALTY_PER = 0.15

# Minimum confidence to include in final report
CONFIDENCE_THRESHOLD = 60.0

# ─── Synthesis ─────────────────────────────────────────────
PDF_COMPRESSION = True
MAX_CLAIMS_IN_REPORT = 100

# ─── Delivery ─────────────────────────────────────────────
GCS_BUCKET = os.environ.get("GCS_BUCKET", f"{GCP_PROJECT}-reports")
GCS_STORAGE_CLASS = "NEARLINE"
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

# ─── Gemini API ────────────────────────────────────────────
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

# ─── Rate Limiting (Free Tier Protection) ──────────────────
GEMINI_FREE_TIER_DELAY = 4.5    # seconds between Gemini calls (15 RPM limit)
SEARCH_DELAY = 3.0              # seconds between search queries
FETCH_DELAY = 2.0               # seconds between fetches to same domain

# ─── Run Management ───────────────────────────────────────
import uuid
from datetime import datetime

def generate_run_id():
    """Generate a unique run identifier."""
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    short_uuid = uuid.uuid4().hex[:8]
    return f"run_{ts}_{short_uuid}"
