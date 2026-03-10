"""
Script de inicialización y datos de prueba para LUBMOVIL 2.0.
Elimina la BD existente y la recrea con el schema actualizado + datos reales.
"""
import os
import sys

# Añadir el directorio raíz al path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Asegurar que la BD sea eliminada antes de importar los modelos
DB_PATH = "lubmovil.db"
if os.path.exists(DB_PATH):
    os.remove(DB_PATH)
    print(f"✓ Base de datos anterior eliminada.")

from app.db.session import engine, Base, SessionLocal
from app.models.models import User, UserRole, Product, ProductCategory, AuditLog, SystemSettings
from app.core.security import get_password_hash

# Crear todas las tablas con el nuevo schema
Base.metadata.create_all(bind=engine)
print("✓ Tablas creadas con el nuevo schema.")

db = SessionLocal()

# ─── USUARIOS ───────────────────────────────────────────────
users = [
    User(username="admin", hashed_password=get_password_hash("admin123"),
         full_name="Administrador LUBMOVIL", role=UserRole.ADMIN, is_active=True),
    User(username="vendedor1", hashed_password=get_password_hash("ventas123"),
         full_name="Carlos Méndez", role=UserRole.VENTAS, is_active=True),
    User(username="instalador1", hashed_password=get_password_hash("campo123"),
         full_name="Luis Rodríguez", role=UserRole.INSTALADOR, is_active=True),
]
for u in users:
    db.add(u)
db.commit()
print(f"✓ {len(users)} usuarios creados.")

# ─── PRODUCTOS DE PRUEBA ─────────────────────────────────────
products_data = [
    # Aceites Minerales
    dict(name="Aceite Mineral 20W50 Qt (946ml)", short_name="20W50 Mineral", barcode="7591234000001",
         brand="Mobil", viscosity="20W50", category=ProductCategory.ACEITE_MINERAL,
         box_price=24.00, units_per_box=12, initial_stock=48, min_stock=12,
         retail_price_usd=4.00, wholesale_price_usd=3.50, distributor_price_usd=3.00,
         compatibility="Motor a gasolina, uso general", is_favorite=True),
    dict(name="Aceite Mineral 15W40 Qt (946ml)", short_name="15W40 Mineral", barcode="7591234000002",
         brand="Shell Rimula", viscosity="15W40", category=ProductCategory.ACEITE_MINERAL,
         box_price=22.00, units_per_box=12, initial_stock=36, min_stock=12,
         retail_price_usd=3.80, wholesale_price_usd=3.30, distributor_price_usd=2.80,
         compatibility="Motores gasolina y diesel", is_favorite=True),
    # Semi-sintéticos
    dict(name="Aceite Semi-sint. 10W30 Qt", short_name="10W30 Semi", barcode="7591234000003",
         brand="Castrol", viscosity="10W30", category=ProductCategory.SEMI_SINTETICO,
         box_price=30.00, units_per_box=12, initial_stock=24, min_stock=6,
         retail_price_usd=5.20, wholesale_price_usd=4.60, distributor_price_usd=4.00,
         compatibility="Gasolina, tecnología moderna EFI"),
    dict(name="Aceite Semi-sint. 5W30 Qt", short_name="5W30 Semi", barcode="7591234000004",
         brand="Gulf", viscosity="5W30", category=ProductCategory.SEMI_SINTETICO,
         box_price=32.00, units_per_box=12, initial_stock=18, min_stock=6,
         retail_price_usd=5.50, wholesale_price_usd=4.80, distributor_price_usd=4.20,
         compatibility="Motores modernos gasolina turbo/no turbo"),
    # Sintéticos
    dict(name="Aceite Full Sintético 5W40 Qt", short_name="5W40 Sintético", barcode="7591234000005",
         brand="Mobil 1", viscosity="5W40", category=ProductCategory.SINTETICO,
         box_price=55.00, units_per_box=12, initial_stock=12, min_stock=4,
         retail_price_usd=8.00, wholesale_price_usd=7.00, distributor_price_usd=6.20,
         compatibility="Motores gasolina y diesel modernos, turbo"),
    dict(name="Aceite Full Sintético 0W20 Qt", short_name="0W20 Sintético", barcode="7591234000006",
         brand="Castrol Edge", viscosity="0W20", category=ProductCategory.SINTETICO,
         box_price=60.00, units_per_box=12, initial_stock=8, min_stock=4,
         retail_price_usd=9.00, wholesale_price_usd=7.80, distributor_price_usd=7.00,
         compatibility="Motores Toyota, Honda nuevos generación 2018+"),
    # Filtros
    dict(name="Filtro de Aceite Kia Picanto / Spark", short_name="Filtro Kia/Spark", barcode="7591234000010",
         brand="Japanparts", viscosity=None, category=ProductCategory.FILTRO,
         box_price=18.00, units_per_box=10, initial_stock=20, min_stock=5,
         retail_price_usd=3.50, wholesale_price_usd=3.00, distributor_price_usd=2.50,
         compatibility="Kia Picanto 2005-2020 / Chevrolet Spark", is_favorite=True),
    dict(name="Filtro de Aceite Toyota Corolla", short_name="Filtro Corolla", barcode="7591234000011",
         brand="Toyota OEM", viscosity=None, category=ProductCategory.FILTRO,
         box_price=22.00, units_per_box=10, initial_stock=15, min_stock=5,
         retail_price_usd=4.50, wholesale_price_usd=4.00, distributor_price_usd=3.50,
         compatibility="Toyota Corolla 1998-2022 / Camry"),
    dict(name="Filtro de Aceite Ford Transit", short_name="Filtro Transit", barcode="7591234000012",
         brand="Mahle", viscosity=None, category=ProductCategory.FILTRO,
         box_price=25.00, units_per_box=10, initial_stock=4, min_stock=5,
         retail_price_usd=5.00, wholesale_price_usd=4.50, distributor_price_usd=4.00,
         compatibility="Ford Transit 2006-2020 Diesel"),
    # Aditivos
    dict(name="Aditivo Limpia Inyectores", short_name="Limpia Inyect.", barcode="7591234000020",
         brand="STP", viscosity=None, category=ProductCategory.ADITIVO,
         box_price=15.00, units_per_box=6, initial_stock=10, min_stock=3,
         retail_price_usd=5.50, wholesale_price_usd=5.00, distributor_price_usd=4.50,
         sell_at_bulk=True, compatibility="Universal gasolina"),
]

created = 0
for pd in products_data:
    initial = pd.pop("initial_stock")
    unit_cost = pd["box_price"] / pd["units_per_box"]
    product = Product(**pd, average_unit_cost=unit_cost, current_stock=initial)
    db.add(product)
    created += 1

db.commit()
print(f"✓ {created} productos de prueba creados.")

# ─── CONFIGURACIÓN DE SISTEMA ─────────────────────────────────
settings = SystemSettings(bcv_rate=433.17)
db.add(settings)
db.commit()
print(f"✓ Configuración del sistema inicializada (Tasa BCV: 433.17).")

# ─── CLIENTES Y VEHÍCULOS DE PRUEBA (CRM) ─────────────────────
from app.models.models import Client, Vehicle, VehicleType, VehicleStatus
from datetime import datetime, timedelta

crm_data = [
    {
        "client": dict(full_name="Juan Carlos Méndez", phone="584141234567", address="El Cafetal"),
        "vehicles": [
            dict(plate="AB123CD", qr_uuid="A1B2C3D4", type=VehicleType.CARRO,
                 brand="Toyota", model="Corolla", year=2018, engine_v="1.6",
                 recommended_viscosity="5W30", oil_capacity_liters=4.0, filter_code="PH6607",
                 last_odometer=85000, last_service_date=datetime.utcnow() - timedelta(days=70),
                 status=VehicleStatus.ACTIVO),
        ]
    },
    {
        "client": dict(full_name="María González Torres", phone="584121234567", address="Las Mercedes"),
        "vehicles": [
            dict(plate="XY456EF", qr_uuid="X4Y5Z6W7", type=VehicleType.CAMIONETA,
                 brand="Ford", model="Explorer", year=2020, engine_v="3.5",
                 recommended_viscosity="5W20", oil_capacity_liters=5.7, filter_code="FL910S",
                 last_odometer=32000, last_service_date=datetime.utcnow() - timedelta(days=30),
                 status=VehicleStatus.ACTIVO),
            dict(plate="MN789GH", qr_uuid="M7N8O9P0", type=VehicleType.MOTO,
                 brand="Honda", model="CB190R", year=2022, engine_v="0.19",
                 recommended_viscosity="10W40", oil_capacity_liters=1.0, filter_code="HF204",
                 last_odometer=12000, last_service_date=datetime.utcnow() - timedelta(days=10),
                 status=VehicleStatus.ACTIVO),
        ]
    },
    {
        "client": dict(full_name="Pedro Ramírez Silva", phone="584161234567", address="Sabana Grande"),
        "vehicles": [
            dict(plate="DF321IJ", qr_uuid="D3E4F5G6", type=VehicleType.PESADO,
                 brand="Mercedes-Benz", model="Sprinter", year=2015, engine_v="2.2",
                 recommended_viscosity="15W40", oil_capacity_liters=8.0, filter_code="W940/25",
                 last_odometer=210000, last_service_date=datetime.utcnow() - timedelta(days=120),
                 status=VehicleStatus.ACTIVO),
            dict(plate="GH654KL", qr_uuid="G6H7I8J9", type=VehicleType.CARRO,
                 brand="Kia", model="Picanto", year=2019, engine_v="1.2",
                 recommended_viscosity="5W30", oil_capacity_liters=3.0, filter_code="C-225",
                 last_odometer=55000, last_service_date=datetime.utcnow() - timedelta(days=45),
                 status=VehicleStatus.ACTIVO),
        ]
    },
]

for entry in crm_data:
    c = Client(**entry["client"])
    db.add(c)
    db.flush()
    for vd in entry["vehicles"]:
        v = Vehicle(client_id=c.id, **vd)
        db.add(v)

db.commit()
print(f"✓ 3 clientes y 5 vehículos de prueba creados con QR.")

db.close()
print("\n✅ Base de datos lista. Inicia el servidor con:")
print("   python -m uvicorn app.main:app --reload")
