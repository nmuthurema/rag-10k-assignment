
from typing import Dict, List
from .retriever import ImprovedRetriever
from .llm import SmartLLM

def build_context(chunks: List[Dict], max_chars: int = 15000) -> str:
    """Build context from chunks without truncation"""
    parts = []
    total_chars = 0
    
    for i, c in enumerate(chunks, 1):
        doc = c["metadata"]["document"]
        page = c["metadata"]["page"]
        text = c["text"]
        
        snippet = f"[{i}] {doc}, p. {page}\\\\n{text}\\\\n\\\\n"
        
        if total_chars + len(snippet) > max_chars:
            break
        
        parts.append(snippet)
        total_chars += len(snippet)
    
    return "".join(parts)

class ImprovedRAGPipeline:
    """Production-ready RAG pipeline"""
    
    def __init__(self, persist_dir="chroma_db"):
        print("\\\\n" + "="*60)
        print("🚀 INITIALIZING QUERY-TYPE-DRIVEN RAG")
        print("="*60)
        print("\\\\n📡 Loading retriever...")
        self.retriever = ImprovedRetriever(persist_dir)
        print("\\\\n🧠 Loading Smart LLM...")
        self.llm = SmartLLM()
        print("\\\\n" + "="*60)
        print("✅ RAG READY")
        print("="*60)
    
    def answer_question(self, query: str, verbose: bool = False) -> Dict:
        """Answer question using query-type-driven approach"""
        if verbose:
            print(f"\\\\n🔍 Query: {query[:80]}...")
        
        # Retrieve chunks
        top_k = 20
        chunks, analysis = self.retriever.retrieve(query, top_k=top_k)
        
        if not chunks:
            return {
                "answer": "This question cannot be answered based on the provided documents.", 
                "sources": []
            }
        
        if verbose:
            table_count = sum(1 for c in chunks if c["metadata"].get("is_table"))
            print(f"  ✅ Retrieved {len(chunks)} chunks (tables: {table_count})")

        table_chunks = [c for c in unique_chunks if c["metadata"].get("is_table")]
        table_context = "\n".join(c["text"] for c in table_chunks[:3])
        context = table_context + "\n\n" + build_context(unique_chunks)

        # Deduplicate
        seen = set()
        unique_chunks = []
        for c in chunks:
            if c["text"] not in seen:
                unique_chunks.append(c)
                seen.add(c["text"])
        
        # Build context
        context = build_context(unique_chunks, max_chars=15000)
        
        # Generate answer
        try:
            result = self.llm.answer(query, context)
        except Exception as e:
            print(f"  ❌ Error: {e}")
            return {"answer": "Not specified in the document.", "sources": []}
        
        answer = result.get("answer", "").strip()
        
        # Extract sources
        valid_sources = []
        for c in unique_chunks[:5]:
            valid_sources.append([c["metadata"]["document"], c["metadata"]["page"]])
        
        return {"answer": answer, "sources": valid_sources}
