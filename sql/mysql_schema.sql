CREATE DATABASE IF NOT EXISTS bluestock
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

USE bluestock;

CREATE TABLE IF NOT EXISTS import_files (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  file_name VARCHAR(255) NOT NULL,
  file_path VARCHAR(768) NOT NULL,
  state_code VARCHAR(8) NULL,
  state_name VARCHAR(255) NULL,
  file_extension VARCHAR(16) NOT NULL,
  imported_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_import_files_path (file_path)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS import_rows (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  import_file_id BIGINT UNSIGNED NOT NULL,
  sheet_name VARCHAR(255) NOT NULL,
  source_row_number INT UNSIGNED NOT NULL,
  row_hash CHAR(64) NOT NULL,
  row_data JSON NOT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_import_rows_source (import_file_id, sheet_name, source_row_number),
  KEY ix_import_rows_hash (row_hash),
  CONSTRAINT fk_import_rows_file
    FOREIGN KEY (import_file_id) REFERENCES import_files (id)
    ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
