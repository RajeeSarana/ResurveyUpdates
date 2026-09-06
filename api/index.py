import os
import sys
from typing import Optional, Dict, Any, List
from fastapi import FastAPI, HTTPException, Depends, Query, status, APIRouter, Header
from fastapi.responses import StreamingResponse, FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from core.database import (
    get_db_status,
    get_districts,
    get_district,
    add_district,
    update_district_master,
    delete_district,
    get_mandals,
    get_mandal,
    add_mandal,
    update_mandal,
    delete_mandal,
    get_villages,
    get_village,
    add_village,
    update_village,
    verify_village,
    delete_village,
    get_dashboard_stats,
    get_executive_summary,
    get_audit_logs,
    get_representatives,
    add_representative,
    update_representative,
    delete_representative,
    get_master_catalog,
    get_master_villages,
    get_master_mandals,
    authenticate_user,
    create_auth_token,
    verify_auth_token,
    get_users,
    get_user,
    add_user,
    update_user,
    update_user_profile,
    reset_user_password,
    change_user_password,
    delete_user
)
from core.export_service import generate_resurvey_excel

app = FastAPI(
    title="Resurvey Updates Monitoring API",
    description="Portal for Cadastral & Non-Cadastral Village Progress Tracking",
    version="2.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Schemas
class LoginRequest(BaseModel):
    username: str
    password: str

class DistrictCreateRequest(BaseModel):
    name: str
    district_id: Optional[str] = None
    non_cadastral_target: Optional[int] = 0
    cadastral_target: Optional[int] = 70
    status: Optional[str] = "Active"

class DistrictUpdateRequest(BaseModel):
    non_cadastral_target: Optional[int] = None
    cadastral_target: Optional[int] = None
    status: Optional[str] = None
    updated_by: Optional[str] = "Admin"
    user_role: Optional[str] = "admin"

class MandalCreateRequest(BaseModel):
    district_name: str
    mandal_name: str
    mandal_name_telugu: Optional[str] = ""
    status: Optional[str] = "Active"

class MandalUpdateRequest(BaseModel):
    mandal_name: Optional[str] = None
    mandal_name_telugu: Optional[str] = None
    district_name: Optional[str] = None
    status: Optional[str] = None

class VillageCreateRequest(BaseModel):
    district_name: str
    category: str
    village_name: str
    village_name_telugu: Optional[str] = ""
    mandal_name: str
    mandal_id: Optional[str] = None
    extent_raw: Optional[str] = ""
    gt_status: Optional[str] = "Completed"
    shapefile_status: Optional[str] = "Pending"
    sent_to_cso: Optional[bool] = False
    workflow_stage: Optional[str] = "Ground Truthing"
    remarks: Optional[str] = ""
    updated_by: Optional[str] = "District Rep"
    user_role: Optional[str] = "district_rep"

class VillageUpdateRequest(BaseModel):
    category: Optional[str] = None
    village_name: Optional[str] = None
    village_name_telugu: Optional[str] = None
    mandal_name: Optional[str] = None
    mandal_id: Optional[str] = None
    extent_raw: Optional[str] = None
    gt_status: Optional[str] = None
    shapefile_status: Optional[str] = None
    sent_to_cso: Optional[bool] = None
    workflow_stage: Optional[str] = None
    remarks: Optional[str] = None
    updated_by: Optional[str] = "District Rep"
    user_role: Optional[str] = "district_rep"

class VerificationRequest(BaseModel):
    status: str  # "Verified" or "Returned for Correction"
    qc_user: Optional[str] = "Lead QC Engineer"
    notes: Optional[str] = ""

class UserCreateRequest(BaseModel):
    username: str
    name: str
    role: str = "district_rep"
    district: str = "All"
    designation: Optional[str] = ""
    phone: Optional[str] = ""
    email: Optional[str] = ""
    default_password: Optional[str] = "Welcome@2026"
    status: Optional[str] = "Active"

class UserUpdateRequest(BaseModel):
    new_username: Optional[str] = None
    name: Optional[str] = None
    role: Optional[str] = None
    district: Optional[str] = None
    designation: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    status: Optional[str] = None

class UserProfileUpdateRequest(BaseModel):
    username: Optional[str] = None
    name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    designation: Optional[str] = None

class AdminPasswordResetRequest(BaseModel):
    new_password: str

class UserChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str
    confirm_password: str

class RepresentativeCreateRequest(BaseModel):
    name: str
    role: str  # "district_rep", "qc_engineer", "executive", "admin"
    designation: str
    assigned_district: str
    phone: Optional[str] = ""
    email: Optional[str] = ""
    status: Optional[str] = "Active"

class RepresentativeUpdateRequest(BaseModel):
    name: Optional[str] = None
    role: Optional[str] = None
    designation: Optional[str] = None
    assigned_district: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    status: Optional[str] = None

class DistrictUpdateRequest(BaseModel):
    non_cadastral_target: Optional[int] = None
    cadastral_target: Optional[int] = None
    updated_by: Optional[str] = "Admin"
    user_role: Optional[str] = "admin"

def calculate_acres(val: Optional[str]) -> float:
    if not val or not str(val).strip():
        return 0.0
    s = str(val).strip()
    try:
        if "-" in s:
            parts = s.split("-")
            ac = float(parts[0]) if parts[0] else 0.0
            gt = float(parts[1]) if len(parts) > 1 and parts[1] else 0.0
            return round(ac + (gt / 40.0), 3)
        elif "." in s:
            parts = s.split(".")
            ac = float(parts[0]) if parts[0] else 0.0
            gt = float(parts[1]) if len(parts) > 1 and parts[1] else 0.0
            if gt < 40:
                return round(ac + (gt / 40.0), 3)
            return round(float(s), 3)
        return round(float(s), 3)
    except Exception:
        return 0.0

def get_current_user(
    authorization: Optional[str] = Header(None),
    x_auth_token: Optional[str] = Header(None)
) -> Optional[Dict[str, Any]]:
    token = None
    if authorization and authorization.startswith("Bearer "):
        token = authorization.split("Bearer ")[1].strip()
    elif x_auth_token:
        token = x_auth_token.strip()
    
    if token:
        return verify_auth_token(token)
    return None

def require_user(
    authorization: Optional[str] = Header(None),
    x_auth_token: Optional[str] = Header(None)
) -> Dict[str, Any]:
    user = get_current_user(authorization, x_auth_token)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Please log in with your officer credentials to perform this operation."
        )
    return user

router = APIRouter()

# System & Auth
@router.get("/status")
def get_system_status():
    return get_db_status()

@router.post("/auth/login")
def login(creds: LoginRequest):
    user = authenticate_user(creds.username, creds.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password"
        )
    token = create_auth_token(user)
    return {
        "success": True,
        "token": token,
        "user": user
    }

@router.post("/auth/logout")
def logout():
    return {"success": True, "message": "Successfully logged out"}

@router.get("/auth/me")
def get_me(user: Dict[str, Any] = Depends(require_user)):
    return {"user": user}

@router.post("/auth/change-password")
def user_change_password(
    payload: UserChangePasswordRequest,
    user: Dict[str, Any] = Depends(require_user)
):
    if payload.new_password != payload.confirm_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New password and confirmation password do not match."
        )
    try:
        change_user_password(
            username=user["username"],
            current_password=payload.current_password,
            new_password=payload.new_password
        )
        return {"success": True, "message": "Password successfully updated. Please use your new password for subsequent logins."}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

@router.put("/auth/profile")
def update_self_profile(
    payload: UserProfileUpdateRequest,
    user: Dict[str, Any] = Depends(require_user)
):
    try:
        current_username = user["username"]
        updates = {k: v for k, v in payload.dict().items() if v is not None}
        updated_user = update_user_profile(current_username, updates)
        new_token = create_auth_token(updated_user)
        return {
            "success": True,
            "token": new_token,
            "user": updated_user,
            "message": "Your profile information has been successfully updated."
        }
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

# Dashboard & Executive Summaries
@router.get("/dashboard/stats")
def get_stats(
    district: Optional[str] = Query(None),
    authorization: Optional[str] = Header(None),
    x_auth_token: Optional[str] = Header(None)
):
    current_user = get_current_user(authorization, x_auth_token)
    if current_user and current_user.get("role") == "district_rep":
        u_dist = current_user.get("district")
        if u_dist and u_dist.lower() != "all":
            district = u_dist
    return get_dashboard_stats(district=district)

@router.get("/executive/summary")
def get_exec_summary():
    return get_executive_summary()

# Audit Logs
@router.get("/audit-logs")
def list_audit_logs(
    record_id: Optional[str] = Query(None),
    district: Optional[str] = Query(None),
    limit: int = Query(100)
):
    return get_audit_logs(record_id=record_id, district=district, limit=limit)

# District Master
@router.get("/districts")
def list_districts():
    return get_districts()

@router.post("/districts", status_code=status.HTTP_201_CREATED)
def create_district(
    payload: DistrictCreateRequest,
    user: Dict[str, Any] = Depends(require_user)
):
    if user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permission denied: Administrator privileges required to create a new district master record."
        )
    try:
        res = add_district(payload.dict(), user_name=user["name"], user_role=user["role"])
        return res
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

@router.put("/districts/{district_id}")
def edit_district_master(
    district_id: str,
    payload: DistrictUpdateRequest,
    user: Dict[str, Any] = Depends(require_user)
):
    if user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permission denied: Administrator privileges required to modify district baseline targets."
        )
    updates = {k: v for k, v in payload.dict().items() if v is not None and k not in ["updated_by", "user_role"]}
    res = update_district_master(
        district_id=district_id,
        updates=updates,
        user_name=user["name"],
        user_role=user["role"]
    )
    if not res:
        raise HTTPException(status_code=404, detail="District not found")
    return res

@router.delete("/districts/{district_id}")
def remove_district(
    district_id: str,
    user: Dict[str, Any] = Depends(require_user)
):
    if user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permission denied: Administrator privileges required to delete a district."
        )
    try:
        success = delete_district(district_id, user_name=user["name"], user_role=user["role"])
        if not success:
            raise HTTPException(status_code=404, detail="District not found")
        return {"success": True, "message": "District successfully removed"}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

# Mandals Master
@router.get("/mandals")
def list_mandals(
    district: Optional[str] = Query(None),
    search: Optional[str] = Query(None)
):
    return get_mandals(district=district, search=search)

@router.get("/mandals/{mandal_id}")
def get_mandal_by_id(mandal_id: str):
    m = get_mandal(mandal_id)
    if not m:
        raise HTTPException(status_code=404, detail="Mandal not found")
    return m

@router.post("/mandals", status_code=status.HTTP_201_CREATED)
def create_mandal(
    payload: MandalCreateRequest,
    user: Dict[str, Any] = Depends(require_user)
):
    if user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permission denied: Administrator privileges required to create a new mandal."
        )
    try:
        return add_mandal(payload.dict(), user_name=user["name"], user_role=user["role"])
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

@router.put("/mandals/{mandal_id}")
def edit_mandal(
    mandal_id: str,
    payload: MandalUpdateRequest,
    user: Dict[str, Any] = Depends(require_user)
):
    if user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permission denied: Administrator privileges required to edit mandal details."
        )
    updates = {k: v for k, v in payload.dict().items() if v is not None}
    res = update_mandal(mandal_id, updates, user_name=user["name"], user_role=user["role"])
    if not res:
        raise HTTPException(status_code=404, detail="Mandal not found")
    return res

@router.delete("/mandals/{mandal_id}")
def remove_mandal(
    mandal_id: str,
    user: Dict[str, Any] = Depends(require_user)
):
    if user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permission denied: Administrator privileges required to delete a mandal."
        )
    try:
        success = delete_mandal(mandal_id, user_name=user["name"], user_role=user["role"])
        if not success:
            raise HTTPException(status_code=404, detail="Mandal not found")
        return {"success": True, "message": "Mandal successfully removed"}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

# Master Catalog
@router.get("/master-catalog")
def get_catalog():
    return get_master_catalog()

# Representatives Master
@router.get("/representatives")
def list_representatives(
    district: Optional[str] = Query(None),
    role: Optional[str] = Query(None)
):
    return get_representatives(district=district, role=role)

@router.post("/representatives", status_code=status.HTTP_201_CREATED)
def create_representative(
    payload: RepresentativeCreateRequest,
    user: Dict[str, Any] = Depends(require_user)
):
    if user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permission denied: Administrator privileges required to add representatives."
        )
    return add_representative(payload.dict())

@router.put("/representatives/{rep_id}")
def edit_representative(
    rep_id: str,
    payload: RepresentativeUpdateRequest,
    user: Dict[str, Any] = Depends(require_user)
):
    if user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permission denied: Administrator privileges required to edit representatives."
        )
    updates = {k: v for k, v in payload.dict().items() if v is not None}
    res = update_representative(rep_id, updates)
    if not res:
        raise HTTPException(status_code=404, detail="Representative not found")
    return res

@router.delete("/representatives/{rep_id}")
def remove_representative(
    rep_id: str,
    user: Dict[str, Any] = Depends(require_user)
):
    if user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permission denied: Administrator privileges required to remove representatives."
        )
    success = delete_representative(rep_id)
    if not success:
        raise HTTPException(status_code=404, detail="Representative not found")
    return {"success": True, "message": "Representative removed"}

# ----------------- USER MANAGEMENT & GOVERNANCE (ADMIN ONLY) -----------------
@router.get("/users")
def list_users(
    district: Optional[str] = Query(None),
    role: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    user: Dict[str, Any] = Depends(require_user)
):
    if user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permission denied: Administrator privileges required to access User Management."
        )
    return get_users(district=district, role=role, search=search, include_passwords=True)

@router.get("/users/{username}")
def get_user_details(
    username: str,
    user: Dict[str, Any] = Depends(require_user)
):
    if user.get("role") != "admin" and user.get("username", "").lower() != username.lower():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permission denied: Cannot view other user account details."
        )
    u = get_user(username)
    if not u:
        raise HTTPException(status_code=404, detail="User not found")
    return u

@router.post("/users", status_code=status.HTTP_201_CREATED)
def create_new_user(
    payload: UserCreateRequest,
    user: Dict[str, Any] = Depends(require_user)
):
    if user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permission denied: Administrator privileges required to create user accounts."
        )
    try:
        created = add_user(payload.dict(), admin_name=user["name"], admin_role=user["role"])
        return created
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

@router.put("/users/{username}")
def update_user_details(
    username: str,
    payload: UserUpdateRequest,
    user: Dict[str, Any] = Depends(require_user)
):
    if user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permission denied: Administrator privileges required to modify user accounts."
        )
    updates = {k: v for k, v in payload.dict().items() if v is not None}
    res = update_user(username, updates, admin_name=user["name"], admin_role=user["role"])
    if not res:
        raise HTTPException(status_code=404, detail="User not found")
    return res

@router.post("/users/{username}/reset-password")
def admin_reset_password(
    username: str,
    payload: AdminPasswordResetRequest,
    user: Dict[str, Any] = Depends(require_user)
):
    if user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permission denied: Administrator privileges required to reset passwords."
        )
    try:
        success = reset_user_password(username, payload.new_password, admin_name=user["name"], admin_role=user["role"])
        if not success:
            raise HTTPException(status_code=404, detail="User not found")
        return {"success": True, "message": f"Password successfully reset for user '{username}'"}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

@router.delete("/users/{username}")
def remove_user(
    username: str,
    user: Dict[str, Any] = Depends(require_user)
):
    if user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permission denied: Administrator privileges required to delete users."
        )
    try:
        success = delete_user(username, admin_name=user["name"], admin_role=user["role"])
        if not success:
            raise HTTPException(status_code=404, detail="User not found")
        return {"success": True, "message": f"User '{username}' successfully deleted"}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


# ----------------- STATE TERRITORIAL MASTER DIRECTORY (10,888 VILLAGES / 604 MANDALS) -----------------
@router.get("/master/villages")
def list_master_villages(
    district: Optional[str] = Query(None),
    mandal: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    is_picked: Optional[bool] = Query(None),
    search: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=500)
):
    return get_master_villages(
        district=district,
        mandal=mandal,
        category=category,
        is_picked=is_picked,
        search=search,
        page=page,
        limit=limit
    )

@router.get("/master/mandals")
def list_master_mandals(
    district: Optional[str] = Query(None),
    search: Optional[str] = Query(None)
):
    return get_master_mandals(district=district, search=search)

# Villages Operations & Verification
@router.get("/villages")
def list_villages(
    district: Optional[str] = Query(None),
    mandal: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    shapefile_status: Optional[str] = Query(None),
    verification_status: Optional[str] = Query(None),
    is_picked: Optional[bool] = Query(None),
    search: Optional[str] = Query(None),
    authorization: Optional[str] = Header(None),
    x_auth_token: Optional[str] = Header(None)
):
    current_user = get_current_user(authorization, x_auth_token)
    # Strictly enforce district isolation for district representatives
    if current_user and current_user.get("role") == "district_rep":
        u_dist = current_user.get("district")
        if u_dist and u_dist.lower() != "all":
            district = u_dist

    return get_villages(
        district=district,
        mandal=mandal,
        category=category,
        shapefile_status=shapefile_status,
        verification_status=verification_status,
        is_picked=is_picked,
        search=search
    )

@router.get("/villages/{village_id}")
def get_village_by_id(village_id: str):
    v = get_village(village_id)
    if not v:
        raise HTTPException(status_code=404, detail="Village record not found")
    return v

@router.post("/villages", status_code=status.HTTP_201_CREATED)
def create_village(
    payload: VillageCreateRequest,
    user: Dict[str, Any] = Depends(require_user)
):
    if user.get("role") not in ["admin", "district_rep"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permission denied: Only designated District Representatives and Administrators can add survey records."
        )

    # If district representative, enforce assigned district match
    if user.get("role") == "district_rep":
        assigned_district = (user.get("district") or "").lower()
        if assigned_district != "all" and payload.district_name.lower() != assigned_district:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission denied: You are assigned to {user.get('district')} district and cannot submit records for {payload.district_name}."
            )

    data = payload.dict()
    data.pop("updated_by", None)
    data.pop("user_role", None)
    data["extent_acres_float"] = calculate_acres(data.get("extent_raw"))
    return add_village(data, user_name=user["name"], user_role=user["role"])

@router.put("/villages/{village_id}")
def edit_village(
    village_id: str,
    payload: VillageUpdateRequest,
    user: Dict[str, Any] = Depends(require_user)
):
    if user.get("role") not in ["admin", "district_rep"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permission denied: Only designated District Representatives and Administrators can modify village records."
        )

    existing = get_village(village_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Village record not found")

    # CRITICAL SECURITY RULE: Prohibit editing or entering data for non-picked villages
    is_picked = bool(existing.get("is_picked_for_resurvey") or existing.get("picked_for_resurvey"))
    if not is_picked:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Editing or entering survey data is not permitted for villages not picked for resurvey."
        )

    # If district representative, enforce assigned district match
    if user.get("role") == "district_rep":
        assigned_district = (user.get("district") or "").lower()
        existing_district = (existing.get("district_name") or "").lower()
        if assigned_district != "all" and existing_district != assigned_district:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission denied: You are assigned to {user.get('district')} district and cannot modify records for {existing.get('district_name')}."
            )

    data = payload.dict()
    data.pop("updated_by", None)
    data.pop("user_role", None)
    updates = {k: v for k, v in data.items() if v is not None}
    
    if "extent_raw" in updates:
        updates["extent_acres_float"] = calculate_acres(updates["extent_raw"])
        
    try:
        updated = update_village(village_id, updates, user_name=user["name"], user_role=user["role"])
        return updated
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))

@router.post("/villages/{village_id}/verify")
def verify_village_record(
    village_id: str,
    payload: VerificationRequest,
    user: Dict[str, Any] = Depends(require_user)
):
    if user.get("role") not in ["admin", "qc_engineer"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permission denied: Only Central QC Verification Engineers and Administrators can certify or return records."
        )

    qc_inspector = f"{user['name']} ({user.get('designation') or 'Central QC'})"
    res = verify_village(
        village_id=village_id,
        status=payload.status,
        qc_user=qc_inspector,
        notes=payload.notes
    )
    if not res:
        raise HTTPException(status_code=404, detail="Village record not found")
    return res

@router.delete("/villages/{village_id}")
def remove_village(
    village_id: str,
    user: Dict[str, Any] = Depends(require_user)
):
    if user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permission denied: Administrator privileges required to delete village records."
        )
    success = delete_village(village_id, user_name=user["name"])
    if not success:
        raise HTTPException(status_code=404, detail="Village record not found")
    return {"success": True, "message": "Village record deleted"}

@router.get("/export/excel")
def export_excel(
    district: Optional[str] = Query(None),
    authorization: Optional[str] = Header(None),
    x_auth_token: Optional[str] = Header(None)
):
    current_user = get_current_user(authorization, x_auth_token)
    if current_user and current_user.get("role") == "district_rep":
        u_dist = current_user.get("district")
        if u_dist and u_dist.lower() != "all":
            district = u_dist
            
    excel_stream = generate_resurvey_excel(district=district)
    fname = f"Resurvey_{district}_Progress.xlsx" if district else "Resurvey_Village_Progress_04-09-2026.xlsx"
    return StreamingResponse(
        excel_stream,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f"attachment; filename={fname}"
        }
    )

app.include_router(router, prefix="/api")
app.include_router(router, prefix="")

PUBLIC_DIR = os.path.join(ROOT_DIR, "public")
if os.path.exists(PUBLIC_DIR):
    @app.get("/")
    def serve_index():
        index_file = os.path.join(PUBLIC_DIR, "index.html")
        if os.path.exists(index_file):
            return FileResponse(
                index_file,
                headers={
                    "Cache-Control": "no-cache, no-store, must-revalidate",
                    "Pragma": "no-cache",
                    "Expires": "0"
                }
            )
        return HTMLResponse("<h3>ResurveyUpdates UI loading...</h3>")
