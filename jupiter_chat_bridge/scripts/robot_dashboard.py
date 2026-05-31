#!/usr/bin/env python3
"""
JungleBot Operations Center
System Monitor / ROS Interface — PyQt5
"""

import sys
import time
import psutil

try:
    import rospy
    from std_msgs.msg import String
    from sensor_msgs.msg import Image
    from cv_bridge import CvBridge
    ROS_AVAILABLE = True
except ImportError:
    ROS_AVAILABLE = False

from PyQt5.QtCore import QTimer, Qt
from PyQt5.QtGui import QImage, QPixmap, QColor, QPalette, QTextCursor, QTextCharFormat
from PyQt5.QtWidgets import (
    QApplication, QWidget, QLabel, QVBoxLayout, QHBoxLayout,
    QFrame, QSizePolicy, QScrollArea, QTextEdit, QCheckBox
)

# ─────────────────────────────────────────
#  PALETTE
# ─────────────────────────────────────────
P = {
    "bg_root":   "#080b0f",
    "bg_panel":  "#0d1117",
    "bg_card":   "#111820",
    "border":    "#1a2535",
    "border_hi": "#1e3a5f",
    "green":     "#1fa363",
    "green_dim": "#0f5233",
    "blue":      "#2d7dd2",
    "blue_dim":  "#163d6a",
    "amber":     "#c8831a",
    "amber_dim": "#5c3c0a",
    "red":       "#c0392b",
    "red_dim":   "#5c1c16",
    "dim":       "#1e2e3e",
    "cyan":      "#17b8c8",
    "purple":    "#7c5cbf",
    "text":      "#d0e4f4",
    "text_sec":  "#5a7a94",
    "text_dim":  "#2e4155",
}

MONO = "'Courier New', 'Consolas', monospace"

GLOBAL_QSS = f"""
QWidget {{
    background-color: {P['bg_root']};
    color: {P['text']};
    font-family: 'Trebuchet MS', 'Verdana', sans-serif;
    font-size: 12px;
}}
QScrollBar:vertical {{
    background: {P['bg_panel']};
    width: 5px;
    margin: 0;
    border: none;
}}
QScrollBar::handle:vertical {{
    background: {P['border_hi']};
    border-radius: 2px;
    min-height: 20px;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar:horizontal {{ height: 0; }}
"""

CAM_W, CAM_H = 640, 480
SNAP_W = 320   # half the cam width — sits beside it
SNAP_H = 480   # same height so the row is uniform


# ─────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────
def hsep():
    l = QFrame()
    l.setFrameShape(QFrame.HLine)
    l.setStyleSheet(f"border:none; border-top:1px solid {P['border']}; margin:2px 0;")
    return l

def sec_lbl(txt):
    l = QLabel(txt.upper())
    l.setStyleSheet(
        f"color:{P['text_dim']}; font-family:{MONO}; font-size:9px; "
        f"letter-spacing:2.5px; background:transparent; border:none; padding-bottom:2px;"
    )
    return l


# ─────────────────────────────────────────
#  TOP BAR
# ─────────────────────────────────────────
class TopBar(QFrame):
    def __init__(self):
        super().__init__()
        self.setFixedHeight(50)
        self.setStyleSheet(
            f"QFrame {{ background:{P['bg_panel']}; border:none; border-bottom:1px solid {P['border']}; }}"
        )
        row = QHBoxLayout(self)
        row.setContentsMargins(18, 0, 18, 0)

        lv = QVBoxLayout(); lv.setSpacing(1)
        t = QLabel("JUNGLEBOT")
        t.setStyleSheet(
            f"color:{P['text']}; font-family:{MONO}; font-size:20px; font-weight:bold; "
            f"letter-spacing:5px; background:transparent; border:none;"
        )
        s = QLabel("SYSTEM MONITOR")
        s.setStyleSheet(
            f"color:{P['text_dim']}; font-family:{MONO}; font-size:8px; "
            f"letter-spacing:2px; background:transparent; border:none;"
        )
        lv.addWidget(t); lv.addWidget(s)
        row.addLayout(lv)
        row.addStretch()

        rv = QVBoxLayout(); rv.setSpacing(1)
        rv.setAlignment(Qt.AlignRight)
        self._clk = QLabel()
        self._clk.setAlignment(Qt.AlignRight)
        self._clk.setStyleSheet(
            f"color:{P['text']}; font-family:{MONO}; font-size:17px; background:transparent; border:none;"
        )
        self._dt = QLabel()
        self._dt.setAlignment(Qt.AlignRight)
        self._dt.setStyleSheet(
            f"color:{P['text_dim']}; font-family:{MONO}; font-size:8px; "
            f"letter-spacing:1px; background:transparent; border:none;"
        )
        rv.addWidget(self._clk); rv.addWidget(self._dt)
        row.addLayout(rv)

        self._tick()
        t2 = QTimer(self); t2.timeout.connect(self._tick); t2.start(1000)

    def _tick(self):
        n = time.localtime()
        self._clk.setText(time.strftime("%H:%M:%S", n))
        self._dt.setText(time.strftime("%A  %d %b %Y", n).upper())


# ─────────────────────────────────────────
#  NODE STATUS
# ─────────────────────────────────────────
class NodeStatus(QWidget):
    _C  = {"ok": P["green"], "warn": P["amber"], "error": P["red"], "idle": P["dim"]}
    _BG = {"ok": P["green_dim"], "warn": P["amber_dim"], "error": P["red_dim"], "idle": P["bg_card"]}

    def __init__(self, label, status="idle"):
        super().__init__()
        self.setFixedHeight(22)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(7)

        self._dot = QLabel()
        self._dot.setFixedSize(8, 8)
        row.addWidget(self._dot, 0, Qt.AlignVCenter)

        lb = QLabel(label)
        lb.setStyleSheet(
            f"color:{P['text_sec']}; font-family:{MONO}; font-size:10px; background:transparent; border:none;"
        )
        row.addWidget(lb, 0, Qt.AlignVCenter)
        row.addStretch()

        self._sl = QLabel()
        self._sl.setFixedWidth(34)
        self._sl.setAlignment(Qt.AlignCenter)
        row.addWidget(self._sl, 0, Qt.AlignVCenter)
        self.set_status(status)

    def set_status(self, s):
        c  = self._C.get(s, P["dim"])
        bg = self._BG.get(s, P["bg_card"])
        self._dot.setStyleSheet(f"background:{c}; border-radius:4px;")
        self._sl.setText(s.upper())
        self._sl.setStyleSheet(
            f"color:{c}; background:{bg}; font-family:{MONO}; font-size:8px; "
            f"letter-spacing:1px; border-radius:2px; padding:1px 3px;"
        )


# ─────────────────────────────────────────
#  TELEMETRY ROW
# ─────────────────────────────────────────
class TelRow(QWidget):
    def __init__(self, key):
        super().__init__()
        self.setFixedHeight(20)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        k = QLabel(key)
        k.setFixedWidth(108)
        k.setStyleSheet(
            f"color:{P['text_dim']}; font-family:{MONO}; font-size:10px; background:transparent; border:none;"
        )
        row.addWidget(k)
        self._v = QLabel("--")
        self._v.setStyleSheet(
            f"color:{P['text']}; font-family:{MONO}; font-size:10px; background:transparent; border:none;"
        )
        row.addWidget(self._v)
        row.addStretch()

    def set(self, v):
        self._v.setText(str(v))


# ─────────────────────────────────────────
#  RESOURCE BAR
# ─────────────────────────────────────────
class ResourceBar(QWidget):
    def __init__(self, label, color):
        super().__init__()
        self._color = color
        self._val = 0
        self.setFixedHeight(26)
        col = QVBoxLayout(self)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(3)

        top = QHBoxLayout(); top.setContentsMargins(0, 0, 0, 0)
        lbl = QLabel(label)
        lbl.setStyleSheet(
            f"color:{P['text_dim']}; font-family:{MONO}; font-size:9px; background:transparent; border:none;"
        )
        top.addWidget(lbl); top.addStretch()
        self._pct = QLabel("0%")
        self._pct.setStyleSheet(
            f"color:{color}; font-family:{MONO}; font-size:9px; background:transparent; border:none;"
        )
        top.addWidget(self._pct)
        col.addLayout(top)

        self._track = QFrame()
        self._track.setFixedHeight(4)
        self._track.setStyleSheet(f"background:{P['border']}; border-radius:2px;")
        col.addWidget(self._track)

        self._fill = QFrame(self._track)
        self._fill.setFixedHeight(4)
        self._fill.setStyleSheet(f"background:{color}; border-radius:2px;")
        self._fill.setFixedWidth(0)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._redraw()

    def set_value(self, pct):
        self._val = pct
        self._pct.setText(f"{pct:.0f}%")
        self._redraw()

    def _redraw(self):
        w = self._track.width()
        self._fill.setFixedWidth(max(0, int(w * self._val / 100)))


# ─────────────────────────────────────────
#  CAMERA PANEL  (fixed height, stretches width)
# ─────────────────────────────────────────
class CameraPanel(QFrame):
    def __init__(self):
        super().__init__()
        self._pix = None
        self.setFixedHeight(CAM_H)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setStyleSheet(
            f"QFrame {{ background:#000; border:1px solid {P['border']}; border-radius:3px; }}"
        )
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)

        self._ph = QLabel("NO SIGNAL")
        self._ph.setAlignment(Qt.AlignCenter)
        self._ph.setStyleSheet(
            f"color:{P['text_dim']}; font-family:{MONO}; font-size:11px; "
            f"letter-spacing:4px; background:transparent; border:none;"
        )
        self._img = QLabel()
        self._img.setAlignment(Qt.AlignCenter)
        self._img.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._img.setStyleSheet("background:transparent; border:none;")
        self._img.hide()

        lay.addWidget(self._ph)
        lay.addWidget(self._img)

    def update_frame(self, pix):
        self._pix = pix
        if self._ph.isVisible():
            self._ph.hide(); self._img.show()
        self._rescale()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._rescale()

    def _rescale(self):
        if self._pix:
            self._img.setPixmap(
                self._pix.scaled(self.width(), self.height(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
            )


# ─────────────────────────────────────────
#  SNAPSHOT PANEL  (beside camera, same height, stretches width)
# ─────────────────────────────────────────
class SnapshotPanel(QFrame):
    def __init__(self):
        super().__init__()
        self._pix = None
        self.setFixedHeight(SNAP_H)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setStyleSheet(
            f"QFrame {{ background:{P['bg_card']}; border:1px dashed {P['border_hi']}; border-radius:3px; }}"
        )
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # label strip at top
        lbl_bar = QFrame()
        lbl_bar.setFixedHeight(22)
        lbl_bar.setStyleSheet(
            f"background:{P['bg_panel']}; border:none; border-bottom:1px solid {P['border']}; border-radius:3px 3px 0 0;"
        )
        lb_row = QHBoxLayout(lbl_bar)
        lb_row.setContentsMargins(8, 0, 8, 0)
        lbl = QLabel("LAST VISION CAPTURE")
        lbl.setStyleSheet(
            f"color:{P['text_dim']}; font-family:{MONO}; font-size:8px; "
            f"letter-spacing:2px; background:transparent; border:none;"
        )
        lb_row.addWidget(lbl)
        lay.addWidget(lbl_bar)

        self._ph = QLabel("AWAITING\nCAPTURE")
        self._ph.setAlignment(Qt.AlignCenter)
        self._ph.setStyleSheet(
            f"color:{P['text_dim']}; font-family:{MONO}; font-size:9px; "
            f"letter-spacing:3px; background:transparent; border:none;"
        )
        self._img = QLabel()
        self._img.setAlignment(Qt.AlignCenter)
        self._img.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._img.setStyleSheet("background:transparent; border:none;")
        self._img.hide()

        lay.addWidget(self._ph)
        lay.addWidget(self._img)

    def update_snapshot(self, pix):
        self._pix = pix
        if self._ph.isVisible():
            self._ph.hide(); self._img.show()
        self._rescale()
        self.setStyleSheet(
            f"QFrame {{ background:{P['bg_card']}; border:2px solid {P['blue']}; border-radius:3px; }}"
        )
        QTimer.singleShot(700, self._reset)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._rescale()

    def _rescale(self):
        if self._pix:
            self._img.setPixmap(
                self._pix.scaled(self.width(), self.height() - 22, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            )

    def _reset(self):
        self.setStyleSheet(
            f"QFrame {{ background:{P['bg_card']}; border:1px dashed {P['border_hi']}; border-radius:3px; }}"
        )


# ─────────────────────────────────────────
#  CONVERSATION TIMELINE
# ─────────────────────────────────────────
class ConversationTimeline(QFrame):
    def __init__(self):
        super().__init__()
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setStyleSheet(
            f"QFrame {{ background:{P['bg_panel']}; border:1px solid {P['border']}; border-radius:4px; }}"
        )
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        hdr = QFrame(); hdr.setFixedHeight(32)
        hdr.setStyleSheet(
            f"background:{P['bg_card']}; border:none; "
            f"border-bottom:1px solid {P['border']}; border-radius:4px 4px 0 0;"
        )
        hrow = QHBoxLayout(hdr); hrow.setContentsMargins(14, 0, 14, 0)
        hl = QLabel("CONVERSATION")
        hl.setStyleSheet(
            f"color:{P['text_dim']}; font-family:{MONO}; font-size:9px; "
            f"letter-spacing:3px; background:transparent; border:none;"
        )
        hrow.addWidget(hl); hrow.addStretch()

        self._asc = QCheckBox("Auto-scroll")
        self._asc.setChecked(True)
        self._asc.setStyleSheet(f"""
            QCheckBox {{ color:{P['text_sec']}; font-family:{MONO}; font-size:9px; spacing:5px; background:transparent; border:none; }}
            QCheckBox::indicator {{ width:10px; height:10px; border:1px solid {P['border_hi']}; border-radius:2px; background:{P['bg_card']}; }}
            QCheckBox::indicator:checked {{ background:{P['blue']}; border:1px solid {P['blue']}; }}
        """)
        hrow.addWidget(self._asc)
        outer.addWidget(hdr)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._scroll.setStyleSheet("background:transparent; border:none;")
        self._scroll.verticalScrollBar().rangeChanged.connect(self._on_range)

        self._content = QWidget()
        self._content.setStyleSheet("background:transparent;")
        self._inner = QVBoxLayout(self._content)
        self._inner.setContentsMargins(14, 10, 14, 10)
        self._inner.setSpacing(0)
        self._inner.addStretch()

        self._scroll.setWidget(self._content)
        outer.addWidget(self._scroll)

    def _on_range(self, mn, mx):
        if self._asc.isChecked():
            self._scroll.verticalScrollBar().setValue(mx)

    def add_entry(self, speaker, text):
        ts = time.strftime("%H:%M:%S")
        is_user = speaker.upper() == "USER"
        color  = P["blue"]  if is_user else P["green"]
        tag_bg = P["blue_dim"] if is_user else P["green_dim"]

        blk = QFrame()
        blk.setStyleSheet("background:transparent; border:none;")
        bl = QVBoxLayout(blk)
        bl.setContentsMargins(0, 5, 0, 5)
        bl.setSpacing(3)

        hr = QHBoxLayout(); hr.setSpacing(8)
        tag = QLabel(speaker.upper())
        tag.setStyleSheet(
            f"color:{color}; background:{tag_bg}; font-family:{MONO}; font-size:9px; "
            f"font-weight:bold; letter-spacing:2px; padding:1px 6px; border-radius:2px; border:none;"
        )
        hr.addWidget(tag, 0, Qt.AlignVCenter)
        tsl = QLabel(f"[{ts}]")
        tsl.setStyleSheet(
            f"color:{P['text_dim']}; font-family:{MONO}; font-size:9px; background:transparent; border:none;"
        )
        hr.addWidget(tsl, 0, Qt.AlignVCenter)
        hr.addStretch()
        bl.addLayout(hr)

        msg = QLabel(text)
        msg.setWordWrap(True)
        msg.setTextInteractionFlags(Qt.TextSelectableByMouse)
        msg.setStyleSheet(
            f"color:{P['text']}; font-size:12px; background:transparent; border:none; padding-left:2px;"
        )
        bl.addWidget(msg)

        sep = QFrame(); sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet(f"border:none; border-top:1px solid {P['border']}; margin:0;")
        bl.addWidget(sep)

        self._inner.insertWidget(self._inner.count() - 1, blk)


# ─────────────────────────────────────────
#  EVENT LOG
# ─────────────────────────────────────────
class EventLog(QFrame):
    def __init__(self):
        super().__init__()
        self.setFixedHeight(150)
        self.setStyleSheet(
            f"QFrame {{ background:{P['bg_panel']}; border:1px solid {P['border']}; border-radius:4px; }}"
        )
        col = QVBoxLayout(self)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(0)

        hdr = QFrame(); hdr.setFixedHeight(28)
        hdr.setStyleSheet(
            f"background:{P['bg_card']}; border:none; "
            f"border-bottom:1px solid {P['border']}; border-radius:4px 4px 0 0;"
        )
        hl = QHBoxLayout(hdr); hl.setContentsMargins(14, 0, 14, 0)
        lbl = QLabel("EVENT LOG")
        lbl.setStyleSheet(
            f"color:{P['text_dim']}; font-family:{MONO}; font-size:9px; "
            f"letter-spacing:3px; background:transparent; border:none;"
        )
        hl.addWidget(lbl)
        col.addWidget(hdr)

        self._log = QTextEdit()
        self._log.setReadOnly(True)
        self._log.setFrameShape(QFrame.NoFrame)
        self._log.setStyleSheet(
            f"background:transparent; color:{P['text_sec']}; font-family:{MONO}; "
            f"font-size:10px; border:none; padding:4px 14px;"
        )
        col.addWidget(self._log)

    def append(self, level, msg):
        ts = time.strftime("%H:%M:%S")
        cs = {"INFO": P["text_sec"], "WARN": P["amber"], "ERROR": P["red"], "OK": P["green"]}
        c = cs.get(level.upper(), P["text_sec"])

        cur = self._log.textCursor()
        cur.movePosition(QTextCursor.End)

        f0 = QTextCharFormat(); f0.setForeground(QColor(P["text_dim"]))
        cur.setCharFormat(f0); cur.insertText(f"[{ts}] ")

        f1 = QTextCharFormat(); f1.setForeground(QColor(c))
        cur.setCharFormat(f1); cur.insertText(f"[{level.upper():5s}] ")

        f2 = QTextCharFormat(); f2.setForeground(QColor(P["text"]))
        cur.setCharFormat(f2); cur.insertText(msg + "\n")

        self._log.setTextCursor(cur)
        self._log.ensureCursorVisible()


# ─────────────────────────────────────────
#  RIGHT SIDEBAR
# ─────────────────────────────────────────
class RightPanel(QFrame):
    def __init__(self):
        super().__init__()
        self.setFixedWidth(250)
        self.setStyleSheet(
            f"QFrame {{ background:{P['bg_panel']}; border:none; border-left:1px solid {P['border']}; }}"
        )
        col = QVBoxLayout(self)
        col.setContentsMargins(13, 13, 13, 13)
        col.setSpacing(9)

        col.addWidget(sec_lbl("Node Status"))
        self.cam  = NodeStatus("usb_cam / image_raw")
        self.sr   = NodeStatus("google_sr (speech)")
        self.tts  = NodeStatus("gtts_input (TTS)")
        for w in [self.cam, self.sr, self.tts]: col.addWidget(w)

        col.addWidget(hsep())
        col.addWidget(sec_lbl("Session Telemetry"))
        self.uptime    = TelRow("UPTIME")
        self.frames    = TelRow("FRAMES")
        self.snapshots = TelRow("SNAPSHOTS")
        self.utt       = TelRow("UTTERANCES")
        self.replies   = TelRow("REPLIES")
        for w in [self.uptime, self.frames, self.snapshots, self.utt, self.replies]:
            col.addWidget(w)

        col.addWidget(hsep())
        col.addWidget(sec_lbl("System Resources"))
        self.cpu_bar  = ResourceBar("CPU", P["cyan"])
        self.mem_bar  = ResourceBar("MEM", P["purple"])
        self.disk_bar = ResourceBar("DISK", P["amber"])
        for w in [self.cpu_bar, self.mem_bar, self.disk_bar]: col.addWidget(w)

        self.cpu_tmp = TelRow("CPU TEMP")
        self.net_up  = TelRow("NET ↑")
        self.net_dn  = TelRow("NET ↓")
        for w in [self.cpu_tmp, self.net_up, self.net_dn]: col.addWidget(w)

        col.addStretch()


# ─────────────────────────────────────────
#  MAIN DASHBOARD
# ─────────────────────────────────────────
class RobotDashboard(QWidget):
    def __init__(self):
        super().__init__()
        if ROS_AVAILABLE:
            rospy.init_node("robot_dashboard_gui", anonymous=True)
            self.bridge = CvBridge()

        self._last_msg   = {"camera": None, "speech": None, "reply": None}
        self._t0         = time.time()
        self._frames     = 0
        self._utts       = 0
        self._replies    = 0
        self._snaps      = 0
        self._prev_net   = psutil.net_io_counters()
        self._prev_net_t = time.time()

        self.setWindowTitle("JungleBot Dashboard")
        # cam(640) + snap(320) + sidebar(250) + margins/spacing ≈ 1260
        self.resize(1280, 940)
        self.setMinimumSize(1100, 680)
        self.setStyleSheet(GLOBAL_QSS)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(TopBar())

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        root.addLayout(body, stretch=1)

        # ── LEFT COLUMN
        left = QVBoxLayout()
        left.setContentsMargins(14, 14, 14, 14)
        left.setSpacing(8)
        body.addLayout(left, stretch=1)

        # Section header for the camera row
        cam_hdr = QHBoxLayout()
        cam_hdr.addWidget(sec_lbl("Live Camera Feed"))
        cam_hdr.addStretch()
        self._cam_live_lbl = QLabel("● NO SIGNAL")
        self._cam_live_lbl.setStyleSheet(
            f"color:{P['text_dim']}; font-family:{MONO}; font-size:9px; background:transparent; border:none;"
        )
        cam_hdr.addWidget(self._cam_live_lbl)
        left.addLayout(cam_hdr)

        # Camera + Snapshot SIDE BY SIDE — both stretch with window width
        cam_snap = QHBoxLayout()
        cam_snap.setSpacing(8)
        cam_snap.setContentsMargins(0, 0, 0, 0)

        self._camera   = CameraPanel()
        self._snapshot = SnapshotPanel()

        cam_snap.addWidget(self._camera,   stretch=2)   # cam gets 2/3 of available width
        cam_snap.addWidget(self._snapshot, stretch=1)   # snapshot gets 1/3

        left.addLayout(cam_snap)

        # Conversation timeline
        self._convo = ConversationTimeline()
        left.addWidget(self._convo, stretch=1)

	# Event log
        #left.addWidget(sec_lbl("System Events"))
        self._evlog = EventLog()
        left.addWidget(self._evlog)
	
        # ── RIGHT SIDEBAR
        self._right = RightPanel()
        body.addWidget(self._right)

        # ── ROS subscriptions
        if ROS_AVAILABLE:
            rospy.Subscriber("/usb_cam/image_raw", Image,  self._cb_cam)
            rospy.Subscriber("/google_sr",          String, self._cb_sr)
            rospy.Subscriber("/gtts_input",         String, self._cb_tts)
            rospy.Subscriber("/vision_snapshot",    Image,  self._cb_snap)

        # ── Timers
        t_ros = QTimer(self); t_ros.timeout.connect(self._ros_spin);    t_ros.start(10)
        t_tel = QTimer(self); t_tel.timeout.connect(self._update_tel);  t_tel.start(1000)
        t_dog = QTimer(self); t_dog.timeout.connect(self._watchdog);    t_dog.start(3000)
        t_sys = QTimer(self); t_sys.timeout.connect(self._update_sys);  t_sys.start(2000)

        self._evlog.append("OK",   "Dashboard initialised (PyQt5)")
        self._evlog.append("INFO", "Waiting for ROS topics..." if ROS_AVAILABLE else "ROS not found — UI-only mode")
        self._update_sys()

    # ── ROS callbacks ─────────────────────
    def _cb_cam(self, data):
        try:
            img = self.bridge.imgmsg_to_cv2(data, "rgb8")
            h, w, ch = img.shape
            qi = QImage(img.data, w, h, ch * w, QImage.Format_RGB888)
            self._camera.update_frame(QPixmap.fromImage(qi))
            self._last_msg["camera"] = time.time()
            self._frames += 1
            self._right.cam.set_status("ok")
            self._cam_live_lbl.setText("● LIVE")
            self._cam_live_lbl.setStyleSheet(
                f"color:{P['green']}; font-family:{MONO}; font-size:9px; background:transparent; border:none;"
            )
        except Exception as e:
            self._evlog.append("ERROR", f"Camera: {e}")

    def _cb_snap(self, data):
        try:
            img = self.bridge.imgmsg_to_cv2(data, "rgb8")
            h, w, ch = img.shape
            qi = QImage(img.data, w, h, ch * w, QImage.Format_RGB888)
            self._snapshot.update_snapshot(QPixmap.fromImage(qi))
            self._snaps += 1
            self._evlog.append("INFO", "Vision snapshot captured")
        except Exception as e:
            self._evlog.append("ERROR", f"Snapshot: {e}")

    def _cb_sr(self, msg):
        self._convo.add_entry("USER", msg.data)
        self._last_msg["speech"] = time.time()
        self._utts += 1
        self._right.sr.set_status("ok")
        self._evlog.append("INFO", f"Utterance: {msg.data[:60]}{'…' if len(msg.data) > 60 else ''}")

    def _cb_tts(self, msg):
        self._convo.add_entry("JUNGLEBOT", msg.data)
        self._last_msg["reply"] = time.time()
        self._replies += 1
        self._right.tts.set_status("ok")
        self._evlog.append("OK", "Reply dispatched to TTS")

    # ── Timers ────────────────────────────
    def _ros_spin(self):
        if ROS_AVAILABLE and rospy.is_shutdown():
            self._evlog.append("WARN", "ROS shutdown detected")
            self.close()

    def _update_tel(self):
        e = int(time.time() - self._t0)
        h, m, s = e // 3600, (e % 3600) // 60, e % 60
        self._right.uptime.set(f"{h:02d}:{m:02d}:{s:02d}")
        self._right.frames.set(self._frames)
        self._right.snapshots.set(self._snaps)
        self._right.utt.set(self._utts)
        self._right.replies.set(self._replies)

    def _watchdog(self):
        now = time.time(); thr = 5.0
        for key, node, name in [
            ("camera", self._right.cam,  "Camera"),
            ("speech", self._right.sr,   "Speech"),
            ("reply",  self._right.tts,  "TTS"),
        ]:
            t = self._last_msg[key]
            if t and (now - t) > thr:
                node.set_status("warn")
                self._evlog.append("WARN", f"{name}: no data for {now - t:.0f}s")
            elif not t:
                node.set_status("idle")

    def _update_sys(self):
        now = time.time()
        net = psutil.net_io_counters()
        dt  = max(now - self._prev_net_t, 0.001)
        sent_ps = (net.bytes_sent - self._prev_net.bytes_sent) / dt
        recv_ps = (net.bytes_recv - self._prev_net.bytes_recv) / dt
        self._prev_net = net
        self._prev_net_t = now

        self._right.cpu_bar.set_value(psutil.cpu_percent(interval=None))
        self._right.mem_bar.set_value(psutil.virtual_memory().percent)
        self._right.disk_bar.set_value(psutil.disk_usage('/').percent)

        try:
            temps = psutil.sensors_temperatures()
            if temps:
                key = next(iter(temps))
                self._right.cpu_tmp.set(f"{temps[key][0].current:.1f} °C")
            else:
                self._right.cpu_tmp.set("N/A")
        except Exception:
            self._right.cpu_tmp.set("N/A")

        def fmt(b):
            for u in ['B', 'KB', 'MB', 'GB']:
                if b < 1024: return f"{b:.1f} {u}/s"
                b /= 1024
            return f"{b:.1f} GB/s"

        self._right.net_up.set(fmt(sent_ps))
        self._right.net_dn.set(fmt(recv_ps))


# ─────────────────────────────────────────
#  ENTRY POINT
# ─────────────────────────────────────────
if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    pal = QPalette()
    pal.setColor(QPalette.Window,          QColor(P["bg_root"]))
    pal.setColor(QPalette.WindowText,      QColor(P["text"]))
    pal.setColor(QPalette.Base,            QColor(P["bg_panel"]))
    pal.setColor(QPalette.AlternateBase,   QColor(P["bg_card"]))
    pal.setColor(QPalette.Text,            QColor(P["text"]))
    pal.setColor(QPalette.Button,          QColor(P["bg_panel"]))
    pal.setColor(QPalette.ButtonText,      QColor(P["text"]))
    pal.setColor(QPalette.Highlight,       QColor(P["blue"]))
    pal.setColor(QPalette.HighlightedText, QColor("#ffffff"))
    app.setPalette(pal)

    dash = RobotDashboard()
    dash.show()
    sys.exit(app.exec_())