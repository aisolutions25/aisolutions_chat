from flask import Flask, render_template, request, jsonify, send_file
from ai_question import ask_deepseek
import pdfkit
import os
from datetime import datetime
import uuid
import atexit  # Import atexit for shutdown handling
import webbrowser
from threading import Timer
from werkzeug.utils import secure_filename  # Import for secure file handling
from PyPDF2 import PdfReader
from docx import Document
import textract

app = Flask(__name__)
app.static_folder = 'static'

# Configuration
PDF_FOLDER = 'chat_saved'
BACKUP_FOLDER = 'chat_backups'  # New folder for chat backups
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'txt', 'pdf', 'docx', 'md'}

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

if not os.path.exists(PDF_FOLDER):
    os.makedirs(PDF_FOLDER)
if not os.path.exists(BACKUP_FOLDER):  # Ensure backup folder exists
    os.makedirs(BACKUP_FOLDER)
if not os.path.exists(UPLOAD_FOLDER):  # Ensure the upload folder exists
    os.makedirs(UPLOAD_FOLDER)

# Chat storage
chats = {}  # Format: {chat_id: {'messages': [], 'files': {filename: content}}}
current_chat_id = 0

def allowed_file(filename):
    """Check if the uploaded file has an allowed extension."""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def generate_formatted_pdf(html_content, chat_id, is_full_chat=False):
    """Generate formatted PDF with proper styling"""
    try:
        # Verify PDF folder exists
        if not os.path.exists(PDF_FOLDER):
            os.makedirs(PDF_FOLDER)

        # Generate unique filename
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"Chat_{chat_id}_{'full' if is_full_chat else 'partial'}_{timestamp}.pdf"
        filepath = os.path.join(PDF_FOLDER, filename)
        
        # Verify CSS path
        css_path = os.path.join(app.static_folder, 'style.css')
        if not os.path.exists(css_path):
            raise FileNotFoundError(f"CSS file not found at {css_path}")

        # PDF configuration
        options = {
            'encoding': 'UTF-8',
            'quiet': '',
            'page-size': 'A4',
            'margin-top': '20mm',
            'margin-right': '20mm',
            'margin-bottom': '20mm',
            'margin-left': '20mm',
            'enable-local-file-access': '',
            'user-style-sheet': css_path
        }
        
        # Wrap content in proper HTML structure
        full_html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <style>{open(css_path).read()}</style>
        </head>
        <body>
            <div class="pdf-content">
                {html_content}
            </div>
        </body>
        </html>
        """
        
        pdfkit.from_string(full_html, filepath, options=options)
        return filepath
    except Exception as e:
        print(f"PDF generation error: {e}")
        return None

def save_all_chats_to_backup():
    """Save all chats to the backup folder as individual files"""
    try:
        for chat_id, chat_data in chats.items():
            messages = chat_data['messages']
            if messages:
                chat_content = ""
                for msg in messages:
                    chat_content += f"Q: {msg['question']}\n"
                    chat_content += f"A: {msg['answer']}\n\n"
                
                # Save chat content to a text file
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                filename = f"chat_{chat_id}_{timestamp}.txt"
                filepath = os.path.join(BACKUP_FOLDER, filename)
                with open(filepath, 'w') as file:
                    file.write(chat_content)
        print("All chats have been saved to the backup folder.")
    except Exception as e:
        print(f"Error saving chats to backup: {e}")

# Register the save_all_chats_to_backup function to run on shutdown
atexit.register(save_all_chats_to_backup)

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/ask', methods=['POST'])
def ask_question():
    global current_chat_id
    chat_id = request.form.get('chat_id', current_chat_id)
    
    if chat_id not in chats:
        chats[chat_id] = {'messages': [], 'files': {}}
    
    try:
        # Process uploaded files
        file_context = []
        for file in request.files.getlist('files'):
            if file and allowed_file(file.filename):
                content = read_file(file)
                filename = secure_filename(file.filename)
                file_context.append(f"File '{filename}' content:\n{content}")
                # Store file in chat history
                chats[chat_id]['files'][filename] = content

        # Build question with context
        user_question = request.form.get('question', '')
        full_query = "\n\n".join(file_context + [f"Question: {user_question}"])
        
        answer = ask_deepseek(full_query)
        
        # Store in chat history
        chats[chat_id]['messages'].append({
            'question': user_question,
            'answer': answer,
            'files': list(chats[chat_id]['files'].keys())
        })
        
        return jsonify({
            'answer': answer,
            'chat_id': chat_id
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/new_chat', methods=['POST'])
def new_chat():
    global current_chat_id
    try:
        # Save current chat if it has content
        if current_chat_id in chats and chats[current_chat_id]['messages']:
            chat_content = ""
            for msg in chats[current_chat_id]['messages']:
                chat_content += f"<div class='message'><div class='message-content'><strong>Q:</strong> {msg['question']}</div></div>"
                chat_content += f"<div class='message'><div class='message-content'><strong>A:</strong> {msg['answer']}</div></div>"
            
            generate_formatted_pdf(chat_content, current_chat_id, is_full_chat=True)
        
        # Create new chat
        current_chat_id += 1
        return jsonify({'chat_id': current_chat_id})
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/get_chat', methods=['POST'])
def get_chat():
    """Retrieve the content of a specific chat."""
    try:
        data = request.json
        chat_id = data.get('chat_id')
        
        if chat_id in chats:
            return jsonify({'chat_id': chat_id, 'messages': chats[chat_id]['messages']})
        else:
            return jsonify({'error': 'Chat not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/save_pdf', methods=['POST'])
def save_pdf():
    try:
        data = request.json
        html_content = data.get('content')
        chat_id = data.get('chat_id')
        is_full_chat = data.get('is_full_chat', False)
        
        if not html_content or not chat_id:
            return jsonify({'error': 'Missing content or chat ID'}), 400
        
        filepath = generate_formatted_pdf(html_content, chat_id, is_full_chat)
        
        if filepath and os.path.exists(filepath):
            return send_file(
                filepath,
                as_attachment=True,
                download_name=f"Chat_{chat_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
            )
        return jsonify({'error': 'PDF generation failed'}), 500
    except Exception as e:
        print(f"PDF save error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/rename_chat', methods=['POST'])
def rename_chat():
    try:
        data = request.json
        chat_id = data.get('chat_id')
        new_name = data.get('new_name')

        if chat_id in chats:
            # Optionally, store the new name in a database or memory
            return jsonify({'message': 'Chat renamed successfully'})
        else:
            return jsonify({'error': 'Chat not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/delete_chat', methods=['POST'])
def delete_chat():
    try:
        data = request.json
        chat_id = data.get('chat_id')

        if chat_id in chats:
            del chats[chat_id]
            return jsonify({'message': 'Chat deleted successfully'})
        else:
            return jsonify({'error': 'Chat not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/upload', methods=['POST'])
def upload_file():
    """Handle file uploads."""
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400
    
    file = request.files['file']
    chat_id = request.form.get('chat_id', current_chat_id)
    
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400
    
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        content = read_file(file)
        
        if chat_id not in chats:
            chats[chat_id] = {'messages': [], 'files': {}}
        
        chats[chat_id]['files'][filename] = content
        return jsonify({'filename': filename})
    
    return jsonify({'error': 'Invalid file type'}), 400

def read_file(file):
    try:
        if file.filename.endswith('.pdf'):
            pdf = PdfReader(file)
            return "\n".join([page.extract_text() for page in pdf.pages])
        elif file.filename.endswith('.docx'):
            doc = Document(file)
            return "\n".join([para.text for para in doc.paragraphs])
        else:
            return textract.process(file).decode('utf-8')
    except Exception as e:
        raise ValueError(f"Error reading file: {str(e)}")

if __name__ == '__main__':
    # Open the website in the default browser only for the main process
    if os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
        port = 5000
        url = f"http://127.0.0.1:{port}"
        Timer(1, lambda: webbrowser.open(url)).start()

    try:
        app.run(debug=True, port=5000)
    except KeyboardInterrupt:
        print("Shutting down server...")
        exit(0)