import logging
from typing import Optional


def configure_logger(name: str, log_file: str = "app.log", level: int = logging.INFO) -> logging.Logger:
    """
    Configures and returns a logger for file output

    Args:
        name (str): Name of the logger (usually the module/class name).
        log_file (str): Path to the log file.
        level (int): Logging level (e.g., logging.INFO, logging.DEBUG).

    Returns:
        logging.Logger: Configured logger instance for file output.
    """
    logger = logging.getLogger(name)

    # Avoid duplicate handlers, and remove existing ones if any
    if logger.hasHandlers():
        logger.handlers.clear()

    file_handler = logging.FileHandler(log_file)

    file_handler.setFormatter(logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    ))

    # Add handler to logger
    logger.addHandler(file_handler)
    logger.setLevel(level)

    return logger


def configure_movie_logger(name: str, log_file: str = "app.log", level: int = logging.INFO) -> logging.Logger:
    """
    Configures and returns a logger for file output

    Args:
        name (str): Name of the logger (usually the module/class name).
        log_file (str): Path to the log file.
        level (int): Logging level (e.g., logging.INFO, logging.DEBUG).

    Returns:
        logging.Logger: Configured logger instance for file output.
    """
    logger = logging.getLogger(name)

    # Avoid duplicate handlers, and remove existing ones if any
    if logger.hasHandlers():
        logger.handlers.clear()

    file_handler = logging.FileHandler(log_file, encoding="utf-8")

    file_handler.setFormatter(logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    ))

    # Add handler to logger
    logger.addHandler(file_handler)
    logger.setLevel(level)

    return logger
