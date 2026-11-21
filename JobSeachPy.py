# ------------------------------------------------------------------------------
# Copyright (c) 2026 Adrian Pascut (ESLAMERA LIMITED). All rights reserved.
#
# LICENCE NOTICE:
# Permitted ONLY for free, non-commercial personal job-search use by Private
# Individuals. Any use, copying, or modification by a Commercial Entity—or for
# non-job-search purposes—requires prior written permission from the author.
#
# BREACH PENALTIES (Liquidated Damages):
# - Commercial Entity Breach: £100,000 per breach/deployment + legal fees.
# - Private Individual Breach: £10,000 per breach + legal fees.
#
# See the root LICENSE file for full legal terms, restrictions, and disclaimers.
# ------------------------------------------------------------------------------

# JobSearchPy.py
import sys
from PySide6.QtWidgets import QApplication
from ui_panel import JobAssistantUI
from automation_worker import AutomationWorker


class JobSearchApp:

    def __init__(self):
        self.app = QApplication(sys.argv)
        self.app.setQuitOnLastWindowClosed(True)

        self.ui = JobAssistantUI()
        self.worker = None
        self.ui.start_search_requested.connect(self.handle_start_search)
        
    def run(self):
        """Launches the UI and starts the main event loop."""
        self.ui.show()
        sys.exit(self.app.exec())

    def handle_start_search(self, search_params: dict):
        """Triggered when user clicks the run/stop button in the UI."""
        # Check if a worker is already running -> If so, treat this as a "Stop Search" request
        if self.worker and self.worker.isRunning():
            self.ui.append_log("⚠️ Stop search requested by user. Signaling worker to halt...")
            self.worker.stop()  # Calls requestInterruption() on the QThread
            self.ui.btn_run.setEnabled(False)  # Temporarily disable until thread finishes cleanup
            self.ui.on_automation_finished()  # Re-enable the button and reset text
            self.worker = None
            return

        self.ui.append_log("[*] Initializing Automation Worker...")

        try:
            # 1. Instantiate worker
            worker = AutomationWorker(search_params)
        
            # 2. Check signal existence before connecting
            if not hasattr(worker, 'log_signal') or worker.log_signal is None:
                raise AttributeError("AutomationWorker is missing a valid 'log_signal' class attribute.")
            if not hasattr(worker, 'progress_signal') or worker.progress_signal is None:
                raise AttributeError("AutomationWorker is missing a valid 'progress_signal' class attribute.")
            if not hasattr(worker, 'refresh_tables_signal') or worker.refresh_tables_signal is None:
                raise AttributeError("AutomationWorker is missing a valid 'refresh_tables_signal' class attribute.")

            # 3. Connect signals safely
            worker.log_signal.connect(self.ui.append_log)
            worker.progress_signal.connect(self.ui.update_progress)
            worker.refresh_tables_signal.connect(self.ui.ai_query_panel.refresh_tables)
            # 4. Assign to instance and start thread
            self.worker = worker
            self.worker.start()
            self.worker.finished.connect(self.ui.on_automation_finished)
            self.ui.stop_search_requested.connect(self.worker.stop)
            
        except Exception as e:
            self.ui.append_log(f"❌ Failed to launch worker thread: {str(e)}")

    def handle_ai_error_prompt(self, step_name: str, error_msg: str, payload: tuple):
        choice_container, event = payload
        
        # Show modal dialog in the UI console / popup window
        # Options: [Stop Execution] | [Continue (Retry)] | [Switch to Backup Model]
        user_choice = self.show_error_dialog(step_name, error_msg)
        
        if user_choice == "stop":
            choice_container["action"] = "stop"
        elif user_choice == "continue":
            choice_container["action"] = "continue"
        elif user_choice == "switch_backup":
            choice_container["action"] = "switch_backup"
            
        event.set() # Unblock the worker thread

if __name__ == "__main__":
    main_app = JobSearchApp()
    main_app.run()