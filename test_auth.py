#!/usr/bin/env python3
"""Test CV Capture authentication and presign endpoint"""
import requests
import json
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Configuration
BASE_URL = "https://ats-tool.test"
API_URL = f"{BASE_URL}/api"

# Test credentials from config
AUTH_TOKEN = "XXXXXXXXXX123"  # Replace with actual token
API_KEY = "XXXXXXXXXX123"     # Replace with actual API key

def test_auth_me():
    """Test if the auth token is valid by calling /auth/me"""
    print("\n=== Testing Auth Token ===")
    headers = {
        'Authorization': f'Bearer {AUTH_TOKEN}',
        'Accept': 'application/json'
    }
    
    url = f"{API_URL}/cv-capture/auth/me"
    print(f"GET {url}")
    print(f"Headers: {headers}")
    
    try:
        resp = requests.get(url, headers=headers, verify=False, timeout=10)
        print(f"Status: {resp.status_code}")
        print(f"Response: {resp.text[:500]}")
        return resp.status_code == 200
    except Exception as e:
        print(f"Error: {e}")
        return False

def test_presign_with_bearer():
    """Test presign endpoint with Bearer token"""
    print("\n=== Testing Presign with Bearer Token ===")
    headers = {
        'Authorization': f'Bearer {AUTH_TOKEN}',
        'Accept': 'application/json',
        'Content-Type': 'application/json'
    }
    
    payload = {
        "file_name": "test.pdf",
        "file_size": 1024,
        "file_type": "application/pdf",
        "sha256": "abc123def456",
        "source": "download"
    }
    
    url = f"{API_URL}/cv-capture/presign"
    print(f"POST {url}")
    print(f"Headers: {headers}")
    print(f"Payload: {json.dumps(payload, indent=2)}")
    
    try:
        resp = requests.post(url, json=payload, headers=headers, verify=False, timeout=10, allow_redirects=False)
        print(f"Status: {resp.status_code}")
        print(f"Response Headers: {dict(resp.headers)}")
        print(f"Response: {resp.text[:500]}")
        return resp.status_code == 200
    except Exception as e:
        print(f"Error: {e}")
        return False

def test_presign_with_api_key():
    """Test presign endpoint with API Key"""
    print("\n=== Testing Presign with API Key ===")
    headers = {
        'X-Api-Key': API_KEY,
        'Accept': 'application/json',
        'Content-Type': 'application/json'
    }
    
    payload = {
        "file_name": "test.pdf",
        "file_size": 1024,
        "file_type": "application/pdf",
        "sha256": "abc123def456",
        "source": "download"
    }
    
    url = f"{API_URL}/cv-capture/presign"
    print(f"POST {url}")
    print(f"Headers: {headers}")
    print(f"Payload: {json.dumps(payload, indent=2)}")
    
    try:
        resp = requests.post(url, json=payload, headers=headers, verify=False, timeout=10, allow_redirects=False)
        print(f"Status: {resp.status_code}")
        print(f"Response Headers: {dict(resp.headers)}")
        print(f"Response: {resp.text[:500]}")
        return resp.status_code == 200
    except Exception as e:
        print(f"Error: {e}")
        return False

def test_login():
    """Test login endpoint to get a valid token"""
    print("\n=== Testing Login Endpoint ===")
    headers = {
        'Accept': 'application/json',
        'Content-Type': 'application/json'
    }
    
    payload = {
        "email": "test@example.com",
        "password": "password"
    }
    
    url = f"{API_URL}/cv-capture/auth/login"
    print(f"POST {url}")
    print(f"Payload: {json.dumps(payload, indent=2)}")
    
    try:
        resp = requests.post(url, json=payload, headers=headers, verify=False, timeout=10)
        print(f"Status: {resp.status_code}")
        print(f"Response: {resp.text[:500]}")
        return resp.status_code == 200
    except Exception as e:
        print(f"Error: {e}")
        return False

if __name__ == "__main__":
    print("CV Capture Authentication Test Suite")
    print("=" * 50)
    
    # Test login first
    test_login()
    
    # Test auth endpoints
    test_auth_me()
    
    # Test presign with both auth methods
    test_presign_with_bearer()
    test_presign_with_api_key()
