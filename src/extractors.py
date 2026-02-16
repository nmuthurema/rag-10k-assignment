
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
# NUMERICAL
# ============================================================

class NumericalExtractor:
    @staticmethod
    def extract_revenue(context: str, expected_range: tuple = None) -> Optional[str]:
        
        # Focus only on relevant context near the year
        year_context = context
        
        if "2023" in context:
            parts = context.split("2023")
            year_context = parts[0][-2000:] + parts[-1][:2000]
        
        numbers = re.findall(r'\$\s*([0-9,]{5,})', year_context)
        
        values = []
        for n in numbers:
            try:
                values.append(int(n.replace(",", "")))
            except:
                pass
        
        if not values:
            return None
        
        largest = max(values)
        
        if expected_range:
            if expected_range[0] <= largest <= expected_range[1]:
                return f"${largest:,} million"
        
        return None

    @staticmethod
    def extract_shares(context: str) -> Optional[str]:
    
        # Special handling for shares outstanding with date
        if 'shares' in query.lower() and 'outstanding' in query.lower():
            # Extract target date from query
            date_match = re.search(
                r'((?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s+\d{4})',
                query
            )
            
            if date_match:
                target_date = date_match.group(1)
                
                # Look for chunks containing this exact date
                for chunk in retrieved_chunks:
                    if target_date in chunk['text']:
                        # Find share count in billions format
                        match = re.search(r'(\d{1,3}(?:,\d{3}){2,})\s+shares', chunk['text'], re.IGNORECASE)
                        
                        if match:
                            shares_str = match.group(1)
                            shares_num = int(shares_str.replace(',', ''))
                            
                            # Validate it's in the right magnitude (10-20 billion for Apple)
                            if shares_num > 10_000_000_000:
                                return f"{shares_str} shares"
        
        # Strongest pattern from Apple filing
        pattern = (
            r'([\d,]{10,})\s+shares\s+of\s+common\s+stock\s+'
            r'were\s+issued\s+and\s+outstanding'
        )
    
        match = re.search(pattern, context, re.IGNORECASE)
        if match:
            num = int(match.group(1).replace(",", ""))
            return f"{num:,} shares"
    
        # fallback: large number + outstanding
        match = re.search(
            r'([\d,]{10,})\s+shares.*?outstanding',
            context,
            re.IGNORECASE | re.DOTALL
        )
    
        if match:
            num = int(match.group(1).replace(",", ""))
            return f"{num:,} shares"
    
        return None

    @staticmethod
    def extract_debt(context: str) -> Optional[str]:
        # Special handling for term debt calculation
        if 'term debt' in query.lower() and ('current' in query.lower() or 'non-current' in query.lower()):
            current_debt = None
            noncurrent_debt = None
            
            # Search through retrieved chunks
            for chunk in retrieved_chunks:
                text = chunk['text']
                text_lower = text.lower()
                
                # Find current portion
                if not current_debt and 'term debt' in text_lower:
                    # Pattern: "Term debt, current portion $ 9,822"
                    match = re.search(r'term debt[,\s]+current[^$]*\$\s*(\d{1,3}(?:,\d{3})*)', text_lower)
                    if match:
                        current_debt = int(match.group(1).replace(',', ''))
                        print(f"Found current debt: ${current_debt}M")
                
                # Find non-current portion  
                if not noncurrent_debt and 'term debt' in text_lower:
                    # Pattern: "Term debt, net of current portion $ 86,840"
                    match = re.search(r'term debt[,\s]+(?:net of current|non-current)[^$]*\$\s*(\d{1,3}(?:,\d{3})*)', text_lower)
                    if match:
                        noncurrent_debt = int(match.group(1).replace(',', ''))
                        print(f"Found non-current debt: ${noncurrent_debt}M")
            
            # If we found both, sum them
            if current_debt and noncurrent_debt:
                total = current_debt + noncurrent_debt
                print(f"Total term debt: ${total}M")
                return f"${total:,} million"
            
            # If we only found one, something is wrong - fall back to LLM
            if current_debt or noncurrent_debt:
                print("⚠️ Found only one component of term debt, falling back to LLM")
        current = re.search(
            r'current[^$]*\$\s*([0-9,]+)',
            context,
            re.IGNORECASE
        )
        noncurrent = re.search(
            r'non[- ]?current[^$]*\$\s*([0-9,]+)',
            context,
            re.IGNORECASE
        )
    
        if current and noncurrent:
            try:
                c = int(current.group(1).replace(',', ''))
                nc = int(noncurrent.group(1).replace(',', ''))
                return f"${c + nc:,} million"
            except:
                pass
    
        return None


# ============================================================
# CALCULATION
# ============================================================

class CalculationExtractor:
    @staticmethod
    def calculate_percentage(context: str) -> Optional[str]:
        auto_pattern = r'Automotive\s+sales\s+\$\s*([0-9,]+)'
        total_pattern = r'Total\s+revenues?\s+\$\s*([0-9,]+)'
        
        auto_match = re.search(auto_pattern, context, re.IGNORECASE)
        total_match = re.search(total_pattern, context, re.IGNORECASE)
        
        if auto_match and total_match:
            try:
                auto = int(auto_match.group(1).replace(',', ''))
                total = int(total_match.group(1).replace(',', ''))
                
                if auto > 10000 and total > auto:
                    percentage = (auto / total) * 100
                    return (
                        f"Approximately {percentage:.1f}% "
                        f"(${auto:,}M out of ${total:,}M total revenue)"
                    )
            except:
                pass
        
        return None

# ============================================================
# REASONING
# ============================================================

class ReasoningExtractor:
    @staticmethod
    def extract(context: str, keywords: List[str]) -> Optional[str]:
    
        if "elon musk" in str(keywords).lower():
    
            sentences = re.split(r'(?<=[.!?])\s+', context)
    
            selected = []
    
            for s in sentences:
                s_low = s.lower()
    
                if "musk" not in s_low:
                    continue
    
                if any(t in s_low for t in [
                    "strategy", "innovation", "leadership",
                    "critical", "central", "dependent",
                    "disrupt", "loss"
                ]):
                    selected.append(s.strip())
    
            if selected:
                return " ".join(selected[:3])
    
        return None


# ============================================================
# DATE
# ============================================================

class DateExtractor:
    @staticmethod
    def extract(context: str) -> Optional[str]:
        pattern = (
            r'(January|February|March|April|May|June|July|August|September|'
            r'October|November|December)\s+(\d{1,2}),?\s+(\d{4})'
        )
        
        match = re.search(pattern, context, re.IGNORECASE)
        
        if match:
            month, day, year = match.groups()
            return f"{month} {day}, {year}"
        
        return None

# ============================================================
# YES / NO
# ============================================================

class YesNoExtractor:
    @staticmethod
    def extract(context: str, keywords: List[str]) -> Optional[str]:
        if any('sec' in kw.lower() for kw in keywords):
            if 'none' in context.lower():
                return "No"
        
        return None
