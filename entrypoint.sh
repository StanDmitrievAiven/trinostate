#!/bin/sh
set -e

# --- Environment Variable Check ---
# Support DATABASE_URL (Aiven) or TRINO_CATALOG_DB_URL
CATALOG_DB_URL="${TRINO_CATALOG_DB_URL:-$DATABASE_URL}"
if [ -z "$CATALOG_DB_URL" ]; then
    echo "ERROR: Database connection required. Set either:"
    echo "  - DATABASE_URL (auto-set when connecting PostgreSQL in Aiven)"
    echo "  - TRINO_CATALOG_DB_URL (for a separate catalog store)"
    exit 1
fi
echo "Using catalog database. Proceeding with startup."
echo "---"

# --- Configure password authentication (if TRINO_ADMIN_USER and TRINO_ADMIN_PASSWORD set) ---
if [ -n "$TRINO_ADMIN_USER" ] && [ -n "$TRINO_ADMIN_PASSWORD" ]; then
    echo "Configuring password authentication..."
    python3 /opt/trino-init/init_password_auth.py
    echo "---"
fi

# --- Initialize schema and fetch catalogs from PG ---
echo "Fetching catalogs from database..."
python3 /opt/trino-init/fetch_catalogs.py
chown -R trino:trino /etc/trino/catalog 2>/dev/null || true
echo "Catalogs synced."
echo "---"

# --- Port configuration (Aiven may inject PORT) ---
if [ -n "$PORT" ]; then
    echo "Configuring Trino to listen on port $PORT"
    CONFIG_FILE="/etc/trino/config.properties"
    if [ -f "$CONFIG_FILE" ]; then
        sed -i "s/^http-server.http.port=.*/http-server.http.port=$PORT/" "$CONFIG_FILE"
        sed -i "s|^discovery.uri=.*|discovery.uri=http://localhost:$PORT|" "$CONFIG_FILE"
    fi
fi

# --- Start Trino ---
# Use launcher directly (bypass run-trino; UBI10-micro lacks runuser)
# Always set node.id=trino (hostnames like pod.ns.svc fail validation)
echo "Starting Trino..."
exec /usr/lib/trino/bin/launcher run --etc-dir /etc/trino -Dnode.id=trino
