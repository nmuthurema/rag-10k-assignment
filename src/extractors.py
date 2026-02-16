
import re
from typing import Optional, List

# ============================================================
# FACTUAL
# ============================================================

class FactualExtractor:
    @staticmethod
    def extract(context: str, keywords: List[str]) -> Optional[str]:
        if any(
            kw.lower() in ['model s', 'model 3', 'model x', 'model y', 'cybertruck', 'vehicles']
            for kw in keywords
        ):
            vehicles = []
            context_lower = context.lower()
            
            if "model s" in context_lower:
                vehicles.append("Model S")
            if "model 3" in context_lower:
                vehicles.append("Model 3")
            if "model x" in context_lower:
                vehicles.append("Model X")
            if "model y" in context_lower:
                vehicles.append("Model Y")
            if "cybertruck" in context_lower:
                vehicles.append("Cybertruck")
            
            if len(vehicles) >= 3:
                return ", ".join(vehicles)
        
        return None

# ============================================================
# NUMERICAL - PURE RAG VERSION
# ============================================================

class NumericalExtractor:
    @staticmethod
    def extract_revenue(context: str, expected_range: tuple = None) -> Optional[str]:
        """Extract total revenue from context"""
        
        # Look for "Total net sales" or "Total revenues" in tables/statements
        patterns = [
            r'Total\s+net\s+sales\s+\$?\s*(\d{1,3}(?:,\d{3})+)',
            r'Total\s+revenues?\s+\$\s*(\d{1,3}(?:,\d{3})+)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, context, re.IGNORECASE)
            if match:
                value = int(match.group(1).replace(",", ""))
                return f"${value:,} million"
        
        return None

    @staticmethod
    def extract_shares(context: str, query: str = "") -> Optional[str]:
        """Extract shares outstanding from context - pure extraction"""
        
        # Extract the date from query to find the right context
        date_match = re.search(
            r'(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s+\d{4}',
            query,
            re.IGNORECASE
        )
        
        target_date = date_match.group(0) if date_match else None
        
        # Strategy: Find large numbers (10+ digits with commas) near "shares" and the target date
        if target_date:
            # Split context into sentences
            sentences = re.split(r'[.!?]', context)
            
            for sentence in sentences:
                # Must contain the target date
                if target_date not in sentence:
                    continue
                
                # Look for large numbers (format: XXX,XXX,XXX,XXX for billions)
                # This pattern matches numbers with 3+ comma groups (billions)
                matches = re.findall(r'\b(\d{1,3}(?:,\d{3}){3,})\b', sentence)
                
                for num_str in matches:
                    # Check if "shares" appears in same sentence
                    if re.search(r'shares?', sentence, re.IGNORECASE):
                        return f"{num_str} shares"
        
        # Fallback: Look for explicit "issued and outstanding" pattern
        pattern = r'(\d{1,3}(?:,\d{3})+)\s+shares[^.]*(?:issued\s+and\s+)?outstanding'
        match = re.search(pattern, context, re.IGNORECASE)
        if match:
            return f"{match.group(1)} shares"
        
        return None

    @staticmethod
    def extract_debt(context: str) -> Optional[str]:
        """Extract and sum term debt components from balance sheet"""
        
        current_debt = None
        noncurrent_debt = None
        
        # Look for current term debt
        # Common formats:
        # "Term debt, current portion $ 9,822"
        # "Current portion of term debt $ 9,822"
        
        current_patterns = [
            r'Term\s+debt[,\s]*current\s+portion\s+\$\s*(\d{1,3}(?:,\d{3})*)',
            r'Current\s+portion[^$]*term\s+debt\s+\$\s*(\d{1,3}(?:,\d{3})*)',
        ]
        
        for pattern in current_patterns:
            match = re.search(pattern, context, re.IGNORECASE)
            if match:
                current_debt = int(match.group(1).replace(',', ''))
                break
        
        # Look for non-current term debt
        # Common formats:
        # "Term debt, net of current portion $ 86,840"
        # "Long-term debt $ 86,840"
        
        noncurrent_patterns = [
            r'Term\s+debt[,\s]*net\s+of\s+current\s+portion\s+\$\s*(\d{1,3}(?:,\d{3})*)',
            r'(?:Non-current|Long-term)\s+(?:portion\s+of\s+)?term\s+debt\s+\$\s*(\d{1,3}(?:,\d{3})*)',
        ]
        
        for pattern in noncurrent_patterns:
            match = re.search(pattern, context, re.IGNORECASE)
            if match:
                noncurrent_debt = int(match.group(1).replace(',', ''))
                break
        
        # If we found both components, sum them
        if current_debt is not None and noncurrent_debt is not None:
            total = current_debt + noncurrent_debt
            return f"${total:,} million"
        
        # If we only found one, that's not enough for "total" - return None
        return None


# ============================================================
# CALCULATION - PURE RAG VERSION
# ============================================================

class CalculationExtractor:
    @staticmethod
    def calculate_percentage(context: str) -> Optional[str]:
        """Calculate automotive sales percentage from financial statements"""
        
        # Look for automotive sales and total revenue in the same context
        auto_patterns = [
            r'Automotive\s+sales\s+\$\s*(\d{1,3}(?:,\d{3})+)',
        ]
        
        total_patterns = [
            r'Total\s+revenues?\s+\$\s*(\d{1,3}(?:,\d{3})+)',
        ]
        
        auto_value = None
        total_value = None
        
        # Find automotive sales
        for pattern in auto_patterns:
            match = re.search(pattern, context, re.IGNORECASE)
            if match:
                auto_value = int(match.group(1).replace(',', ''))
                break
        
        # Find total revenue
        for pattern in total_patterns:
            match = re.search(pattern, context, re.IGNORECASE)
            if match:
                total_value = int(match.group(1).replace(',', ''))
                break
        
        # Calculate if both found and total > automotive (sanity check)
        if auto_value and total_value and total_value > auto_value:
            percentage = (auto_value / total_value) * 100
            return f"Approximately {percentage:.1f}% (${auto_value:,}M out of ${total_value:,}M total revenue)"
        
        return None

# ============================================================
# REASONING - PURE RAG VERSION
# ============================================================

class ReasoningExtractor:
    @staticmethod
    def extract(context: str, keywords: List[str]) -> Optional[str]:
        """Extract reasoning from risk factors or other sections"""
        
        if "elon musk" in str(keywords).lower():
            # Find sentences mentioning both Musk and dependency/importance
            sentences = re.split(r'(?<=[.!?])\s+', context)
            
            relevant_sentences = []
            
            for sentence in sentences:
                s_lower = sentence.lower()
                
                # Must mention Musk
                if "musk" not in s_lower:
                    continue
                
                # And mention dependency or importance
                if any(term in s_lower for term in [
                    "depend", "critical", "central", "essential", 
                    "important", "key", "vital", "crucial"
                ]):
                    relevant_sentences.append(sentence.strip())
            
            if not relevant_sentences:
                return None
            
            # Combine the most relevant sentences (up to 3)
            combined = " ".join(relevant_sentences[:3])
            
            # Try to extract a concise summary from the combined text
            # Look for the core statement about dependency
            if "highly dependent" in combined.lower():
                # Find the sentence with "highly dependent"
                for s in relevant_sentences:
                    if "highly dependent" in s.lower():
                        # Clean up and return this sentence
                        # Remove extra whitespace, limit length
                        cleaned = re.sub(r'\s+', ' ', s).strip()
                        if len(cleaned) > 300:
                            cleaned = cleaned[:300] + "..."
                        return cleaned
            
            # Fallback: return the combined relevant text, limited to reasonable length
            combined = re.sub(r'\s+', ' ', combined).strip()
            if len(combined) > 350:
                combined = combined[:350] + "..."
            
            return combined if combined else None
        
        return None


# ============================================================
# DATE
# ============================================================

class DateExtractor:
    @staticmethod
    def extract(context: str) -> Optional[str]:
        """Extract date from signature pages or filing info"""
        
        # Look for date patterns, prioritizing those near "Date:" or signature context
        pattern = (
            r'(?:Date:\s*)?'
            r'(January|February|March|April|May|June|July|August|September|'
            r'October|November|December)\s+(\d{1,2}),?\s+(\d{4})'
        )
        
        match = re.search(pattern, context, re.IGNORECASE)
        
        if match:
            month = match.group(1)
            day = match.group(2)
            year = match.group(3)
            return f"{month} {day}, {year}"
        
        return None

# ============================================================
# YES / NO
# ============================================================

class YesNoExtractor:
    @staticmethod
    def extract(context: str, keywords: List[str]) -> Optional[str]:
        """Extract yes/no answers from context"""
        
        # For SEC staff comments question
        if any('sec' in kw.lower() for kw in keywords):
            # Look for "None" in response to staff comments
            if re.search(r'\bNone\b', context):
                return "No"
        
        return None
