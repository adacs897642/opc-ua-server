# db/schema.py
# -*- coding: utf-8 -*-
"""
Проверка и авто-создание схемы базы данных
(Адаптировано под реальную структуру БД)
"""

import logging
from typing import List, Dict, Optional, TYPE_CHECKING

# ✅ Импортируем только для проверки типов (не во время выполнения)
if TYPE_CHECKING:
    from db.connection import Database

logger = logging.getLogger(__name__)


class SchemaValidator:
    """Валидатор схемы базы данных"""

    # ✅ Таблицы которые должны существовать
    REQUIRED_TABLES = [
        'objects_new',
        'opc_params',
        'pvalues',
        'pvaluesm1',  # ← ← ← Строчные буквы (как у вас)
        'pvalues_log',  # ← ← ← Для логирования
        'pcoords',
        'commands_catalog',
        'commands_queue',
        'device_config_history',
        'desc_params',
        'device_command_queue',
        'opc_users',
        'opc_roles',
        'opc_user_roles',
        'opc_permissions',
        'opc_role_permissions',
        'opc_auth_log'
    ]

    # ✅ CREATE TABLE statements (точно как у вас)
    TABLE_DEFINITIONS = {
        'objects_new': """
            CREATE TABLE IF NOT EXISTS public.objects_new (
                id serial4 PRIMARY KEY,
                tb int4 NULL,
                num int4 NULL,
                name varchar NOT NULL,
                sim varchar NULL,
                sname varchar NOT NULL,
                created_at timestamptz DEFAULT now(),
                updated_at timestamptz,
                CONSTRAINT objects_new_name_sim_key UNIQUE (name, sim),
                CONSTRAINT objects_new_unique UNIQUE (sname),
                CONSTRAINT objects_new_unique_1 UNIQUE (sim)
            )
        """,

        'opc_params': """
            CREATE TABLE IF NOT EXISTS public.opc_params (
            alias varchar NOT NULL,
            sim varchar NOT NULL,
            description varchar DEFAULT ''::character varying NULL,
            name varchar DEFAULT ''::character varying NULL,
            unit varchar DEFAULT ''::character varying NULL,
            comment varchar DEFAULT ''::character varying NULL,
            type varchar DEFAULT 'string'::character varying NULL,
            pgroup varchar DEFAULT ''::character varying NULL,
	        disp varchar DEFAULT ''::character varying NULL,
            CONSTRAINT opc_params_pkey PRIMARY KEY (alias),
            CONSTRAINT opc_params_sim_fkey 
                FOREIGN KEY (sim) 
                REFERENCES public.objects_new(sim) 
                ON DELETE CASCADE ON UPDATE CASCADE
            )
        """,

        'pvalues': """
            CREATE TABLE IF NOT EXISTS public.pvalues (
                id serial4 NOT NULL,
                alias varchar NOT NULL,
                name varchar NULL,
                time timestamptz DEFAULT now() NULL,
                value varchar NULL,
                grad varchar NULL,
                units varchar NULL,
                valid bool NULL,
                msg varchar NULL,
                CONSTRAINT alias_not_empty CHECK (((alias)::text <> ''::text)),
                CONSTRAINT pvalues_pkey PRIMARY KEY (alias)
            )
        """,

        'pvaluesm1': """
            CREATE TABLE IF NOT EXISTS public.pvaluesm1 (
                alias varchar NOT NULL,
                time timestamptz DEFAULT now() NULL,
                value varchar NULL,
                valid bool NULL,
                CONSTRAINT pvaluesm1_pkey PRIMARY KEY (alias)
            )
        """,

        'pvalues_log': """
            CREATE TABLE IF NOT EXISTS public.pvalues_log (
                id serial4 NOT NULL,
                alias varchar NULL,
                time timestamptz DEFAULT now() NULL,
                value varchar NULL,
                grad varchar NULL,
                valid bool NULL,
                CONSTRAINT pvalues_log_pkey PRIMARY KEY (id)
            )
        """,

        'pcoords': """
            CREATE TABLE IF NOT EXISTS public.pcoords (
                alias varchar NOT NULL,
                px int2 NULL,
                py int2 NULL,
                hx int2 NULL,
                hy int2 NULL,
                nico int2 NULL,
                CONSTRAINT pcoords_pkey PRIMARY KEY (alias)
            )
        """,

        'commands_catalog': """
            CREATE TABLE IF NOT EXISTS public.commands_catalog (
                id serial PRIMARY KEY,
                code varchar(50) NOT NULL UNIQUE,
                name varchar(100) NOT NULL,
                description text NULL,
                has_params bool DEFAULT false,
                param_schema jsonb NULL,
                is_active bool DEFAULT true,
                required_role varchar(50) DEFAULT 'operator'::character varying NULL,
	            version int4 DEFAULT 1 NULL,
	            updated_at timestamptz DEFAULT now() NULL
            )
        """,

        'commands_queue': """
            CREATE TABLE IF NOT EXISTS public.commands_queue (
                id serial PRIMARY KEY,
                command_id int4 NOT NULL,
                sim varchar(50) NULL,
                params jsonb NULL,
                status varchar(20) DEFAULT 'pending',
                result_message text NULL,
                created_at timestamptz DEFAULT now(),
                executed_at timestamptz NULL,
                requested_by varchar(50) DEFAULT 'opc_user',
                priority int4 DEFAULT 2,
                started_at timestamptz NULL,
                completed_at timestamptz NULL,
                retry_count int4 DEFAULT 0,
                CONSTRAINT commands_queue_command_id_fkey 
                    FOREIGN KEY (command_id) REFERENCES commands_catalog(id)
                    ON DELETE CASCADE ON UPDATE CASCADE,
                CONSTRAINT commands_queue_sim_fkey 
                    FOREIGN KEY (sim) REFERENCES objects_new(sim) 
                    ON DELETE SET NULL ON UPDATE CASCADE
            )
        """,
        'device_config_history': """
            CREATE TABLE IF NOT EXISTS public.device_config_history (
                id serial PRIMARY KEY,
                sim varchar(50) NOT NULL,
                param_name varchar(100) NOT NULL,
                param_value text NOT NULL,
                timeout int4 DEFAULT 30,
                filepath text NULL,
                created_at timestamptz DEFAULT now(),
                updated_at timestamptz,
                status varchar(20) DEFAULT 'pending',
                result_message text NULL,
                requested_by varchar(50) DEFAULT 'opc_user',
                CONSTRAINT device_config_history_sim_param UNIQUE (sim, param_name),
                CONSTRAINT device_config_history_sim_fkey 
                    FOREIGN KEY (sim) REFERENCES objects_new(sim) 
                    ON DELETE CASCADE ON UPDATE CASCADE,
                CONSTRAINT device_config_history_status_check 
                    CHECK (status = ANY (ARRAY['pending', 'done', 'error']))
            )
        """,
        'desc_params': """
            CREATE TABLE IF NOT EXISTS public.desc_params (
                id_dev int4 NOT NULL,
                tb int4 NOT NULL,
                num int4 NOT NULL,
                alias varchar NOT NULL,
                name varchar NOT NULL,
                units varchar NULL,
                max int4 NULL,
                min int4 NULL,
                type varchar NULL,
                CONSTRAINT desc_params_alias_check CHECK (((alias)::text <> ''::text)),
                CONSTRAINT desc_params_name_check CHECK (((name)::text <> ''::text)),
                CONSTRAINT desc_params_pkey PRIMARY KEY (id_dev, tb, num),
                CONSTRAINT desc_params_tb_alias_name_key UNIQUE (tb, alias, name),
                CONSTRAINT desc_params_tb_num_key UNIQUE (tb, num)
            )
        """,
        'device_command_queue': """
                CREATE TABLE IF NOT EXISTS public.device_command_queue (
                    id serial PRIMARY KEY,
                    sim varchar(50) NOT NULL,
                    command_code varchar(50) NOT NULL,
                    command_type varchar(20) DEFAULT 'text',
                    filepath text NULL,
                    command_data text NULL,
                    status varchar(20) DEFAULT 'pending',
                    sent_at timestamptz NULL,
                    acknowledged_at timestamptz NULL,
                    result_message text NULL,
                    created_at timestamptz DEFAULT now(),
                    retry_count int4 DEFAULT 0,
                    priority int4 DEFAULT 2,
                    CONSTRAINT device_command_queue_sim_fkey 
                        FOREIGN KEY (sim) REFERENCES objects_new(sim)
                        ON DELETE CASCADE ON UPDATE CASCADE
                )
            """,
        'opc_users': """        
                    CREATE TABLE IF NOT EXISTS opc_users (
                        id SERIAL PRIMARY KEY,
                        username VARCHAR(64) UNIQUE NOT NULL,
                        password_hash VARCHAR(255) NOT NULL,  -- SHA256(salt+password+salt)
                        enabled BOOLEAN DEFAULT TRUE,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                        last_login TIMESTAMP WITH TIME ZONE,
                        failed_attempts INTEGER DEFAULT 0,
                        locked_until TIMESTAMP WITH TIME ZONE,
                        CONSTRAINT username_not_empty CHECK (char_length(username) >= 3)
                    );""",
        'opc_roles': """
                    CREATE TABLE IF NOT EXISTS opc_roles (
                        id SERIAL PRIMARY KEY,
                        role_name VARCHAR(32) UNIQUE NOT NULL,
                        description TEXT,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                    );""",
        'opc_user_roles': """
                    CREATE TABLE IF NOT EXISTS opc_user_roles (
                        user_id INTEGER REFERENCES opc_users(id) ON DELETE CASCADE,
                        role_id INTEGER REFERENCES opc_roles(id) ON DELETE CASCADE,
                        granted_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                        granted_by VARCHAR(64),  -- кто выдал роль
                        PRIMARY KEY (user_id, role_id)
                    );""",
        'opc_permissions': """
                    CREATE TABLE IF NOT EXISTS opc_permissions (
                        id SERIAL PRIMARY KEY,
                        permission_name VARCHAR(64) UNIQUE NOT NULL,  -- 'read', 'write', 'execute', 'configure'
                        description TEXT
                    );""",
        'opc_role_permissions':
            """CREATE TABLE IF NOT EXISTS opc_role_permissions (
                        role_id INTEGER REFERENCES opc_roles(id) ON DELETE CASCADE,
                        permission_id INTEGER REFERENCES opc_permissions(id) ON DELETE CASCADE,
                        PRIMARY KEY (role_id, permission_id)
                    );""",
        'opc_auth_log':
            """CREATE TABLE IF NOT EXISTS opc_auth_log (
                    id SERIAL PRIMARY KEY,
                    username VARCHAR(64) NOT NULL,
                    success BOOLEAN NOT NULL,
                    client_address INET,
                    user_agent TEXT,  -- OPC UA клиент (UaExpert, custom, etc.)
                    error_message TEXT,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                ); """
    }

    # ✅ Индексы
    INDEX_DEFINITIONS = {
        'i1_pvalues':
            """CREATE INDEX IF NOT EXISTS i1_pvalues ON public.pvalues USING btree (alias)""",
        'i2_pvalues':
            """CREATE INDEX IF NOT EXISTS i2_pvalues ON public.pvalues USING btree (id)""",
        'i3_pvalues':
            """CREATE INDEX IF NOT EXISTS i3_pvalues ON public.pvalues USING btree (id, alias)""",
        'idx_commands_queue_status':
            """CREATE INDEX IF NOT EXISTS idx_commands_queue_status ON commands_queue(status)""",
        'idx_commands_queue_sim':
            """CREATE INDEX IF NOT EXISTS idx_commands_queue_sim ON commands_queue(sim)""",
        'idx_commands_queue_created':
            """CREATE INDEX IF NOT EXISTS idx_commands_queue_created ON commands_queue(created_at DESC)""",
        'idx_device_config_sim':
            """CREATE INDEX IF NOT EXISTS idx_device_config_sim ON device_config_history(sim)""",
        'idx_device_config_param':
            """CREATE INDEX IF NOT EXISTS idx_device_config_param ON device_config_history(param_name)""",
        'idx_device_cmd_queue_sim':
            """CREATE INDEX IF NOT EXISTS idx_device_cmd_queue_sim ON device_command_queue(sim)""",
        'idx_device_cmd_queue_status':
            """CREATE INDEX IF NOT EXISTS idx_device_cmd_queue_status ON device_command_queue(status)""",
        'idx_device_cmd_queue_created':
            """CREATE INDEX IF NOT EXISTS idx_device_cmd_queue_created ON device_command_queue(created_at DESC)""",
        'idx_opc_roles_name':
            """CREATE INDEX IF NOT EXISTS idx_opc_roles_name ON opc_roles(role_name);""",
        'idx_opc_permissions_name':
            """CREATE INDEX IF NOT EXISTS idx_opc_permissions_name ON opc_permissions(permission_name);""",
        'idx_opc_users_username':
            """CREATE INDEX IF NOT EXISTS idx_opc_users_username ON opc_users(username);""",
        'idx_opc_users_enabled':
            """CREATE INDEX IF NOT EXISTS idx_opc_users_enabled ON opc_users(enabled) WHERE enabled = FALSE;""",
        'idx_opc_auth_log_username':
            """CREATE INDEX IF NOT EXISTS idx_opc_auth_log_username ON opc_auth_log(username);""",
        'idx_opc_auth_log_time':
            """CREATE INDEX IF NOT EXISTS idx_opc_auth_log_time ON opc_auth_log(created_at DESC);"""
    }

    # ✅ Триггеры и функции (проверка существования)
    TRIGGER_DEFINITIONS = {
        'new_objects_new': """
            CREATE OR REPLACE FUNCTION public.new_objects_new()
            RETURNS trigger AS $$
            BEGIN
                PERFORM pg_notify('objects_new', NEW.id::text);
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql
        """,

        'newvalue': """
        -- DROP FUNCTION public.newvalue();
            CREATE OR REPLACE FUNCTION public.newvalue()
             RETURNS trigger
             LANGUAGE plpgsql
            AS $function$
            DECLARE
               time_old  timestamp;
               value_old text;
               valid_old boolean;
            BEGIN
            
            time_old:=  time FROM pvalues WHERE alias=NEW.alias;
            value_old:= value FROM pvalues WHERE alias=NEW.alias;
            valid_old:= valid FROM pvalues WHERE alias=NEW.alias;
            
            BEGIN
            INSERT INTO pvaluesM1(alias, time, value, valid) VALUES (NEW.alias, NEW.time, NEW.value, NEW.valid);
            EXCEPTION
            WHEN OTHERS THEN
            UPDATE pvaluesM1 SET time=time_old, value=value_old,valid=valid_old WHERE alias=NEW.alias;
            END;
            
            DELETE FROM pvalues WHERE alias=NEW.alias;
            RETURN NEW;
            END;
            $function$
            ;
        """,
        'notify_opc_user_change': """-- ✅ Функция для отправки уведомления
            CREATE OR REPLACE FUNCTION notify_opc_user_change()
            RETURNS TRIGGER AS $$
            DECLARE
                payload JSON;
                username TEXT;
            BEGIN
                -- ✅ Определить имя пользователя
                IF TG_OP = 'DELETE' THEN
                    username = OLD.username;
                ELSE
                    username = NEW.username;
                END IF;
                
                -- ✅ Сформировать payload
                payload = json_build_object(
                    'action', LOWER(TG_OP),
                    'username', username,
                    'timestamp', NOW()
                );
                
                -- ✅ Отправить уведомление
                PERFORM pg_notify('opc_user_change', payload::text);
                
                RETURN NULL;
            END;
            $$ LANGUAGE plpgsql;""",
        # 'newvalue': """
        # CREATE OR REPLACE FUNCTION public.newvalue()
        # RETURNS trigger AS $$
        # BEGIN
        #     -- ✅ UPSERT вместо INSERT + EXCEPTION + UPDATE
        #     INSERT INTO pvaluesm1(alias, time, value, valid)
        #     VALUES (NEW.alias, NEW.time, NEW.value, NEW.valid)
        #     ON CONFLICT (alias) DO UPDATE
        #         SET time = EXCLUDED.time,
        #             value = EXCLUDED.value,
        #             valid = EXCLUDED.valid,
        #             updated_at = now();
        #
        #     -- ✅ Удаляем из pvalues (перемещение в m1)
        #     DELETE FROM pvalues WHERE alias = NEW.alias;
        #
        #     RETURN NULL;  -- Для BEFORE INSERT триггера
        # END;
        # $$ LANGUAGE plpgsql
        # """,
        'calcspd': """
            -- DROP FUNCTION public.calcspd();
            CREATE OR REPLACE FUNCTION public.calcspd()
             RETURNS trigger
             LANGUAGE plpgsql
            AS $function$
            DECLARE
               notifier  text;
               spd real;
               tm_cur timestamp;
               tm_M1 timestamp;
               val_cur real;
               val_M1 real;
            
            BEGIN
            
               tm_cur:= time FROM pvalues WHERE alias=NEW.alias;
               tm_M1:= time FROM pvaluesM1 WHERE alias=NEW.alias;
            BEGIN
               val_cur:= value::real FROM pvalues WHERE alias=NEW.alias;
               EXCEPTION
               WHEN OTHERS THEN
               val_cur:= 0;
            END;
            BEGIN
               val_M1:= value::real FROM pvaluesM1 WHERE alias=NEW.alias;
               EXCEPTION
               WHEN OTHERS THEN
               val_M1:= 0;
            END;
            
            BEGIN
               spd:=(val_cur-val_M1);
               EXCEPTION
               WHEN OTHERS THEN
               spd:=0;
            END;
               UPDATE pvalues SET grad=spd WHERE alias=NEW.alias;
            
               INSERT INTO pvalues_log(alias,time,value,grad,valid)
               VALUES (NEW.alias, NEW.time, NEW.value, spd, NEW.valid);
               notifier := 'NOTIFY "' || NEW.alias || '"';
               EXECUTE notifier;
               NOTIFY pvalues;
            
            RETURN NEW;
            END;
            $function$
            ;

        """
        # 'calcspd': """
        #     CREATE OR REPLACE FUNCTION public.calcspd()
        #     RETURNS trigger AS $$
        #     DECLARE
        #         val_m1 real;
        #         spd real;
        #     BEGIN
        #         -- ✅ Одно получение предыдущего значения
        #         SELECT value::real INTO val_m1
        #         FROM pvaluesm1
        #         WHERE alias = NEW.alias;
        #
        #         -- ✅ Вычисление скорости (градиента)
        #         spd := COALESCE(NEW.value::real, 0) - COALESCE(val_m1, 0);
        #
        #         -- ✅ Обновляем градиент
        #         UPDATE pvalues
        #         SET grad = spd::varchar
        #         WHERE alias = NEW.alias;
        #
        #         -- ✅ Логирование
        #         INSERT INTO pvalues_log(alias, time, value, grad, valid)
        #         VALUES (NEW.alias, NEW.time, NEW.value, spd::varchar, NEW.valid);
        #
        #         -- ✅ Уведомление (без EXECUTE)
        #         PERFORM pg_notify(NEW.alias, COALESCE(NEW.value, ''));
        #
        #         RETURN NULL;  -- Для AFTER INSERT триггера
        #     END;
        #     $$ LANGUAGE plpgsql
        # """,
    }

    def __init__(self, db_connection):
        # ✅ Принимаем connection напрямую, а не Database объект
        self.conn = db_connection
        self.logger = logging.getLogger('db.schema')

    def _query(self, sql: str, params: tuple = None) -> list:
        """Выполняет SELECT запрос"""
        try:
            with self.conn.cursor() as cur:
                cur.execute(sql, params or ())
                return cur.fetchall()
        except Exception as e:
            self.logger.error(f"❌ Ошибка запроса: {e}")
            return []

    def _execute(self, sql: str, params: tuple = None) -> bool:
        """Выполняет INSERT/UPDATE/CREATE запрос"""
        try:
            with self.conn.cursor() as cur:
                cur.execute(sql, params or ())
                self.conn.commit()
                return True
        except Exception as e:
            self.logger.error(f"❌ Ошибка выполнения: {e}")
            self.conn.rollback()
            return False

    def check_tables(self) -> Dict[str, bool]:
        """Проверяет существование необходимых таблиц"""
        result = {}

        for table in self.REQUIRED_TABLES:
            rows = self._query("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_schema = 'public' 
                    AND table_name = %s
                )
            """, (table,))

            exists = rows[0][0] if rows else False
            result[table] = exists

            if exists:
                self.logger.info(f"✅ Таблица {table} существует")
            else:
                self.logger.warning(f"⚠️ Таблица {table} НЕ существует")

        return result

    def create_missing_tables(self) -> List[str]:
        """Создаёт отсутствующие таблицы"""
        created = []

        for table, create_sql in self.TABLE_DEFINITIONS.items():
            rows = self._query("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_schema = 'public' 
                    AND table_name = %s
                )
            """, (table,))

            if not rows or not rows[0][0]:
                if self._execute(create_sql):
                    self.logger.info(f"✅ Таблица {table} создана")
                    created.append(table)
            else:
                self.logger.debug(f"   Таблица {table} уже существует")

        return created

    def create_indexes(self) -> List[str]:
        """Создаёт отсутствующие индексы"""
        created = []

        for index_name, create_sql in self.INDEX_DEFINITIONS.items():
            rows = self._query("""
                SELECT EXISTS (
                    SELECT FROM pg_indexes 
                    WHERE schemaname = 'public' 
                    AND indexname = %s
                )
            """, (index_name,))

            if not rows or not rows[0][0]:
                if self._execute(create_sql):
                    self.logger.info(f"✅ Индекс {index_name} создан")
                    created.append(index_name)
            else:
                self.logger.debug(f"   Индекс {index_name} уже существует")

        return created

    def check_triggers(self) -> Dict[str, bool]:
        """Проверяет существование триггеров и функций"""
        result = {}

        for func_name in self.TRIGGER_DEFINITIONS.keys():
            rows = self._query("""
                SELECT EXISTS (
                    SELECT FROM pg_proc 
                    WHERE proname = %s
                )
            """, (func_name,))

            exists = rows[0][0] if rows else False
            result[func_name] = exists

            if exists:
                self.logger.info(f"✅ Функция {func_name} существует")
            else:
                self.logger.warning(f"⚠️ Функция {func_name} НЕ существует")

        return result

    def create_triggers(self) -> List[str]:
        """Создаёт отсутствующие функции"""
        created = []

        for func_name, create_sql in self.TRIGGER_DEFINITIONS.items():
            if self._execute(create_sql):
                self.logger.info(f"✅ Функция {func_name} создана/обновлена")
                created.append(func_name)

        return created

    def validate_and_fix(self) -> dict:
        """Полная проверка и исправление схемы"""
        self.logger.info("🔍 Проверка схемы базы данных...")

        tables_status = self.check_tables()
        missing_tables = [t for t, exists in tables_status.items() if not exists]

        created_tables = []
        if missing_tables:
            self.logger.warning(f"⚠️ Отсутствуют таблицы: {missing_tables}")
            self.logger.info("🔧 Создание отсутствующих таблиц...")
            created_tables = self.create_missing_tables()

        self.logger.info("🔧 Проверка индексов...")
        created_indexes = self.create_indexes()

        self.logger.info("🔧 Проверка триггеров и функций...")
        triggers_status = self.check_triggers()
        created_triggers = self.create_triggers()

        report = {
            'total_tables': len(self.REQUIRED_TABLES),
            'existing_tables': len([t for t, e in tables_status.items() if e]),
            'missing_tables': missing_tables,
            'created_tables': created_tables,
            'created_indexes': created_indexes,
            'created_triggers': created_triggers,
            'is_valid': len(missing_tables) == 0 or len(created_tables) == len(missing_tables)
        }

        if report['is_valid']:
            self.logger.info("✅ Схема базы данных валидна")
        else:
            self.logger.error("❌ Ошибки при создании схемы базы данных")

        return report
