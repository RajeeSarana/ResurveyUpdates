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
REPRESENTATIVES_FILE = os.path.join(DATA_DIR, "representatives.json")
AUDIT_LOGS_FILE = os.path.join(DATA_DIR, "audit_logs.json")

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
            logger.info("Connected to MongoDB Atlas!")
            
            if mongo_db.districts.count_documents({}) == 0:
                seed_mongo_from_files(mongo_db)
            return
        except Exception as e:
            logger.warning(f"Failed to connect to MongoDB ({e}). Falling back to local data store.")
            is_mongo = False
    else:
        is_mongo = False

def seed_mongo_from_files(db):
    try:
        for file_path, collection_name in [
            (DISTRICTS_FILE, "districts"),
            (VILLAGES_FILE, "villages"),
            (USERS_FILE, "users"),
            (REPRESENTATIVES_FILE, "representatives"),
            (AUDIT_LOGS_FILE, "audit_logs")
        ]:
            if os.path.exists(file_path):
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if data:
                        db[collection_name].insert_many(data)
        logger.info("MongoDB seeded successfully.")
    except Exception as e:
        logger.error(f"Error seeding MongoDB: {e}")

def _load_json(file_path: str) -> List[Dict[str, Any]]:
    if not os.path.exists(file_path):
        return []
    with open(file_path, 'r', encoding='utf-8') as f:
        return json.load(f)

def _save_json(file_path: str, data: Any):
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def get_db_status() -> Dict[str, Any]:
    global is_mongo
    return {
        "is_mongodb": is_mongo,
        "engine": "MongoDB Atlas" if is_mongo else "Embedded Local Data Engine",
        "database": DB_NAME if is_mongo else "local_json",
        "ready_for_cloud": True
    }

# ----------------- AUDIT LOGS -----------------
def log_change(
    record_id: str,
    village_name: str,
    district_name: str,
    user_name: str,
    user_role: str,
    action: str,
    details: str,
    changes: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    log_entry = {
        "id": f"log-{int(datetime.utcnow().timestamp() * 1000)}",
        "timestamp": datetime.utcnow().isoformat(),
        "record_id": record_id,
        "village_name": village_name,
        "district_name": district_name,
        "user_name": user_name,
        "user_role": user_role,
        "action": action,
        "details": details,
        "changes": changes or {}
    }
    if is_mongo and mongo_db is not None:
        mongo_db.audit_logs.insert_one(dict(log_entry))
        if "_id" in log_entry:
            del log_entry["_id"]
    
    logs = _load_json(AUDIT_LOGS_FILE)
    logs.insert(0, log_entry)  # prepend latest
    _save_json(AUDIT_LOGS_FILE, logs[:500])  # keep recent 500
    return log_entry

def get_audit_logs(
    record_id: Optional[str] = None,
    district: Optional[str] = None,
    limit: int = 100
) -> List[Dict[str, Any]]:
    if is_mongo and mongo_db is not None:
        query = {}
        if record_id:
            query["record_id"] = record_id
        if district and district.lower() != "all":
            query["district_name"] = {"$regex": f"^{district}$", "$options": "i"}
        docs = list(mongo_db.audit_logs.find(query, {"_id": 0}).sort("timestamp", -1).limit(limit))
        return docs

    logs = _load_json(AUDIT_LOGS_FILE)
    filtered = []
    for l in logs:
        if record_id and l.get("record_id") != record_id:
            continue
        if district and district.lower() != "all":
            if l.get("district_name", "").lower() != district.lower():
                continue
        filtered.append(l)
    return filtered[:limit]

# ----------------- DISTRICTS MASTER -----------------
def get_districts() -> List[Dict[str, Any]]:
    if is_mongo and mongo_db is not None:
        return list(mongo_db.districts.find({}, {"_id": 0}))
    return _load_json(DISTRICTS_FILE)

def update_district_master(
    district_id: str,
    updates: Dict[str, Any],
    user_name: str = "Admin",
    user_role: str = "admin"
) -> Optional[Dict[str, Any]]:
    districts = _load_json(DISTRICTS_FILE)
    target = None
    for d in districts:
        if d.get("district_id") == district_id or d.get("name").lower() == district_id.lower():
            target = d
            diff = {}
            for k, v in updates.items():
                if k in target and target[k] != v:
                    diff[k] = {"from": target[k], "to": v}
                target[k] = v
            break
    
    if target:
        _save_json(DISTRICTS_FILE, districts)
        if is_mongo and mongo_db is not None:
            mongo_db.districts.update_one(
                {"district_id": target["district_id"]},
                {"$set": updates}
            )
        log_change(
            record_id=target["district_id"],
            village_name=f"District Master: {target['name']}",
            district_name=target["name"],
            user_name=user_name,
            user_role=user_role,
            action="District Master Updated",
            details=f"Targets updated for {target['name']}",
            changes=diff
        )
        return target
    return None

# ----------------- REPRESENTATIVES MASTER -----------------
def get_representatives(
    district: Optional[str] = None,
    role: Optional[str] = None
) -> List[Dict[str, Any]]:
    if is_mongo and mongo_db is not None:
        query = {}
        if district and district.lower() != "all":
            query["assigned_district"] = {"$in": [district, "All"]}
        if role and role.lower() != "all":
            query["role"] = role
        return list(mongo_db.representatives.find(query, {"_id": 0}))

    reps = _load_json(REPRESENTATIVES_FILE)
    filtered = []
    for r in reps:
        if district and district.lower() != "all":
            if r.get("assigned_district") != district and r.get("assigned_district") != "All":
                continue
        if role and role.lower() != "all":
            if r.get("role") != role:
                continue
        filtered.append(r)
    return filtered

def add_representative(rep: Dict[str, Any]) -> Dict[str, Any]:
    if "id" not in rep or not rep["id"]:
        rep["id"] = f"rep-{int(datetime.utcnow().timestamp() * 1000)}"
    if is_mongo and mongo_db is not None:
        mongo_db.representatives.insert_one(dict(rep))
        if "_id" in rep:
            del rep["_id"]
    reps = _load_json(REPRESENTATIVES_FILE)
    reps.append(rep)
    _save_json(REPRESENTATIVES_FILE, reps)
    return rep

def update_representative(rep_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    reps = _load_json(REPRESENTATIVES_FILE)
    for idx, r in enumerate(reps):
        if r.get("id") == rep_id:
            reps[idx].update(updates)
            _save_json(REPRESENTATIVES_FILE, reps)
            if is_mongo and mongo_db is not None:
                mongo_db.representatives.update_one({"id": rep_id}, {"$set": updates})
            return reps[idx]
    return None

def delete_representative(rep_id: str) -> bool:
    if is_mongo and mongo_db is not None:
        mongo_db.representatives.delete_one({"id": rep_id})
    reps = _load_json(REPRESENTATIVES_FILE)
    init_len = len(reps)
    reps = [r for r in reps if r.get("id") != rep_id]
    if len(reps) < init_len:
        _save_json(REPRESENTATIVES_FILE, reps)
        return True
    return False

# ----------------- VILLAGES OPERATIONS -----------------
def get_villages(
    district: Optional[str] = None,
    category: Optional[str] = None,
    shapefile_status: Optional[str] = None,
    verification_status: Optional[str] = None,
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
        if verification_status and verification_status.lower() != "all":
            query["verification_status"] = verification_status
        if search and search.strip():
            s = search.strip()
            query["$or"] = [
                {"village_name": {"$regex": s, "$options": "i"}},
                {"mandal_name": {"$regex": s, "$options": "i"}},
                {"remarks": {"$regex": s, "$options": "i"}}
            ]
        return list(mongo_db.villages.find(query, {"_id": 0}))

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
        if verification_status and verification_status.lower() != "all":
            if r.get("verification_status", "") != verification_status:
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

def add_village(
    village: Dict[str, Any],
    user_name: str = "District Rep",
    user_role: str = "district_rep"
) -> Dict[str, Any]:
    if "id" not in village or not village["id"]:
        village["id"] = f"vlg-{int(datetime.utcnow().timestamp() * 1000)}"
    if "updated_at" not in village:
        village["updated_at"] = datetime.utcnow().isoformat()
    if "verification_status" not in village:
        village["verification_status"] = "Pending QC"
    
    if is_mongo and mongo_db is not None:
        mongo_db.villages.insert_one(dict(village))
        if "_id" in village:
            del village["_id"]
    
    records = _load_json(VILLAGES_FILE)
    records.append(village)
    _save_json(VILLAGES_FILE, records)

    # Log creation audit
    log_change(
        record_id=village["id"],
        village_name=village.get("village_name", ""),
        district_name=village.get("district_name", ""),
        user_name=user_name,
        user_role=user_role,
        action="Created",
        details=f"New village survey record submitted by {user_name}",
        changes={
            "extent": {"from": None, "to": village.get("extent_raw")},
            "gt_status": {"from": None, "to": village.get("gt_status")},
            "verification_status": {"from": None, "to": "Pending QC"}
        }
    )
    return village

def update_village(
    village_id: str,
    updates: Dict[str, Any],
    user_name: str = "District Rep",
    user_role: str = "district_rep"
) -> Optional[Dict[str, Any]]:
    existing = get_village(village_id)
    if not existing:
        return None

    diff = {}
    for k, v in updates.items():
        if k in existing and existing[k] != v:
            diff[k] = {"from": existing[k], "to": v}

    updates["updated_at"] = datetime.utcnow().isoformat()
    updates["updated_by"] = user_name

    # If edited by district rep, move back to Pending QC unless already verified
    if user_role == "district_rep" and existing.get("verification_status") == "Returned for Correction":
        updates["verification_status"] = "Pending QC"

    if is_mongo and mongo_db is not None:
        mongo_db.villages.update_one({"id": village_id}, {"$set": updates})
    
    records = _load_json(VILLAGES_FILE)
    for idx, v in enumerate(records):
        if v.get("id") == village_id:
            records[idx].update(updates)
            _save_json(VILLAGES_FILE, records)
            
            # Log audit trail if diff exists
            if diff:
                log_change(
                    record_id=village_id,
                    village_name=records[idx].get("village_name", ""),
                    district_name=records[idx].get("district_name", ""),
                    user_name=user_name,
                    user_role=user_role,
                    action="Updated",
                    details=f"Record updated by {user_name} ({user_role}): {', '.join(diff.keys())}",
                    changes=diff
                )
            return records[idx]
    return None

def verify_village(
    village_id: str,
    status: str,  # "Verified" or "Returned for Correction"
    qc_user: str = "Lead QC Engineer",
    notes: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    updates = {
        "verification_status": status,
        "verified_by": qc_user,
        "verified_at": datetime.utcnow().isoformat(),
        "qc_notes": notes or ""
    }
    if status == "Verified":
        updates["sent_to_cso"] = True
    elif status == "Returned for Correction":
        updates["shapefile_status"] = "Error"

    existing = get_village(village_id)
    if not existing:
        return None

    diff = {
        "verification_status": {"from": existing.get("verification_status"), "to": status},
        "qc_notes": {"from": existing.get("qc_notes"), "to": notes}
    }

    updated = update_village(village_id, updates, user_name=qc_user, user_role="qc_engineer")
    if updated:
        log_change(
            record_id=village_id,
            village_name=updated.get("village_name", ""),
            district_name=updated.get("district_name", ""),
            user_name=qc_user,
            user_role="qc_engineer",
            action="QC Verification: " + status,
            details=f"QC Review completed: {status}. Notes: {notes or 'None'}",
            changes=diff
        )
    return updated

def delete_village(village_id: str, user_name: str = "Admin") -> bool:
    v = get_village(village_id)
    if not v:
        return False

    if is_mongo and mongo_db is not None:
        mongo_db.villages.delete_one({"id": village_id})
    
    records = _load_json(VILLAGES_FILE)
    records = [r for r in records if r.get("id") != village_id]
    _save_json(VILLAGES_FILE, records)

    log_change(
        record_id=village_id,
        village_name=v.get("village_name", ""),
        district_name=v.get("district_name", ""),
        user_name=user_name,
        user_role="admin",
        action="Deleted",
        details=f"Village survey record deleted by {user_name}",
        changes={}
    )
    return True

# ----------------- STATS & EXECUTIVE SUMMARIES -----------------
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

    # Verification workflow counts
    verified_count = [v for v in villages if v.get("verification_status") == "Verified"]
    pending_qc_count = [v for v in villages if v.get("verification_status") == "Pending QC"]
    returned_count = [v for v in villages if v.get("verification_status") == "Returned for Correction"]
    
    total_acres = sum(v.get("extent_acres_float", 0.0) or 0.0 for v in villages)
    
    district_summary = []
    for d in districts:
        d_name = d["name"]
        d_vlgs = [v for v in villages if v.get("district_name", "").lower() == d_name.lower()]
        d_non_cad_gt = [v for v in d_vlgs if v.get("category") == "Non-Cadastral" and v.get("gt_status") == "Completed"]
        d_cad_gt = [v for v in d_vlgs if v.get("category") == "Cadastral" and v.get("gt_status") == "Completed"]
        d_sf_sent = [v for v in d_vlgs if v.get("sent_to_cso") is True or v.get("shapefile_status") == "Completed"]
        d_sf_err = [v for v in d_vlgs if v.get("shapefile_status") == "Error"]
        d_verified = [v for v in d_vlgs if v.get("verification_status") == "Verified"]
        d_acres = sum(v.get("extent_acres_float", 0.0) or 0.0 for v in d_vlgs)
        
        district_summary.append({
            "district": d_name,
            "district_id": d.get("district_id", d_name.lower().replace(" ", "_")),
            "non_cadastral_target": d.get("non_cadastral_target", 0),
            "cadastral_target": d.get("cadastral_target", 0),
            "non_cadastral_gt_done": len(d_non_cad_gt),
            "cadastral_gt_done": len(d_cad_gt),
            "total_gt_done": len(d_non_cad_gt) + len(d_cad_gt),
            "shapefiles_sent": len(d_sf_sent),
            "shapefiles_error": len(d_sf_err),
            "verified_count": len(d_verified),
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
        "verification": {
            "verified": len(verified_count),
            "pending_qc": len(pending_qc_count),
            "returned_for_correction": len(returned_count)
        },
        "total_extent_acres": round(total_acres, 2),
        "districts_summary": district_summary
    }

def get_executive_summary() -> Dict[str, Any]:
    stats = get_dashboard_stats()
    reps = get_representatives()
    logs = get_audit_logs(limit=10)

    # Calculate overall progress rates
    nc_rate = round((stats["gt_completed"]["non_cadastral"] / max(stats["targets"]["non_cadastral"], 1)) * 100, 1)
    cad_rate = round((stats["gt_completed"]["cadastral"] / max(stats["targets"]["cadastral"], 1)) * 100, 1)
    qc_rate = round((stats["verification"]["verified"] / max(stats["gt_completed"]["total"], 1)) * 100, 1)

    # Top performing districts
    ranked_districts = sorted(
        stats["districts_summary"],
        key=lambda d: (d["total_gt_done"], -d["shapefiles_error"]),
        reverse=True
    )

    return {
        "statewide_progress": {
            "non_cadastral_completion_pct": nc_rate,
            "cadastral_completion_pct": cad_rate,
            "qc_verification_pct": qc_rate,
            "total_surveyed_acres": stats["total_extent_acres"],
            "shapefile_readiness_pct": round((stats["shapefiles"]["completed"] / max(stats["gt_completed"]["total"], 1)) * 100, 1)
        },
        "top_performing_districts": ranked_districts[:5],
        "districts_needing_attention": [d for d in ranked_districts if d["shapefiles_error"] > 0][:5],
        "active_representatives_count": len([r for r in reps if r.get("status") == "Active"]),
        "recent_audit_trail": logs
    }

def authenticate_user(username: str, password: str) -> Optional[Dict[str, Any]]:
    users = _load_json(USERS_FILE)
    user = next((u for u in users if u.get("username") == username), None)
    if user and user.get("password") == password:
        user_safe = dict(user)
        if "password" in user_safe:
            del user_safe["password"]
        return user_safe
    return None

init_db()
