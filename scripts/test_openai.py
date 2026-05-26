#!/usr/bin/env python3
"""Check OpenAI API key connectivity and models."""

import os
import sys
import json
import urllib.request
import urllib.error
from pathlib import Path
from dotenv import load_dotenv

def main() -> int:
    # Load dotenv from current directory
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)
    else:
        load_dotenv()

    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key or api_key == "sk-your-key-here":
        print("❌ Error: OPENAI_API_KEY is not set or is still the placeholder in .env")
        print("Please edit the .env file in the project root or set it in your terminal:")
        print("  export OPENAI_API_KEY=\"your-actual-key\"")
        return 1

    # Obfuscate key for printing
    masked_key = api_key[:6] + "..." + api_key[-4:] if len(api_key) > 10 else "invalid"
    print(f"Checking OpenAI API connection with key: {masked_key}")

    # Use urllib for standard library request to avoid any SDK version mismatch
    url = "https://api.openai.com/v1/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    data = {
        "model": "gpt-4o-mini",
        "messages": [{"role": "user", "content": "Hello, is this key working?"}],
        "max_tokens": 10
    }

    req = urllib.request.Request(
        url,
        data=json.dumps(data).encode("utf-8"),
        headers=headers,
        method="POST"
    )

    try:
        print("Sending request to OpenAI API (gpt-4o-mini)...")
        with urllib.request.urlopen(req, timeout=10) as response:
            res_data = json.loads(response.read().decode("utf-8"))
            reply = res_data["choices"][0]["message"]["content"].strip()
            print("✅ Success! Connection verified.")
            print(f"Response: \"{reply}\"")
            return 0
    except urllib.error.HTTPError as e:
        print(f"❌ HTTP Error {e.code}: {e.reason}")
        try:
            err_body = e.read().decode("utf-8")
            err_json = json.loads(err_body)
            print(f"Details: {err_json.get('error', {}).get('message', err_body)}")
        except Exception:
            pass
        return 1
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())
