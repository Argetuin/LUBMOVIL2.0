import json
import base64
import os
import uuid
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from app.db.session import get_db
from app.models.models import (
    Vehicle, Product, ServiceOrder, ServiceRecord, OrderStatus, SystemSettings, User,
    Treasury, CashFlowType
)
from app.schemas.schemas import ServiceOrderCreate, ServiceOrderResponse

router = APIRouter()

# Configuración de carpetas para guardar evidencias
UPLOAD_DIR = "app/static/uploads/orders"
os.makedirs(UPLOAD_DIR, exist_ok=True)


def _save_base64_image(b64_str: str, prefix: str) -> str:
    """Extrae el header de base64 y guarda la imagen localmente, retornando la URL."""
    if not b64_str or not b64_str.startswith("data:image"):
        return ""
    
    try:
        # Formato esperado: "data:image/jpeg;base64,...datos..."
        header, encoded = b64_str.split(",", 1)
        ext = header.split(";")[0].split("/")[1]
        filename = f"{prefix}_{uuid.uuid4().hex[:8]}.{ext}"
        filepath = os.path.join(UPLOAD_DIR, filename)
        
        with open(filepath, "wb") as f:
            f.write(base64.b64decode(encoded))
            
        return f"/static/uploads/orders/{filename}"
    except Exception as e:
        print(f"Error guardando imagen {prefix}: {e}")
        return ""


@router.get("/quote")
def calculate_quote(vehicle_id: int, oil_product_id: int, filter_product_id: int = None, db: Session = Depends(get_db)):
    """
    Motor Cotizador: Calcula el monto total del servicio sumando los costos de aceite, 
    el filtro, la mano de obra y la logística. Valida que haya stock sugerido.
    """
    vehicle = db.query(Vehicle).filter(Vehicle.id == vehicle_id).first()
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vehículo no encontrado")
        
    oil = db.query(Product).filter(Product.id == oil_product_id).first()
    if not oil:
        raise HTTPException(status_code=404, detail="Aceite no encontrado o Inactivo")
        
    capacity_qts = vehicle.oil_capacity_qts or 0.0
    if capacity_qts <= 0:
        raise HTTPException(status_code=400, detail="El vehículo no tiene configurada la capacidad de aceite (Qts/L)")

    # Validación de Stock
    if oil.current_stock < capacity_qts:
        raise HTTPException(status_code=400, detail=f"Stock insuficiente de aceite. Requerido: {capacity_qts}, Disponible: {oil.current_stock}")

    oil_total = capacity_qts * oil.retail_price_usd
    filter_total = 0.0
    filter_data = None
    
    if filter_product_id:
        filter_item = db.query(Product).filter(Product.id == filter_product_id).first()
        if not filter_item:
            raise HTTPException(status_code=404, detail="Filtro no encontrado")
        if filter_item.current_stock < 1:
             raise HTTPException(status_code=400, detail=f"Stock insuficiente del filtro {filter_item.name}.")
             
        filter_total = filter_item.retail_price_usd
        filter_data = {
            "id": filter_item.id,
            "name": filter_item.name,
            "unit_price": filter_item.retail_price_usd,
            "qty": 1
        }

    # Cargos Fijos (pueden venir de config más adelante)
    labor_fee = 15.0
    logistics_fee = 1.5
    
    grand_total = oil_total + filter_total + labor_fee + logistics_fee

    return {
        "vehicle": {
            "id": vehicle.id,
            "plate": vehicle.plate,
            "brand": vehicle.brand,
            "model": vehicle.model,
            "capacity_qts": capacity_qts
        },
        "breakdown": {
            "oil": {
                "id": oil.id,
                "name": oil.name,
                "unit_price_usd": oil.retail_price_usd,
                "qty": capacity_qts,
                "subtotal": round(oil_total, 2)
            },
            "filter": filter_data,
            "labor_fee": labor_fee,
            "logistics_fee": logistics_fee
        },
        "total_usd": round(grand_total, 2)
    }


@router.post("/checkout")
def checkout_service(payload: dict, db: Session = Depends(get_db)):
    """
    MOTOR TRANSACCIONAL (El Cerebro)
    Recibe el payload masivo desde el Wizard UI, procesa el pago, deduce inventario, 
    crea el tracking del vehículo y guarda evidencias en un bloque atómico.
    """
    # 1. Extraer identificadores base
    vehicle_id = payload.get("vehicle_id")
    user_id = payload.get("user_id", 1)  # Por ahora forzamos admin (TODO: Extraer de token)
    
    vehicle = db.query(Vehicle).filter(Vehicle.id == vehicle_id).first()
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vehículo no encontrado")
        
    # Extraer variables técnicas
    actual_odometer = int(payload.get("odometer_at_service", 0))
    if actual_odometer <= vehicle.current_odometer:
        raise HTTPException(status_code=400, detail=f"El odómetro actual ({actual_odometer}) debe ser mayor al histórico ({vehicle.current_odometer})")
        
    # Extraer desgloses financieros
    items = payload.get("items", {})
    oil_id = items.get("oil_id")
    oil_qty = float(items.get("oil_qty", 0))
    filter_id = items.get("filter_id")
    
    # 2. INICIO DE TRANSACCIÓN ATÓMICA
    try:
        # --- A. VERIFICACIÓN Y DEDUCCIÓN DE INVENTARIO ---
        oil_product = db.query(Product).with_for_update().filter(Product.id == oil_id).first()
        if not oil_product or oil_product.current_stock < oil_qty:
            raise ValueError(f"Stock insuficiente para el aceite (Req: {oil_qty})")
            
        oil_product.current_stock -= oil_qty
        products_used = {"aceite": f"{oil_product.name} ({oil_qty} Qt/L)"}
        
        filter_cost = 0.0
        if filter_id:
            filter_product = db.query(Product).with_for_update().filter(Product.id == filter_id).first()
            if not filter_product or filter_product.current_stock < 1:
                raise ValueError("Stock insuficiente para el filtro")
                
            filter_product.current_stock -= 1
            filter_cost = filter_product.retail_price_usd
            products_used["filtro"] = filter_product.name
            
        # --- B. GUARDADO DE IMÁGENES LOCALES (EVIDENCIA) ---
        url_odo = _save_base64_image(payload.get("photo_odometer"), "odo")
        url_before = _save_base64_image(payload.get("photo_before"), "bef")
        url_after = _save_base64_image(payload.get("photo_after"), "aft")
        
        # Generar identificador único de Orden
        order_number = f"LM-{datetime.now().strftime('%y%m%d')}-{uuid.uuid4().hex[:4].upper()}"

        # Obtener tasa BCV Actual
        bcv_rate = 0.0
        sys_config = db.query(SystemSettings).first()
        if sys_config:
            bcv_rate = sys_config.bcv_rate
            
        total_usd = float(payload.get("total_usd", 0.0))
        total_bs = total_usd * bcv_rate if bcv_rate else 0.0
        
        # --- C. CREACIÓN DE LA ORDEN DE SERVICIO PESADA ---
        order = ServiceOrder(
            order_number=order_number,
            vehicle_id=vehicle.id,
            user_id=user_id,
            status=OrderStatus.COMPLETADA,
            date=datetime.utcnow(),
            
            # Finanzas guardadas como Snapshot
            oil_cost_at_time=oil_product.average_unit_cost, # Costo en almacén
            filter_cost_at_time=filter_cost,
            labor_fee=15.0,
            logistics_fee=1.5,
            total_amount_usd=total_usd,
            bcv_rate_at_time=bcv_rate,
            total_amount_bs=total_bs,
            
            payment_method=payload.get("payment_method"),
            
            # Formatos de Campo
            odometer_at_service=actual_odometer,
            is_drained=payload.get("checklist", {}).get("drained", False),
            is_filter_new=payload.get("checklist", {}).get("filter", False),
            is_plug_tight=payload.get("checklist", {}).get("plug", False),
            is_cleaned=payload.get("checklist", {}).get("cleaned", False),
            
            # Evidencias
            photo_odometer_url=url_odo,
            photo_engine_before_url=url_before,
            photo_engine_after_url=url_after,
            signature_data=payload.get("signature_data"), # Base64 Canvas
            
            notes=payload.get("notes", ""),
            products_json=json.dumps(products_used)
        )
        db.add(order)
        db.flush() # Para obtener el ID de la orden

        # --- D. REGISTRO EN TESORERÍA ---
        treasury_entry = Treasury(
            amount_usd=total_usd,
            amount_bs=total_bs,
            rate=bcv_rate,
            description=f"Pago de Servicio Orden {order_number} - Placa {vehicle.plate}",
            entry_type=CashFlowType.INGRESO,
            payment_method=payload.get("payment_method"),
            reference_order_id=order.id
        )
        db.add(treasury_entry)
        
        # --- E. ACTUALIZACIÓN DEL CRM (SERVICE RECORD HISTÓRICO) ---
        record = ServiceRecord(
            vehicle_id=vehicle.id,
            date=datetime.utcnow(),
            odometer_at_service=actual_odometer,
            service_type="Servicio LubMovil Estándar",
            products_json=json.dumps(products_used),
            total_cost_usd=total_usd,
            payment_method=payload.get("payment_method"),
            notes_technician=f"Orden #{order_number}. " + payload.get("notes", "")
        )
        db.add(record)
        
        # --- F. ACTUALIZACIÓN DE ESTADO DEL VEHÍCULO ---
        vehicle.current_odometer = actual_odometer
        vehicle.last_service_date = datetime.utcnow()
        vehicle.service_count += 1
        
        # --- G. COMMIT GENERAL (ATÓMICO) ---
        db.commit()
        db.refresh(order)
        
        # === 3. VERIFICACIÓN DE INTEGRIDAD (HEALTH CHECK) ===
        # Consultamos el stock nuevamente para garantizar el Commit
        check_oil = db.query(Product).filter(Product.id == oil_id).first()
        # Aquí se podría inyectar lógica compleja o de colas de mensajes
        # Si la validación detectara un bug gravísimo en la DB (raro en SQL Relacional post-commit):
        if hasattr(check_oil, 'current_stock') and check_oil.current_stock < 0:
            print("CRITICAL: Negative stock detected post-commit on Product ID:", oil_id)

        return {
            "status": "success",
            "message": "Transacción completada, stock actualizado y CRM sincronizado.",
            "order": {
                "id": order.id,
                "order_number": order.order_number,
                "total_usd": total_usd,
                "total_bs": order.total_bs
            }
        }
        
    except ValueError as ve:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(ve))
    except SQLAlchemyError as err:
        db.rollback()
        print("SQL ERROR:", err) # Log critical
        raise HTTPException(status_code=500, detail="Error crítico de base de datos. Transacción revertida. Contacte soporte.")
    except Exception as e:
        db.rollback()
        print("UNEXPECTED ERROR:", e)
        raise HTTPException(status_code=500, detail="Error inesperado durante el checkout. Transacción segura invocada.")
