from PyQt6.QtWidgets import QSplashScreen, QProgressBar, QLabel, QApplication
from PyQt6.QtGui import QPixmap, QPainter, QLinearGradient, QColor, QFont
from PyQt6.QtCore import Qt

class SplashScreen(QSplashScreen):
    def __init__(self):
        # Create a nice dark splash image programmatically
        pixmap = QPixmap(600, 350)
        pixmap.fill(QColor("#1e1e1e"))
        
        painter = QPainter(pixmap)
        
        # Gradient Background
        gradient = QLinearGradient(0, 0, 600, 350)
        gradient.setColorAt(0, QColor("#2b2b2b"))
        gradient.setColorAt(1, QColor("#1e1e1e"))
        painter.fillRect(pixmap.rect(), gradient)
        
        # Draw Logo/Title
        painter.setPen(QColor("#ffffff"))
        painter.setFont(QFont("Segoe UI", 32, QFont.Weight.Bold))
        painter.drawText(pixmap.rect().adjusted(0, -50, 0, 0), Qt.AlignmentFlag.AlignCenter, "PhotoSortX AI")
        
        painter.setPen(QColor("#007acc"))
        painter.setFont(QFont("Segoe UI", 14))
        painter.drawText(pixmap.rect().adjusted(0, 40, 0, 0), Qt.AlignmentFlag.AlignCenter, "Event-Based Intelligent Sorter")
        
        painter.end()
        
        super().__init__(pixmap)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint)
        
        # Progress Bar
        self.progress = QProgressBar(self)
        self.progress.setGeometry(50, 280, 500, 6)
        self.progress.setStyleSheet("""
            QProgressBar { border: none; background-color: #333; border-radius: 3px; }
            QProgressBar::chunk { background-color: #007acc; border-radius: 3px; }
        """)
        self.progress.setTextVisible(False)
        
        # Status Label
        self.status_label = QLabel("Initializing...", self)
        self.status_label.setGeometry(50, 250, 500, 20)
        self.status_label.setStyleSheet("color: #888; font-size: 12px;")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

    def show_message(self, msg, progress):
        self.status_label.setText(msg)
        self.progress.setValue(progress)
        QApplication.processEvents()
