BEGIN;

-- job_queue definition

CREATE TABLE job_queue (
  id serial,
  job_id UUID NOT NULL,
  payload JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (id)
);

COMMIT;
