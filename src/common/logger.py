"""
OmniTranslator Pro - Logging System Setup
"""

import logging
import sys
from pathlib import Path
from common.paths import get_app_data_path

def setup_logger(name: str = "OmniTranslator") -> logging.Logger:
    """Initializes and returns a configured logger instance."""
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
        
    logger.setLevel(logging.DEBUG)
    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(formatter)
    logger.addHandler(ch)
    
    log_dir = get_app_data_path("logs")
    log_dir.mkdir(exist_ok=True)
    fh = logging.FileHandler(log_dir / "omni_translator.log", encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(formatter)
    logger.addHandler(fh)
    
    return logger
