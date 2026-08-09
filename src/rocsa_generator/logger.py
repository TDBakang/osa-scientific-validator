"""Logging infrastructure for rocsa_generator."""

import logging
import sys
from typing import Optional

LOGGER_NAME = "rocsa_generator"


def get_logger(name: Optional[str] = None) -> logging.Logger:
    """Retrieve a child or root logger for rocsa_generator."""
    if name:
        return logging.getLogger(f"{LOGGER_NAME}.{name}")
    return logging.getLogger(LOGGER_NAME)


def configure_logging(level: int = logging.INFO, json_format: bool = False) -> None:
    """
    Configure standard logging handler and formatting.
    
    Call this from CLI or main application entrypoints.
    """
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(level)
    logger.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)

    if json_format:
        formatter = logging.Formatter(
            '{"time":"%(asctime)s", "name":"%(name)s", "level":"%(levelname)s", "message":"%(message)s"}'
        )
    else:
        formatter = logging.Formatter(
            "[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.propagate = False