# # rag_orchestrator.py
# import os
# from typing import List, Dict, Any, TypedDict, Optional
# from langgraph.graph import StateGraph, END
# from pdf_processor import PDFProcessor
# from vector_db import EfficientVectorDB
# from query_processor import QueryProcessor

# class RAGState(TypedDict):
#     pdf_directory: str
#     pdf_files: List[str]
#     processed_pdfs: List[Dict[str, Any]]
#     current_pdf: Optional[Dict[str, Any]]
#     query: str
#     query_analysis: Dict[str, Any]
#     retrieved_chunks: List[Dict[str, Any]]
#     response: str
#     db_initialized: bool
#     ingestion_mode: bool

# class RAGOrchestrator:
#     """Main orchestrator for the RAG system using LangGraph"""
    
#     def __init__(self, pdf_directory: str, gemini_api_key: str):
#         self.pdf_directory = pdf_directory
#         self.gemini_api_key = gemini_api_key
#         self.pdf_processor = PDFProcessor(gemini_api_key)
#         self.vector_db = EfficientVectorDB()
#         self.query_processor = QueryProcessor(gemini_api_key)
#         self.workflow = self._create_workflow()
#         self._ingestion_completed = False
    
#     def _create_workflow(self) -> StateGraph:
#         """Create the LangGraph workflow"""
#         workflow = StateGraph(RAGState)
        
#         # Add nodes with correct method names
#         workflow.add_node("initialize", self._initialize_system)
#         workflow.add_node("process_pdf", self._process_next_pdf)
#         workflow.add_node("add_to_db", self._add_to_database)
#         workflow.add_node("analyze_query", self._analyze_query)
#         workflow.add_node("retrieve_info", self._retrieve_information)
#         workflow.add_node("generate_response", self._generate_response)
        
#         # Set entry point
#         workflow.set_entry_point("initialize")
        
#         # Add edges for PDF processing (only in ingestion mode)
#         workflow.add_conditional_edges(
#             "initialize",
#             lambda state: "process_pdf" if state.get("ingestion_mode", False) else "analyze_query"
#         )
        
#         # Proper PDF processing loop
#         workflow.add_edge("process_pdf", "add_to_db")
#         workflow.add_conditional_edges(
#             "add_to_db",
#             lambda state: "process_pdf" if state["pdf_files"] else END
#         )
        
#         # Add edges for query processing
#         workflow.add_edge("analyze_query", "retrieve_info")
#         workflow.add_edge("retrieve_info", "generate_response")
#         workflow.add_edge("generate_response", END)
        
#         return workflow.compile()
    
#     def _initialize_system(self, state: RAGState) -> dict:
#         """Initialize the system"""
#         if not os.path.exists(state["pdf_directory"]):
#             raise ValueError(f"Directory {state['pdf_directory']} does not exist")
        
#         pdf_files = [f for f in os.listdir(state["pdf_directory"]) if f.lower().endswith('.pdf')]
        
#         # Only reset DB if we're doing ingestion (when ingestion_mode is True)
#         reset_db = state["ingestion_mode"]
#         db_initialized = self.vector_db.initialize(reset=reset_db)
        
#         return {
#             "pdf_files": pdf_files if state["ingestion_mode"] else [],
#             "processed_pdfs": [],
#             "db_initialized": db_initialized
#         }
    
#     def _process_next_pdf(self, state: RAGState) -> dict:
#         """Process next PDF (only in ingestion mode)"""
#         if not state["pdf_files"]:
#             return {"pdf_files": [], "current_pdf": None}
        
#         pdf_file = state["pdf_files"][0]
#         pdf_path = os.path.join(state["pdf_directory"], pdf_file)
#         pdf_index = len(state["processed_pdfs"])
        
#         print(f"Processing {pdf_file} ({len(state['processed_pdfs']) + 1}/{len(state['pdf_files']) + len(state['processed_pdfs'])})...")
        
#         # Process PDF using the enhanced processor
#         try:
#             documents = self.pdf_processor.process_pdf_for_db(pdf_path, pdf_index)
            
#             if not documents:
#                 print(f"Warning: Could not process {pdf_file}")
#                 return {"pdf_files": state["pdf_files"][1:], "current_pdf": None}
            
#             current_pdf = {
#                 "name": pdf_file,
#                 "index": pdf_index,
#                 "documents": documents
#             }
            
#             return {
#                 "current_pdf": current_pdf,
#                 "pdf_files": state["pdf_files"][1:]
#             }
            
#         except Exception as e:
#             print(f"Error processing {pdf_file}: {e}")
#             return {"pdf_files": state["pdf_files"][1:], "current_pdf": None}
    
#     def _add_to_database(self, state: RAGState) -> dict:
#         """Add PDF to database (only in ingestion mode)"""
#         if not state["current_pdf"] or not state["db_initialized"]:
#             return {"processed_pdfs": state["processed_pdfs"]}
        
#         current_pdf = state["current_pdf"]
#         success = self.vector_db.add_documents_batch(current_pdf["documents"])
        
#         if success:
#             processed_pdfs = state["processed_pdfs"] + [current_pdf]
#             print(f"Successfully processed {current_pdf['name']}")
#             return {"processed_pdfs": processed_pdfs}
#         else:
#             print(f"Failed to add {current_pdf['name']} to database")
#             return {"processed_pdfs": state["processed_pdfs"]}
    
#     def _analyze_query(self, state: RAGState) -> dict:
#         """Analyze user query"""
#         return {"query_analysis": self.query_processor.analyze_query(state["query"])}
    
#     def _retrieve_information(self, state: RAGState) -> dict:
#         """Retrieve relevant information without filtering"""
#         if not state["db_initialized"]:
#             return {"retrieved_chunks": []}
        
#         # Retrieve documents without any filtering
#         retrieved_chunks = self.vector_db.query(
#             state["query"],
#             n_results=10  # Get more results for better context
#         )
        
#         # Return top results without additional filtering
#         return {"retrieved_chunks": retrieved_chunks[:15]}
    
#     def _generate_response(self, state: RAGState) -> dict:
#         """Generate response"""
#         retrieved_info = self.query_processor.format_retrieved_info(state["retrieved_chunks"])
#         response = self.query_processor.generate_response(state["query"], retrieved_info)
#         return {"response": response}
    
#     def load_pdfs(self) -> dict:
#         """Load all PDFs into the system (one-time ingestion)"""
#         initial_state = {
#             "pdf_directory": self.pdf_directory,
#             "pdf_files": [],
#             "processed_pdfs": [],
#             "current_pdf": None,
#             "query": "",
#             "query_analysis": {},
#             "retrieved_chunks": [],
#             "response": "",
#             "db_initialized": False,
#             "ingestion_mode": True
#         }
        
#         result = self.workflow.invoke(initial_state)
#         self._ingestion_completed = True
#         print(f"Processing complete. Processed {len(result['processed_pdfs'])} PDF files")
#         print(f"Total documents in database: {self.vector_db.get_document_count()}")
#         return result
    
#     def query(self, user_query: str) -> str:
#         """Execute a query against the loaded documents (querying only)"""
#         # Check if database has documents
#         if not self.vector_db.is_initialized():
#             # Try to connect to existing database
#             if not self.vector_db.initialize(reset=False):
#                 return "Database not initialized. Please run ingestion first."
        
#         if self.vector_db.get_document_count() == 0:
#             return "No documents found in database. Please run ingestion first."
        
#         query_state = {
#             "pdf_directory": self.pdf_directory,
#             "pdf_files": [],
#             "processed_pdfs": [],
#             "current_pdf": None,
#             "query": user_query,
#             "query_analysis": {},
#             "retrieved_chunks": [],
#             "response": "",
#             "db_initialized": True,
#             "ingestion_mode": False
#         }
        
#         result = self.workflow.invoke(query_state)
#         return result["response"]
import os
from typing import List, Dict, Any, TypedDict, Optional
from langgraph.graph import StateGraph, END

from pdf_processor import PDFProcessor
from vector_db import EfficientVectorDB
from query_processor import QueryProcessor


class RAGState(TypedDict):
    pdf_directory: str
    pdf_files: List[str]
    processed_pdfs: List[Dict[str, Any]]
    current_pdf: Optional[Dict[str, Any]]
    query: str
    query_analysis: Dict[str, Any]
    retrieved_chunks: List[Dict[str, Any]]
    response: str
    db_initialized: bool
    ingestion_mode: bool
    conversation_context: List[Dict[str, Any]]


class RAGOrchestrator:
    """
    Main orchestrator for RAG system
    optimized for Groq token limits
    """

    def __init__(
        self,
        pdf_directory: str,
        grok_api_key: str
    ):

        self.pdf_directory = pdf_directory

        self.grok_api_key = grok_api_key

        self.pdf_processor = PDFProcessor(
            grok_api_key
        )

        self.vector_db = EfficientVectorDB()

        self.query_processor = QueryProcessor(
            grok_api_key
        )

        self.workflow = self._create_workflow()

        self._ingestion_completed = False

    # =====================================
    # CREATE WORKFLOW
    # =====================================

    def _create_workflow(self) -> StateGraph:

        workflow = StateGraph(RAGState)

        workflow.add_node(
            "initialize",
            self._initialize_system
        )

        workflow.add_node(
            "process_pdf",
            self._process_next_pdf
        )

        workflow.add_node(
            "add_to_db",
            self._add_to_database
        )

        workflow.add_node(
            "analyze_query",
            self._analyze_query
        )

        workflow.add_node(
            "retrieve_info",
            self._retrieve_information
        )

        workflow.add_node(
            "generate_response",
            self._generate_response
        )

        workflow.set_entry_point("initialize")

        workflow.add_conditional_edges(
            "initialize",
            lambda state:
            "process_pdf"
            if state.get("ingestion_mode", False)
            else "analyze_query"
        )

        workflow.add_edge(
            "process_pdf",
            "add_to_db"
        )

        workflow.add_conditional_edges(
            "add_to_db",
            lambda state:
            "process_pdf"
            if state["pdf_files"]
            else END
        )

        workflow.add_edge(
            "analyze_query",
            "retrieve_info"
        )

        workflow.add_edge(
            "retrieve_info",
            "generate_response"
        )

        workflow.add_edge(
            "generate_response",
            END
        )

        return workflow.compile()

    # =====================================
    # INITIALIZE SYSTEM
    # =====================================

    def _initialize_system(
        self,
        state: RAGState
    ) -> dict:

        if not os.path.exists(
            state["pdf_directory"]
        ):

            raise ValueError(
                f"Directory {state['pdf_directory']} does not exist"
            )

        pdf_files = [
            f for f in os.listdir(
                state["pdf_directory"]
            )
            if f.lower().endswith('.pdf')
        ]

        reset_db = state["ingestion_mode"]

        db_initialized = self.vector_db.initialize(
            reset=reset_db
        )

        return {
            "pdf_files": (
                pdf_files
                if state["ingestion_mode"]
                else []
            ),
            "processed_pdfs": [],
            "db_initialized": db_initialized,
            "conversation_context": state.get(
                "conversation_context",
                []
            )
        }

    # =====================================
    # PROCESS PDF
    # =====================================

    def _process_next_pdf(
        self,
        state: RAGState
    ) -> dict:

        if not state["pdf_files"]:
            return {
                "pdf_files": [],
                "current_pdf": None
            }

        pdf_file = state["pdf_files"][0]

        pdf_path = os.path.join(
            state["pdf_directory"],
            pdf_file
        )

        pdf_index = len(
            state["processed_pdfs"]
        )

        print(
            f"Processing {pdf_file}..."
        )

        try:

            documents = (
                self.pdf_processor.process_pdf_for_db(
                    pdf_path,
                    pdf_index,
                    skip_image_processing=False
                )
            )

            if not documents:

                print(
                    f"Warning: Could not process {pdf_file}"
                )

                return {
                    "pdf_files": state["pdf_files"][1:],
                    "current_pdf": None
                }

            current_pdf = {
                "name": pdf_file,
                "index": pdf_index,
                "documents": documents
            }

            return {
                "current_pdf": current_pdf,
                "pdf_files": state["pdf_files"][1:]
            }

        except Exception as e:

            print(
                f"Error processing {pdf_file}: {e}"
            )

            return {
                "pdf_files": state["pdf_files"][1:],
                "current_pdf": None
            }

    # =====================================
    # ADD TO DATABASE
    # =====================================

    def _add_to_database(
        self,
        state: RAGState
    ) -> dict:

        if (
            not state["current_pdf"]
            or not state["db_initialized"]
        ):

            return {
                "processed_pdfs": state[
                    "processed_pdfs"
                ]
            }

        current_pdf = state["current_pdf"]

        success = (
            self.vector_db.add_documents_batch(
                current_pdf["documents"]
            )
        )

        if success:

            processed_pdfs = (
                state["processed_pdfs"]
                + [current_pdf]
            )

            print(
                f"Successfully processed {current_pdf['name']}"
            )

            return {
                "processed_pdfs": processed_pdfs
            }

        else:

            print(
                f"Failed to add {current_pdf['name']}"
            )

            return {
                "processed_pdfs": state[
                    "processed_pdfs"
                ]
            }

    # =====================================
    # ANALYZE QUERY
    # =====================================

    def _analyze_query(
        self,
        state: RAGState
    ) -> dict:

        enhanced_analysis = (
            self.query_processor.analyze_query(
                state["query"],
                state.get(
                    "conversation_context",
                    []
                )
            )
        )

        return {
            "query_analysis": enhanced_analysis
        }

    # =====================================
    # RETRIEVE INFORMATION
    # =====================================

    def _retrieve_information(
        self,
        state: RAGState
    ) -> dict:

        if not state["db_initialized"]:
            return {
                "retrieved_chunks": []
            }

        try:

            retrieved_chunks = self.vector_db.query(

                state["query"],

                # IMPORTANT
                # Reduced to avoid Groq TPM limit
                n_results=3,

                conversation_context=(
                    state.get(
                        "conversation_context",
                        []
                    )
                )
            )

            # =========================
            # TRIM LARGE CHUNKS
            # =========================

            trimmed_chunks = []

            for chunk in retrieved_chunks:

                chunk_text = chunk.get(
                    "chunk_text",
                    ""
                )

                # Reduce chunk size
                chunk["chunk_text"] = (
                    chunk_text[:700]
                )

                trimmed_chunks.append(chunk)

            return {
                "retrieved_chunks": trimmed_chunks
            }

        except Exception as e:

            print(
                f"Retrieval error: {e}"
            )

            return {
                "retrieved_chunks": []
            }

    # =====================================
    # GENERATE RESPONSE
    # =====================================

    def _generate_response(
        self,
        state: RAGState
    ) -> dict:

        retrieved_info = (
            self.query_processor.format_retrieved_info(
                state["retrieved_chunks"]
            )
        )

        response = (
            self.query_processor.generate_response(
                state["query"],
                retrieved_info,
                state.get(
                    "conversation_context",
                    []
                )
            )
        )

        return {
            "response": response
        }

    # =====================================
    # LOAD PDFS
    # =====================================

    def load_pdfs(self) -> dict:

        initial_state = {
            "pdf_directory": self.pdf_directory,
            "pdf_files": [],
            "processed_pdfs": [],
            "current_pdf": None,
            "query": "",
            "query_analysis": {},
            "retrieved_chunks": [],
            "response": "",
            "db_initialized": False,
            "ingestion_mode": True,
            "conversation_context": []
        }

        result = self.workflow.invoke(
            initial_state,
            config={
                "recursion_limit": 400
            }
        )

        self._ingestion_completed = True

        print(
            f"Processed {len(result['processed_pdfs'])} PDFs"
        )

        print(
            f"Total docs: {self.vector_db.get_document_count()}"
        )

        return result

    # =====================================
    # QUERY DOCUMENTS
    # =====================================

    def query(
        self,
        user_query: str,
        conversation_context: List[
            Dict[str, Any]
        ] = None
    ) -> str:

        if not self.vector_db.is_initialized():

            if not self.vector_db.initialize(
                reset=False
            ):

                return (
                    "Database not initialized."
                )

        if self.vector_db.get_document_count() == 0:

            return (
                "No documents found in database."
            )

        query_state = {
            "pdf_directory": self.pdf_directory,
            "pdf_files": [],
            "processed_pdfs": [],
            "current_pdf": None,
            "query": user_query,
            "query_analysis": {},
            "retrieved_chunks": [],
            "response": "",
            "db_initialized": True,
            "ingestion_mode": False,
            "conversation_context": (
                conversation_context or []
            )
        }

        result = self.workflow.invoke(
            query_state
        )

        return result["response"]

    # =====================================
    # QUERY SPECIFIC PDF
    # =====================================

    def query_pdf(
        self,
        user_query: str,
        pdf_name: str,
        conversation_context: List[
            Dict[str, Any]
        ] = None
    ) -> str:

        if not self.vector_db.is_initialized():

            if not self.vector_db.initialize(
                reset=False
            ):

                return (
                    "Database not initialized."
                )

        if self.vector_db.get_document_count() == 0:

            return (
                "No documents found in database."
            )

        query_analysis = (
            self.query_processor.analyze_query(
                user_query,
                conversation_context or []
            )
        )

        retrieved_chunks = (
            self.vector_db.query_with_pdf_filter(
                user_query,
                pdf_name,

                # Reduced for Groq limits
                n_results=2
            )
        )

        # Trim chunk sizes
        for chunk in retrieved_chunks:

            chunk["chunk_text"] = (
                chunk.get(
                    "chunk_text",
                    ""
                )[:700]
            )

        retrieved_info = (
            self.query_processor.format_retrieved_info(
                retrieved_chunks
            )
        )

        response = (
            self.query_processor.generate_response(
                user_query,
                retrieved_info,
                conversation_context or []
            )
        )

        return response
