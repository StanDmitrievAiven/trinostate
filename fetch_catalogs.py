#!/usr/bin/env python3
"""
Fetch Trino catalog definitions from PostgreSQL and write .properties files.
Run at container startup to restore catalogs after a restart.
"""
import os
import sys
import json

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
except ImportError:
    print("ERROR: psycopg2 required. Install with: pip install psycopg2-binary", file=sys.stderr)
    sys.exit(1)

INIT_SCHEMA = """
CREATE TABLE IF NOT EXISTS trino_catalogs (
  id SERIAL PRIMARY KEY,
  name VARCHAR(255) UNIQUE NOT NULL,
  properties JSONB NOT NULL,
  created_at TIMESTAMPTZ DEFAULT NOW()
);
"""


def main():
    db_url = os.environ.get("TRINO_CATALOG_DB_URL") or os.environ.get("DATABASE_URL")
    if not db_url:
        print("ERROR: DATABASE_URL or TRINO_CATALOG_DB_URL must be set", file=sys.stderr)
        sys.exit(1)

    # postgres:// -> postgresql:// for psycopg2
    if db_url.startswith("postgres://"):
        db_url = "postgresql://" + db_url[11:]

    catalog_dir = "/etc/trino/catalog"
    os.makedirs(catalog_dir, exist_ok=True)

    conn = psycopg2.connect(db_url)
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute(INIT_SCHEMA)
        print("Schema initialized.")

        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT name, properties FROM trino_catalogs")
            rows = cur.fetchall()

        for row in rows:
            name = row["name"]
            props = row["properties"]
            if isinstance(props, str):
                props = json.loads(props)
            path = os.path.join(catalog_dir, f"{name}.properties")
            with open(path, "w") as f:
                for k, v in props.items():
                    f.write(f"{k}={v}\n")
            print(f"  Wrote catalog: {name}")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
