from flask import Flask, render_template, request, redirect, url_for, flash
# Removed: import mysql.connector
from pymongo import MongoClient # Import MongoClient
from pymongo.errors import ConnectionFailure, OperationFailure # For better error handling
from datetime import datetime
import os

app = Flask(__name__)
# Load secret key from environment variable
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'you_are_precious')

# --- MongoDB Atlas Configuration ---
# ⚠️ Replace <db_password> with your actual database user password!
# It's HIGHLY recommended to load this whole string from an environment variable
MONGO_URI = os.environ.get(
    'MONGO_URI',
    "mongodb+srv://srividhya2972004_db_user:dIDRYQL0HHMhzQke@lisa-app-cluster.bn27hqg.mongodb.net/?retryWrites=true&w=majority&appName=lisa-app-cluster"
)
DATABASE_NAME = "lisa_app_agreements" # You can choose this name
COLLECTION_NAME = "agreements"        # You can choose this name

# --- APK Download Link ---
APK_DOWNLOAD_URL = os.environ.get('APK_DOWNLOAD_URL', 'YOUR_DEFAULT_APK_LINK_OR_EMPTY')
# Function to get MongoDB collection and client
def get_db_collection():
    client = None # Initialize client to None
    try:
        # Add serverSelectionTimeoutMS to handle connection issues faster
        client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        # The ismaster command is cheap and does not require auth.
        client.admin.command('ping')
        print("MongoDB connection successful.")
        db = client[DATABASE_NAME]
        collection = db[COLLECTION_NAME]
        return collection, client # Return both collection and client
    except ConnectionFailure as e:
        print(f"Error connecting to MongoDB (ConnectionFailure): {e}")
        if client:
            client.close()
        return None, None
    except Exception as e:
        print(f"An unexpected error occurred connecting to MongoDB: {e}")
        if client:
            client.close()
        return None, None

# --- Route to display the agreement page ---
@app.route('/')
def index():
    return render_template('agreement.html')

# --- Route to handle the form submission ---
@app.route('/submit', methods=['POST'])
def submit_agreement():
    name = request.form.get('user_name')
    email = request.form.get('user_email')
    phone = request.form.get('user_phone', '')
    agree = request.form.get('agree_terms')

    # --- Server-Side Validation ---
    if not name or not email:
        flash("Name and Email are required.")
        return redirect(url_for('index'))
    if agree != 'yes':
        flash("You must agree to the terms.")
        return redirect(url_for('index'))

    # --- Save to MongoDB ---
    collection, client = get_db_collection()
    if collection is None:
        flash("Database connection error. Please try again later.")
        return redirect(url_for('index'))

    try:
        agreement_doc = {
            "name": name,
            "email": email,
            "phone": phone,
            "agreed_at": datetime.utcnow() # Use UTC for timestamps
        }
        # Insert the document
        result = collection.insert_one(agreement_doc)
        print(f"Agreement recorded for: {name} ({email}) with ID: {result.inserted_id}")

        # --- Redirect to APK download ---
        # Only redirect AFTER successful database insertion
        return redirect(APK_DOWNLOAD_URL)

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
    app.run(host='0.0.0.0', port=5001)