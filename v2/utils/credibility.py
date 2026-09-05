"""
External credibility signals.
"""
try:
    import whois
    _WHOIS_AVAILABLE = True
except ImportError:
    _WHOIS_AVAILABLE = False

from datetime import datetime

class CredibilityEngine:
    def __init__(self):
        self.whitelist = {
            "reuters.com": 0.95, "apnews.com": 0.95, "bbc.com": 0.90, "nature.com": 0.95,
            "arxiv.org": 0.85, "nytimes.com": 0.85, "washingtonpost.com": 0.85,
            "theguardian.com": 0.85, "forbes.com": 0.75, "techcrunch.com": 0.75, "wired.com": 0.75
        }
        self.blacklist = {
            "breitbart.com": 0.1, "infowars.com": 0.1, "thegatewaypundit.com": 0.1,
            "naturalnews.com": 0.1, "sputniknews.com": 0.1, "rt.com": 0.1
        }
        self.tld_scores = {
            ".gov": 0.95, ".mil": 0.95, ".edu": 0.90, ".org": 0.70, ".com": 0.50,
            ".io": 0.30, ".xyz": 0.30, ".tk": 0.30
        }
        self.subdomain_platforms = {"blogspot.com", "wordpress.com", "medium.com"}
        self._cache = {}

    def get_domain_type(self, domain: str) -> str:
        if any(domain.endswith(tld) for tld in [".gov", ".mil", ".edu"]):
            return "institutional"
        if domain in self.whitelist:
            return "institutional"
        if domain in self.blacklist:
            return "aggregator"
        if any(platform in domain for platform in self.subdomain_platforms):
            return "anonymous"
        return "unknown"

    def assess_domain(self, domain: str) -> dict:
        if domain in self._cache:
            return self._cache[domain]
            
        base_score = 0.5
        signals = []
        
        for tld, score in self.tld_scores.items():
            if domain.endswith(tld):
                base_score = score
                signals.append(f"TLD {tld} classification")
                break
                
        if domain in self.whitelist:
            base_score = self.whitelist[domain]
            signals.append("Whitelist match")
        elif domain in self.blacklist:
            base_score = self.blacklist[domain]
            signals.append("Blacklist match")
            
        for platform in self.subdomain_platforms:
            if domain.endswith(platform) and domain != platform:
                base_score -= 0.1
                signals.append("Subdomain penalty")
                break
                
        if _WHOIS_AVAILABLE:
            try:
                w = whois.whois(domain)
                creation_date = w.creation_date
                if isinstance(creation_date, list):
                    creation_date = creation_date[0]
                if creation_date:
                    age_years = (datetime.utcnow() - creation_date).days / 365.25
                    if age_years > 10:
                        base_score += 0.1
                        signals.append("Domain age > 10 years")
                    elif age_years < 1:
                        base_score -= 0.1
                        signals.append("Domain age < 1 year")
            except Exception:
                pass

        base_score = max(0.0, min(1.0, base_score))
        
        result = {
            "domain_type": self.get_domain_type(domain),
            "base_score": base_score,
            "signals": signals
        }
        self._cache[domain] = result
        return result
