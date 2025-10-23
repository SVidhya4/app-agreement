from flask import Flask, render_template, request, redirect, url_for, flash
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, OperationFailure, DuplicateKeyError # Added DuplicateKeyError
from datetime import datetime, timezone # Added timezone
import os

app = Flask(__name__)
# Load secret key from environment variable or use a default
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'you_are_precious') # Using your specified default

# --- MongoDB Atlas Configuration ---
# Load MONGO_URI from environment variable or use the provided default
# REMEMBER TO REPLACE <db_password> or set the environment variable
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
    email = request.form.get('user_email', '').strip().lower() # Store email lowercase for consistency
    phone = request.form.get('user_phone', '').strip()
    agree = request.form.get('agree_terms')

    # --- Server-Side Validation ---
    if not name or not email:
        flash("Name and Email are required.")
        return redirect(url_for('index'))
    if agree != 'yes':
        flash("You must agree to the terms.")
        return redirect(url_for('index'))
    if not APK_DOWNLOAD_URL: # Check if download URL is configured
        flash("Download link is not configured. Please contact the administrator.")
        print("ERROR: APK_DOWNLOAD_URL is not set.")
        return redirect(url_for('index'))


    # --- Save to MongoDB ---
    collection, client = get_db_collection()
    if collection is None:
        flash("Database connection error. Please try again later.")
        return redirect(url_for('index'))

    try:
        # --- Check for existing email or phone ---
        query_conditions = [{"email": email}]
        # Only add phone to the query if it's not empty
        if phone:
            query_conditions.append({"phone": phone})

        existing_agreement = collection.find_one({"$or": query_conditions})

        if existing_agreement:
            # Determine which field caused the conflict
            error_message = "This email address has already agreed to the terms."
            # Check phone only if it was provided and matches the existing record
            if phone and existing_agreement.get('phone') == phone:
                error_message = "This phone number has already agreed to the terms."
            flash(error_message)
            return redirect(url_for('index'))

        # --- If no duplicate, proceed to save ---
        agreement_doc = {
            "name": name,
            "email": email,
            "phone": phone if phone else None, # Store None if phone is empty
            "agreed_at": datetime.now(timezone.utc) # CORRECT timezone-aware UTC timestamp
        }
        result = collection.insert_one(agreement_doc)
        print(f"Agreement recorded for: {name} ({email}) with ID: {result.inserted_id}")

        # --- Redirect to APK download ---
        return redirect(APK_DOWNLOAD_URL)

    except DuplicateKeyError as e:
         # This catches errors if the unique index in MongoDB is violated
         # (Handles race conditions where the check above might miss a concurrent insert)
        print(f"Duplicate key error during MongoDB insertion: {e.details}")
        # Try to determine which field caused it based on the index name in the error (may vary)
        if 'email_1' in str(e.details):
             flash("This email address has already agreed (concurrent check).")
        elif 'phone_1' in str(e.details):
             flash("This phone number has already agreed (concurrent check).")
        else:
             flash("This email or phone number has already agreed.")
        return redirect(url_for('index'))

    except OperationFailure as e:
        print(f"Error inserting into MongoDB (OperationFailure): {e.details}")
        flash("Error saving agreement due to database operation failure.")
        return redirect(url_for('index'))
    except Exception as e:
        print(f"An unexpected error occurred during MongoDB insertion: {e}")
        flash("Error saving agreement. Please try again.")
        return redirect(url_for('index'))
    finally:
        if client:
            client.close() # Ensure the connection is closed

# --- Start the server ---
if __name__ == '__main__':
    # Use 0.0.0.0 for Render, port will be assigned by Render (usually)
    # For local testing, use port=5001 or another available port
    port = int(os.environ.get('PORT', 5001)) # Render uses PORT env var
    app.run(host='0.0.0.0', port=port)