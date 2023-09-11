BEGIN;

-- Function to update the field updated_at
CREATE FUNCTION refresh_updated_at()
RETURNS TRIGGER
LANGUAGE plpgsql AS
$func$
BEGIN
  NEW.updated_at := now();
  RETURN NEW;
END
$func$;

-- Table triggers
CREATE TRIGGER trig_cidr_updated before
UPDATE
  ON
  cidr FOR EACH ROW EXECUTE FUNCTION refresh_updated_at();

CREATE TRIGGER trig_list_updated before
UPDATE
  ON
  list FOR EACH ROW EXECUTE FUNCTION refresh_updated_at();

CREATE TRIGGER trig_user_login_updated before
UPDATE
  ON
  user_login FOR EACH ROW EXECUTE FUNCTION refresh_updated_at();

COMMIT;
