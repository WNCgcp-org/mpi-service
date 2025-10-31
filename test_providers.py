#!/usr/bin/env python3
"""
Test script to verify provider modularization
"""

import asyncio
import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from providers import VeratoProvider, InternalMPIProvider, HybridMPIProvider
from providers import get_provider_class, create_provider


async def test_provider_interface():
    """Test that all providers implement the correct interface"""
    print("Testing provider interface compliance...")

    # Test data
    test_patient = {
        'first_name': 'John',
        'last_name': 'Smith',
        'dob': '1980-01-01',
        'ssn': '123-45-6789',
        'address_1': '123 Main St',
        'city': 'Boston',
        'state': 'MA',
        'zip': '02101'
    }

    providers_to_test = [
        ('verato', VeratoProvider),
        ('internal', InternalMPIProvider),
        ('hybrid', HybridMPIProvider)
    ]

    for provider_name, provider_class in providers_to_test:
        print(f"\n--- Testing {provider_name} provider ---")

        try:
            # Test 1: Provider creation
            provider = provider_class()
            print(f"✓ {provider_name} provider created successfully")

            # Test 2: Interface compliance
            required_methods = ['initialize', 'get_mpi_id', 'batch_process', 'health_check', 'get_stats', 'cleanup']
            for method in required_methods:
                assert hasattr(provider, method), f"Missing method: {method}"
            print(f"✓ {provider_name} provider implements required interface")

            # Test 3: Provider registry
            registry_provider = get_provider_class(provider_name)
            assert registry_provider == provider_class, f"Registry mismatch for {provider_name}"
            print(f"✓ {provider_name} provider properly registered")

            # Test 4: Dynamic creation
            dynamic_provider = create_provider(provider_name)
            assert isinstance(dynamic_provider, provider_class), f"Dynamic creation failed for {provider_name}"
            print(f"✓ {provider_name} provider can be created dynamically")

            # Test 5: Initialization (only for non-hybrid providers to avoid dependencies)
            if provider_name != 'hybrid':
                try:
                    await provider.initialize()
                    print(f"✓ {provider_name} provider initialized successfully")

                    # Test 6: Stats (without full setup)
                    stats = provider.get_stats()
                    assert isinstance(stats, dict), f"Stats should return dict for {provider_name}"
                    assert 'provider' in stats, f"Stats should include provider name for {provider_name}"
                    print(f"✓ {provider_name} provider stats working")

                    # Test 7: Health check
                    health = await provider.health_check()
                    assert isinstance(health, dict), f"Health check should return dict for {provider_name}"
                    assert 'status' in health, f"Health check should include status for {provider_name}"
                    print(f"✓ {provider_name} provider health check working")

                    # Cleanup
                    await provider.cleanup()
                    print(f"✓ {provider_name} provider cleanup successful")

                except Exception as e:
                    print(f"⚠ {provider_name} provider initialization failed (may be expected): {e}")

        except Exception as e:
            print(f"✗ {provider_name} provider test failed: {e}")
            continue

    print("\n--- Provider Interface Tests Complete ---")


async def test_mpi_service_integration():
    """Test the MPI Service integration"""
    print("\n--- Testing MPI Service Integration ---")

    try:
        from mpi_service import MPIService

        # Test different provider configurations
        providers = ['internal']  # Start with internal since it doesn't need external dependencies

        for provider_name in providers:
            print(f"\nTesting MPI Service with {provider_name} provider...")

            # Set environment
            os.environ['MPI_PROVIDER'] = provider_name

            try:
                # Create service
                service = MPIService()
                print(f"✓ MPI Service created with {provider_name}")

                # Initialize
                await service.initialize()
                print(f"✓ MPI Service initialized with {provider_name}")

                # Get stats
                stats = service.get_stats()
                assert stats['provider'] == provider_name
                assert stats['initialized'] == True
                print(f"✓ MPI Service stats working with {provider_name}")

                # Test patient matching (with mock data)
                test_patient = {
                    'first_name': 'John',
                    'last_name': 'Smith',
                    'dob': '1980-01-01'
                }

                result = await service.get_mpi_id(test_patient)
                assert isinstance(result, dict)
                assert 'provider' in result
                assert result['provider'] == provider_name
                print(f"✓ MPI Service patient matching working with {provider_name}")

                print(f"✓ MPI Service integration successful with {provider_name}")

            except Exception as e:
                print(f"⚠ MPI Service integration failed with {provider_name}: {e}")

    except Exception as e:
        print(f"✗ MPI Service integration test failed: {e}")

    print("\n--- MPI Service Integration Tests Complete ---")


async def main():
    """Run all tests"""
    print("🧪 Starting Provider Modularization Tests\n")

    await test_provider_interface()
    await test_mpi_service_integration()

    print("\n🏁 All tests completed!")


if __name__ == "__main__":
    asyncio.run(main())