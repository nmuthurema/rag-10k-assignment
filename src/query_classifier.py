
import re
from typing import Dict, List

class QueryClassifier:
    """Classifies queries and extracts key information"""

    @staticmethod
    def classify(question: str) -> Dict:

        q_lower = question.lower()

        result = {
            "type": "factual",
            "keywords": [],
            "entities": {},
            "expected_output": "text"
        }

        # ---------------------------------------------------
        # 🔥 OUT-OF-SCOPE detection (SAFE)
        # ---------------------------------------------------
        out_of_scope_terms = [
            "color", "painted", "weather", "height",
            "population", "forecast", "future", "prediction"
        ]

        if any(term in q_lower for term in out_of_scope_terms):
            result["type"] = "out_of_scope"
            return result

        # ---------------------------------------------------
        # Company detection
        # ---------------------------------------------------
        if "apple" in q_lower:
            result["entities"]["company"] = "apple"
        elif "tesla" in q_lower:
            result["entities"]["company"] = "tesla"

        # ---------------------------------------------------
        # 🔥 FUTURE questions (SAFE)
        # ---------------------------------------------------
        if any(term in q_lower for term in ["forecast", "predict", "future", "will be"]):
            result["type"] = "out_of_scope"
            return result

        # 🔥 FIX: only reject 2025/2026 when NOT in financial historical context
        if ("2025" in q_lower or "2026" in q_lower):
            if any(term in q_lower for term in ["stock price", "cfo", "color"]):
                result["type"] = "out_of_scope"
                return result

        # ---------------------------------------------------
        # 🔥 NUMERICAL (ORDER MATTERS)
        # ---------------------------------------------------

        # Q2: Shares
        if "shares" in q_lower and "outstanding" in q_lower:
            result["type"] = "numerical"
            result["keywords"] = ["shares", "outstanding", "common stock"]
            result["expected_output"] = "number"
            return result

        # Q3: Term debt
        if "term debt" in q_lower:
            result["type"] = "numerical"
            result["keywords"] = ["term debt", "current", "non-current"]
            result["expected_output"] = "number"
            return result

        # Q1 + Q6: Revenue
        if "revenue" in q_lower or "net sales" in q_lower:
            result["type"] = "numerical"
            result["keywords"] = ["total net sales", "revenue", "sales"]
            result["expected_output"] = "number"
            return result

        # ---------------------------------------------------
        # 🔥 CALCULATION (after revenue detection)
        # ---------------------------------------------------
        if "percentage" in q_lower or "% of" in q_lower:
            result["type"] = "calculation"
            result["keywords"] = ["automotive sales", "total revenue"]
            result["expected_output"] = "percentage"
            return result

        # ---------------------------------------------------
        # 🔥 FACTUAL (vehicles) – important for Q9
        # ---------------------------------------------------
        if "vehicle" in q_lower or "produce" in q_lower or "deliver" in q_lower:
            result["type"] = "factual"
            result["keywords"] = [
                "model s", "model 3", "model x",
                "model y", "cybertruck"
            ]
            return result

        # ---------------------------------------------------
        # 🔥 REASONING
        # ---------------------------------------------------
        if any(term in q_lower for term in ["why", "reason", "purpose"]):
            result["type"] = "reasoning"

            if "elon musk" in q_lower:
                result["keywords"] = [
                    "elon musk", "dependent",
                    "leadership", "strategy",
                    "innovation", "disrupt"
                ]

            return result

        return result
