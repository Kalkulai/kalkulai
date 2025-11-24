# ENHANCED FUZZY MATCHING FOR DYNAMIC CATALOGS

from typing import List, Tuple, Optional
from difflib import SequenceMatcher
import re


def normalize_for_matching(text: str) -> str:
    """Normalize text for fuzzy matching"""
    # Lowercase
    text = text.lower()
    # Remove special chars but keep spaces
    text = re.sub(r'[^\w\s-]', '', text)
    # Normalize whitespace
    text = ' '.join(text.split())
    return text


def extract_tokens(text: str) -> List[str]:
    """Extract significant tokens from text"""
    normalized = normalize_for_matching(text)
    # Split on spaces and hyphens
    tokens = re.split(r'[\s-]+', normalized)
    # Keep tokens >= 3 chars
    return [t for t in tokens if len(t) >= 3]


def token_overlap_score(query_tokens: List[str], product_tokens: List[str]) -> float:
    """Calculate token overlap score (Jaccard similarity)"""
    if not query_tokens or not product_tokens:
        return 0.0
    
    query_set = set(query_tokens)
    product_set = set(product_tokens)
    
    intersection = len(query_set & product_set)
    union = len(query_set | product_set)
    
    return intersection / union if union > 0 else 0.0


def ngram_similarity(s1: str, s2: str, n: int = 3) -> float:
    """Calculate n-gram similarity between two strings"""
    def get_ngrams(text: str, n: int) -> set:
        text = normalize_for_matching(text)
        return set(text[i:i+n] for i in range(len(text) - n + 1))
    
    ngrams1 = get_ngrams(s1, n)
    ngrams2 = get_ngrams(s2, n)
    
    if not ngrams1 or not ngrams2:
        return 0.0
    
    intersection = len(ngrams1 & ngrams2)
    union = len(ngrams1 | ngrams2)
    
    return intersection / union if union > 0 else 0.0


def levenshtein_distance(s1: str, s2: str) -> int:
    """Calculate Levenshtein distance between two strings"""
    if len(s1) < len(s2):
        return levenshtein_distance(s2, s1)
    
    if len(s2) == 0:
        return len(s1)
    
    previous_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            # Cost of insertions, deletions, or substitutions
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row
    
    return previous_row[-1]


def levenshtein_similarity(s1: str, s2: str) -> float:
    """Convert Levenshtein distance to similarity score (0-1)"""
    s1_norm = normalize_for_matching(s1)
    s2_norm = normalize_for_matching(s2)
    
    distance = levenshtein_distance(s1_norm, s2_norm)
    max_len = max(len(s1_norm), len(s2_norm))
    
    if max_len == 0:
        return 1.0
    
    return 1.0 - (distance / max_len)


def combined_similarity(query: str, product_name: str) -> float:
    """
    Calculate combined similarity score using multiple methods
    
    Returns score between 0 and 1, where:
    - 1.0 = perfect match
    - 0.8+ = very good match
    - 0.6+ = good match
    - 0.4+ = acceptable match
    - <0.4 = poor match
    
    V2.0 weights (optimized):
    - Sequence matching: 40% (increased - best for fuzzy matches)
    - N-gram: 25% (increased - catches partial matches)
    - Token overlap: 20% (decreased - too strict)
    - Levenshtein: 15% (same - good for typos)
    """
    query_tokens = extract_tokens(query)
    product_tokens = extract_tokens(product_name)
    
    # 1. Token overlap (Jaccard) - weight 20% (reduced from 35%)
    token_score = token_overlap_score(query_tokens, product_tokens)
    
    # 2. Sequence matching - weight 40% (increased from 30%)
    sequence_score = SequenceMatcher(None, 
                                    normalize_for_matching(query),
                                    normalize_for_matching(product_name)).ratio()
    
    # 3. N-gram similarity - weight 25% (increased from 20%)
    ngram_score = ngram_similarity(query, product_name, n=3)
    
    # 4. Levenshtein similarity - weight 15% (same)
    lev_score = levenshtein_similarity(query, product_name)
    
    # Weighted average
    combined = (
        token_score * 0.20 +
        sequence_score * 0.40 +
        ngram_score * 0.25 +
        lev_score * 0.15
    )
    
    return combined


def find_best_matches(
    query: str,
    catalog: List[str],
    top_k: int = 5,
    min_score: float = 0.25  # Lowered to catch more fuzzy matches
) -> List[Tuple[str, float]]:
    """
    Find best matching products from catalog
    
    Args:
        query: User query
        catalog: List of product names
        top_k: Number of top matches to return
        min_score: Minimum similarity score (default 0.25)
    
    Returns:
        List of (product_name, score) tuples, sorted by score desc
    """
    matches = []
    
    for product_name in catalog:
        score = combined_similarity(query, product_name)
        if score >= min_score:
            matches.append((product_name, score))
    
    # Sort by score descending
    matches.sort(key=lambda x: x[1], reverse=True)
    
    return matches[:top_k]


# USAGE EXAMPLES:

if __name__ == "__main__":
    # Test cases
    catalog = [
        "Dispersionsfarbe weiß, matt, 10 L",
        "Dispersionsfarbe cremeweiß, 10 L",
        "Tiefengrund lösemittelfrei, 10 L",
        "Putzgrund für Fassaden, 10 L",
        "Silikonharzfarbe weiß, 15 L",
    ]
    
    # Test 1: Exact match
    print("Test 1: 'Dispersionsfarbe weiß'")
    matches = find_best_matches("Dispersionsfarbe weiß", catalog, top_k=3)
    for product, score in matches:
        print(f"  {score:.3f} - {product}")
    print()
    
    # Test 2: Fuzzy match
    print("Test 2: 'Tiefgrund Innen'")
    matches = find_best_matches("Tiefgrund Innen", catalog, top_k=3)
    for product, score in matches:
        print(f"  {score:.3f} - {product}")
    print()
    
    # Test 3: Generic query
    print("Test 3: 'weiße Farbe'")
    matches = find_best_matches("weiße Farbe", catalog, top_k=3)
    for product, score in matches:
        print(f"  {score:.3f} - {product}")
    print()
    
    # Test 4: Typo
    print("Test 4: 'Dispersonsfarbe weis'")
    matches = find_best_matches("Dispersonsfarbe weis", catalog, top_k=3)
    for product, score in matches:
        print(f"  {score:.3f} - {product}")