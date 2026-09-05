"""
Truth-Filtering Research Pipeline v2 — Data Models
Defines the shape of every record that flows through the pipeline.
"""
from dataclasses import dataclass, field, asdict
from typing import List, Optional
from datetime import datetime


@dataclass
class DiscoveredURL:
    """Stage 1 output — a URL found by search."""
    url: str
    domain: str
    query_used: str
    run_id: str
    status: str = "pending"       # pending → queued → fetched → failed
    discovered_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self):
        return asdict(self)


@dataclass
class ScrapedPage:
    """Stage 3 output — fetched and cleaned page text."""
    url: str
    domain: str
    run_id: str
    url_hash: str                 # SHA-256 of the URL
    content_hash: str             # SimHash of the cleaned text
    raw_text: str
    char_count: int
    is_duplicate: bool = False    # Set by Stage 4 dedup
    is_relevant: bool = True      # Set by Stage 4 relevance filter
    status: str = "scraped"       # scraped → deduplicated → extracted → archived
    scraped_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self):
        d = asdict(self)
        # Don't store full text in the dict representation for logging
        d['raw_text_length'] = len(self.raw_text)
        return d


@dataclass
class ExtractedClaim:
    """Stage 5 output — one atomic factual claim from a page."""
    claim: str
    subject: str
    numbers: List[str] = field(default_factory=list)
    source_url: str = ""
    source_domain: str = ""
    run_id: str = ""
    claim_id: str = ""            # Set during extraction
    cluster_id: Optional[str] = None
    embedding: Optional[List[float]] = None
    status: str = "extracted"     # extracted → clustered → scored

    def to_dict(self):
        d = asdict(self)
        # Embeddings are large — exclude from casual serialization
        if d.get('embedding'):
            d['embedding_dims'] = len(d['embedding'])
            del d['embedding']
        return d


@dataclass
class ClaimCluster:
    """Stage 6 output — a group of claims saying the same thing."""
    cluster_id: str
    representative_claim: str
    member_claim_ids: List[str] = field(default_factory=list)
    source_domains: List[str] = field(default_factory=list)
    source_urls: List[str] = field(default_factory=list)
    independent_source_count: int = 0
    has_contradictions: bool = False
    contradicting_claims: List[str] = field(default_factory=list)
    run_id: str = ""
    status: str = "clustered"     # clustered → scored

    def to_dict(self):
        return asdict(self)


@dataclass
class DomainCredibility:
    """Stage 7 — persistent credibility record per domain."""
    domain: str
    domain_type: str = "unknown"  # primary, institutional, practitioner, aggregator, anonymous
    credibility_score: float = 0.5  # 0.0 to 1.0, starts neutral
    total_claims_seen: int = 0
    claims_verified: int = 0
    claims_contradicted: int = 0
    last_updated: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    # Type multipliers for initial scoring
    TYPE_MULTIPLIERS = {
        "primary": 1.0,           # Official source / original data
        "institutional": 0.9,     # Major news orgs, academic institutions
        "practitioner": 0.7,      # Industry blogs, expert practitioners
        "aggregator": 0.4,        # Content farms, aggregators
        "anonymous": 0.3,         # Anonymous forums, unverifiable
        "unknown": 0.5,
    }

    def effective_score(self) -> float:
        """Blend the historical score with the type multiplier."""
        type_mult = self.TYPE_MULTIPLIERS.get(self.domain_type, 0.5)
        if self.total_claims_seen == 0:
            return type_mult
        # As more data comes in, lean more on historical evidence
        historical_weight = min(0.8, self.total_claims_seen / 100)
        return (historical_weight * self.credibility_score) + ((1 - historical_weight) * type_mult)

    def to_dict(self):
        d = asdict(self)
        d.pop('TYPE_MULTIPLIERS', None)
        d['effective_score'] = self.effective_score()
        return d


@dataclass
class ScoredClaim:
    """Stage 8-9 output — a claim with its final confidence score."""
    cluster_id: str
    representative_claim: str
    confidence_score: float       # 0–100%
    verifiability_tier: str       # checkable_data, corroboration, anecdotal
    independent_source_count: int
    source_domains: List[str] = field(default_factory=list)
    source_urls: List[str] = field(default_factory=list)
    avg_source_credibility: float = 0.5
    has_contradictions: bool = False
    contradiction_penalty: float = 0.0
    run_id: str = ""

    def to_dict(self):
        return asdict(self)


@dataclass
class ResearchRun:
    """Metadata for one complete pipeline execution."""
    run_id: str
    topic: str
    status: str = "started"       # started → searching → scraping → extracting → scoring → synthesizing → delivered → cleaned
    urls_discovered: int = 0
    urls_scraped: int = 0
    pages_after_dedup: int = 0
    claims_extracted: int = 0
    clusters_formed: int = 0
    claims_above_threshold: int = 0
    pdf_gcs_path: str = ""
    started_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    finished_at: Optional[str] = None

    def to_dict(self):
        return asdict(self)
