-- Таблица команд с метаданными
CREATE TABLE commands_catalog (
    id SERIAL PRIMARY KEY,
    code VARCHAR(50) UNIQUE NOT NULL,
    name VARCHAR(100) NOT NULL,
    description TEXT,
    has_params BOOLEAN DEFAULT FALSE,
    param_schema JSONB DEFAULT '[]'::jsonb,
    is_active BOOLEAN DEFAULT TRUE,
    required_role VARCHAR(50) DEFAULT 'operator',
    version INT DEFAULT 1,              -- Версия записи
    updated_at TIMESTAMPTZ DEFAULT NOW() -- Время последнего изменения
);

-- Триггер: обновляет хэш при любом изменении в commands_catalog
CREATE OR REPLACE FUNCTION update_commands_hash() RETURNS TRIGGER AS $$
BEGIN
    -- Вычисляем хэш от всех активных команд
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
    EXECUTE procedure update_commands_hash();

