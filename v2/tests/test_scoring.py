def calculate_confidence_score(
    verifiability_tier: str,
    source_count: int,
    avg_credibility: float,
    contradiction_count: int
) -> float:
    # Verifiability tier ceilings
    TIER_CEILINGS = {
        "checkable_data": 1.0,
        "corroboration": 0.80,
        "anecdotal": 0.40,
    }
    
    # Source count scaling: f(n) = min(1.0, 0.3 + 0.1 * n)
    SOURCE_COUNT_BASE = 0.3
    SOURCE_COUNT_STEP = 0.1
    
    # Contradiction penalty per conflicting source
    CONTRADICTION_PENALTY_PER = 0.15
    
    if source_count == 0:
        return 0.0
        
    tier_ceiling = TIER_CEILINGS.get(verifiability_tier, 0.40)
    source_mult = min(1.0, SOURCE_COUNT_BASE + SOURCE_COUNT_STEP * source_count)
    
    # Base score
    score = tier_ceiling * source_mult * avg_credibility
    
    # Apply contradictions
    penalty = contradiction_count * CONTRADICTION_PENALTY_PER
    score = max(0.0, score - penalty)
    
    return score * 100.0


def test_single_source_corroboration():
    # 1 source, corroboration tier, avg_credibility 0.5
    # score = 0.80 * 0.4 * 0.5 = 0.16 -> 16%
    score = calculate_confidence_score("corroboration", 1, 0.5, 0)
    assert abs(score - 16.0) < 0.01

def test_multiple_sources_boost():
    # 5 sources -> f(5) = 0.8
    # score = 0.80 * 0.8 * 0.5 = 0.32 -> 32%
    score_1 = calculate_confidence_score("corroboration", 1, 0.5, 0)
    score_5 = calculate_confidence_score("corroboration", 5, 0.5, 0)
    assert score_5 > score_1
    assert abs(score_5 - 32.0) < 0.01

def test_checkable_data_ceiling():
    # ceiling is 1.0. With 7 sources, f(7) = 1.0, credibility = 1.0 -> 100%
    score = calculate_confidence_score("checkable_data", 7, 1.0, 0)
    assert abs(score - 100.0) < 0.01

def test_anecdotal_ceiling():
    # ceiling is 0.40. With 10 sources, f(10)=1.0, credibility = 1.0 -> 40%
    score = calculate_confidence_score("anecdotal", 10, 1.0, 0)
    assert abs(score - 40.0) < 0.01

def test_contradiction_penalty():
    # base score 32%
    # 1 contradiction -> 32 - 15 = 17%
    score = calculate_confidence_score("corroboration", 5, 0.5, 1)
    assert abs(score - 17.0) < 0.01

def test_zero_sources():
    score = calculate_confidence_score("corroboration", 0, 0.5, 0)
    assert score == 0.0

def test_high_credibility_sources():
    # credibility 0.95 vs 0.5
    score_high = calculate_confidence_score("corroboration", 1, 0.95, 0)
    score_norm = calculate_confidence_score("corroboration", 1, 0.5, 0)
    assert score_high > score_norm
    assert abs(score_high - 30.4) < 0.01

def test_low_credibility_sources():
    # credibility 0.2 vs 0.5
    score_low = calculate_confidence_score("corroboration", 1, 0.2, 0)
    score_norm = calculate_confidence_score("corroboration", 1, 0.5, 0)
    assert score_low < score_norm
    assert abs(score_low - 6.4) < 0.01
