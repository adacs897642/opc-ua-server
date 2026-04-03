# opc/cert_manager.py
# -*- coding: utf-8 -*-
"""
Менеджер сертификатов OPC UA
Автогенерация при отсутствии + проверка валидности
Генерирует сертификаты с SAN (DNS + IP) для совместимости с UaExpert
"""

import os
import socket
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Tuple, List, Set, Optional, Dict

from cryptography import x509
from cryptography.x509.oid import NameOID, ExtensionOID
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.backends import default_backend
import ipaddress

logger = logging.getLogger('opc.cert_manager')


class CertManager:
    """Управление сертификатами OPC UA сервера"""

    def __init__(
            self,
            pki_dir: str = "pki/own",
            common_name: str = "opc-server.local",
            organization: str = "SystemX",
            country: str = "RU",
            state: str = "Moscow",
            locality: str = "Moscow",
            validity_days: int = 365,
            additional_dns: List[str] = None,
            additional_ips: List[str] = None
    ):
        self.pki_dir = Path(pki_dir)
        self.common_name = common_name
        self.organization = organization
        self.country = country
        self.state = state
        self.locality = locality

        # ✅ Преобразовать в int если строка
        try:
            self.validity_days = int(validity_days)
        except (ValueError, TypeError):
            self.validity_days = 365
            logger.warning(f"⚠️ Неверный validity_days={validity_days}, используем 365")

        # ✅ Дополнительные DNS/IP из конфига
        self.additional_dns = additional_dns or []
        self.additional_ips = additional_ips or []

        self.cert_path = self.pki_dir / "certificate.pem"
        self.key_path = self.pki_dir / "private_key.pem"

    def ensure_certificates(self) -> bool:
        """
        Проверить и при необходимости создать сертификаты

        Returns:
            bool: True если сертификаты готовы к использованию
        """
        # ✅ 1. Проверить существуют ли файлы
        if self.cert_path.exists() and self.key_path.exists():
            logger.info(f"✅ Сертификаты найдены: {self.cert_path}")

            # ✅ 2. Проверить валидность
            if self._validate_certificates():
                logger.info("✅ Сертификаты валидны")
                return True
            else:
                logger.warning("⚠️ Сертификаты невалидны, будут пересозданы")

        # ✅ 3. Создать новые
        logger.info("🔑 Генерация новых сертификатов...")
        try:
            self._generate_certificates()
            logger.info(f"✅ Сертификаты созданы: {self.cert_path}")
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка генерации сертификатов: {e}", exc_info=True)
            return False

    def _validate_certificates(self) -> bool:
        """
        Проверить валидность существующих сертификатов

        Returns:
            bool: True если сертификаты валидны
        """
        try:
            # ✅ Загрузить сертификат
            with open(self.cert_path, 'rb') as f:
                cert = x509.load_pem_x509_certificate(f.read(), default_backend())

            # ✅ 1. Проверить срок действия
            now = datetime.now(timezone.utc)

            try:
                not_before = cert.not_valid_before_utc
                not_after = cert.not_valid_after_utc
            except AttributeError:
                not_before = cert.not_valid_before.replace(tzinfo=timezone.utc)
                not_after = cert.not_valid_after.replace(tzinfo=timezone.utc)

            if now < not_before:
                logger.warning(f"⚠️ Сертификат ещё не активен: {not_before}")
                return False
            if now > not_after:
                logger.warning(f"⚠️ Сертификат истёк: {not_after}")
                return False

            # ✅ 2. Проверить что ключ соответствует сертификату
            try:
                with open(self.key_path, 'rb') as f:
                    private_key = serialization.load_pem_private_key(
                        f.read(), password=None, backend=default_backend()
                    )

                # ✅ Получить публичные ключи
                cert_public_key = cert.public_key()
                key_public_key = private_key.public_key()

                # ✅ Сравнить публичные числа
                cert_numbers = cert_public_key.public_numbers()
                key_numbers = key_public_key.public_numbers()

                if cert_numbers.n != key_numbers.n:
                    logger.warning("⚠️ Ключ не соответствует сертификату (modulus)!")
                    return False
                if cert_numbers.e != key_numbers.e:
                    logger.warning("⚠️ Ключ не соответствует сертификату (exponent)!")
                    return False

                logger.debug("✅ Ключ соответствует сертификату")

            except FileNotFoundError:
                logger.warning(f"⚠️ Файл ключа не найден: {self.key_path}")
                return False
            except Exception as e:
                logger.warning(f"⚠️ Не удалось проверить соответствие ключа: {e}")
                logger.warning("⚠️ Пропускаем проверку ключа, продолжаем запуск")

            # ✅ 3. Проверить SubjectAltName (требуется для OPC UA и UaExpert)
            try:
                san_ext = cert.extensions.get_extension_for_oid(
                    ExtensionOID.SUBJECT_ALTERNATIVE_NAME
                )
                if not san_ext.value:
                    logger.warning("⚠️ SubjectAltName пуст!")
                    return False

                # ✅ Логировать что есть в SAN
                san_entries = [str(name) for name in san_ext.value]
                logger.debug(f"📋 SAN содержит: {san_entries}")

            except x509.ExtensionNotFound:
                logger.warning("⚠️ SubjectAltName отсутствует (требуется для OPC UA)!")
                return False

            # ✅ 4. Предупреждение если скоро истекает
            days_left = (not_after - now).days
            if days_left < 30:
                logger.warning(f"⚠️ Сертификат истекает через {days_left} дней!")

            logger.info(f"✅ Сертификат валиден (осталось {days_left} дней)")
            return True

        except Exception as e:
            logger.error(f"❌ Ошибка проверки сертификатов: {e}", exc_info=True)
            return False

    def _get_server_addresses(self) -> Tuple[List[str], List[str]]:
        """
        Получить DNS имена и IP адреса сервера для SAN

        Returns:
            tuple: (dns_names, ip_addresses)
        """
        dns_names: Set[str] = {
            self.common_name,
            "localhost",
        }
        ip_addresses: Set[str] = {
            "127.0.0.1",
            "::1",
        }

        # ✅ Добавить hostname (как в рабочей OpenSSL команде)
        try:
            hostname = socket.gethostname()
            dns_names.add(hostname)
            dns_names.add(f"{hostname}.local")  # mDNS
            logger.debug(f"🌐 Hostname: {hostname}")
        except Exception as e:
            logger.debug(f"⚠️ Не удалось получить hostname: {e}")

        # ✅ Добавить все IPv4 адреса
        try:
            for iface in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
                ip = iface[4][0]
                ip_addresses.add(ip)
                logger.debug(f"🌐 Найден IPv4: {ip}")
        except Exception as e:
            logger.debug(f"⚠️ Не удалось получить IP адреса: {e}")

        # ✅ Попытаться получить внешний IP (через подключение к Google DNS)
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            ip_addresses.add(ip)
            s.close()
            logger.debug(f"🌐 Внешний IP: {ip}")
        except Exception as e:
            logger.debug(f"⚠️ Не удалось получить внешний IP: {e}")

        # ✅ Добавить дополнительные из конфига
        for dns in self.additional_dns:
            dns_names.add(dns)
        for ip in self.additional_ips:
            ip_addresses.add(ip)

        return sorted(list(dns_names)), sorted(list(ip_addresses))

    def _generate_certificates(self):
        """Сгенерировать новую пару сертификат+ключ с SAN (как в рабочей OpenSSL команде)"""

        # ✅ 1. Создать директорию
        self.pki_dir.mkdir(parents=True, exist_ok=True)

        # ✅ 2. Получить локальные IP и DNS имена
        dns_names, ip_addresses = self._get_server_addresses()
        logger.info(f"🌐 DNS: {dns_names}")
        logger.info(f"🌐 IP: {ip_addresses}")

        # ✅ 3. Сгенерировать приватный ключ
        logger.debug("🔑 Генерация RSA-2048 ключа...")
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
            backend=default_backend()
        )

        # ✅ 4. Создать subject/issuer (как в OpenSSL команде)
        subject = issuer = x509.Name([
            x509.NameAttribute(NameOID.COUNTRY_NAME, self.country),
            x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, self.state),
            x509.NameAttribute(NameOID.LOCALITY_NAME, self.locality),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, self.organization),
            x509.NameAttribute(NameOID.COMMON_NAME, self.common_name),
        ])

        # ✅ 5. Создать builder
        builder = x509.CertificateBuilder()
        builder = builder.subject_name(subject)
        builder = builder.issuer_name(issuer)
        builder = builder.public_key(private_key.public_key())
        builder = builder.serial_number(x509.random_serial_number())
        builder = builder.not_valid_before(datetime.now(timezone.utc))
        builder = builder.not_valid_after(datetime.now(timezone.utc) + timedelta(days=self.validity_days))

        # ✅ 6. Добавить SubjectAltName (ОБЯЗАТЕЛЬНО для OPC UA и UaExpert!)
        san_entries = []
        for dns in dns_names:
            san_entries.append(x509.DNSName(dns))
            logger.debug(f"   🌐 DNS: {dns}")
        for ip_str in ip_addresses:
            try:
                san_entries.append(x509.IPAddress(ipaddress.ip_address(ip_str)))
                logger.debug(f"   🌐 IP: {ip_str}")
            except ValueError as e:
                logger.warning(f"⚠️ Неверный IP {ip_str}: {e}")

            # ✅ 1. Basic Constraints (как в OpenSSL)
        builder = builder.add_extension(
            x509.BasicConstraints(ca=True, path_length=0),  # ← ← ← ca=True!
            critical=True  # ← ← ← critical=True!
        )

        # ✅ 2. Subject Alternative Name (ОБЯЗАТЕЛЬНО)
        builder = builder.add_extension(
            x509.SubjectAlternativeName(san_entries),
            critical=False
        )

        # ✅ 3. Subject Key Identifier
        builder = builder.add_extension(
            x509.SubjectKeyIdentifier.from_public_key(private_key.public_key()),
            critical=False
        )

        # ✅ 4. Authority Key Identifier
        builder = builder.add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_public_key(private_key.public_key()),
            critical=False
        )

        # ✅ 8. Подписать сертификат (SHA256 как в OpenSSL команде)
        logger.debug("✍️  Подпись SHA256...")
        certificate = builder.sign(private_key, hashes.SHA256(), default_backend())

        # ✅ 9. Сохранить ключ (chmod 600 для безопасности)
        with open(self.key_path, "wb") as f:
            f.write(private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.TraditionalOpenSSL,
                encryption_algorithm=serialization.NoEncryption()
            ))
        os.chmod(self.key_path, 0o600)  # 🔒 Только владелец читает

        # ✅ 10. Сохранить сертификат
        with open(self.cert_path, "wb") as f:
            f.write(certificate.public_bytes(serialization.Encoding.PEM))

        # ✅ 11. Показать информацию (как в OpenSSL выводе)
        logger.info(f"✅ Сертификат создан:")
        logger.info(f"   Subject: {certificate.subject.rfc4514_string()}")
        logger.info(
            f"   Valid: {certificate.not_valid_before.strftime('%Y-%m-%d %H:%M:%S')} — {certificate.not_valid_after.strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info(f"   SAN: {len(san_entries)} записей ({len(dns_names)} DNS + {len(ip_addresses)} IP)")

    def regenerate(self, backup: bool = True) -> bool:
        """
        Принудительно пересоздать сертификаты

        Args:
            backup: Создать бэкап старых сертификатов

        Returns:
            bool: True если успешно
        """
        if backup and self.cert_path.exists():
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_dir = self.pki_dir / f"backup_{timestamp}"
            backup_dir.mkdir(exist_ok=True)

            import shutil
            shutil.copy2(self.cert_path, backup_dir / "certificate.pem.old")
            shutil.copy2(self.key_path, backup_dir / "private_key.pem.old")

            logger.info(f"💾 Бэкап создан: {backup_dir}")

        # ✅ Удалить старые
        if self.cert_path.exists():
            self.cert_path.unlink()
        if self.key_path.exists():
            self.key_path.unlink()

        # ✅ Создать новые
        return self.ensure_certificates()

    def get_certificate_info(self) -> dict:
        """Получить информацию о сертификате"""
        if not self.cert_path.exists():
            return {"error": "Certificate not found"}

        try:
            with open(self.cert_path, 'rb') as f:
                cert = x509.load_pem_x509_certificate(f.read(), default_backend())

            san_ext = cert.extensions.get_extension_for_oid(
                ExtensionOID.SUBJECT_ALTERNATIVE_NAME
            )

            try:
                not_after = cert.not_valid_after_utc
            except AttributeError:
                not_after = cert.not_valid_after.replace(tzinfo=timezone.utc)

            return {
                "subject": cert.subject.rfc4514_string(),
                "issuer": cert.issuer.rfc4514_string(),
                "valid_from": cert.not_valid_before.isoformat(),
                "valid_to": not_after.isoformat(),
                "days_left": (not_after - datetime.now(timezone.utc)).days,
                "signature_algorithm": cert.signature_algorithm_oid._name,
                "san": [str(name) for name in san_ext.value],
                "serial": format(cert.serial_number, 'X'),
            }
        except Exception as e:
            return {"error": str(e)}
# # opc/cert_manager.py
# # -*- coding: utf-8 -*-
# """
# Менеджер сертификатов OPC UA
# Автогенерация при отсутствии + проверка валидности
# """
#
# import os
# import socket
# import logging
# from datetime import datetime, timedelta, timezone
# from pathlib import Path
# from typing import Tuple, Optional, List, Set
#
# from cryptography import x509
# from cryptography.x509.oid import NameOID, ExtensionOID
# from cryptography.hazmat.primitives import hashes, serialization
# from cryptography.hazmat.primitives.asymmetric import rsa
# from cryptography.hazmat.backends import default_backend
# import ipaddress
#
# logger = logging.getLogger('opc.cert_manager')
#
#
# class CertManager:
#     """Управление сертификатами OPC UA сервера"""
#
#     def __init__(
#             self,
#             pki_dir: str = "pki/own",
#             common_name: str = "opc-server.local",
#             organization: str = "SystemX",
#             validity_days: int = 365
#     ):
#         self.pki_dir = Path(pki_dir)
#         self.common_name = common_name
#         self.organization = organization
#
#         # ✅ ИСПРАВЛЕНИЕ 1: Преобразовать в int если строка
#         try:
#             self.validity_days = int(validity_days)
#         except (ValueError, TypeError):
#             self.validity_days = 365
#             logger.warning(f"⚠️ Неверный validity_days={validity_days}, используем 365")
#
#         self.cert_path = self.pki_dir / "certificate.pem"
#         self.key_path = self.pki_dir / "private_key.pem"
#
#     def ensure_certificates(self) -> bool:
#         """
#         Проверить и при необходимости создать сертификаты
#
#         Returns:
#             bool: True если сертификаты готовы к использованию
#         """
#         # ✅ 1. Проверить существуют ли файлы
#         if self.cert_path.exists() and self.key_path.exists():
#             logger.info(f"✅ Сертификаты найдены: {self.cert_path}")
#
#             # ✅ 2. Проверить валидность
#             if self._validate_certificates():
#                 logger.info("✅ Сертификаты валидны")
#                 return True
#             else:
#                 logger.warning("⚠️ Сертификаты невалидны, будут пересозданы")
#
#         # ✅ 3. Создать новые
#         logger.info("🔑 Генерация новых сертификатов...")
#         try:
#             self._generate_certificates()
#             logger.info(f"✅ Сертификаты созданы: {self.cert_path}")
#             return True
#         except Exception as e:
#             logger.error(f"❌ Ошибка генерации сертификатов: {e}", exc_info=True)
#             return False
#
#     # opc/cert_manager.py
#
#     def _validate_certificates(self) -> bool:
#         """
#         Проверить валидность существующих сертификатов
#
#         Returns:
#             bool: True если сертификаты валидны
#         """
#         try:
#             # ✅ Загрузить сертификат
#             with open(self.cert_path, 'rb') as f:
#                 cert = x509.load_pem_x509_certificate(f.read(), default_backend())
#
#             # ✅ 1. Проверить срок действия
#             now = datetime.now(timezone.utc)
#
#             try:
#                 not_before = cert.not_valid_before_utc
#                 not_after = cert.not_valid_after_utc
#             except AttributeError:
#                 not_before = cert.not_valid_before.replace(tzinfo=timezone.utc)
#                 not_after = cert.not_valid_after.replace(tzinfo=timezone.utc)
#
#             if now < not_before:
#                 logger.warning(f"⚠️ Сертификат ещё не активен: {not_before}")
#                 return False
#             if now > not_after:
#                 logger.warning(f"⚠️ Сертификат истёк: {not_after}")
#                 return False
#
#             # ✅ 2. Проверить что ключ соответствует сертификату
#             try:
#                 with open(self.key_path, 'rb') as f:
#                     private_key = serialization.load_pem_private_key(
#                         f.read(), password=None, backend=default_backend()
#                     )
#
#                 # ✅ Получить публичные ключи
#                 cert_public_key = cert.public_key()
#                 key_public_key = private_key.public_key()
#
#                 # ✅ Сравнить публичные числа
#                 cert_numbers = cert_public_key.public_numbers()
#                 key_numbers = key_public_key.public_numbers()
#
#                 if cert_numbers.n != key_numbers.n:
#                     logger.warning("⚠️ Ключ не соответствует сертификату (modulus)!")
#                     return False
#                 if cert_numbers.e != key_numbers.e:
#                     logger.warning("⚠️ Ключ не соответствует сертификату (exponent)!")
#                     return False
#
#                 logger.debug("✅ Ключ соответствует сертификату")
#
#             except FileNotFoundError:
#                 logger.warning(f"⚠️ Файл ключа не найден: {self.key_path}")
#                 return False
#             except Exception as e:
#                 # ✅ Не блокировать запуск если проверка не прошла
#                 logger.warning(f"⚠️ Не удалось проверить соответствие ключа: {e}")
#                 logger.warning("⚠️ Пропускаем проверку ключа, продолжаем запуск")
#                 # ✅ Не возвращать False — лучше пропустить проверку чем пересоздавать
#
#             # ✅ 3. Проверить SubjectAltName (требуется для OPC UA)
#             try:
#                 san_ext = cert.extensions.get_extension_for_oid(
#                     ExtensionOID.SUBJECT_ALTERNATIVE_NAME
#                 )
#                 if not san_ext.value:
#                     logger.warning("⚠️ SubjectAltName пуст!")
#                     return False
#             except x509.ExtensionNotFound:
#                 logger.warning("⚠️ SubjectAltName отсутствует (требуется для OPC UA)!")
#                 return False
#
#             # ✅ 4. Предупреждение если скоро истекает
#             days_left = (not_after - now).days
#             if days_left < 30:
#                 logger.warning(f"⚠️ Сертификат истекает через {days_left} дней!")
#
#             logger.info(f"✅ Сертификат валиден (осталось {days_left} дней)")
#             return True
#
#         except Exception as e:
#             logger.error(f"❌ Ошибка проверки сертификатов: {e}", exc_info=True)
#             # ✅ При ошибке проверки — лучше пересоздать чем не запуститься
#             return False
#
#     def _generate_certificates(self):
#         """Сгенерировать новую пару сертификат+ключ"""
#
#         # ✅ 1. Создать директорию
#         self.pki_dir.mkdir(parents=True, exist_ok=True)
#
#         # ✅ 2. Получить локальные IP и DNS имена
#         dns_names, ip_addresses = self._get_server_addresses()
#         logger.info(f"🌐 DNS: {dns_names}")
#         logger.info(f"🌐 IP: {ip_addresses}")
#
#         # ✅ 3. Сгенерировать приватный ключ
#         logger.debug("🔑 Генерация RSA-2048 ключа...")
#         private_key = rsa.generate_private_key(
#             public_exponent=65537,
#             key_size=2048,
#             backend=default_backend()
#         )
#
#         # ✅ 4. Создать subject/issuer
#         subject = issuer = x509.Name([
#             x509.NameAttribute(NameOID.COUNTRY_NAME, "RU"),
#             x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "Unknown"),
#             x509.NameAttribute(NameOID.LOCALITY_NAME, "Unknown"),
#             x509.NameAttribute(NameOID.ORGANIZATION_NAME, self.organization),
#             x509.NameAttribute(NameOID.COMMON_NAME, self.common_name),
#         ])
#
#         # ✅ 5. Создать builder
#         builder = x509.CertificateBuilder()
#         builder = builder.subject_name(subject)
#         builder = builder.issuer_name(issuer)
#         builder = builder.public_key(private_key.public_key())
#         builder = builder.serial_number(x509.random_serial_number())
#         builder = builder.not_valid_before(datetime.now(timezone.utc))
#         builder = builder.not_valid_after(datetime.now(timezone.utc) + timedelta(days=self.validity_days))
#
#         # ✅ 6. Добавить SubjectAltName (ОБЯЗАТЕЛЬНО для OPC UA)
#         san_entries = []
#         for dns in dns_names:
#             san_entries.append(x509.DNSName(dns))
#         for ip_str in ip_addresses:
#             try:
#                 san_entries.append(x509.IPAddress(ipaddress.ip_address(ip_str)))
#             except ValueError:
#                 logger.warning(f"⚠️ Неверный IP: {ip_str}")
#
#         builder = builder.add_extension(
#             x509.SubjectAlternativeName(san_entries),
#             critical=False
#         )
#
#         # ✅ 7. Добавить обязательные расширения OPC UA
#         builder = builder.add_extension(
#             x509.BasicConstraints(ca=False, path_length=None),
#             critical=True
#         )
#         builder = builder.add_extension(
#             x509.KeyUsage(
#                 digital_signature=True,
#                 content_commitment=False,
#                 key_encipherment=True,
#                 data_encipherment=False,
#                 key_agreement=False,
#                 key_cert_sign=False,
#                 crl_sign=False,
#                 encipher_only=False,
#                 decipher_only=False
#             ),
#             critical=True
#         )
#         builder = builder.add_extension(
#             x509.ExtendedKeyUsage([x509.oid.ExtendedKeyUsageOID.SERVER_AUTH]),
#             critical=False
#         )
#
#         # ✅ 8. Подписать сертификат
#         logger.debug("✍️  Подпись SHA256...")
#         certificate = builder.sign(private_key, hashes.SHA256(), default_backend())
#
#         # ✅ 9. Сохранить ключ (chmod 600!)
#         with open(self.key_path, "wb") as f:
#             f.write(private_key.private_bytes(
#                 encoding=serialization.Encoding.PEM,
#                 format=serialization.PrivateFormat.TraditionalOpenSSL,
#                 encryption_algorithm=serialization.NoEncryption()
#             ))
#         os.chmod(self.key_path, 0o600)  # 🔒 Только владелец читает
#
#         # ✅ 10. Сохранить сертификат
#         with open(self.cert_path, "wb") as f:
#             f.write(certificate.public_bytes(serialization.Encoding.PEM))
#
#         # ✅ 11. Показать информацию
#         logger.info(f"✅ Сертификат создан:")
#         logger.info(f"   Subject: {certificate.subject.rfc4514_string()}")
#         logger.info(f"   Valid: {certificate.not_valid_before} — {certificate.not_valid_after}")
#         logger.info(f"   SAN: {len(san_entries)} записей")
#
#     def _get_server_addresses(self) -> Tuple[List[str], List[str]]:
#         """
#         Получить DNS имена и IP адреса сервера для SAN
#
#         Returns:
#             tuple: (dns_names, ip_addresses)
#         """
#         dns_names: Set[str] = {
#             self.common_name,
#             "localhost",
#         }
#         ip_addresses: Set[str] = {
#             "127.0.0.1",
#             "::1",
#         }
#
#         # ✅ Добавить hostname
#         try:
#             hostname = socket.gethostname()
#             dns_names.add(hostname)
#             dns_names.add(f"{hostname}.local")  # mDNS
#         except:
#             pass
#
#         # ✅ Добавить все IP адреса
#         try:
#             for iface in socket.getaddrinfo(socket.gethostname(), None):
#                 ip = iface[4][0]
#                 if ':' not in ip:  # IPv4
#                     ip_addresses.add(ip)
#         except:
#             pass
#
#         # ✅ Попытаться получить внешний IP
#         try:
#             s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
#             s.connect(("8.8.8.8", 80))
#             ip = s.getsockname()[0]
#             ip_addresses.add(ip)
#             s.close()
#         except:
#             pass
#
#         return sorted(list(dns_names)), sorted(list(ip_addresses))
#
#     def regenerate(self, backup: bool = True) -> bool:
#         """
#         Принудительно пересоздать сертификаты
#
#         Args:
#             backup: Создать бэкап старых сертификатов
#
#         Returns:
#             bool: True если успешно
#         """
#         if backup and self.cert_path.exists():
#             # ✅ Создать бэкап
#             timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
#             backup_dir = self.pki_dir / f"backup_{timestamp}"
#             backup_dir.mkdir(exist_ok=True)
#
#             import shutil
#             shutil.copy2(self.cert_path, backup_dir / "certificate.pem.old")
#             shutil.copy2(self.key_path, backup_dir / "private_key.pem.old")
#
#             logger.info(f"💾 Бэкап создан: {backup_dir}")
#
#         # ✅ Удалить старые
#         if self.cert_path.exists():
#             self.cert_path.unlink()
#         if self.key_path.exists():
#             self.key_path.unlink()
#
#         # ✅ Создать новые
#         return self.ensure_certificates()
#
#     def get_certificate_info(self) -> dict:
#         """Получить информацию о сертификате"""
#         if not self.cert_path.exists():
#             return {"error": "Certificate not found"}
#
#         try:
#             with open(self.cert_path, 'rb') as f:
#                 cert = x509.load_pem_x509_certificate(f.read(), default_backend())
#
#             san_ext = cert.extensions.get_extension_for_oid(
#                 ExtensionOID.SUBJECT_ALTERNATIVE_NAME
#             )
#
#             # ✅ Использовать UTC версии
#             try:
#                 not_after = cert.not_valid_after_utc
#             except AttributeError:
#                 not_after = cert.not_valid_after.replace(tzinfo=timezone.utc)
#
#             return {
#                 "subject": cert.subject.rfc4514_string(),
#                 "issuer": cert.issuer.rfc4514_string(),
#                 "valid_from": cert.not_valid_before.isoformat(),
#                 "valid_to": not_after.isoformat(),
#                 "days_left": (not_after - datetime.now(timezone.utc)).days,
#                 "signature_algorithm": cert.signature_algorithm_oid._name,
#                 "san": [str(name) for name in san_ext.value],
#                 "serial": format(cert.serial_number, 'X'),
#             }
#         except Exception as e:
#             return {"error": str(e)}
