#!/usr/bin/env python3
"""Check available models in speaches service."""
import httpx

def check_models(base_url: str = "http://localhost:8000"):
    """Check available models."""
    
    print(f"Checking models at {base_url}")
    print("=" * 60)
    
    # Try common endpoints
    endpoints = [
        "/v1/models",
        "/models",
        "/v1/audio/models",
    ]
    
    with httpx.Client(timeout=10) as client:
        for endpoint in endpoints:
            url = f"{base_url}{endpoint}"
            print(f"\nTrying: {url}")
            try:
                response = client.get(url)
                if response.status_code == 200:
                    print(f"✓ SUCCESS")
                    data = response.json()
                    print(f"Response: {data}")
                else:
                    print(f"✗ Status {response.status_code}")
            except Exception as e:
                print(f"✗ Error: {e}")
    
    print("\n" + "=" * 60)
    print("\nIf no models endpoint found, try these common Whisper models:")
    print("  - openai/whisper-large-v3")
    print("  - openai/whisper-large-v2")
    print("  - openai/whisper-medium")
    print("  - large-v3")
    print("  - large-v2")
    print("  - medium")

if __name__ == "__main__":
    check_models()
