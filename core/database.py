import math
import os
import re
import json
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
DISTRICTS_FILE = os.path.join(DATA_DIR, "districts.json")
MANDALS_FILE = os.path.join(DATA_DIR, "mandals.json")
VILLAGES_FILE = os.path.join(DATA_DIR, "villages.json")
USERS_FILE = os.path.join(DATA_DIR, "users.json")
REPRESENTATIVES_FILE = os.path.join(DATA_DIR, "representatives.json")
AUDIT_LOGS_FILE = os.path.join(DATA_DIR, "audit_logs.json")
MASTER_VILLAGES_FILE = os.path.join(DATA_DIR, "master_villages.json")
MASTER_MANDALS_FILE = os.path.join(DATA_DIR, "master_mandals.json")

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
            (MANDALS_FILE, "mandals"),
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

def get_district(district_id: str) -> Optional[Dict[str, Any]]:
    districts = get_districts()
    d_low = district_id.lower().strip()
    return next((d for d in districts if d.get("district_id", "").lower() == d_low or d.get("name", "").lower() == d_low), None)

def add_district(
    data: Dict[str, Any],
    user_name: str = "Admin",
    user_role: str = "admin"
) -> Dict[str, Any]:
    districts = _load_json(DISTRICTS_FILE)
    name = data.get("name", "").strip()
    if not name:
        raise ValueError("District name cannot be empty.")
    
    # Check for duplicate
    if any(d.get("name", "").lower() == name.lower() for d in districts):
        raise ValueError(f"District '{name}' already exists in master records.")
    
    district_id = data.get("district_id") or name.lower().replace(" ", "_")
    district_record = {
        "district_id": district_id,
        "name": name,
        "non_cadastral_target": int(data.get("non_cadastral_target", 0) or 0),
        "cadastral_target": int(data.get("cadastral_target", 70) or 70),
        "status": data.get("status", "Active")
    }
    
    if is_mongo and mongo_db is not None:
        mongo_db.districts.insert_one(dict(district_record))
        if "_id" in district_record:
            del district_record["_id"]
            
    districts.append(district_record)
    _save_json(DISTRICTS_FILE, districts)
    
    log_change(
        record_id=district_record["district_id"],
        village_name=f"District Master: {district_record['name']}",
        district_name=district_record["name"],
        user_name=user_name,
        user_role=user_role,
        action="District Master Created",
        details=f"New district '{district_record['name']}' registered by {user_name}",
        changes={
            "non_cadastral_target": {"from": None, "to": district_record["non_cadastral_target"]},
            "cadastral_target": {"from": None, "to": district_record["cadastral_target"]}
        }
    )
    return district_record

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

def delete_district(
    district_id: str,
    user_name: str = "Admin",
    user_role: str = "admin"
) -> bool:
    districts = _load_json(DISTRICTS_FILE)
    target = next((d for d in districts if d.get("district_id") == district_id or d.get("name").lower() == district_id.lower()), None)
    if not target:
        return False
    
    # Dependency check: check if any mandals or villages are linked
    mandals = get_mandals(district=target["name"])
    villages = get_villages(district=target["name"])
    if mandals or villages:
        raise ValueError(f"Cannot delete district '{target['name']}'. It contains {len(mandals)} mandals and {len(villages)} village survey records. Deactivate it instead.")
    
    if is_mongo and mongo_db is not None:
        mongo_db.districts.delete_one({"district_id": target["district_id"]})
    
    districts = [d for d in districts if d.get("district_id") != target["district_id"]]
    _save_json(DISTRICTS_FILE, districts)
    
    log_change(
        record_id=target["district_id"],
        village_name=f"District Master: {target['name']}",
        district_name=target["name"],
        user_name=user_name,
        user_role=user_role,
        action="District Master Deleted",
        details=f"District '{target['name']}' removed from master registry by {user_name}",
        changes={}
    )
    return True

# ----------------- MANDALS MASTER -----------------
def get_mandals(
    district: Optional[str] = None,
    search: Optional[str] = None
) -> List[Dict[str, Any]]:
    if is_mongo and mongo_db is not None:
        query = {}
        if district and district.lower() != "all":
            query["district_name"] = {"$regex": f"^{district}$", "$options": "i"}
        if search and search.strip():
            s = search.strip()
            query["$or"] = [
                {"mandal_name": {"$regex": s, "$options": "i"}},
                {"mandal_name_telugu": {"$regex": s, "$options": "i"}}
            ]
        return list(mongo_db.mandals.find(query, {"_id": 0}))

    mandals = _load_json(MANDALS_FILE)
    filtered = []
    for m in mandals:
        if district and district.lower() != "all":
            if m.get("district_name", "").lower() != district.lower():
                continue
        if search and search.strip():
            s = search.strip().lower()
            m_name = m.get("mandal_name", "").lower()
            m_tel = m.get("mandal_name_telugu", "").lower()
            if s not in m_name and s not in m_tel:
                continue
        filtered.append(m)
    return filtered

def get_mandal(mandal_id: str) -> Optional[Dict[str, Any]]:
    if is_mongo and mongo_db is not None:
        return mongo_db.mandals.find_one({"id": mandal_id}, {"_id": 0})
    for m in _load_json(MANDALS_FILE):
        if m.get("id") == mandal_id:
            return m
    return None

def add_mandal(
    data: Dict[str, Any],
    user_name: str = "Admin",
    user_role: str = "admin"
) -> Dict[str, Any]:
    district_name = data.get("district_name", "").strip()
    mandal_name = data.get("mandal_name", "").strip()
    if not district_name or not mandal_name:
        raise ValueError("District name and Mandal name are required.")

    # Validate parent district exists
    district_info = get_district(district_name)
    if not district_info:
        raise ValueError(f"Parent district '{district_name}' does not exist in master records.")

    mandals = _load_json(MANDALS_FILE)
    # Check duplicate in same district
    for m in mandals:
        if m.get("district_name", "").lower() == district_name.lower() and m.get("mandal_name", "").lower() == mandal_name.lower():
            raise ValueError(f"Mandal '{mandal_name}' already exists under district '{district_name}'.")

    mandal_id = data.get("id") or f"mnd-{int(datetime.utcnow().timestamp() * 1000)}"
    mandal_record = {
        "id": mandal_id,
        "mandal_name": mandal_name,
        "mandal_name_telugu": data.get("mandal_name_telugu", "").strip(),
        "district_name": district_info["name"],
        "district_id": district_info.get("district_id", district_name.lower().replace(" ", "_")),
        "status": data.get("status", "Active"),
        "created_at": datetime.utcnow().isoformat()
    }

    if is_mongo and mongo_db is not None:
        mongo_db.mandals.insert_one(dict(mandal_record))
        if "_id" in mandal_record:
            del mandal_record["_id"]

    mandals.append(mandal_record)
    _save_json(MANDALS_FILE, mandals)

    log_change(
        record_id=mandal_record["id"],
        village_name=f"Mandal Master: {mandal_record['mandal_name']}",
        district_name=mandal_record["district_name"],
        user_name=user_name,
        user_role=user_role,
        action="Mandal Master Created",
        details=f"New mandal '{mandal_record['mandal_name']}' added under {mandal_record['district_name']} by {user_name}",
        changes={
            "mandal_name": {"from": None, "to": mandal_record["mandal_name"]},
            "district_name": {"from": None, "to": mandal_record["district_name"]}
        }
    )
    return mandal_record

def update_mandal(
    mandal_id: str,
    updates: Dict[str, Any],
    user_name: str = "Admin",
    user_role: str = "admin"
) -> Optional[Dict[str, Any]]:
    mandals = _load_json(MANDALS_FILE)
    target = None
    for idx, m in enumerate(mandals):
        if m.get("id") == mandal_id:
            target = m
            diff = {}
            for k, v in updates.items():
                if k in target and target[k] != v:
                    diff[k] = {"from": target[k], "to": v}
                target[k] = v
            mandals[idx] = target
            break

    if target:
        _save_json(MANDALS_FILE, mandals)
        if is_mongo and mongo_db is not None:
            mongo_db.mandals.update_one({"id": mandal_id}, {"$set": updates})

        if diff:
            log_change(
                record_id=mandal_id,
                village_name=f"Mandal Master: {target['mandal_name']}",
                district_name=target["district_name"],
                user_name=user_name,
                user_role=user_role,
                action="Mandal Master Updated",
                details=f"Mandal '{target['mandal_name']}' updated by {user_name}",
                changes=diff
            )
        return target
    return None

def delete_mandal(
    mandal_id: str,
    user_name: str = "Admin",
    user_role: str = "admin"
) -> bool:
    mandals = _load_json(MANDALS_FILE)
    target = next((m for m in mandals if m.get("id") == mandal_id), None)
    if not target:
        return False

    # Dependency check: check if any villages belong to this mandal
    villages = get_villages(district=target["district_name"])
    m_villages = [v for v in villages if v.get("mandal_name", "").lower() == target["mandal_name"].lower()]
    if m_villages:
        raise ValueError(f"Cannot delete mandal '{target['mandal_name']}'. It contains {len(m_villages)} village survey records. Deactivate it instead.")

    if is_mongo and mongo_db is not None:
        mongo_db.mandals.delete_one({"id": mandal_id})

    mandals = [m for m in mandals if m.get("id") != mandal_id]
    _save_json(MANDALS_FILE, mandals)

    log_change(
        record_id=mandal_id,
        village_name=f"Mandal Master: {target['mandal_name']}",
        district_name=target["district_name"],
        user_name=user_name,
        user_role=user_role,
        action="Mandal Master Deleted",
        details=f"Mandal '{target['mandal_name']}' removed from master registry by {user_name}",
        changes={}
    )
    return True

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

import hmac
import hashlib
import base64
import time

AUTH_SECRET_KEY = os.environ.get("AUTH_SECRET_KEY", "resurvey-monitoring-portal-auth-secret-2026")

def create_auth_token(user_data: Dict[str, Any], expires_in: int = 86400 * 7) -> str:
    payload = {
        "username": user_data.get("username"),
        "name": user_data.get("name"),
        "role": user_data.get("role"),
        "district": user_data.get("district", "All"),
        "designation": user_data.get("designation", ""),
        "exp": int(time.time()) + expires_in
    }
    data_b64 = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()
    sig = hmac.new(AUTH_SECRET_KEY.encode(), data_b64.encode(), hashlib.sha256).hexdigest()
    return f"{data_b64}.{sig}"

def verify_auth_token(token: str) -> Optional[Dict[str, Any]]:
    if not token or "." not in token:
        return None
    try:
        data_b64, sig = token.strip().split(".")
        expected_sig = hmac.new(AUTH_SECRET_KEY.encode(), data_b64.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected_sig):
            return None
        payload = json.loads(base64.urlsafe_b64decode(data_b64.encode()).decode())
        if payload.get("exp", 0) < time.time():
            return None
        return payload
    except Exception:
        return None

def authenticate_user(username: str, password: str) -> Optional[Dict[str, Any]]:
    users = _load_json(USERS_FILE)
    u_lower = username.lower().strip()
    user = next((u for u in users if u.get("username", "").lower() == u_lower), None)
    
    # STRICT CREDENTIAL VERIFICATION: Exact password match against stored user record
    if user:
        if user.get("status", "Active") == "Inactive":
            return None
        
        stored_pwd = user.get("password")
        if stored_pwd and password == stored_pwd:
            user_safe = dict(user)
            if "password" in user_safe:
                del user_safe["password"]
            return user_safe
    return None

def get_users(
    district: Optional[str] = None,
    role: Optional[str] = None,
    search: Optional[str] = None,
    include_passwords: bool = True
) -> List[Dict[str, Any]]:
    users = _load_json(USERS_FILE)
    result = []
    
    search_lower = search.lower().strip() if search else None
    district_lower = district.lower().strip() if district and district.lower() != "all" else None
    role_lower = role.lower().strip() if role and role.lower() != "all" else None

    for u in users:
        if district_lower:
            u_dist = (u.get("district") or "").lower()
            if u_dist != district_lower:
                continue
        if role_lower:
            u_role = (u.get("role") or "").lower()
            if u_role != role_lower:
                continue
        if search_lower:
            name = (u.get("name") or "").lower()
            uname = (u.get("username") or "").lower()
            desig = (u.get("designation") or "").lower()
            if search_lower not in name and search_lower not in uname and search_lower not in desig:
                continue

        safe_u = dict(u)
        if not include_passwords and "password" in safe_u:
            del safe_u["password"]
        if "status" not in safe_u:
            safe_u["status"] = "Active"
        if "is_default_password" not in safe_u:
            safe_u["is_default_password"] = True
        result.append(safe_u)

    return sorted(result, key=lambda x: (x.get("district", ""), x.get("username", "")))

def get_user(username: str) -> Optional[Dict[str, Any]]:
    users = _load_json(USERS_FILE)
    u_lower = username.lower().strip()
    user = next((u for u in users if u.get("username", "").lower() == u_lower), None)
    if user:
        safe_u = dict(user)
        if "password" in safe_u:
            del safe_u["password"]
        if "status" not in safe_u:
            safe_u["status"] = "Active"
        if "is_default_password" not in safe_u:
            safe_u["is_default_password"] = True
        return safe_u
    return None

def add_user(user_data: Dict[str, Any], admin_name: str, admin_role: str) -> Dict[str, Any]:
    username = (user_data.get("username") or "").lower().strip()
    if not username or not re.match(r"^[a-z0-9_]{3,30}$", username):
        raise ValueError("Username must be 3-30 characters with lowercase letters, digits, or underscores only.")
    
    users = _load_json(USERS_FILE)
    if any(u.get("username", "").lower() == username for u in users):
        raise ValueError(f"User with username '{username}' already exists.")

    default_password = user_data.get("default_password") or "Welcome@2026"
    
    new_user = {
        "username": username,
        "password": default_password,
        "name": user_data.get("name", "").strip(),
        "role": user_data.get("role", "district_rep"),
        "district": user_data.get("district", "All"),
        "designation": user_data.get("designation", "").strip(),
        "phone": user_data.get("phone", "").strip(),
        "email": user_data.get("email", "").strip(),
        "status": user_data.get("status", "Active"),
        "is_default_password": True,
        "created_at": datetime.utcnow().isoformat(),
        "created_by": admin_name,
        "password_updated_at": None
    }

    if is_mongo and mongo_db is not None:
        mongo_db.users.insert_one(dict(new_user))
        if "_id" in new_user:
            del new_user["_id"]

    users.append(new_user)
    _save_json(USERS_FILE, users)

    # Log to audit trail
    log_change(
        record_id=f"user-{username}",
        village_name=f"Account: {username}",
        district_name=new_user["district"],
        user_name=admin_name,
        user_role=admin_role,
        action="User Account Created",
        details=f"Created officer account '{username}' (Role: {new_user['role']}, District: {new_user['district']}) with default password.",
        changes={"role": new_user["role"], "district": new_user["district"], "status": new_user["status"]}
    )

    safe_u = dict(new_user)
    del safe_u["password"]
    safe_u["initial_password"] = default_password
    return safe_u

def update_user(username: str, updates: Dict[str, Any], admin_name: str, admin_role: str) -> Optional[Dict[str, Any]]:
    users = _load_json(USERS_FILE)
    u_lower = username.lower().strip()
    
    target_idx = next((i for i, u in enumerate(users) if u.get("username", "").lower() == u_lower), None)
    if target_idx is None:
        return None

    # Support username rename if new_username is specified
    new_username = (updates.get("new_username") or updates.get("username") or "").lower().strip()
    old_username = users[target_idx]["username"]
    final_username = old_username

    if new_username and new_username != u_lower:
        if not re.match(r"^[a-z0-9_]{3,30}$", new_username):
            raise ValueError("Username must be 3-30 characters with lowercase letters, digits, or underscores only.")
        if any(u.get("username", "").lower() == new_username for i, u in enumerate(users) if i != target_idx):
            raise ValueError(f"Username '{new_username}' is already taken.")
        users[target_idx]["username"] = new_username
        final_username = new_username

    allowed_fields = ["name", "role", "district", "designation", "phone", "email", "status"]
    filtered_updates = {k: v for k, v in updates.items() if k in allowed_fields and v is not None}
    filtered_updates["updated_at"] = datetime.utcnow().isoformat()
    
    users[target_idx].update(filtered_updates)
    _save_json(USERS_FILE, users)
    
    if is_mongo and mongo_db is not None:
        mongo_db.users.update_one({"username": u_lower}, {"$set": {**filtered_updates, "username": final_username}})
    
    log_change(
        record_id=f"user-{final_username}",
        village_name=f"Account: {final_username}",
        district_name=users[target_idx].get("district", "All"),
        user_name=admin_name,
        user_role=admin_role,
        action="User Account Updated",
        details=f"Admin '{admin_name}' updated details for user '{old_username}' -> '{final_username}': {filtered_updates}",
        changes={**filtered_updates, "username": final_username}
    )
    
    safe_u = dict(users[target_idx])
    return safe_u

def update_user_profile(current_username: str, updates: Dict[str, Any]) -> Dict[str, Any]:
    users = _load_json(USERS_FILE)
    u_lower = current_username.lower().strip()
    
    target_idx = next((i for i, u in enumerate(users) if u.get("username", "").lower() == u_lower), None)
    if target_idx is None:
        raise ValueError("User account not found.")

    new_username = (updates.get("username") or updates.get("new_username") or "").lower().strip()
    old_username = users[target_idx]["username"]
    final_username = old_username

    if new_username and new_username != u_lower:
        if not re.match(r"^[a-z0-9_]{3,30}$", new_username):
            raise ValueError("Username must be 3-30 characters with lowercase letters, digits, or underscores only.")
        if any(u.get("username", "").lower() == new_username for i, u in enumerate(users) if i != target_idx):
            raise ValueError(f"Username '{new_username}' is already taken. Please choose another username.")
        users[target_idx]["username"] = new_username
        final_username = new_username

    # Update personal details: name, phone, email, designation
    for field in ["name", "phone", "email", "designation"]:
        if field in updates and updates[field] is not None:
            users[target_idx][field] = str(updates[field]).strip()

    users[target_idx]["profile_updated_at"] = datetime.utcnow().isoformat()
    _save_json(USERS_FILE, users)

    if is_mongo and mongo_db is not None:
        mongo_db.users.update_one(
            {"username": u_lower},
            {"$set": {
                "username": final_username,
                "name": users[target_idx].get("name", ""),
                "phone": users[target_idx].get("phone", ""),
                "email": users[target_idx].get("email", ""),
                "designation": users[target_idx].get("designation", ""),
                "profile_updated_at": users[target_idx]["profile_updated_at"]
            }}
        )

    log_change(
        record_id=f"user-{final_username}",
        village_name=f"Account: {final_username}",
        district_name=users[target_idx].get("district", "All"),
        user_name=users[target_idx].get("name", final_username),
        user_role=users[target_idx].get("role", "user"),
        action="User Profile Updated",
        details=f"Officer updated personal profile: ID={final_username}, Name={users[target_idx].get('name')}, Contact={users[target_idx].get('phone')}",
        changes={"old_username": old_username, "new_username": final_username, "name": users[target_idx].get("name")}
    )

    safe_u = dict(users[target_idx])
    return safe_u

def reset_user_password(username: str, new_password: str, admin_name: str, admin_role: str) -> bool:
    if not new_password or len(new_password.strip()) < 4:
        raise ValueError("Password must be at least 4 characters long.")

    users = _load_json(USERS_FILE)
    u_lower = username.lower().strip()
    
    for idx, u in enumerate(users):
        if u.get("username", "").lower() == u_lower:
            users[idx]["password"] = new_password.strip()
            users[idx]["is_default_password"] = True
            users[idx]["password_updated_at"] = datetime.utcnow().isoformat()
            users[idx]["status"] = "Active"
            
            _save_json(USERS_FILE, users)
            if is_mongo and mongo_db is not None:
                mongo_db.users.update_one(
                    {"username": u_lower},
                    {"$set": {
                        "password": new_password.strip(),
                        "is_default_password": True,
                        "password_updated_at": users[idx]["password_updated_at"],
                        "status": "Active"
                    }}
                )
            
            log_change(
                record_id=f"user-{username}",
                village_name=f"Account: {username}",
                district_name=users[idx].get("district", "All"),
                user_name=admin_name,
                user_role=admin_role,
                action="Password Reset by Admin",
                details=f"Administrator '{admin_name}' reset password for user '{username}' to temporary default.",
                changes={"is_default_password": True}
            )
            return True
    return False

def change_user_password(username: str, current_password: str, new_password: str) -> bool:
    if not new_password or len(new_password.strip()) < 4:
        raise ValueError("New password must be at least 4 characters long.")

    users = _load_json(USERS_FILE)
    u_lower = username.lower().strip()
    
    for idx, u in enumerate(users):
        if u.get("username", "").lower() == u_lower:
            stored_pwd = u.get("password")
            if stored_pwd != current_password:
                raise ValueError("Current password is incorrect.")
            
            users[idx]["password"] = new_password.strip()
            users[idx]["is_default_password"] = False
            users[idx]["password_updated_at"] = datetime.utcnow().isoformat()
            
            _save_json(USERS_FILE, users)
            if is_mongo and mongo_db is not None:
                mongo_db.users.update_one(
                    {"username": u_lower},
                    {"$set": {
                        "password": new_password.strip(),
                        "is_default_password": False,
                        "password_updated_at": users[idx]["password_updated_at"]
                    }}
                )
            
            log_change(
                record_id=f"user-{username}",
                village_name=f"Account: {username}",
                district_name=users[idx].get("district", "All"),
                user_name=users[idx].get("name", username),
                user_role=users[idx].get("role", "user"),
                action="Password Changed by User",
                details=f"User '{username}' successfully updated their personal account password.",
                changes={"is_default_password": False}
            )
            return True
    raise ValueError("User not found.")

def delete_user(username: str, admin_name: str, admin_role: str) -> bool:
    u_lower = username.lower().strip()
    if u_lower in ["admin", admin_name.lower()]:
        raise ValueError("Cannot delete your own active administrator account.")
        
    users = _load_json(USERS_FILE)
    init_len = len(users)
    target_user = next((u for u in users if u.get("username", "").lower() == u_lower), None)
    if not target_user:
        return False

    users = [u for u in users if u.get("username", "").lower() != u_lower]
    if len(users) < init_len:
        _save_json(USERS_FILE, users)
        if is_mongo and mongo_db is not None:
            mongo_db.users.delete_one({"username": u_lower})

        log_change(
            record_id=f"user-{username}",
            village_name=f"Account: {username}",
            district_name=target_user.get("district", "All"),
            user_name=admin_name,
            user_role=admin_role,
            action="User Account Deleted",
            details=f"Administrator '{admin_name}' deleted user account '{username}'.",
            changes={"deleted_user": username}
        )
        return True
    return False


# ----------------- STATE TERRITORIAL MASTER REGISTRY (10,888 VILLAGES / 604 MANDALS) -----------------
def get_master_villages(
    district: Optional[str] = None,
    mandal: Optional[str] = None,
    category: Optional[str] = None,
    is_picked: Optional[bool] = None,
    search: Optional[str] = None,
    page: int = 1,
    limit: int = 50
) -> Dict[str, Any]:
    all_villages = _load_json(MASTER_VILLAGES_FILE)
    filtered = all_villages

    d_clean = district.lower().strip() if district and district.lower() != "all" else None
    m_clean = mandal.lower().strip() if mandal and mandal.lower() != "all" else None
    c_clean = category.lower().strip() if category and category.lower() != "all" else None
    s_clean = search.lower().strip() if search else None

    if d_clean:
        filtered = [v for v in filtered if v.get("district_name", "").lower() == d_clean]
    if m_clean:
        filtered = [v for v in filtered if v.get("mandal_name", "").lower() == m_clean]
    if c_clean:
        filtered = [v for v in filtered if v.get("category", "").lower() == c_clean]
    if is_picked is not None:
        filtered = [v for v in filtered if v.get("is_picked_for_resurvey") == is_picked]
    if s_clean:
        filtered = [
            v for v in filtered
            if s_clean in v.get("village_name", "").lower()
            or s_clean in v.get("mandal_name", "").lower()
            or s_clean in v.get("district_name", "").lower()
        ]

    total_matches = len(filtered)
    total_pages = max(1, math.ceil(total_matches / limit)) if limit > 0 else 1
    safe_page = max(1, min(page, total_pages))
    offset = (safe_page - 1) * limit
    slice_data = filtered[offset : offset + limit]

    return {
        "data": slice_data,
        "total": total_matches,
        "page": safe_page,
        "limit": limit,
        "total_pages": total_pages,
        "summary": {
            "total_state_villages": len(all_villages),
            "total_non_cadastral": 373,
            "total_cadastral": 10515,
            "total_picked_for_resurvey": 2609,
            "total_non_survey_phase": 8279
        }
    }

def get_master_mandals(
    district: Optional[str] = None,
    search: Optional[str] = None
) -> List[Dict[str, Any]]:
    mandals = _load_json(MASTER_MANDALS_FILE)
    filtered = mandals
    d_clean = district.lower().strip() if district and district.lower() != "all" else None
    s_clean = search.lower().strip() if search else None

    if d_clean:
        filtered = [m for m in filtered if m.get("district_name", "").lower() == d_clean]
    if s_clean:
        filtered = [
            m for m in filtered
            if s_clean in m.get("mandal_name", "").lower()
            or s_clean in m.get("district_name", "").lower()
        ]
    return sorted(filtered, key=lambda x: (x.get("district_name", ""), x.get("mandal_name", "")))

# ----------------- EXTENSIBLE MASTER CATALOG -----------------
def get_master_catalog() -> Dict[str, Any]:
    districts = get_districts()
    mandals = get_mandals()
    villages = get_villages()
    reps = get_representatives()

    return {
        "active_entities": [
            {
                "entity_key": "districts",
                "name": "Districts Master",
                "icon": "fa-landmark",
                "count": len(districts),
                "status": "Active",
                "description": "Administrative district territorial records with Non-Cadastral and Cadastral baseline targets.",
                "fields": ["district_id", "name", "non_cadastral_target", "cadastral_target", "status"]
            },
            {
                "entity_key": "mandals",
                "name": "State Mandals Registry",
                "icon": "fa-building-columns",
                "count": 604,
                "status": "Active",
                "description": "Comprehensive statewide directory of all 604 administrative mandals mapped to their 32 parent districts.",
                "fields": ["id", "mandal_name", "district_name", "total_villages", "resurvey_villages_count", "status"]
            },
            {
                "entity_key": "villages",
                "name": "Revenue Villages Registry",
                "icon": "fa-tree-city",
                "count": 10888,
                "status": "Active",
                "description": "Complete state territorial registry of 10,888 revenue villages (373 Non-Cadastral + 10,515 Cadastral; 2,609 Picked for Resurvey).",
                "fields": ["id", "village_name", "mandal_name", "district_name", "category", "is_picked_for_resurvey", "resurvey_phase"]
            },
            {
                "entity_key": "representatives",
                "name": "Field Officers & QC Master",
                "icon": "fa-users-gear",
                "count": len(reps),
                "status": "Active",
                "description": "Designated field officers, district data entry representatives, and central office verification engineers.",
                "fields": ["id", "name", "role", "designation", "assigned_district", "phone", "email", "status"]
            },
            {
                "entity_key": "users",
                "name": "User Accounts & Officers",
                "icon": "fa-user-lock",
                "count": len(_load_json(USERS_FILE)),
                "status": "Active",
                "description": "Authenticated officer credentials, role permissions, district assignments, and password governance.",
                "fields": ["username", "name", "role", "district", "designation", "status", "is_default_password"]
            }
        ],
        "extensible_entities": [
            {
                "entity_key": "survey_agencies",
                "name": "Survey Agencies & Vendors Master",
                "icon": "fa-briefcase",
                "phase": "Phase 2 Ready",
                "status": "Configurable",
                "description": "Empaneled drone flight agencies, ground truthing vendors, GIS processing consortiums, and contact points.",
                "proposed_schema": [
                    {"name": "agency_id", "type": "String", "required": True},
                    {"name": "agency_name", "type": "String", "required": True},
                    {"name": "registration_no", "type": "String", "required": True},
                    {"name": "gstin", "type": "String", "required": False},
                    {"name": "empaneled_districts", "type": "Array<String>", "required": True},
                    {"name": "allocated_villages_count", "type": "Integer", "required": False},
                    {"name": "primary_contact_person", "type": "String", "required": True},
                    {"name": "contact_phone", "type": "String", "required": True},
                    {"name": "status", "type": "Enum (Active/Suspended/Completed)", "required": True}
                ]
            },
            {
                "entity_key": "survey_equipment",
                "name": "Survey Instruments & Drone Master",
                "icon": "fa-satellite-dish",
                "phase": "Phase 2 Ready",
                "status": "Configurable",
                "description": "Master registry of DGPS base/rover units, Electronic Total Stations (ETS), and DGCA-certified drones.",
                "proposed_schema": [
                    {"name": "equipment_id", "type": "String", "required": True},
                    {"name": "equipment_type", "type": "Enum (DGPS Base / DGPS Rover / ETS / Survey Drone)", "required": True},
                    {"name": "make_model", "type": "String", "required": True},
                    {"name": "serial_number", "type": "String", "required": True},
                    {"name": "dgca_uin", "type": "String", "required": False},
                    {"name": "calibration_expiry", "type": "Date", "required": True},
                    {"name": "assigned_district", "type": "String", "required": True},
                    {"name": "status", "type": "Enum (Operational/Under Maintenance/Decommissioned)", "required": True}
                ]
            },
            {
                "entity_key": "revenue_divisions",
                "name": "Revenue Divisions Master",
                "icon": "fa-sitemap",
                "phase": "Phase 2 Ready",
                "status": "Configurable",
                "description": "Sub-collector and Revenue Divisional Officer (RDO) jurisdictions grouping mandals within districts.",
                "proposed_schema": [
                    {"name": "division_id", "type": "String", "required": True},
                    {"name": "division_name", "type": "String", "required": True},
                    {"name": "district_name", "type": "String", "required": True},
                    {"name": "headquarters", "type": "String", "required": True},
                    {"name": "rdo_officer_name", "type": "String", "required": False},
                    {"name": "status", "type": "Enum (Active/Inactive)", "required": True}
                ]
            },
            {
                "entity_key": "gazette_notifications",
                "name": "Statutory Survey Gazette Master",
                "icon": "fa-scroll",
                "phase": "Phase 2 Ready",
                "status": "Configurable",
                "description": "Statutory Section 6(1) and Section 13 survey notifications, Gazette notification dates, and GO references.",
                "proposed_schema": [
                    {"name": "notification_id", "type": "String", "required": True},
                    {"name": "go_number", "type": "String", "required": True},
                    {"name": "notification_date", "type": "Date", "required": True},
                    {"name": "gazette_reference_no", "type": "String", "required": True},
                    {"name": "district_name", "type": "String", "required": True},
                    {"name": "applicable_category", "type": "Enum (Cadastral/Non-Cadastral)", "required": True},
                    {"name": "status", "type": "Enum (Draft/Gazetted/Superseded)", "required": True}
                ]
            }
        ]
    }

init_db()

