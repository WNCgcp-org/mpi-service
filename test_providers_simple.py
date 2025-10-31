#!/usr/bin/env python3
"""
Simple test script to verify provider modularization structure
"""

import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))


def test_imports():
    """Test that all provider modules can be imported"""
    print("Testing provider imports...")

    try:
        # Test base provider
        from providers.base_provider import BaseMPIProvider, MPIResult, ProviderConfig
        print("✓ Base provider imports successful")

        # Test individual providers
        from providers.verato_provider import VeratoProvider, VeratoProviderConfig
        print("✓ Verato provider imports successful")

        from providers.internal import InternalMPIProvider, InternalProviderConfig
        print("✓ Internal provider imports successful")

        from providers.hybrid import HybridMPIProvider, HybridProviderConfig, HybridStrategy
        print("✓ Hybrid provider imports successful")

        # Test package imports
        from providers import PROVIDER_REGISTRY, get_provider_class, create_provider
        print("✓ Provider package imports successful")

        return True

    except Exception as e:
        print(f"✗ Import test failed: {e}")
        return False


def test_provider_registry():
    """Test provider registry functionality"""
    print("\nTesting provider registry...")

    try:
        from providers import PROVIDER_REGISTRY, get_provider_class, create_provider

        # Test registry contents
        expected_providers = ['verato', 'internal', 'hybrid']
        for provider_name in expected_providers:
            assert provider_name in PROVIDER_REGISTRY, f"Missing provider: {provider_name}"
            print(f"✓ {provider_name} registered")

        # Test get_provider_class
        for provider_name in expected_providers:
            provider_class = get_provider_class(provider_name)
            assert provider_class is not None, f"Failed to get class for {provider_name}"
            print(f"✓ get_provider_class('{provider_name}') works")

        # Test create_provider (without config)
        for provider_name in expected_providers:
            provider = create_provider(provider_name)
            assert provider is not None, f"Failed to create {provider_name}"
            print(f"✓ create_provider('{provider_name}') works")

        return True

    except Exception as e:
        print(f"✗ Registry test failed: {e}")
        return False


def test_interface_compliance():
    """Test that providers implement the required interface"""
    print("\nTesting interface compliance...")

    try:
        from providers.base_provider import BaseMPIProvider
        from providers import VeratoProvider, InternalMPIProvider, HybridMPIProvider

        providers = [
            ('VeratoProvider', VeratoProvider),
            ('InternalMPIProvider', InternalMPIProvider),
            ('HybridMPIProvider', HybridMPIProvider)
        ]

        required_methods = [
            'initialize', 'get_mpi_id', 'batch_process',
            'health_check', 'get_stats', 'cleanup'
        ]

        for provider_name, provider_class in providers:
            # Check inheritance
            assert issubclass(provider_class, BaseMPIProvider), f"{provider_name} doesn't inherit from BaseMPIProvider"

            # Check methods
            for method in required_methods:
                assert hasattr(provider_class, method), f"{provider_name} missing method: {method}"

            print(f"✓ {provider_name} implements required interface")

        return True

    except Exception as e:
        print(f"✗ Interface compliance test failed: {e}")
        return False


def test_mpi_result():
    """Test MPIResult functionality"""
    print("\nTesting MPIResult...")

    try:
        from providers.base_provider import MPIResult

        # Test creation
        result = MPIResult(
            mpi_id="TEST-123",
            confidence=0.95,
            provider="test",
            source="test_source"
        )

        assert result.mpi_id == "TEST-123"
        assert result.confidence == 0.95
        assert result.provider == "test"
        assert result.source == "test_source"
        print("✓ MPIResult creation works")

        # Test to_dict
        result_dict = result.to_dict()
        assert isinstance(result_dict, dict)
        assert result_dict['mpi_id'] == "TEST-123"
        assert result_dict['confidence'] == 0.95
        print("✓ MPIResult.to_dict() works")

        # Test with error
        error_result = MPIResult(
            mpi_id=None,
            confidence=0.0,
            provider="test",
            source="error",
            error="Test error"
        )

        error_dict = error_result.to_dict()
        assert 'error' in error_dict
        assert error_dict['error'] == "Test error"
        print("✓ MPIResult with error works")

        return True

    except Exception as e:
        print(f"✗ MPIResult test failed: {e}")
        return False


def test_file_structure():
    """Test that all expected files exist"""
    print("\nTesting file structure...")

    expected_files = [
        'src/providers/__init__.py',
        'src/providers/base_provider.py',
        'src/providers/verato.py',
        'src/providers/verato_provider.py',
        'src/providers/internal.py',
        'src/providers/hybrid.py',
        'src/mpi_service.py',
        'src/main.py'
    ]

    all_exist = True
    for file_path in expected_files:
        if os.path.exists(file_path):
            print(f"✓ {file_path} exists")
        else:
            print(f"✗ {file_path} missing")
            all_exist = False

    return all_exist


def main():
    """Run all tests"""
    print("🧪 Starting Provider Modularization Verification\n")

    tests = [
        ("File Structure", test_file_structure),
        ("Imports", test_imports),
        ("MPIResult", test_mpi_result),
        ("Interface Compliance", test_interface_compliance),
        ("Provider Registry", test_provider_registry)
    ]

    passed = 0
    total = len(tests)

    for test_name, test_func in tests:
        print(f"\n{'='*20} {test_name} {'='*20}")
        try:
            if test_func():
                print(f"✅ {test_name} PASSED")
                passed += 1
            else:
                print(f"❌ {test_name} FAILED")
        except Exception as e:
            print(f"❌ {test_name} FAILED with exception: {e}")

    print(f"\n{'='*60}")
    print(f"🏁 Tests completed: {passed}/{total} passed")

    if passed == total:
        print("🎉 All provider modularization tests PASSED!")
        print("\n✅ Provider modularization verification successful!")
        print("\nSummary:")
        print("- ✅ Base provider interface created")
        print("- ✅ Verato provider follows standard interface")
        print("- ✅ Internal provider created with probabilistic matching")
        print("- ✅ Hybrid provider created with multiple strategies")
        print("- ✅ Provider registry and dynamic loading works")
        print("- ✅ All providers implement required interface")
        return True
    else:
        print("❌ Some tests failed. Please check the output above.")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)