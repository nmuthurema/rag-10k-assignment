
from typing import Dict, List
from .retriever import Retriever
from .llm import LocalLLM

def build_context(chunks: List[Dict], max_chars: int = 3000) -> str:
    parts = []
    total_chars = 0
    for i, c in enumerate(chunks, 1):
        doc = c["metadata"]["document"]
        page = c["metadata"]["page"]
        text = c["text"]
        snippet = f"[{i}] {doc}, p. {page}\n{text[:600]}\n\n"
        if total_chars + len(snippet) > max_chars:
            break
        parts.append(snippet)
        total_chars += len(snippet)
    return "".join(parts)

class RAGPipeline:
    def __init__(self, persist_dir="chroma_db"):
        print("Initializing RAG...")
        print("=" * 60)
        print("\n🔄 Loading retriever...")
        self.retriever = Retriever(persist_dir)
        print("\n🔄 Loading LLM...")
        self.llm = LocalLLM()
        print("\n" + "=" * 60)
        print("✅ RAG ready")
        print("=" * 60)
    
    def answer_question(self, query: str) -> Dict:
        print("\n  🔍 Retrieving...")
        chunks = self.retriever.retrieve(query, top_k=5)
        if not chunks:
            return {"answer": "This question cannot be answered based on the provided documents.", "sources": []}
        print(f"  ✅ Retrieved {len(chunks)} chunks")
        seen = set()
        unique_chunks = []
        for c in chunks:
            if c["text"] not in seen:
                unique_chunks.append(c)
                seen.add(c["text"])
        context = build_context(unique_chunks)
        print("  🤖 Generating answer...")
        try:
            result = self.llm.answer(query, context)
        except Exception as e:
            print(f"  ❌ Error: {e}")
            return {"answer": "Not specified in the document.", "sources": []}
        answer = result.get("answer", "").strip()
        if "not specified" in answer.lower():
            return {"answer": "Not specified in the document.", "sources": []}
        if "cannot be answered" in answer.lower():
            return {"answer": "This question cannot be answered based on the provided documents.", "sources": []}
        valid_sources = []
        for c in unique_chunks:
            valid_sources.append([c["metadata"]["document"], c["metadata"]["page"]])
        print(f"  ✅ Done")
        return {"answer": answer, "sources": valid_sources}
