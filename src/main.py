"""
OmniTranslator Pro - Main Entry Point
Integrates PySide6 GUI with qasync asyncio event loop.
"""

import sys
import asyncio
from PySide6 import QtWidgets
import qasync
import qdarktheme

from common.logger import setup_logger
from common.paths import get_resource_path
from ui.main_window import MainWindow

logger = setup_logger("Main")

def main():
    """Initializes application and launches PySide6 event loop."""
    logger.info("Starting OmniTranslator Pro...")
    
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
    app.setStyle("Fusion")
    
    qdarktheme.setup_theme(theme="dark", custom_colors={"primary": "#8E75FF"})
    
    qss_path = get_resource_path("assets/styles/theme.qss")
    if qss_path.exists():
        with open(qss_path, "r", encoding="utf-8") as f:
            app.setStyleSheet(app.styleSheet() + "\n" + f.read())
            
    loop = qasync.QEventLoop(app)
    asyncio.set_event_loop(loop)
    
    window = MainWindow(loop=loop)
    window.show()
    
    app.lastWindowClosed.connect(loop.stop)
    
    with loop:
        loop.run_forever()

if __name__ == "__main__":
    main()
