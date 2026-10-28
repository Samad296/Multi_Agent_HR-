import uuid

from fastapi import APIRouter, Depends

from app.api.deps import TenantContext, get_context, get_db
from app.schemas.leave import BalanceOut, LeaveCreate, LeaveOut, TypeOut
from app.services import leave_service as svc

router = APIRouter(prefix="/leave", tags=["leave"])


@router.get("/types", response_model=list[TypeOut])
def types(db=Depends(get_db)):
    return svc.list_types(db)


@router.get("/balances", response_model=list[BalanceOut])
def balances(ctx: TenantContext = Depends(get_context), db=Depends(get_db)):
    return svc.get_balances(db, ctx)


@router.get("/requests", response_model=list[LeaveOut])
def requests(ctx: TenantContext = Depends(get_context), db=Depends(get_db)):
    return svc.list_requests(db, ctx)


@router.post("/requests", response_model=LeaveOut, status_code=201)
def submit(body: LeaveCreate, ctx: TenantContext = Depends(get_context), db=Depends(get_db)):
    req = svc.submit_request(db, ctx, body.leave_type_id, body.start_date, body.end_date, body.reason)
    db.commit()
    return req


@router.post("/requests/{request_id}/approve", response_model=LeaveOut)
def approve(request_id: uuid.UUID, ctx: TenantContext = Depends(get_context), db=Depends(get_db)):
    req = svc.decide_request(db, ctx, request_id, approve=True)
    db.commit()
    return req


@router.post("/requests/{request_id}/reject", response_model=LeaveOut)
def reject(request_id: uuid.UUID, ctx: TenantContext = Depends(get_context), db=Depends(get_db)):
    req = svc.decide_request(db, ctx, request_id, approve=False)
    db.commit()
    return req


@router.post("/requests/{request_id}/cancel", response_model=LeaveOut)
def cancel(request_id: uuid.UUID, ctx: TenantContext = Depends(get_context), db=Depends(get_db)):
    req = svc.cancel_request(db, ctx, request_id)
    db.commit()
    return req