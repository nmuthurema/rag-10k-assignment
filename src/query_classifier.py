
import re
from typing import Dict, List

class QueryClassifier:
    """Classifies queries into types and extracts key information"""
    
    @staticmethod
    def classify(question: str) -> Dict:
        q_lower = question.lower()
        
        result = {
            "type": "factual",
            "keywords": [],
            "entities": {},
            "expected_output": "text"
        }
        
        # Extract entities
        if "apple" in q_lower:
            result["entities"]["company"] = "apple"
        elif "tesla" in q_lower:
            result["entities"]["company"] = "tesla"
        
        year_match = re.search(r'20\d{2}', question)
        if year_match:
            result["entities"]["year"] = year_match.group(0)
        
        # Detect out-of-scope
        if any(term in q_lower for term in ["forecast", "predict", "future", "will be"]):
            result["type"] = "out_of_scope"
            return result
        
        if "2025" in question or "2026" in question:
            if any(term in q_lower for term in ["cfo", "stock price", "color"]):
                result["type"] = "out_of_scope"
                return result

        # Detect unanswerable "trivia" questions
        trivia_patterns = ['what color', 'what size', 'what material', 'painted']
        if any(pattern in q_lower for pattern in trivia_patterns):
            result["type"] = "out_of_scope"
            return result
            
        # Detect calculation type
        if "percentage" in q_lower or "% of" in q_lower or "what percent" in q_lower:
            result["type"] = "calculation"
            result["expected_output"] = "percentage"
            if "automotive" in q_lower:
                result["keywords"] = ["automotive sales", "total revenue"]
            return result
        
        # Detect numerical type
        numerical_indicators = [
            "how many", "how much", "what is the total", "what is the amount",
            "what was the", "number of"
        ]
        
        numerical_terms = ["revenue", "debt", "shares", "income", "assets", "price", "amount"]
        
        if any(ind in q_lower for ind in numerical_indicators) or any(term in q_lower for term in numerical_terms):
            result["type"] = "numerical"
            result["expected_output"] = "number"
            
            if "revenue" in q_lower:
                result["keywords"] = ["revenue", "sales", "net sales"]
            elif "debt" in q_lower:
                result["keywords"] = ["term debt", "debt", "current", "non-current"]
            elif "shares" in q_lower:
                result["keywords"] = ["shares outstanding", "common stock", "shares"]
            
            return result
        
        # Detect date type
        if "date" in q_lower or "when" in q_lower:
            result["expected_output"] = "date"
            if "filed" in q_lower:
                result["keywords"] = ["filed", "signature", "signed"]
            return result
        
        # Detect yes/no type
        if q_lower.startswith("does") or q_lower.startswith("is") or q_lower.startswith("are"):
            result["expected_output"] = "yes_no"
            if "sec" in q_lower and "comments" in q_lower:
                result["keywords"] = ["sec", "staff comments", "item 1b"]
            return result
        
        # Reasoning questions
        if any(term in q_lower for term in ["why", "reason", "purpose", "explain"]):
            result["type"] = "reasoning"
            if "elon musk" in q_lower:
                result["keywords"] = ["elon musk", "dependent", "leadership"]
            elif "lease pass-through" in q_lower:
                result["keywords"] = ["lease", "pass-through", "solar", "ppa"]
            return result
        
        # Factual questions
        if "what types" in q_lower or "what vehicles" in q_lower or "which" in q_lower:
            result["type"] = "factual"
            if "vehicles" in q_lower:
                result["keywords"] = ["model s", "model 3", "model x", "model y", "cybertruck", "vehicles"]
            return result
        
        return result
