from typing import Optional, List
from pydantic import BaseModel, ConfigDict
from datetime import datetime
from app.models.models import UserRole, ProductCategory

# --- Usuario Schemas ---
class UserBase(BaseModel):
    username: str
    full_name: Optional[str] = None
    role: UserRole = UserRole.INSTALADOR
    is_active: Optional[bool] = True

class UserCreate(UserBase):
    password: str

class UserUpdate(UserBase):
    password: Optional[str] = None

class UserInDBBase(BaseModel):
    id: int
    username: str
    full_name: Optional[str] = None
    role: UserRole
    is_active: bool
    last_login: Optional[datetime] = None
    
    model_config = ConfigDict(from_attributes=True)

class User(UserInDBBase):
    pass

# --- Producto Schemas ---
class ProductBase(BaseModel):
    name: str
    brand: Optional[str] = None
    viscosity: Optional[str] = None
    category: ProductCategory
    min_stock: int = 5
    compatibility: Optional[str] = None

class ProductCreate(ProductBase):
    box_price: float
    units_per_box: int
    initial_stock: int = 0
    barcode: Optional[str] = None
    short_name: Optional[str] = None
    retail_price_usd: Optional[float] = None
    wholesale_price_usd: Optional[float] = 0.0
    distributor_price_usd: Optional[float] = 0.0
    is_favorite: bool = False
    sell_at_bulk: bool = False
    control_inventory: bool = True

class ProductUpdate(BaseModel):
    name: Optional[str] = None
    brand: Optional[str] = None
    viscosity: Optional[str] = None
    category: Optional[ProductCategory] = None
    min_stock: Optional[int] = None
    compatibility: Optional[str] = None
    current_stock: Optional[int] = None
    average_unit_cost: Optional[float] = None
    retail_price_usd: Optional[float] = None
    wholesale_price_usd: Optional[float] = None
    distributor_price_usd: Optional[float] = None
    is_favorite: Optional[bool] = None

class Product(ProductBase):
    id: int
    current_stock: int
    average_unit_cost: float
    # box_price y average_unit_cost se ocultarán para el rol VENTAS en la API
    
    model_config = ConfigDict(from_attributes=True)

class ProductAdmin(Product):
    box_price: float
    units_per_box: int

# --- Kit Schemas ---
class KitItemBase(BaseModel):
    product_id: int
    quantity: int

class KitItemCreate(KitItemBase):
    pass

class KitItemInDB(KitItemBase):
    id: int
    kit_id: int
    
    model_config = ConfigDict(from_attributes=True)

class KitBase(BaseModel):
    name: str
    description: Optional[str] = None

class KitCreate(KitBase):
    items: List[KitItemCreate]

class Kit(KitBase):
    id: int
    items: List[KitItemInDB]
    
    model_config = ConfigDict(from_attributes=True)

# --- Seguridad Schemas ---
class Token(BaseModel):
    access_token: str
    token_type: str

class TokenPayload(BaseModel):
    sub: Optional[str] = None

# ─── CRM ELITE ────────────────────────────────────────────────────────────────

from app.models.models import VehicleType, VehicleStatus

class VehicleBase(BaseModel):
    plate: str
    type: VehicleType = VehicleType.CARRO
    brand: Optional[str] = None
    model: Optional[str] = None
    year: Optional[int] = None
    engine_v: Optional[str] = None
    oil_capacity_liters: Optional[float] = None
    recommended_viscosity: Optional[str] = None
    filter_code: Optional[str] = None
    last_odometer: Optional[int] = None

class VehicleCreate(VehicleBase):
    pass

class VehicleUpdate(BaseModel):
    brand: Optional[str] = None
    model: Optional[str] = None
    year: Optional[int] = None
    engine_v: Optional[str] = None
    oil_capacity_liters: Optional[float] = None
    recommended_viscosity: Optional[str] = None
    filter_code: Optional[str] = None
    last_odometer: Optional[int] = None
    last_service_date: Optional[datetime] = None
    status: Optional[VehicleStatus] = None

class VehicleResponse(VehicleBase):
    id: int
    client_id: int
    qr_uuid: str
    qr_scan_count: int
    status: VehicleStatus
    last_service_date: Optional[datetime] = None
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)

class ClientBase(BaseModel):
    full_name: str
    phone: Optional[str] = None
    address: Optional[str] = None

class ClientCreate(ClientBase):
    # Primer vehículo opcional al crear el cliente
    vehicle: Optional[VehicleCreate] = None

class ClientUpdate(BaseModel):
    full_name: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    loyalty_points: Optional[int] = None

class ClientResponse(ClientBase):
    id: int
    total_spent: float
    loyalty_points: int
    created_at: Optional[datetime] = None
    vehicles: List[VehicleResponse] = []

    model_config = ConfigDict(from_attributes=True)
