CREATE TABLE commands_config_history (
    id SERIAL PRIMARY KEY,
    action VARCHAR(20) NOT NULL,  -- INSERT, UPDATE, DELETE
    command_code VARCHAR(50),
    old_hash VARCHAR(64),
    new_hash VARCHAR(64),
    changed_by VARCHAR(50) DEFAULT current_user,
    changed_at TIMESTAMPTZ DEFAULT NOW()
);

-- Триггер для логирования
CREATE OR REPLACE FUNCTION log_commands_change() RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        INSERT INTO commands_config_history (action, command_code, new_hash)
        VALUES ('INSERT', NEW.code,
                (SELECT config_hash FROM commands_config_version WHERE id = 1));
    ELSIF TG_OP = 'UPDATE' THEN
        INSERT INTO commands_config_history (action, command_code, old_hash, new_hash)
        VALUES ('UPDATE', NEW.code,
                (SELECT config_hash FROM commands_config_version WHERE id = 1),
                (SELECT config_hash FROM commands_config_version WHERE id = 1));
    ELSIF TG_OP = 'DELETE' THEN
        INSERT INTO commands_config_history (action, command_code, old_hash)
        VALUES ('DELETE', OLD.code,
                (SELECT config_hash FROM commands_config_version WHERE id = 1));
    END IF;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_commands_audit
    AFTER INSERT OR UPDATE OR DELETE
    ON commands_catalog
    EXECUTE FUNCTION log_commands_change();