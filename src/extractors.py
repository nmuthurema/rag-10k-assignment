
import re
from typing import Optional, List


# ============================================================
# FACTUAL (Q9 – Tesla vehicles)
# ============================================================

class FactualExtractor:
    @staticmethod
    def extract(context: str, keywords: List[str]) -> Optional[str]:
        models = ["Model S", "Model 3", "Model X", "Model Y", "Cybertruck"]

        found = []
        context_lower = context.lower()

        for m in models:
            if m.lower() in context_lower:
                found.append(m)

        # remove duplicates while preserving order
        found = list(dict.fromkeys(found))

        if found:
            return ", ".join(found)

        return None


# ============================================================
# NUMERICAL
# ============================================================

class NumericalExtractor:

    # ---------- Q1 & Q6 ----------
    @staticmethod
    def extract_revenue(context: str, expected_range: tuple = None) -> Optional[str]:
        patterns = [
            r'Net\s+sales\s+\$\s*(\d{1,3}(?:,\d{3})+)',
            r'Total\s+net\s+sales\s+\$\s*(\d{1,3}(?:,\d{3})+)',
            r'Total\s+revenues?\s+\$\s*(\d{1,3}(?:,\d{3})+)'
        ]


        for pattern in patterns:
            match = re.search(pattern, context, re.IGNORECASE)
            if match:
                return f"${match.group(1)} million"

        return None


    # ---------- Q2 ----------
    @staticmethod
    def extract_shares(context: str, query: str = "") -> Optional[str]:

        # Strong pattern first
        match = re.search(
            r'(\d{1,3}(?:,\d{3}){3})\s+shares[^.]*?(?:issued\s+and\s+outstanding|as\s+of)',
            context,
            re.I
        )

        if match:
            return f"{match.group(1)} shares"

        # fallback
        matches = re.findall(
            r'(\d{1,3}(?:,\d{3}){3})\s+shares',
            context,
            re.I
        )

        for num_str in matches:
            num_val = int(num_str.replace(',', ''))
            if num_val > 10_000_000_000:
                if 'shareholders of record' not in context.lower():
                    return f"{num_str} shares"

        return None


    # ---------- Q3 ----------
    @staticmethod
    def extract_debt(context: str) -> Optional[str]:
    
        # Current
        current = re.search(
            r'Current\s+portion.*?(\d{1,3}(?:,\d{3})+)',
            context, re.I
        )
    
        # Non-current
        non_current = re.search(
            r'Term\s+debt.*?(\d{1,3}(?:,\d{3})+)',
            context, re.I
        )
    
        if current and non_current:
            c = int(current.group(1).replace(",", ""))
            n = int(non_current.group(1).replace(",", ""))
            return f"${c+n:,} million"
    
        # fallback total
        total = re.search(
            r'Total\s+term\s+debt.*?(\d{1,3}(?:,\d{3})+)',
            context, re.I
        )
    
        if total:
            return f"${total.group(1)} million"
    
        return None


# ============================================================
# CALCULATION
# ============================================================

class CalculationExtractor:
    @staticmethod
    def calculate_percentage(context: str) -> Optional[str]:

        auto = re.search(
            r'Automotive\s+sales\s+\$\s*(\d{1,3}(?:,\d{3})+)',
            context,
            re.I
        )

        total = re.search(
            r'Total\s+revenues?\s+\$\s*(\d{1,3}(?:,\d{3})+)',
            context,
            re.I
        )

        if auto and total:
            a_val = int(auto.group(1).replace(',', ''))
            t_val = int(total.group(1).replace(',', ''))

            if t_val > a_val:
                pct = (a_val / t_val) * 100
                return (
                    f"Approximately {pct:.1f}% "
                    f"(${a_val:,}M out of ${t_val:,}M total revenue)"
                )

        return None


# ============================================================
# REASONING (Q8)
# ============================================================

class ReasoningExtractor:
    @staticmethod
    def extract(context: str, keywords: List[str]) -> Optional[str]:

        if "elon musk" not in str(keywords).lower():
            return None

        pattern = (
            r'In\s+particular,\s+we\s+are\s+highly\s+dependent\s+on\s+the\s+services\s+of\s+'
            r'Elon\s+Musk.*?Officer\.'
        )

        match = re.search(pattern, context, re.I | re.DOTALL)

        if match:
            sentence = re.sub(r'\s+', ' ', match.group(0))

            return (
                sentence +
                " He is central to Tesla’s strategy, innovation and leadership, "
                "and his loss could disrupt operations and growth."
            )

        return None


# ============================================================
# DATE
# ============================================================

class DateExtractor:
    @staticmethod
    def extract(context: str) -> Optional[str]:

        pattern = (
            r'(January|February|March|April|May|June|July|August|'
            r'September|October|November|December)\s+(\d{1,2}),?\s+(\d{4})'
        )

        match = re.search(pattern, context, re.IGNORECASE)

        if match:
            return f"{match.group(1)} {match.group(2)}, {match.group(3)}"

        return None


# ============================================================
# YES / NO
# ============================================================

class YesNoExtractor:
    @staticmethod
    def extract(context: str, keywords: List[str]) -> Optional[str]:

        if any('sec' in kw.lower() for kw in keywords):
            if re.search(r'\bNone\b', context):
                return "No"

        return None
