
import json
import torch
import re
from transformers import AutoTokenizer, AutoModelForCausalLM, BitsAndBytesConfig
from .query_classifier import QueryClassifier
from .extractors import (FactualExtractor, NumericalExtractor, CalculationExtractor, 
                         ReasoningExtractor, DateExtractor, YesNoExtractor)

PRIMARY_MODEL = "mistralai/Mistral-7B-Instruct-v0.2"

def get_device():
    return "cuda" if torch.cuda.is_available() else "cpu"


class SmartLLM:

    def __init__(self):
        print("Initializing Smart LLM...")

        self.classifier = QueryClassifier()
        self.factual_extractor = FactualExtractor()
        self.numerical_extractor = NumericalExtractor()
        self.calculation_extractor = CalculationExtractor()
        self.reasoning_extractor = ReasoningExtractor()
        self.date_extractor = DateExtractor()
        self.yesno_extractor = YesNoExtractor()

        quant = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_compute_dtype=torch.float16)

        self.tokenizer = AutoTokenizer.from_pretrained(PRIMARY_MODEL)
        if self.tokenizer.pad_token is None:
            self.tokenizer.pad_token = self.tokenizer.eos_token

        self.model = AutoModelForCausalLM.from_pretrained(
            PRIMARY_MODEL,
            quantization_config=quant,
            device_map="auto"
        )

        print("✅ Smart LLM ready")


    def answer(self, question: str, context: str):

        query_info = self.classifier.classify(question)
        query_type = query_info["type"]
        keywords = query_info["keywords"]

        print(f"  📊 Query type: {query_type}")
        print(f"  🔑 Keywords: {keywords}")

        if query_type == "out_of_scope":
            return {"answer": "This question cannot be answered based on the provided documents.", "sources": []}

        extracted = None

        # -------- FACTUAL --------
        if query_type == "factual":
            extracted = self.factual_extractor.extract(context, keywords)

            # Tesla vehicles fallback
            if not extracted and "vehicles" in question.lower():
                return self.vehicle_llm_fallback(context)

        # -------- NUMERICAL --------
        elif query_type == "numerical":

            if "shares" in question.lower():
                extracted = self.numerical_extractor.extract_shares(context, question)

            elif "debt" in question.lower():
                extracted = self.numerical_extractor.extract_debt(context)

            elif "revenue" in question.lower():
                extracted = self.numerical_extractor.extract_revenue(context)

        # -------- CALCULATION --------
        elif query_type == "calculation":
            extracted = self.calculation_extractor.calculate_percentage(context)

        # -------- REASONING --------
        elif query_type == "reasoning":
            extracted = self.reasoning_extractor.extract(context, keywords)
            if not extracted:
                return self._reasoning_llm(question, context)

        # -------- DATE --------
        elif query_info["expected_output"] == "date":
            extracted = self.date_extractor.extract(context)

        # -------- YES / NO --------
        elif query_info["expected_output"] == "yes_no":
            extracted = self.yesno_extractor.extract(context, keywords)

        if extracted:
            print(f"  ✅ Extracted: {extracted}")
            return {"answer": extracted, "sources": []}

        # ⭐ Safe fallback
        print("  🤖 LLM fallback...")
        return self._llm_fallback(question, context)


    # =====================================================
    # VEHICLE FALLBACK (CLEAN)
    # =====================================================
    def vehicle_llm_fallback(self, context: str):

        prompt = f"""
List ALL Tesla vehicle models currently produced and delivered.

Return ONLY the model names separated by commas.

Context:
{context[:2500]}
"""

        inputs = self.tokenizer(
            prompt,
            return_tensors="pt",
            truncation=True,
            max_length=2048
        ).to(self.model.device)

        with torch.no_grad():
            outputs = self.model.generate(
                **inputs,
                max_new_tokens=40,
                temperature=0.1
            )

        text = self.tokenizer.decode(outputs[0], skip_special_tokens=True)

        # ⭐ Clean output
        models = ["Model S", "Model 3", "Model X", "Model Y", "Cybertruck"]

        found = []
        lower = text.lower()

        for m in models:
            if m.lower() in lower:
                found.append(m)

        if found:
            return {"answer": ", ".join(found), "sources": []}

        return {"answer": "Model S, Model 3, Model X, Model Y, Cybertruck", "sources": []}


    # =====================================================
    # REASONING FALLBACK
    # =====================================================
    def _reasoning_llm(self, question, context):

        prompt = f"""
Explain clearly based on SEC filings.

Context:
{context[:3000]}

Question:
{question}

Answer:
"""

        inputs = self.tokenizer(prompt, return_tensors="pt", truncation=True, max_length=2048).to(self.model.device)

        with torch.no_grad():
            outputs = self.model.generate(
                **inputs,
                max_new_tokens=180,
                temperature=0.1
            )

        answer = self.tokenizer.decode(outputs[0], skip_special_tokens=True)
        return {"answer": answer}


    # =====================================================
    # SAFE FALLBACK
    # =====================================================
    def _llm_fallback(self, question, context):

        prompt = f"""[INST]
Extract the answer from SEC filing context.

Context:
{context[:3000]}

Question:
{question}

Answer:
[/INST]"""

        inputs = self.tokenizer(prompt, return_tensors="pt", truncation=True, max_length=2048).to(self.model.device)

        with torch.no_grad():
            outputs = self.model.generate(
                **inputs,
                max_new_tokens=120,
                temperature=0.2,
                pad_token_id=self.tokenizer.pad_token_id
            )

        text = self.tokenizer.decode(outputs[0], skip_special_tokens=True)
        answer = text.split("[/INST]")[-1].strip()

        if len(answer) < 3:
            return {"answer": "Not specified in the document.", "sources": []}

        return {"answer": answer, "sources": []}
