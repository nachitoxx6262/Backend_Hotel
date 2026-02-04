"""
Endpoints de Caja - Sistema de Ingresos y Egresos
"""
from datetime import datetime, date, timedelta
from typing import List, Optional
from decimal import Decimal
from io import StringIO
import csv

from fastapi import APIRouter, Depends, HTTPException, status, Query, Response
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, and_, or_, desc

from database import conexion
from models.usuario import Usuario
from models.core import (
    Transaction, TransactionCategory, CashClosing,
    Cliente, Stay, Subscription,
    TransactionType, PaymentMethod
)
from schemas.caja import (
    TransactionCategoryCreate, TransactionCategoryUpdate, TransactionCategoryResponse,
    TransactionCreate, TransactionResponse, TransactionAnnul, TransactionFilters,
    TransactionCreateAutomatic,
    CajaSummary, CajaSummaryByCategory,
    CashClosingCreate, CashClosingResponse,
    TransactionTypeEnum, PaymentMethodEnum
)
from utils.dependencies import get_current_user, require_admin_or_manager
from utils.logging_utils import log_event


router = APIRouter(prefix="/caja", tags=["Caja"])


# ============================================================================
# CATEGORÍAS DE TRANSACCIONES
# ============================================================================

@router.get("/categorias", response_model=List[TransactionCategoryResponse])
async def get_categories(
    tipo: Optional[TransactionTypeEnum] = None,
    activo: Optional[bool] = None,
    current_user: Usuario = Depends(get_current_user),
    db: Session = Depends(conexion.get_db)
):
    """
    Lista todas las categorías de ingresos/egresos del tenant.
    Filtros opcionales: tipo (ingreso/egreso), activo (true/false).
    """
    try:
        if not current_user.empresa_usuario_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Usuario no pertenece a ningún hotel"
            )
        
        query = db.query(TransactionCategory).filter(
            TransactionCategory.empresa_usuario_id == current_user.empresa_usuario_id
        )
        
        if tipo:
            query = query.filter(TransactionCategory.tipo == tipo.value)
        
        if activo is not None:
            query = query.filter(TransactionCategory.activo == activo)
        
        categories = query.order_by(TransactionCategory.nombre).all()
        
        return categories
        
    except HTTPException:
        raise
    except Exception as e:
        log_event("caja", current_user.username, "Error al listar categorías", f"error={str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al obtener categorías"
        )


@router.post("/categorias", response_model=TransactionCategoryResponse, status_code=status.HTTP_201_CREATED)
async def create_category(
    category_data: TransactionCategoryCreate,
    current_user: Usuario = Depends(require_admin_or_manager),
    db: Session = Depends(conexion.get_db)
):
    """
    Crea una nueva categoría de ingreso o egreso.
    Solo administradores y gerentes.
    """
    try:
        if not current_user.empresa_usuario_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Usuario no pertenece a ningún hotel"
            )
        
        # Verificar si ya existe una categoría con el mismo nombre y tipo
        exists = db.query(TransactionCategory).filter(
            TransactionCategory.empresa_usuario_id == current_user.empresa_usuario_id,
            TransactionCategory.nombre == category_data.nombre,
            TransactionCategory.tipo == category_data.tipo.value if hasattr(category_data.tipo, 'value') else category_data.tipo
        ).first()
        
        if exists:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Ya existe una categoría '{category_data.nombre}' de tipo {category_data.tipo}"
            )
        
        # Crear categoría
        new_category = TransactionCategory(
            empresa_usuario_id=current_user.empresa_usuario_id,
            nombre=category_data.nombre,
            tipo=category_data.tipo.value if hasattr(category_data.tipo, 'value') else category_data.tipo,
            descripcion=category_data.descripcion,
            activo=category_data.activo,
            es_sistema=False
        )
        
        db.add(new_category)
        db.commit()
        db.refresh(new_category)
        
        log_event("caja", current_user.username, "Categoría creada", f"id={new_category.id}, nombre={new_category.nombre}")
        
        return new_category
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        log_event("caja", current_user.username, "Error al crear categoría", f"error={str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al crear categoría"
        )


@router.patch("/categorias/{category_id}", response_model=TransactionCategoryResponse)
async def update_category(
    category_id: int,
    category_data: TransactionCategoryUpdate,
    current_user: Usuario = Depends(require_admin_or_manager),
    db: Session = Depends(conexion.get_db)
):
    """
    Actualiza una categoría existente.
    No se pueden editar categorías del sistema (es_sistema=true).
    """
    try:
        category = db.query(TransactionCategory).filter(
            TransactionCategory.id == category_id,
            TransactionCategory.empresa_usuario_id == current_user.empresa_usuario_id
        ).first()
        
        if not category:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Categoría no encontrada"
            )
        
        if category.es_sistema:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No se puede editar una categoría del sistema"
            )
        
        # Actualizar campos
        if category_data.nombre is not None:
            # Verificar duplicados
            exists = db.query(TransactionCategory).filter(
                TransactionCategory.id != category_id,
                TransactionCategory.empresa_usuario_id == current_user.empresa_usuario_id,
                TransactionCategory.nombre == category_data.nombre,
                TransactionCategory.tipo == category.tipo.value if hasattr(category.tipo, 'value') else category.tipo
            ).first()
            
            if exists:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Ya existe otra categoría con el nombre '{category_data.nombre}'"
                )
            
            category.nombre = category_data.nombre
        
        if category_data.descripcion is not None:
            category.descripcion = category_data.descripcion
        
        if category_data.activo is not None:
            category.activo = category_data.activo
        
        db.commit()
        db.refresh(category)
        
        log_event("caja", current_user.username, "Categoría actualizada", f"id={category.id}")
        
        return category
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        log_event("caja", current_user.username, "Error al actualizar categoría", f"error={str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al actualizar categoría"
        )


# ============================================================================
# TRANSACCIONES (INGRESOS Y EGRESOS)
# ============================================================================

@router.get("/transacciones", response_model=List[TransactionResponse])
async def get_transactions(
    fecha_desde: Optional[datetime] = None,
    fecha_hasta: Optional[datetime] = None,
    tipo: Optional[TransactionTypeEnum] = None,
    category_id: Optional[int] = None,
    metodo_pago: Optional[PaymentMethodEnum] = None,
    incluir_anuladas: bool = False,
    limit: int = Query(100, le=1000),
    offset: int = 0,
    current_user: Usuario = Depends(get_current_user),
    db: Session = Depends(conexion.get_db)
):
    """
    Lista transacciones con filtros opcionales.
    Por defecto excluye transacciones anuladas.
    """
    try:
        if not current_user.empresa_usuario_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Usuario no pertenece a ningún hotel"
            )
        
        query = db.query(Transaction).filter(
            Transaction.empresa_usuario_id == current_user.empresa_usuario_id
        )
        
        # Aplicar filtros
        if fecha_desde:
            query = query.filter(Transaction.fecha >= fecha_desde)
        
        if fecha_hasta:
            query = query.filter(Transaction.fecha <= fecha_hasta)
        
        if tipo:
            query = query.filter(Transaction.tipo == tipo.value)
        
        if category_id:
            query = query.filter(Transaction.category_id == category_id)
        
        if metodo_pago:
            query = query.filter(Transaction.metodo_pago == metodo_pago.value)
        
        if not incluir_anuladas:
            query = query.filter(Transaction.anulada == False)
        
        # Ordenar por fecha descendente
        query = query.order_by(desc(Transaction.fecha))
        
        # Paginación
        transactions = query.offset(offset).limit(limit).all()
        
        # Enriquecer con datos relacionados
        result = []
        for trans in transactions:
            trans_dict = {
                "id": trans.id,
                "empresa_usuario_id": trans.empresa_usuario_id,
                "tipo": trans.tipo,
                "category_id": trans.category_id,
                "monto": trans.monto,
                "metodo_pago": trans.metodo_pago,
                "referencia": trans.referencia,
                "fecha": trans.fecha,
                "usuario_id": trans.usuario_id,
                "stay_id": trans.stay_id,
                "subscription_id": trans.subscription_id,
                "cliente_id": trans.cliente_id,
                "anulada": trans.anulada,
                "anulada_por_id": trans.anulada_por_id,
                "anulada_fecha": trans.anulada_fecha,
                "motivo_anulacion": trans.motivo_anulacion,
                "transaction_anulacion_id": trans.transaction_anulacion_id,
                "es_automatica": trans.es_automatica,
                "created_at": trans.created_at,
                "notas": trans.notas,
                "metadata_json": trans.metadata_json,
                "usuario_nombre": trans.usuario.username if trans.usuario else None,
                "category_nombre": trans.category.nombre if trans.category else None,
                "cliente_nombre": f"{trans.cliente.nombre} {trans.cliente.apellido}" if trans.cliente else None
            }
            result.append(TransactionResponse(**trans_dict))
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        log_event("caja", current_user.username, "Error al listar transacciones", f"error={str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al obtener transacciones"
        )


@router.get("/transacciones/{transaction_id}", response_model=TransactionResponse)
async def get_transaction(
    transaction_id: int,
    current_user: Usuario = Depends(get_current_user),
    db: Session = Depends(conexion.get_db)
):
    """
    Obtiene una transacción específica por ID.
    """
    try:
        transaction = db.query(Transaction).filter(
            Transaction.id == transaction_id,
            Transaction.empresa_usuario_id == current_user.empresa_usuario_id
        ).first()
        
        if not transaction:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Transacción no encontrada"
            )
        
        trans_dict = {
            "id": transaction.id,
            "empresa_usuario_id": transaction.empresa_usuario_id,
            "tipo": transaction.tipo,
            "category_id": transaction.category_id,
            "monto": transaction.monto,
            "metodo_pago": transaction.metodo_pago,
            "referencia": transaction.referencia,
            "fecha": transaction.fecha,
            "usuario_id": transaction.usuario_id,
            "stay_id": transaction.stay_id,
            "subscription_id": transaction.subscription_id,
            "cliente_id": transaction.cliente_id,
            "anulada": transaction.anulada,
            "anulada_por_id": transaction.anulada_por_id,
            "anulada_fecha": transaction.anulada_fecha,
            "motivo_anulacion": transaction.motivo_anulacion,
            "transaction_anulacion_id": transaction.transaction_anulacion_id,
            "es_automatica": transaction.es_automatica,
            "created_at": transaction.created_at,
            "notas": transaction.notas,
            "metadata_json": transaction.metadata_json,
            "usuario_nombre": transaction.usuario.username if transaction.usuario else None,
            "category_nombre": transaction.category.nombre if transaction.category else None,
            "cliente_nombre": f"{transaction.cliente.nombre} {transaction.cliente.apellido}" if transaction.cliente else None
        }
        
        return TransactionResponse(**trans_dict)
        
    except HTTPException:
        raise
    except Exception as e:
        log_event("caja", current_user.username, "Error al obtener transacción", f"error={str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al obtener transacción"
        )


@router.post("/transacciones", response_model=TransactionResponse, status_code=status.HTTP_201_CREATED)
async def create_transaction(
    transaction_data: TransactionCreate,
    current_user: Usuario = Depends(get_current_user),
    db: Session = Depends(conexion.get_db)
):
    """
    Crea una nueva transacción (ingreso o egreso).
    Requiere categoría válida y monto positivo.
    """
    try:
        if not current_user.empresa_usuario_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Usuario no pertenece a ningún hotel"
            )
        
        # Verificar que la categoría existe y pertenece al tenant
        category = db.query(TransactionCategory).filter(
            TransactionCategory.id == transaction_data.category_id,
            TransactionCategory.empresa_usuario_id == current_user.empresa_usuario_id,
            TransactionCategory.activo == True
        ).first()
        
        if not category:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Categoría no encontrada o inactiva"
            )
        
        # Verificar que el tipo coincida con la categoría
        if transaction_data.tipo != category.tipo:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"El tipo de transacción no coincide con la categoría (esperado: {category.tipo})"
            )
        
        # Verificar cliente si se proporciona
        if transaction_data.cliente_id:
            cliente = db.query(Cliente).filter(
                Cliente.id == transaction_data.cliente_id,
                Cliente.empresa_usuario_id == current_user.empresa_usuario_id
            ).first()
            
            if not cliente:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Cliente no encontrado"
                )
        
        # Crear transacción
        new_transaction = Transaction(
            empresa_usuario_id=current_user.empresa_usuario_id,
            tipo=transaction_data.tipo.value if hasattr(transaction_data.tipo, 'value') else transaction_data.tipo,
            category_id=transaction_data.category_id,
            monto=transaction_data.monto,
            metodo_pago=transaction_data.metodo_pago.value if hasattr(transaction_data.metodo_pago, 'value') else transaction_data.metodo_pago,
            referencia=transaction_data.referencia,
            fecha=transaction_data.fecha,
            usuario_id=current_user.id,
            cliente_id=transaction_data.cliente_id,
            notas=transaction_data.notas,
            es_automatica=False
        )
        
        db.add(new_transaction)
        db.commit()
        db.refresh(new_transaction)
        
        log_event(
            "caja",
            current_user.username,
            f"Transacción creada",
            f"id={new_transaction.id}, tipo={new_transaction.tipo}, monto={new_transaction.monto}"
        )
        
        # Enriquecer respuesta
        trans_dict = {
            "id": new_transaction.id,
            "empresa_usuario_id": new_transaction.empresa_usuario_id,
            "tipo": new_transaction.tipo,
            "category_id": new_transaction.category_id,
            "monto": new_transaction.monto,
            "metodo_pago": new_transaction.metodo_pago,
            "referencia": new_transaction.referencia,
            "fecha": new_transaction.fecha,
            "usuario_id": new_transaction.usuario_id,
            "stay_id": new_transaction.stay_id,
            "subscription_id": new_transaction.subscription_id,
            "cliente_id": new_transaction.cliente_id,
            "anulada": new_transaction.anulada,
            "anulada_por_id": new_transaction.anulada_por_id,
            "anulada_fecha": new_transaction.anulada_fecha,
            "motivo_anulacion": new_transaction.motivo_anulacion,
            "transaction_anulacion_id": new_transaction.transaction_anulacion_id,
            "es_automatica": new_transaction.es_automatica,
            "created_at": new_transaction.created_at,
            "notas": new_transaction.notas,
            "metadata_json": new_transaction.metadata_json,
            "usuario_nombre": current_user.username,
            "category_nombre": category.nombre,
            "cliente_nombre": f"{cliente.nombre} {cliente.apellido}" if transaction_data.cliente_id else None
        }
        
        return TransactionResponse(**trans_dict)
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        log_event("caja", current_user.username, "Error al crear transacción", f"error={str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al crear transacción"
        )


@router.post("/transacciones/{transaction_id}/anular", response_model=TransactionResponse)
async def annul_transaction(
    transaction_id: int,
    annul_data: TransactionAnnul,
    current_user: Usuario = Depends(require_admin_or_manager),
    db: Session = Depends(conexion.get_db)
):
    """
    Anula una transacción existente.
    Crea automáticamente una transacción de ajuste (movimiento opuesto).
    Solo administradores y gerentes.
    """
    try:
        # Buscar transacción
        transaction = db.query(Transaction).filter(
            Transaction.id == transaction_id,
            Transaction.empresa_usuario_id == current_user.empresa_usuario_id
        ).first()
        
        if not transaction:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Transacción no encontrada"
            )
        
        if transaction.anulada:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="La transacción ya está anulada"
            )
        
        # Crear transacción de ajuste (opuesta)
        tipo_opuesto = TransactionType.EGRESO if transaction.tipo == TransactionType.INGRESO else TransactionType.INGRESO
        
        # Buscar categoría "Ajuste" o crear una genérica
        categoria_ajuste = db.query(TransactionCategory).filter(
            TransactionCategory.empresa_usuario_id == current_user.empresa_usuario_id,
            TransactionCategory.nombre == "Anulación/Ajuste",
            TransactionCategory.tipo == tipo_opuesto.value if isinstance(tipo_opuesto, TransactionType) else tipo_opuesto
        ).first()
        
        if not categoria_ajuste:
            # Crear categoría de ajuste
            categoria_ajuste = TransactionCategory(
                empresa_usuario_id=current_user.empresa_usuario_id,
                nombre="Anulación/Ajuste",
                tipo=tipo_opuesto.value if hasattr(tipo_opuesto, 'value') else tipo_opuesto,
                descripcion="Categoría automática para anulaciones",
                activo=True,
                es_sistema=True
            )
            db.add(categoria_ajuste)
            db.flush()
        
        # Crear movimiento de ajuste
        ajuste_transaction = Transaction(
            empresa_usuario_id=current_user.empresa_usuario_id,
            tipo=tipo_opuesto.value if hasattr(tipo_opuesto, 'value') else tipo_opuesto,
            category_id=categoria_ajuste.id,
            monto=transaction.monto,
            metodo_pago=transaction.metodo_pago,
            referencia=f"Anulación de transacción #{transaction.id}",
            fecha=datetime.utcnow(),
            usuario_id=current_user.id,
            notas=f"Movimiento de ajuste por anulación. Motivo: {annul_data.motivo_anulacion}",
            es_automatica=True
        )
        
        db.add(ajuste_transaction)
        db.flush()
        
        # Marcar transacción original como anulada
        transaction.anulada = True
        transaction.anulada_por_id = current_user.id
        transaction.anulada_fecha = datetime.utcnow()
        transaction.motivo_anulacion = annul_data.motivo_anulacion
        transaction.transaction_anulacion_id = ajuste_transaction.id
        
        db.commit()
        db.refresh(transaction)
        
        log_event(
            "caja",
            current_user.username,
            f"Transacción anulada",
            f"id={transaction.id}, ajuste_id={ajuste_transaction.id}"
        )
        
        # Enriquecer respuesta
        trans_dict = {
            "id": transaction.id,
            "empresa_usuario_id": transaction.empresa_usuario_id,
            "tipo": transaction.tipo,
            "category_id": transaction.category_id,
            "monto": transaction.monto,
            "metodo_pago": transaction.metodo_pago,
            "referencia": transaction.referencia,
            "fecha": transaction.fecha,
            "usuario_id": transaction.usuario_id,
            "stay_id": transaction.stay_id,
            "subscription_id": transaction.subscription_id,
            "cliente_id": transaction.cliente_id,
            "anulada": transaction.anulada,
            "anulada_por_id": transaction.anulada_por_id,
            "anulada_fecha": transaction.anulada_fecha,
            "motivo_anulacion": transaction.motivo_anulacion,
            "transaction_anulacion_id": transaction.transaction_anulacion_id,
            "es_automatica": transaction.es_automatica,
            "created_at": transaction.created_at,
            "notas": transaction.notas,
            "metadata_json": transaction.metadata_json,
            "usuario_nombre": transaction.usuario.username if transaction.usuario else None,
            "category_nombre": transaction.category.nombre if transaction.category else None,
            "cliente_nombre": f"{transaction.cliente.nombre} {transaction.cliente.apellido}" if transaction.cliente else None
        }
        
        return TransactionResponse(**trans_dict)
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        log_event("caja", current_user.username, "Error al anular transacción", f"error={str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al anular transacción"
        )


# ============================================================================
# RESUMEN DE CAJA
# ============================================================================

@router.get("/resumen", response_model=CajaSummary)
async def get_caja_summary(
    fecha_desde: Optional[datetime] = None,
    fecha_hasta: Optional[datetime] = None,
    current_user: Usuario = Depends(get_current_user),
    db: Session = Depends(conexion.get_db)
):
    """
    Obtiene un resumen de caja para el período especificado.
    Por defecto: día actual.
    """
    try:
        if not current_user.empresa_usuario_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Usuario no pertenece a ningún hotel"
            )
        
        # Si no se especifica rango, usar día actual
        if not fecha_desde:
            fecha_desde = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        
        if not fecha_hasta:
            fecha_hasta = datetime.now().replace(hour=23, minute=59, second=59, microsecond=999999)
        
        # Query base
        transactions = db.query(Transaction).filter(
            Transaction.empresa_usuario_id == current_user.empresa_usuario_id,
            Transaction.fecha >= fecha_desde,
            Transaction.fecha <= fecha_hasta,
            Transaction.anulada == False
        ).all()
        
        # Calcular totales
        total_ingresos = Decimal("0.00")
        total_egresos = Decimal("0.00")
        
        ingresos_efectivo = Decimal("0.00")
        ingresos_transferencia = Decimal("0.00")
        ingresos_tarjeta = Decimal("0.00")
        ingresos_otros = Decimal("0.00")
        
        egresos_efectivo = Decimal("0.00")
        egresos_transferencia = Decimal("0.00")
        egresos_tarjeta = Decimal("0.00")
        egresos_otros = Decimal("0.00")
        
        cantidad_ingresos = 0
        cantidad_egresos = 0
        
        for trans in transactions:
            if trans.tipo == TransactionType.INGRESO:
                total_ingresos += trans.monto
                cantidad_ingresos += 1
                
                if trans.metodo_pago == PaymentMethod.EFECTIVO:
                    ingresos_efectivo += trans.monto
                elif trans.metodo_pago == PaymentMethod.TRANSFERENCIA:
                    ingresos_transferencia += trans.monto
                elif trans.metodo_pago == PaymentMethod.TARJETA:
                    ingresos_tarjeta += trans.monto
                else:
                    ingresos_otros += trans.monto
            else:
                total_egresos += trans.monto
                cantidad_egresos += 1
                
                if trans.metodo_pago == PaymentMethod.EFECTIVO:
                    egresos_efectivo += trans.monto
                elif trans.metodo_pago == PaymentMethod.TRANSFERENCIA:
                    egresos_transferencia += trans.monto
                elif trans.metodo_pago == PaymentMethod.TARJETA:
                    egresos_tarjeta += trans.monto
                else:
                    egresos_otros += trans.monto
        
        saldo = total_ingresos - total_egresos
        efectivo_caja = ingresos_efectivo - egresos_efectivo
        
        return CajaSummary(
            total_ingresos=total_ingresos,
            total_egresos=total_egresos,
            saldo=saldo,
            efectivo_caja=efectivo_caja,
            ingresos_efectivo=ingresos_efectivo,
            ingresos_transferencia=ingresos_transferencia,
            ingresos_tarjeta=ingresos_tarjeta,
            ingresos_otros=ingresos_otros,
            egresos_efectivo=egresos_efectivo,
            egresos_transferencia=egresos_transferencia,
            egresos_tarjeta=egresos_tarjeta,
            egresos_otros=egresos_otros,
            cantidad_ingresos=cantidad_ingresos,
            cantidad_egresos=cantidad_egresos,
            fecha_desde=fecha_desde,
            fecha_hasta=fecha_hasta
        )
        
    except HTTPException:
        raise
    except Exception as e:
        log_event("caja", current_user.username, "Error al obtener resumen", f"error={str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al obtener resumen de caja"
        )


@router.get("/resumen/por-categoria", response_model=List[CajaSummaryByCategory])
async def get_summary_by_category(
    fecha_desde: Optional[datetime] = None,
    fecha_hasta: Optional[datetime] = None,
    tipo: Optional[TransactionTypeEnum] = None,
    current_user: Usuario = Depends(get_current_user),
    db: Session = Depends(conexion.get_db)
):
    """
    Obtiene un resumen de caja agrupado por categoría.
    """
    try:
        if not current_user.empresa_usuario_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Usuario no pertenece a ningún hotel"
            )
        
        # Si no se especifica rango, usar día actual
        if not fecha_desde:
            fecha_desde = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        
        if not fecha_hasta:
            fecha_hasta = datetime.now().replace(hour=23, minute=59, second=59, microsecond=999999)
        
        # Query con agrupación
        query = db.query(
            TransactionCategory.id.label("category_id"),
            TransactionCategory.nombre.label("category_nombre"),
            TransactionCategory.tipo.label("tipo"),
            func.sum(Transaction.monto).label("total"),
            func.count(Transaction.id).label("cantidad")
        ).join(
            Transaction, Transaction.category_id == TransactionCategory.id
        ).filter(
            Transaction.empresa_usuario_id == current_user.empresa_usuario_id,
            Transaction.fecha >= fecha_desde,
            Transaction.fecha <= fecha_hasta,
            Transaction.anulada == False
        )
        
        if tipo:
            query = query.filter(Transaction.tipo == tipo.value)
        
        query = query.group_by(
            TransactionCategory.id,
            TransactionCategory.nombre,
            TransactionCategory.tipo
        ).order_by(desc("total"))
        
        results = query.all()
        
        return [
            CajaSummaryByCategory(
                category_id=r.category_id,
                category_nombre=r.category_nombre,
                tipo=r.tipo,
                total=r.total or Decimal("0.00"),
                cantidad=r.cantidad or 0
            )
            for r in results
        ]
        
    except HTTPException:
        raise
    except Exception as e:
        log_event("caja", current_user.username, "Error al obtener resumen por categoría", f"error={str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al obtener resumen por categoría"
        )


# ============================================================================
# CIERRE DE CAJA
# ============================================================================

@router.post("/cierres", response_model=CashClosingResponse, status_code=status.HTTP_201_CREATED)
async def create_cash_closing(
    closing_data: CashClosingCreate,
    current_user: Usuario = Depends(get_current_user),
    db: Session = Depends(conexion.get_db)
):
    """
    Crea un cierre de caja para el turno del usuario.
    Calcula automáticamente ingresos/egresos y diferencia con efectivo declarado.
    """
    try:
        if not current_user.empresa_usuario_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Usuario no pertenece a ningún hotel"
            )
        
        # Calcular totales del sistema para el período
        transactions = db.query(Transaction).filter(
            Transaction.empresa_usuario_id == current_user.empresa_usuario_id,
            Transaction.fecha >= closing_data.fecha_apertura,
            Transaction.fecha <= datetime.utcnow(),
            Transaction.anulada == False,
            Transaction.metodo_pago == PaymentMethod.EFECTIVO  # Solo efectivo
        ).all()
        
        ingresos_sistema = sum(
            t.monto for t in transactions if t.tipo == TransactionType.INGRESO
        ) or Decimal("0.00")
        
        egresos_sistema = sum(
            t.monto for t in transactions if t.tipo == TransactionType.EGRESO
        ) or Decimal("0.00")
        
        saldo_sistema = ingresos_sistema - egresos_sistema
        diferencia = closing_data.efectivo_declarado - saldo_sistema
        
        # Crear cierre
        new_closing = CashClosing(
            empresa_usuario_id=current_user.empresa_usuario_id,
            usuario_id=current_user.id,
            fecha_apertura=closing_data.fecha_apertura,
            fecha_cierre=datetime.utcnow(),
            ingresos_sistema=ingresos_sistema,
            egresos_sistema=egresos_sistema,
            saldo_sistema=saldo_sistema,
            efectivo_declarado=closing_data.efectivo_declarado,
            diferencia=diferencia,
            notas=closing_data.notas
        )
        
        db.add(new_closing)
        db.commit()
        db.refresh(new_closing)
        
        log_event(
            "caja",
            current_user.username,
            "Cierre de caja creado",
            f"id={new_closing.id}, diferencia={diferencia}"
        )
        
        return CashClosingResponse(
            **new_closing.__dict__,
            usuario_nombre=current_user.username
        )
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        log_event("caja", current_user.username, "Error al crear cierre", f"error={str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al crear cierre de caja"
        )


@router.get("/cierres", response_model=List[CashClosingResponse])
async def get_cash_closings(
    fecha_desde: Optional[datetime] = None,
    fecha_hasta: Optional[datetime] = None,
    usuario_id: Optional[int] = None,
    limit: int = Query(50, le=200),
    current_user: Usuario = Depends(get_current_user),
    db: Session = Depends(conexion.get_db)
):
    """
    Lista cierres de caja del tenant.
    Filtros opcionales: rango de fechas, usuario.
    """
    try:
        if not current_user.empresa_usuario_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Usuario no pertenece a ningún hotel"
            )
        
        query = db.query(CashClosing).filter(
            CashClosing.empresa_usuario_id == current_user.empresa_usuario_id
        )
        
        if fecha_desde:
            query = query.filter(CashClosing.fecha_cierre >= fecha_desde)
        
        if fecha_hasta:
            query = query.filter(CashClosing.fecha_cierre <= fecha_hasta)
        
        if usuario_id:
            query = query.filter(CashClosing.usuario_id == usuario_id)
        
        closings = query.order_by(desc(CashClosing.fecha_cierre)).limit(limit).all()
        
        result = []
        for closing in closings:
            result.append(CashClosingResponse(
                **closing.__dict__,
                usuario_nombre=closing.usuario.username if closing.usuario else None
            ))
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        log_event("caja", current_user.username, "Error al listar cierres", f"error={str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al obtener cierres de caja"
        )


# ============================================================================
# EXPORTACIÓN
# ============================================================================

@router.get("/transacciones/exportar/csv")
async def export_transactions_csv(
    fecha_desde: Optional[datetime] = None,
    fecha_hasta: Optional[datetime] = None,
    tipo: Optional[TransactionTypeEnum] = None,
    current_user: Usuario = Depends(get_current_user),
    db: Session = Depends(conexion.get_db)
):
    """
    Exporta transacciones a CSV.
    """
    try:
        if not current_user.empresa_usuario_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Usuario no pertenece a ningún hotel"
            )
        
        # Si no se especifica rango, usar mes actual
        if not fecha_desde:
            fecha_desde = datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        
        if not fecha_hasta:
            fecha_hasta = datetime.now()
        
        query = db.query(Transaction).filter(
            Transaction.empresa_usuario_id == current_user.empresa_usuario_id,
            Transaction.fecha >= fecha_desde,
            Transaction.fecha <= fecha_hasta
        )
        
        if tipo:
            query = query.filter(Transaction.tipo == tipo.value)
        
        transactions = query.order_by(Transaction.fecha).all()
        
        # Crear CSV en memoria
        output = StringIO()
        writer = csv.writer(output)
        
        # Encabezados
        writer.writerow([
            "ID", "Fecha", "Tipo", "Categoría", "Monto", "Método de Pago",
            "Referencia", "Usuario", "Notas", "Anulada", "Motivo Anulación"
        ])
        
        # Filas
        for trans in transactions:
            writer.writerow([
                trans.id,
                trans.fecha.strftime("%Y-%m-%d %H:%M:%S"),
                trans.tipo.value,
                trans.category.nombre if trans.category else "",
                str(trans.monto),
                trans.metodo_pago.value,
                trans.referencia or "",
                trans.usuario.username if trans.usuario else "",
                trans.notas or "",
                "Sí" if trans.anulada else "No",
                trans.motivo_anulacion or ""
            ])
        
        output.seek(0)
        
        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={
                "Content-Disposition": f"attachment; filename=transacciones_{fecha_desde.strftime('%Y%m%d')}_{fecha_hasta.strftime('%Y%m%d')}.csv"
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        log_event("caja", current_user.username, "Error al exportar transacciones", f"error={str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al exportar transacciones"
        )


# ============================================================================
# FUNCIÓN INTERNA PARA TRANSACCIONES AUTOMÁTICAS
# ============================================================================

async def create_automatic_transaction(
    transaction_data: TransactionCreateAutomatic,
    empresa_usuario_id: int,
    usuario_id: int,
    db: Session
) -> Transaction:
    """
    Función interna para crear transacciones automáticas desde checkout o Stripe.
    No es un endpoint público.
    """
    try:
        new_transaction = Transaction(
            empresa_usuario_id=empresa_usuario_id,
            tipo=transaction_data.tipo.value if hasattr(transaction_data.tipo, 'value') else transaction_data.tipo,
            category_id=transaction_data.category_id,
            monto=transaction_data.monto,
            metodo_pago=transaction_data.metodo_pago.value if hasattr(transaction_data.metodo_pago, 'value') else transaction_data.metodo_pago,
            referencia=transaction_data.referencia,
            fecha=datetime.utcnow(),
            usuario_id=usuario_id,
            stay_id=transaction_data.stay_id,
            subscription_id=transaction_data.subscription_id,
            cliente_id=transaction_data.cliente_id,
            notas=transaction_data.notas,
            es_automatica=True
        )
        
        db.add(new_transaction)
        db.flush()
        
        log_event(
            "caja",
            str(usuario_id),
            "Transacción automática creada",
            f"id={new_transaction.id}, tipo={new_transaction.tipo}, monto={new_transaction.monto}"
        )
        
        return new_transaction
        
    except Exception as e:
        log_event("caja", str(usuario_id), "Error al crear transacción automática", f"error={str(e)}")
        raise


# ============================================================================
# TRANSACCIONES POR STAY
# ============================================================================

@router.get("/stays/{stay_id}/transactions", response_model=List[TransactionResponse])
async def get_stay_transactions(
    stay_id: int,
    current_user: Usuario = Depends(get_current_user),
    db: Session = Depends(conexion.get_db)
):
    """
    Obtiene todas las transacciones relacionadas a una estadía específica.
    Útil para mostrar múltiples pagos en una factura.
    """
    try:
        if not current_user.empresa_usuario_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Usuario no pertenece a ningún hotel"
            )
        
        # Query transacciones del stay
        transactions = db.query(Transaction).filter(
            Transaction.empresa_usuario_id == current_user.empresa_usuario_id,
            Transaction.stay_id == stay_id,
            Transaction.anulada == False
        ).order_by(Transaction.fecha.asc()).all()
        
        # Mapear a respuesta
        result = []
        for t in transactions:
            trans_dict = {
                "id": t.id,
                "empresa_usuario_id": t.empresa_usuario_id,
                "tipo": t.tipo,
                "category_id": t.category_id,
                "monto": t.monto,
                "metodo_pago": t.metodo_pago,
                "referencia": t.referencia,
                "fecha": t.fecha,
                "usuario_id": t.usuario_id,
                "stay_id": t.stay_id,
                "subscription_id": t.subscription_id,
                "cliente_id": t.cliente_id,
                "anulada": t.anulada,
                "fecha_anulacion": t.fecha_anulacion,
                "usuario_anulacion_id": t.usuario_anulacion_id,
                "motivo_anulacion": t.motivo_anulacion,
                "es_automatica": t.es_automatica,
                "created_at": t.created_at,
                "notas": t.notas,
                "metadata_json": t.metadata_json,
                "usuario_nombre": t.usuario.username if t.usuario else None,
                "category_nombre": t.category.nombre if t.category else None,
                "cliente_nombre": f"{t.cliente.nombre} {t.cliente.apellido}" if t.cliente else None
            }
            result.append(TransactionResponse(**trans_dict))
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        log_event("caja", current_user.username, "Error al obtener transacciones del stay", f"stay_id={stay_id}, error={str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al obtener transacciones del stay"
        )
