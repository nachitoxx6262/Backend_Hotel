"""
Script para generar datos históricos de prueba
Genera reservas, estadías, cargos y pagos de los últimos 60 días
"""
import sys
import random
from datetime import datetime, timedelta, date
from sqlalchemy.orm import Session
from database.conexion import SessionLocal, engine
from models.core import (
    Cliente, ClienteCorporativo, EmpresaUsuario, Reservation, Stay, Room, RoomType,
    StayRoomOccupancy, StayCharge, StayPayment
)
from models.usuario import Usuario

# Datos de ejemplo
NOMBRES = ["Juan", "María", "Carlos", "Ana", "Pedro", "Laura", "Luis", "Carmen", "Jorge", "Elena"]
APELLIDOS = ["García", "Rodríguez", "Martínez", "López", "González", "Pérez", "Sánchez", "Ramírez", "Torres", "Flores"]
EMPRESAS_NOMBRES = [
    "Constructora ABC", "Tecnología XYZ", "Grupo Industrial MNO", 
    "Servicios Empresariales PQR", "Comercializadora STU"
]

def get_random_phone():
    return f"+502-{random.randint(3000,9999)}-{random.randint(1000,9999)}"

def get_random_email(nombre, apellido):
    return f"{nombre.lower()}.{apellido.lower()}@email.com"

def seed_clientes(db: Session, tenant_id: int, cantidad: int = 50):
    """Crear clientes de prueba"""
    clientes = []
    for i in range(cantidad):
        nombre = random.choice(NOMBRES)
        apellido = random.choice(APELLIDOS)
        cliente = Cliente(
            nombre=nombre,
            apellido=apellido,
            tipo_documento=random.choice(["DNI", "DPI", "Pasaporte"]),
            numero_documento=f"{random.randint(1000000000, 9999999999)}",
            email=get_random_email(nombre, apellido) if random.random() > 0.3 else None,
            telefono=get_random_phone() if random.random() > 0.2 else None,
            empresa_usuario_id=tenant_id,
            created_at=datetime.now() - timedelta(days=random.randint(90, 365))
        )
        db.add(cliente)
        clientes.append(cliente)
    
    db.commit()
    print(f"✅ Creados {cantidad} clientes")
    return clientes

def seed_empresas(db: Session, tenant_id: int):
    """Crear empresas de prueba"""
    empresas = []
    for nombre in EMPRESAS_NOMBRES:
        empresa = ClienteCorporativo(
            nombre=nombre,
            cuit=f"{random.randint(10000000000, 99999999999)}",
            contacto_nombre=random.choice(NOMBRES) + " " + random.choice(APELLIDOS),
            contacto_telefono=get_random_phone(),
            contacto_email=f"info@{nombre.lower().replace(' ', '')}.com",
            activo=True,
            empresa_usuario_id=tenant_id,
            created_at=datetime.now() - timedelta(days=random.randint(180, 730))
        )
        db.add(empresa)
        empresas.append(empresa)
    
    db.commit()
    print(f"✅ Creadas {len(empresas)} empresas")
    return empresas

def seed_historical_reservations(db: Session, tenant_id: int, clientes: list, empresas: list, dias_atras: int = 60):
    """Crear reservas y estadías históricas"""
    
    # Obtener habitaciones y tipos
    rooms = db.query(Room).filter(Room.activo == True, Room.empresa_usuario_id == tenant_id).all()
    room_types = db.query(RoomType).filter(RoomType.empresa_usuario_id == tenant_id).all()
    usuarios = db.query(Usuario).filter(Usuario.empresa_usuario_id == tenant_id, Usuario.deleted.is_(False)).all()
    
    if not rooms:
        print("❌ No hay habitaciones en la base de datos")
        return
    
    if not usuarios:
        print("❌ No hay usuarios en la base de datos")
        return
    
    usuario_sistema = usuarios[0]
    
    # Generar reservas históricas
    total_reservas = 0
    total_stays = 0
    
    fecha_inicio = datetime.now() - timedelta(days=dias_atras)
    
    for dia in range(dias_atras):
        fecha = fecha_inicio + timedelta(days=dia)
        
        # Crear entre 1-5 reservas por día
        num_reservas = random.randint(1, 5)
        
        for _ in range(num_reservas):
            cliente = random.choice(clientes)
            empresa = random.choice(empresas) if random.random() > 0.6 else None
            
            # Duración de la estadía
            duracion = random.randint(1, 7)
            fecha_checkin = fecha.date()
            fecha_checkout = fecha_checkin + timedelta(days=duracion)
            
            # Crear reservación
            reservation = Reservation(
                cliente_id=cliente.id,
                empresa_id=empresa.id if empresa else None,
                empresa_usuario_id=tenant_id,
                fecha_checkin=fecha_checkin,
                fecha_checkout=fecha_checkout,
                estado="cerrada" if fecha_checkout < datetime.now().date() else "confirmada",
                notas=f"Reserva histórica de prueba",
                created_at=fecha
            )
            db.add(reservation)
            db.flush()
            total_reservas += 1
            
            # 80% de las reservas tienen estadía
            if random.random() > 0.2:
                # Crear estadía
                checkin_real = datetime.combine(fecha_checkin, datetime.min.time()) + timedelta(hours=random.randint(14, 18))
                checkout_real = None
                estado = "activa"
                
                if fecha_checkout < datetime.now().date():
                    checkout_real = datetime.combine(fecha_checkout, datetime.min.time()) + timedelta(hours=random.randint(10, 12))
                    estado = "cerrada"
                elif fecha_checkin < datetime.now().date() and fecha_checkout >= datetime.now().date():
                    estado = "activa"
                else:
                    estado = "llegada"
                
                stay = Stay(
                    empresa_usuario_id=tenant_id,
                    reservation_id=reservation.id,
                    estado=estado,
                    checkin_real=checkin_real,
                    checkout_real=checkout_real
                )
                db.add(stay)
                db.flush()
                total_stays += 1
                
                # Asignar habitación(es)
                num_habitaciones = random.randint(1, 2)
                habitaciones_asignadas = random.sample(rooms, min(num_habitaciones, len(rooms)))
                
                for room in habitaciones_asignadas:
                    occupancy = StayRoomOccupancy(
                        stay_id=stay.id,
                        room_id=room.id,
                        desde=checkin_real,
                        hasta=checkout_real if checkout_real else None,
                        motivo="Asignación inicial",
                        creado_por=usuario_sistema.id
                    )
                    db.add(occupancy)
                
                # Generar cargos
                room_type = db.query(RoomType).filter(RoomType.id == habitaciones_asignadas[0].room_type_id).first()
                precio_base = float(room_type.precio_base) if room_type and room_type.precio_base else 250.0
                
                # Cargo por habitación
                for noche in range(duracion):
                    cargo_noche = StayCharge(
                        stay_id=stay.id,
                        tipo="room_revenue",
                        descripcion=f"Habitación - Noche {noche + 1}",
                        cantidad=1,
                        monto_unitario=precio_base,
                        monto_total=precio_base,
                        creado_por=str(usuario_sistema.id),
                        created_at=checkin_real + timedelta(days=noche)
                    )
                    db.add(cargo_noche)
                
                # Cargos adicionales aleatorios
                if random.random() > 0.5:
                    monto_extra = random.uniform(50, 200)
                    cargo_extra = StayCharge(
                        stay_id=stay.id,
                        tipo="servicio",
                        descripcion=random.choice(["Lavandería", "Room Service", "Minibar", "Spa"]),
                        cantidad=1,
                        monto_unitario=monto_extra,
                        monto_total=monto_extra,
                        creado_por=str(usuario_sistema.id),
                        created_at=checkin_real + timedelta(days=random.randint(0, duracion-1))
                    )
                    db.add(cargo_extra)
                
                db.flush()
                
                # Generar pagos si la estadía está cerrada
                if estado == "cerrada":
                    total_cargos = db.query(StayCharge).filter(
                        StayCharge.stay_id == stay.id
                    ).all()
                    
                    total_adeudado = sum(float(c.monto_total) for c in total_cargos)
                    
                    # Pagar el 80-100% del total
                    porcentaje_pago = random.uniform(0.8, 1.0)
                    monto_pagado = total_adeudado * porcentaje_pago
                    
                    # Dividir en 1-3 pagos
                    num_pagos = random.randint(1, 3)
                    for i in range(num_pagos):
                        monto_pago = monto_pagado / num_pagos
                        pago = StayPayment(
                            stay_id=stay.id,
                            monto=monto_pago,
                            metodo=random.choice(["efectivo", "tarjeta", "transferencia"]),
                            referencia=f"PAY-{random.randint(10000, 99999)}",
                            timestamp=checkin_real + timedelta(days=random.randint(0, duracion)),
                            es_reverso=False,
                            usuario=str(usuario_sistema.id)
                        )
                        db.add(pago)
    
    db.commit()
    print(f"✅ Creadas {total_reservas} reservas históricas")
    print(f"✅ Creadas {total_stays} estadías históricas")

def main():
    print("🚀 Iniciando generación de datos históricos...")
    print("=" * 60)
    
    db = SessionLocal()
    
    try:
        # Verificar si ya hay datos
        existing_clientes = db.query(Cliente).count()
        existing_reservas = db.query(Reservation).count()
        
        if existing_reservas > 50:
            respuesta = input(f"⚠️  Ya existen {existing_reservas} reservas. ¿Continuar? (s/n): ")
            if respuesta.lower() != 's':
                print("❌ Operación cancelada")
                return
        
        tenant = db.query(EmpresaUsuario).first()
        if not tenant:
            print("❌ No hay EmpresaUsuario. Crea un tenant primero.")
            return

        # Crear clientes si no hay suficientes
        if existing_clientes < 30:
            print(f"📊 Solo hay {existing_clientes} clientes. Creando más...")
            clientes = seed_clientes(db, tenant.id, 50)
        else:
            print(f"✅ Usando {existing_clientes} clientes existentes")
            clientes = db.query(Cliente).filter(Cliente.empresa_usuario_id == tenant.id).all()
        
        # Crear empresas si no hay
        empresas_count = db.query(ClienteCorporativo).filter(ClienteCorporativo.empresa_usuario_id == tenant.id).count()
        if empresas_count < 3:
            print(f"🏢 Solo hay {empresas_count} empresas. Creando más...")
            empresas = seed_empresas(db, tenant.id)
        else:
            print(f"✅ Usando {empresas_count} empresas existentes")
            empresas = db.query(ClienteCorporativo).filter(ClienteCorporativo.empresa_usuario_id == tenant.id).all()
        
        # Generar datos históricos
        print("\n📅 Generando reservas y estadías históricas (últimos 60 días)...")
        seed_historical_reservations(db, tenant.id, clientes, empresas, dias_atras=60)
        
        print("\n" + "=" * 60)
        print("✅ ¡Datos históricos generados exitosamente!")
        print("\n📊 Resumen:")
        print(f"   - Clientes: {db.query(Cliente).count()}")
        print(f"   - Empresas: {db.query(ClienteCorporativo).count()}")
        print(f"   - Reservas: {db.query(Reservation).count()}")
        print(f"   - Estadías: {db.query(Stay).count()}")
        print(f"   - Ocupaciones: {db.query(StayRoomOccupancy).count()}")
        print(f"   - Cargos: {db.query(StayCharge).count()}")
        print(f"   - Pagos: {db.query(StayPayment).count()}")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    main()
