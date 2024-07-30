from flask import Flask, request, render_template, send_file, url_for
import pdfplumber
import mysql.connector
import re
from fuzzywuzzy import fuzz
import spacy
import io
from io import BytesIO

app = Flask(__name__)

# Load the spaCy model
nlp = spacy.load("en_core_web_sm")

# MySQL database connection
db = mysql.connector.connect(
    host="localhost",
    user="root",
    password="",
    database="resume_db"
)

# Create resumes table if it doesn't exist
cursor = db.cursor()
cursor.execute("""
    CREATE TABLE IF NOT EXISTS resumes (
        id INT AUTO_INCREMENT PRIMARY KEY,
        filename VARCHAR(255),
        text LONGTEXT,
        name VARCHAR(255),
        mobile_number VARCHAR(20),
        email_address VARCHAR(100),
        score INT,
        uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
""")

# Upload resumes and input text
@app.route('/job/upload_resumes', methods=['GET', 'POST'])
def upload_resumes():
    if request.method == 'POST':
        resumes = request.files.getlist('resumes')
        input_text = request.form.get('input_text')
        input_text = input_text.lower()

        uploaded_resumes = []

        # Extract text from each resume using pdfplumber
        for resume in resumes:
            with pdfplumber.open(resume) as pdf:
                text = ""
                for page in pdf.pages:
                    text += page.extract_text()

                # Process the text using spaCy
                doc = nlp(text)
                # Extract names from the text
                names = [ent.text for ent in doc.ents if ent.label_ == "PERSON"]
                name = names[0] if names else ""
                # Extract mobile numbers from the text
                mobile_numbers = re.findall(r"""
                (\+91\s?\d{5}\s?\d{5}) |  # International format with spaces
                (\+91\s?\d{10}) |         # International format without spaces
                (\d{5}\s?\d{5}) |         # Standard format with spaces
                (\d{5}-\d{5}) |           # Standard format with dashes
                (\d{10})                   # Standard format without spaces or dashes
                """, text, re.VERBOSE)
                mobile_number = mobile_numbers[0][0] if mobile_numbers else ""
                # Extract email addresses from the text
                email_addresses = re.findall(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', text)
                email_address = email_addresses[0] if email_addresses else ""

                # Store extracted text, name, mobile number, email address, and filename in MySQL database
                cursor = db.cursor()
                cursor.execute("INSERT INTO resumes (filename, text, name, mobile_number, email_address) VALUES (%s, %s, %s, %s, %s)", (resume.filename, text, name.lower(), mobile_number, email_address))
                db.commit()
                
                # Retrieve the inserted resume ID
                resume_id = cursor.lastrowid
                uploaded_resumes.append((resume_id, text.lower(), name.lower(), mobile_number, email_address))

        # Match input text with extracted text and calculate scores
        if input_text:
            keywords = re.findall(r'\b\w+\b', input_text)
            matched_results = []

            for resume_id, text, name, mobile_number, email_address in uploaded_resumes:
                score = 0
                for keyword in keywords:
                    if keyword in text or keyword in name or keyword in mobile_number or keyword in email_address:
                        score += 1
                score = min(100, score * (100 // len(keywords)))  # Normalize score out of 100

                # Update the resume with the calculated score
                cursor.execute("UPDATE resumes SET score = %s WHERE id = %s", (score, resume_id))
                db.commit()

                matched_results.append((resume_id, name, mobile_number, email_address, score))

            # Sort results by score in descending order
            matched_results.sort(key=lambda x: x[4], reverse=True)

            # Render Page 2 with matched results
            return render_template('results.html', matched_results=matched_results)

    return render_template('upload_resumes.html')

# Serve PDF files
@app.route('/pdf/<int:resume_id>')
def serve_pdf(resume_id):
    cursor = db.cursor()
    cursor.execute("SELECT filename, text FROM resumes WHERE id = %s", (resume_id,))
    result = cursor.fetchone()
    if result:
        filename, pdf_data = result
        return send_file(
            io.BytesIO(pdf_data.encode('utf-8')),
            as_attachment=False,
            mimetype='application/pdf'
        )
    return "File not found", 404

# Run the app
if __name__ == '__main__':
    app.run(debug=True)