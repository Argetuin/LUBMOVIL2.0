from sqlalchemy.orm import Session
from sqlalchemy import or_
from app.models.models import Client, Vehicle, VehicleStatus, AuditLog
from app.schemas.schemas import ClientCreate, ClientUpdate, VehicleCreate, VehicleUpdate
from datetime import datetime, timedelta
from typing import List, Optional
import uuid


# ─── Utilidades ────────────────────────────────────────────────────────────────

def normalize_plate(plate: str) -> str:
    """Normaliza la placa: MAYÚSCULAS, sin espacios ni guiones."""
    return plate.upper().replace("-", "").replace(" ", "").strip()


def generate_qr_uuid() -> str:
    """Genera un token único de 8 caracteres para la identidad QR del vehículo."""
    return uuid.uuid4().hex[:8].upper()


def project_next_service(
    last_odometer: int,
    last_service_date: datetime,
    avg_km_per_day: float = 50.0,   # ~1500 km/mes por defecto
    interval_km: int = 5000
) -> dict:
    """
    Proyecta la fecha estimada del próximo servicio.
    Retorna: km_restantes, fecha_estimada, porcentaje_completado
    """
    if not last_odometer or not last_service_date:
        return {"km_restantes": interval_km, "fecha_estimada": None, "porcentaje": 0}

    days_elapsed = (datetime.utcnow() - last_service_date).days
    estimated_current_km = last_odometer + (days_elapsed * avg_km_per_day)
    km_at_last_service = last_odometer
    km_restantes = max(0, interval_km - (estimated_current_km - km_at_last_service))
    porcentaje = min(100, int(((interval_km - km_restantes) / interval_km) * 100))

    days_to_next = int(km_restantes / avg_km_per_day) if avg_km_per_day > 0 else 180
    fecha_estimada = datetime.utcnow() + timedelta(days=days_to_next)

    return {
        "km_restantes": int(km_restantes),
        "fecha_estimada": fecha_estimada.strftime("%d/%m/%Y"),
        "porcentaje": porcentaje,
        "alerta": porcentaje >= 80
    }


# ─── Clientes ──────────────────────────────────────────────────────────────────

def get_clients(db: Session, skip: int = 0, limit: int = 100) -> List[Client]:
    return db.query(Client).order_by(Client.full_name).offset(skip).limit(limit).all()


def get_client(db: Session, client_id: int) -> Optional[Client]:
    return db.query(Client).filter(Client.id == client_id).first()


def smart_search(db: Session, q: str) -> List[Client]:
    """
    Búsqueda simultánea por nombre, teléfono o placa de vehículo.
    Retorna lista de clientes que coincidan en cualquiera de los tres campos.
    """
    q_norm = q.upper().replace("-", "").replace(" ", "")
    term = f"%{q}%"
    plate_term = f"%{q_norm}%"

    # Buscar clientes por nombre o teléfono
    clients_by_name_phone = db.query(Client).filter(
        or_(
            Client.full_name.ilike(term),
            Client.phone.ilike(term)
        )
    ).all()

    # Buscar vehículos por placa y obtener sus clientes
    vehicles = db.query(Vehicle).filter(Vehicle.plate.ilike(plate_term)).all()
    client_ids_from_plates = {v.client_id for v in vehicles}

    # Combinar sin duplicados
    all_clients = {c.id: c for c in clients_by_name_phone}
    for cid in client_ids_from_plates:
        if cid not in all_clients:
            c = get_client(db, cid)
            if c:
                all_clients[cid] = c

    return list(all_clients.values())


def create_client(db: Session, data: ClientCreate, user_id: int) -> Client:
    # Limpiar teléfono: solo dígitos
    phone_clean = "".join(filter(str.isdigit, data.phone or "")) or None

    db_client = Client(
        full_name=data.full_name.strip().title(),
        phone=phone_clean,
        address=data.address
    )
    db.add(db_client)
    db.flush()  # Para obtener el id antes del commit

    # Si viene con vehículo integrado, crearlo también
    if data.vehicle:
        _create_vehicle_obj(db, db_client.id, data.vehicle)

    audit = AuditLog(
        user_id=user_id, action="CREATE_CLIENT",
        description=f"Cliente creado: {db_client.full_name}"
    )
    db.add(audit)
    db.commit()
    db.refresh(db_client)
    return db_client


def update_client(db: Session, db_client: Client, data: ClientUpdate, user_id: int) -> Client:
    for field in data.model_fields_set:
        value = getattr(data, field)
        if hasattr(db_client, field):
            setattr(db_client, field, value)
    db.commit()
    db.refresh(db_client)
    return db_client


def delete_client(db: Session, db_client: Client):
    db.delete(db_client)
    db.commit()


# ─── Vehículos ─────────────────────────────────────────────────────────────────

def get_vehicle(db: Session, vehicle_id: int) -> Optional[Vehicle]:
    return db.query(Vehicle).filter(Vehicle.id == vehicle_id).first()


def get_vehicle_by_uuid(db: Session, qr_uuid: str) -> Optional[Vehicle]:
    """Retorna el vehículo por UUID e incrementa el contador de escaneos."""
    v = db.query(Vehicle).filter(Vehicle.qr_uuid == qr_uuid).first()
    if v:
        v.qr_scan_count = (v.qr_scan_count or 0) + 1
        db.commit()
        db.refresh(v)
    return v


def _create_vehicle_obj(db: Session, client_id: int, data: VehicleCreate) -> Vehicle:
    """Helper interno para crear el objeto Vehicle."""
    plate = normalize_plate(data.plate)

    # Generar UUID único garantizado
    qr_uuid = generate_qr_uuid()
    while db.query(Vehicle).filter(Vehicle.qr_uuid == qr_uuid).first():
        qr_uuid = generate_qr_uuid()

    db_vehicle = Vehicle(
        client_id=client_id,
        plate=plate,
        qr_uuid=qr_uuid,
        type=data.type,
        brand=data.brand,
        model=data.model,
        year=data.year,
        engine_v=data.engine_v,
        oil_capacity_liters=data.oil_capacity_liters,
        recommended_viscosity=data.recommended_viscosity,
        filter_code=data.filter_code,
        last_odometer=data.last_odometer
    )
    db.add(db_vehicle)
    return db_vehicle


def create_vehicle(db: Session, client_id: int, data: VehicleCreate, user_id: int) -> Vehicle:
    v = _create_vehicle_obj(db, client_id, data)
    audit = AuditLog(
        user_id=user_id, action="CREATE_VEHICLE",
        description=f"Vehículo registrado: {normalize_plate(data.plate)} para cliente {client_id}"
    )
    db.add(audit)
    db.commit()
    db.refresh(v)
    return v


def update_vehicle(db: Session, db_vehicle: Vehicle, data: VehicleUpdate, user_id: int) -> Vehicle:
    for field in data.model_fields_set:
        value = getattr(data, field)
        if hasattr(db_vehicle, field):
            setattr(db_vehicle, field, value)
    audit = AuditLog(
        user_id=user_id, action="UPDATE_VEHICLE",
        description=f"Ficha actualizada: {db_vehicle.plate}"
    )
    db.add(audit)
    db.commit()
    db.refresh(db_vehicle)
    return db_vehicle


def delete_vehicle(db: Session, db_vehicle: Vehicle, user_id: int):
    plate = db_vehicle.plate
    db.delete(db_vehicle)
    audit = AuditLog(
        user_id=user_id, action="DELETE_VEHICLE",
        description=f"Vehículo eliminado: {plate}"
    )
    db.add(audit)
    db.commit()
