"""
OmniTranslator Pro - Path & Resource Management
Handles PyInstaller bundling (_MEIPASS) and executable run environments.
"""

import sys
import os
from pathlib import Path

def get_resource_path(relative_path: str) -> Path:
    """
    Get absolute path to resource, works for dev and PyInstaller bundle.
    
    Args:
        relative_path: Relative path to target resource (e.g. 'assets/styles/theme.qss')
        
    Returns:
        Path object pointing to absolute resource location.
    """
    if hasattr(sys, '_MEIPASS'):
        base_path = Path(getattr(sys, '_MEIPASS'))
    else:
        base_path = Path(__file__).resolve().parent.parent.parent
    
    return base_path / relative_path

def get_app_data_path(file_name: str = "") -> Path:
    """
    Get user configuration/data persistence path.
    
    Args:
        file_name: Optional relative file path (e.g. 'config.json')
        
    Returns:
        Path object pointing to persistent user workspace directory.
    """
    if hasattr(sys, 'frozen'):
        base_path = Path(sys.executable).parent
    else:
        base_path = Path(os.getcwd())
    
    if file_name:
        return base_path / file_name
    return base_path
