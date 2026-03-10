from datetime import timedelta, datetime
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, Response, Form, Request
from sqlalchemy.orm import Session
from app.api import deps
from app.core import security
from app.core.config import settings
from app.models.models import User, AuditLog
from app.schemas import schemas

router = APIRouter()

@router.post("/login")
def login(
    response: Response,
    db: Session = Depends(deps.get_db),
    username: str = Form(...),
    password: str = Form(...)
) -> Any:
    user = db.query(User).filter(User.username == username).first()
    if not user or not security.verify_password(password, user.hashed_password):
        raise HTTPException(status_code=400, detail="Credenciales incorrectas")
    if not user.is_active:
        raise HTTPException(status_code=400, detail="Usuario inactivo")

    access_token_expires = timedelta(days=settings.ACCESS_TOKEN_EXPIRE_DAYS)
    access_token = security.create_access_token(
        user.username, expires_delta=access_token_expires
    )

    # Configurar cookie httponly
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        max_age=int(access_token_expires.total_seconds()),
        expires=int(access_token_expires.total_seconds()),
        samesite="Lax",
        secure=False, # Cambiar a True en producción con HTTPS
    )

    # Registrar en AuditLog
    user.last_login = datetime.utcnow()
    audit_log = AuditLog(
        user_id=user.id,
        action="LOGIN",
        description=f"Usuario {username} inició sesión"
    )
    db.add(audit_log)
    db.commit()

    return {"msg": "Login exitoso"}

@router.get("/logout")
def logout(response: Response):
    response.delete_cookie("access_token")
    return {"msg": "Sesión cerrada"}
