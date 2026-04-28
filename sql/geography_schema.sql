CREATE TABLE IF NOT EXISTS countries (
  id SMALLINT UNSIGNED NOT NULL AUTO_INCREMENT,
  code CHAR(2) NOT NULL,
  name VARCHAR(128) NOT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_countries_code (code),
  UNIQUE KEY uq_countries_name (name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS states (
  id INT UNSIGNED NOT NULL AUTO_INCREMENT,
  country_id SMALLINT UNSIGNED NOT NULL,
  code VARCHAR(8) NOT NULL,
  name VARCHAR(255) NOT NULL,
  search_name VARCHAR(255) NOT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_states_code (code),
  KEY ix_states_country_name (country_id, search_name),
  CONSTRAINT fk_states_country FOREIGN KEY (country_id) REFERENCES countries (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS districts (
  id INT UNSIGNED NOT NULL AUTO_INCREMENT,
  state_id INT UNSIGNED NOT NULL,
  code VARCHAR(8) NOT NULL,
  name VARCHAR(255) NOT NULL,
  search_name VARCHAR(255) NOT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_districts_state_code (state_id, code),
  KEY ix_districts_state_name (state_id, search_name),
  CONSTRAINT fk_districts_state FOREIGN KEY (state_id) REFERENCES states (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS sub_districts (
  id INT UNSIGNED NOT NULL AUTO_INCREMENT,
  district_id INT UNSIGNED NOT NULL,
  code VARCHAR(16) NOT NULL,
  name VARCHAR(255) NOT NULL,
  search_name VARCHAR(255) NOT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_sub_districts_district_code (district_id, code),
  KEY ix_sub_districts_district_name (district_id, search_name),
  CONSTRAINT fk_sub_districts_district FOREIGN KEY (district_id) REFERENCES districts (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS villages (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  sub_district_id INT UNSIGNED NOT NULL,
  code VARCHAR(16) NOT NULL,
  name VARCHAR(255) NOT NULL,
  display_name VARCHAR(1024) NOT NULL,
  search_name VARCHAR(255) NOT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_villages_sub_district_code (sub_district_id, code),
  KEY ix_villages_sub_district_name (sub_district_id, search_name),
  KEY ix_villages_search_name (search_name),
  FULLTEXT KEY ft_villages_name (name, display_name),
  CONSTRAINT fk_villages_sub_district FOREIGN KEY (sub_district_id) REFERENCES sub_districts (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS api_clients (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  name VARCHAR(255) NOT NULL,
  email VARCHAR(255) NOT NULL,
  business_name VARCHAR(255) NULL,
  gst_number VARCHAR(32) NULL,
  phone VARCHAR(32) NULL,
  password_hash VARCHAR(255) NULL,
  plan VARCHAR(32) NOT NULL DEFAULT 'free',
  status VARCHAR(32) NOT NULL DEFAULT 'pending_approval',
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_api_clients_email (email),
  KEY ix_api_clients_status_plan (status, plan)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS admin_users (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  name VARCHAR(255) NOT NULL,
  email VARCHAR(255) NOT NULL,
  password_hash VARCHAR(255) NOT NULL,
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_admin_users_email (email)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS api_keys (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  client_id BIGINT UNSIGNED NOT NULL,
  name VARCHAR(120) NOT NULL DEFAULT 'Default',
  key_prefix VARCHAR(16) NOT NULL,
  key_hash CHAR(64) NOT NULL,
  secret_hash CHAR(64) NOT NULL,
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  last_used_at TIMESTAMP NULL,
  expires_at TIMESTAMP NULL,
  PRIMARY KEY (id),
  UNIQUE KEY uq_api_keys_key_hash (key_hash),
  KEY ix_api_keys_client (client_id),
  CONSTRAINT fk_api_keys_client FOREIGN KEY (client_id) REFERENCES api_clients (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS api_usage_events (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  client_id BIGINT UNSIGNED NOT NULL,
  api_key_id BIGINT UNSIGNED NOT NULL,
  endpoint VARCHAR(255) NOT NULL,
  status_code SMALLINT UNSIGNED NOT NULL,
  latency_ms INT UNSIGNED NOT NULL,
  ip_address VARCHAR(64) NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY ix_api_usage_client_time (client_id, created_at),
  KEY ix_api_usage_key_time (api_key_id, created_at),
  CONSTRAINT fk_api_usage_client FOREIGN KEY (client_id) REFERENCES api_clients (id),
  CONSTRAINT fk_api_usage_key FOREIGN KEY (api_key_id) REFERENCES api_keys (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS user_state_access (
  user_id BIGINT UNSIGNED NOT NULL,
  state_id INT UNSIGNED NOT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (user_id, state_id),
  CONSTRAINT fk_user_state_access_user FOREIGN KEY (user_id) REFERENCES api_clients (id),
  CONSTRAINT fk_user_state_access_state FOREIGN KEY (state_id) REFERENCES states (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
