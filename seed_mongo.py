"""
One-click MongoDB Atlas Seeding Script for ResurveyUpdates Portal
Usage:
    python seed_mongo.py "mongodb+srv://<username>:<password>@cluster0.xxxxx.mongodb.net/?retryWrites=true&w=majority"
Or set environment variable MONGODB_URI and run:
    python seed_mongo.py
"""

import sys
import os
import json

def seed():
    uri = sys.argv[1] if len(sys.argv) > 1 else os.getenv("MONGODB_URI")
    if not uri:
        print("Error: Please provide your MongoDB Atlas connection string.")
        print("Example: python seed_mongo.py \"mongodb+srv://admin:pass@cluster0.abcde.mongodb.net/?retryWrites=true&w=majority\"")
        sys.exit(1)

    try:
        from pymongo import MongoClient
        print(f"Connecting to MongoDB...")
        client = MongoClient(uri, serverSelectionTimeoutMS=5000)
        client.admin.command("ping")
        print("Connected successfully!")
    except Exception as e:
        print(f"Failed to connect to MongoDB: {e}")
        sys.exit(1)

    db_name = os.getenv("MONGODB_DB", "resurvey_portal")
    db = client[db_name]

    base_dir = os.path.dirname(os.path.abspath(__file__))
    districts_file = os.path.join(base_dir, "data", "districts.json")
    villages_file = os.path.join(base_dir, "data", "villages.json")
    users_file = os.path.join(base_dir, "data", "users.json")

    # Load data
    with open(districts_file, 'r', encoding='utf-8') as f:
        districts = json.load(f)
    with open(villages_file, 'r', encoding='utf-8') as f:
        villages = json.load(f)
    with open(users_file, 'r', encoding='utf-8') as f:
        users = json.load(f)

    # Seed districts
    db.districts.delete_many({})
    db.districts.insert_many(districts)
    db.districts.create_index("district_id", unique=True)
    db.districts.create_index("name")
    print(f"Seeded {len(districts)} districts into '{db_name}.districts'")

    # Seed villages
    db.villages.delete_many({})
    db.villages.insert_many(villages)
    db.villages.create_index("id", unique=True)
    db.villages.create_index("district_name")
    db.villages.create_index("category")
    db.villages.create_index("shapefile_status")
    print(f"Seeded {len(villages)} village records into '{db_name}.villages'")

    # Seed users
    db.users.delete_many({})
    db.users.insert_many(users)
    db.users.create_index("username", unique=True)
    print(f"Seeded {len(users)} users into '{db_name}.users'")

    print("\n" + "=" * 60)
    print("MONGODB ATLAS SEEDING COMPLETED SUCCESSFULLY!")
    print(f"Districts: {len(districts)} (All 32 Project Districts)")
    print(f"Non-Cadastral Villages: {len([v for v in villages if v.get('category') == 'Non-Cadastral'])}")
    print(f"Cadastral Villages: {len([v for v in villages if v.get('category') == 'Cadastral'])}")
    print("=" * 60)

if __name__ == "__main__":
    seed()
