# utils/logging_config.py

import logging
import sys
from pathlib import Path


def setup_logging(config_path: str) -> None:
    """Настраивает логирование"""
    import json

    with open(config_path, 'r', encoding='utf-8') as f:
        config = json.load(f)

    log_cfg = config.get('logging', {})
    level = getattr(logging, log_cfg.get('level', 'INFO').upper())

    handlers = [logging.StreamHandler(sys.stdout)]

    if log_cfg.get('file'):
        Path(log_cfg['file']).parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_cfg['file'], encoding='utf-8'))

    logging.basicConfig(
        level=level,
        format=log_cfg.get('format', '%(asctime)s [%(levelname)s] %(name)s: %(message)s'),
        handlers=handlers,
        force=True
    )


def get_logger(name: str) -> logging.Logger:
    """Получает именованный логгер"""
    return logging.getLogger(name)