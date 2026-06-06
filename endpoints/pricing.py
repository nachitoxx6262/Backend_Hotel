"""
Hotel Pricing Endpoints
Endpoints para gestionar Planes de Tarifa (RatePlan) y Tarifas Diarias (DailyRate)
"""

from datetime import datetime, date
from typing import List, Optional
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException, Query, Path, status, UploadFile, File
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import and_, or_, func
from pydantic import BaseModel, Field, field_validator

from database.conexion import get_db
from models.core import RatePlan, DailyRate, RoomType, Reservation, Stay
from utils.logging_utils import log_event
from utils.invoice_engine import compute_invoice
from utils.dependencies import get_current_user

router = APIRouter(prefix="/api/pricing", tags=["Hotel Pricing"])


# ========================================================================
# SCHEMAS
# ========================================================================

class RatePlanSchema(BaseModel):
    id: Optional[int] = None
    nombre: str
    descripcion: Optional[str] = None
    reglas: Optional[dict] = None
    activo: bool = True

    class Config:
        from_attributes = True


class DailyRateSchema(BaseModel):
    id: Optional[int] = None
    room_type_id: int
    rate_plan_id: Optional[int] = None
    fecha: str  # YYYY-MM-DD
    precio: Decimal

    model_config = {"from_attributes": True}

    @field_validator("fecha", mode="before")
    @classmethod
    def coerce_fecha(cls, v):
        """Accept datetime objects and convert to YYYY-MM-DD string."""
        if hasattr(v, "date"):
            return v.date().isoformat()
        return str(v)


# ========================================================================
# RATE PLANS ENDPOINTS
# ========================================================================

@router.get("/rate-plans", response_model=List[RatePlanSchema])
def get_rate_plans(
    activo: Optional[bool] = Query(None, description="Filtrar por estado activo"),
    db: Session = Depends(get_db)
):
    """
    Obtener todos los planes de tarifa
    """
    query = db.query(RatePlan)
    
    if activo is not None:
        query = query.filter(RatePlan.activo == activo)
    
    plans = query.all()
    return plans


@router.post("/rate-plans", response_model=RatePlanSchema, status_code=status.HTTP_201_CREATED)
def create_rate_plan(
    payload: RatePlanSchema,
    db: Session = Depends(get_db)
):
    """
    Crear un nuevo plan de tarifa
    """
    if not payload.nombre or not payload.nombre.strip():
        raise HTTPException(status_code=400, detail="Nombre del plan es requerido")
    
    # Verificar que no existe un plan con el mismo nombre
    existing = db.query(RatePlan).filter(RatePlan.nombre == payload.nombre).first()
    if existing:
        raise HTTPException(status_code=409, detail="Ya existe un plan con este nombre")
    
    plan = RatePlan(
        nombre=payload.nombre,
        descripcion=payload.descripcion,
        reglas=payload.reglas or {},
        activo=payload.activo
    )
    
    db.add(plan)
    db.commit()
    db.refresh(plan)
    
    log_event("pricing", "sistema", "RatePlan creado", f"id={plan.id}, nombre={plan.nombre}")
    
    return plan


@router.get("/rate-plans/{plan_id}", response_model=RatePlanSchema)
def get_rate_plan(
    plan_id: int = Path(..., gt=0),
    db: Session = Depends(get_db)
):
    """
    Obtener un plan de tarifa específico
    """
    plan = db.query(RatePlan).filter(RatePlan.id == plan_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="Plan no encontrado")
    
    return plan


@router.patch("/rate-plans/{plan_id}", response_model=RatePlanSchema)
def update_rate_plan(
    plan_id: int = Path(..., gt=0),
    payload: RatePlanSchema = ...,
    db: Session = Depends(get_db)
):
    """
    Actualizar un plan de tarifa
    """
    plan = db.query(RatePlan).filter(RatePlan.id == plan_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="Plan no encontrado")
    
    # Actualizar campos
    if payload.nombre:
        plan.nombre = payload.nombre
    if payload.descripcion is not None:
        plan.descripcion = payload.descripcion
    if payload.reglas is not None:
        plan.reglas = payload.reglas
    if payload.activo is not None:
        plan.activo = payload.activo
    
    db.commit()
    db.refresh(plan)
    
    log_event("pricing", "sistema", "RatePlan actualizado", f"id={plan.id}")
    
    return plan


@router.delete("/rate-plans/{plan_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_rate_plan(
    plan_id: int = Path(..., gt=0),
    db: Session = Depends(get_db)
):
    """
    Eliminar un plan de tarifa (soft delete - marcar como inactivo)
    """
    plan = db.query(RatePlan).filter(RatePlan.id == plan_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="Plan no encontrado")
    
    # Soft delete: marcar como inactivo
    plan.activo = False
    db.commit()
    
    log_event("pricing", "sistema", "RatePlan desactivado", f"id={plan.id}")
    
    return None


# ========================================================================
# DAILY RATES ENDPOINTS
# ========================================================================

@router.get("/daily-rates", response_model=List[DailyRateSchema])
def get_daily_rates(
    room_type_id: Optional[int] = Query(None, description="Filtrar por tipo de habitación"),
    rate_plan_id: Optional[int] = Query(None, description="Filtrar por plan de tarifa"),
    from_date: Optional[str] = Query(None, description="Desde fecha (YYYY-MM-DD)"),
    to_date: Optional[str] = Query(None, description="Hasta fecha (YYYY-MM-DD)"),
    db: Session = Depends(get_db)
):
    """
    Obtener tarifas diarias con filtros opcionales
    """
    query = db.query(DailyRate).options(
        joinedload(DailyRate.room_type),
        joinedload(DailyRate.rate_plan)
    )
    
    if room_type_id:
        query = query.filter(DailyRate.room_type_id == room_type_id)
    
    if rate_plan_id:
        query = query.filter(DailyRate.rate_plan_id == rate_plan_id)
    
    if from_date:
        try:
            start_dt = datetime.fromisoformat(from_date.replace('Z', '+00:00'))
            query = query.filter(DailyRate.fecha >= start_dt)
        except:
            pass
    
    if to_date:
        try:
            end_dt = datetime.fromisoformat(to_date.replace('Z', '+00:00'))
            query = query.filter(DailyRate.fecha <= end_dt)
        except:
            pass
    
    rates = query.order_by(DailyRate.fecha.desc()).all()
    return rates


@router.post("/daily-rates", response_model=DailyRateSchema, status_code=status.HTTP_201_CREATED)
def create_daily_rate(
    payload: DailyRateSchema,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Crear una nueva tarifa diaria
    """
    # Validar room_type existe
    room_type = db.query(RoomType).filter(RoomType.id == payload.room_type_id).first()
    if not room_type:
        raise HTTPException(status_code=400, detail="Tipo de habitación no encontrado")
    
    # Validar rate_plan si se proporciona
    if payload.rate_plan_id:
        plan = db.query(RatePlan).filter(RatePlan.id == payload.rate_plan_id).first()
        if not plan:
            raise HTTPException(status_code=400, detail="Plan de tarifa no encontrado")
    
    # Verificar que no existe una tarifa duplicada
    fecha_dt = datetime.fromisoformat(payload.fecha)
    existing = db.query(DailyRate).filter(
        and_(
            DailyRate.room_type_id == payload.room_type_id,
            DailyRate.fecha == fecha_dt,
            DailyRate.rate_plan_id == payload.rate_plan_id
        )
    ).first()
    
    if existing:
        raise HTTPException(status_code=409, detail="Ya existe una tarifa para esta fecha y tipo de habitación")
    
    rate = DailyRate(
        room_type_id=payload.room_type_id,
        rate_plan_id=payload.rate_plan_id,
        fecha=fecha_dt,
        precio=payload.precio,
        empresa_usuario_id=current_user.empresa_usuario_id
    )
    
    db.add(rate)
    db.commit()
    db.refresh(rate)
    
    log_event("pricing", "sistema", "DailyRate creado", 
              f"room_type={payload.room_type_id}, fecha={payload.fecha}, precio={payload.precio}")
    
    return rate


@router.get("/daily-rates/{rate_id}", response_model=DailyRateSchema)
def get_daily_rate(
    rate_id: int = Path(..., gt=0),
    db: Session = Depends(get_db)
):
    """
    Obtener una tarifa diaria específica
    """
    rate = db.query(DailyRate).filter(DailyRate.id == rate_id).first()
    if not rate:
        raise HTTPException(status_code=404, detail="Tarifa no encontrada")
    
    return rate


@router.patch("/daily-rates/{rate_id}", response_model=DailyRateSchema)
def update_daily_rate(
    rate_id: int = Path(..., gt=0),
    payload: DailyRateSchema = ...,
    db: Session = Depends(get_db)
):
    """
    Actualizar una tarifa diaria
    """
    rate = db.query(DailyRate).filter(DailyRate.id == rate_id).first()
    if not rate:
        raise HTTPException(status_code=404, detail="Tarifa no encontrada")
    
    if payload.precio:
        rate.precio = payload.precio
    
    db.commit()
    db.refresh(rate)
    
    log_event("pricing", "sistema", "DailyRate actualizado", f"id={rate.id}, precio={payload.precio}")
    
    return rate


@router.delete("/daily-rates/{rate_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_daily_rate(
    rate_id: int = Path(..., gt=0),
    db: Session = Depends(get_db)
):
    """
    Eliminar una tarifa diaria
    """
    rate = db.query(DailyRate).filter(DailyRate.id == rate_id).first()
    if not rate:
        raise HTTPException(status_code=404, detail="Tarifa no encontrada")
    
    db.delete(rate)
    db.commit()
    
    log_event("pricing", "sistema", "DailyRate eliminado", f"id={rate.id}")
    
    return None


# ========================================================================
# HELPER: Get DailyRate for a specific date and room type
# ========================================================================

def get_daily_rate_for_date(
    room_type_id: int,
    fecha: date,
    rate_plan_id: Optional[int] = None,
    db: Session = None
) -> Optional[DailyRate]:
    """
    Obtener la tarifa diaria para una fecha y tipo de habitación específicos
    
    Precedencia:
    1. DailyRate específico para esa fecha + rate_plan (si aplica)
    2. DailyRate general para esa fecha (sin rate_plan)
    3. Tarifa base del RoomType
    """
    if not db:
        return None
    
    fecha_dt = datetime.combine(fecha, datetime.min.time())
    
    # 1. Intentar obtener con plan específico
    if rate_plan_id:
        rate = db.query(DailyRate).filter(
            and_(
                DailyRate.room_type_id == room_type_id,
                DailyRate.fecha == fecha_dt,
                DailyRate.rate_plan_id == rate_plan_id
            )
        ).first()
        if rate:
            return rate
    
    # 2. Obtener sin plan
    rate = db.query(DailyRate).filter(
        and_(
            DailyRate.room_type_id == room_type_id,
            DailyRate.fecha == fecha_dt,
            DailyRate.rate_plan_id.is_(None)
        )
    ).first()
    if rate:
        return rate

    # 3. Fallback: construir una tarifa virtual con el precio_base del RoomType
    room_type = db.query(RoomType).filter(RoomType.id == room_type_id).first()
    if room_type and room_type.precio_base:
        virtual = DailyRate.__new__(DailyRate)
        virtual.id = None
        virtual.room_type_id = room_type_id
        virtual.fecha = fecha_dt
        virtual.rate_plan_id = None
        virtual.precio = room_type.precio_base
        virtual.disponible = True
        virtual.min_estancia = 1
        virtual.notas = None
        return virtual

    return None


# ============================================================================
# BULK UPLOAD DE TARIFAS VIA CSV
# ============================================================================

@router.post("/daily-rates/bulk-upload")
async def bulk_upload_rates(
    file: UploadFile = File(..., description="CSV con columnas: room_type_id,fecha,precio[,rate_plan_id,disponible]"),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """
    Importa tarifas diarias desde un archivo CSV.

    Formato del CSV:
        room_type_id,fecha,precio[,rate_plan_id,disponible]

    - `fecha` en formato YYYY-MM-DD
    - `precio` valor numérico positivo
    - `rate_plan_id` opcional
    - `disponible` opcional (true/false), default true

    Retorna: {inserted, updated, errors, error_detail}
    """
    import csv, io

    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="El archivo debe ser .csv")

    tenant_id = current_user.empresa_usuario_id
    if not tenant_id:
        raise HTTPException(status_code=401, detail="Sin tenant asociado")

    contents = await file.read()
    try:
        text = contents.decode("utf-8-sig")  # utf-8-sig elimina BOM de Excel
    except UnicodeDecodeError:
        text = contents.decode("latin-1")

    reader = csv.DictReader(io.StringIO(text))

    required = {"room_type_id", "fecha", "precio"}
    if not reader.fieldnames or not required.issubset({f.strip().lower() for f in reader.fieldnames}):
        raise HTTPException(
            status_code=422,
            detail=f"El CSV debe tener columnas: {', '.join(required)}. Columnas encontradas: {reader.fieldnames}"
        )

    inserted = 0
    updated = 0
    error_detail = []

    for row_num, row in enumerate(reader, start=2):  # start=2 porque row 1 es header
        # Normalizar claves
        row = {k.strip().lower(): v.strip() for k, v in row.items()}

        try:
            room_type_id = int(row["room_type_id"])
            precio = float(row["precio"])
            fecha_str = row["fecha"]
            rate_plan_id = int(row["rate_plan_id"]) if row.get("rate_plan_id") else None
            disponible_str = row.get("disponible", "true").lower()
            disponible = disponible_str not in ("false", "0", "no")

            # Validar precio positivo
            if precio <= 0:
                raise ValueError("El precio debe ser mayor a 0")

            # Parsear fecha
            try:
                fecha_dt = datetime.strptime(fecha_str, "%Y-%m-%d")
            except ValueError:
                raise ValueError(f"Fecha inválida '{fecha_str}' — usar formato YYYY-MM-DD")

            # Validar room_type pertenece al tenant
            rt = db.query(RoomType).filter(
                RoomType.id == room_type_id,
                RoomType.empresa_usuario_id == tenant_id,
            ).first()
            if not rt:
                raise ValueError(f"room_type_id={room_type_id} no existe en este tenant")

            # Upsert
            existing = db.query(DailyRate).filter(
                DailyRate.room_type_id == room_type_id,
                DailyRate.fecha == fecha_dt,
                DailyRate.rate_plan_id == rate_plan_id,
            ).first()

            if existing:
                existing.precio = precio
                existing.disponible = disponible
                updated += 1
            else:
                new_rate = DailyRate(
                    room_type_id=room_type_id,
                    rate_plan_id=rate_plan_id,
                    fecha=fecha_dt,
                    precio=precio,
                    disponible=disponible,
                    empresa_usuario_id=tenant_id,
                )
                db.add(new_rate)
                inserted += 1

        except Exception as exc:
            error_detail.append({"row": row_num, "error": str(exc), "data": dict(row)})
            continue

    db.commit()

    log_event("pricing", current_user.username, "Bulk upload tarifas",
              f"inserted={inserted} updated={updated} errors={len(error_detail)}")

    return {
        "inserted": inserted,
        "updated": updated,
        "errors": len(error_detail),
        "error_detail": error_detail[:20],  # Máx 20 errores detallados
    }
