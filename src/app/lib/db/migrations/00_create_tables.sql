BEGIN;

-- user definition

CREATE TYPE user_role_datatype AS ENUM (
  'USER',
  'SUPERUSER');

CREATE TABLE user_login (
  id UUID NOT NULL,
  login TEXT NOT NULL UNIQUE,
  salt TEXT NOT NULL,
  hashed_password TEXT NOT NULL,
  role user_role_datatype NOT NULL DEFAULT 'USER',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (id)
);

-- list definition

CREATE TYPE list_type_datatype AS ENUM (
  'DENY',
  'SAFE');

CREATE TABLE list (
  id TEXT NOT NULL UNIQUE,
  user_id UUID NOT NULL,
  list_type list_type_datatype NOT NULL DEFAULT 'DENY',
  enabled BOOLEAN NOT NULL DEFAULT true,
  tags TEXT[] NOT NULL DEFAULT '{"DEFAULT"}',
  description TEXT NOT NULL DEFAULT '',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (id, user_id),
  FOREIGN KEY (user_id) REFERENCES user_login(id) ON DELETE CASCADE
);

-- cidr definition

CREATE TABLE cidr (
  id SERIAL NOT NULL UNIQUE,
  address CIDR NOT NULL,
  list_id TEXT NOT NULL,
  expires_at TIMESTAMPTZ NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (address, list_id),
  FOREIGN KEY (list_id) REFERENCES list(id) ON DELETE CASCADE
);

COMMIT;
