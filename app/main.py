from fastapi import FastAPI, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from datetime import datetime
import locale

from app.api.routes import auth, inventory, crm as crm_routes
from app.core.config import settings
from app.api import deps
from app.models import models
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

# Incluir rutas de API
app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(inventory.router, prefix="/api/inventory", tags=["inventory"])
app.include_router(crm_routes.router, prefix="/api/crm", tags=["crm"])

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
            
        return templates.TemplateResponse("index.html", {
            "request": request, 
            "user": current_user,
            "settings": settings,
            "rates": current_rates,
            "now": datetime.now().strftime("%A, %d de %B de %Y")
        })
    except HTTPException:
        return RedirectResponse(url="/login")

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
    except HTTPException:
        return RedirectResponse(url="/login")

@app.get("/crm", response_class=HTMLResponse)
async def crm_page(request: Request, db: Session = Depends(deps.get_db)):
    try:
        current_user = await deps.get_current_user(request, db)
        from app.crud import crm as crud_crm
        clients = crud_crm.get_clients(db)
        return templates.TemplateResponse("crm.html", {
            "request": request,
            "user": current_user,
            "settings": settings,
            "clients": clients
        })
    except HTTPException:
        return RedirectResponse(url="/login")


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
