#!/usr/bin/env python3
"""
DynaRoute Integration Test
=========================

Tests the DynaRoute service integration with OpenAI fallback.
This script can be run independently to verify the implementation.

Usage:
    python test_dynaroute_integration.py
"""

import asyncio
import os
import sys
from typing import Dict, Any

# Add the app directory to Python path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'orchestrator', 'app'))

# Test environment variables
os.environ['DYNAROUTE_ENABLED'] = 'true'
os.environ['DYNAROUTE_API_KEY'] = 'test_key'  # Will fail and test fallback
os.environ['OPENAI_API_KEY'] = os.getenv('OPENAI_API_KEY', 'test_openai_key')

async def test_dynaroute_service():
    """Test DynaRoute service initialization and configuration"""
    print("🔧 Testing DynaRoute Service Configuration...")

    try:
        from services.dynaroute_service import DynaRouteService, DynaRouteConfig

        # Test configuration from environment
        config = DynaRouteConfig.from_environment()
        print(f"✅ Configuration loaded: enabled={config.enabled}, timeout={config.timeout}")

        # Test service initialization
        service = DynaRouteService(config)
        print(f"✅ Service initialized with {len(service.metrics)} metrics tracked")

        return service

    except Exception as e:
        print(f"❌ Service initialization failed: {e}")
        return None

async def test_health_check(service):
    """Test health check functionality"""
    print("\n🏥 Testing Health Check...")

    try:
        health = await service.health_check()
        print(f"✅ Health check completed:")
        print(f"   - Overall status: {health.get('status')}")
        print(f"   - DynaRoute available: {health.get('dynaroute', {}).get('available')}")
        print(f"   - OpenAI available: {health.get('openai', {}).get('available')}")
        print(f"   - Circuit breaker open: {health.get('circuit_breaker', {}).get('is_open')}")

        return health.get('status') == 'healthy'

    except Exception as e:
        print(f"❌ Health check failed: {e}")
        return False

async def test_chat_completion_fallback(service):
    """Test chat completion with fallback (DynaRoute should fail, OpenAI should work)"""
    print("\n💬 Testing Chat Completion (Fallback Scenario)...")

    test_messages = [
        {"role": "user", "content": "Say 'Integration test successful' in 3 words"}
    ]

    try:
        response = await service.chat_completion(
            messages=test_messages,
            model="gpt-4o-mini",
            max_tokens=20,
            user_id="test_user",
            service_name="integration_test"
        )

        print(f"✅ Chat completion successful:")
        print(f"   - Response: {response.choices[0].message.content[:100]}")
        print(f"   - Model used: {response.model}")
        print(f"   - Has usage info: {'usage' in response}")

        # Check if DynaRoute was used or fell back to OpenAI
        if hasattr(response, 'dynaroute_metadata'):
            print("   - ✅ Used DynaRoute (with metadata)")
        else:
            print("   - ⚠️  Used OpenAI fallback (expected with test key)")

        return True

    except Exception as e:
        print(f"❌ Chat completion failed: {e}")
        return False

async def test_metrics(service):
    """Test metrics collection"""
    print("\n📊 Testing Metrics Collection...")

    try:
        metrics = service.get_metrics()
        print(f"✅ Metrics collected:")
        print(f"   - Total requests: {metrics.get('total_requests')}")
        print(f"   - DynaRoute requests: {metrics.get('dynaroute_requests')}")
        print(f"   - OpenAI fallback requests: {metrics.get('openai_fallback_requests')}")
        print(f"   - Success rate: {metrics.get('success_rate', 0):.2%}")
        print(f"   - DynaRoute usage rate: {metrics.get('dynaroute_usage_rate', 0):.2%}")

        return True

    except Exception as e:
        print(f"❌ Metrics collection failed: {e}")
        return False

async def test_config_info(service):
    """Test configuration info"""
    print("\n⚙️  Testing Configuration Info...")

    try:
        config_info = service.get_config_info()
        print(f"✅ Configuration info retrieved:")
        print(f"   - DynaRoute enabled: {config_info.get('dynaroute_enabled')}")
        print(f"   - DynaRoute available: {config_info.get('dynaroute_available')}")
        print(f"   - API key configured: {config_info.get('api_key_configured')}")
        print(f"   - Timeout: {config_info.get('timeout')}s")

        return True

    except Exception as e:
        print(f"❌ Configuration info failed: {e}")
        return False

async def test_integration_with_original_interface():
    """Test that the DynaRoute service works as a drop-in replacement"""
    print("\n🔄 Testing Drop-in Replacement Compatibility...")

    try:
        from services.dynaroute_service import get_dynaroute_service

        # This should work exactly like get_openai_proxy()
        proxy = get_dynaroute_service()

        # Test that it has the same interface as OpenAI proxy
        required_methods = ['chat_completion', 'embedding', 'health_check']

        for method in required_methods:
            if not hasattr(proxy, method):
                print(f"❌ Missing required method: {method}")
                return False
            print(f"✅ Has required method: {method}")

        print("✅ Interface compatibility confirmed")
        return True

    except Exception as e:
        print(f"❌ Interface compatibility test failed: {e}")
        return False

async def main():
    """Run all tests"""
    print("🚀 DynaRoute Integration Test Suite")
    print("=" * 50)

    results = []

    # Test 1: Service initialization
    service = await test_dynaroute_service()
    results.append(service is not None)

    if service:
        # Test 2: Health check
        results.append(await test_health_check(service))

        # Test 3: Chat completion with fallback
        results.append(await test_chat_completion_fallback(service))

        # Test 4: Metrics
        results.append(await test_metrics(service))

        # Test 5: Configuration info
        results.append(await test_config_info(service))

    # Test 6: Interface compatibility
    results.append(await test_integration_with_original_interface())

    # Summary
    print("\n" + "=" * 50)
    print("🎯 Test Results Summary")
    passed = sum(results)
    total = len(results)

    print(f"✅ Passed: {passed}/{total}")
    if passed < total:
        print(f"❌ Failed: {total - passed}/{total}")

    if passed == total:
        print("🎉 All tests passed! DynaRoute integration is ready.")
        return 0
    else:
        print("⚠️  Some tests failed. Review the output above.")
        return 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)