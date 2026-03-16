-- 2. Очередь команд (Исполнение)
CREATE TABLE commands_queue (
    id SERIAL PRIMARY KEY,
    command_id INT REFERENCES commands_catalog(id),
    params JSONB,                          -- Переданные параметры
    status VARCHAR(20) DEFAULT 'pending',  -- pending, processing, done, failed
    result_message TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    executed_at TIMESTAMPTZ,
    requested_by VARCHAR(50)               -- Кто отправил (из OPC UA сессии)
);
