import os
import sys
from typing import Optional, Dict, Any
from fastapi import FastAPI, HTTPException, Depends, Query, status
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
    get_villages,
    get_village,
    add_village,
    update_village,
    delete_village,
    get_dashboard_stats,
    authenticate_user
)
from core.export_service import generate_resurvey_excel

app = FastAPI(
    title="Resurvey Updates Monitoring API",
    description="Portal for Cadastral & Non-Cadastral Village Progress Tracking",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class LoginRequest(BaseModel):
    username: str
    password: str

class VillageCreateRequest(BaseModel):
    district_name: str
    category: str  # "Non-Cadastral" or "Cadastral"
    village_name: str
    mandal_name: str
    extent_raw: Optional[str] = ""
    gt_status: Optional[str] = "Completed"
    shapefile_status: Optional[str] = "Pending"
    sent_to_cso: Optional[bool] = False
    workflow_stage: Optional[str] = "Ground Truthing"
    remarks: Optional[str] = ""
    updated_by: Optional[str] = "Field Member"

class VillageUpdateRequest(BaseModel):
    category: Optional[str] = None
    village_name: Optional[str] = None
    mandal_name: Optional[str] = None
    extent_raw: Optional[str] = None
    gt_status: Optional[str] = None
    shapefile_status: Optional[str] = None
    sent_to_cso: Optional[bool] = None
    workflow_stage: Optional[str] = None
    remarks: Optional[str] = None
    updated_by: Optional[str] = None

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

@app.get("/api/status")
def get_system_status():
    return get_db_status()

@app.post("/api/auth/login")
def login(creds: LoginRequest):
    user = authenticate_user(creds.username, creds.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password"
        )
    return {
        "success": True,
        "token": f"token-{user['username']}",
        "user": user
    }

@app.get("/api/dashboard/stats")
def get_stats():
    return get_dashboard_stats()

@app.get("/api/districts")
def list_districts():
    return get_districts()

@app.get("/api/villages")
def list_villages(
    district: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    shapefile_status: Optional[str] = Query(None),
    search: Optional[str] = Query(None)
):
    return get_villages(
        district=district,
        category=category,
        shapefile_status=shapefile_status,
        search=search
    )

@app.get("/api/villages/{village_id}")
def get_village_by_id(village_id: str):
    v = get_village(village_id)
    if not v:
        raise HTTPException(status_code=404, detail="Village record not found")
    return v

@app.post("/api/villages", status_code=status.HTTP_201_CREATED)
def create_village(payload: VillageCreateRequest):
    data = payload.dict()
    data["extent_acres_float"] = calculate_acres(data.get("extent_raw"))
    return add_village(data)

@app.put("/api/villages/{village_id}")
def edit_village(village_id: str, payload: VillageUpdateRequest):
    existing = get_village(village_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Village record not found")
    
    updates = {k: v for k, v in payload.dict().items() if v is not None}
    if "extent_raw" in updates:
        updates["extent_acres_float"] = calculate_acres(updates["extent_raw"])
        
    updated = update_village(village_id, updates)
    return updated

@app.delete("/api/villages/{village_id}")
def remove_village(village_id: str):
    success = delete_village(village_id)
    if not success:
        raise HTTPException(status_code=404, detail="Village record not found")
    return {"success": True, "message": "Village record deleted"}

@app.get("/api/export/excel")
def export_excel():
    excel_stream = generate_resurvey_excel()
    return StreamingResponse(
        excel_stream,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": "attachment; filename=Resurvey_Village_Progress_04-09-2026.xlsx"
        }
    )

PUBLIC_DIR = os.path.join(ROOT_DIR, "public")
if os.path.exists(PUBLIC_DIR):
    @app.get("/")
    def serve_index():
        index_file = os.path.join(PUBLIC_DIR, "index.html")
        if os.path.exists(index_file):
            return FileResponse(index_file)
        return HTMLResponse("<h3>ResurveyUpdates UI loading...</h3>")
