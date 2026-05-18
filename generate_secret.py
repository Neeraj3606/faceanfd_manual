#!/usr/bin/env python3
"""
Generate a secure SECRET_KEY for production
"""

import secrets
import string

def generate_secret_key(length=64):
    """Generate a secure random secret key"""
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))

if __name__ == "__main__":
    key = generate_secret_key()
    print("=" * 60)
    print("🔐 Generated SECRET_KEY for Production")
    print("=" * 60)
    print(f"\nSECRET_KEY={key}\n")
    print("=" * 60)
    print("📋 Instructions:")
    print("1. Copy the above SECRET_KEY")
    print("2. Open .env file")
    print("3. Replace 'change-this-secret-key-in-production' with this key")
    print("=" * 60)
