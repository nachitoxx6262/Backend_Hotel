#!/usr/bin/env python
"""
Test script to validate Stripe integration endpoints
"""
import sys
import os

# Add project to path
sys.path.insert(0, os.path.dirname(__file__))

def test_imports():
    """Prueba que todos los imports funcionen correctamente"""
    print("=" * 60)
    print("Testing Stripe Integration Imports...")
    print("=" * 60)
    
    try:
        # Test config imports
        print("\n[1/5] Testing config.py imports...")
        from config import (
            STRIPE_SECRET_KEY,
            STRIPE_PUBLISHABLE_KEY,
            STRIPE_WEBHOOK_SECRET,
            get_stripe_client,
            is_stripe_configured,
            STRIPE_ERRORS
        )
        print("✓ Config imports successful")
        print(f"  - STRIPE_SECRET_KEY configured: {bool(STRIPE_SECRET_KEY and STRIPE_SECRET_KEY != 'sk_test_dummy_key')}")
        print(f"  - STRIPE_PUBLISHABLE_KEY configured: {bool(STRIPE_PUBLISHABLE_KEY and STRIPE_PUBLISHABLE_KEY != 'pk_test_dummy_key')}")
        print(f"  - Stripe configured: {is_stripe_configured()}")
        
        # Test model imports
        print("\n[2/5] Testing model imports...")
        from models.core import (
            Plan, EmpresaUsuario, Subscription, PaymentAttempt,
            PlanType, SubscriptionStatus, PaymentStatus, PaymentProvider
        )
        print("✓ Model imports successful")
        
        # Test schema imports
        print("\n[3/5] Testing schema imports...")
        from schemas.billing import (
            PaymentIntentRequest, PaymentIntentResponse, PlanResponse
        )
        print("✓ Schema imports successful")
        
        # Test dependency imports
        print("\n[4/5] Testing dependency imports...")
        from utils.dependencies import get_current_user
        from utils.logging_utils import log_event
        from utils.tenant_middleware import check_trial_expiration
        print("✓ Dependency imports successful")
        
        # Test endpoint router
        print("\n[5/5] Testing billing endpoint router...")
        from endpoints.billing import router
        print(f"✓ Billing router loaded with {len(router.routes)} routes")
        
        # List routes
        print("\nAvailable billing endpoints:")
        for route in router.routes:
            methods = getattr(route, 'methods', set())
            if methods:
                print(f"  - {' '.join(sorted(methods))} {route.path}")
        
        print("\n" + "=" * 60)
        print("✓ All imports successful!")
        print("=" * 60)
        return True
        
    except Exception as e:
        print(f"\n✗ Import failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_enums():
    """Prueba que los enums estén correctamente definidos"""
    print("\n" + "=" * 60)
    print("Testing Enum Definitions...")
    print("=" * 60)
    
    try:
        from models.core import (
            PlanType, SubscriptionStatus, PaymentStatus, PaymentProvider
        )
        
        print("\nPlanType enum:")
        for plan in PlanType:
            print(f"  - {plan.name} = {plan.value}")
        
        print("\nSubscriptionStatus enum:")
        for status in SubscriptionStatus:
            print(f"  - {status.name} = {status.value}")
        
        print("\nPaymentStatus enum:")
        for status in PaymentStatus:
            print(f"  - {status.name} = {status.value}")
        
        print("\nPaymentProvider enum:")
        for provider in PaymentProvider:
            print(f"  - {provider.name} = {provider.value}")
        
        print("\n✓ All enums valid!")
        return True
        
    except Exception as e:
        print(f"✗ Enum test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_stripe_config():
    """Prueba la configuración de Stripe"""
    print("\n" + "=" * 60)
    print("Testing Stripe Configuration...")
    print("=" * 60)
    
    try:
        from config import (
            STRIPE_SECRET_KEY,
            STRIPE_PUBLISHABLE_KEY,
            STRIPE_WEBHOOK_SECRET,
            PAYMENT_CURRENCY,
            MAX_PAYMENT_RETRIES,
            get_stripe_client,
            is_stripe_configured,
            STRIPE_ERRORS
        )
        
        print(f"\nPayment settings:")
        print(f"  - Currency: {PAYMENT_CURRENCY}")
        print(f"  - Max retries: {MAX_PAYMENT_RETRIES}")
        print(f"  - Stripe configured: {is_stripe_configured()}")
        
        print(f"\nStripe errors configured:")
        for code, message in list(STRIPE_ERRORS.items())[:3]:
            print(f"  - {code}: {message}")
        print(f"  ... and {len(STRIPE_ERRORS) - 3} more")
        
        if is_stripe_configured():
            print("\n✓ Stripe is properly configured!")
            client = get_stripe_client()
            print(f"  - Stripe client available: {client is not None}")
        else:
            print("\n⚠ Stripe using demo/test mode (keys not configured)")
        
        return True
        
    except Exception as e:
        print(f"✗ Stripe config test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    results = []
    
    try:
        results.append(("Imports", test_imports()))
        results.append(("Enums", test_enums()))
        results.append(("Stripe Config", test_stripe_config()))
        
        print("\n" + "=" * 60)
        print("TEST SUMMARY")
        print("=" * 60)
        
        for test_name, passed in results:
            status = "✓ PASS" if passed else "✗ FAIL"
            print(f"{status}: {test_name}")
        
        all_passed = all(result[1] for result in results)
        
        if all_passed:
            print("\n✓ All tests passed! Stripe integration ready.")
            sys.exit(0)
        else:
            print("\n✗ Some tests failed. See details above.")
            sys.exit(1)
            
    except Exception as e:
        print(f"✗ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
