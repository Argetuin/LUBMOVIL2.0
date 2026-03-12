from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Float, Enum as SQLEnum
from sqlalchemy.orm import relationship
from datetime import datetime
import enum
from app.db.session import Base

class UserRole(str, enum.Enum):
    ADMIN = "admin"
    VENTAS = "ventas"
    INSTALADOR = "instalador"

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    full_name = Column(String)
    role = Column(SQLEnum(UserRole), default=UserRole.INSTALADOR)
    is_active = Column(Boolean, default=True)
    last_login = Column(DateTime, default=datetime.utcnow)

class ProductCategory(str, enum.Enum):
    ACEITE_MINERAL = "Aceite Mineral"
    SEMI_SINTETICO = "Semi-sintético"
    SINTETICO = "Sintético"
    FILTRO = "Filtro"
    ADITIVO = "Aditivo"

class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True, nullable=False)
    short_name = Column(String)                         # Para tickets/reportes
    barcode = Column(String, unique=True, index=True)   # Código de barras
    brand = Column(String, index=True)
    viscosity = Column(String)
    category = Column(SQLEnum(ProductCategory))
    
    # Precios y Costos
    box_price = Column(Float, default=0.0)
    units_per_box = Column(Integer, default=1)
    average_unit_cost = Column(Float, default=0.0)
    retail_price_usd = Column(Float, default=0.0)       # Precio al detal (PVP)
    wholesale_price_usd = Column(Float, default=0.0)    # Precio al mayor
    distributor_price_usd = Column(Float, default=0.0)  # Precio distribuidor
    
    # Stock
    current_stock = Column(Integer, default=0)
    min_stock = Column(Integer, default=5)
    
    # Flags de Control
    is_favorite = Column(Boolean, default=False)        # Alta rotación
    sell_at_bulk = Column(Boolean, default=False)       # Venta por medida
    control_inventory = Column(Boolean, default=True)   # Descontar stock en ventas
    
    compatibility = Column(String)
    image_path = Column(String, nullable=True)   # Ruta relativa: /static/product_images/{filename}


class Kit(Base):
    __tablename__ = "kits"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True, nullable=False)
    description = Column(String)
    
    items = relationship("KitItem", back_populates="kit", cascade="all, delete-orphan")

class KitItem(Base):
    __tablename__ = "kit_items"

    id = Column(Integer, primary_key=True, index=True)
    kit_id = Column(Integer, ForeignKey("kits.id"))
    product_id = Column(Integer, ForeignKey("products.id"))
    quantity = Column(Integer, default=1)

    kit = relationship("Kit", back_populates="items")
    product = relationship("Product")

class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    action = Column(String)
    description = Column(String)
    timestamp = Column(DateTime, default=datetime.utcnow)

    user = relationship("User")

class SystemSettings(Base):
    __tablename__ = "system_settings"

    id = Column(Integer, primary_key=True, index=True)
    bcv_rate = Column(Float, default=0.0)
    last_api_sync = Column(DateTime)

# ─── CRM ELITE ────────────────────────────────────────────────────────────────

class Client(Base):
    __tablename__ = "clients"

    id = Column(Integer, primary_key=True, index=True)
    full_name = Column(String, index=True, nullable=False)
    phone = Column(String, index=True)          # Formato internacional ej: 584121234567
    email = Column(String, nullable=True)
    address_reference = Column(String)                     # Zona/Sector
    total_spent_usd = Column(Float, default=0.0)     # Acumulativo en USD
    created_at = Column(DateTime, default=datetime.utcnow)

    vehicles = relationship("Vehicle", back_populates="client", cascade="all, delete-orphan")


class VehicleType(str, enum.Enum):
    MOTO      = "Moto"
    CARRO     = "Carro"
    CAMIONETA = "Camioneta"
    PESADO    = "Pesado"


class VehicleStatus(str, enum.Enum):
    ACTIVO   = "Activo"
    INACTIVO = "Inactivo"


class Vehicle(Base):
    __tablename__ = "vehicles"

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.id"), nullable=False)

    # Identificación
    plate = Column(String, unique=True, index=True, nullable=False)  # Siempre MAYÚSCULAS sin guiones
    qr_uuid = Column(String, unique=True, index=True, nullable=False)
    qr_scan_count = Column(Integer, default=0)
    status = Column(SQLEnum(VehicleStatus), default=VehicleStatus.ACTIVO)

    # Datos del Vehículo
    type = Column(SQLEnum(VehicleType), default=VehicleType.CARRO)
    brand = Column(String)
    model = Column(String)
    year = Column(Integer)
    engine_type = Column(String)                   # Ej: "1.6", "5.7"

    # Ficha Técnica Pro
    oil_capacity_qts = Column(Float)            # Capacidad en Qts/Litros
    recommended_viscosity = Column(String)      # Ej: "15W40", "5W30"
    filter_model_oil = Column(String)           # Código del filtro de aceite
    filter_model_air = Column(String)           # Código del filtro de aire

    # Estado Actual
    current_odometer = Column(Integer, default=0)             # Último KM registrado
    last_service_date = Column(DateTime, nullable=True)        # Fecha del último cambio
    service_count = Column(Integer, default=0)                 # Contador para programa de lealtad

    created_at = Column(DateTime, default=datetime.utcnow)

    client = relationship("Client", back_populates="vehicles")
    service_records = relationship("ServiceRecord", back_populates="vehicle", cascade="all, delete-orphan", order_by="desc(ServiceRecord.date)")


class ServiceRecord(Base):
    __tablename__ = "service_records"

    id = Column(Integer, primary_key=True, index=True)
    vehicle_id = Column(Integer, ForeignKey("vehicles.id"), nullable=False)
    date = Column(DateTime, default=datetime.utcnow)
    
    # Datos de este evento específico
    odometer_at_service = Column(Integer, nullable=False)
    service_type = Column(String, default="Cambio de Aceite")
    
    # Guarda un resumen JSON de los repuestos consumidos Ej: [{"product_id": 1, "name": "Aceite 15w40", "qty": 4}]
    products_json = Column(String, nullable=True)
    
    total_cost_usd = Column(Float, default=0.0)
    payment_method = Column(String, nullable=True)
    notes_technician = Column(String, nullable=True)
    
    is_loyalty_applied = Column(Boolean, default=False)

    vehicle = relationship("Vehicle", back_populates="service_records")
