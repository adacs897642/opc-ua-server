-- Таблица для хранения хэша конфигурации
CREATE TABLE IF NOT EXISTS commands_config_version (
    id INT PRIMARY KEY DEFAULT 1,
    config_hash VARCHAR(64),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    CHECK (id = 1)
);

-- Триггер для обновления хэша при изменении commands_catalog
CREATE OR REPLACE FUNCTION update_commands_hash() RETURNS TRIGGER AS $$
BEGIN
    UPDATE commands_config_version SET
        config_hash = MD5(
            STRING_AGG(code || ':' || version::text || ':' || is_active::text, ','
                       ORDER BY code)
        ),
        updated_at = NOW()
    FROM (SELECT code, version, is_active FROM commands_catalog ORDER BY code) AS cmds;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_commands_hash
    AFTER INSERT OR UPDATE OR DELETE OR TRUNCATE
    ON commands_catalog
    EXECUTE FUNCTION update_commands_hash();

-- Инициализация
INSERT INTO commands_config_version (id, config_hash)
VALUES (1, '')
ON CONFLICT (id) DO NOTHING;