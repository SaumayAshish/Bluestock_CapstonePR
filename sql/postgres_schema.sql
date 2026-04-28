CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE TABLE IF NOT EXISTS import_files (
  id BIGSERIAL PRIMARY KEY,
  file_name VARCHAR(255) NOT NULL,
  file_path VARCHAR(768) NOT NULL UNIQUE,
  state_code VARCHAR(8),
  state_name VARCHAR(255),
  file_extension VARCHAR(16) NOT NULL,
  imported_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS import_rows (
  id BIGSERIAL PRIMARY KEY,
  import_file_id BIGINT NOT NULL REFERENCES import_files (id) ON DELETE CASCADE,
  sheet_name VARCHAR(255) NOT NULL,
  source_row_number INTEGER NOT NULL,
  row_hash CHAR(64) NOT NULL,
  row_data JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE (import_file_id, sheet_name, source_row_number)
);

CREATE INDEX IF NOT EXISTS ix_import_rows_hash ON import_rows (row_hash);

CREATE TABLE IF NOT EXISTS countries (
  id SMALLSERIAL PRIMARY KEY,
  code CHAR(2) NOT NULL UNIQUE,
  name VARCHAR(128) NOT NULL UNIQUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS states (
  id SERIAL PRIMARY KEY,
  country_id SMALLINT NOT NULL REFERENCES countries (id),
  code VARCHAR(8) NOT NULL UNIQUE,
  name VARCHAR(255) NOT NULL,
  search_name VARCHAR(255) NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_states_country_name ON states (country_id, search_name);

CREATE TABLE IF NOT EXISTS districts (
  id SERIAL PRIMARY KEY,
  state_id INTEGER NOT NULL REFERENCES states (id),
  code VARCHAR(8) NOT NULL,
  name VARCHAR(255) NOT NULL,
  search_name VARCHAR(255) NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE (state_id, code)
);

CREATE INDEX IF NOT EXISTS ix_districts_state_name ON districts (state_id, search_name);

CREATE TABLE IF NOT EXISTS sub_districts (
  id SERIAL PRIMARY KEY,
  district_id INTEGER NOT NULL REFERENCES districts (id),
  code VARCHAR(16) NOT NULL,
  name VARCHAR(255) NOT NULL,
  search_name VARCHAR(255) NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE (district_id, code)
);

CREATE INDEX IF NOT EXISTS ix_sub_districts_district_name ON sub_districts (district_id, search_name);

CREATE TABLE IF NOT EXISTS villages (
  id BIGSERIAL PRIMARY KEY,
  sub_district_id INTEGER NOT NULL REFERENCES sub_districts (id),
  code VARCHAR(16) NOT NULL,
  name VARCHAR(255) NOT NULL,
  display_name VARCHAR(1024) NOT NULL,
  search_name VARCHAR(255) NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE (sub_district_id, code)
);

CREATE INDEX IF NOT EXISTS ix_villages_sub_district_name ON villages (sub_district_id, search_name);
CREATE INDEX IF NOT EXISTS ix_villages_search_name ON villages (search_name);
CREATE INDEX IF NOT EXISTS ix_villages_name_trgm ON villages USING GIN (search_name gin_trgm_ops);

CREATE TABLE IF NOT EXISTS api_clients (
  id BIGSERIAL PRIMARY KEY,
  name VARCHAR(255) NOT NULL,
  email VARCHAR(255) NOT NULL UNIQUE,
  business_name VARCHAR(255),
  gst_number VARCHAR(32),
  phone VARCHAR(32),
  password_hash VARCHAR(255),
  plan VARCHAR(32) NOT NULL DEFAULT 'free',
  status VARCHAR(32) NOT NULL DEFAULT 'pending_approval',
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_api_clients_status_plan ON api_clients (status, plan);

CREATE TABLE IF NOT EXISTS admin_users (
  id BIGSERIAL PRIMARY KEY,
  name VARCHAR(255) NOT NULL,
  email VARCHAR(255) NOT NULL UNIQUE,
  password_hash VARCHAR(255) NOT NULL,
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS api_keys (
  id BIGSERIAL PRIMARY KEY,
  client_id BIGINT NOT NULL REFERENCES api_clients (id),
  name VARCHAR(120) NOT NULL DEFAULT 'Default',
  key_prefix VARCHAR(16) NOT NULL,
  key_hash CHAR(64) NOT NULL UNIQUE,
  secret_hash CHAR(64) NOT NULL,
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  last_used_at TIMESTAMPTZ,
  expires_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS ix_api_keys_client ON api_keys (client_id);

CREATE TABLE IF NOT EXISTS api_usage_events (
  id BIGSERIAL PRIMARY KEY,
  client_id BIGINT NOT NULL REFERENCES api_clients (id),
  api_key_id BIGINT NOT NULL REFERENCES api_keys (id),
  endpoint VARCHAR(255) NOT NULL,
  status_code SMALLINT NOT NULL,
  latency_ms INTEGER NOT NULL,
  ip_address VARCHAR(64),
  created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_api_usage_client_time ON api_usage_events (client_id, created_at);
CREATE INDEX IF NOT EXISTS ix_api_usage_key_time ON api_usage_events (api_key_id, created_at);
CREATE INDEX IF NOT EXISTS ix_api_usage_endpoint_time ON api_usage_events (endpoint, created_at);

CREATE TABLE IF NOT EXISTS user_state_access (
  user_id BIGINT NOT NULL REFERENCES api_clients (id),
  state_id INTEGER NOT NULL REFERENCES states (id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (user_id, state_id)
);

