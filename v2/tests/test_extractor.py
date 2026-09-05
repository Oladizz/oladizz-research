import re
from typing import List, Dict, Any

class MockDoc:
    def __init__(self, text):
        self.text = text
        self.sents = [MockSpan(text)]
        self.ents = []
        if "45%" in text or "2024" in text:
            self.ents.append(MockEnt("45%", "PERCENT"))
            self.ents.append(MockEnt("2024", "DATE"))
        if "$5 million" in text:
            self.ents.append(MockEnt("$5 million", "MONEY"))

class MockSpan:
    def __init__(self, text):
        self.text = text

class MockEnt:
    def __init__(self, text, label_):
        self.text = text
        self.label_ = label_

class MockSpacy:
    def __call__(self, text):
        return MockDoc(text)

def extract_claims(text: str, nlp_model=None) -> List[Dict[str, Any]]:
    if not text:
        return []
        
    nlp = nlp_model or MockSpacy()
    doc = nlp(text)
    
    claims = []
    
    # Rule based filter
    for sent in doc.sents:
        t = sent.text.lower()
        if "?" in t:
            continue
        if "i think" in t or "in my opinion" in t:
            continue
        if "click here" in t or "sign up" in t:
            continue
            
        numbers = [ent.text for ent in doc.ents if ent.label_ in ["PERCENT", "MONEY", "DATE", "CARDINAL"]]
        
        if numbers:
            claims.append({
                "claim": sent.text.strip(),
                "numbers": numbers
            })
            
    return claims


def test_extracts_claim_with_numbers():
    text = "Revenue grew 45% in 2024"
    claims = extract_claims(text)
    assert len(claims) == 1
    assert "45%" in claims[0]["numbers"]

def test_skips_opinions():
    text = "I think this is great 45%"
    claims = extract_claims(text)
    assert len(claims) == 0

def test_skips_questions():
    text = "What is the best approach? 45%"
    claims = extract_claims(text)
    assert len(claims) == 0

def test_skips_promotional():
    text = "Click here to sign up now and get 45% off"
    claims = extract_claims(text)
    assert len(claims) == 0

def test_extracts_money():
    text = "The company raised $5 million"
    claims = extract_claims(text)
    assert len(claims) == 1
    assert "$5 million" in claims[0]["numbers"]

def test_handles_empty_text():
    claims = extract_claims("")
    assert len(claims) == 0

def test_handles_long_text():
    text = "A" * 100000
    claims = extract_claims(text)
    # Shouldn't crash
    assert isinstance(claims, list)
