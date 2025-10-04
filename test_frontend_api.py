#!/usr/bin/env python3
"""
Test the frontend API calls to see what's happening.
"""

import requests
import json

def test_frontend_api_calls():
    """Test API calls as the frontend would make them."""
    print("🧪 Testing Frontend API Calls")
    print("=" * 50)
    
    base_url = "http://localhost:8765"
    headers = {
        "accept": "application/json",
        "Authorization": "Bearer dev-token-123",
        "Content-Type": "application/json"
    }
    
    # Test the same endpoints the frontend calls
    endpoints = [
        ("/api/v1/controller/health", "Health check"),
        ("/api/v1/controller/overview", "System overview"),
        ("/api/v1/controller/costs?include_forecast=true&granularity=day", "Cost metrics"),
        ("/api/v1/controller/orchestrators?page_size=100", "Orchestrators list"),
        ("/api/v1/controller/organizations?page_size=5", "Organizations list"),
        ("/api/v1/controller/orchestrators/live", "Live orchestrators"),
        ("/api/v1/controller/logs?page_size=400", "System logs"),
    ]
    
    for endpoint, description in endpoints:
        try:
            response = requests.get(f"{base_url}{endpoint}", headers=headers)
            print(f"\n{description}:")
            print(f"  Status: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                if data.get("success"):
                    print(f"  ✅ Success: {data.get('message', 'OK')}")
                    
                    # Show some data for key endpoints
                    if "organizations" in endpoint:
                        items = data.get("data", {}).get("items", [])
                        print(f"  📊 Organizations: {len(items)} items")
                        if items:
                            print(f"      First org: {items[0].get('name', 'Unknown')}")
                    
                    elif "orchestrators" in endpoint and "live" not in endpoint:
                        items = data.get("data", {}).get("items", [])
                        print(f"  📊 Orchestrators: {len(items)} items")
                        if items:
                            print(f"      First orch: {items[0].get('organization_name', 'Unknown')}")
                    
                    elif "overview" in endpoint:
                        overview_data = data.get("data", {})
                        print(f"  📊 Active Organizations: {overview_data.get('active_organizations', 0)}")
                        print(f"  📊 Total Cost: ${overview_data.get('total_cost', 0)}")
                    
                    elif "costs" in endpoint:
                        cost_data = data.get("data", {})
                        history = cost_data.get("history", [])
                        print(f"  📊 Cost History: {len(history)} data points")
                        if history:
                            print(f"      Latest cost: ${history[-1].get('cost', 0)}")
                
                else:
                    print(f"  ⚠️  API returned success=false")
                    print(f"      Response: {data}")
            else:
                print(f"  ❌ Error: {response.status_code}")
                print(f"      Response: {response.text[:200]}...")
                
        except Exception as e:
            print(f"  ❌ Exception: {e}")
    
    print("\n" + "=" * 50)
    print("🎯 If all endpoints show data, the issue is in the frontend configuration.")
    print("   The frontend might not be sending the Authorization header properly.")

if __name__ == "__main__":
    test_frontend_api_calls()


