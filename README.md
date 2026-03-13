# Trino on Aiven App Runtime

This repository contains a Docker-based deployment for [Trino](https://trino.io/) on Aiven's App Runtime platform, with **catalog and connector configuration persisted in PostgreSQL**. After a container restart, Trino restores all catalogs from the database—no lost connections.

## Overview

- Extends the official `trinodb/trino` Docker image
- Stores catalog definitions in a PostgreSQL table (`trino_catalogs`)
- On startup, fetches catalogs from PG and writes `.properties` files to `/etc/trino/catalog/`
- Single-node mode (coordinator + worker in one container), suitable for stateless Aiven apps

## Prerequisites

- Aiven account with App Runtime access
- PostgreSQL database service in Aiven (for catalog storage)
- Git repository access (this repo)

## Required Environment Variables

### Database Connection

- `DATABASE_URL` – Auto-set when you connect a PostgreSQL service in Aiven's "Connect services" step
- `TRINO_CATALOG_DB_URL` – Optional. Use a different PostgreSQL for catalog storage than `DATABASE_URL`

### Optional

- `PORT` – If Aiven injects a `PORT` env var, Trino will listen on it instead of 8080

## PostgreSQL Schema

The entrypoint creates the `trino_catalogs` table automatically. For reference, the schema is:

```sql
CREATE TABLE IF NOT EXISTS trino_catalogs (
  id SERIAL PRIMARY KEY,
  name VARCHAR(255) UNIQUE NOT NULL,
  properties JSONB NOT NULL,
  created_at TIMESTAMPTZ DEFAULT NOW()
);
```

## Adding Catalogs

Insert rows into `trino_catalogs`. The `properties` column is JSONB with key-value pairs for the catalog's `.properties` file.

### Example: PostgreSQL Connector

```sql
INSERT INTO trino_catalogs (name, properties) VALUES (
  'mypostgres',
  '{
    "connector.name": "postgresql",
    "connection-url": "jdbc:postgresql://host:5432/mydb",
    "connection-user": "user",
    "connection-password": "secret"
  }'::jsonb
);
```

### Example: JMX (Built-in)

```sql
INSERT INTO trino_catalogs (name, properties) VALUES (
  'jmx',
  '{"connector.name": "jmx"}'::jsonb
);
```

### Example: Iceberg with Lakekeeper

```sql
INSERT INTO trino_catalogs (name, properties) VALUES (
  'iceberg',
  '{
    "connector.name": "iceberg",
    "iceberg.catalog.type": "rest",
    "iceberg.rest-catalog.uri": "http://lakekeeper:8181"
  }'::jsonb
);
```

## Deployment to Aiven App Runtime

1. **Create a PostgreSQL Service** in Aiven (if you don't have one).
2. **Create an App Runtime Application**
   - Source: This GitHub repository
   - Branch: `main`
   - Build context: `trino/` (or root if the Dockerfile is at repo root)
3. **Connect PostgreSQL** in "Connect services" so `DATABASE_URL` is set.
4. **Add catalogs** to the `trino_catalogs` table (via `psql` or any PostgreSQL client).
5. **Configure port** – Open port **8080** in App Runtime.
6. **Deploy** – Aiven builds and runs the container.

## Accessing Trino

- **Web UI:** `https://<your-app-hostname>:8080/`
- **CLI:** `trino --server https://<your-app-hostname>:8080`

## Project Structure

```
trino/
├── Dockerfile          # Multi-stage: UBI Python + Trino
├── entrypoint.sh       # Validates env, fetches catalogs, starts Trino
├── fetch_catalogs.py   # Reads trino_catalogs from PG, writes .properties files
├── init-schema.sql     # Schema reference (auto-applied by fetch_catalogs.py)
└── README.md           # This file
```

## How It Works

1. **Startup:** Entrypoint runs `fetch_catalogs.py`, which connects to PostgreSQL.
2. **Schema:** Creates `trino_catalogs` table if it doesn't exist.
3. **Fetch:** Selects all rows from `trino_catalogs`.
4. **Write:** For each row, creates `/etc/trino/catalog/{name}.properties`.
5. **Start:** Launches Trino. Trino loads catalogs from the written files.

After a restart, the same flow runs again, so all catalogs are restored from PG.

## Resource Requirements

Trino is memory-intensive. Recommended:

- **RAM:** 4–8 GB minimum
- **CPU:** 2 vCPUs

## Troubleshooting

### No catalogs after restart

- Ensure rows exist in `trino_catalogs`.
- Check application logs for `fetch_catalogs.py` errors.
- Verify `DATABASE_URL` or `TRINO_CATALOG_DB_URL` is set.

### Database connection errors

- Confirm PostgreSQL is reachable from App Runtime (VPC/network).
- Use `postgresql://` or `postgres://` in the connection string.

### Port configuration

- Trino defaults to 8080. If Aiven sets `PORT`, the entrypoint updates `config.properties` automatically.

## Security Considerations

- Credentials in `trino_catalogs.properties` (e.g. `connection-password`) are stored in PostgreSQL. Restrict access to the catalog database.
- Consider encrypting sensitive properties or using a secrets manager for production.

## Resources

- [Trino Documentation](https://trino.io/docs/current/)
- [Trino Connectors](https://trino.io/docs/current/connector.html)
- [Aiven App Runtime](https://docs.aiven.io/docs/products/app-runtime)
