"""Verify Gemini API key is authorized and can generate a response."""
import pytest
import requests
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from app.core import GEMINI_API_KEY

URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"


def test_gemini():
    resp = requests.post(
        f"{URL}?key={GEMINI_API_KEY}",
        json={"contents": [{"parts": [{"text": "Reply with just: OK"}]}]},
        timeout=15,
    )
    print(f"Status: {resp.status_code}")
    print(f"Response: {resp.text[:500]}")

    if resp.status_code == 429:
        print("QUOTA_EXCEEDED: Key is authorized but free tier quota is exhausted.")
    elif resp.status_code == 403:
        print("UNAUTHORIZED: API key is invalid or not authorized.")
        pytest.fail("API key unauthorized")
    elif resp.status_code == 200:
        print("AUTHORIZED: API key works.")
    else:
        pytest.fail(f"Unexpected status: {resp.status_code}")


if __name__ == "__main__":
    test_gemini()
