import sys

from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QApplication,
    QMainWindow,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


class WorkerThread(QThread):
    log_signal = pyqtSignal(str)

    def run(self):
        self.log_signal.emit("--- SUCCESS: Worker thread `run` method was executed. ---")
        import time
        time.sleep(2)
        self.log_signal.emit("--- SUCCESS: Worker thread finished. ---")

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("QThread Test")
        self.log_box = QTextEdit()
        self.start_button = QPushButton("Start Thread")
        self.start_button.clicked.connect(self.start_worker)

        layout = QVBoxLayout()
        layout.addWidget(self.log_box)
        layout.addWidget(self.start_button)

        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)

        self.log_box.append("Application started. Click the button to test QThread.")

    def start_worker(self):
        self.log_box.append("`start_worker` called. Creating thread...")
        self.worker_thread = WorkerThread()
        self.worker_thread.log_signal.connect(self.log_box.append)
        self.worker_thread.finished.connect(lambda: self.log_box.append("`finished` signal received."))
        self.worker_thread.start()
        self.log_box.append("`thread.start()` has been called. Waiting for thread to run...")

    def closeEvent(self, event):
        if hasattr(self, 'worker_thread') and self.worker_thread.isRunning():
            self.log_box.append("Window closing. Waiting for thread to finish...")
            self.worker_thread.wait()
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
