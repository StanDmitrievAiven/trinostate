#!/usr/bin/env python3
"""
Helper script to encrypt catalog properties before inserting into trino_catalogs.
Use this when TRINO_CATALOG_ENCRYPTION_KEY is set in your Trino deployment.

Usage:
  # Generate a new encryption key (store as secret in Aiven):
  python3 encrypt_catalog.py --generate-key

  # Encrypt catalog properties for INSERT:
  python3 encrypt_catalog.py --key "YOUR_KEY_OR_PASSPHRASE" --properties '{"connector.name":"postgresql","connection-password":"secret"}'

  # Or from a file:
  python3 encrypt_catalog.py --key "YOUR_KEY" --file catalog.json
"""
import argparse
import base64
import json
import sys

try:
    from cryptography.fernet import Fernet
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
except ImportError:
    print("ERROR: pip install cryptography", file=sys.stderr)
    sys.exit(1)


def get_fernet(key: str) -> Fernet:
    """Create Fernet from key or passphrase (must match fetch_catalogs.py logic)."""
    k = key.encode() if isinstance(key, str) else key
    if len(k) == 44:
        try:
            return Fernet(k)
        except Exception:
            pass
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=b"trino-catalog-store",
        iterations=480000,
    )
    derived = base64.urlsafe_b64encode(kdf.derive(k))
    return Fernet(derived)


def main():
    parser = argparse.ArgumentParser(description="Encrypt Trino catalog properties")
    parser.add_argument("--generate-key", action="store_true", help="Generate a new Fernet key")
    parser.add_argument("--key", help="Encryption key or passphrase")
    parser.add_argument("--properties", help="JSON string of catalog properties")
    parser.add_argument("--file", help="Path to JSON file with catalog properties")
    parser.add_argument("--output-format", choices=["json", "sql"], default="sql",
                        help="Output format: json (for API) or sql (INSERT statement)")
    args = parser.parse_args()

    if args.generate_key:
        key = Fernet.generate_key().decode()
        print("Generated encryption key (store as TRINO_CATALOG_ENCRYPTION_KEY secret):")
        print(key)
        return

    if not args.key:
        print("ERROR: --key required (or use --generate-key)", file=sys.stderr)
        sys.exit(1)

    if args.properties:
        props = json.loads(args.properties)
    elif args.file:
        with open(args.file) as f:
            props = json.load(f)
    else:
        print("ERROR: --properties or --file required", file=sys.stderr)
        sys.exit(1)

    fernet = get_fernet(args.key)
    encrypted = fernet.encrypt(json.dumps(props).encode()).decode()

    result = {"_encrypted": True, "data": encrypted}

    if args.output_format == "sql":
        # Escape single quotes for SQL
        props_sql = json.dumps(result).replace("'", "''")
        print("-- Use this in your INSERT statement:")
        print(f"INSERT INTO trino_catalogs (name, properties) VALUES ('your_catalog_name', '{props_sql}'::jsonb);")
    else:
        print(json.dumps(result))


if __name__ == "__main__":
    main()
