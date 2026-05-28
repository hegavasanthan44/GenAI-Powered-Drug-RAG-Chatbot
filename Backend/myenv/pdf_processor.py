import os
import re
import uuid
import json
import threading
import concurrent.futures
from typing import List, Dict, Any, Optional
from unstructured.partition.pdf import partition_pdf
from unstructured.documents.elements import CompositeElement, Table, Image
import requests
from PIL import Image as PILImage
import io
import base64
import pdfplumber
import camelot
import pandas as pd
import warnings
import fitz  # PyMuPDF for better image extraction
import tempfile
import torch
from transformers import BlipProcessor, BlipForConditionalGeneration
from functools import lru_cache
import time
from queue import Queue

class PDFProcessor:
    """Enhanced PDF processor with sequential page numbering and performance optimizations"""
    
    def __init__(self, grok_api_key: str = None, max_workers: int = None):
        if grok_api_key:
            self.grok_api_key = grok_api_key
            self.grok_endpoint = "https://api.x.ai/v1/messages"
        else:
            self.grok_api_key = None
            self.grok_endpoint = None
        
        # Initialize BLIP model for image captioning
        self.blip_processor = BlipProcessor.from_pretrained("Salesforce/blip-image-captioning-base")
        self.blip_model = BlipForConditionalGeneration.from_pretrained("Salesforce/blip-image-captioning-base")
        
        # Set device (GPU if available, else CPU)
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.blip_model.to(self.device)
        
        # Thread pool for parallel processing
        self.max_workers = max_workers or (os.cpu_count() or 4)
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers)
        
        # FDA sections
        self.fda_sections = [
            "BOXED WARNING", "INDICATIONS AND USAGE", "DOSAGE AND ADMINISTRATION",
            "CONTRAINDICATIONS", "WARNINGS AND PRECAUTIONS", "ADVERSE REACTIONS",
            "DRUG INTERACTIONS", "USE IN SPECIFIC POPULATIONS", "PATIENT COUNSELING INFORMATION",
            "CLINICAL PHARMACOLOGY", "HOW SUPPLIED/STORAGE AND HANDLING", "MEDICATION GUIDE",
            "DESCRIPTION", "CLINICAL STUDIES", "MECHANISM OF ACTION", "PHARMACOKINETICS",
            "NONCLINICAL TOXICOLOGY", "CLINICAL TRIALS"
        ]
        self.fda_section_pattern = re.compile(
            r'^\s*(' + '|'.join(re.escape(section) for section in self.fda_sections) + r')\s*$',
            re.IGNORECASE | re.MULTILINE
        )
        
        # Create directory for extracted images if it doesn't exist
        self.image_output_dir = "./extracted_images"
        os.makedirs(self.image_output_dir, exist_ok=True)
        
        # Cache for expensive operations
        self._table_signature_cache = set()

    def _get_page_number(self, physical_page_idx: int) -> str:
        """
        Get sequential page number (1-based)
        """
        return str(physical_page_idx + 1)

    def _process_element(self, element, extracted_tables):
        """Process a single element (thread-safe)"""
        # Get physical page index from metadata
        physical_page_idx = 0
        if hasattr(element.metadata, 'page_number'):
            physical_page_idx = element.metadata.page_number - 1  # Convert to 0-based
        
        # Get sequential page number
        page_num = self._get_page_number(physical_page_idx)
        
        element_data = {
            "type": type(element).__name__,
            "text": str(element),
            "metadata": element.metadata.to_dict(),
            "physical_page_index": physical_page_idx,
            "page_number": page_num  # Use sequential page number
        }
        
        # Handle tables
        if isinstance(element, Table):
            print(f"\n=== UNSTRUCTURED.IO TABLE DETECTED ===")
            print(f"Page: {element_data['page_number']} (Physical: {physical_page_idx + 1})")
            
            element_data["table_data"] = self._structure_table_data(element)
            element_data["text_representation"] = self._create_table_text_representation(
                element_data["table_data"], element_data["page_number"]
            )
            
            print(f"Structured table data headers: {element_data['table_data']['headers']}")
            print(f"Structured table has {element_data['table_data']['row_count']} rows")
            print("=== END UNSTRUCTURED.IO TABLE ===\n")
            
            table_signature = self._get_table_signature(element_data)
            if table_signature not in extracted_tables:
                extracted_tables.add(table_signature)
                return element_data
            return None
            
        # Handle images
        elif isinstance(element, Image) and hasattr(element.metadata, 'image_path'):
            element_data["image_path"] = element.metadata.image_path
            # Defer image captioning to later to avoid blocking
            return element_data
        
        return element_data

    def extract_elements(self, pdf_path: str) -> List[Dict[str, Any]]:
        """Extract elements with sequential page numbering using parallel processing"""
        print(f"Extracting elements from {pdf_path}...")
        start_time = time.time()
        
        processed_elements = []
        extracted_tables = set()
        
        try:
            # Strategy 1: Use Unstructured.io for text and basic structure
            elements = partition_pdf(
                filename=pdf_path,
                extract_images_in_pdf=True,
                infer_table_structure=True,
                chunking_strategy="by_title",
                max_characters=4000,
                new_after_n_chars=3800,
                combine_text_under_n_chars=2000,
                image_output_dir_path=self.image_output_dir,
                strategy="hi_res",
                languages=["eng"],
            )
            
            # Process elements in parallel
            futures = []
            for element in elements:
                futures.append(
                    self.executor.submit(
                        self._process_element, 
                        element, 
                        extracted_tables
                    )
                )
            
            for future in concurrent.futures.as_completed(futures):
                result = future.result()
                if result:
                    processed_elements.append(result)
            
        except Exception as e:
            print(f"Unstructured.io extraction failed: {e}")
        
        # Strategy 2: Use pdfplumber for additional text extraction with sequential page numbers
        try:
            with pdfplumber.open(pdf_path) as pdf:
                futures = []
                for physical_page_idx, page in enumerate(pdf.pages):
                    futures.append(
                        self.executor.submit(
                            self._extract_page_text,
                            page,
                            physical_page_idx
                        )
                    )
                
                for future in concurrent.futures.as_completed(futures):
                    result = future.result()
                    if result:
                        processed_elements.append(result)
        except Exception as e:
            print(f"PDFPlumber extraction failed: {e}")
        
        # Strategy 3: Use Camelot for table extraction with sequential page numbers
        try:
            print("\n=== CAMELOT TABLE EXTRACTION ATTEMPT ===")
            # Use threading for Camelot table extraction
            camelot_future = self.executor.submit(camelot.read_pdf, pdf_path, pages='all', flavor='stream')
            tables = camelot_future.result()
            print(f"Camelot found {len(tables)} potential tables")
            
            camelot_futures = []
            for i, table in enumerate(tables):
                camelot_futures.append(
                    self.executor.submit(
                        self._process_camelot_table,
                        table,
                        i,
                        extracted_tables
                    )
                )
            
            for future in concurrent.futures.as_completed(camelot_futures):
                result = future.result()
                if result:
                    processed_elements.append(result)
                    
        except Exception as e:
            print(f"Camelot table extraction failed: {e}")
        
        # Strategy 4: Enhanced image extraction using PyMuPDF with sequential page numbers
        try:
            image_future = self.executor.submit(
                self._extract_images_with_pymupdf, 
                pdf_path
            )
            image_elements = image_future.result()
            processed_elements.extend(image_elements)
            print(f"Extracted {len(image_elements)} images using PyMuPDF")
        except Exception as e:
            print(f"PyMuPDF image extraction failed: {e}")
        
        # Process image captions in parallel (deferred from earlier)
        image_elements = [e for e in processed_elements if e["type"] == "Image" and "image_path" in e and "image_description" not in e]
        if image_elements:
            print(f"Processing {len(image_elements)} image captions in parallel...")
            caption_futures = []
            for img_element in image_elements:
                caption_futures.append(
                    self.executor.submit(
                        self._caption_image_and_update_element,
                        img_element
                    )
                )
            
            # Wait for all captioning to complete
            concurrent.futures.wait(caption_futures)
        
        end_time = time.time()
        print(f"Element extraction completed in {end_time - start_time:.2f} seconds")
        
        return processed_elements

    def _extract_page_text(self, page, physical_page_idx):
        """Extract text from a single page (thread-safe)"""
        text = page.extract_text()
        if text:
            page_num = self._get_page_number(physical_page_idx)
            return {
                "type": "TextElement",
                "text": text,
                "metadata": {"page_number": page_num},
                "physical_page_index": physical_page_idx,
                "page_number": page_num
            }
        return None

    def _process_camelot_table(self, table, table_index, extracted_tables):
        """Process a single Camelot table (thread-safe)"""
        if table.parsing_report and table.parsing_report.get('accuracy', 0) > 50:
            # Camelot uses 1-based physical page numbers
            physical_page_idx = table.page - 1
            page_num = self._get_page_number(physical_page_idx)
            
            table_data = {
                "headers": table.df.iloc[0].tolist() if not table.df.empty else [],
                "data": table.df.iloc[1:].values.tolist() if len(table.df) > 1 else [],
                "row_count": len(table.df) - 1 if len(table.df) > 1 else 0,
                "col_count": len(table.df.columns) if not table.df.empty else 0
            }
            
            # Create table element
            table_element = {
                "type": "Table",
                "text": table.df.to_string(),
                "metadata": {"page_number": page_num},
                "physical_page_index": physical_page_idx,
                "page_number": page_num,
                "table_data": table_data,
                "text_representation": self._create_table_text_representation(table_data, page_num),
                "extraction_method": "camelot"
            }
            
            # Check for duplicates before adding
            table_signature = self._get_table_signature(table_element)
            if table_signature not in extracted_tables:
                extracted_tables.add(table_signature)
                print(f"=== CAMELOT TABLE ADDED (Page {page_num}) ===\n")
                return table_element
            else:
                print("=== CAMELOT TABLE SKIPPED (DUPLICATE) ===\n")
        else:
            accuracy = table.parsing_report.get('accuracy', 0) if table.parsing_report else 0
            print(f"Table {table_index+1} skipped due to low accuracy ({accuracy}%)\n")
        
        return None

    def _caption_image_and_update_element(self, img_element):
        """Caption an image and update the element (thread-safe)"""
        img_element["image_description"] = self._caption_image_with_blip(img_element["image_path"])

    def _get_table_signature(self, table_element: Dict[str, Any]) -> str:
        """Create a unique signature for a table to detect duplicates"""
        page_num = table_element.get("page_number", 0)
        content_hash = hash(table_element.get("text", "")[:200])  
        signature = f"{page_num}_{content_hash}"
        
        # Check cache first
        if signature in self._table_signature_cache:
            return signature
            
        # Add to cache
        self._table_signature_cache.add(signature)
        return signature

    def _extract_images_with_pymupdf(self, pdf_path: str) -> List[Dict[str, Any]]:
        """Extract images using PyMuPDF with sequential page numbering"""
        image_elements = []
        doc = fitz.open(pdf_path)
        
        for physical_page_idx in range(len(doc)):
            page = doc.load_page(physical_page_idx)
            image_list = page.get_images()
            
            page_num = self._get_page_number(physical_page_idx)
            
            for img_index, img in enumerate(image_list):
                xref = img[0]
                base_image = doc.extract_image(xref)
                if base_image:
                    image_bytes = base_image["image"]
                    image_ext = base_image["ext"]
                    
                    # Save image to file
                    image_filename = f"image_page{page_num}_{img_index}.{image_ext}"
                    image_path = os.path.join(self.image_output_dir, image_filename)
                    
                    with open(image_path, "wb") as f:
                        f.write(image_bytes)
                    
                    image_elements.append({
                        "type": "Image",
                        "text": f"Image on page {page_num}",
                        "metadata": {"page_number": page_num},
                        "physical_page_index": physical_page_idx,
                        "page_number": page_num,
                        "image_path": image_path,
                        # Image captioning will be done in parallel later
                    })
        
        doc.close()
        return image_elements

    def _caption_image_with_blip(self, image_path: str) -> str:
        """Generate caption for image using BLIP model"""
        try:
            if not os.path.exists(image_path):
                return "Image caption not available - file not found"
            
            # Check if image is too small (likely decorative)
            img = PILImage.open(image_path)
            width, height = img.size
            if width < 50 or height < 50:
                return "Small decorative image - no significant content"
            
            # Convert to RGB if needed
            if img.mode != "RGB":
                img = img.convert("RGB")
            
            # Process image with BLIP
            inputs = self.blip_processor(images=img, return_tensors="pt").to(self.device)
            outputs = self.blip_model.generate(**inputs, max_length=50, num_beams=5)
            
            # Decode the caption
            caption = self.blip_processor.decode(outputs[0], skip_special_tokens=True)
            
            return caption
            
        except Exception as e:
            print(f"Error captioning image {image_path}: {e}")
            return f"Medical image showing relevant information. [Image processing error: {str(e)}]"

    def _structure_table_data(self, table_element: Table) -> Dict[str, Any]:
        """Structure table data from Unstructured.io"""
        table_text = str(table_element)
        print(f"Raw table text for structuring:\n{table_text[:200]}...") 
        
        rows = [line.split('\t') for line in table_text.split('\n') if line.strip()]
        
        if not rows:
            print("No rows found in table")
            return {"headers": [], "data": [], "row_count": 0, "col_count": 0}
        
        print(f"Found {len(rows)} rows in table")
        
        # Try to identify headers
        headers = []
        data_rows = rows
        
        if len(rows) > 1 and self._is_likely_header_row(rows[0], rows[1]):
            headers = [cell.strip() for cell in rows[0]]
            data_rows = rows[1:]
            print(f"Header row identified: {headers}")
        else:
            max_cols = max(len(row) for row in rows)
            headers = [f"Column_{i+1}" for i in range(max_cols)]
            print(f"No header row found, using default headers: {headers}")
        
        result = {
            "headers": headers,
            "data": data_rows,
            "row_count": len(data_rows),
            "col_count": len(headers)
        }
    
        print(f"Final structured table: {result['row_count']} rows x {result['col_count']} columns")
        return result

    def _is_likely_header_row(self, row: List[str], next_row: List[str]) -> bool:
        """Determine if a row is likely a header"""
        print(f"Checking if row is header: {row}")
        print(f"Next row for comparison: {next_row}")
        
        if not any(cell.strip() for cell in row):
            print("Row empty - not a header")
            return False
        
        header_indicators = 0
        total_cells = len([cell for cell in row if cell.strip()])
        
        for cell in row:
            cell_text = cell.strip()
            if not cell_text:
                continue
                
            if cell_text.isupper():
                header_indicators += 1
                print(f"Header indicator: '{cell_text}' is uppercase")
            elif re.search(r'[%$#&]|\b(rate|ratio|percentage|score|value)\b', cell_text.lower()):
                header_indicators += 1
                print(f"Header indicator: '{cell_text}' contains special character or header keyword")
            elif len(cell_text) < 20 and not cell_text.isdigit():
                header_indicators += 1
                print(f"Header indicator: '{cell_text}' is short and not numeric")
        
        # Check if next row contains data (numbers)
        data_indicators = 0
        for cell in next_row:
            if re.search(r'\d', cell):
                data_indicators += 1
                print(f"Data indicator: '{cell}' contains numbers")
                break
        
        result = header_indicators > 0 and data_indicators > 0
        print(f"Header decision: {result} (header_indicators: {header_indicators}, data_indicators: {data_indicators})")
        return result

    def _create_table_text_representation(self, table_data: Dict[str, Any], page_num: str) -> str:
        """Create comprehensive textual representation of table"""
        print(f"\nCreating text representation for table on page {page_num}")
        
        text_rep = f"Table from page {page_num}. "
        
        if table_data["headers"]:
            text_rep += f"Headers: {', '.join([h for h in table_data['headers'] if h])}. "
            print(f"Table headers: {table_data['headers']}")
        
        # Add sample data rows for comprehensive search (limit to 3 rows for debugging)
        sample_rows = min(3, len(table_data["data"]))
        print(f"Adding {sample_rows} sample rows to text representation:")
        
        for i, row in enumerate(table_data["data"][:sample_rows]):
            if any(cell.strip() for cell in row):
                row_data = []
                for j, cell in enumerate(row):
                    if cell.strip() and j < len(table_data["headers"]):
                        header_name = table_data["headers"][j] if table_data["headers"][j] else f"Column_{j+1}"
                        row_data.append(f"{header_name}: {cell}")
                
                if row_data:
                    text_rep += f"Row {i+1}: {', '.join(row_data)}. "
                    print(f"Row {i+1}: {row_data}")
        
        # Add summary if there are more rows
        if len(table_data["data"]) > sample_rows:
            remaining = len(table_data["data"]) - sample_rows
            text_rep += f"Plus {remaining} more rows. "
            print(f"... plus {remaining} more rows")
        
        print(f"Final text representation length: {len(text_rep)} characters")
        print(f"Text representation preview: {text_rep[:200]}...")
        
        return text_rep.strip()

    def extract_sections(self, elements: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Extract sections from processed elements"""
        if not elements:
            return []
        
        # Combine text elements with page markers
        combined_text = ""
        current_page = "1"
        
        for element in elements:
            if element["type"] in ["CompositeElement", "TextElement"] and element["text"].strip():
                if element["page_number"] != current_page:
                    combined_text += f"\n--- Page {element['page_number']} ---\n"
                    current_page = element["page_number"]
                combined_text += element["text"] + "\n"
        
        # Check if document follows FDA format
        is_fda = self.is_fda_format(combined_text)
        
        # Extract sections
        sections = []
        current_section = "INTRODUCTION"
        content = ""
        page_start = "1"
        page_end = "1"

        lines = combined_text.split("\n")
        for line in lines:
            # Check for page markers
            if line.startswith("--- Page "):
                if content.strip():
                    sections.append({
                        "section": current_section,
                        "content": content.strip(),
                        "page_start": page_start,
                        "page_end": page_end,
                        "is_fda": is_fda
                    })
                    content = ""
                
                match = re.match(r'--- Page (\S+) ---', line)
                if match:
                    page_start = match.group(1)
                    page_end = page_start
                continue

            # Check for section headers
            section_match = None
            if is_fda:
                section_match = self.fda_section_pattern.match(line.upper())
            else:
                section_match = (re.match(r'^\s*([A-Z][A-Z\s\-]+(?:\.|:)?)\s*$', line)
                                 and len(line.strip()) < 100
                                 and not line.strip().isdigit())

            if section_match:
                if content.strip():
                    sections.append({
                        "section": current_section,
                        "content": content.strip(),
                        "page_start": page_start,
                        "page_end": page_end,
                        "is_fda": is_fda
                    })
                current_section = line.strip().upper()
                content = ""
                page_start = page_end
            else:
                content += line + "\n"
                page_end = current_page

        if content.strip():
            sections.append({
                "section": current_section,
                "content": content.strip(),
                "page_start": page_start,
                "page_end": page_end,
                "is_fda": is_fda
            })

        return sections

    def is_fda_format(self, text: str) -> bool:
        count = sum(1 for section in self.fda_sections if section.upper() in text.upper())
        return count >= 3

    def chunk_content(self, content: str, chunk_size: int = 800, overlap: int = 100) -> List[Dict[str, Any]]:
        chunks = []
        words = content.split()
        if len(words) <= chunk_size:
            return [{"content": content, "chunk_id": "chunk_0"}]
        for i in range(0, len(words), chunk_size - overlap):
            chunk_words = words[i:i + chunk_size]
            chunk_text = " ".join(chunk_words)
            if chunk_text.strip():
                chunks.append({
                    "content": chunk_text,
                    "chunk_id": f"chunk_{i // chunk_size}"
                })
        return chunks

    def prepare_documents_for_db(self, pdf_name: str, pdf_index: int, 
                                elements: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Prepare all extracted elements for database storage"""
        documents_batch = []
        
        # First, extract sections from text elements
        text_elements = [e for e in elements if e["type"] in ["CompositeElement", "TextElement"]]
        sections = self.extract_sections(text_elements)
        
        # Process text sections in parallel
        section_futures = []
        for section in sections:
            section_futures.append(
                self.executor.submit(
                    self._process_section_for_db,
                    section, pdf_name, pdf_index
                )
            )
        
        for future in concurrent.futures.as_completed(section_futures):
            section_docs = future.result()
            documents_batch.extend(section_docs)
        
        # Process tables - USING SEQUENTIAL PAGE NUMBERS
        table_elements = [e for e in elements if e["type"] == "Table"]
        table_futures = []
        for table_idx, table in enumerate(table_elements):
            table_futures.append(
                self.executor.submit(
                    self._process_table_for_db,
                    table, table_idx, pdf_name, pdf_index
                )
            )
        
        for future in concurrent.futures.as_completed(table_futures):
            table_doc = future.result()
            if table_doc:
                documents_batch.append(table_doc)
        
        # Process images - USING SEQUENTIAL PAGE NUMBERS
        image_elements = [e for e in elements if e["type"] == "Image" and "image_description" in e]
        image_futures = []
        for image_idx, image in enumerate(image_elements):
            image_futures.append(
                self.executor.submit(
                    self._process_image_for_db,
                    image, image_idx, pdf_name, pdf_index
                )
            )
        
        for future in concurrent.futures.as_completed(image_futures):
            image_doc = future.result()
            if image_doc:
                documents_batch.append(image_doc)
        
        return documents_batch

    def _process_section_for_db(self, section, pdf_name, pdf_index):
        """Process a section for database storage (thread-safe)"""
        section_docs = []
        if "chunks" not in section:
            section["chunks"] = self.chunk_content(section["content"])
        for chunk in section["chunks"]:
            doc_id = str(uuid.uuid4())
            metadata = {
                "pdf_index": pdf_index,
                "pdf_name": pdf_name,
                "section": section["section"],
                "page_start": section["page_start"],
                "page_end": section["page_end"],
                "is_fda": section.get("is_fda", False),
                "content_type": self._classify_content_type(chunk["content"]),
                "has_tables": False,
                "has_images": False,
                "doc_type": "text",
                "citation": f"Page {section['page_start']}-{section['page_end']}, {section['section']}",
                "pdf_identifier": f"pdf_{pdf_index}{pdf_name.replace(' ', '')}"
            }
            
            section_docs.append({
                "id": doc_id,
                "content": chunk["content"],
                "metadata": self._ensure_chromadb_compatible(metadata)
            })
        
        return section_docs

    def _process_table_for_db(self, table, table_idx, pdf_name, pdf_index):
        """Process a table for database storage (thread-safe)"""
        doc_id = str(uuid.uuid4())
        
        metadata = {
            "pdf_index": pdf_index,
            "pdf_name": pdf_name,
            "section": "TABULAR_DATA",
            "page_number": table["page_number"],  # Sequential page number
            "is_fda": False,
            "content_type": "tabular",
            "has_tables": True,
            "has_images": False,
            "doc_type": "table",
            "table_id": str(uuid.uuid4()),
            "table_index": table_idx + 1,
            "citation": f"Page {table['page_number']}, Table {table_idx + 1}",  # Sequential citation
            "table_headers": table.get("table_data", {}).get("headers", []),
            "table_row_count": table.get("table_data", {}).get("row_count", 0),
            "table_data_sample": json.dumps(table.get("table_data", {}).get("data", [])[:2]),
            "pdf_identifier": f"pdf_{pdf_index}{pdf_name.replace(' ', '')}"
        }
        
        return {
            "id": doc_id,
            "content": table.get("text_representation", table["text"]),
            "metadata": self._ensure_chromadb_compatible(metadata)
        }

    def _process_image_for_db(self, image, image_idx, pdf_name, pdf_index):
        """Process an image for database storage (thread-safe)"""
        doc_id = str(uuid.uuid4())
        
        metadata = {
            "pdf_index": pdf_index,
            "pdf_name": pdf_name,
            "section": "VISUAL_DATA",
            "page_number": image["page_number"],  # Sequential page number
            "is_fda": False,
            "content_type": "visual",
            "has_tables": False,
            "has_images": True,
            "doc_type": "image",
            "image_id": str(uuid.uuid4()),
            "image_index": image_idx + 1,
            "citation": f"Page {image['page_number']}, Figure {image_idx + 1}",  # Sequential citation
            "original_image_path": image.get("image_path", ""),
            "image_caption": image.get("image_description", ""),
            "pdf_identifier": f"pdf_{pdf_index}{pdf_name.replace(' ', '')}"
        }
        
        return {
            "id": doc_id,
            "content": image["image_description"],
            "metadata": self._ensure_chromadb_compatible(metadata)
        }

    def _classify_content_type(self, content: str) -> str:
        content_lower = content.lower()
        medical_keywords = {
            'dose', 'dosage', 'mg', 'kg', 'injection', 'infusion', 'treatment',
            'therapy', 'side effects', 'adverse', 'contraindications', 'warnings',
            'patient', 'clinical', 'studies', 'efficacy', 'safety', 'medical'
        }
        table_keywords = {'table', 'figure', 'chart', 'graph', 'data', 'results'}

        if "TABLES:" in content or any(keyword in content_lower for keyword in table_keywords):
            return "tabular"
        elif any(keyword in content_lower for keyword in medical_keywords):
            return "medical"
        elif len(content_lower.split()) < 50:
            return "metadata"
        else:
            return "general"
        
    def _ensure_chromadb_compatible(self, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Ensure all metadata values are compatible with ChromaDB"""
        compatible_metadata = {}
        for key, value in metadata.items():
            if isinstance(value, (list, tuple)):
                compatible_metadata[key] = json.dumps(value)
            elif isinstance(value, (str, int, float, bool)) or value is None:
                compatible_metadata[key] = value
            else:
                compatible_metadata[key] = str(value)
        return compatible_metadata

    def process_pdf_for_db(self, pdf_path: str, pdf_index: int = 0, skip_image_processing: bool = False) -> List[Dict[str, Any]]:
        """Complete PDF processing pipeline with option to skip image processing"""
        pdf_name = os.path.basename(pdf_path)
        print(f"\n[Processing] Starting processing for {pdf_name}...")
        start_time = time.time()
        
        # Extract all elements using multiple strategies
        elements = self.extract_elements(pdf_path)
        
        # Count different element types
        text_count = sum(1 for e in elements if e["type"] in ["CompositeElement", "TextElement"])
        table_count = sum(1 for e in elements if e["type"] == "Table")
        image_count = sum(1 for e in elements if e["type"] == "Image" and "image_description" in e)
        
        print(f"[Processing Summary] Extracted {text_count} text elements, {table_count} tables, {image_count} images")
        
        # If skipping image processing, filter out image elements
        if skip_image_processing:
            elements = [e for e in elements if e["type"] != "Image"]
            print(f"[Processing Summary] Skipped image processing, removed {image_count} image elements")
        
        # Prepare documents for database
        documents = self.prepare_documents_for_db(pdf_name, pdf_index, elements)
        print(f"[Processing Summary] Prepared {len(documents)} documents for database storage")
        
        # Count document types
        text_docs = sum(1 for doc in documents if doc['metadata']['doc_type'] == 'text')
        table_docs = sum(1 for doc in documents if doc['metadata']['doc_type'] == 'table')
        image_docs = sum(1 for doc in documents if doc['metadata']['doc_type'] == 'image')
        
        print(f"[Processing Summary] Document types - Text: {text_docs}, Tables: {table_docs}, Images: {image_docs}")
        
        end_time = time.time()
        print(f"[Processing Summary] Total processing time: {end_time - start_time:.2f} seconds")
        
        return documents

    def process_multiple_pdfs(self, pdf_paths: List[str]) -> List[Dict[str, Any]]:
        """
        Process multiple PDFs and return all documents organized by PDF
        
        Args:
            pdf_paths: List of paths to PDF files
            
        Returns:
            List of all documents from all PDFs, with metadata indicating which PDF they belong to
        """
        all_documents = []
        
        for pdf_index, pdf_path in enumerate(pdf_paths):
            if not os.path.exists(pdf_path):
                print(f"Warning: PDF file not found - {pdf_path}")
                continue
                
            try:
                documents = self.process_pdf_for_db(pdf_path, pdf_index)
                all_documents.extend(documents)
                print(f"Successfully processed {pdf_path} - {len(documents)} documents")
                
            except Exception as e:
                print(f"Error processing {pdf_path}: {str(e)}")
                continue
        
        return all_documents

    def cleanup(self):
        """Clean up resources"""
        self.executor.shutdown(wait=True)