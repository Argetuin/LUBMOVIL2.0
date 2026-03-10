from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from typing import List, Optional
import csv
import io
import os
import shutil
import uuid
from app.api import deps
from app.crud import inventory
from app.models.models import User, UserRole, SystemSettings, ProductCategory
from app.schemas import schemas

router = APIRouter()

@router.get("/products", response_model=List[schemas.Product])
def read_products(
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    category: Optional[str] = None
):
    products = inventory.get_products(db)
    if category:
        products = [p for p in products if p.category == category]
    
    # Si es ADMIN, devolvemos todo. Si es VENTAS, el schema ocultará costos si se configura.
    # Pero para ser estrictos, limpiaremos los campos manualmente si no es admin.
    if current_user.role != UserRole.ADMIN:
        for p in products:
            p.box_price = 0.0
            p.average_unit_cost = 0.0
            
    return products

@router.post("/products", response_model=schemas.Product)
def create_product(
    product: schemas.ProductCreate,
    db: Session = Depends(deps.get_db),
    admin_user: User = Depends(deps.role_required([UserRole.ADMIN]))
):
    return inventory.create_product(db, product, user_id=admin_user.id)

@router.post("/kits", response_model=schemas.Kit)
def create_kit(
    kit: schemas.KitCreate,
    db: Session = Depends(deps.get_db),
    admin_user: User = Depends(deps.role_required([UserRole.ADMIN]))
):
    return inventory.create_kit(db, kit, user_id=admin_user.id)

@router.get("/calculate-pvp/{product_id}")
def get_product_pvp(
    product_id: int,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user)
):
    db_product = inventory.get_product(db, product_id)
    if not db_product:
        raise HTTPException(status_code=404, detail="Producto no encontrado")
    
    settings = db.query(SystemSettings).first()
    bcv_rate = settings.bcv_rate if settings else 1.0
    
    # Precio dinámico basado en PMP + margen + logística
    price_info = inventory.calculate_pvp(db_product.average_unit_cost, bcv_rate)
    return price_info
@router.put("/products/{product_id}")
def update_product_prices(
    product_id: int,
    data: schemas.ProductUpdate,
    db: Session = Depends(deps.get_db),
    admin_user: User = Depends(deps.role_required([UserRole.ADMIN]))
):
    db_product = inventory.get_product(db, product_id)
    if not db_product:
        raise HTTPException(status_code=404, detail="Producto no encontrado")
    
    updated = inventory.update_product(db, db_product, data, user_id=admin_user.id)
    return {"ok": True, "product_id": updated.id, "name": updated.name}

@router.post("/products/{product_id}/stock")
def add_stock(
    product_id: int,
    box_price: float,
    quantity: int,
    db: Session = Depends(deps.get_db),
    admin_user: User = Depends(deps.role_required([UserRole.ADMIN]))
):
    db_product = inventory.get_product(db, product_id)
    if not db_product:
        raise HTTPException(status_code=404, detail="Producto no encontrado")
    
    updated = inventory.add_stock_pmp(db, db_product, box_price, quantity, user_id=admin_user.id)
    return {"ok": True, "new_stock": updated.current_stock, "new_pmp": updated.average_unit_cost}

@router.delete("/products/{product_id}")
def delete_product(
    product_id: int,
    db: Session = Depends(deps.get_db),
    admin_user: User = Depends(deps.role_required([UserRole.ADMIN]))
):
    db_product = inventory.get_product(db, product_id)
    if not db_product:
        raise HTTPException(status_code=404, detail="Producto no encontrado")
    
    inventory.delete_product(db, db_product, user_id=admin_user.id)
    return {"ok": True}

@router.get("/export")
def export_products_csv(
    db: Session = Depends(deps.get_db),
    admin_user: User = Depends(deps.role_required([UserRole.ADMIN, UserRole.VENTAS]))
):
    products = inventory.get_products(db)
    output = io.StringIO()
    writer = csv.writer(output, delimiter=',', quoting=csv.QUOTE_MINIMAL)
    writer.writerow([
        "name", "barcode", "brand", "viscosity", "category",
        "box_price", "units_per_box", "retail_price_usd", "wholesale_price_usd",
        "distributor_price_usd", "current_stock", "min_stock"
    ])
    for p in products:
        writer.writerow([
            p.name, p.barcode or "", p.brand or "", p.viscosity or "", p.category.value,
            p.box_price, p.units_per_box, p.retail_price_usd, p.wholesale_price_usd,
            p.distributor_price_usd, p.current_stock, p.min_stock
        ])
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=inventario_lubmovil.csv"}
    )

@router.post("/import")
async def import_products_csv(
    file: UploadFile = File(...),
    db: Session = Depends(deps.get_db),
    admin_user: User = Depends(deps.role_required([UserRole.ADMIN]))
):
    if not file.filename.endswith('.csv'):
        raise HTTPException(status_code=400, detail="Debe ser un archivo CSV")
    
    contents = await file.read()
    decoded = contents.decode('utf-8', errors='ignore')
    reader = csv.DictReader(io.StringIO(decoded))
    
    imported_count = 0
    for row in reader:
        try:
            # Buscar categoría válida o usar por defecto
            category_str = row.get("category", "").strip()
            category_enum = ProductCategory.ADITIVO
            for cat in ProductCategory:
                if cat.value.lower() == category_str.lower():
                    category_enum = cat
                    break
                    
            prod_data = schemas.ProductCreate(
                name=row.get("name", "Producto CSV"),
                barcode=row.get("barcode", "") or None,
                brand=row.get("brand", "") or None,
                viscosity=row.get("viscosity", "") or None,
                category=category_enum,
                box_price=float(row.get("box_price", 0) or 0),
                units_per_box=int(row.get("units_per_box", 1) or 1),
                retail_price_usd=float(row.get("retail_price_usd", 0) or 0),
                wholesale_price_usd=float(row.get("wholesale_price_usd", 0) or 0),
                distributor_price_usd=float(row.get("distributor_price_usd", 0) or 0),
                initial_stock=int(row.get("current_stock", 0) or 0),
                min_stock=int(row.get("min_stock", 5) or 5)
            )
            inventory.create_product(db, prod_data, user_id=admin_user.id)
            imported_count += 1
        except Exception as e:
            print(f"Error importando fila: {row} -> {e}")
            continue
            
    return {"ok": True, "imported": imported_count}

@router.post("/products/{product_id}/image")
async def upload_product_image(
    product_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(deps.get_db),
    admin_user: User = Depends(deps.role_required([UserRole.ADMIN]))
):
    db_product = inventory.get_product(db, product_id)
    if not db_product:
        raise HTTPException(status_code=404, detail="Producto no encontrado")
        
    allowed_types = ["image/jpeg", "image/png", "image/webp"]
    if file.content_type not in allowed_types:
        raise HTTPException(status_code=400, detail="El archivo debe ser JPG, PNG o WEBP")
        
    ext = file.filename.split('.')[-1]
    filename = f"{uuid.uuid4().hex}.{ext}"
    images_dir = "app/static/product_images"
    os.makedirs(images_dir, exist_ok=True)
    
    file_path = os.path.join(images_dir, filename)
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
        
    db_product.image_path = f"/static/product_images/{filename}"
    db.commit()
    return {"ok": True, "image_path": db_product.image_path}

