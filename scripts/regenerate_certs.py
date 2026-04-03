#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Генерация сертификатов OPC UA с SAN (DNS + IP)
Совместимо с UaExpert (как OpenSSL с -addext)

Эквивалент команды:
openssl req -x509 -newkey rsa:2048 \
  -keyout pki/own/private_key.pem \
  -out pki/own/certificate.pem \
  -days 365 -nodes \
  -subj "/C=RU/ST=Moscow/L=Moscow/O=SystemX/CN=opc-server.local" \
  -addext "subjectAltName=DNS:opc-server.local,DNS:localhost,DNS:hostname,IP:127.0.0.1,IP:192.168.31.151"
"""

import os
import sys
import socket
import argparse
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography import x509
from cryptography.x509.oid import NameOID, ExtensionOID
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.backends import default_backend
import ipaddress

# ✅ Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


def get_server_addresses(additional_dns=None, additional_ips=None) -> tuple:
    """
    Получить DNS имена и IP адреса для SAN

    Returns:
        tuple: (dns_names, ip_addresses)
    """
    dns_names = {
        "opc-server.local",
        "localhost",
    }
    ip_addresses = {
        "127.0.0.1",
        "::1",
    }

    # ✅ Добавить hostname
    try:
        hostname = socket.gethostname()
        dns_names.add(hostname)
        dns_names.add(f"{hostname}.local")
        logger.info(f"🌐 Hostname: {hostname}")
    except Exception as e:
        logger.debug(f"⚠️ Не удалось получить hostname: {e}")

    # ✅ Добавить все IPv4 адреса
    try:
        for iface in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = iface[4][0]
            ip_addresses.add(ip)
            logger.info(f"🌐 Найден IPv4: {ip}")
    except Exception as e:
        logger.debug(f"⚠️ Не удалось получить IP адреса: {e}")

    # ✅ Попытаться получить внешний IP
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        ip_addresses.add(ip)
        s.close()
        logger.info(f"🌐 Внешний IP: {ip}")
    except Exception as e:
        logger.debug(f"⚠️ Не удалось получить внешний IP: {e}")

    # ✅ Добавить дополнительные из аргументов
    if additional_dns:
        for dns in additional_dns:
            dns_names.add(dns)
    if additional_ips:
        for ip in additional_ips:
            ip_addresses.add(ip)

    return sorted(list(dns_names)), sorted(list(ip_addresses))


def generate_certificates(
        output_dir: str = "pki/own",
        common_name: str = "opc-server.local",
        organization: str = "SystemX",
        country: str = "RU",
        state: str = "Moscow",
        locality: str = "Moscow",
        validity_days: int = 365,
        additional_dns: list = None,
        additional_ips: list = None,
        force: bool = False
):
    """
    Сгенерировать сертификаты OPC UA с SAN (как cert_manager)

    Args:
        output_dir: Директория для сохранения
        common_name: CN сертификата
        organization: O сертификата
        country: C сертификата
        state: ST сертификата
        locality: L сертификата
        validity_days: Срок действия в днях
        additional_dns: Дополнительные DNS имена
        additional_ips: Дополнительные IP адреса
        force: Пересоздать даже если существуют
    """

    pki_dir = Path(output_dir)
    cert_path = pki_dir / "certificate.pem"
    key_path = pki_dir / "private_key.pem"

    # ✅ Проверить существуют ли сертификаты
    if cert_path.exists() and key_path.exists() and not force:
        logger.warning(f"⚠️ Сертификаты уже существуют: {cert_path}")
        logger.warning("   Используйте --force для пересоздания")
        logger.warning("   Или удалите файлы вручную")
        return False

    # ✅ Создать директорию
    pki_dir.mkdir(parents=True, exist_ok=True)

    # ✅ Получить DNS и IP для SAN
    dns_names, ip_addresses = get_server_addresses(additional_dns, additional_ips)
    logger.info(f"🌐 DNS для SAN: {dns_names}")
    logger.info(f"🌐 IP для SAN: {ip_addresses}")

    # ✅ Подтверждение перед генерацией
    if not force:
        print("\n⚠️  ВНИМАНИЕ:")
        print("   При пересоздании сертификатов ВСЕ клиенты должны будут")
        print("   заново доверять серверу (удалить старый сертификат в UaExpert)")
        print("\n   Продолжить? (y/N): ", end='')
        if input().strip().lower() != 'y':
            logger.info("❌ Отменено пользователем")
            return False

    # ✅ Удалить старые если force
    if force:
        if cert_path.exists():
            cert_path.unlink()
            logger.info(f"🗑️  Удалён старый сертификат: {cert_path}")
        if key_path.exists():
            key_path.unlink()
            logger.info(f"🗑️  Удалён старый ключ: {key_path}")

    # ✅ 1. Сгенерировать приватный ключ
    logger.info("🔑 Генерация RSA-2048 ключа...")
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
        backend=default_backend()
    )

    # ✅ 2. Создать subject/issuer
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, country),
        x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, state),
        x509.NameAttribute(NameOID.LOCALITY_NAME, locality),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, organization),
        x509.NameAttribute(NameOID.COMMON_NAME, common_name),
    ])

    # ✅ 3. Создать builder
    builder = x509.CertificateBuilder()
    builder = builder.subject_name(subject)
    builder = builder.issuer_name(issuer)
    builder = builder.public_key(private_key.public_key())
    builder = builder.serial_number(x509.random_serial_number())
    builder = builder.not_valid_before(datetime.now(timezone.utc))
    builder = builder.not_valid_after(datetime.now(timezone.utc) + timedelta(days=validity_days))

    # ✅ 4. Basic Constraints (КАК В CERT_MANAGER - для совместимости с UaExpert)
    logger.debug("✏️  Добавление Basic Constraints (CA:TRUE, critical)")
    builder = builder.add_extension(
        x509.BasicConstraints(ca=True, path_length=0),  # ← ← ← ca=True!
        critical=True  # ← ← ← critical=True!
    )

    # ✅ 5. Subject Alternative Name (ОБЯЗАТЕЛЬНО для UaExpert!)
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

    logger.debug("✏️  Добавление Subject Alternative Name")
    builder = builder.add_extension(
        x509.SubjectAlternativeName(san_entries),
        critical=False
    )

    # ✅ 6. Subject Key Identifier
    logger.debug("✏️  Добавление Subject Key Identifier")
    builder = builder.add_extension(
        x509.SubjectKeyIdentifier.from_public_key(private_key.public_key()),
        critical=False
    )

    # ✅ 7. Authority Key Identifier
    logger.debug("✏️  Добавление Authority Key Identifier")
    builder = builder.add_extension(
        x509.AuthorityKeyIdentifier.from_issuer_public_key(private_key.public_key()),
        critical=False
    )

    # ❌ 8. НЕ добавлять Key Usage (как в OpenSSL - для совместимости!)
    # ❌ 9. НЕ добавлять Extended Key Usage (как в OpenSSL - для совместимости!)

    # ✅ 10. Подписать сертификат
    logger.info("✍️  Подпись SHA256...")
    certificate = builder.sign(private_key, hashes.SHA256(), default_backend())

    # ✅ 11. Сохранить ключ
    with open(key_path, "wb") as f:
        f.write(private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption()
        ))
    os.chmod(key_path, 0o600)
    logger.info(f"✅ Ключ сохранён: {key_path}")

    # ✅ 12. Сохранить сертификат
    with open(cert_path, "wb") as f:
        f.write(certificate.public_bytes(serialization.Encoding.PEM))
    logger.info(f"✅ Сертификат сохранён: {cert_path}")

    # ✅ 13. Показать информацию
    print("\n" + "=" * 60)
    print("✅ СЕРТИФИКАТЫ СОЗДАНЫ (совместимы с UaExpert)")
    print("=" * 60)
    print(f"📋 Subject: {certificate.subject.rfc4514_string()}")
    print(
        f"📅 Действует: {certificate.not_valid_before.strftime('%Y-%m-%d')} — {certificate.not_valid_after.strftime('%Y-%m-%d')}")
    print(f"🔐 Алгоритм: SHA256withRSA (2048 bit)")
    print(f"🔒 Basic Constraints: CA:TRUE (critical)")
    print(f"🌐 SAN ({len(san_entries)} записей):")
    for entry in san_entries:
        print(f"   • {entry}")
    print("=" * 60)
    print("\n📋 Расширения:")
    print("   ✅ Basic Constraints: CA:TRUE (critical)")
    print("   ✅ Subject Alternative Name")
    print("   ✅ Subject Key Identifier")
    print("   ✅ Authority Key Identifier")
    print("   ❌ Key Usage: НЕ добавлено (для совместимости)")
    print("   ❌ Extended Key Usage: НЕ добавлено (для совместимости)")
    print("=" * 60)
    print("\n⚠️  ВАЖНО:")
    print("   1. Перезапустите OPC UA сервер")
    print("   2. В UaExpert: удалите старый сертификат")
    print("      (Options → Security → Trusted Servers)")
    print("   3. Подключитесь заново и нажмите 'Trust Server Certificate'")
    print("=" * 60)

    return True


def main():
    parser = argparse.ArgumentParser(
        description='Генерация сертификатов OPC UA с SAN (как cert_manager)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Примеры:
  %(prog)s
  %(prog)s --force
  %(prog)s --ip 192.168.31.151 --ip 10.0.0.5
  %(prog)s --dns myserver.local --dns opc.internal
  %(prog)s --cn myopc.server.com --org "My Company"
        '''
    )

    parser.add_argument('--output', '-o', default='pki/own',
                        help='Директория для сертификатов (по умолчанию: pki/own)')
    parser.add_argument('--cn', '--common-name', default='opc-server.local',
                        help='Common Name сертификата (по умолчанию: opc-server.local)')
    parser.add_argument('--org', '--organization', default='SystemX',
                        help='Organization (по умолчанию: SystemX)')
    parser.add_argument('--country', '-c', default='RU',
                        help='Country (по умолчанию: RU)')
    parser.add_argument('--state', '-s', default='Moscow',
                        help='State/Province (по умолчанию: Moscow)')
    parser.add_argument('--locality', '-l', default='Moscow',
                        help='Locality/City (по умолчанию: Moscow)')
    parser.add_argument('--days', '-d', type=int, default=365,
                        help='Срок действия в днях (по умолчанию: 365)')
    parser.add_argument('--dns', action='append', dest='additional_dns',
                        help='Дополнительные DNS имена (можно указать несколько)')
    parser.add_argument('--ip', action='append', dest='additional_ips',
                        help='Дополнительные IP адреса (можно указать несколько)')
    parser.add_argument('--force', '-f', action='store_true',
                        help='Пересоздать даже если сертификаты существуют')
    parser.add_argument('--quiet', '-q', action='store_true',
                        help='Тихий режим (меньше вывода)')

    args = parser.parse_args()

    if args.quiet:
        logging.getLogger().setLevel(logging.WARNING)

    success = generate_certificates(
        output_dir=args.output,
        common_name=args.cn,
        organization=args.org,
        country=args.country,
        state=args.state,
        locality=args.locality,
        validity_days=args.days,
        additional_dns=args.additional_dns,
        additional_ips=args.additional_ips,
        force=args.force
    )

    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()