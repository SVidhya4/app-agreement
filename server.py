from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session # Added jsonify and session
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, OperationFailure, DuplicateKeyError
from datetime import datetime, timezone, timedelta # Added timedelta
import os
import random # For OTP generation
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail

app = Flask(__name__)
# Load secret key - ESSENTIAL for sessions
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'you_are_precious')
# Configure session cookie settings (optional but recommended for security)
app.config.update(
    SESSION_COOKIE_SECURE=True, # Send cookie only over HTTPS (if applicable)
    SESSION_COOKIE_HTTPONLY=True, # Prevent JavaScript access to cookie
    SESSION_COOKIE_SAMESITE='Lax', # Mitigate CSRF
    PERMANENT_SESSION_LIFETIME=timedelta(minutes=10) # Set OTP validity time
)

# --- Configurations (MONGO_URI, DB names, APK_URL, Email) remain the same ---
MONGO_URI = os.environ.get(
    'MONGO_URI',
    "mongodb+srv://lisa_app_user:<db_password>@cluster0.mongodb.net/?retryWrites=true&w=majority"
)
DATABASE_NAME = "lisa_app_agreements"
COLLECTION_NAME = "agreements"
APK_DOWNLOAD_URL = os.environ.get('APK_DOWNLOAD_URL', '')
EMAIL_SENDER_ADDRESS = os.environ.get('EMAIL_SENDER_ADDRESS', '')
SENDGRID_API_KEY = os.environ.get('SENDGRID_API_KEY', '')

# --- Helper Functions (get_db_collection, send_email - slightly modified) ---
def get_db_collection():
    # ... (Keep existing get_db_collection function) ...
    client = None
    try:
        client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        client.admin.command('ping')
        print("MongoDB connection successful.")
        db = client[DATABASE_NAME]
        collection = db[COLLECTION_NAME]
        return collection, client
    except ConnectionFailure as e:
        print(f"Error connecting to MongoDB (ConnectionFailure): {e}")
        if client: client.close()
        return None, None
    except Exception as e:
        print(f"An unexpected error occurred connecting to MongoDB: {e}")
        if client: client.close()
        return None, None

def send_otp_email(recipient_email, recipient_name, otp): # Modified to send OTP
    if not SENDGRID_API_KEY or not EMAIL_SENDER_ADDRESS:
        print("ERROR: SendGrid API Key or Sender Address not configured.")
        return False
    # No need to check APK_DOWNLOAD_URL here

    subject = "Your LISA App Verification Code"
    body_html = f"""Hi {recipient_name},<br><br>
Thank you for showing interest in trying out the **LISA app**.<br><br>
Your One-Time Password (OTP) is: <strong>{otp}</strong><br><br>
This code will expire in 10 minutes.<br><br>
Best regards,<br>
Sri Vidhya
"""
    message = Mail(
        from_email=EMAIL_SENDER_ADDRESS,
        to_emails=recipient_email,
        subject=subject,
        html_content=body_html)

    try:
        print(f"Attempting to send OTP email to {recipient_email} via SendGrid...")
        sg = SendGridAPIClient(SENDGRID_API_KEY)
        response = sg.send(message)
        print(f"SendGrid response status code: {response.status_code}")
        return 200 <= response.status_code < 300
    except Exception as e:
        print(f"ERROR: Failed to send OTP email via SendGrid: {e}")
        return False

# --- Routes ---

@app.route('/')
def index():
    # Clear any stale OTP data if the user reloads the main page
    session.pop('otp_data', None)
    return render_template('agreement.html')

# --- NEW Route: Generate OTP, Store in Session, Send Email ---
@app.route('/send_otp', methods=['POST'])
def send_otp():
    name = request.form.get('user_name', '').strip()
    email = request.form.get('user_email', '').strip().lower()
    agree = request.form.get('agree_terms')

    # Basic Validation
    if not name or not email:
        return jsonify(success=False, message="Name and Email are required.")
    if agree != 'yes':
        return jsonify(success=False, message="You must agree to the terms.")
    if not EMAIL_SENDER_ADDRESS or not SENDGRID_API_KEY:
         print("ERROR: Email sender credentials missing.")
         return jsonify(success=False, message="Email sending is not configured.")

    # Generate OTP
    otp = str(random.randint(100000, 999999)) # 6-digit OTP
    otp_expiry = datetime.now(timezone.utc) + timedelta(minutes=10) # OTP valid for 10 mins

    # Store OTP and user data temporarily in session
    session['otp_data'] = {
        'email': email,
        'name': name,
        'otp': otp,
        'expiry': otp_expiry.isoformat() # Store expiry as string
    }

    # Send OTP email
    email_sent = send_otp_email(email, name, otp)

    if email_sent:
        return jsonify(success=True, message=f"OTP sent to {email}. It will expire in 10 minutes.")
    else:
        session.pop('otp_data', None) # Clear session if email failed
        return jsonify(success=False, message="Failed to send OTP email. Please try again or contact support.")


# --- NEW Route: Verify OTP, Save to DB, Return Download URL ---
@app.route('/verify_otp', methods=['POST'])
def verify_otp():
    submitted_otp = request.form.get('otp_code', '').strip()
    email = request.form.get('user_email', '').strip().lower() # Get email from hidden field

    # Retrieve stored OTP data from session
    otp_data = session.get('otp_data')

    # Validations
    if not submitted_otp:
        return jsonify(success=False, message="Please enter the OTP.")
    if not otp_data or otp_data.get('email') != email:
        return jsonify(success=False, message="Session error or email mismatch. Please start over.")

    stored_otp = otp_data.get('otp')
    expiry_str = otp_data.get('expiry')
    name = otp_data.get('name') # Get name from session

    # Check expiration
    try:
        expiry_dt = datetime.fromisoformat(expiry_str)
        if datetime.now(timezone.utc) > expiry_dt:
            session.pop('otp_data', None) # Clear expired OTP
            return jsonify(success=False, message="OTP has expired. Please request a new one.")
    except (ValueError, TypeError):
         session.pop('otp_data', None)
         return jsonify(success=False, message="Invalid session data. Please start over.")


    # Check OTP match
    if submitted_otp == stored_otp:
        # OTP Correct - Save to DB (if not already present) and return download URL
        collection, client = get_db_collection()
        if collection is None:
            return jsonify(success=False, message="Database error during verification.")

        try:
            # Check again if email exists before inserting
            existing_agreement = collection.find_one({"email": email})
            if not existing_agreement:
                agreement_doc = {
                    "name": name,
                    "email": email,
                    # Phone is not collected anymore
                    "agreed_at": datetime.now(timezone.utc)
                }
                collection.insert_one(agreement_doc)
                print(f"Agreement verified and recorded for: {name} ({email})")
            else:
                 print(f"Agreement verified for existing user: {name} ({email})")

            # Clear OTP from session AFTER successful verification & DB operation
            session.pop('otp_data', None)

            # Return success and the download URL
            return jsonify(success=True, download_url=APK_DOWNLOAD_URL)

        except Exception as db_error:
            print(f"Database error during OTP verification save: {db_error}")
            return jsonify(success=False, message="Database error saving agreement.")
        finally:
            if client: client.close()

    else:
        # OTP Incorrect
        return jsonify(success=False, message="Invalid OTP code.")


# --- Remove the old /submit route ---
# @app.route('/submit', methods=['POST'])
# def submit_agreement():
#    ... (Delete this entire function) ...


# --- Start the server ---
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5001))
    app.run(host='0.0.0.0', port=port)