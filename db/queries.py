# db/queries.py
# -*- coding: utf-8 -*-
"""
Централизованное хранилище SQL-запросов
Версия для схемы: objects_new + opc_params + pvalues (без изменений)
"""

# ============================================================================
# Телеметрия (АДАПТИРОВАНО под существующую pvalues)
# ============================================================================

# db/queries.py

LOAD_TELEMETRY = """
    SELECT 
        onew.name AS obj_name,
        op.sim,
        onew.sname AS lpu,
        COALESCE(tp.t1 * 2, %s) AS period,
        op.alias,
        op.name AS param_name,
        COALESCE(op.unit, op.disp, pv.units, '') AS unit,  -- Приоритет: unit → disp → pv.units
        op.comment,
        COALESCE(op.type, 'string') AS param_type,
        COALESCE(op.description, op.comment, '') AS description,
        pv.value,
        pv.time,
        pc.nico,
        op.pgroup,        -- ← Группа для структуры OPC UA
        op.disp           -- ← Отображение для клиентов
    FROM opc_params op
    INNER JOIN objects_new onew ON onew.sim = op.sim
    LEFT JOIN pvalues pv ON pv.alias = op.alias
    LEFT JOIN pcoords pc ON pc.alias = op.alias
    LEFT JOIN term_params tp ON tp.id = onew.id
    WHERE op.alias IS NOT NULL AND op.alias <> ''
      AND op.sim IS NOT NULL AND op.sim <> ''
    ORDER BY op.sim, op.pgroup, op.alias  -- ← Сортировка по группе
"""
# ============================================================================
# Отдельные запросы для параметров
# ============================================================================

GET_PARAMETER_VALUE = """
    SELECT value, time::timestamptz 
    FROM pvalues 
    WHERE alias = %s 
    LIMIT 1
"""

GET_PARAMETER_NICO = """
    SELECT nico::int 
    FROM pcoords 
    WHERE alias = %s 
    LIMIT 1
"""

GET_PARAMETER_BY_ALIAS = """
    SELECT alias, sim, name, unit, type, comment, description, pgroup, disp
    FROM opc_params
    WHERE alias = %s
    LIMIT 1
"""

# ============================================================================
# Запросы для объектов
# ============================================================================

GET_OBJECT_BY_SIM = """
    SELECT id, name, sim, sname, tb, num
    FROM objects_new
    WHERE sim = %s
    LIMIT 1
"""

GET_OBJECT_PARAMS = """
    SELECT alias, name, unit, type, comment, description, pgroup, disp
    FROM opc_params
    WHERE sim = %s
    ORDER BY alias
"""

# ============================================================================
# Запись значений (UPDATE или INSERT)
# ============================================================================

UPSERT_PVALUE = """
    INSERT INTO pvalues (alias, name, value, time, units, valid, msg)
    VALUES (%s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT (alias) DO UPDATE SET
        value = EXCLUDED.value,
        time = EXCLUDED.time,
        units = EXCLUDED.units,
        valid = EXCLUDED.valid,
        msg = EXCLUDED.msg
"""

# ============================================================================
# История значений
# ============================================================================

GET_PARAMETER_HISTORY = """
    SELECT value, time::timestamptz 
    FROM pvalues_log 
    WHERE alias = %s
    ORDER BY time DESC 
    LIMIT %s
"""

CLEAR_OLD_HISTORY = """
    DELETE FROM pvalues_log 
    WHERE time < NOW() - INTERVAL '%s days'
"""

# db/queries.py

# ============================================================================
# Команды (ОБНОВЛЕНО с sim)
# ============================================================================

LOAD_COMMANDS_CATALOG = """
    SELECT id, code, name, description, has_params, param_schema, is_active
    FROM commands_catalog
    WHERE is_active = TRUE
    ORDER BY code
"""

QUEUE_COMMAND = """
    INSERT INTO commands_queue (command_id, sim, params, status, requested_by)
    VALUES (%s, %s, %s, 'pending', %s)
    RETURNING id
"""

FETCH_PENDING_COMMANDS = """
    SELECT 
        q.id, 
        q.command_id, 
        q.sim,                    -- ← НОВОЕ!
        c.code, 
        q.params,
        COALESCE(q.priority, 2) as priority,
        COALESCE(q.requested_by, 'system') as requested_by,
        q.created_at
    FROM commands_queue q
    JOIN commands_catalog c ON c.id = q.command_id
    WHERE q.status = %s
    ORDER BY COALESCE(q.priority, 2) ASC, q.created_at ASC
    LIMIT 10
"""

GET_COMMAND_BY_ID = """
    SELECT 
        q.id,
        q.command_id,
        q.sim,
        c.code,
        c.name,
        c.has_params,
        c.param_schema,
        q.params,
        q.status,
        q.result_message,
        q.created_at,
        q.executed_at
    FROM commands_queue q
    JOIN commands_catalog c ON c.id = q.command_id
    WHERE q.id = %s
"""

GET_COMMANDS_BY_SIM = """
    SELECT 
        q.id,
        c.code,
        c.name,
        q.params,
        q.status,
        q.created_at,
        q.executed_at
    FROM commands_queue q
    JOIN commands_catalog c ON c.id = q.command_id
    WHERE q.sim = %s
    ORDER BY q.created_at DESC
    LIMIT %s
"""

GET_CONFIG_HASH = """
    SELECT config_hash FROM commands_config_version WHERE id = 1
"""