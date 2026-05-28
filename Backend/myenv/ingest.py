# ingest.py
from rag_orchestrator import RAGOrchestrator
import os

def main():
    # Initialize the system for ingestion
    pdf_folder = "./pdf"
    grok_api_key = os.getenv("GROK_API_KEY", "your_grok_api_key_here")
    
    # Check what PDFs are available
    pdf_files = [f for f in os.listdir(pdf_folder) if f.lower().endswith('.pdf')]
    print(f"Found {len(pdf_files)} PDF files: {pdf_files}")
    
    rag_system = RAGOrchestrator(pdf_folder, grok_api_key)
    
    # Load PDFs (one-time ingestion)
    print("Starting PDF ingestion process...")
    print("This will clear any existing database and create a new one.")
    print("=" * 60)
    
    result = rag_system.load_pdfs()
    
    print("=" * 60)
    print("Ingestion completed!")
    print(f"Processed {len(result['processed_pdfs'])} PDF files")
    
    # Verify database content
    doc_count = rag_system.vector_db.get_document_count()
    print(f"Total documents in database: {doc_count}")
    
    if doc_count == 0:
        print("WARNING: No documents found in database!")
    else:
        print("Database is now ready for querying.")

if __name__ == "__main__":
    main()