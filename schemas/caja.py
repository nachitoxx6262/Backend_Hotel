"""
Schemas Pydantic para el sistema de caja - Ingresos y Egresos
"""
from typing import Optional
from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel, Field, validator
from enum import Enum


# ========== ENUMS ==========

class TransactionTypeEnum(str, Enum):
    """Tipo de transacción"""
    INGRESO = "ingreso"
    EGRESO = "egreso"


class PaymentMethodEnum(str, Enum):
    """Métodos de pago"""
    EFECTIVO = "efectivo"
    TRANSFERENCIA = "transferencia"
    TARJETA = "tarjeta"
    CHEQUE = "cheque"
    OTRO = "otro"


# ========== SCHEMAS DE CATEGORÍAS ==========

class TransactionCategoryBase(BaseModel):
    nombre: str = Field(..., min_length=1, max_length=100)
    tipo: TransactionTypeEnum
    descripcion: Optional[str] = None
    activo: bool = True


class TransactionCategoryCreate(TransactionCategoryBase):
    """Schema para crear una nueva categoría"""
    pass


class TransactionCategoryUpdate(BaseModel):
    """Schema para actualizar una categoría existente"""
    nombre: Optional[str] = Field(None, min_length=1, max_length=100)
    descripcion: Optional[str] = None
    activo: Optional[bool] = None


class TransactionCategoryResponse(TransactionCategoryBase):
    """Schema de respuesta para categoría"""
    id: int
    empresa_usuario_id: int
    es_sistema: bool
    created_at: datetime

    class Config:
        from_attributes = True


# ========== SCHEMAS DE TRANSACCIONES ==========

class TransactionBase(BaseModel):
    tipo: TransactionTypeEnum
    category_id: int
    monto: Decimal = Field(..., gt=0, max_digits=12, decimal_places=2)
    metodo_pago: PaymentMethodEnum
    referencia: Optional[str] = Field(None, max_length=255)
    fecha: datetime = Field(default_factory=datetime.utcnow)
    notas: Optional[str] = None


class TransactionCreate(TransactionBase):
    """Schema para crear una nueva transacción"""
    cliente_id: Optional[int] = None
    
    @validator('monto')
    def validate_monto(cls, v):
        if v <= 0:
            raise ValueError('El monto debe ser mayor a 0')
        return v


class TransactionCreateAutomatic(BaseModel):
    """Schema para transacciones automáticas (checkout, stripe)"""
    tipo: TransactionTypeEnum
    category_id: int
    monto: Decimal = Field(..., gt=0)
    metodo_pago: PaymentMethodEnum
    referencia: Optional[str] = None
    stay_id: Optional[int] = None
    subscription_id: Optional[int] = None
    cliente_id: Optional[int] = None
    notas: Optional[str] = None


class TransactionResponse(TransactionBase):
    """Schema de respuesta para transacción"""
    id: int
    empresa_usuario_id: int
    usuario_id: Optional[int]
    stay_id: Optional[int]
    subscription_id: Optional[int]
    cliente_id: Optional[int]
    anulada: bool
    anulada_por_id: Optional[int]
    anulada_fecha: Optional[datetime]
    motivo_anulacion: Optional[str]
    transaction_anulacion_id: Optional[int]
    es_automatica: bool
    created_at: datetime
    metadata_json: Optional[dict] = None
    
    # Datos relacionados opcionales
    usuario_nombre: Optional[str] = None
    category_nombre: Optional[str] = None
    cliente_nombre: Optional[str] = None

    class Config:
        from_attributes = True


class TransactionAnnul(BaseModel):
    """Schema para anular una transacción"""
    motivo_anulacion: str = Field(..., min_length=5, max_length=500)


class TransactionFilters(BaseModel):
    """Schema para filtros de búsqueda"""
    fecha_desde: Optional[datetime] = None
    fecha_hasta: Optional[datetime] = None
    tipo: Optional[TransactionTypeEnum] = None
    category_id: Optional[int] = None
    metodo_pago: Optional[PaymentMethodEnum] = None
    usuario_id: Optional[int] = None
    anulada: Optional[bool] = False  # Por defecto excluye anuladas
    incluir_anuladas: Optional[bool] = False


# ========== SCHEMAS DE RESUMEN DE CAJA ==========

class CajaSummary(BaseModel):
    """Resumen de caja del día/período"""
    total_ingresos: Decimal = Field(default=Decimal("0.00"))
    total_egresos: Decimal = Field(default=Decimal("0.00"))
    saldo: Decimal = Field(default=Decimal("0.00"))
    efectivo_caja: Decimal = Field(default=Decimal("0.00"))
    
    # Desglose por método de pago
    ingresos_efectivo: Decimal = Field(default=Decimal("0.00"))
    ingresos_transferencia: Decimal = Field(default=Decimal("0.00"))
    ingresos_tarjeta: Decimal = Field(default=Decimal("0.00"))
    ingresos_otros: Decimal = Field(default=Decimal("0.00"))
    
    egresos_efectivo: Decimal = Field(default=Decimal("0.00"))
    egresos_transferencia: Decimal = Field(default=Decimal("0.00"))
    egresos_tarjeta: Decimal = Field(default=Decimal("0.00"))
    egresos_otros: Decimal = Field(default=Decimal("0.00"))
    
    # Contadores
    cantidad_ingresos: int = 0
    cantidad_egresos: int = 0
    
    # Período
    fecha_desde: datetime
    fecha_hasta: datetime


class CajaSummaryByCategory(BaseModel):
    """Resumen de caja agrupado por categoría"""
    category_id: int
    category_nombre: str
    tipo: TransactionTypeEnum
    total: Decimal
    cantidad: int


# ========== SCHEMAS DE CIERRE DE CAJA ==========

class CashClosingBase(BaseModel):
    efectivo_declarado: Decimal = Field(..., ge=0, max_digits=12, decimal_places=2)
    notas: Optional[str] = None


class CashClosingCreate(CashClosingBase):
    """Schema para crear un cierre de caja"""
    fecha_apertura: datetime = Field(..., description="Fecha y hora de apertura del turno")
    
    @validator('efectivo_declarado')
    def validate_efectivo(cls, v):
        if v < 0:
            raise ValueError('El efectivo declarado no puede ser negativo')
        return v


class CashClosingResponse(CashClosingBase):
    """Schema de respuesta para cierre de caja"""
    id: int
    empresa_usuario_id: int
    usuario_id: Optional[int]
    fecha_apertura: datetime
    fecha_cierre: datetime
    ingresos_sistema: Decimal
    egresos_sistema: Decimal
    saldo_sistema: Decimal
    diferencia: Decimal
    created_at: datetime
    
    # Datos relacionados
    usuario_nombre: Optional[str] = None

    class Config:
        from_attributes = True


# ========== SCHEMAS DE EXPORTACIÓN ==========

class TransactionExportRow(BaseModel):
    """Schema para exportación a CSV/Excel"""
    id: int
    fecha: str
    tipo: str
    categoria: str
    monto: str
    metodo_pago: str
    referencia: Optional[str]
    usuario: Optional[str]
    notas: Optional[str]
    anulada: str
    motivo_anulacion: Optional[str]
