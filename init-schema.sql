-- Trino catalog store: persists connector config across restarts
CREATE TABLE IF NOT EXISTS trino_catalogs (
  id SERIAL PRIMARY KEY,
  name VARCHAR(255) UNIQUE NOT NULL,
  properties JSONB NOT NULL,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Kafka client config (SASL_SSL etc.) - written to /etc/trino/kafka-client.properties
CREATE TABLE IF NOT EXISTS trino_kafka_config (
  id SERIAL PRIMARY KEY,
  config_text TEXT NOT NULL,
  created_at TIMESTAMPTZ DEFAULT NOW()
);
