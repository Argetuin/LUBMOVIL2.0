from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from app.api import deps
from app.crud import crm as crud_crm
from app.models.models import User, UserRole
from app.schemas import schemas

router = APIRouter()


# ─── Clientes ──────────────────────────────────────────────────────────────────

@router.get("/clients", response_model=List[schemas.ClientResponse])
def list_clients(
    q: Optional[str] = Query(None, min_length=1),
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user)
):
    """Lista todos los clientes. Si se pasa ?q= hace smart search por nombre, teléfono o placa."""
    if q:
        return crud_crm.smart_search(db, q)
    return crud_crm.get_clients(db)


@router.post("/clients", response_model=schemas.ClientResponse)
def create_client(
    data: schemas.ClientCreate,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user)
):
    return crud_crm.create_client(db, data, user_id=current_user.id)


@router.get("/clients/{client_id}", response_model=schemas.ClientResponse)
def get_client(
    client_id: int,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user)
):
    client = crud_crm.get_client(db, client_id)
    if not client:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")
    return client


@router.put("/clients/{client_id}", response_model=schemas.ClientResponse)
def update_client(
    client_id: int,
    data: schemas.ClientUpdate,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user)
):
    client = crud_crm.get_client(db, client_id)
    if not client:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")
    return crud_crm.update_client(db, client, data, user_id=current_user.id)


@router.delete("/clients/{client_id}")
def delete_client(
    client_id: int,
    db: Session = Depends(deps.get_db),
    admin: User = Depends(deps.role_required([UserRole.ADMIN]))
):
    client = crud_crm.get_client(db, client_id)
    if not client:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")
    crud_crm.delete_client(db, client)
    return {"ok": True}


# ─── Vehículos ─────────────────────────────────────────────────────────────────

@router.post("/clients/{client_id}/vehicles", response_model=schemas.VehicleResponse)
def add_vehicle(
    client_id: int,
    data: schemas.VehicleCreate,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user)
):
    client = crud_crm.get_client(db, client_id)
    if not client:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")
    try:
        return crud_crm.create_vehicle(db, client_id, data, user_id=current_user.id)
    except Exception as e:
        if "UNIQUE constraint" in str(e):
            raise HTTPException(status_code=400, detail="Ya existe un vehículo con esa placa")
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/vehicles/{vehicle_id}", response_model=schemas.VehicleResponse)
def update_vehicle(
    vehicle_id: int,
    data: schemas.VehicleUpdate,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user)
):
    vehicle = crud_crm.get_vehicle(db, vehicle_id)
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vehículo no encontrado")
    return crud_crm.update_vehicle(db, vehicle, data, user_id=current_user.id)


@router.delete("/vehicles/{vehicle_id}")
def delete_vehicle(
    vehicle_id: int,
    db: Session = Depends(deps.get_db),
    admin: User = Depends(deps.role_required([UserRole.ADMIN]))
):
    vehicle = crud_crm.get_vehicle(db, vehicle_id)
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vehículo no encontrado")
    crud_crm.delete_vehicle(db, vehicle, user_id=admin.id)
    return {"ok": True}


@router.get("/vehicles/{vehicle_id}/projection")
def get_service_projection(
    vehicle_id: int,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user)
):
    vehicle = crud_crm.get_vehicle(db, vehicle_id)
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vehículo no encontrado")
    projection = crud_crm.project_next_service(
        last_odometer=vehicle.current_odometer or 0,
        last_service_date=vehicle.last_service_date or vehicle.created_at
    )
    return projection


# ─── Servicios ─────────────────────────────────────────────────────────────────

@router.post("/vehicles/{vehicle_id}/services", response_model=schemas.ServiceRecordResponse)
def add_service_record(
    vehicle_id: int,
    data: schemas.ServiceRecordCreate,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user)
):
    vehicle = crud_crm.get_vehicle(db, vehicle_id)
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vehículo no encontrado")
    return crud_crm.create_service_record(db, vehicle_id, data, user_id=current_user.id)
