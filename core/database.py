import os
import json
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
DISTRICTS_FILE = os.path.join(DATA_DIR, "districts.json")
VILLAGES_FILE = os.path.join(DATA_DIR, "villages.json")
USERS_FILE = os.path.join(DATA_DIR, "users.json")

MONGODB_URI = os.getenv("MONGODB_URI")
DB_NAME = os.getenv("MONGODB_DB", "resurvey_portal")

mongo_client = None
mongo_db = None
is_mongo = False

def init_db():
    global mongo_client, mongo_db, is_mongo
    if MONGODB_URI:
        try:
            from pymongo import MongoClient
            client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=3000)
            client.admin.command('ping')
            mongo_client = client
            mongo_db = client[DB_NAME]
            is_mongo = True
            logger.info("Successfully connected to MongoDB Atlas!")
            
            # Ensure collections are seeded if empty
            if mongo_db.districts.count_documents({}) == 0:
                seed_mongo_from_files(mongo_db)
            return
        except Exception as e:
            logger.warning(f"Failed to connect to MongoDB ({e}). Falling back to local data files.")
            is_mongo = False
    else:
        logger.info("No MONGODB_URI set. Operating on local JSON data store.")
        is_mongo = False

def seed_mongo_from_files(db):
    try:
        if os.path.exists(DISTRICTS_FILE):
            with open(DISTRICTS_FILE, 'r', encoding='utf-8') as f:
                dists = json.load(f)
                if dists:
                    db.districts.insert_many(dists)
        if os.path.exists(VILLAGES_FILE):
            with open(VILLAGES_FILE, 'r', encoding='utf-8') as f:
                vlgs = json.load(f)
                if vlgs:
                    db.villages.insert_many(vlgs)
        if os.path.exists(USERS_FILE):
            with open(USERS_FILE, 'r', encoding='utf-8') as f:
                usrs = json.load(f)
                if usrs:
                    db.users.insert_many(usrs)
        logger.info("MongoDB seeded successfully from baseline dataset.")
    except Exception as e:
        logger.error(f"Error seeding MongoDB: {e}")

# Helper local JSON loaders
def _load_json(file_path: str) -> List[Dict[str, Any]]:
    if not os.path.exists(file_path):
        return []
    with open(file_path, 'r', encoding='utf-8') as f:
        return json.load(f)

def _save_json(file_path: str, data: Any):
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

# API Operations
def get_db_status() -> Dict[str, Any]:
    global is_mongo
    return {
        "is_mongodb": is_mongo,
        "engine": "MongoDB Atlas / Mongo Server" if is_mongo else "Embedded Local Data Engine",
        "database": DB_NAME if is_mongo else "local_json",
        "ready_for_cloud": True
    }

def get_districts() -> List[Dict[str, Any]]:
    if is_mongo and mongo_db is not None:
        docs = list(mongo_db.districts.find({}, {"_id": 0}))
        return docs
    return _load_json(DISTRICTS_FILE)

def get_villages(
    district: Optional[str] = None,
    category: Optional[str] = None,
    shapefile_status: Optional[str] = None,
    search: Optional[str] = None
) -> List[Dict[str, Any]]:
    if is_mongo and mongo_db is not None:
        query = {}
        if district and district.lower() != "all":
            query["district_name"] = {"$regex": f"^{district}$", "$options": "i"}
        if category and category.lower() != "all":
            query["category"] = category
        if shapefile_status and shapefile_status.lower() != "all":
            query["shapefile_status"] = shapefile_status
        if search and search.strip():
            s = search.strip()
            query["$or"] = [
                {"village_name": {"$regex": s, "$options": "i"}},
                {"mandal_name": {"$regex": s, "$options": "i"}},
                {"remarks": {"$regex": s, "$options": "i"}}
            ]
        docs = list(mongo_db.villages.find(query, {"_id": 0}))
        return docs
    
    # Fallback to local
    records = _load_json(VILLAGES_FILE)
    filtered = []
    for r in records:
        if district and district.lower() != "all":
            if r.get("district_name", "").lower() != district.lower():
                continue
        if category and category.lower() != "all":
            if r.get("category", "") != category:
                continue
        if shapefile_status and shapefile_status.lower() != "all":
            if r.get("shapefile_status", "") != shapefile_status:
                continue
        if search and search.strip():
            s = search.strip().lower()
            v_name = r.get("village_name", "").lower()
            m_name = r.get("mandal_name", "").lower()
            rem = r.get("remarks", "").lower()
            if s not in v_name and s not in m_name and s not in rem:
                continue
        filtered.append(r)
    return filtered

def get_village(village_id: str) -> Optional[Dict[str, Any]]:
    if is_mongo and mongo_db is not None:
        return mongo_db.villages.find_one({"id": village_id}, {"_id": 0})
    for v in _load_json(VILLAGES_FILE):
        if v.get("id") == village_id:
            return v
    return None

def add_village(village: Dict[str, Any]) -> Dict[str, Any]:
    if "id" not in village or not village["id"]:
        village["id"] = f"vlg-{int(datetime.utcnow().timestamp() * 1000)}"
    if "updated_at" not in village:
        village["updated_at"] = datetime.utcnow().isoformat()
    
    if is_mongo and mongo_db is not None:
        mongo_db.villages.insert_one(dict(village))
        if "_id" in village:
            del village["_id"]
        return village
    
    records = _load_json(VILLAGES_FILE)
    records.append(village)
    _save_json(VILLAGES_FILE, records)
    return village

def update_village(village_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    updates["updated_at"] = datetime.utcnow().isoformat()
    if is_mongo and mongo_db is not None:
        mongo_db.villages.update_one({"id": village_id}, {"$set": updates})
        return mongo_db.villages.find_one({"id": village_id}, {"_id": 0})
    
    records = _load_json(VILLAGES_FILE)
    for idx, v in enumerate(records):
        if v.get("id") == village_id:
            records[idx].update(updates)
            _save_json(VILLAGES_FILE, records)
            return records[idx]
    return None

def delete_village(village_id: str) -> bool:
    if is_mongo and mongo_db is not None:
        res = mongo_db.villages.delete_one({"id": village_id})
        return res.deleted_count > 0
    
    records = _load_json(VILLAGES_FILE)
    initial_len = len(records)
    records = [r for r in records if r.get("id") != village_id]
    if len(records) < initial_len:
        _save_json(VILLAGES_FILE, records)
        return True
    return False

def get_dashboard_stats() -> Dict[str, Any]:
    districts = get_districts()
    villages = get_villages()
    
    total_non_cadastral_target = sum(d.get("non_cadastral_target", 0) for d in districts)
    total_cadastral_target = sum(d.get("cadastral_target", 0) for d in districts)
    
    gt_non_cadastral = [v for v in villages if v.get("category") == "Non-Cadastral" and v.get("gt_status") == "Completed"]
    gt_cadastral = [v for v in villages if v.get("category") == "Cadastral" and v.get("gt_status") == "Completed"]
    
    shapefile_completed = [v for v in villages if v.get("shapefile_status") == "Completed"]
    shapefile_error = [v for v in villages if v.get("shapefile_status") == "Error"]
    shapefile_in_progress = [v for v in villages if v.get("shapefile_status") == "In Progress"]
    sent_to_cso_count = [v for v in villages if v.get("sent_to_cso") is True]
    
    total_acres = sum(v.get("extent_acres_float", 0.0) or 0.0 for v in villages)
    
    # District wise rollups
    district_summary = []
    for d in districts:
        d_name = d["name"]
        d_vlgs = [v for v in villages if v.get("district_name", "").lower() == d_name.lower()]
        d_non_cad_gt = [v for v in d_vlgs if v.get("category") == "Non-Cadastral" and v.get("gt_status") == "Completed"]
        d_cad_gt = [v for v in d_vlgs if v.get("category") == "Cadastral" and v.get("gt_status") == "Completed"]
        d_sf_sent = [v for v in d_vlgs if v.get("sent_to_cso") is True or v.get("shapefile_status") == "Completed"]
        d_sf_err = [v for v in d_vlgs if v.get("shapefile_status") == "Error"]
        d_acres = sum(v.get("extent_acres_float", 0.0) or 0.0 for v in d_vlgs)
        
        district_summary.append({
            "district": d_name,
            "non_cadastral_target": d.get("non_cadastral_target", 0),
            "cadastral_target": d.get("cadastral_target", 0),
            "non_cadastral_gt_done": len(d_non_cad_gt),
            "cadastral_gt_done": len(d_cad_gt),
            "total_gt_done": len(d_non_cad_gt) + len(d_cad_gt),
            "shapefiles_sent": len(d_sf_sent),
            "shapefiles_error": len(d_sf_err),
            "total_extent_acres": round(d_acres, 2),
            "villages_count": len(d_vlgs)
        })
    
    return {
        "total_districts": len(districts),
        "targets": {
            "non_cadastral": total_non_cadastral_target,
            "cadastral": total_cadastral_target,
            "combined": total_non_cadastral_target + total_cadastral_target
        },
        "gt_completed": {
            "non_cadastral": len(gt_non_cadastral),
            "cadastral": len(gt_cadastral),
            "total": len(gt_non_cadastral) + len(gt_cadastral)
        },
        "shapefiles": {
            "completed": len(shapefile_completed),
            "error": len(shapefile_error),
            "in_progress": len(shapefile_in_progress),
            "sent_to_cso": len(sent_to_cso_count)
        },
        "total_extent_acres": round(total_acres, 2),
        "districts_summary": district_summary
    }

def authenticate_user(username: str, password: str) -> Optional[Dict[str, Any]]:
    if is_mongo and mongo_db is not None:
        user = mongo_db.users.find_one({"username": username}, {"_id": 0})
    else:
        users = _load_json(USERS_FILE)
        user = next((u for u in users if u.get("username") == username), None)
    
    if user and user.get("password") == password:
        user_safe = dict(user)
        if "password" in user_safe:
            del user_safe["password"]
        return user_safe
    return None

# Initialize on module import
init_db()
