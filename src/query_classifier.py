
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
        # 🔥 Strong OUT-OF-SCOPE detection
        # ---------------------------------------------------
        out_of_scope_terms = [
            "color", "painted", "weather", "height",
            "population", "stock price", "forecast",
            "future", "prediction"
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
        # Future / prediction
        # ---------------------------------------------------
        if any(term in q_lower for term in ["forecast", "predict", "future", "will be"]):
            result["type"] = "out_of_scope"
            return result
    
        if "2025" in question or "2026" in question:
            if any(term in q_lower for term in ["cfo", "stock price", "color"]):
                result["type"] = "out_of_scope"
                return result
    
        # ---------------------------------------------------
        # Numerical
        # ---------------------------------------------------
        if "shares" in q_lower and "outstanding" in q_lower:
            result["type"] = "numerical"
            result["keywords"] = ["shares outstanding", "common stock", "shares"]
            result["expected_output"] = "number"
            return result
    
        if "term debt" in q_lower:
            result["type"] = "numerical"
            result["keywords"] = ["term debt", "current", "non-current"]
            result["expected_output"] = "number"
            return result
    
        if "revenue" in q_lower:
            result["type"] = "numerical"
            result["keywords"] = ["revenue", "sales", "net sales"]
            result["expected_output"] = "number"
            return result
    
        # ---------------------------------------------------
        # Calculation
        # ---------------------------------------------------
        if "percentage" in q_lower:
            result["type"] = "calculation"
            result["keywords"] = ["automotive sales", "total revenue"]
            result["expected_output"] = "percentage"
            return result
    
        # ---------------------------------------------------
        # Reasoning
        # ---------------------------------------------------
        if any(term in q_lower for term in ["why", "reason", "purpose"]):
            result["type"] = "reasoning"
            if "elon musk" in q_lower:
                result["keywords"] = [
                    "elon musk", "dependent", "leadership",
                    "strategy", "innovation", "disrupt"
                ]
            return result
    
        return result
