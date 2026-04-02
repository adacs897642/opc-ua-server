# opc/user_manager.py
# -*- coding: utf-8 -*-
"""
Менеджер пользователей OPC UA с загрузкой из БД
"""

import hashlib
import logging
import json
import os
import struct
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, List, Set

from opcua import ua

# ✅ Для расшифровки пароля
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.backends import default_backend

logger = logging.getLogger('opc.user_manager')

# ✅ Константы
MAX_FAILED_ATTEMPTS = 5
LOCKOUT_DURATION_SECONDS = 300  # 5 минут


class UserManager:
    """Менеджер пользователей OPC UA с поддержкой БД"""

    def __init__(self, config: dict = None, db_connection=None):
        """
        Args:
            config: Конфигурация приложения
            db_connection: psycopg2 connection для загрузки пользователей
        """
        self.config = config or {}
        self.db = db_connection  # ✅ Сохраняем соединение с БД
        # ✅ ✅ ✅ Подписаться на канал opc_user_change


        # ✅ Кэш пользователей (загружается из БД или fallback на JSON)
        self.users: Dict[str, str] = {}  # username → password_hash
        self.roles: Dict[str, Set[str]] = {}  # username → set of permissions
        self.key_path: Optional[str] = None
        # ✅ Rate limiting
        self._login_attempts: Dict[str, tuple] = {}  # username → (count, timestamp)

        # ✅ Инициализация
        self._init_key_path()
        self._load_users()
        self._init_solt_phrase()

        logger.info(f"✅ UserManager инициализирован: {len(self.users)} пользователей")

    def _init_solt_phrase(self):
        """Инициализировать solt для расшифровки"""
        self.solt = self.config.get('server', {}).get('security', {}).get('solt')
        if self.solt:
            logger.info(f"✅ Ключ для расшифровки: {self.solt}")
        else:
            logger.warning("⚠️ Solt phrase не указан — расшифровка пароля не будет работать!")

    def _init_key_path(self):
        """Инициализировать путь к ключу для расшифровки"""
        self.key_path = self.config.get('server', {}).get('security', {}).get('key_path')
        if self.key_path:
            logger.info(f"✅ Ключ для расшифровки: {self.key_path}")
        else:
            logger.warning("⚠️ key_path не указан — расшифровка пароля не будет работать!")

    def _hash_password(self, password: str) -> str:
        """Хеширование пароля: SHA256(salt + password + salt)"""
        return hashlib.sha256(f"{self.solt}{password}{self.solt}".encode()).hexdigest()

    def _load_users(self):
        """Загрузить пользователей из БД или fallback на JSON"""
        try:
            if self.db and self._load_users_from_db():
                logger.info(f"✅ Загружено {len(self.users)} пользователей из БД")
                return
        except Exception as e:
            logger.error(f"❌ Ошибка загрузки из БД: {e}")
            logger.warning("⚠️ Переключаемся на fallback из users.json")

        # ✅ Fallback: загрузить из JSON файла
        self._load_users_from_json()

    def _load_users_from_db(self) -> bool:
        """
        Загрузить пользователей из БД

        Returns:
            bool: True если загрузка успешна
        """
        if not self.db:
            return False

        cursor = self.db.cursor()

        try:
            # ✅ Загрузить пользователей
            cursor.execute("""
                SELECT username, password_hash, enabled 
                FROM opc_users 
                WHERE enabled = TRUE
            """)

            users = {}
            for row in cursor.fetchall():
                username, password_hash, enabled = row
                if enabled:
                    users[username] = password_hash

            if not users:
                logger.warning("⚠️ Нет активных пользователей в opc_users")
                return False

            # ✅ Загрузить роли и права для каждого пользователя
            cursor.execute("""
                SELECT 
                    u.username,
                    p.permission_name
                FROM opc_users u
                JOIN opc_user_roles ur ON u.id = ur.user_id
                JOIN opc_roles r ON ur.role_id = r.id
                JOIN opc_role_permissions rp ON r.id = rp.role_id
                JOIN opc_permissions p ON rp.permission_id = p.id
                WHERE u.enabled = TRUE
            """)

            roles: Dict[str, Set[str]] = {username: set() for username in users}
            for username, permission in cursor.fetchall():
                if username in roles:
                    roles[username].add(permission)

            # ✅ Сохранить в кэш
            self.users = users
            self.roles = roles

            logger.debug(f"📋 Загружены права: {dict((k, list(v)) for k, v in roles.items())}")
            return True

        finally:
            cursor.close()

    def _load_users_from_json(self):
        """Fallback: загрузить пользователей из JSON файла"""
        users_file = self.config.get('users_file', 'users.json')

        if os.path.exists(users_file):
            try:
                with open(users_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                self.users = data.get('users', {})

                # ✅ Загрузить роли если есть
                if 'roles' in data:
                    for username, role_list in data['roles'].items():
                        self.roles[username] = set(role_list)

                logger.info(f"✅ Загружено {len(self.users)} пользователей из {users_file}")
                return

            except Exception as e:
                logger.error(f"❌ Ошибка загрузки {users_file}: {e}")

        # ✅ Дефолтные пользователи если ничего не загрузилось
        self.users = {
            'admin': self._hash_password('Admin123!'),
            'operator': self._hash_password('Operator123!'),
            'viewer': self._hash_password('Viewer123!'),
        }
        self.roles = {
            'admin': {'read', 'write', 'execute', 'configure'},
            'operator': {'read', 'write', 'execute'},
            'viewer': {'read'},
        }
        logger.warning("⚠️ Используются дефолтные пользователи!")

    def _check_rate_limit(self, username: str) -> bool:
        """
        Проверить лимит попыток входа

        Returns:
            bool: True если можно пытаться войти
        """
        now = time.time()
        attempts = self._login_attempts.get(username, (0, 0))

        # ✅ Сбросить если прошло время блокировки
        if attempts[0] >= MAX_FAILED_ATTEMPTS:
            if now - attempts[1] >= LOCKOUT_DURATION_SECONDS:
                self._login_attempts[username] = (0, 0)
                return True
            else:
                remaining = LOCKOUT_DURATION_SECONDS - (now - attempts[1])
                logger.warning(f"🚫 {username} заблокирован на {remaining:.0f} сек")
                return False

        return True

    def _record_login_attempt(self, username: str, success: bool):
        """Записать попытку входа для rate limiting и аудита"""
        now = time.time()

        if success:
            # ✅ Сбросить счётчик при успешном входе
            self._login_attempts[username] = (0, 0)
        else:
            # ✅ Увеличить счётчик неудачных попыток
            attempts = self._login_attempts.get(username, (0, 0))
            self._login_attempts[username] = (attempts[0] + 1, now)

        # ✅ Записать в аудит (асинхронно если возможно)
        self._log_auth_attempt(username, success)

    def _log_auth_attempt(self, username: str, success: bool, error: str = None):
        """Записать попытку аутентификации в БД"""
        if not self.db:
            return

        try:
            cursor = self.db.cursor()
            cursor.execute("""
                INSERT INTO opc_auth_log (username, success, error_message)
                VALUES (%s, %s, %s)
            """, (username, success, error))
            self.db.commit()
            cursor.close()
        except Exception as e:
            logger.error(f"❌ Ошибка записи аудита: {e}")

    def authenticate(self, username: str, password: str) -> bool:
        """
        Проверка логина/пароля с авто-перезагрузкой если пользователь не найден
        """
        # ✅ 1. Быстрая проверка в кэше
        if username in self.users:
            password_hash = self._hash_password(password)
            if self.users[username] == password_hash:
                logger.info(f"✅ Аутентификация успешна: {username}")
                return True
            else:
                logger.warning(f"⚠️ Неверный пароль: {username}")
                return False

        # ✅ 2. Пользователя нет в кэше — возможно он добавлен в БД
        logger.debug(f"🔍 {username} не в кэше, пробуем reload...")

        if self.reload_if_needed(username):
            # ✅ После reload проверить ещё раз
            if username in self.users:
                password_hash = self._hash_password(password)
                if self.users[username] == password_hash:
                    logger.info(f"✅ Аутентификация успешна (после reload): {username}")
                    return True

        # ✅ 3. Всё ещё не найден
        logger.warning(f"⚠️ Пользователь не найден: {username}")
        return False

    def get_permissions(self, username: str) -> Set[str]:
        """Получить права пользователя"""
        return self.roles.get(username, set())

    def has_permission(self, username: str, permission: str) -> bool:
        """Проверить наличие права у пользователя"""
        return permission in self.get_permissions(username)

    def _extract_password(self, decrypted_bytes: bytes) -> str:
        """Извлечь пароль из расшифрованных байтов"""
        # ✅ Попытка 1: Прямое декодирование UTF-8
        try:
            return decrypted_bytes.decode('utf-8').strip('\x00')
        except UnicodeDecodeError:
            pass

        # ✅ Попытка 2: Пропустить 4-байтовый префикс длины
        if len(decrypted_bytes) >= 4:
            try:
                length = struct.unpack('<I', decrypted_bytes[:4])[0]
                if 4 + length <= len(decrypted_bytes) and 0 < length <= 128:
                    password_bytes = decrypted_bytes[4:4 + length]
                    try:
                        return password_bytes.decode('utf-8').strip('\x00')
                    except UnicodeDecodeError:
                        pass
            except:
                pass

        # ✅ Попытка 3: Найти печатаемую ASCII подстроку
        ascii_printable = re.findall(b'[\\x20-\\x7E]+', decrypted_bytes)
        if ascii_printable:
            best = max(ascii_printable, key=len)
            if len(best) >= 3:
                try:
                    return best.decode('ascii')
                except:
                    pass

        # ✅ Попытка 4: Обрезать нули
        stripped = decrypted_bytes.strip(b'\x00')
        try:
            return stripped.decode('utf-8')
        except:
            pass

        # ✅ Fallback: Latin-1
        logger.warning("⚠️ Возвращаем как latin-1")
        return decrypted_bytes.decode('latin-1').strip('\x00')

    def _decrypt_password_rsa(self, encrypted_password: bytes) -> str:
        """Расшифровать пароль через cryptography"""
        if not self.key_path:
            raise ValueError("key_path не настроен!")
        if not os.path.exists(self.key_path):
            raise FileNotFoundError(f"Ключ не найден: {self.key_path}")

        logger.debug(f"🔑 Загрузка ключа: {self.key_path}")

        with open(self.key_path, 'rb') as f:
            private_key = serialization.load_pem_private_key(
                f.read(), password=None, backend=default_backend()
            )

        # ✅ Попробовать алгоритмы в порядке предпочтения
        algorithms = [
            ("OAEP+SHA256", padding.OAEP(
                mgf=padding.MGF1(hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None
            )),
            ("OAEP+SHA1", padding.OAEP(
                mgf=padding.MGF1(hashes.SHA1()),
                algorithm=hashes.SHA1(),
                label=None
            )),
        ]

        for name, pad in algorithms:
            try:
                decrypted = private_key.decrypt(encrypted_password, pad)
                logger.debug(f"🔓 {name}: {len(decrypted)} байт")

                password = self._extract_password(decrypted)
                logger.debug(f"✅ {name}: пароль извлечён: {len(password)} символов")

                # ✅ Показать хеш для отладки (не сам пароль!)
                pwd_hash = hashlib.sha256(password.encode()).hexdigest()[:16]
                logger.debug(f"🔐 Хеш: {pwd_hash}...")

                return password
            except Exception as e:
                logger.debug(f"❌ {name}: {e}")

        raise ValueError("Все алгоритмы расшифровки не сработали")

    def check_user_token(self, server, id_token):
        """
        Проверка токена пользователя — вызывается библиотекой python-opcua

        Returns:
            bool: True если доступ разрешён
        """
        try:
            # ✅ Anonymous токен
            if isinstance(id_token, ua.AnonymousIdentityToken):
                anonymous_allowed = self.config.get('server', {}).get('security', {}).get('anonymous_allowed', False)
                if anonymous_allowed:
                    logger.info("✅ Anonymous доступ разрешён")
                    return True
                else:
                    logger.warning("⚠️ Anonymous доступ запрещён")
                    return False

            # ✅ UserName токен
            if isinstance(id_token, ua.UserNameIdentityToken):
                username = id_token.UserName
                password = ''

                logger.info(f"🔐 Попытка входа: {username}")

                # ✅ Проверить rate limit
                if not self._check_rate_limit(username):
                    self._log_auth_attempt(username, False, "rate_limited")
                    return False

                # ✅ Получить и расшифровать пароль
                if id_token.Password:
                    try:
                        password = id_token.Password.decode('utf-8')
                        logger.debug("🔓 Пароль в открытом виде")
                    except UnicodeDecodeError:
                        try:
                            password = self._decrypt_password_rsa(id_token.Password)
                            logger.debug(f"🔓 Пароль расшифрован: {len(password)} символов")
                        except Exception as e:
                            logger.error(f"❌ Расшифровка: {e}")
                            self._record_login_attempt(username, False)
                            return False

                # ✅ Проверить логин/пароль
                if self.authenticate(username, password):
                    logger.info(f"✅ Вход успешен: {username}")
                    self._record_login_attempt(username, True)
                    return True
                else:
                    logger.error(f"❌ Вход неудачен: {username}")
                    self._record_login_attempt(username, False)
                    return False

            # ✅ Неизвестный токен
            logger.warning(f"⚠️ Неизвестный токен: {type(id_token)}")
            return False

        except Exception as e:
            logger.error(f"❌ Ошибка check_user_token: {e}", exc_info=True)
            return False

    def reload_users(self):
        """
        Перезагрузить пользователей из БД (hot-reload)

        Вызывается при получении NOTIFY opc_user_change
        """
        logger.info("🔄 Перезагрузка пользователей из БД...")

        try:
            if not self.db:
                logger.warning("⚠️ Нет соединения с БД, пропускаем reload")
                return False

            # ✅ Сохранить старые данные для сравнения
            old_users = self.users.copy()
            old_roles = {k: v.copy() for k, v in self.roles.items()}

            # ✅ Загрузить новые данные
            if self._load_users_from_db():
                # ✅ Логировать изменения
                added = set(self.users.keys()) - set(old_users.keys())
                removed = set(old_users.keys()) - set(self.users.keys())
                modified = {
                    u for u in self.users
                    if u in old_users and self.users[u] != old_users[u]
                }

                if added:
                    logger.info(f"✅ Добавлены: {', '.join(added)}")
                if removed:
                    logger.info(f"✅ Удалены: {', '.join(removed)}")
                if modified:
                    logger.info(f"✅ Изменены: {', '.join(modified)}")

                logger.info(f"✅ Перезагружено: {len(self.users)} пользователей")
                return True
            else:
                logger.warning("⚠️ Не удалось загрузить пользователей из БД")
                return False

        except Exception as e:
            logger.error(f"❌ Ошибка reload_users: {e}", exc_info=True)
            # ✅ Не терять старые данные при ошибке
            return False

    def reload_if_needed(self, username: str = None) -> bool:
        """
        Умная перезагрузка: только если пользователь не в кэше

        Args:
            username: Если указан — проверить только его

        Returns:
            bool: True если данные были перезагружены
        """
        if username and username in self.users:
            # ✅ Пользователь уже в кэше — не перезагружать
            return False

        # ✅ Перезагрузить весь кэш
        return self.reload_users()
