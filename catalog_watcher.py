#!/usr/bin/env python3
"""
Watch trino_catalogs in PostgreSQL and run CREATE CATALOG for new catalogs.
Requires catalog.management=dynamic in Trino config.
Runs in background; no Trino restart needed when catalogs are added to PG.
"""
import os
import sys
import json
import base64
import time
import urllib.request
import ssl

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
except ImportError:
    print("ERROR: psycopg2 required", file=sys.stderr)
    sys.exit(1)

try:
    from cryptography.fernet import Fernet
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
except ImportError:
    Fernet = None

TRINO_URL = os.environ.get("TRINO_INTERNAL_URL", "http://127.0.0.1:8080")
TRINO_USER = os.environ.get("TRINO_ADMIN_USER", "admin")
TRINO_PASSWORD = os.environ.get("TRINO_ADMIN_PASSWORD", "")
POLL_INTERVAL = int(os.environ.get("CATALOG_WATCHER_INTERVAL", "60"))


def _get_fernet(encryption_key: str):
    if not Fernet:
        return None
    key = encryption_key.encode() if isinstance(encryption_key, str) else encryption_key
    try:
        return Fernet(key)
    except Exception:
        pass
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=b"trino-catalog-store",
        iterations=480000,
    )
    derived = base64.urlsafe_b64encode(kdf.derive(key))
    return Fernet(derived)


def _decrypt_properties(props, fernet):
    if not isinstance(props, dict) or not props.get("_encrypted") or "data" not in props:
        return props
    try:
        decrypted = fernet.decrypt(props["data"].encode()).decode()
        return json.loads(decrypted)
    except Exception:
        return props


def trino_query(query: str) -> list:
    """Execute query on Trino via REST API."""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    req = urllib.request.Request(
        f"{TRINO_URL}/v1/statement",
        data=query.encode("utf-8"),
        headers={
            "Content-Type": "application/text",
            "X-Trino-User": TRINO_USER,
        },
        method="POST",
    )
    if TRINO_PASSWORD:
        import base64 as b64
        auth = b64.b64encode(f"{TRINO_USER}:{TRINO_PASSWORD}".encode()).decode()
        req.add_header("Authorization", f"Basic {auth}")
    with urllib.request.urlopen(req, context=ctx, timeout=10) as r:
        data = json.loads(r.read().decode())
    next_uri = data.get("nextUri")
    while next_uri:
        time.sleep(0.2)
        req = urllib.request.Request(next_uri, method="GET")
        if TRINO_PASSWORD:
            req.add_header("Authorization", f"Basic {auth}")
        with urllib.request.urlopen(req, context=ctx, timeout=10) as r:
            data = json.loads(r.read().decode())
        if data.get("error"):
            raise RuntimeError(data["error"].get("message", str(data["error"])))
        if data.get("data"):
            return data["data"]
        next_uri = data.get("nextUri")
    return []


def get_trino_catalogs() -> set:
    """Get set of catalog names from Trino."""
    rows = trino_query("SHOW CATALOGS")
    return {r[0] for r in rows} if rows else set()


def build_create_catalog_sql(name: str, props: dict, kafka_config_path: str = None) -> str:
    """Build CREATE CATALOG SQL from properties."""
    connector = props.get("connector.name", "memory")
    if props.get("connector.name") == "kafka":
        invalid = {"kafka.sasl.jaas.config", "kafka.sasl.mechanism", "kafka.security.protocol",
                   "kafka.ssl.endpoint.identification.algorithm"}
        props = {k: v for k, v in props.items() if k not in invalid}
        if kafka_config_path:
            props["kafka.config.resources"] = kafka_config_path
    parts = []
    for k, v in props.items():
        if k == "connector.name":
            continue
        # Escape single quotes in value: ' -> ''
        v_escaped = str(v).replace("'", "''")
        # Property names with - need double quotes
        key = f'"{k}"' if "-" in k or "." in k else k
        parts.append(f"{key} = '{v_escaped}'")
    with_clause = " WITH (" + ", ".join(parts) + ")" if parts else ""
    return f'CREATE CATALOG "{name}" USING {connector}{with_clause}'


def main():
    db_url = os.environ.get("TRINO_CATALOG_DB_URL") or os.environ.get("DATABASE_URL")
    if not db_url:
        print("ERROR: DATABASE_URL required", file=sys.stderr)
        sys.exit(1)
    if db_url.startswith("postgres://"):
        db_url = "postgresql://" + db_url[11:]

    encryption_key = os.environ.get("TRINO_CATALOG_ENCRYPTION_KEY")
    fernet = _get_fernet(encryption_key) if encryption_key else None

    kafka_config_path = "/etc/trino/kafka-client.properties"
    kafka_config_exists = os.path.exists(kafka_config_path)

    seen = set()
    print(f"Catalog watcher started. Polling every {POLL_INTERVAL}s. New catalogs in PG will be added without restart.")

    while True:
        try:
            trino_catalogs = get_trino_catalogs()
            conn = psycopg2.connect(db_url)
            try:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute("SELECT name, properties FROM trino_catalogs")
                    rows = cur.fetchall()
                for row in rows:
                    name = row["name"]
                    props = row["properties"]
                    if isinstance(props, str):
                        props = json.loads(props)
                    if fernet and isinstance(props, dict):
                        props = _decrypt_properties(props, fernet)
                    if name in trino_catalogs:
                        continue
                    if name in seen:
                        continue
                    try:
                        sql = build_create_catalog_sql(name, dict(props), kafka_config_path if kafka_config_exists else None)
                        trino_query(sql)
                        print(f"  Added catalog: {name}")
                        seen.add(name)
                        trino_catalogs.add(name)
                    except Exception as e:
                        print(f"  Failed to add {name}: {e}", file=sys.stderr)
            finally:
                conn.close()
        except Exception as e:
            print(f"Watcher error: {e}", file=sys.stderr)
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
