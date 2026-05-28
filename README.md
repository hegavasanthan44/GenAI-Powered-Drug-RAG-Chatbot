Medical RAG ChatBot 💊

A sophisticated Retrieval-Augmented Generation (RAG) system designed specifically for pharmaceutical and medical document analysis. This chatbot provides accurate, source-cited responses to drug-related queries by processing FDA drug labels and medical documents.

 🌟 Features

- Advanced PDF Processing: Multi-strategy extraction of text, tables, and images from medical PDFs
- Conversational Memory: Maintains context across conversations with drug-specific follow-ups
- Multimodal Support: Handles text, tables, and images with proper captioning
- Voice Interface: Speech-to-text and text-to-speech capabilities
- Source Citation: Provides precise citations for all medical information
- Real-time Processing: Fast query response with optimized vector database
- Web Interface: Modern React-based chat interface

🚀 Quick Start

 Prerequisites
- Python 3.8+
- Node.js 16+
- Google Gemini API key
- FFmpeg (for audio processing)

1. Backend Setup
# Create virtual environment
  python -m venv venv
  source venv\Scripts\activate
  
# Install dependencies
  pip install -r requirements.txt

# Set up environment variables
  cp .env.example .env  # Edit .env with your Gemini API key

2.Frontend Setup
cd frontend
npm install

3.Add PDF Documents
# Place your medical PDFs in the ./pdf directory
mkdir -p pdf
# Copy your drug label PDFs to this folder

🚀 Running the Application
1.Start the Backend Server
  python main.py
  Server will start on http://localhost:5001
2.Ingest PDF Documents (First time only)
  python ingest.py
3.Start the Frontend
  npm start
  Frontend will start on http://localhost:3000

   
