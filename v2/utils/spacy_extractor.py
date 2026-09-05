import numpy as np
import re
from typing import List, Dict

_nlp = None


def get_nlp():
    global _nlp
    if _nlp is None:
        try:
            import spacy
            try:
                _nlp = spacy.load("en_core_web_sm")
            except OSError:
                import subprocess
                subprocess.run(["python", "-m", "spacy", "download", "en_core_web_sm"])
                _nlp = spacy.load("en_core_web_sm")
        except Exception as e:
            print(f"Warning: could not load spaCy: {e}. Using regex extraction fallback.")
            _nlp = None
    return _nlp

OPINION_MARKERS = [
    "i think", "i believe", "in my opinion", "arguably", 
    "it seems", "probably", "maybe", "might"
]

PROMOTIONAL_MARKERS = [
    "click here", "subscribe", "sign up", "buy now", "limited time"
]

NUMBER_REGEX = re.compile(r"(\$?\d+(?:,\d+)*(?:\.\d+)?%?|\b\d+\s*(?:million|billion|trillion|k|m|b)\b)", re.IGNORECASE)

def extract_claims_from_text(text: str, source_url: str, source_domain: str) -> List[Dict]:
    """
    Extract factual claims from text using spaCy NER and regex.
    Limits processing to first 50K characters.
    """
    if not text:
        return []
        
    text = text[:50000]
    nlp_model = get_nlp()
    
    if nlp_model is None:
        claims = []
        sentences = text.replace('\n', ' ').split('.')
        for sent in sentences:
            sentence = sent.strip()
            if len(sentence.split()) < 8 or len(sentence.split()) > 60:
                continue
            if sentence.endswith('?'):
                continue
            lower_sent = sentence.lower()
            if any(marker in lower_sent for marker in OPINION_MARKERS):
                continue
            if any(marker in lower_sent for marker in PROMOTIONAL_MARKERS):
                continue
            numbers = NUMBER_REGEX.findall(sentence)
            if numbers:
                claims.append({
                    "claim": sentence,
                    "subject": "",
                    "numbers": list(set(numbers)),
                    "source_url": source_url,
                    "source_domain": source_domain
                })
        return claims

    doc = nlp_model(text)
    
    claims = []
    
    for sent in doc.sents:
        sentence = sent.text.strip()
        
        # a. Skip if it's a question
        if sentence.endswith("?"):
            continue
            
        lower_sent = sentence.lower()
        
        # b. Skip opinion markers
        if any(marker in lower_sent for marker in OPINION_MARKERS):
            continue
            
        # c. Length filter
        words = lower_sent.split()
        if len(words) < 10 or len(words) > 50:
            continue
            
        # d. Skip promotional
        if any(marker in lower_sent for marker in PROMOTIONAL_MARKERS):
            continue
            
        # e. Extract named entities
        valid_ents = [ent for ent in sent.ents if ent.label_ in {"ORG", "PERSON", "MONEY", "PERCENT", "DATE", "CARDINAL", "GPE"}]
        
        # f. Extract numbers
        numbers = NUMBER_REGEX.findall(sentence)
        
        # g. Filtering logic
        has_number = len(numbers) > 0
        has_entities = len(valid_ents)
        
        if (has_entities >= 1 and has_number) or (has_entities >= 2):
            primary_entity = valid_ents[0].text if valid_ents else ""
            claims.append({
                "claim": sentence,
                "subject": primary_entity,
                "numbers": list(set(numbers)),
                "source_url": source_url,
                "source_domain": source_domain
            })
            
    return claims
