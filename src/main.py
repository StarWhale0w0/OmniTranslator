"""
OmniTranslator Pro - Main Entry Point
Integrates PySide6 GUI with qasync asyncio event loop.
"""

import sys
import asyncio
import traceback
from pathlib import Path

from PySide6 import QtWidgets
import qasync

from common.logger import setup_logger
from common.paths import get_resource_path
from ui.main_window import MainWindow

logger = setup_logger("Main")


def main() -> None:
    """Initializes PySide6 application, loads QSS, and launches qasync event loop."""
    try:
        logger.info("Initializing OmniTranslator Pro...")

        # 1. QApplication instance
        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
        app.setStyle("Fusion")

        # 2. Load QSS Stylesheet
        try:
            qss_path = get_resource_path("assets/styles/theme.qss")
            if qss_path and qss_path.exists():
                with open(qss_path, "r", encoding="utf-8") as f:
                    app.setStyleSheet(f.read())
                    logger.info(f"Theme stylesheet loaded successfully from: {qss_path}")
            else:
                logger.warning(f"Theme QSS file not found at '{qss_path}'. Running with default Fusion style.")
        except Exception as e_qss:
            logger.warning(f"Failed to load theme QSS stylesheet: {e_qss}")

        # 3. Setup qasync Event Loop
        loop = qasync.QEventLoop(app)
        asyncio.set_event_loop(loop)

        # 4. Instantiate and Show Main Window
        window = MainWindow(loop=loop)
        window.show()

        # Ensure loop stops when last window closes
        app.lastWindowClosed.connect(loop.stop)

        # 5. Run Event Loop
        logger.info("OmniTranslator Pro UI rendered. Entering event loop...")
        with loop:
            loop.run_forever()

    except Exception as e:
        logger.critical(f"Fatal unhandled exception in main entrypoint: {e}", exc_info=True)
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
