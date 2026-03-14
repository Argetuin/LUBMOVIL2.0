from fastapi import FastAPI, Request, Depends, HTTPException
from typing import Optional, List, Any
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import func
from sqlalchemy.orm import Session
from datetime import datetime
import locale
import json

from app.api.routes import auth, inventory, crm as crm_routes, brain
from app.core.config import settings
from app.api import deps
from app.models import models
from app.models.models import SystemSettings, ProductCategory, Product, Client, ServiceOrder, OrderStatus # Added missing models
from app.db.session import engine
from app.core import rates

# Intentar establecer locale en español para fechas
try:
    locale.setlocale(locale.LC_TIME, "es_ES.UTF-8")
except:
    try:
        locale.setlocale(locale.LC_TIME, "es_ES")
    except:
        pass

# Crear tablas
models.Base.metadata.create_all(bind=engine)

app = FastAPI(title=settings.PROJECT_NAME)

app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")

# Filtros personalizados para Jinja2
def from_json(value):
    try:
        return json.loads(value)
    except:
        return {}

templates.env.filters["from_json"] = from_json

# Incluir rutas de API
app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(inventory.router, prefix="/api/inventory", tags=["inventory"])
app.include_router(crm_routes.router, prefix="/api/crm", tags=["crm"])
app.include_router(brain.router, prefix="/api/brain", tags=["brain transactional"])

@app.get("/", response_class=HTMLResponse)
async def index(request: Request, db: Session = Depends(deps.get_db)):
    try:
        current_user = await deps.get_current_user(request, db)
        
        # Sincronizar tasas para el dashboard
        try:
            current_rates = await rates.sync_rates_db(db, user_id=current_user.id)
        except Exception as e:
            print(f"Error syncing rates: {e}")
            current_rates = {"usd_oficial": 0.0, "usd_paralelo": 0.0, "eur_oficial": 0.0}
            
        # Preparar productos para el cotizador rápido
        oils = db.query(Product).filter(
            Product.category.in_([ProductCategory.ACEITE_MINERAL, ProductCategory.SEMI_SINTETICO, ProductCategory.SINTETICO])
        ).order_by(Product.name).all()
        
        filters = db.query(Product).filter(
            Product.category == ProductCategory.FILTRO
        ).order_by(Product.name).all()

        products_data = {
            "oils": [{"id": p.id, "name": f"{p.brand} - {p.name}" if p.brand else p.name, "price_usd": float(p.retail_price_usd or 0.0)} for p in oils],
            "filters": [{"id": p.id, "name": f"{p.brand} - {p.name}" if p.brand else p.name, "price_usd": float(p.retail_price_usd or 0.0)} for p in filters]
        }

        # Calcular Métricas Reales
        today = datetime.now().date()
        orders_today_query = db.query(ServiceOrder).filter(ServiceOrder.status == OrderStatus.COMPLETADA, func.date(ServiceOrder.date) == today)
        orders_today = orders_today_query.count()
        revenue_today = db.query(func.sum(ServiceOrder.total_amount_usd)).filter(ServiceOrder.status == OrderStatus.COMPLETADA, func.date(ServiceOrder.date) == today).scalar() or 0.0
        active_services = db.query(ServiceOrder).filter(ServiceOrder.status == OrderStatus.EN_EJECUCION).count()
        low_stock_count = db.query(Product).filter(Product.current_stock <= Product.min_stock).count()
        recent_sales = db.query(ServiceOrder).order_by(ServiceOrder.date.desc()).limit(5).all()

        return templates.TemplateResponse("index.html", {
            "request": request, 
            "user": current_user,
            "settings": settings,
            "rates": current_rates,
            "products_json": json.dumps(products_data),
            "now": datetime.now().strftime("%A, %d de %B de %Y"),
            "stats": {
                "orders_today": orders_today,
                "revenue_today": round(revenue_today, 2),
                "active_services": active_services,
                "low_stock_count": low_stock_count
            },
            "recent_sales": recent_sales
        })
    except HTTPException as e:
        if e.status_code == 401:
            return RedirectResponse(url="/login")
        raise e
    except Exception as e:
        import traceback
        print(f"ERROR in index route: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {
        "request": request,
        "settings": settings
    })

@app.get("/inventory", response_class=HTMLResponse)
async def inventory_page(request: Request, db: Session = Depends(deps.get_db)):
    try:
        current_user = await deps.get_current_user(request, db)
        
        from app.crud import inventory as crud_inventory
        products = crud_inventory.get_products(db)
        
        # Obtener tasa BCV oficial
        settings_db = db.query(models.SystemSettings).first()
        bcv_rate = settings_db.bcv_rate if settings_db else 1.0
        
        # Obtener tasa paralela (Binance) en tiempo real
        try:
            current_rates = await rates.fetch_rates()
            paralelo_rate = current_rates.get("usd_paralelo", bcv_rate)
        except Exception:
            paralelo_rate = bcv_rate

        # Preparar datos extendidos (PVP) para la vista
        for p in products:
            p.pvp = crud_inventory.calculate_pvp(p.average_unit_cost, bcv_rate)
            
        return templates.TemplateResponse("inventory.html", {
            "request": request,
            "user": current_user,
            "settings": settings,
            "products": products,
            "bcv_rate": bcv_rate,
            "paralelo_rate": paralelo_rate
        })
    except Exception as e:
        import traceback
        print(f"ERROR in index route: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/crm", response_class=HTMLResponse)
async def crm_page(request: Request, db: Session = Depends(deps.get_db)):
    try:
        current_user = await deps.get_current_user(request, db)
        from app.crud import crm as crud_crm
        clients = crud_crm.get_clients(db)
        
        clients_list = []
        for c in clients:
            c_dict = {
                "id": c.id,
                "full_name": c.full_name,
                "phone": c.phone or "",
                "address": c.address_reference or "",
                "total_spent": float(c.total_spent_usd or 0.0),
                "vehicles": []
            }
            for v in c.vehicles:
                v_dict = {
                    "id": v.id,
                    "plate": v.plate,
                    "brand": v.brand or "",
                    "model": v.model or "",
                    "year": v.year or "",
                    "engine_type": v.engine_type or "",
                    "recommended_viscosity": v.recommended_viscosity or "",
                    "capacity": v.oil_capacity_qts or "",
                    "filter_oil": v.filter_model_oil or "",
                    "filter_air": v.filter_model_air or "",
                    "odometer": v.current_odometer or "",
                    "qr": v.qr_uuid,
                    "service_count": v.service_count or 0,
                    "service_records": []
                }
                for sr in v.service_records:
                    v_dict["service_records"].append({
                        "id": sr.id,
                        "date": sr.date.isoformat() if sr.date else None,
                        "odometer": sr.odometer_at_service,
                        "service_type": sr.service_type,
                        "total_cost": float(sr.total_cost_usd or 0.0),
                        "payment_method": sr.payment_method or "",
                        "notes": sr.notes_technician or ""
                    })
                c_dict["vehicles"].append(v_dict)
            clients_list.append(c_dict)
            
        return templates.TemplateResponse("crm.html", {
            "request": request,
            "user": current_user,
            "settings": settings,
            "clients": clients,
            "clients_json": json.dumps(clients_list)
        })
    except Exception as e:
        import traceback
        print(f"ERROR in index route: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/quick-quote")
async def quick_quote(
    oil_id: Optional[int] = None, 
    oil_qty: float = 1.0, 
    filter_id: Optional[int] = None,
    include_labor: bool = False,
    include_logistics: bool = False,
    db: Session = Depends(deps.get_db)
):
    """Calcula un presupuesto rápido sin registrar nada."""
    try:
        total_usd = 0.0
        breakdown = []

        if oil_id:
            oil = db.query(Product).filter(Product.id == oil_id).first()
            if oil:
                sub = float(oil.retail_price_usd or 0.0) * oil_qty
                total_usd += sub
                breakdown.append({"item": oil.name, "subtotal": sub})

        if filter_id:
            f = db.query(Product).filter(Product.id == filter_id).first()
            if f:
                sub = float(f.retail_price_usd or 0.0)
                total_usd += sub
                breakdown.append({"item": f.name, "subtotal": sub})

        if include_labor:
            total_usd += 15.0
            breakdown.append({"item": "Mano de Obra", "subtotal": 15.0})

        if include_logistics:
            total_usd += 1.50
            breakdown.append({"item": "Logística", "subtotal": 1.50})

        # Obtener tasa BCV
        sys_config = db.query(SystemSettings).first()
        bcv_rate = sys_config.bcv_rate if sys_config else 1.0

        return {
            "total_usd": round(total_usd, 2),
            "total_bs": round(total_usd * bcv_rate, 2),
            "breakdown": breakdown
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/cerebro", response_class=HTMLResponse)
async def cerebro_page(request: Request, db: Session = Depends(deps.get_db)):
    """Módulo El Cerebro: Wizard de Orden de Servicio y Cobro."""
    try:
        current_user = await deps.get_current_user(request, db) # Ensure user is logged in
        # Clients Data (para buscar por placa o cliente)
        clients = db.query(Client).order_by(Client.full_name).all()
        clients_data = []
        for c in clients:
            for v in c.vehicles:
                clients_data.append({
                    "vehicle_id": v.id,
                    "plate": v.plate,
                    "brand": v.brand or "",
                    "model": v.model or "",
                    "year": v.year or "",
                    "capacity_qts": v.oil_capacity_qts or 0.0,
                    "last_odometer": v.current_odometer or 0,
                    "client_id": c.id,
                    "client_name": c.full_name,
                    "client_phone": c.phone
                })

        # Inventory Data
        oils = db.query(Product).filter(
            Product.category.in_([ProductCategory.ACEITE_MINERAL, ProductCategory.SEMI_SINTETICO, ProductCategory.SINTETICO])
        ).order_by(Product.name).all()
        
        filters = db.query(Product).filter(
            Product.category == ProductCategory.FILTRO
        ).order_by(Product.name).all()

        products_data = {
            "oils": [{"id": p.id, "name": f"{p.brand} - {p.name}" if p.brand else p.name, "brand": p.brand or "", "price_usd": p.retail_price_usd, "stock": p.current_stock} for p in oils],
            "filters": [{"id": p.id, "name": f"{p.brand} - {p.name}" if p.brand else p.name, "brand": p.brand or "", "price_usd": p.retail_price_usd, "stock": p.current_stock} for p in filters]
        }

        # System Config
        sys_config = db.query(SystemSettings).first()
        bcv_rate = sys_config.bcv_rate if sys_config else 1.0
        
        # Obtener tasa paralela (Binance) para cálculos de conversión preferidos del usuario
        try:
            from app.core import rates as rates_service
            current_rates = await rates_service.fetch_rates()
            paralelo_rate = current_rates.get("usd_paralelo", bcv_rate)
        except Exception:
            paralelo_rate = bcv_rate

        return templates.TemplateResponse("cerebro.html", {
            "request": request,
            "user": current_user,
            "settings": settings,
            "bcv_rate": bcv_rate,
            "paralelo_rate": paralelo_rate,
            "vehicles_json": json.dumps(clients_data),
            "products_json": json.dumps(products_data)
        })
    except Exception as e:
        import traceback
        print(f"ERROR in index route: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        import traceback
        error_msg = traceback.format_exc()
        # Intentar guardar en un log absoluto o relativo visible
        try:
            with open("error_cerebro.log", "w") as f:
                f.write(error_msg)
        except:
            pass
        print(f"CRITICAL ERROR in /cerebro: {e}")
        # Retornar con settings para evitar crash en base.html
        return templates.TemplateResponse("cerebro.html", {
            "request": request,
            "user": current_user if 'current_user' in locals() else None,
            "settings": settings,
            "bcv_rate": 1.0,
            "paralelo_rate": 1.0,
            "vehicles_json": "[]",
            "products_json": "{\"oils\": [], \"filters\": []}"
        })

@app.get("/cerebro/receipt/{order_id}", response_class=HTMLResponse)
async def receipt_page(order_id: int, request: Request, db: Session = Depends(deps.get_db)):
    """Vista de Recibo Digital para el cliente."""
    try:
        from app.models.models import ServiceOrder
        order = db.query(ServiceOrder).filter(ServiceOrder.id == order_id).first()
        if not order:
            raise HTTPException(status_code=404, detail="Recibo no encontrado")
        
        return templates.TemplateResponse("receipt_template.html", {
            "request": request,
            "order": order
        })
    except Exception as e:
        print(f"Error cargando recibo: {e}")
        return HTMLResponse("Error al cargar el recibo.")


@app.get("/v/{qr_uuid}", response_class=HTMLResponse)
async def vehicle_public(qr_uuid: str, db: Session = Depends(deps.get_db)):
    """Landing pública del QR — sin autenticación. NO expone datos personales del cliente."""
    from app.crud import crm as crud_crm
    vehicle = crud_crm.get_vehicle_by_uuid(db, qr_uuid)
    if not vehicle:
        return HTMLResponse("<h3>Ficha no encontrada</h3>", status_code=404)

    projection = crud_crm.project_next_service(
        last_odometer=vehicle.last_odometer or 0,
        last_service_date=vehicle.last_service_date or vehicle.created_at
    )
    wa_msg = (
        f"Hola, quiero agendar mi servicio para el vehículo {vehicle.plate} "
        f"({vehicle.brand or ''} {vehicle.model or ''})’."
    )
    return templates.TemplateResponse("vehicle_public.html", {
        "request": {},          # No se necesita request para esta template estática
        "vehicle": vehicle,
        "projection": projection,
        "whatsapp_number": "58412000000",  # Cambiar por número real de LubMovil
        "whatsapp_msg": wa_msg
    })
