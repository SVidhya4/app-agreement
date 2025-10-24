from flask import Flask, render_template, request, redirect, url_for, flash, jsonify # Added jsonify for potential future API use
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, OperationFailure, DuplicateKeyError
from datetime import datetime, timezone
import os
import smtplib # For sending email
from email.mime.text import MIMEText # For formatting email

app = Flask(__name__)
# Load secret key from environment variable or use a default
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'you_are_precious')

# --- MongoDB Atlas Configuration ---
MONGO_URI = os.environ.get(
    'MONGO_URI',
    "mongodb+srv://lisa_app_user:<db_password>@cluster0.mongodb.net/?retryWrites=true&w=majority"
)
DATABASE_NAME = "lisa_app_agreements"
COLLECTION_NAME = "agreements"

# --- APK Download Link ---
APK_DOWNLOAD_URL = os.environ.get('APK_DOWNLOAD_URL', '')

# --- Email Configuration (Load from Environment Variables) ---
EMAIL_SENDER_ADDRESS = os.environ.get('EMAIL_SENDER_ADDRESS', '') # Your email address (e.g., your_email@gmail.com)
EMAIL_SENDER_PASSWORD = os.environ.get('EMAIL_SENDER_PASSWORD', '') # Your email password or App Password
SMTP_SERVER = os.environ.get('SMTP_SERVER', 'smtp.gmail.com') # e.g., smtp.gmail.com for Gmail
SMTP_PORT = int(os.environ.get('SMTP_PORT', 587)) # e.g., 587 for Gmail TLS

# --- Function to get MongoDB connection ---
def get_db_collection():
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

# --- Function to Send Email ---
def send_download_link_email(recipient_email, recipient_name):
    if not EMAIL_SENDER_ADDRESS or not EMAIL_SENDER_PASSWORD:
        print("ERROR: Email sender credentials are not configured in environment variables.")
        return False # Indicate failure

    subject = "Your LISA App Download Link"
    body = f"""Hi {recipient_name},

Thank you for agreeing to the terms.

Here is your download link for the LISA app test version:
{APK_DOWNLOAD_URL}

Please remember this is for personal use only.

Best regards,
Sri Vidhya
"""
    msg = MIMEText(body)
    msg['Subject'] = subject
    msg['From'] = EMAIL_SENDER_ADDRESS
    msg['To'] = recipient_email

    try:
        print(f"Attempting to send email to {recipient_email} via {SMTP_SERVER}:{SMTP_PORT}...")
        # Connect to SMTP server and send email
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls() # Start TLS encryption
            server.login(EMAIL_SENDER_ADDRESS, EMAIL_SENDER_PASSWORD)
            server.sendmail(EMAIL_SENDER_ADDRESS, recipient_email, msg.as_string())
        print(f"Email sent successfully to {recipient_email}")
        return True # Indicate success
    except smtplib.SMTPAuthenticationError:
        print(f"ERROR: SMTP Authentication failed. Check email address/password (or App Password).")
        return False
    except Exception as e:
        print(f"ERROR: Failed to send email: {e}")
        return False # Indicate failure

# --- Route to display the agreement page ---
@app.route('/')
def index():
    return render_template('agreement.html')

# --- Route to handle the form submission ---
@app.route('/submit', methods=['POST'])
def submit_agreement():
    name = request.form.get('user_name', '').strip()
    email = request.form.get('user_email', '').strip().lower()
    phone = request.form.get('user_phone', '').strip() # Phone is now optional
    agree = request.form.get('agree_terms')

    # --- Server-Side Validation ---
    if not name or not email:
        flash("Name and Email are required.")
        return redirect(url_for('index'))
    if agree != 'yes':
        flash("You must agree to the terms.")
        return redirect(url_for('index'))
    if not APK_DOWNLOAD_URL:
        flash("Download link is not configured.")
        print("ERROR: APK_DOWNLOAD_URL is not set.")
        return redirect(url_for('index'))
    if not EMAIL_SENDER_ADDRESS or not EMAIL_SENDER_PASSWORD:
         flash("Email sending is not configured. Cannot send link.")
         print("ERROR: Email sender credentials missing.")
         return redirect(url_for('index'))


    # --- Connect to MongoDB ---
    collection, client = get_db_collection()
    if collection is None:
        flash("Database connection error. Please try again later.")
        return redirect(url_for('index'))

    is_new_user = False
    try:
        # --- Check if email already exists ---
        # Phone check is removed from uniqueness constraint for this flow
        existing_agreement = collection.find_one({"email": email})

        if existing_agreement:
            print(f"Existing user attempt for email: {email}. Sending email again.")
            # User already exists, don't need to insert again
            pass
        else:
            # --- If no duplicate email, proceed to save ---
            is_new_user = True
            agreement_doc = {
                "name": name,
                "email": email,
                "phone": phone if phone else None,
                "agreed_at": datetime.now(timezone.utc)
            }
            result = collection.insert_one(agreement_doc)
            print(f"Agreement recorded for new user: {name} ({email}) with ID: {result.inserted_id}")

        # --- Attempt to send the email ---
        email_sent = send_download_link_email(email, name)

        if email_sent:
            flash(f"Thank you, {name}! The download link has been sent to {email}.")
        else:
            # If email fails, inform the user but don't prevent access if they agreed
            flash("Thank you for agreeing. However, there was an issue sending the email. Please contact the administrator for the link.")
            # If it was a new user and email failed, maybe rollback the insert? (Optional, depends on desired logic)
            # if is_new_user:
            #     try: collection.delete_one({"_id": result.inserted_id}) except: pass

        # --- Redirect back to the index page with flash message ---
        return redirect(url_for('index'))

    except DuplicateKeyError as e:
         # This might happen if email unique index exists and check failed due to race condition
         print(f"Duplicate key error (race condition) for email: {email}. Attempting to send email.")
         # Attempt to send email even if duplicate error occurs
         email_sent = send_download_link_email(email, name)
         if email_sent: flash(f"It seems you've agreed before. The link has been re-sent to {email}.")
         else: flash("There was an issue re-sending the email. Please contact administrator.")
         return redirect(url_for('index'))

    except OperationFailure as e:
        print(f"Error during MongoDB operation: {e.details}")
        flash("Database operation error. Please try again.")
        return redirect(url_for('index'))
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        flash("An unexpected error occurred. Please try again.")
        return redirect(url_for('index'))
    finally:
        if client:
            client.close()

# --- Start the server ---
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5001))
    app.run(host='0.0.0.0', port=port)