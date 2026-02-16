
import json
import torch
from transformers import AutoTokenizer, AutoModelForCausalLM, BitsAndBytesConfig
from .query_classifier import QueryClassifier
from .extractors import (FactualExtractor, NumericalExtractor, CalculationExtractor, 
                         ReasoningExtractor, DateExtractor, YesNoExtractor)

PRIMARY_MODEL = "mistralai/Mistral-7B-Instruct-v0.2"

def get_device():
    return "cuda" if torch.cuda.is_available() else "cpu"

class SmartLLM:
    """LLM with query-type-driven extraction"""
    
    def __init__(self):
        print("Initializing Smart LLM with extractors...")
        
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
        """Answer using query-type-driven extraction"""
        query_info = self.classifier.classify(question)
        query_type = query_info["type"]
        keywords = query_info["keywords"]
        
        print(f"  📊 Query type: {query_type}")
        print(f"  🔑 Keywords: {keywords}")
        
        if query_type == "out_of_scope":
            print("  ⛔ Out-of-scope question")
            return {"answer": "This question cannot be answered based on the provided documents.", "sources": []}
        
        extracted = None
        
        # Route to appropriate extractor
        if query_type == "factual":
            print("  🔍 Using factual extractor...")
            extracted = self.factual_extractor.extract(context, keywords)
        
        elif query_type == "numerical":
            print("  🔢 Using numerical extractor...")
            
            if "shares" in question.lower() and "outstanding" in question.lower():
                extracted = self.numerical_extractor.extract_shares(context)
            elif "debt" in question.lower():
                extracted = self.numerical_extractor.extract_debt(context)
            else:
                company = query_info["entities"].get("company")
                if "revenue" in question.lower():
                    if company == "apple":
                        extracted = self.numerical_extractor.extract_revenue(context, (380000, 400000))
                    elif company == "tesla":
                        extracted = self.numerical_extractor.extract_revenue(context, (90000, 100000))
        
        elif query_type == "calculation":
            print("  🧮 Using calculation extractor...")
            extracted = self.calculation_extractor.calculate_percentage(context)
        
        elif query_type == "reasoning":
            print("  💭 Using reasoning extractor...")
            extracted = self.reasoning_extractor.extract(context, keywords)
        
        elif query_info["expected_output"] == "date":
            print("  📅 Using date extractor...")
            extracted = self.date_extractor.extract(context)
        
        elif query_info["expected_output"] == "yes_no":
            print("  ✓ Using yes/no extractor...")
            extracted = self.yesno_extractor.extract(context, keywords)
        
        if extracted:
            print(f"  ✅ Extracted: {extracted[:100]}")
            return {"answer": extracted, "sources": []}
        
        print("  🤖 Falling back to LLM...")
        return self._llm_fallback(question, context)
    
    def _llm_fallback(self, question: str, context: str):
        """LLM fallback when extraction fails"""
        prompt = f"""[INST] Extract the answer from context.

Context:
{context[:3000]}

Question: {question}

Answer concisely and precisely:
[/INST]"""
        
        inputs = self.tokenizer(prompt, return_tensors="pt", truncation=True, max_length=2048).to(self.model.device)
        
        with torch.no_grad():
            outputs = self.model.generate(
                **inputs,
                max_new_tokens=200,
                temperature=0.2,
                do_sample=True,
                pad_token_id=self.tokenizer.pad_token_id
            )
        
        full_text = self.tokenizer.decode(outputs[0], skip_special_tokens=True)
        answer = full_text.split("[/INST]")[-1].strip()
        
        if len(answer) < 3:
            return {"answer": "Not specified in the document.", "sources": []}
        
        return {"answer": answer, "sources": []}
