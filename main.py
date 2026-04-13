import sys
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt
from ui.modals import StartupModelModal
from ui.main_window import CodeGodEnterprise
from core.llm_engine import LlamaInferenceCore
from core.sre import logger

def main():
    if hasattr(Qt, 'AA_EnableHighDpiScaling'): 
        QApplication.setAttribute(Qt.ApplicationAttribute.AA_EnableHighDpiScaling, True)
    
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    
    # 1. Startup Modal
    modal = StartupModelModal()
    if modal.exec() != StartupModelModal.DialogCode.Accepted:
        logger.info("User cancelled boot process.")
        sys.exit(0)
        
    model_path = modal.selected_model_path
    
    # 2. Boot Engine
    engine = LlamaInferenceCore.get_instance()
    if not engine.load_model(model_path):
        from PyQt6.QtWidgets import QMessageBox
        QMessageBox.critical(None, "Boot Error", "LLM Engine initialization failed. Halting system.")
        sys.exit(1)
        
    # 3. Main Enterprise Dashboard
    ex = CodeGodEnterprise()
    ex.show()
    sys.exit(app.exec())

if __name__ == '__main__':
    main()