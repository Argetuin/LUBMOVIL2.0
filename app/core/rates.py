import httpx
from datetime import datetime
from typing import Optional, Dict
from sqlalchemy.orm import Session
from app.models.models import SystemSettings, AuditLog

API_URLS = {
    "usd_oficial": "https://ve.dolarapi.com/v1/dolares/oficial",
    "usd_paralelo": "https://ve.dolarapi.com/v1/dolares/paralelo",
    "eur_oficial": "https://ve.dolarapi.com/v1/euros/oficial"
}

async def fetch_rates() -> Dict[str, float]:
    rates = {}
    async with httpx.AsyncClient() as client:
        for key, url in API_URLS.items():
            try:
                response = await client.get(url, timeout=10.0)
                if response.status_code == 200:
                    data = response.json()
                    rates[key] = float(data["promedio"])
            except Exception as e:
                print(f"Error fetching {key}: {e}")
                rates[key] = 0.0
    return rates

async def sync_rates_db(db: Session, user_id: Optional[int] = None):
    rates = await fetch_rates()
    
    # Store USD Oficial as primary in SystemSettings
    settings = db.query(SystemSettings).first()
    if not settings:
        settings = SystemSettings(
            bcv_rate=rates.get("usd_oficial", 0.0),
            cash_rate=rates.get("usd_paralelo", rates.get("usd_oficial", 0.0)) # Default to parallel if possible
        )
        db.add(settings)
    else:
        settings.bcv_rate = rates.get("usd_oficial", 0.0)
        # If cash_rate is 0, initialize it with parallel or official
        if settings.cash_rate == 0:
            settings.cash_rate = rates.get("usd_paralelo", rates.get("usd_oficial", 0.0))
    
    settings.last_api_sync = datetime.utcnow()
    
    # Añadir cash_rate a la respuesta para el frontend
    rates["cash_rate"] = settings.cash_rate
    
    # Log the sync
    audit = AuditLog(
        user_id=user_id,
        action="SYNC_RATES",
        description=f"Tasas sincronizadas: USD Oficial {rates.get('usd_oficial')}, Paralelo {rates.get('usd_paralelo')}, Efectivo {settings.cash_rate}"
    )
    db.add(audit)
    db.commit()
    return rates
