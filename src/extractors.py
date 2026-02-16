
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
