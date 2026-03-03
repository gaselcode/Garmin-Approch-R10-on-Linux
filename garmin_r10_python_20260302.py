import sys
import asyncio
import struct
import sqlite3
from datetime import datetime
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QLabel, QVBoxLayout, QWidget, QGridLayout,
    QFrame, QHBoxLayout, QLineEdit, QPushButton, QComboBox
)
from PyQt6.QtCore import Qt, pyqtSignal, QObject, QThread
from PyQt6.QtGui import QShortcut, QKeySequence
from bleak import BleakClient

# --- KONFIGURATION ---
R10_ADDRESS = "E4:7B:DD:3F:78:D7"
SERVICE_UUID = "6a4e2800-667b-11e3-949a-0800200c9a66"
NOTIFY_UUID = "6a4e2810-667b-11e3-949a-0800200c9a66"
WRITE_UUID = "6a4e2820-667b-11e3-949a-0800200c9a66"

# ==========================================
# DATENBANK LOGIK
# ==========================================
class ShotDatabase:
    def __init__(self, db_name="golf_data.db"):
        self.db_name = db_name
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_name) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS shots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME,
                    ball_speed REAL,
                    launch_angle REAL,
                    backspin REAL,
                    carry_dist REAL,
                    total_dist REAL,
                    club TEXT
                )
            """)

    def save_shot(self, m, club):
        with sqlite3.connect(self.db_name) as conn:
            conn.execute("""
                INSERT INTO shots (timestamp, ball_speed, launch_angle, backspin, carry_dist, total_dist, club)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (datetime.now(), m['ball_speed'], m['launch_angle'], m['backspin'], m['carry'], m['total'], club))

# ==========================================
# BLUETOOTH & PARSER LOGIK
# ==========================================
class R10Worker(QObject):
    data_received = pyqtSignal(dict)
    status_changed = pyqtSignal(str)  # sends status codes: "connecting", "connected", "error:..."

    def run(self):
        asyncio.run(self.main_loop())

    async def main_loop(self):
        self.status_changed.emit("connecting")
        try:
            async with BleakClient(R10_ADDRESS) as client:
                self.status_changed.emit("connected")

                # Handshake / Wake-up
                await client.write_gatt_char(WRITE_UUID, bytearray([0x01]))

                def notification_handler(sender, data):
                    if len(data) > 50:  # Ein Shot-Paket ist groß
                        parsed = self.parse_packet(data)
                        if parsed:
                            self.data_received.emit(parsed)

                await client.start_notify(NOTIFY_UUID, notification_handler)

                # Keep-alive Loop
                while True:
                    await asyncio.sleep(20)
                    if client.is_connected:
                        await client.write_gatt_char(WRITE_UUID, bytearray([0x01]))

        except Exception as e:
            self.status_changed.emit(f"error:{str(e)}")

    def parse_packet(self, data):
        try:
            return {
                'ball_speed': round(struct.unpack('<f', data[12:16])[0], 1),
                'launch_angle': round(struct.unpack('<f', data[16:20])[0], 1),
                'backspin': int(struct.unpack('<f', data[24:28])[0]),
                'carry': round(struct.unpack('<f', data[44:48])[0], 1),
                'total': round(struct.unpack('<f', data[48:52])[0], 1)
            }
        except:
            return None

# ==========================================
# GUI (INTERNATIONALISIERT, KORRIGIERT)
# ==========================================
class GolfApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.db = ShotDatabase()
        self.current_lang = "de"  # Standard: Deutsch
        self.translations = self._init_translations()
        self.init_ui()
        self.start_worker()
        self.retranslate_ui()

    def _init_translations(self):
        return {
            "de": {
                "window_title": "Garmin R10 Linux Monitor",
                "header_title": "R10 MONITOR",
                "club_placeholder": "Schläger eingeben (z.B. 'Driver')",
                "club_label": "Schläger:",
                "language_label": "Sprache:",
                "club_display": {
                    "Driver": "D)river",
                    "Holz 3": "Holz 3)",
                    "Eisen 7": "Eisen 7)",
                    "Eisen 9": "Eisen 9)",
                    "PW": "P)W",
                    "SW": "S)W",
                },
                "metrics": {
                    "total": {"name": "Gesamtstrecke", "unit": "m"},
                    "carry": {"name": "Carry-Distanz", "unit": "m"},
                    "ball_speed": {"name": "Ballgeschwindigkeit", "unit": "m/s"},
                    "launch_angle": {"name": "Abflugwinkel", "unit": "°"},
                    "backspin": {"name": "Backspin", "unit": "U/min"},
                },
                "status": {
                    "initializing": "Initialisierung...",
                    "connecting": "Suche R10...",
                    "connected": "Verbunden",
                    "error": "Verbindungsfehler: {}",
                    "shot_saved": "Schlag mit {} gespeichert!",
                },
            },
            "en": {
                "window_title": "Garmin R10 Linux Monitor",
                "header_title": "R10 MONITOR",
                "club_placeholder": "Enter club (e.g. 'Driver')",
                "club_label": "Club:",
                "language_label": "Language:",
                "club_display": {
                    "Driver": "D)river",
                    "Holz 3": "3 Wood)",
                    "Eisen 7": "7 Iron)",
                    "Eisen 9": "9 Iron)",
                    "PW": "P)W",
                    "SW": "S)W",
                },
                "metrics": {
                    "total": {"name": "Total Distance", "unit": "m"},
                    "carry": {"name": "Carry Distance", "unit": "m"},
                    "ball_speed": {"name": "Ball Speed", "unit": "m/s"},
                    "launch_angle": {"name": "Launch Angle", "unit": "°"},
                    "backspin": {"name": "Backspin", "unit": "rpm"},
                },
                "status": {
                    "initializing": "Initializing...",
                    "connecting": "Searching for R10...",
                    "connected": "Connected",
                    "error": "Connection error: {}",
                    "shot_saved": "Shot with {} saved!",
                },
            }
        }

    def tr(self, key, *args, **kwargs):
        """Holt den übersetzten String für die aktuelle Sprache."""
        keys = key.split(".")
        d = self.translations[self.current_lang]
        for k in keys:
            d = d[k]
        if args or kwargs:
            return d.format(*args, **kwargs)
        return d

    def init_ui(self):
        self.setWindowTitle(self.tr("window_title"))
        self.setGeometry(100, 100, 1000, 750)
        self.setStyleSheet("QMainWindow { background-color: #1a1a2e; }")

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)

        # ========== HEADER ==========
        header = QHBoxLayout()
        self.title_label = QLabel(self.tr("header_title"))
        self.title_label.setStyleSheet("color: white; font-size: 28px; font-weight: bold; padding: 10px;")

        # Sprachauswahl
        self.lang_combo = QComboBox()
        self.lang_combo.addItems(["Deutsch", "English"])
        self.lang_combo.currentIndexChanged.connect(self.change_language)
        self.lang_combo.setStyleSheet("background-color: #0f3460; color: white; border-radius: 10px; padding: 5px;")
        self.lang_label = QLabel(self.tr("language_label"))
        self.lang_label.setStyleSheet("color: white;")

        # Schlägerauswahl per Tastatur (freie Eingabe)
        self.club_line_edit = QLineEdit()
        self.club_line_edit.setPlaceholderText(self.tr("club_placeholder"))
        self.club_line_edit.setStyleSheet("background-color: #0f3460; color: white; border-radius: 10px; padding: 10px; font-size: 18px;")
        self.club_line_edit.setFixedWidth(200)
        self.club_line_edit.returnPressed.connect(self.update_club_from_text)

        # Buttons für schnelle Auswahl – mit Tastenkürzeln (D, 3, 7, 9, P, S)
        club_buttons_layout = QHBoxLayout()
        # Definition: (Taste, interner Schlägername)
        club_defs = [
            ("D", "Driver"),
            ("3", "Holz 3"),
            ("7", "Eisen 7"),
            ("9", "Eisen 9"),
            ("P", "PW"),
            ("S", "SW")
        ]
        self.club_buttons = []  # Liste von Tupeln (button, club_name)
        for key, club_name in club_defs:
            button = QPushButton()
            button.setStyleSheet("background-color: #0f3460; color: white; border-radius: 10px; padding: 5px; font-size: 16px;")
            button.clicked.connect(lambda _, c=club_name: self.set_club(c))
            club_buttons_layout.addWidget(button)
            self.club_buttons.append((button, club_name))
            # Tastenkürzel für diese Taste (global im Fenster)
            shortcut = QShortcut(QKeySequence(key), self)
            shortcut.activated.connect(lambda c=club_name: self.set_club(c))

        self.club_label = QLabel(self.tr("club_label"))
        self.club_label.setStyleSheet("color: white;")

        header.addWidget(self.title_label)
        header.addStretch()
        header.addWidget(self.lang_label)
        header.addWidget(self.lang_combo)
        header.addSpacing(20)
        header.addWidget(self.club_label)
        header.addWidget(self.club_line_edit)
        header.addLayout(club_buttons_layout)
        layout.addLayout(header)

        # ========== DATEN-GRID ==========
        self.grid_layout = QGridLayout()
        self.metric_widgets = {}
        self.cards = []  # Liste der Card-Widgets, um sie vor Garbage Collection zu schützen
        metrics = ["total", "carry", "ball_speed", "launch_angle", "backspin"]
        colors = ["#e94560", "#0f3460", "#0f3460", "#0f3460", "#0f3460"]

        for i, (key, color) in enumerate(zip(metrics, colors)):
            card, title_label, unit_label, value_label = self.create_card(color)
            self.cards.append(card)
            self.metric_widgets[key] = {
                "title": title_label,
                "unit": unit_label,
                "value": value_label
            }
            self.grid_layout.addWidget(card, i // 2, i % 2)

        layout.addLayout(self.grid_layout)

        # ========== STATUSLEISTE ==========
        self.status_bar = QLabel(self.tr("status.initializing"))
        self.status_bar.setStyleSheet("color: #888; padding: 10px;")
        layout.addWidget(self.status_bar)

    def create_card(self, color):
        """Erzeugt eine Karte und gibt (card, title_label, unit_label, value_label) zurück."""
        card = QFrame()
        card.setStyleSheet(f"background-color: #16213e; border: 2px solid {color}; border-radius: 15px;")
        l = QVBoxLayout(card)

        title = QLabel()
        title.setStyleSheet("color: #888; font-size: 16px; border: none;")
        value = QLabel("0.0")
        value.setStyleSheet("color: white; font-size: 48px; font-weight: bold; border: none;")
        unit = QLabel()
        unit.setStyleSheet(f"color: {color}; font-size: 18px; border: none;")

        l.addWidget(title, alignment=Qt.AlignmentFlag.AlignCenter)
        l.addWidget(value, alignment=Qt.AlignmentFlag.AlignCenter)
        l.addWidget(unit, alignment=Qt.AlignmentFlag.AlignCenter)

        return card, title, unit, value

    def change_language(self, index):
        """Wird aufgerufen, wenn die Sprache über die ComboBox geändert wird."""
        self.current_lang = "de" if index == 0 else "en"
        self.retranslate_ui()

    def retranslate_ui(self):
        """Aktualisiert alle Texte basierend auf der aktuellen Sprache."""
        # Fenstertitel
        self.setWindowTitle(self.tr("window_title"))

        # Header
        self.title_label.setText(self.tr("header_title"))
        self.lang_label.setText(self.tr("language_label"))
        self.club_label.setText(self.tr("club_label"))
        self.club_line_edit.setPlaceholderText(self.tr("club_placeholder"))

        # Club-Buttons
        for button, club_name in self.club_buttons:
            button.setText(self.tr(f"club_display.{club_name}"))

        # Metrik-Karten
        for key, widgets in self.metric_widgets.items():
            metric = self.tr(f"metrics.{key}")
            widgets["title"].setText(metric["name"])
            widgets["unit"].setText(metric["unit"])

        # Status-Bar (falls gerade kein aktiver Status vom Worker, setze initial)
        self.status_bar.setText(self.tr("status.initializing"))

    def set_club(self, club_name):
        """Setzt den ausgewählten Schläger und aktualisiert das Textfeld."""
        self.club_line_edit.setText(club_name)
        self.current_club = club_name

    def update_club_from_text(self):
        """Aktualisiert den ausgewählten Schläger basierend auf der Tastatureingabe."""
        self.current_club = self.club_line_edit.text()

    def start_worker(self):
        self.thread = QThread()
        self.worker = R10Worker()
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.data_received.connect(self.process_shot)
        self.worker.status_changed.connect(self.handle_status)
        self.thread.start()

    def handle_status(self, code):
        """Verarbeitet Status-Codes vom Worker und zeigt übersetzte Meldungen an."""
        if code == "connecting":
            self.status_bar.setText(self.tr("status.connecting"))
        elif code == "connected":
            self.status_bar.setText(self.tr("status.connected"))
        elif code.startswith("error:"):
            error_msg = code[6:]  # "error:" abschneiden
            self.status_bar.setText(self.tr("status.error", error_msg))
        else:
            # Fallback für unbekannte Codes
            self.status_bar.setText(code)

    def process_shot(self, data):
        # 1. Update UI
        for key, value in data.items():
            if key in self.metric_widgets:
                self.metric_widgets[key]["value"].setText(str(value))

        # 2. Save to DB
        club = self.current_club if hasattr(self, 'current_club') else "Unbekannt"
        self.db.save_shot(data, club)

        # 3. Statusmeldung (übersetzt)
        msg = self.tr("status.shot_saved", club)
        self.status_bar.setText(msg)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = GolfApp()
    window.show()
    sys.exit(app.exec())