
import re
from typing import Dict


def analyze_query(query: str) -> Dict:

    q = query.lower()

    result = {
        "future": False,
        "company": None,
        "numeric": False,
        "keywords": [],
        "year": None
    }

    # --------------------------------------------------
    # FUTURE / OUT OF SCOPE
    # --------------------------------------------------
    future_terms = ["forecast", "prediction", "future", "2025", "2026"]

    if any(t in q for t in future_terms):
        result["future"] = True
        return result

    # --------------------------------------------------
    # COMPANY DETECTION
    # --------------------------------------------------
    if "apple" in q:
        result["company"] = "apple"
    elif "tesla" in q:
        result["company"] = "tesla"

    # --------------------------------------------------
    # NUMERIC QUESTIONS
    # --------------------------------------------------
    numeric_terms = [
        "revenue", "debt", "shares", "percentage",
        "amount", "total", "income", "cash", "assets"
    ]

    if any(t in q for t in numeric_terms):
        result["numeric"] = True

    # --------------------------------------------------
    # YEAR EXTRACTION
    # --------------------------------------------------
    year_match = re.search(r"(20\d{2})", query)
    if year_match:
        result["year"] = year_match.group(1)

    # --------------------------------------------------
    # KEYWORDS
    # --------------------------------------------------
    key_terms = [
        "revenue", "automotive", "debt", "shares",
        "staff comments", "vehicles", "lease"
    ]

    result["keywords"] = [k for k in key_terms if k in q]

    return result
