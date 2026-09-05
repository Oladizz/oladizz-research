import re

def simhash(text: str, hashbits: int = 64) -> int:
    if not text:
        return 0
    # simple simhash implementation for testing
    words = text.lower().split()
    if not words:
        return 0
        
    v = [0] * hashbits
    for word in words:
        # Simple hash function for words
        h = hash(word)
        for i in range(hashbits):
            bitmask = 1 << i
            if h & bitmask:
                v[i] += 1
            else:
                v[i] -= 1
                
    fingerprint = 0
    for i in range(hashbits):
        if v[i] >= 0:
            fingerprint |= (1 << i)
            
    return fingerprint

def hamming_distance(hash1: int, hash2: int) -> int:
    x = (hash1 ^ hash2) & ((1 << 64) - 1)
    tot = 0
    while x:
        tot += 1
        x &= x - 1
    return tot

def test_identical_texts_same_hash():
    text = "this is a very specific text that should be identical."
    h1 = simhash(text)
    h2 = simhash(text)
    assert h1 == h2
    assert hamming_distance(h1, h2) == 0

def test_similar_texts_close_hash():
    base = "the quick brown fox jumps over the lazy dog and runs through the forest with great speed and agility. " * 5
    text1 = base + "The weather today was completely sunny."
    text2 = base + "The weather today was remarkably sunny."
    h1 = simhash(text1)
    h2 = simhash(text2)
    dist = hamming_distance(h1, h2)
    assert dist <= 3

def test_different_texts_far_hash():
    text1 = "the quick brown fox jumps over the lazy dog"
    text2 = "revenue grew 45 percent in the last quarter of 2024"
    h1 = simhash(text1)
    h2 = simhash(text2)
    dist = hamming_distance(h1, h2)
    assert dist > 3

def test_empty_text():
    h1 = simhash("")
    h2 = simhash("something")
    assert h1 == 0
    assert hamming_distance(h1, h2) > 0

def test_hamming_distance_symmetric():
    text1 = "apple banana"
    text2 = "apple orange"
    h1 = simhash(text1)
    h2 = simhash(text2)
    assert hamming_distance(h1, h2) == hamming_distance(h2, h1)
