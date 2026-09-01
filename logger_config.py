import logging
import sys
from typing import Optional


def configure_logger(
    name: str,
    log_file: str = "app.log",
    level: int = logging.INFO,
    encoding: Optional[str] = None,
) -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.propagate = False

    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    handler_keys = {(type(h), getattr(h, "baseFilename", None), getattr(h, "stream", None)) for h in logger.handlers}

    file_handler = logging.FileHandler(log_file, encoding=encoding or "utf-8")
    file_handler.setFormatter(formatter)
    file_key = (type(file_handler), file_handler.baseFilename, None)
    if file_key not in handler_keys:
        logger.addHandler(file_handler)

    has_stderr = any(isinstance(h, logging.StreamHandler) and getattr(h, "stream", None) is sys.stderr for h in logger.handlers)
    if not has_stderr:
        stream_handler = logging.StreamHandler(sys.stderr)
        stream_handler.setFormatter(formatter)
        logger.addHandler(stream_handler)

    return logger


def configure_movie_logger(name: str, log_file: str = "app.log", level: int = logging.INFO) -> logging.Logger:
    return configure_logger(name, log_file=log_file, level=level, encoding="utf-8")
