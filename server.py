from flask import Flask, render_template, request, redirect, url_for, flash
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, OperationFailure, DuplicateKeyError
from datetime import datetime, timezone
import os
# Removed: import smtplib
# Removed: from email.mime.text import MIMEText
from sendgrid import SendGridAPIClient # Import SendGrid
from sendgrid.helpers.mail import Mail # Import Mail helper

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

# --- Email Configuration (Load SendGrid Key and Sender Address) ---
# Ensure these are set in your Render Environment Variables
EMAIL_SENDER_ADDRESS = os.environ.get('EMAIL_SENDER_ADDRESS', '') # Your verified sender email
SENDGRID_API_KEY = os.environ.get('SENDGRID_API_KEY', '')     # Your SendGrid API Key

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

# --- Function to Send Email using SendGrid ---
def send_download_link_email(recipient_email, recipient_name):
    if not SENDGRID_API_KEY or not EMAIL_SENDER_ADDRESS:
        print("ERROR: SendGrid API Key or Sender Address not configured.")
        return False # Indicate failure
    if not APK_DOWNLOAD_URL:
        print("ERROR: APK Download URL not configured for email.")
        return False # Indicate failure

    subject = "Your LISA App Download Link"
    # Use HTML content for better formatting and clickable link
    body_html = f"""Hi {recipient_name},<br><br>
Thank you for agreeing to the terms.<br><br>
Here is your download link for the LISA app test version:<br>
<a href="{APK_DOWNLOAD_URL}">{APK_DOWNLOAD_URL}</a><br><br>
Please remember this is for personal use only.<br><br>
Best regards,<br>
Sri Vidhya
"""
    # Create a Mail object
    message = Mail(
        from_email=EMAIL_SENDER_ADDRESS,
        to_emails=recipient_email,
        subject=subject,
        html_content=body_html)

    try:
        print(f"Attempting to send email to {recipient_email} via SendGrid...")
        sg = SendGridAPIClient(SENDGRID_API_KEY)
        response = sg.send(message) # Send the email
        print(f"SendGrid response status code: {response.status_code}")
        # Check if SendGrid accepted the request (status code 2xx)
        if 200 <= response.status_code < 300:
             print(f"Email successfully initiated to {recipient_email}")
             return True
        else:
             # Log the error details from SendGrid if available
             print(f"ERROR: SendGrid failed with status {response.status_code}. Body: {response.body}")
             return False
    except Exception as e:
        print(f"ERROR: Failed to send email via SendGrid: {e}")
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
    phone = request.form.get('user_phone', '').strip() # Phone is optional
    agree = request.form.get('agree_terms')

    # --- Server-Side Validation ---
    if not name or not email:
        flash("Name and Email are required.")
        return redirect(url_for('index'))
    if agree != 'yes':
        flash("You must agree to the terms.")
        return redirect(url_for('index'))
    # Check essential configurations
    if not APK_DOWNLOAD_URL:
        flash("Download link is not configured.")
        print("ERROR: APK_DOWNLOAD_URL is not set.")
        return redirect(url_for('index'))
    if not SENDGRID_API_KEY or not EMAIL_SENDER_ADDRESS:
         flash("Email sending is not configured. Cannot send link.")
         print("ERROR: SendGrid API Key or Sender Address missing.")
         return redirect(url_for('index'))

    # --- Connect to MongoDB ---
    collection, client = get_db_collection()
    if collection is None:
        flash("Database connection error. Please try again later.")
        return redirect(url_for('index'))

    is_new_user = False
    try:
        # --- Check if email already exists ---
        existing_agreement = collection.find_one({"email": email})

        if existing_agreement:
            print(f"Existing user attempt for email: {email}. Sending email again.")
            pass # Don't insert again
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
            flash("Thank you for agreeing. However, there was an issue sending the email. Please contact the administrator for the link.")
            # Optional: Rollback DB insert if email fails for a new user
            # if is_new_user and 'result' in locals() and result.inserted_id:
            #     try: collection.delete_one({"_id": result.inserted_id}); print("Rolled back DB insert due to email failure.") except: pass

        # --- Redirect back to the index page with flash message ---
        return redirect(url_for('index'))

    except DuplicateKeyError as e:
         print(f"Duplicate key error (race condition) for email: {email}. Attempting to send email.")
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