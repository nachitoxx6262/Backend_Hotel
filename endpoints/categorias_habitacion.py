"""
Endpoints para gestión de Categorías de Habitaciones
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import and_
from datetime import datetime
from database.conexion import SessionLocal
from models import CategoriaHabitacion
from schemas.categorias import CategoriaCreate, CategoriaUpdate, CategoriaRead
from utils.logging_utils import log_event

router = APIRouter(prefix="/categorias", tags=["Categorías"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("", response_model=list[CategoriaRead])
def listar_categorias(db: Session = Depends(get_db)):
    """Listar todas las categorías activas"""
    try:
        categorias = db.query(CategoriaHabitacion).filter(
            CategoriaHabitacion.activo.is_(True)
        ).order_by(CategoriaHabitacion.nombre).all()
        
        return categorias
    except Exception as e:
        log_event("CATEGORIAS", "sistema", "ERROR", f"Error listando: {str(e)}")
        raise HTTPException(status_code=500, detail="Error al listar categorías")


@router.get("/{categoria_id}", response_model=CategoriaRead)
def obtener_categoria(categoria_id: int, db: Session = Depends(get_db)):
    """Obtener una categoría específica"""
    try:
        categoria = db.query(CategoriaHabitacion).filter(
            CategoriaHabitacion.id == categoria_id
        ).first()
        
        if not categoria:
            raise HTTPException(status_code=404, detail="Categoría no encontrada")
        
        return categoria
    except HTTPException:
        raise
    except Exception as e:
        log_event("CATEGORIAS", "sistema", "ERROR", f"Error obteniendo {categoria_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Error al obtener categoría")


@router.post("", response_model=CategoriaRead)
def crear_categoria(categoria: CategoriaCreate, db: Session = Depends(get_db)):
    """Crear nueva categoría de habitación"""
    try:
        # Validaciones
        if not categoria.nombre or not categoria.nombre.strip():
            raise HTTPException(status_code=400, detail="El nombre es obligatorio")
        
        nombre_limpio = categoria.nombre.strip()
        
        # Verificar duplicados
        existe = db.query(CategoriaHabitacion).filter(
            CategoriaHabitacion.nombre.ilike(nombre_limpio)
        ).first()
        
        if existe:
            raise HTTPException(status_code=409, detail=f"La categoría '{nombre_limpio}' ya existe")
        
        # Validar capacidad
        if not categoria.capacidad_personas or categoria.capacidad_personas < 1:
            raise HTTPException(status_code=400, detail="La capacidad debe ser mayor a 0")
        
        # Validar precio
        if categoria.precio_base_noche is None or categoria.precio_base_noche < 0:
            raise HTTPException(status_code=400, detail="El precio no puede ser negativo")
        
        # Crear categoría
        nueva_categoria = CategoriaHabitacion(
            nombre=nombre_limpio,
            descripcion=categoria.descripcion.strip() if categoria.descripcion else None,
            capacidad_personas=categoria.capacidad_personas,
            precio_base_noche=categoria.precio_base_noche,
            amenidades=categoria.amenidades if categoria.amenidades else [],
            activo=True,
            creado_en=datetime.utcnow()
        )
        
        db.add(nueva_categoria)
        db.commit()
        db.refresh(nueva_categoria)
        
        log_event("CATEGORIAS", "sistema", "CREATE", f"Categoría: {nombre_limpio} (ID: {nueva_categoria.id})")
        
        return nueva_categoria
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        log_event("CATEGORIAS", "sistema", "ERROR", f"Error creando: {str(e)}")
        raise HTTPException(status_code=500, detail="Error al crear categoría")


@router.put("/{categoria_id}", response_model=CategoriaRead)
def actualizar_categoria(categoria_id: int, categoria: CategoriaUpdate, db: Session = Depends(get_db)):
    """Actualizar categoría existente"""
    try:
        # Buscar categoría
        db_categoria = db.query(CategoriaHabitacion).filter(
            CategoriaHabitacion.id == categoria_id
        ).first()
        
        if not db_categoria:
            raise HTTPException(status_code=404, detail="Categoría no encontrada")
        
        # Validaciones
        if categoria.nombre and categoria.nombre.strip():
            nombre_limpio = categoria.nombre.strip()
            
            # Verificar duplicados (si cambió el nombre)
            if nombre_limpio != db_categoria.nombre:
                existe = db.query(CategoriaHabitacion).filter(
                    CategoriaHabitacion.nombre.ilike(nombre_limpio)
                ).first()
                
                if existe:
                    raise HTTPException(status_code=409, detail=f"La categoría '{nombre_limpio}' ya existe")
            
            db_categoria.nombre = nombre_limpio
        
        if categoria.descripcion is not None:
            db_categoria.descripcion = categoria.descripcion.strip() if categoria.descripcion else None
        
        if categoria.capacidad_personas is not None:
            if categoria.capacidad_personas < 1:
                raise HTTPException(status_code=400, detail="La capacidad debe ser mayor a 0")
            db_categoria.capacidad_personas = categoria.capacidad_personas
        
        if categoria.precio_base_noche is not None:
            if categoria.precio_base_noche < 0:
                raise HTTPException(status_code=400, detail="El precio no puede ser negativo")
            db_categoria.precio_base_noche = categoria.precio_base_noche
        
        if categoria.amenidades is not None:
            db_categoria.amenidades = categoria.amenidades
        
        if categoria.activo is not None:
            db_categoria.activo = categoria.activo
        
        # Actualizar timestamp
        db_categoria.actualizado_en = datetime.utcnow()
        
        db.commit()
        db.refresh(db_categoria)
        
        log_event("CATEGORIAS", "sistema", "UPDATE", f"Categoría: {db_categoria.nombre} (ID: {categoria_id})")
        
        return db_categoria
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        log_event("CATEGORIAS", "sistema", "ERROR", f"Error actualizando {categoria_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Error al actualizar categoría")


@router.delete("/{categoria_id}")
def eliminar_categoria(categoria_id: int, db: Session = Depends(get_db)):
    """Eliminar categoría (verificar que no tenga habitaciones)"""
    try:
        # Buscar categoría
        categoria = db.query(CategoriaHabitacion).filter(
            CategoriaHabitacion.id == categoria_id
        ).first()
        
        if not categoria:
            raise HTTPException(status_code=404, detail="Categoría no encontrada")
        
        # Verificar si tiene habitaciones asociadas
        habitaciones = db.query(Habitacion).filter(
            Habitacion.categoria_id == categoria_id
        ).count()
        
        if habitaciones > 0:
            raise HTTPException(
                status_code=409, 
                detail=f"No se puede eliminar. Hay {habitaciones} habitación(es) usando esta categoría"
            )
        
        nombre = categoria.nombre
        db.delete(categoria)
        db.commit()
        
        log_event("CATEGORIAS", "sistema", "DELETE", f"Categoría: {nombre} (ID: {categoria_id})")
        
        return {"message": f"Categoría '{nombre}' eliminada"}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        log_event("CATEGORIAS", "sistema", "ERROR", f"Error eliminando {categoria_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Error al eliminar categoría")


# Importar después para evitar circular imports
from models import Habitacion
