#!/usr/bin/env python3
"""Test Brave Search API connectivity."""

import os
import requests

def test_brave_search():
    """Test if Brave Search API is working."""
    api_key = os.environ.get("BRAVE_API_KEY")

    print("=" * 60)
    print("Brave Search API Test")
    print("=" * 60)
    print()

    # Check if API key is set
    if not api_key:
        print("❌ BRAVE_API_KEY environment variable is NOT set")
        print()
        print("To fix this:")
        print("1. Get a free API key at: https://brave.com/search/api/")
        print("2. Set it as an environment variable:")
        print("   export BRAVE_API_KEY=your_api_key_here")
        print()
        return False

    print(f"✓ BRAVE_API_KEY is set: {api_key[:10]}...{api_key[-4:]}")
    print()

    # Test API call
    print("Testing API call...")
    try:
        headers = {"X-Subscription-Token": api_key, "Accept": "application/json"}
        params = {"q": "test query", "count": 1}

        response = requests.get(
            "https://api.search.brave.com/res/v1/web/search",
            headers=headers,
            params=params,
            timeout=10,
        )

        print(f"Status Code: {response.status_code}")
        print()

        if response.status_code == 200:
            data = response.json()
            results = data.get("web", {}).get("results", [])
            print(f"✓ API call successful!")
            print(f"✓ Found {len(results)} results")

            if results:
                print()
                print("Sample result:")
                print(f"  Title: {results[0].get('title', 'N/A')}")
                print(f"  URL: {results[0].get('url', 'N/A')}")

            return True

        elif response.status_code == 401:
            print("❌ Authentication failed - API key is invalid")
            print("Get a new key at: https://brave.com/search/api/")
            return False

        elif response.status_code == 429:
            print("❌ Rate limit exceeded")
            print("Free tier allows 15,000 queries/month")
            return False

        else:
            print(f"❌ API returned error status: {response.status_code}")
            print(f"Response: {response.text[:200]}")
            return False

    except requests.exceptions.Timeout:
        print("❌ Request timed out")
        return False

    except requests.exceptions.ConnectionError:
        print("❌ Connection error - check your internet connection")
        return False

    except Exception as e:
        print(f"❌ Error: {e}")
        return False

if __name__ == "__main__":
    success = test_brave_search()
    print()
    print("=" * 60)
    if success:
        print("Result: Brave Search is working! ✓")
    else:
        print("Result: Brave Search is NOT available ✗")
    print("=" * 60)
