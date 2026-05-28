
# import chromadb
# import shutil
# from typing import List, Dict, Any, Optional
# import os
# import json

# class EfficientVectorDB:
#     """Enhanced Vector database manager with improved multimodal support"""
    
#     def __init__(self, persist_directory: str = "./chroma_db"):
#         self.persist_directory = persist_directory
#         self.client = None
#         self.collection = None
#         self._initialized = False
    
#     def initialize(self, reset: bool = False) -> bool:
#         """Initialize the database with optional cleanup"""
#         try:
#             # Clean up existing database if reset requested
#             if reset and os.path.exists(self.persist_directory):
#                 shutil.rmtree(self.persist_directory)
#                 print(f"Cleaned up existing database at {self.persist_directory}")
            
#             # Create or connect to client and collection
#             self.client = chromadb.PersistentClient(path=self.persist_directory)
#             self.collection = self.client.get_or_create_collection(
#                 name="medical_documents",
#                 metadata={"hnsw:space": "cosine", "description": "FDA drug labels and medical documents with multimodal support"}
#             )
            
#             self._initialized = True
#             if reset:
#                 print("Vector database initialized successfully")
#             else:
#                 print("Connected to existing vector database")
#             return True
            
#         except Exception as e:
#             print(f"Error initializing database: {e}")
#             self._initialized = False
#             return False
        
#     def is_initialized(self) -> bool:
#         """Check if database is initialized"""
#         return self._initialized and self.collection is not None
    
#     def add_documents_batch(self, documents_batch: List[Dict[str, Any]]) -> bool:
#         """Add a batch of documents to the database"""
#         if not self.is_initialized() or not documents_batch:
#             return False
        
#         try:
#             # Separate documents, metadatas, and ids
#             documents = [doc["content"] for doc in documents_batch]
#             metadatas = [doc["metadata"] for doc in documents_batch]
#             ids = [doc["id"] for doc in documents_batch]
            
#             # Add to collection
#             self.collection.add(
#                 documents=documents,
#                 metadatas=metadatas,
#                 ids=ids
#             )
            
#             print(f"Added {len(documents_batch)} documents to database")
#             return True
            
#         except Exception as e:
#             print(f"Error adding documents to database: {e}")
#             return False
    
#     def get_document_count(self) -> int:
#         """Get the number of documents in the collection"""
#         if not self.is_initialized():
#             return 0
#         try:
#             return self.collection.count()
#         except:
#             return 0
    
#     def query(self, query_text: str, n_results: int = 8, pdf_filter: str = None, 
#               content_types: List[str] = None) -> List[Dict[str, Any]]:
#         """Enhanced query with content type filtering and multimodal support"""
#         if not self.is_initialized():
#             return []
        
#         try:
#             # Build where filter
#             where_filter = {}
            
#             if pdf_filter:
#                 where_filter["pdf_name"] = {"$contains": pdf_filter.lower()}
            
#             if content_types:
#                 where_filter["content_type"] = {"$in": content_types}
            
#             # Get more results for better filtering
#             results = self.collection.query(
#                 query_texts=[query_text],
#                 n_results=min(n_results * 3, 25),
#                 where=where_filter if where_filter else None
#             )
            
#             return self._process_query_results(results, n_results)
            
#         except Exception as e:
#             print(f"Error querying database: {e}")
#             # Fallback to query without any filters
#             try:
#                 results = self.collection.query(
#                     query_texts=[query_text],
#                     n_results=n_results * 2
#                 )
#                 return self._process_query_results(results, n_results)
#             except Exception as e2:
#                 print(f"Error in fallback query: {e2}")
#                 return []
    
#     def _process_query_results(self, results: Any, n_results: int) -> List[Dict[str, Any]]:
#         """Process and rank query results with enhanced metadata handling"""
#         if not results or not results["documents"] or len(results["documents"][0]) == 0:
#             return []
        
#         scored_results = []
        
#         for i in range(len(results["documents"][0])):
#             metadata = results["metadatas"][0][i]
            
#             # Handle metadata parsing safely
#             try:
#                 if isinstance(metadata.get('table_data_sample'), str):
#                     metadata['table_data_sample'] = json.loads(metadata['table_data_sample'])
#             except:
#                 metadata['table_data_sample'] = []
            
#             # Get page information with proper fallbacks
#             page_info = self._get_page_info(metadata)
            
#             score = self._calculate_relevance_score(
#                 results["documents"][0][i],
#                 metadata,
#                 results["distances"][0][i] if results["distances"] else 0.5
#             )
            
#             scored_results.append({
#                 "chunk_text": results["documents"][0][i],
#                 "pdf_index": metadata.get("pdf_index", 0),
#                 "pdf_name": metadata.get("pdf_name", "unknown"),
#                 "section": metadata.get("section", ""),
#                 "page_start": page_info.get("start", 1),
#                 "page_end": page_info.get("end", 1),
#                 "pdf_page_number": metadata.get("pdf_page_number", page_info.get("start", 1)),
#                 "pdf_page_start": metadata.get("pdf_page_start", page_info.get("start", 1)),
#                 "pdf_page_end": metadata.get("pdf_page_end", page_info.get("end", 1)),
#                 "is_fda": metadata.get("is_fda", False),
#                 "content_type": metadata.get("content_type", "general"),
#                 "doc_type": metadata.get("doc_type", "text"),
#                 "table_index": metadata.get("table_index"),
#                 "row_index": metadata.get("row_index"),
#                 "image_index": metadata.get("image_index"),
#                 "score": score,
#                 "distance": results["distances"][0][i] if results["distances"] else 0.5
#             })
        
#         # Sort by score and return top results
#         scored_results.sort(key=lambda x: x["score"], reverse=True)
#         return scored_results[:n_results]
    
#     def _get_page_info(self, metadata: Dict[str, Any]) -> Dict[str, int]:
#         """Extract page information with proper fallbacks"""
#         page_start = (
#             metadata.get('pdf_page_start') or 
#             metadata.get('page_start') or 
#             metadata.get('pdf_page_number') or 
#             1
#         )
        
#         page_end = (
#             metadata.get('pdf_page_end') or 
#             metadata.get('page_end') or 
#             page_start
#         )
        
#         return {"start": page_start, "end": page_end}
    
#     def _calculate_relevance_score(self, chunk_text: str, metadata: Dict[str, Any], distance: float) -> float:
#         """Calculate enhanced relevance score"""
#         base_score = 1.0 - min(distance, 1.0)  # Convert distance to similarity
        
#         # Content type weights
#         content_type_weights = {
#             "medical": 0.5,
#             "tabular": 0.4,
#             "visual": 0.4,
#             "general": 0.3,
#             "metadata": 0.1
#         }
        
#         content_bonus = content_type_weights.get(metadata.get("content_type", "general"), 0.3)
        
#         # FDA document bonus
#         fda_bonus = 0.3 if metadata.get("is_fda", False) else 0.0
        
#         # Section importance
#         section = metadata.get("section", "").lower()
#         section_bonus = 0.0
#         if any(key in section for key in ['dosage', 'administration']):
#             section_bonus = 0.2
#         elif any(key in section for key in ['adverse', 'warning', 'contraindication']):
#             section_bonus = 0.1
        
#         # Document type bonus
#         doc_type_bonus = 0.1 if metadata.get("doc_type") in ["table", "image"] else 0.0
        
#         # Calculate final score
#         final_score = base_score * 0.6 + content_bonus * 0.2 + fda_bonus * 0.1 + section_bonus * 0.1 + doc_type_bonus * 0.1
        
#         return min(final_score, 1.0)
    
#     def list_all_documents(self) -> List[str]:
#         """List all unique PDF names in the database"""
#         if not self.is_initialized():
#             return []
        
#         try:
#             results = self.collection.get()
#             pdf_names = set()
            
#             for metadata in results["metadatas"]:
#                 pdf_name = metadata.get("pdf_name")
#                 if pdf_name and pdf_name != "unknown":
#                     pdf_names.add(pdf_name)
            
#             return list(pdf_names)
#         except Exception as e:
#             print(f"Error listing documents: {e}")
#             return []


import chromadb
import shutil
from typing import List, Dict, Any, Optional
import os
import json
import re

class EfficientVectorDB:
    """Enhanced Vector database manager with conversation context support"""
    
    def __init__(self, persist_directory: str = "./chroma_db"):
        self.persist_directory = persist_directory
        self.client = None
        self.collection = None
        self._initialized = False
    
    def initialize(self, reset: bool = False) -> bool:
        """Initialize the database with optional cleanup"""
        try:
            # Clean up existing database if reset requested
            if reset and os.path.exists(self.persist_directory):
                shutil.rmtree(self.persist_directory)
                print(f"Cleaned up existing database at {self.persist_directory}")
            
            # Create or connect to client and collection
            self.client = chromadb.PersistentClient(path=self.persist_directory)
            self.collection = self.client.get_or_create_collection(
                name="medical_documents",
                metadata={"hnsw:space": "cosine", "description": "FDA drug labels and medical documents with multimodal support"}
            )
            
            self._initialized = True
            if reset:
                print("Vector database initialized successfully")
            else:
                print("Connected to existing vector database")
            return True
            
        except Exception as e:
            print(f"Error initializing database: {e}")
            self._initialized = False
            return False
        
    def is_initialized(self) -> bool:
        """Check if database is initialized"""
        return self._initialized and self.collection is not None
    
    def add_documents_batch(self, documents_batch: List[Dict[str, Any]]) -> bool:
        """Add a batch of documents to the database"""
        if not self.is_initialized() or not documents_batch:
            return False
        
        try:
            # Separate documents, metadatas, and ids
            documents = [doc["content"] for doc in documents_batch]
            metadatas = [doc["metadata"] for doc in documents_batch]
            ids = [doc["id"] for doc in documents_batch]
            
            # Add to collection
            self.collection.add(
                documents=documents,
                metadatas=metadatas,
                ids=ids
            )
            
            print(f"Added {len(documents_batch)} documents to database")
            return True
            
        except Exception as e:
            print(f"Error adding documents to database: {e}")
            return False
    
    def get_document_count(self) -> int:
        """Get the number of documents in the collection"""
        if not self.is_initialized():
            return 0
        try:
            return self.collection.count()
        except:
            return 0
    
    def query(self, query_text: str, n_results: int = 8, pdf_filter: str = None, 
              content_types: List[str] = None, conversation_context: List[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """Enhanced query with content type filtering, conversation context, and multimodal support"""
        if not self.is_initialized():
            return []
        
        try:
            # Enhance query with conversation context
            enhanced_query = self._enhance_query_with_context(query_text, conversation_context)
            
            # Build where filter
            where_filter = {}
            
            if pdf_filter:
                where_filter["pdf_name"] = {"$contains": pdf_filter.lower()}
            
            if content_types:
                where_filter["content_type"] = {"$in": content_types}
            
            # Get more results for better filtering
            results = self.collection.query(
                query_texts=[enhanced_query],
                n_results=min(n_results * 3, 25),
                where=where_filter if where_filter else None
            )
            
            return self._process_query_results(results, n_results, query_text, conversation_context)
            
        except Exception as e:
            print(f"Error querying database: {e}")
            # Fallback to query without any filters
            try:
                results = self.collection.query(
                    query_texts=[query_text],
                    n_results=n_results * 2
                )
                return self._process_query_results(results, n_results, query_text, conversation_context)
            except Exception as e2:
                print(f"Error in fallback query: {e2}")
                return []
    
    def _enhance_query_with_context(self, query_text: str, conversation_context: List[Dict[str, Any]]) -> str:
        """Enhance the query with conversation context"""
        if not conversation_context:
            return query_text
        
        # Extract drug names and key topics from conversation context
        context_keywords = set()
        current_drug = None
        
        for exchange in reversed(conversation_context):
            # Look for drug mentions
            drug_keywords = [
  'orencia',
  'simponi',
  'aria',
  'humira',
  'enbrel',
  'remicade',
  'keytruda',
  'alora_pi',
  'Augtyro',
  'BLUJEPA',
  'Cinbinqo',
  'dalvance_pi',
  'Herceptin',
  'Ibuprofen',
  'jakafi',
  'methadone',
  'Olumiant',
  'opzelura-prescribing-infor',
  'PRILOSEC',
  'rinvoq_pi',
  'Sotyktu',
  'STELARA',
  'XELJANZ'
]

            for drug in drug_keywords:
                if drug in exchange.get('user_query', '').lower() or drug in exchange.get('assistant_response', '').lower():
                    current_drug = drug
                    break
            
            if current_drug:
                break
        
        # If we found a drug in context but it's not in the current query, add it
        if current_drug and current_drug not in query_text.lower():
            enhanced_query = f"{current_drug} {query_text}"
            print(f"Enhanced query with context drug: {enhanced_query}")
            return enhanced_query
        
        return query_text
    
    def _process_query_results(self, results: Any, n_results: int, original_query: str, 
                             conversation_context: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Process and rank query results with enhanced metadata handling and context awareness"""
        if not results or not results["documents"] or len(results["documents"][0]) == 0:
            return []
        
        scored_results = []
        
        for i in range(len(results["documents"][0])):
            metadata = results["metadatas"][0][i]
            
            # Handle metadata parsing safely
            try:
                if isinstance(metadata.get('table_data_sample'), str):
                    metadata['table_data_sample'] = json.loads(metadata['table_data_sample'])
            except:
                metadata['table_data_sample'] = None
            
            # Calculate relevance score based on multiple factors
            relevance_score = self._calculate_relevance_score(
                results["documents"][0][i],
                results["distances"][0][i],
                original_query,
                metadata,
                conversation_context
            )
            
            # Create result dict with enhanced metadata
            result_dict = {
                "chunk_text": results["documents"][0][i],
                "metadata": metadata,
                "distance": results["distances"][0][i],
                "relevance_score": relevance_score,
                "id": results["ids"][0][i],
                "pdf_name": metadata.get("pdf_name", "Unknown"),
                "section": metadata.get("section", "Unknown"),
                "content_type": metadata.get("content_type", "text"),
                "doc_type": metadata.get("doc_type", "text"),
                "pdf_page_number": metadata.get("pdf_page_number"),
                "pdf_page_start": metadata.get("pdf_page_start"),
                "pdf_page_end": metadata.get("pdf_page_end"),
                "page_start": metadata.get("page_start"),
                "page_end": metadata.get("page_end"),
                "table_index": metadata.get("table_index"),
                "image_index": metadata.get("image_index"),
                "table_data_sample": metadata.get("table_data_sample")
            }
            
            scored_results.append(result_dict)
        
        # Sort by relevance score (descending)
        scored_results.sort(key=lambda x: x["relevance_score"], reverse=True)
        
        # Return top n_results
        return scored_results[:n_results]
    
    def _calculate_relevance_score(self, content: str, distance: float, query: str, 
                                 metadata: Dict[str, Any], conversation_context: List[Dict[str, Any]]) -> float:
        """Calculate enhanced relevance score with conversation context awareness"""
        base_score = 1.0 - distance  # Convert distance to similarity
        
        # Boost for conversation context relevance
        context_boost = 1.0
        if conversation_context:
            # Check if this result matches the current conversation topic
            current_drug = None
            for exchange in reversed(conversation_context):
                if exchange.get('detected_drug'):
                    current_drug = exchange['detected_drug']
                    break
            
            if current_drug and current_drug.lower() in content.lower():
                context_boost = 1.5  # 50% boost for context-relevant content
        
        # Content type weighting
        content_type = metadata.get("content_type", "text")
        type_weight = {
            "text": 1.0,
            "table": 1.2,  # Slight preference for tables
            "image": 0.8   # Slight penalty for images (harder to process)
        }.get(content_type, 1.0)
        
        # Section importance weighting
        section = metadata.get("section", "").lower()
        section_weight = {
            "highlights": 1.5,
            "indications and usage": 1.4,
            "dosage and administration": 1.4,
            "warnings and precautions": 1.4,
            "adverse reactions": 1.4,
            "clinical studies": 1.2,
            "mechanism of action": 1.2,
            "description": 1.1,
            "how supplied/storage and handling": 0.8,
            "patient counseling information": 1.0,
            "references": 0.7
        }.get(section, 1.0)
        
        # Query-specific boosts
        query_boost = 1.0
        query_lower = query.lower()
        
        # Boost for exact matches in important sections
        if any(keyword in query_lower for keyword in ["side effect", "adverse", "warning"]):
            if "adverse" in section.lower() or "warning" in section.lower():
                query_boost = 1.3
        
        # Boost for dosage-related queries
        if any(keyword in query_lower for keyword in ["dose", "dosage", "administration"]):
            if "dosage" in section.lower() or "administration" in section.lower():
                query_boost = 1.3
        
        # Calculate final score
        final_score = base_score * context_boost * type_weight * section_weight * query_boost
        
        return final_score
    
    def list_all_documents(self) -> List[str]:
        """List all unique PDFs in the database"""
        if not self.is_initialized():
            return []
        
        try:
            # Get all documents to extract unique PDF names
            all_results = self.collection.get()
            if not all_results or not all_results["metadatas"]:
                return []
            
            unique_pdfs = set()
            for metadata in all_results["metadatas"]:
                if "pdf_name" in metadata:
                    unique_pdfs.add(metadata["pdf_name"])
            
            return sorted(list(unique_pdfs))
            
        except Exception as e:
            print(f"Error listing documents: {e}")
            return []
        
    # Add this method to the EfficientVectorDB class
    def query_with_pdf_filter(self, query_text: str, pdf_name: str, n_results: int = 8) -> List[Dict[str, Any]]:
        """Query documents from a specific PDF"""
        if not self.is_initialized():
            return []
        
        try:
            # Filter by PDF name
            where_filter = {"pdf_name": {"$eq": pdf_name}}
            
            results = self.collection.query(
                query_texts=[query_text],
                n_results=n_results,
                where=where_filter
            )
            
            return self._process_query_results(results, n_results, query_text, None)
            
        except Exception as e:
            print(f"Error querying with PDF filter: {e}")
            # Fallback to regular query
            return self.query(query_text, n_results)