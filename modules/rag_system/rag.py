import os
import numpy as np
import json
from flask import Blueprint, request, jsonify
from werkzeug.utils import secure_filename
from dotenv import load_dotenv
import google.generativeai as genai
import PyPDF2
from pptx import Presentation

load_dotenv()
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

embedding_model_name = "models/embedding-001"
answer_model = genai.GenerativeModel("gemini-pro")

rag_bp = Blueprint('rag', __name__)

UPLOAD_FOLDER = "uploads"
EMBEDDINGS_FOLDER = "embeddings"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(EMBEDDINGS_FOLDER, exist_ok=True)

ALLOWED_DOC_EXTENSIONS = {'pdf', 'pptx', 'ppt'}

def allowed_doc(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_DOC_EXTENSIONS

def extract_text_from_pdf(filepath):
    text = ""
    with open(filepath, 'rb') as f:
        reader = PyPDF2.PdfReader(f)
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"
    return text

def extract_text_from_ppt(filepath):
    text = ""
    prs = Presentation(filepath)
    for slide in prs.slides:
        for shape in slide.shapes:
            if hasattr(shape, "text"):
                text += shape.text + "\n"
    return text

def chunk_text(text, chunk_size=500, overlap=50):
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end]
        if chunk.strip():
            chunks.append(chunk)
        start = end - overlap
    return chunks

def get_embedding(text):
    result = genai.embed_content(
        model=embedding_model_name,
        content=text,
        task_type="retrieval_document"
    )
    return result['embedding']

def cosine_similarity(vec1, vec2):
    vec1 = np.array(vec1)
    vec2 = np.array(vec2)
    dot = np.dot(vec1, vec2)
    norm = np.linalg.norm(vec1) * np.linalg.norm(vec2)
    if norm == 0:
        return 0.0
    return dot / norm

def find_top_chunks(question_embedding, all_embeddings, all_chunks, top_k=3):
    scores = []
    for i, chunk_emb in enumerate(all_embeddings):
        score = cosine_similarity(question_embedding, chunk_emb)
        scores.append((score, i))
    scores.sort(reverse=True, key=lambda x: x[0])
    top_indices = [idx for _, idx in scores[:top_k]]
    return [all_chunks[i] for i in top_indices]

def answer_with_ai(question, relevant_chunks):
    context = "\n\n---\n\n".join(relevant_chunks)
    prompt = f"""You are a helpful AI assistant. Use ONLY the information in the context below to answer the question.
If the answer is not in the context, say "I could not find this information in the document."

CONTEXT:
{context}

QUESTION:
{question}

ANSWER:"""
    response = answer_model.generate_content(prompt)
    return response.text

@rag_bp.route('/upload', methods=['POST'])
def upload_document():
    if 'file' not in request.files:
        return jsonify({"error": "No file in request"}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No file selected"}), 400
    if not allowed_doc(file.filename):
        return jsonify({"error": "Only PDF, PPTX, PPT files are allowed"}), 400
    filename = secure_filename(file.filename)
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    file.save(filepath)

    extension = filename.rsplit('.', 1)[1].lower()
    try:
        if extension == 'pdf':
            text = extract_text_from_pdf(filepath)
        else:
            text = extract_text_from_ppt(filepath)
        if not text.strip():
            return jsonify({"error": "No text could be extracted."}), 400
        chunks = chunk_text(text)
        if not chunks:
            return jsonify({"error": "Text too short."}), 400
        embeddings = [get_embedding(chunk) for chunk in chunks]
        doc_name = filename.rsplit('.', 1)[0]
        np.save(os.path.join(EMBEDDINGS_FOLDER, f"{doc_name}_embeddings.npy"), np.array(embeddings))
        with open(os.path.join(EMBEDDINGS_FOLDER, f"{doc_name}_chunks.json"), 'w') as f:
            json.dump(chunks, f)
        return jsonify({
            "success": True,
            "document": doc_name,
            "chunks_created": len(chunks),
            "message": f"Document processed. {len(chunks)} chunks ready."
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@rag_bp.route('/query', methods=['POST'])
def query_document():
    data = request.get_json()
    if not data or 'question' not in data or 'document' not in data:
        return jsonify({"error": "Provide 'question' and 'document' in JSON"}), 400
    question = data['question'].strip()
    doc_name = data['document'].strip()

    emb_path = os.path.join(EMBEDDINGS_FOLDER, f"{doc_name}_embeddings.npy")
    chunks_path = os.path.join(EMBEDDINGS_FOLDER, f"{doc_name}_chunks.json")
    if not os.path.exists(emb_path) or not os.path.exists(chunks_path):
        return jsonify({"error": f"Document '{doc_name}' not found. Upload first."}), 404

    try:
        all_embeddings = np.load(emb_path)
        with open(chunks_path, 'r') as f:
            all_chunks = json.load(f)
        question_emb = get_embedding(question)
        top_chunks = find_top_chunks(question_emb, all_embeddings, all_chunks)
        answer = answer_with_ai(question, top_chunks)
        return jsonify({
            "question": question,
            "answer": answer,
            "source_chunks": top_chunks
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500