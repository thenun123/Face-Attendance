"""
Attendance API Routes — JWT protected
GET  /attendance           → authenticated (viewers filtered to their dept)
GET  /attendance/stats     → authenticated
GET  /attendance/export    → authenticated
POST /attendance/early-leave  → admin only
POST /attendance/mark-absent  → admin only
GET  /unknown-faces           → authenticated
POST /unknown-faces/{id}/resolve → admin only
"""

import csv
import io
from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, Query, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.schemas import (
    AttendanceRecord, DashboardStats, UnknownFaceOut,
    EarlyLeaveRequest, EarlyLeaveResponse,
)
from app.core.auth import require_auth, require_admin
from app.db.crud import (
    get_attendance, get_today_stats, get_unknown_faces,
    mark_absent_for_today, mark_early_leave, resolve_unknown_face,
)
from app.db.database import get_db, AdminUser

router = APIRouter()


@router.get("/attendance", response_model=List[AttendanceRecord])
async def query_attendance(
    date_filter: Optional[date] = Query(None),
    employee_id: Optional[str] = Query(None),
    department: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: AdminUser = Depends(require_auth),
):
    # Viewers are restricted to their own department
    if current_user.role == "viewer" and current_user.department:
        department = current_user.department

    records = await get_attendance(db, date_filter=date_filter, employee_id=employee_id, department=department)
    return [
        AttendanceRecord(
            id=r.id,
            employee_id=r.employee_id,
            employee_name=r.employee.name if r.employee else None,
            date=r.date,
            check_in_time=r.check_in_time,
            check_out_time=r.check_out_time,
            total_hours=r.total_hours,
            status=r.status,
            confidence=r.confidence,
        )
        for r in records
    ]


@router.get("/attendance/stats", response_model=DashboardStats)
async def get_dashboard_stats(
    db: AsyncSession = Depends(get_db),
    current_user: AdminUser = Depends(require_auth),
):
    stats = await get_today_stats(db)
    return DashboardStats(**stats)


@router.get("/attendance/export")
async def export_attendance_csv(
    date_filter: Optional[date] = Query(None),
    department: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: AdminUser = Depends(require_auth),
):
    if current_user.role == "viewer" and current_user.department:
        department = current_user.department

    records = await get_attendance(db, date_filter=date_filter, department=department)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "ID", "Employee ID", "Name", "Day", "Date",
        "Check In", "Check Out", "Total Hours", "Status",
    ])
    for r in records:
        day_name = r.date.strftime("%A") if r.date else ""
        writer.writerow([
            r.id, r.employee_id,
            r.employee.name if r.employee else "",
            day_name,
            r.date.strftime("%d-%m-%Y") if r.date else "",
            r.check_in_time.strftime("%I:%M:%S %p") if r.check_in_time else "",
            r.check_out_time.strftime("%I:%M:%S %p") if r.check_out_time else "",
            r.total_hours or "",
            r.status,
        ])
    output.seek(0)
    filename = f"attendance_{date_filter or date.today()}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.post("/attendance/early-leave", response_model=EarlyLeaveResponse)
async def early_leave(
    request: EarlyLeaveRequest,
    db: AsyncSession = Depends(get_db),
    current_user: AdminUser = Depends(require_admin),
):
    result = await mark_early_leave(db, employee_id=request.employee_id)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["reason"])
    return EarlyLeaveResponse(**result)


@router.post("/attendance/mark-absent")
async def run_absent_batch(
    db: AsyncSession = Depends(get_db),
    current_user: AdminUser = Depends(require_admin),
):
    count = await mark_absent_for_today(db)
    return {"message": f"Marked {count} employees as Absent for today."}


@router.get("/unknown-faces", response_model=List[UnknownFaceOut])
async def list_unknown_faces(
    unresolved_only: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    current_user: AdminUser = Depends(require_auth),
):
    return await get_unknown_faces(db, unresolved_only=unresolved_only)


@router.post("/unknown-faces/{face_id}/resolve")
async def resolve_face_alert(
    face_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: AdminUser = Depends(require_admin),
):
    success = await resolve_unknown_face(db, face_id)
    if not success:
        raise HTTPException(status_code=404, detail="Unknown face record not found.")
    return {"message": f"Face alert {face_id} resolved."}
