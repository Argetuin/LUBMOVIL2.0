from sqlalchemy.orm import Session
from app.models.models import Product, Kit, KitItem, AuditLog, SystemSettings
from app.schemas.schemas import ProductCreate, KitCreate
from typing import List, Optional

def get_product(db: Session, product_id: int):
    return db.query(Product).filter(Product.id == product_id).first()

def get_products(db: Session, skip: int = 0, limit: int = 100):
    return db.query(Product).offset(skip).limit(limit).all()

def create_product(db: Session, product: ProductCreate, user_id: int):
    # Calcular costo unitario inicial
    unit_cost = product.box_price / product.units_per_box if product.units_per_box > 0 else 0
    # Si no se especifica precio de venta, aplicar fórmula base
    retail = product.retail_price_usd or (unit_cost + 15.0 + 1.50)
    
    db_product = Product(
        name=product.name,
        short_name=product.short_name,
        barcode=product.barcode,
        brand=product.brand,
        viscosity=product.viscosity,
        category=product.category,
        box_price=product.box_price,
        units_per_box=product.units_per_box,
        average_unit_cost=unit_cost,
        retail_price_usd=retail,
        wholesale_price_usd=product.wholesale_price_usd or 0.0,
        distributor_price_usd=product.distributor_price_usd or 0.0,
        current_stock=product.initial_stock,
        min_stock=product.min_stock,
        compatibility=product.compatibility,
        is_favorite=product.is_favorite,
        sell_at_bulk=product.sell_at_bulk,
        control_inventory=product.control_inventory
    )
    db.add(db_product)
    db.commit()
    db.refresh(db_product)
    
    audit = AuditLog(
        user_id=user_id,
        action="CREATE_PRODUCT",
        description=f"Producto creado: {product.name}. Stock inicial: {product.initial_stock}"
    )
    db.add(audit)
    db.commit()
    return db_product

def update_product(db: Session, db_product: Product, data, user_id: int):
    """Actualiza precios y flags del producto. Acepta cero como valor válido."""
    # model_fields_set contiene SOLO los campos que el cliente envió explícitamente
    for field in data.model_fields_set:
        value = getattr(data, field)
        if hasattr(db_product, field):
            setattr(db_product, field, value)
    audit = AuditLog(
        user_id=user_id, action="UPDATE_PRODUCT",
        description=f"Precios actualizados: {db_product.name}"
    )
    db.add(audit)
    db.commit()
    db.refresh(db_product)
    return db_product

def delete_product(db: Session, db_product: Product, user_id: int):
    product_name = db_product.name
    product_id = db_product.id
    db.delete(db_product)
    audit = AuditLog(
        user_id=user_id, action="DELETE_PRODUCT",
        description=f"Producto eliminado: [{product_id}] {product_name}"
    )
    db.add(audit)
    db.commit()

def add_stock_pmp(db: Session, db_product: Product, box_price: float, quantity: int, user_id: int):
    """Entrada de mercancía con cálculo de Costo Promedio Ponderado."""
    new_unit_cost = box_price / db_product.units_per_box if db_product.units_per_box > 0 else box_price
    total_stock = db_product.current_stock + quantity
    if total_stock > 0:
        total_value = (db_product.current_stock * db_product.average_unit_cost) + (quantity * new_unit_cost)
        db_product.average_unit_cost = total_value / total_stock
    db_product.current_stock = total_stock
    db_product.box_price = box_price
    audit = AuditLog(
        user_id=user_id, action="ADD_STOCK",
        description=f"Entrada stock: {db_product.name}. +{quantity} uds. Nuevo PMP: ${db_product.average_unit_cost:.2f}"
    )
    db.add(audit)
    db.commit()
    db.refresh(db_product)
    return db_product

def add_product_stock_pmp(db: Session, product_id: int, new_quantity: int, new_box_price: float, user_id: int):
    """
    Actualiza el stock y el Costo Promedio Ponderado (PMP).
    Fórmula: ((Stock_Actual * Costo_Promedio_Actual) + (Nueva_Cantidad * Nuevo_Costo_Unitario)) / (Stock_Total)
    """
    db_product = get_product(db, product_id)
    if not db_product:
        return None
    
    new_unit_cost = new_box_price / db_product.units_per_box if db_product.units_per_box > 0 else 0
    
    if db_product.current_stock + new_quantity > 0:
        total_value = (db_product.current_stock * db_product.average_unit_cost) + (new_quantity * new_unit_cost)
        db_product.average_unit_cost = total_value / (db_product.current_stock + new_quantity)
    else:
        db_product.average_unit_cost = new_unit_cost

    db_product.current_stock += new_quantity
    db_product.box_price = new_box_price # Actualiza el último precio de caja
    
    audit = AuditLog(
        user_id=user_id,
        action="UPDATE_STOCK_PMP",
        description=f"Entrada stock: {db_product.name}. Cant:+{new_quantity}. Nuevo PMP: {db_product.average_unit_cost}"
    )
    db.add(audit)
    db.commit()
    db.refresh(db_product)
    return db_product

def create_kit(db: Session, kit_data: KitCreate, user_id: int):
    db_kit = Kit(name=kit_data.name, description=kit_data.description)
    db.add(db_kit)
    db.flush() # Para obtener el kit.id
    
    for item in kit_data.items:
        db_item = KitItem(
            kit_id=db_kit.id,
            product_id=item.product_id,
            quantity=item.quantity
        )
        db.add(db_item)
    
    audit = AuditLog(
        user_id=user_id,
        action="CREATE_KIT",
        description=f"Kit creado: {kit_data.name} con {len(kit_data.items)} productos"
    )
    db.add(audit)
    db.commit()
    db.refresh(db_kit)
    return db_kit

def calculate_pvp(total_cost_usd: float, bcv_rate: float):
    """
    Fórmula: (Costo) + Margen_Fijo ($15) + Gastos_Logística ($1.50)
    Sincronizado con USD y Bs mediante tasa BCV.
    """
    pvp_usd = total_cost_usd + 15.0 + 1.50
    pvp_bs = pvp_usd * bcv_rate
    return {"usd": pvp_usd, "bs": pvp_bs}

def sell_kit_atomic(db: Session, kit_id: int, user_id: int):
    """
    Verifica stock y descuenta atómicamente todos los componentes de un kit.
    """
    db_kit = db.query(Kit).filter(Kit.id == kit_id).first()
    if not db_kit:
        raise Exception("Kit no encontrado")
    
    # Verificar stock primero
    for item in db_kit.items:
        if item.product.current_stock < item.quantity:
            raise Exception(f"Stock insuficiente para el producto: {item.product.name}")
    
    # Descontar stock
    for item in db_kit.items:
        item.product.current_stock -= item.quantity
    
    audit = AuditLog(
        user_id=user_id,
        action="SELL_KIT",
        description=f"Venta de Kit: {db_kit.name}. Stock descontado."
    )
    db.add(audit)
    db.commit()
    return True
