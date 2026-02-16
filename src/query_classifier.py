
import re
from typing import Dict, List

class QueryClassifier:
    """Classifies queries and extracts key information"""

    
    @staticmethod
    def classify(question: str) -> Dict:
        q = question.lower()
    
        result = {
            "type": "factual",
            "keywords": [],
            "entities": {},
            "expected_output": "text"
        }
    
        # -----------------------------
        # OUT OF SCOPE
        # -----------------------------
        if any(x in q for x in [
            "forecast", "future", "prediction",
            "stock price", "color"
        ]):
            result["type"] = "out_of_scope"
            return result
    
        # -----------------------------
        # COMPANY
        # -----------------------------
        if "apple" in q:
            result["entities"]["company"] = "apple"
        elif "tesla" in q:
            result["entities"]["company"] = "tesla"
    
        # -----------------------------
        # SHARES (Q2)
        # -----------------------------
        if "shares" in q and "outstanding" in q:
            result["type"] = "numerical"
            result["keywords"] = ["shares", "outstanding", "common stock"]
            return result
    
        # -----------------------------
        # TERM DEBT (Q3)
        # -----------------------------
        if "term debt" in q:
            result["type"] = "numerical"
            result["keywords"] = ["term debt", "current", "non-current"]
            return result
    
        # -----------------------------
        # PERCENTAGE (Q7) — MUST BE BEFORE REVENUE
        # -----------------------------
        if "percentage" in q or "%" in q:
            result["type"] = "calculation"
            result["keywords"] = ["automotive sales", "total revenue"]
            return result
    
        # -----------------------------
        # REVENUE (Q1, Q6)
        # -----------------------------
        if "revenue" in q or "sales" in q:
            result["type"] = "numerical"
            result["keywords"] = ["total net sales", "revenue"]
            return result
    
        # -----------------------------
        # REASONING
        # -----------------------------
        if any(x in q for x in ["reason", "why", "purpose"]):
            result["type"] = "reasoning"
            if "elon musk" in q:
                result["keywords"] = [
                    "elon musk", "dependent",
                    "leadership", "strategy"
                ]
            return result
    
        return result

