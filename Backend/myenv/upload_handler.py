# upload_handler.py
import os
import uuid
from typing import Dict, Any
from flask import request, jsonify
from werkzeug.utils import secure_filename
from pdf_processor import PDFProcessor
from vector_db import EfficientVectorDB
import threading

class UploadHandler:
    """Handles PDF uploads and background processing"""
    
    def __init__(self, upload_folder: str, grok_api_key: str):
        self.upload_folder = upload_folder
        self.grok_api_key = grok_api_key
        self.vector_db = EfficientVectorDB()
        self.processing_queue = {}
        os.makedirs(upload_folder, exist_ok=True)
    
    def allowed_file(self, filename: str) -> bool:
        """Check if the uploaded file is a PDF"""
        return '.' in filename and filename.rsplit('.', 1)[1].lower() == 'pdf'
    
    def handle_upload(self, request) -> Dict[str, Any]:
        """Handle file upload and start background processing"""
        if 'file' not in request.files:
            return {"success": False, "error": "No file provided"}
        
        file = request.files['file']
        if file.filename == '':
            return {"success": False, "error": "No file selected"}
        
        if file and self.allowed_file(file.filename):
            # Generate unique ID for this upload
            upload_id = str(uuid.uuid4())
            filename = secure_filename(file.filename)
            file_path = os.path.join(self.upload_folder, f"{upload_id}_{filename}")
            
            # Save the file
            file.save(file_path)
            
            # Add to processing queue
            self.processing_queue[upload_id] = {
                "filename": filename,
                "file_path": file_path,
                "status": "queued",
                "progress": 0,
                "documents_processed": 0
            }
            
            # Start background processing
            thread = threading.Thread(
                target=self.process_pdf_background,
                args=(upload_id, file_path, filename)
            )
            thread.daemon = True
            thread.start()
            
            return {
                "success": True,
                "upload_id": upload_id,
                "filename": filename,
                "message": "File uploaded and processing started"
            }
        
        return {"success": False, "error": "Invalid file type"}
    
    def process_pdf_background(self, upload_id: str, file_path: str, filename: str):
        """Process PDF in background thread"""
        try:
            # Update status
            self.processing_queue[upload_id]["status"] = "processing"
            
            # Initialize database if needed
            if not self.vector_db.is_initialized():
                self.vector_db.initialize(reset=False)
            
            # Process PDF
            processor = PDFProcessor(self.grok_api_key)
            
            # Get next PDF index
            existing_pdfs = self.vector_db.list_all_documents()
            pdf_index = len(existing_pdfs)
            
            # Process the PDF
            documents = processor.process_pdf_for_db(file_path, pdf_index)
            
            # Update progress
            self.processing_queue[upload_id]["documents_processed"] = len(documents)
            self.processing_queue[upload_id]["progress"] = 50
            
            # Add to database
            success = self.vector_db.add_documents_batch(documents)
            
            # Update status
            if success:
                self.processing_queue[upload_id]["status"] = "completed"
                self.processing_queue[upload_id]["progress"] = 100
            else:
                self.processing_queue[upload_id]["status"] = "failed"
                
        except Exception as e:
            self.processing_queue[upload_id]["status"] = "failed"
            self.processing_queue[upload_id]["error"] = str(e)
    
    def get_status(self, upload_id: str) -> Dict[str, Any]:
        """Get processing status for an upload"""
        if upload_id in self.processing_queue:
            return self.processing_queue[upload_id]
        return {"status": "not_found"}
    
    def list_uploads(self) -> Dict[str, Any]:
        """List all uploads and their status"""
        return self.processing_queue