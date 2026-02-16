
import os
import re
import torch
from typing import List, Dict
from pypdf import PdfReader
from sentence_transformers import SentenceTransformer
from chromadb import PersistentClient

EMBED_MODEL_NAME = "BAAI/bge-base-en"
COLLECTION_NAME = "sec_10k"
CHUNK_SIZE = 600
CHUNK_OVERLAP = 150

def get_device():
    return "cuda" if torch.cuda.is_available() else "cpu"

# FIXED: Improved table detection
class TableDetector:
    @staticmethod
    def has_dollar_amounts(line: str) -> bool:
        """Check if line has dollar amounts"""
        return bool(re.search(r'\$\s*[\d,]+', line))
    
    @staticmethod
    def has_multiple_numbers(line: str) -> bool:
        """Check if line has multiple numbers (common in tables)"""
        numbers = re.findall(r'\d{1,3}(?:,\d{3})*', line)
        return len(numbers) >= 2
    
    @staticmethod
    def has_wide_spacing(line: str) -> bool:
        """Check if line has wide spacing (table columns)"""
        # 2+ spaces indicate column separation
        return bool(re.search(r'\s{2,}', line))
    
    @staticmethod
    def is_financial_keyword(line: str) -> bool:
        """Check for financial statement keywords"""
        keywords = [
            'assets', 'liabilities', 'equity', 'revenue', 'sales',
            'income', 'cash', 'debt', 'total', 'net', 'balance',
            'current', 'non-current', 'shares', 'common stock',
            'term debt', 'accounts payable', 'inventory'
        ]
        line_lower = line.lower()
        return any(kw in line_lower for kw in keywords)
    
    @staticmethod
    def is_table_row(line: str) -> bool:
        """Enhanced table row detection"""
        if len(line.strip()) < 5:
            return False
        
        # Strong indicators
        has_dollars = TableDetector.has_dollar_amounts(line)
        has_numbers = TableDetector.has_multiple_numbers(line)
        has_spacing = TableDetector.has_wide_spacing(line)
        has_keyword = TableDetector.is_financial_keyword(line)
        
        # Table row if:
        # 1. Has dollar amounts AND spacing
        # 2. Has multiple numbers AND spacing
        # 3. Has financial keyword AND (numbers OR spacing)
        
        if has_dollars and has_spacing:
            return True
        
        if has_numbers and has_spacing:
            return True
        
        if has_keyword and (has_numbers or has_spacing or has_dollars):
            return True
        
        return False
    
    @staticmethod
    def extract_table_blocks(text: str) -> List[Dict]:
        """Extract tables with improved detection"""
        lines = text.split('\n')
        tables = []
        current_table = []
        in_table = False
        
        for i, line in enumerate(lines):
            stripped = line.strip()
            
            if not stripped:
                # Empty line might end table
                if in_table and len(current_table) >= 3:
                    tables.append({
                        'text': '\n'.join(current_table),
                        'lines': current_table.copy(),
                        'start_line': i - len(current_table),
                        'end_line': i
                    })
                    current_table = []
                    in_table = False
                continue
            
            is_table = TableDetector.is_table_row(line)
            
            if is_table:
                in_table = True
                current_table.append(stripped)
            else:
                # Not a table row
                if in_table and len(current_table) >= 3:
                    # Save accumulated table
                    tables.append({
                        'text': '\n'.join(current_table),
                        'lines': current_table.copy(),
                        'start_line': i - len(current_table),
                        'end_line': i
                    })
                current_table = []
                in_table = False
        
        # Catch table at end of text
        if len(current_table) >= 3:
            tables.append({
                'text': '\n'.join(current_table),
                'lines': current_table.copy(),
                'start_line': len(lines) - len(current_table),
                'end_line': len(lines)
            })
        
        return tables

def detect_section(text: str) -> str:
    """Detect document section with better patterns"""
    t = text.lower()
    
    # Balance sheet detection
    if "consolidated balance sheet" in t:
        return "balance_sheet"
    if "balance sheet" in t and any(word in t for word in ['assets', 'liabilities']):
        return "balance_sheet"
    
    # Income statement
    if "consolidated statements of operations" in t:
        return "income_statement"
    if "income statement" in t or "statement of operations" in t:
        return "income_statement"
    
    # Cash flow
    if "cash flow" in t:
        return "cash_flow"
    
    # Item sections
    if "item 8" in t:
        return "item_8"
    if "item 7" in t:
        return "item_7"
    if "item 1a" in t:
        return "item_1a"
    if "item 5" in t:
        return "item_5"
    
    return "general"

def load_pdf(path: str) -> List[Dict]:
    """Load PDF pages"""
    reader = PdfReader(path)
    pages = []
    for i, page in enumerate(reader.pages):
        try:
            text = page.extract_text() or ""
        except:
            text = ""
        pages.append({"page": i + 1, "text": text})
    return pages

def smart_chunk(pages: List[Dict]) -> List[Dict]:
    """Chunk with table preservation - FIXED"""
    chunks = []
    
    for p in pages:
        page = p["page"]
        text = p["text"]
        
        # Extract tables
        tables = TableDetector.extract_table_blocks(text)
        table_line_ranges = set()
        
        # Track which lines are in tables
        for t in tables:
            for line_num in range(t["start_line"], t["end_line"]):
                table_line_ranges.add(line_num)
        
        # Create table chunks (keep tables intact)
        for t in tables:
            table_text = t["text"]
            
            # Only create chunk if table has meaningful content
            if len(table_text) > 50:
                chunks.append({
                    "text": table_text,
                    "page": page,
                    "section": detect_section(table_text),
                    "is_table": True
                })
        
        # Create non-table chunks
        lines = text.split('\n')
        non_table_lines = [
            line for i, line in enumerate(lines) 
            if i not in table_line_ranges and line.strip()
        ]
        
        non_table_text = '\n'.join(non_table_lines)
        words = non_table_text.split()
        
        start = 0
        while start < len(words):
            end = min(start + CHUNK_SIZE, len(words))
            chunk_text = " ".join(words[start:end])
            
            # Only create chunk if it has content
            if len(chunk_text.strip()) > 20:
                chunks.append({
                    "text": chunk_text,
                    "page": page,
                    "section": detect_section(chunk_text),
                    "is_table": False
                })
            
            if end == len(words):
                break
            start = end - CHUNK_OVERLAP
    
    return chunks

def build_documents(data_folder="data") -> List[Dict]:
    """Build document collection"""
    docs = []
    print("📄 Processing PDFs...")
    
    for file in os.listdir(data_folder):
        if not file.endswith(".pdf"):
            continue
        
        path = os.path.join(data_folder, file)
        print(f"  Processing: {file}")
        
        pages = load_pdf(path)
        company = "apple" if "10-q" in file.lower() or "10-k" in file.lower() else "tesla"
        chunks = smart_chunk(pages)
        
        for i, c in enumerate(chunks):
            docs.append({
                "id": f"{file}_p{c['page']}_{i}",
                "text": c["text"],
                "metadata": {
                    "document": file,
                    "page": int(c["page"]),
                    "is_table": bool(c.get("is_table", False)),
                    "company": company,
                    "section": str(c.get("section", "general"))
                }
            })
        
        # Debug: Show table detection stats for this file
        table_chunks = [c for c in chunks if c.get("is_table")]
        print(f"    • Total chunks: {len(chunks)}")
        print(f"    • Table chunks: {len(table_chunks)}")
        
        # Show sample table chunks
        balance_sheet_tables = [c for c in table_chunks if "balance" in c["section"]]
        if balance_sheet_tables:
            print(f"    • Balance sheet tables: {len(balance_sheet_tables)}")
            print(f"      Sample from page {balance_sheet_tables[0]['page']}:")
            print(f"      {balance_sheet_tables[0]['text'][:200]}...")
    
    print(f"\n📊 Total chunks: {len(docs)}")
    table_count = sum(1 for d in docs if d["metadata"]["is_table"])
    print(f"  • Tables: {table_count}")
    print(f"  • Balance sheets: {sum(1 for d in docs if d['metadata']['section'] == 'balance_sheet')}")
    print(f"  • Income statements: {sum(1 for d in docs if d['metadata']['section'] == 'income_statement')}")
    
    return docs

def index_documents(persist_dir="/kaggle/working/chroma_db"):
    import shutil
    import time
    import gc
    
    # CRITICAL: Force cleanup
    if os.path.exists(persist_dir):
        try:
            shutil.rmtree(persist_dir, ignore_errors=True)
        except:
            pass
        time.sleep(3)
    
    gc.collect()
    
    os.makedirs(persist_dir, exist_ok=True)
    os.chmod(persist_dir, 0o777)
    
    print("DB path:", persist_dir)
    
    model = SentenceTransformer(EMBED_MODEL_NAME, device=get_device())
    
    client = PersistentClient(path=persist_dir)
    
    try:
        client.delete_collection(COLLECTION_NAME)
        time.sleep(1)
    except:
        pass
    
    collection = client.get_or_create_collection(COLLECTION_NAME)
    
    docs = build_documents()
    texts = [d["text"] for d in docs]
    
    print("\n🔢 Generating embeddings...")
    embeddings = model.encode(texts, batch_size=32, convert_to_numpy=True, show_progress_bar=True)
    
    print("💿 Storing vectors...")
    
    batch_size = 50
    for i in range(0, len(docs), batch_size):
        try:
            collection.add(
                ids=[d["id"] for d in docs[i:i+batch_size]],
                documents=texts[i:i+batch_size],
                metadatas=[d["metadata"] for d in docs[i:i+batch_size]],
                embeddings=embeddings[i:i+batch_size].tolist()
            )
        except Exception as e:
            print(f"Warning: Batch {i} failed: {e}")
            for j in range(i, min(i+batch_size, len(docs))):
                try:
                    collection.add(
                        ids=[docs[j]["id"]],
                        documents=[texts[j]],
                        metadatas=[docs[j]["metadata"]],
                        embeddings=[embeddings[j].tolist()]
                    )
                except Exception as e2:
                    print(f"  Skipped doc {j}: {e2}")
    
    print(f"✅ Indexed {len(docs)} chunks")
    
    # Verify tables were indexed
    table_count = sum(1 for d in docs if d["metadata"]["is_table"])
    print(f"✅ Verified {table_count} table chunks indexed")
