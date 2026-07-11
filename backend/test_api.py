#!/usr/bin/env python3
"""
Simple test script for Meeting Note Taker API
"""
import requests
import json

API_BASE_URL = "http://localhost:8000"

def test_health():
    """Test health endpoint"""
    print("Testing health endpoint...")
    try:
        response = requests.get(f"{API_BASE_URL}/health")
        print(f"✓ Health check: {response.status_code} - {response.json()}")
        return True
    except Exception as e:
        print(f"✗ Health check failed: {e}")
        return False

def test_list_meetings():
    """Test list meetings endpoint"""
    print("\nTesting list meetings endpoint...")
    try:
        response = requests.get(f"{API_BASE_URL}/api/meetings/list")
        print(f"✓ List meetings: {response.status_code}")
        data = response.json()
        print(f"  Found {data.get('total', 0)} meetings")
        return True
    except Exception as e:
        print(f"✗ List meetings failed: {e}")
        return False

def main():
    """Run tests"""
    print("Meeting Note Taker API Tests\n")
    print("=" * 50)
    
    health_ok = test_health()
    if not health_ok:
        print("\n⚠ API server is not running!")
        print("Start it with: uvicorn api.main:app --reload")
        return
    
    test_list_meetings()
    
    print("\n" + "=" * 50)
    print("✓ Basic tests completed!")

if __name__ == "__main__":
    main()

