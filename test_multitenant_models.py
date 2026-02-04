#!/usr/bin/env python3
"""
Test de validación: Verificar que todos los modelos multi-tenant importan correctamente
"""

def test_imports():
    """Test que todos los imports funcionan"""
    try:
        print("🔍 Testing imports...")
        
        # Models core
        from models.core import (
            Plan, PlanType,
            EmpresaUsuario,
            Subscription, SubscriptionStatus,
            PaymentAttempt, PaymentStatus, PaymentProvider,
            ClienteCorporativo,
            Cliente,
            RoomType,
            Room,
            DailyRate,
            Reservation,
            Stay,
            HousekeepingTask,
            HotelSettings,
        )
        print("   ✅ models/core.py imports OK")
        
        # Models usuario
        from models.usuario import Usuario
        print("   ✅ models/usuario.py imports OK")
        
        # Models rol
        from models.rol import Rol, Permiso, RolPermiso
        print("   ✅ models/rol.py imports OK")
        
        return True
    except ImportError as e:
        print(f"   ❌ Import Error: {str(e)}")
        return False
    except SyntaxError as e:
        print(f"   ❌ Syntax Error: {str(e)}")
        return False
    except Exception as e:
        print(f"   ❌ Unexpected Error: {str(e)}")
        return False

def test_enums():
    """Test que los enums se definieron correctamente"""
    try:
        print("🔍 Testing enums...")
        
        from models.core import PlanType, SubscriptionStatus, PaymentStatus, PaymentProvider
        
        # PlanType
        assert PlanType.DEMO.value == "demo"
        assert PlanType.BASICO.value == "basico"
        assert PlanType.PREMIUM.value == "premium"
        print("   ✅ PlanType enum OK")
        
        # SubscriptionStatus
        assert SubscriptionStatus.ACTIVO.value == "activo"
        assert SubscriptionStatus.VENCIDO.value == "vencido"
        print("   ✅ SubscriptionStatus enum OK")
        
        # PaymentStatus
        assert PaymentStatus.PENDIENTE.value == "pendiente"
        assert PaymentStatus.EXITOSO.value == "exitoso"
        assert PaymentStatus.FALLIDO.value == "fallido"
        print("   ✅ PaymentStatus enum OK")
        
        # PaymentProvider
        assert PaymentProvider.DUMMY.value == "dummy"
        assert PaymentProvider.MERCADO_PAGO.value == "mercado_pago"
        assert PaymentProvider.STRIPE.value == "stripe"
        print("   ✅ PaymentProvider enum OK")
        
        return True
    except (AssertionError, AttributeError) as e:
        print(f"   ❌ Enum Error: {str(e)}")
        return False
    except Exception as e:
        print(f"   ❌ Unexpected Error: {str(e)}")
        return False

def test_model_structure():
    """Test que los modelos tienen la estructura correcta"""
    try:
        print("🔍 Testing model structure...")
        
        from models.core import EmpresaUsuario, Subscription, PaymentAttempt, ClienteCorporativo
        from models.usuario import Usuario
        from models.rol import Rol
        
        # Verificar que las clases tienen __tablename__
        assert hasattr(EmpresaUsuario, '__tablename__')
        assert EmpresaUsuario.__tablename__ == "empresa_usuarios"
        print("   ✅ EmpresaUsuario structure OK")
        
        assert hasattr(Subscription, '__tablename__')
        assert Subscription.__tablename__ == "subscriptions"
        print("   ✅ Subscription structure OK")
        
        assert hasattr(Usuario, '__tablename__')
        assert Usuario.__tablename__ == "usuarios"
        print("   ✅ Usuario structure OK")
        
        assert hasattr(Rol, '__tablename__')
        assert Rol.__tablename__ == "roles"
        print("   ✅ Rol structure OK")
        
        return True
    except (AssertionError, AttributeError) as e:
        print(f"   ❌ Structure Error: {str(e)}")
        return False
    except Exception as e:
        print(f"   ❌ Unexpected Error: {str(e)}")
        return False

def test_fk_columns():
    """Test que las columnas de FK fueron agregadas"""
    try:
        print("🔍 Testing FK columns...")
        
        from models.usuario import Usuario
        from models.core import Room, RoomType, Reservation, Stay, HousekeepingTask, HotelSettings
        from models.rol import Rol
        
        # Usuario debe tener empresa_usuario_id y es_super_admin
        # Verificar a través de la inspección de columnas
        from sqlalchemy import inspect
        
        usuario_cols = {c.name for c in inspect(Usuario).columns}
        assert 'empresa_usuario_id' in usuario_cols, "Usuario missing empresa_usuario_id"
        assert 'es_super_admin' in usuario_cols, "Usuario missing es_super_admin"
        print("   ✅ Usuario.empresa_usuario_id + es_super_admin OK")
        
        room_cols = {c.name for c in inspect(Room).columns}
        assert 'empresa_usuario_id' in room_cols, "Room missing empresa_usuario_id"
        print("   ✅ Room.empresa_usuario_id OK")
        
        roomtype_cols = {c.name for c in inspect(RoomType).columns}
        assert 'empresa_usuario_id' in roomtype_cols, "RoomType missing empresa_usuario_id"
        print("   ✅ RoomType.empresa_usuario_id OK")
        
        reservation_cols = {c.name for c in inspect(Reservation).columns}
        assert 'empresa_usuario_id' in reservation_cols, "Reservation missing empresa_usuario_id"
        print("   ✅ Reservation.empresa_usuario_id OK")
        
        stay_cols = {c.name for c in inspect(Stay).columns}
        assert 'empresa_usuario_id' in stay_cols, "Stay missing empresa_usuario_id"
        print("   ✅ Stay.empresa_usuario_id OK")
        
        hk_cols = {c.name for c in inspect(HousekeepingTask).columns}
        assert 'empresa_usuario_id' in hk_cols, "HousekeepingTask missing empresa_usuario_id"
        print("   ✅ HousekeepingTask.empresa_usuario_id OK")
        
        settings_cols = {c.name for c in inspect(HotelSettings).columns}
        assert 'empresa_usuario_id' in settings_cols, "HotelSettings missing empresa_usuario_id"
        print("   ✅ HotelSettings.empresa_usuario_id OK")
        
        rol_cols = {c.name for c in inspect(Rol).columns}
        assert 'empresa_usuario_id' in rol_cols, "Rol missing empresa_usuario_id"
        print("   ✅ Rol.empresa_usuario_id OK")
        
        return True
    except (AssertionError, AttributeError) as e:
        print(f"   ❌ FK Column Error: {str(e)}")
        return False
    except Exception as e:
        print(f"   ❌ Unexpected Error: {str(e)}")
        return False

def main():
    print("=" * 70)
    print("🧪 MULTI-TENANT MODELS VALIDATION TEST")
    print("=" * 70)
    
    all_passed = True
    
    # Test 1: Imports
    if not test_imports():
        all_passed = False
    
    # Test 2: Enums
    if not test_enums():
        all_passed = False
    
    # Test 3: Model structure
    if not test_model_structure():
        all_passed = False
    
    # Test 4: FK columns
    try:
        if not test_fk_columns():
            all_passed = False
    except Exception as e:
        print(f"   ⚠️  FK test skipped (DB not accessible): {str(e)}")
    
    print("=" * 70)
    if all_passed:
        print("✅ ALL VALIDATION TESTS PASSED")
        print("   System is ready for migration execution")
    else:
        print("❌ SOME TESTS FAILED")
        print("   Please fix errors above before running migrations")
    print("=" * 70)
    
    return all_passed

if __name__ == "__main__":
    import sys
    sys.exit(0 if main() else 1)
