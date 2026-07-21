#!/usr/bin/env python3
"""
Dhan Access Token Generator
Generates (via PIN+TOTP if configured, otherwise manual paste) and saves a
Dhan access token to the .env file.

Unlike Upstox, Dhan has no browser-redirect OAuth flow for a retail app: a
token is either generated automatically with PIN+TOTP, or copied manually
from the Dhan web portal (web.dhan.co -> My Profile -> DhanHQ Trading APIs
-> Access DhanHQ APIs -> Generate Token).
"""

import os
import sys
from dotenv import load_dotenv

_BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_BACKEND_DIR)
_ENV_FILE = os.path.join(_PROJECT_ROOT, ".env")

load_dotenv(_ENV_FILE)

sys.path.insert(0, _BACKEND_DIR)
from dhan_token_manager import dhan_token_manager  # noqa: E402
import config  # noqa: E402


def main():
    print("=" * 80)
    print("DHAN ACCESS TOKEN GENERATOR")
    print("=" * 80)

    client_id = config.DHAN_CLIENT_ID
    if not client_id:
        print("❌ Error: DHAN_CLIENT_ID not found in .env file")
        print("Please add it to your .env file first.")
        return

    print(f"\n✅ Client ID: {client_id}")

    have_totp = bool(config.DHAN_PIN and config.DHAN_TOTP_SECRET)

    if have_totp:
        print("\n" + "=" * 80)
        print("Generating token automatically via PIN + TOTP...")
        print("=" * 80)

        result = dhan_token_manager.generate_access_token_via_totp()

        if result.get("success"):
            print(f"\n✅ {result['message']}")
            print(f"✅ Generated at: {result.get('generated_at')}")
            print("\n⚠️  Remember: Dhan tokens are valid for ~24 hours.")
            print("   Schedule this script to run daily before market open.")
            return
        else:
            print(f"\n❌ Automatic generation failed: {result.get('message')}")
            print("Falling back to manual paste...")

    print("\n" + "=" * 80)
    print("STEP 1: Get your token from the Dhan portal")
    print("=" * 80)
    print(f"\n🌐 Open: {dhan_token_manager.get_login_url()}")
    print("📝 Instructions:")
    print("1. Log in to your Dhan account")
    print("2. Go to My Profile -> DhanHQ Trading APIs")
    print("3. Click 'Generate Token' (or copy your existing valid token)")
    print("4. Paste the token below")

    token = input("\nPaste your Dhan access token: ").strip()

    if not token:
        print("\n❌ No token provided")
        return

    result = dhan_token_manager.save_manual_token(token)

    if result.get("success"):
        print(f"\n✅ {result['message']}")
        print(f"✅ Generated at: {result.get('generated_at')}")
        print("\n" + "=" * 80)
        print("Verifying token...")
        print("=" * 80)
        is_valid, message = dhan_token_manager.validate_token_with_api()
        if is_valid:
            print(f"✅ Token is valid: {message}")
        else:
            print(f"❌ Token verification failed: {message}")
    else:
        print(f"\n❌ {result.get('message')}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n❌ Operation cancelled by user")
