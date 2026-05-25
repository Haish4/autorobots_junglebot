#!/usr/bin/env python3
"""
JungleBot System Monitor
Robot Operations Dashboard — PyQt5 / ROS Interface
"""

import sys
import time
import rospy
from std_msgs.msg import String
from sensor_msgs.msg import Image
from cv_bridge import CvBridge
import cv2

from PyQt5.QtCore import QTimer, Qt, QThread, pyqtSignal, QPropertyAnimation, QEasingCurve
from PyQt5.QtGui import QImage, QPixmap, QFont, QFontDatabase, QColor, QPainter, QPen, QBrush, QPalette
from PyQt5.QtWidgets import (
    QApplication, QWidget, QLabel, QVBoxLayout, QHBoxLayout,
    QFrame, QSizePolicy, QGridLayout, QSpacerItem
)

# ─────────────────────────────────────────────
#  DESIGN TOKENS
# ─────────────────────────────────────────────
PALETTE = {
    "bg_deep":       "#0a0c0f",
    "bg_panel":      "#10141a",
    "bg_card":       "#151b24",
    "bg_input":      "#1a2030",
    "border":        "#1e2a3a",
    "border_accent": "#1e3a5f",
    "accent_blue":   "#2d7dd2",
    "accent_green":  "#1fa363",
    "accent_amber":  "#c8831a",
    "accent_red":    "#c0392b",
    "text_primary":  "#dce8f5",
    "text_secondary":"#6a8099",
    "text_muted":    "#3d5166",
    "rule":          "#1e2a3a",
}

MONO = "Courier New"
SANS = "Arial"

GLOBAL_QSS = f"""
QWidget {{
    background-color: {PALETTE['bg_deep']};
    color: {PALETTE['text_primary']};
    font-family: {SANS};
    font-size: 13px;
}}
QFrame[class="panel"] {{
    background-color: {PALETTE['bg_panel']};
    border: 1px solid {PALETTE['border']};
    border-radius: 4px;
}}
QFrame[class="card"] {{
    background-color: {PALETTE['bg_card']};
    border: 1px solid {PALETTE['border']};
    border-radius: 3px;
}}
QLabel[class="section-title"] {{
    color: {PALETTE['text_secondary']};
    font-size: 10px;
    font-family: {MONO};
    letter-spacing: 2px;
    text-transform: uppercase;
    padding: 0px;
    background: transparent;
    border: none;
}}
QLabel[class="status-ok"] {{
    color: {PALETTE['accent_green']};
    font-family: {MONO};
    font-size: 11px;
    background: transparent;
    border: none;
}}
QLabel[class="status-warn"] {{
    color: {PALETTE['accent_amber']};
    font-family: {MONO};
    font-size: 11px;
    background: transparent;
    border: none;
}}
QLabel[class="status-error"] {{
    color: {PALETTE['accent_red']};
    font-family: {MONO};
    font-size: 11px;
    background: transparent;
    border: none;
}}
QLabel[class="data-value"] {{
    color: {PALETTE['text_primary']};
    font-family: {MONO};
    font-size: 13px;
    background: transparent;
    border: none;
}}
"""


# ─────────────────────────────────────────────
#  REUSABLE COMPONENTS
# ─────────────────────────────────────────────

def make_separator():
    line = QFrame()
    line.setFrameShape(QFrame.HLine)
    line.setStyleSheet(f"border: none; border-top: 1px solid {PALETTE['border']}; margin: 4px 0px;")
    return line


def make_section_title(text):
    lbl = QLabel(text.upper())
    lbl.setProperty("class", "section-title")
    lbl.setStyleSheet(f"""
        color: {PALETTE['text_secondary']};
        font-size: 10px;
        font-family: {MONO};
        letter-spacing: 2px;
        padding: 0px;
        background: transparent;
        border: none;
    """)
    return lbl


class StatusIndicator(QWidget):
    """A small colored dot + label for system status."""
    STATUS_COLORS = {
        "ok":      PALETTE["accent_green"],
        "warn":    PALETTE["accent_amber"],
        "error":   PALETTE["accent_red"],
        "idle":    PALETTE["text_muted"],
    }

    def __init__(self, label_text, status="idle", parent=None):
        super().__init__(parent)
        self._status = status
        self.setFixedHeight(22)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self._dot = QLabel()
        self._dot.setFixedSize(8, 8)
        self._update_dot()
        layout.addWidget(self._dot, 0, Qt.AlignVCenter)

        self._text = QLabel(label_text)
        self._text.setStyleSheet(f"color: {PALETTE['text_secondary']}; font-size: 11px; font-family: {MONO}; background: transparent; border: none;")
        layout.addWidget(self._text, 0, Qt.AlignVCenter)
        layout.addStretch()

    def _update_dot(self):
        color = self.STATUS_COLORS.get(self._status, PALETTE["text_muted"])
        self._dot.setStyleSheet(f"""
            background-color: {color};
            border-radius: 4px;
        """)

    def set_status(self, status):
        self._status = status
        self._update_dot()


class InfoRow(QWidget):
    """Key / value pair row for telemetry display."""
    def __init__(self, key, value="—", parent=None):
        super().__init__(parent)
        self.setFixedHeight(28)
        self.setStyleSheet("background: transparent;")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        key_lbl = QLabel(key)
        key_lbl.setStyleSheet(f"color: {PALETTE['text_muted']}; font-size: 11px; font-family: {MONO}; background: transparent; border: none;")
        key_lbl.setFixedWidth(140)

        self._val = QLabel(value)
        self._val.setStyleSheet(f"color: {PALETTE['text_primary']}; font-size: 11px; font-family: {MONO}; background: transparent; border: none;")

        layout.addWidget(key_lbl)
        layout.addWidget(self._val)
        layout.addStretch()

    def set_value(self, value):
        self._val.setText(value)


class SpeechBox(QFrame):
    """Styled text display box for speech / AI reply text streams."""
    def __init__(self, accent_color, placeholder, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"""
            QFrame {{
                background-color: {PALETTE['bg_input']};
                border: 1px solid {PALETTE['border']};
                border-left: 3px solid {accent_color};
                border-radius: 3px;
                padding: 0px;
            }}
        """)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)

        self._label = QLabel(placeholder)
        self._label.setWordWrap(True)
        self._label.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self._label.setStyleSheet(f"""
            color: {PALETTE['text_secondary']};
            font-size: 13px;
            font-family: {SANS};
            line-height: 1.6;
            background: transparent;
            border: none;
        """)
        layout.addWidget(self._label)

    def set_text(self, text):
        self._label.setText(text)
        self._label.setStyleSheet(f"""
            color: {PALETTE['text_primary']};
            font-size: 13px;
            font-family: {SANS};
            line-height: 1.6;
            background: transparent;
            border: none;
        """)


class TopBar(QFrame):
    """Top header bar with system identity and live clock."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(54)
        self.setStyleSheet(f"""
            QFrame {{
                background-color: {PALETTE['bg_panel']};
                border: none;
                border-bottom: 1px solid {PALETTE['border']};
            }}
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 0, 20, 0)

        # Left: System identity
        id_layout = QVBoxLayout()
        id_layout.setSpacing(0)

        title = QLabel("JUNGLEBOT")
        title.setStyleSheet(f"""
            color: {PALETTE['text_primary']};
            font-size: 16px;
            font-family: {MONO};
            font-weight: bold;
            letter-spacing: 4px;
            background: transparent;
            border: none;
        """)

        subtitle = QLabel("SYSTEM OPERATIONS MONITOR  //  ROS INTERFACE")
        subtitle.setStyleSheet(f"""
            color: {PALETTE['text_muted']};
            font-size: 9px;
            font-family: {MONO};
            letter-spacing: 2px;
            background: transparent;
            border: none;
        """)

        id_layout.addWidget(title)
        id_layout.addWidget(subtitle)
        layout.addLayout(id_layout)
        layout.addStretch()

        # Right: Clock + session label
        right_layout = QVBoxLayout()
        right_layout.setSpacing(0)
        right_layout.setAlignment(Qt.AlignRight)

        self._clock = QLabel()
        self._clock.setAlignment(Qt.AlignRight)
        self._clock.setStyleSheet(f"""
            color: {PALETTE['text_primary']};
            font-size: 16px;
            font-family: {MONO};
            background: transparent;
            border: none;
        """)

        self._date = QLabel()
        self._date.setAlignment(Qt.AlignRight)
        self._date.setStyleSheet(f"""
            color: {PALETTE['text_muted']};
            font-size: 9px;
            font-family: {MONO};
            letter-spacing: 1px;
            background: transparent;
            border: none;
        """)

        right_layout.addWidget(self._clock)
        right_layout.addWidget(self._date)
        layout.addLayout(right_layout)

        self._tick()
        timer = QTimer(self)
        timer.timeout.connect(self._tick)
        timer.start(1000)

    def _tick(self):
        now = time.localtime()
        self._clock.setText(time.strftime("%H:%M:%S", now))
        self._date.setText(time.strftime("%A  %d %B %Y", now).upper())


class CameraPanel(QFrame):
    """Camera feed display with overlay label."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"""
            QFrame {{
                background-color: #000000;
                border: 1px solid {PALETTE['border']};
                border-radius: 3px;
            }}
        """)
        self.setMinimumSize(480, 320)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)

        # Both widgets live in the layout from the start
        self._img_label = QLabel()
        self._img_label.setAlignment(Qt.AlignCenter)
        self._img_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._img_label.setStyleSheet("background: transparent; border: none;")
        self._img_label.hide()  # hidden until first frame

        self._placeholder = QLabel("NO SIGNAL")
        self._placeholder.setAlignment(Qt.AlignCenter)
        self._placeholder.setStyleSheet(f"""
            color: {PALETTE['text_muted']};
            font-family: {MONO};
            font-size: 12px;
            letter-spacing: 4px;
            background: transparent;
            border: none;
        """)

        self._layout.addWidget(self._placeholder)
        self._layout.addWidget(self._img_label)

    def update_frame(self, pixmap):
        if self._placeholder.isVisible():
            self._placeholder.hide()
            self._img_label.show()

        # Use the panel's own size, not the label's (label may report 0 before paint)
        scaled = pixmap.scaled(
            self.width(), self.height(),
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation
        )
        self._img_label.setPixmap(scaled)


# ─────────────────────────────────────────────
#  MAIN DASHBOARD WINDOW
# ─────────────────────────────────────────────

class RobotDashboard(QWidget):

    def __init__(self):
        super().__init__()

        # ROS init
        rospy.init_node("robot_dashboard_gui", anonymous=True)
        self.bridge = CvBridge()
        self._last_msg_time = {"camera": None, "speech": None, "reply": None}

        # Window
        self.setWindowTitle("JungleBot — System Monitor")
        self.resize(1200, 720)
        self.setMinimumSize(960, 600)
        self.setStyleSheet(GLOBAL_QSS)

        # Root layout
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Top bar
        self._topbar = TopBar()
        root.addWidget(self._topbar)

        # Body
        body = QHBoxLayout()
        body.setContentsMargins(16, 16, 16, 16)
        body.setSpacing(14)
        root.addLayout(body)

        # ── LEFT COLUMN ──────────────────────────────
        left_col = QVBoxLayout()
        left_col.setSpacing(12)
        body.addLayout(left_col, stretch=3)

        # Camera section
        cam_header = QHBoxLayout()
        cam_header.addWidget(make_section_title("Live Camera Feed"))
        cam_header.addStretch()
        self._cam_status = StatusIndicator("NO SIGNAL", status="idle")
        cam_header.addWidget(self._cam_status)
        left_col.addLayout(cam_header)

        self._camera_panel = CameraPanel()
        left_col.addWidget(self._camera_panel)

        # AI snapshot section
        left_col.addSpacing(4)
        left_col.addWidget(make_section_title("Last Frame Dispatched to Vision Analyser"))

        self._ai_label = QLabel("AWAITING CAPTURE")
        self._ai_label.setAlignment(Qt.AlignCenter)
        self._ai_label.setFixedHeight(120)
        self._ai_label.setStyleSheet(f"""
            background-color: {PALETTE['bg_card']};
            border: 1px dashed {PALETTE['border_accent']};
            border-radius: 3px;
            color: {PALETTE['text_muted']};
            font-family: {MONO};
            font-size: 10px;
            letter-spacing: 3px;
        """)
        left_col.addWidget(self._ai_label)

        # ── RIGHT COLUMN ─────────────────────────────
        right_col = QVBoxLayout()
        right_col.setSpacing(12)
        body.addLayout(right_col, stretch=2)

        # System status panel
        status_frame = QFrame()
        status_frame.setStyleSheet(f"""
            QFrame {{
                background-color: {PALETTE['bg_panel']};
                border: 1px solid {PALETTE['border']};
                border-radius: 4px;
                padding: 4px;
            }}
        """)
        status_inner = QVBoxLayout(status_frame)
        status_inner.setContentsMargins(14, 12, 14, 12)
        status_inner.setSpacing(6)

        status_inner.addWidget(make_section_title("Node Status"))
        status_inner.addSpacing(4)

        self._node_cam   = StatusIndicator("usb_cam / image_raw",  status="idle")
        self._node_sr    = StatusIndicator("google_sr (speech rec)", status="idle")
        self._node_tts   = StatusIndicator("gtts_input (TTS bridge)", status="idle")

        status_inner.addWidget(self._node_cam)
        status_inner.addWidget(self._node_sr)
        status_inner.addWidget(self._node_tts)
        status_inner.addSpacing(8)
        status_inner.addWidget(make_separator())
        status_inner.addSpacing(6)

        status_inner.addWidget(make_section_title("Session Telemetry"))
        status_inner.addSpacing(4)

        self._row_uptime     = InfoRow("UPTIME")
        self._row_frames     = InfoRow("FRAMES RECV")
        self._row_utterances = InfoRow("UTTERANCES")
        self._row_replies    = InfoRow("REPLIES")

        for row in [self._row_uptime, self._row_frames, self._row_utterances, self._row_replies]:
            status_inner.addWidget(row)

        right_col.addWidget(status_frame)

        # Speech input panel
        right_col.addWidget(make_section_title("Operator Input  —  Speech Recognition"))
        self._speech_box = SpeechBox(
            accent_color=PALETTE["accent_blue"],
            placeholder="Listening for operator input..."
        )
        self._speech_box.setMinimumHeight(110)
        right_col.addWidget(self._speech_box)

        # Bot reply panel
        right_col.addWidget(make_section_title("System Response  —  JungleBot"))
        self._reply_box = SpeechBox(
            accent_color=PALETTE["accent_green"],
            placeholder="Awaiting bridge node..."
        )
        self._reply_box.setMinimumHeight(110)
        right_col.addWidget(self._reply_box)

        right_col.addStretch()

        # ── ROS SUBSCRIBERS ──────────────────────────
        rospy.Subscriber("/usb_cam/image_raw", Image, self.camera_callback)
        rospy.Subscriber("/google_sr",         String, self.user_speech_callback)
        rospy.Subscriber("/gtts_input",        String, self.bot_reply_callback)

        # ── TELEMETRY COUNTERS ───────────────────────
        self._start_time   = time.time()
        self._frame_count  = 0
        self._utterance_count = 0
        self._reply_count  = 0

        # ── UPDATE TIMERS ────────────────────────────
        self._ros_timer = QTimer()
        self._ros_timer.timeout.connect(self._check_ros)
        self._ros_timer.start(10)

        self._telemetry_timer = QTimer()
        self._telemetry_timer.timeout.connect(self._update_telemetry)
        self._telemetry_timer.start(1000)

        # Watchdog: mark node status stale if no msg received
        self._watchdog_timer = QTimer()
        self._watchdog_timer.timeout.connect(self._watchdog)
        self._watchdog_timer.start(3000)

    # ─── ROS CALLBACKS ────────────────────────────

    def camera_callback(self, data):
        try:
            cv_img = self.bridge.imgmsg_to_cv2(data, "rgb8")
            h, w, ch = cv_img.shape
            qt_img = QImage(cv_img.data, w, h, ch * w, QImage.Format_RGB888)
            pixmap = QPixmap.fromImage(qt_img)
            self._camera_panel.update_frame(pixmap)
            self._last_msg_time["camera"] = time.time()
            self._frame_count += 1
            self._node_cam.set_status("ok")
        except Exception as e:
            rospy.logerr(f"[Dashboard] Camera frame error: {e}")

    def user_speech_callback(self, msg):
        self._speech_box.set_text(msg.data)
        self._last_msg_time["speech"] = time.time()
        self._utterance_count += 1
        self._node_sr.set_status("ok")

    def bot_reply_callback(self, msg):
        self._reply_box.set_text(msg.data)
        self._last_msg_time["reply"] = time.time()
        self._reply_count += 1
        self._node_tts.set_status("ok")

    # ─── INTERNAL UPDATES ─────────────────────────

    def _check_ros(self):
        if rospy.is_shutdown():
            self.close()

    def _update_telemetry(self):
        elapsed = int(time.time() - self._start_time)
        h, m, s = elapsed // 3600, (elapsed % 3600) // 60, elapsed % 60
        self._row_uptime.set_value(f"{h:02d}:{m:02d}:{s:02d}")
        self._row_frames.set_value(str(self._frame_count))
        self._row_utterances.set_value(str(self._utterance_count))
        self._row_replies.set_value(str(self._reply_count))

    def _watchdog(self):
        now = time.time()
        threshold = 5.0  # seconds before marking stale

        if self._last_msg_time["camera"] and (now - self._last_msg_time["camera"]) > threshold:
            self._node_cam.set_status("warn")
        elif not self._last_msg_time["camera"]:
            self._node_cam.set_status("idle")

        if self._last_msg_time["speech"] and (now - self._last_msg_time["speech"]) > threshold:
            self._node_sr.set_status("warn")
        elif not self._last_msg_time["speech"]:
            self._node_sr.set_status("idle")

        if self._last_msg_time["reply"] and (now - self._last_msg_time["reply"]) > threshold:
            self._node_tts.set_status("warn")
        elif not self._last_msg_time["reply"]:
            self._node_tts.set_status("idle")


# ─────────────────────────────────────────────
#  ENTRY POINT
# ─────────────────────────────────────────────

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    # Apply dark palette for native widgets
    palette = QPalette()
    palette.setColor(QPalette.Window,          QColor(PALETTE["bg_deep"]))
    palette.setColor(QPalette.WindowText,      QColor(PALETTE["text_primary"]))
    palette.setColor(QPalette.Base,            QColor(PALETTE["bg_panel"]))
    palette.setColor(QPalette.AlternateBase,   QColor(PALETTE["bg_card"]))
    palette.setColor(QPalette.Text,            QColor(PALETTE["text_primary"]))
    palette.setColor(QPalette.Button,          QColor(PALETTE["bg_panel"]))
    palette.setColor(QPalette.ButtonText,      QColor(PALETTE["text_primary"]))
    palette.setColor(QPalette.Highlight,       QColor(PALETTE["accent_blue"]))
    palette.setColor(QPalette.HighlightedText, QColor("#ffffff"))
    app.setPalette(palette)

    dashboard = RobotDashboard()
    dashboard.show()
    sys.exit(app.exec_())