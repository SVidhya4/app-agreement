from flask import Flask, render_template, request, redirect, url_for, flash
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, OperationFailure, DuplicateKeyError
from datetime import datetime, timezone
import os

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
# Load APK_DOWNLOAD_URL from environment variable or use an empty default
APK_DOWNLOAD_URL = os.environ.get('APK_DOWNLOAD_URL', '')

# Function to get MongoDB collection and client
def get_db_collection():
    client = None
    try:
        client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        client.admin.command('ping') # Verify connection
        print("MongoDB connection successful.")
        db = client[DATABASE_NAME]
        collection = db[COLLECTION_NAME]
        return collection, client
    except ConnectionFailure as e:
        print(f"Error connecting to MongoDB (ConnectionFailure): {e}")
        if client: client.close()
        return None, None
    except Exception as e: # Catch other potential errors like configuration errors
        print(f"An unexpected error occurred connecting to MongoDB: {e}")
        if client: client.close()
        return None, None

# --- Route to display the agreement page ---
@app.route('/')
def index():
    # Ensure agreement.html is in the 'templates' folder
    return render_template('agreement.html')

# --- Route to handle the form submission ---
@app.route('/submit', methods=['POST'])
def submit_agreement():
    name = request.form.get('user_name', '').strip()
    email = request.form.get('user_email', '').strip().lower() # Store email lowercase
    phone = request.form.get('user_phone', '').strip()
    agree = request.form.get('agree_terms')

    # --- Server-Side Validation ---
    if not name or not email:
        flash("Name and Email are required.")
        return redirect(url_for('index'))
    if agree != 'yes':
        flash("You must agree to the terms.")
        return redirect(url_for('index'))
    # Check if download URL is configured
    if not APK_DOWNLOAD_URL:
        flash("Download link is not configured.")
        print("ERROR: APK_DOWNLOAD_URL is not set.")
        return redirect(url_for('index'))

    # --- Connect to MongoDB ---
    collection, client = get_db_collection()
    if collection is None:
        flash("Database connection error. Please try again later.")
        return redirect(url_for('index'))

    # Default redirect is the download link
    redirect_url = APK_DOWNLOAD_URL

    try:
        # --- Check for existing email or phone ---
        query_conditions = [{"email": email}]
        if phone:
            query_conditions.append({"phone": phone})

        existing_agreement = collection.find_one({"$or": query_conditions})

        if existing_agreement:
            # If entry exists, log it and prepare to redirect to download
            print(f"Duplicate entry attempt for email: {email} or phone: {phone}. Redirecting to download.")
            # redirect_url is already set to APK_DOWNLOAD_URL
            pass # Skip insertion

        else:
            # --- If no duplicate, proceed to save ---
            agreement_doc = {
                "name": name,
                "email": email,
                "phone": phone if phone else None,
                "agreed_at": datetime.now(timezone.utc)
            }
            result = collection.insert_one(agreement_doc)
            print(f"Agreement recorded for new user: {name} ({email}) with ID: {result.inserted_id}")
            # redirect_url remains APK_DOWNLOAD_URL

    # --- Error Handling ---
    except DuplicateKeyError as e:
         # Race condition duplicate - still redirect to download
         print(f"Duplicate key error (race condition) for email: {email} or phone: {phone}. Redirecting to download.")
         pass # redirect_url is already APK_DOWNLOAD_URL
    except OperationFailure as e:
        print(f"Error during MongoDB operation: {e.details}")
        flash("Database operation error. Please try again.")
        redirect_url = url_for('index') # On DB error, redirect back to index
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        flash("An unexpected error occurred. Please try again.")
        redirect_url = url_for('index') # On other errors, redirect back to index
    finally:
        if client:
            client.close() # Ensure the connection is closed

    # --- Perform the redirect ---
    # Will redirect to APK_DOWNLOAD_URL on success or duplicate,
    # or back to index() on database/unexpected errors.
    return redirect(redirect_url)


# --- Start the server ---
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5001))
    app.run(host='0.0.0.0', port=port)