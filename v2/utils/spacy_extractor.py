import re
import spacy
from typing import List, Dict

try:
    nlp = spacy.load("en_core_web_sm")
except OSError:
    import subprocess
    subprocess.run(["python", "-m", "spacy", "download", "en_core_web_sm"])
    nlp = spacy.load("en_core_web_sm")

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
    doc = nlp(text)
    
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
