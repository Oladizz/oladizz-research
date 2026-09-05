import re
from typing import List

SYNONYMS = {
    "must have": ["essential", "required", "critical", "important", "necessary"],
    "best": ["top", "leading", "optimal"],
    "guide": ["tutorial", "handbook", "overview"],
}

MODIFIERS_PREPEND = ["best", "top"]
MODIFIERS_APPEND = ["checklist", "guide", "2026", "examples"]

QUESTIONS = [
    "what are the {topic}",
    "how to {topic}",
    "why is {topic} important"
]

NICHES = [
    "for business",
    "for ecommerce",
    "for startups"
]

def expand_topic(topic: str, count: int = 15) -> List[str]:
    """
    Expand a topic into a list of search query variants using templates and synonyms.
    """
    queries = set()
    queries.add(topic)
    
    # 1. Question forms
    for q in QUESTIONS:
        queries.add(q.format(topic=topic))
        
    # 2. Modifiers
    for mod in MODIFIERS_PREPEND:
        queries.add(f"{mod} {topic}")
    for mod in MODIFIERS_APPEND:
        queries.add(f"{topic} {mod}")
        
    # 3. Niches
    for niche in NICHES:
        queries.add(f"{topic} {niche}")
        
    # 4. Synonyms (simple substitution)
    topic_lower = topic.lower()
    for phrase, syns in SYNONYMS.items():
        if phrase in topic_lower:
            for syn in syns:
                new_topic = re.sub(rf"\b{phrase}\b", syn, topic_lower, flags=re.IGNORECASE)
                if new_topic != topic_lower:
                    queries.add(new_topic)
                    queries.add(f"{new_topic} guide")

    return list(queries)[:count]
