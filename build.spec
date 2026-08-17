# -*- mode: python ; coding: utf-8 -*-

import os
import sys
from pathlib import Path

block_cipher = None

# Comprehensive hidden imports for PyInstaller standalone bundling
hidden_imports = [
    # GUI & Async
    'PySide6.QtCore',
    'PySide6.QtGui',
    'PySide6.QtWidgets',
    'qasync',
    
    # LLM & Networking
    'google.genai',
    'google.genai.types',
    'google.genai.client',
    'google.genai.models',
    'google.genai.errors',
    
    # Document parsers
    'bs4',
    'bs4.builder._htmlparser',
    'ebooklib',
    'ebooklib.epub',
    'lxml',
    'lxml.etree',
    
    # Utilities
    'pydantic',
    'dotenv',
    'tqdm',
    'PIL',
    'PIL.Image',
    
    # Internal project modules
    'common.config_loader',
    'common.logger',
    'common.paths',
    'core.event_models',
    'core.orchestrator',
    'core.session_manager',
    'domain.chunkers.base_chunker',
    'domain.chunkers.epub_dom_chunker',
    'domain.chunkers.txt_chunker',
    'domain.chunkers.plain_text_chunker',
    'domain.glossary.extractor',
    'domain.glossary.injector',
    'domain.postprocess.cleaner',
    'domain.postprocess.quality_checker',
    'domain.profiles.base_profile',
    'domain.profiles.ja_profile',
    'domain.profiles.zh_profile',
    'domain.profiles.en_profile',
    'infra.epub_io',
    'infra.gemini_client',
    'infra.key_manager',
    'infra.txt_io',
    'ui.main_window',
    'ui.settings_dialog',
    'ui.signals',
    'ui.widgets.glossary_table',
    'ui.widgets.language_toggle',
    'ui.widgets.log_view',
    'ui.widgets.preview_panel',
]

datas = [
    ('assets', 'assets'),
    ('config.json', '.')
]

# Check icon file existence
icon_file = 'assets/icons/app_icon.ico'
icon_path = icon_file if os.path.exists(icon_file) else None

a = Analysis(
    ['src/main.py'],
    pathex=['src'],
    binaries=[],
    datas=datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'unittest'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='OmniTranslatorPro',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon_path
)
