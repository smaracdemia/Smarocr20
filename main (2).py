
from flask import Flask, render_template, request, flash, redirect, url_for, jsonify
import os
from werkzeug.utils import secure_filename
from datetime import datetime, date
import pytesseract
from PIL import Image
import re
import hashlib
import json

app = Flask(__name__)
app.secret_key = 'your-secret-key-change-this'
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# Create uploads directory if it doesn't exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# File to store used screenshot hashes (to prevent reuse)
USED_SCREENSHOTS_FILE = 'used_screenshots.json'

# Required payment details
REQUIRED_NAME = "YABETS AKALU GEBREMICHAEL"
REQUIRED_ACCOUNT = "1000650258367"
MINIMUM_AMOUNT = 20

def load_used_screenshots():
    """Load list of used screenshot hashes"""
    try:
        with open(USED_SCREENSHOTS_FILE, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return []

def save_used_screenshot(image_hash):
    """Save screenshot hash to prevent reuse"""
    used_screenshots = load_used_screenshots()
    used_screenshots.append({
        'hash': image_hash,
        'timestamp': datetime.now().isoformat()
    })
    with open(USED_SCREENSHOTS_FILE, 'w') as f:
        json.dump(used_screenshots, f)

def get_image_hash(image_path):
    """Generate hash of image to detect duplicates"""
    with open(image_path, 'rb') as f:
        return hashlib.md5(f.read()).hexdigest()

def is_screenshot_used(image_hash):
    """Check if screenshot has been used before"""
    used_screenshots = load_used_screenshots()
    return any(item['hash'] == image_hash for item in used_screenshots)

def extract_text_from_image(image_path):
    """Extract text from image using OCR"""
    try:
        image = Image.open(image_path)
        text = pytesseract.image_to_string(image)
        return text
    except Exception as e:
        return f"Error extracting text: {str(e)}"

def validate_payment_screenshot(text, image_hash):
    """Validate payment screenshot based on requirements"""
    errors = []
    
    # Check if screenshot was already used
    if is_screenshot_used(image_hash):
        errors.append("This screenshot has already been used. Please upload a new payment screenshot.")
        return False, errors
    
    # Convert text to uppercase for easier matching
    text_upper = text.upper()
    
    # Check for required name or account number
    name_found = REQUIRED_NAME.upper() in text_upper
    account_found = REQUIRED_ACCOUNT in text
    
    if not (name_found or account_found):
        errors.append(f"Payment must be made to {REQUIRED_NAME} or account {REQUIRED_ACCOUNT}")
    
    # Extract and validate amount - look for amount patterns more specifically
    amount_patterns = [
        r'(?:ETB|BIRR|BR)\s*(\d+(?:\.\d{2})?)',  # Currency prefix
        r'(\d+(?:\.\d{2})?)\s*(?:ETB|BIRR|BR)',  # Currency suffix
        r'Amount[:\s]+(\d+(?:\.\d{2})?)',        # Amount: 20
        r'Total[:\s]+(\d+(?:\.\d{2})?)',         # Total: 20
        r'Pay[:\s]+(\d+(?:\.\d{2})?)',           # Pay: 20
    ]
    
    valid_amount = False
    found_amounts = []
    
    for pattern in amount_patterns:
        amounts = re.findall(pattern, text, re.IGNORECASE)
        for amount_str in amounts:
            try:
                amount = float(amount_str)
                found_amounts.append(amount)
                if amount >= MINIMUM_AMOUNT:
                    valid_amount = True
            except ValueError:
                continue
    
    if not valid_amount:
        if found_amounts:
            max_found = max(found_amounts)
            errors.append(f"Payment amount found ({max_found} ETB) is less than required minimum of {MINIMUM_AMOUNT} ETB")
        else:
            errors.append(f"No valid payment amount found. Amount must be {MINIMUM_AMOUNT} ETB or greater")
    
    # Check for today's date
    today = date.today()
    date_patterns = [
        today.strftime("%d/%m/%Y"),
        today.strftime("%d-%m-%Y"),
        today.strftime("%Y-%m-%d"),
        today.strftime("%d.%m.%Y"),
        today.strftime("%B %d, %Y"),
        today.strftime("%d %B %Y")
    ]
    
    date_found = any(date_pattern in text for date_pattern in date_patterns)
    if not date_found:
        errors.append("Payment date must be today's date")
    
    return len(errors) == 0, errors

@app.route('/')
def index():
    redirect_url = request.args.get('redirect', '')
    return render_template('index.html', redirect_url=redirect_url)

@app.route('/upload', methods=['POST'])
def upload_payment():
    if 'payment_screenshot' not in request.files:
        flash('No file selected')
        return redirect(url_for('index'))
    
    file = request.files['payment_screenshot']
    if file.filename == '':
        flash('No file selected')
        return redirect(url_for('index'))
    
    if file and file.filename.lower().endswith(('.png', '.jpg', '.jpeg')):
        filename = secure_filename(file.filename)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_')
        filename = timestamp + filename
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        
        # Get image hash
        image_hash = get_image_hash(filepath)
        
        # Extract text using OCR
        extracted_text = extract_text_from_image(filepath)
        
        # Validate payment
        is_valid, errors = validate_payment_screenshot(extracted_text, image_hash)
        
        # Clean up uploaded file
        os.remove(filepath)
        
        # Get redirect URL from form
        redirect_url = request.form.get('redirect_url', '')
        
        if is_valid:
            # Save screenshot hash to prevent reuse
            save_used_screenshot(image_hash)
            return render_template('result.html', 
                                 is_valid=True, 
                                 errors=[], 
                                 extracted_text=extracted_text,
                                 redirect_url=redirect_url)
        else:
            return render_template('result.html', 
                                 is_valid=False, 
                                 errors=errors, 
                                 extracted_text=extracted_text,
                                 redirect_url=redirect_url)
    
    flash('Please upload a valid image file (PNG, JPG, JPEG)')
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
