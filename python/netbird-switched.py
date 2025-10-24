#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NetBird Environment Switcher (Linux-only, runs as normal user)
"""

import os, sys, re, json, subprocess, threading, time, shutil
from pathlib import Path
from PySide6 import QtCore, QtGui, QtWidgets

APP_DIR = Path(sys.argv[0]).resolve().parent
ENVS_PATH = APP_DIR / "envs.json"

# Hide noisy QPainter warnings (harmless)
def _qt_msg_handler(mode, ctx, msg):
    if msg.startswith("QPainter::"): return
    sys.stderr.write(msg + "\n")
QtCore.qInstallMessageHandler(_qt_msg_handler)

QtWidgets.QApplication.setStyle("Fusion")

# ---------- platform check (Linux-only) ----------
def _require_linux_or_exit():
    if not sys.platform.startswith("linux"):
        QtWidgets.QMessageBox.critical(None, "Unsupported OS", "This application supports Linux only.")
        sys.exit(1)

# ---------- CLI ----------
def run_cmd(cmd: str, timeout: int = 60):
    try:
        p = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return p.returncode, p.stdout.strip(), p.stderr.strip()
    except Exception as e:
        return 255, "", str(e)

def nb_service_start(): return run_cmd("netbird service start", timeout=10)
def nb_down(): return run_cmd("netbird down")
def nb_status(detail: bool = True):
    return run_cmd(f"netbird status{' -d' if detail else ''}")

def nb_up_async(url: str):
    """
    """
    args = ["netbird", "up", "--management-url", url]
    
    try:
        return subprocess.Popen(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )
    except Exception:
        return None

def parse_mgmt_url(text: str):
    m = re.search(r"Management:\s*Connected(?:\s*to)?\s*(https?://[^\s]+)", text, re.IGNORECASE)
    return m.group(1) if m else None

def _pump_proc_output(proc: subprocess.Popen, bus: "UIBus"):
    """
    Stream netbird's stdout (merged with stderr) into the Activity Log and
    auto-open the first https:// URL via xdg-open.
    """
    opened = False
    try:
        for raw in iter(proc.stdout.readline, ''):
            line = raw.rstrip("\r\n")
            if not line:
                continue
            bus.log.emit(line)
            if not opened:
                m = re.search(r'(https://\S+)', line)
                if m:
                    try:
                        subprocess.Popen(
                            ["xdg-open", m.group(1)],
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL
                        )
                    except Exception:
                        pass
                    opened = True
    except Exception as e:
        bus.log.emit(f"! output stream error: {e}")

# ---------- networks ----------
def networks_select_all():
    """
    Select all networks by parsing 'netbird networks list' and feeding the
    resulting *network IDs* to 'netbird networks select'.
    """
    rc, out, err = run_cmd("netbird networks list")
    if rc != 0:
        return "netbird networks list", rc, out, err

    text = out or ""
    ids = []

    def is_cidr(tok: str) -> bool:
        return bool(re.match(r"^\d{1,3}(?:\.\d{1,3}){3}/\d{1,2}$", tok))

    def is_ip(tok: str) -> bool:
        return bool(re.match(r"^\d{1,3}(?:\.\d{1,3}){3}$", tok))

    # 1) Key-value style lines: "... ID: <id> ..."
    for line in text.splitlines():
        m = re.search(r"\bID:\s*([A-Za-z0-9][A-Za-z0-9_.-]+)\b", line)
        if m:
            tok = m.group(1)
            if tok and not is_ip(tok) and not is_cidr(tok):
                ids.append(tok)

    # 2) Table header with an 'ID' column
    if not ids:
        header_idx = None
        lines = text.splitlines()
        for i, raw in enumerate(lines):
            s = raw.strip()
            if not s:
                continue
            cols = re.split(r"\s{2,}", re.sub(r"^[^\w]+", "", s))
            if any(c.strip().lower() == "id" for c in cols):
                for j, c in enumerate(cols):
                    if c.strip().lower() == "id":
                        header_idx = j
                        break
                for data in lines[i+1:]:
                    ds = data.strip()
                    if not ds:
                        continue
                    dcols = re.split(r"\s{2,}", re.sub(r"^[^\w]+", "", ds))
                    if header_idx is not None and len(dcols) > header_idx:
                        tok = dcols[header_idx].strip()
                        if tok and tok.lower() != "id" and not is_ip(tok) and not is_cidr(tok):
                            ids.append(tok)
                break

    # De-dup while preserving order
    seen = set(); uniq = []
    for i in ids:
        if i not in seen:
            seen.add(i); uniq.append(i)
    ids = uniq

    if not ids:
        return "parse networks list (IDs)", 1, text, "No network IDs parsed from 'netbird networks list'"

    # Select in safe chunks; quote each id
    for i in range(0, len(ids), 15):
        chunk = ids[i:i+15]
        cmd = "netbird networks select " + " ".join(f'"{x}"' for x in chunk)
        rc2, out2, err2 = run_cmd(cmd)
        if rc2 != 0:
            return cmd, rc2, out2, err2

    return "netbird networks select <ids>", 0, "Selected: " + ", ".join(ids), ""

def networks_refresh():
    rc, out, err = run_cmd("netbird networks refresh")

    def looks_like_help(s: str) -> bool:
        return bool(s) and "Usage:" in s and "netbird networks" in s

    if rc == 0 and looks_like_help(out):  # Clean noisy help output
        out = ""
    return rc, out, err

# ---------- data ----------
def ensure_envs_file(p: Path):
    if not p.exists(): p.write_text("[]", encoding="utf-8")

def load_envs(p: Path):
    ensure_envs_file(p)
    data = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(data, list): raise ValueError("envs.json must be a JSON array")
    for i, e in enumerate(data):
        if not isinstance(e, dict) or "name" not in e or "management_url" not in e:
            raise ValueError(f"Item #{i+1} must have 'name' and 'management_url'")
    return data

def save_envs(p: Path, envs: list):
    p.write_text(json.dumps(envs, indent=2), encoding="utf-8")

# ---------- app icon (safe) ----------
def make_app_icon(size=128) -> QtGui.QIcon:
    if getattr(make_app_icon, "_icon", None): return make_app_icon._icon
    img = QtGui.QImage(size, size, QtGui.QImage.Format_ARGB32); img.fill(QtCore.Qt.transparent)
    p = QtGui.QPainter()
    if p.begin(img):
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        r = QtCore.QRectF(0, 0, size, size)
        path = QtGui.QPainterPath(); path.addRoundedRect(r.adjusted(6, 6, -6, -6), size*0.18, size*0.18)
        p.fillPath(path, QtGui.QColor("#0f141b"))
        inner = r.adjusted(size*0.16, size*0.16, -size*0.16, -size*0.16)
        p.setPen(QtGui.QPen(QtGui.QColor("#10b981"), size*0.07)); p.drawEllipse(inner)
        f = QtGui.QFont(); f.setBold(True); f.setPointSizeF(size*0.4); p.setFont(f)
        p.setPen(QtGui.QPen(QtGui.QColor("#e5e7eb"))); p.drawText(r, QtCore.Qt.AlignCenter, "NB")
        p.end()
    icon = QtGui.QIcon(QtGui.QPixmap.fromImage(img)); make_app_icon._icon = icon; return icon

# ---------- UI pieces ----------
class EnvCard(QtWidgets.QFrame):
    clicked = QtCore.Signal()
    def __init__(self, name: str, selected=False, active=False, parent=None):
        super().__init__(parent)
        self.name, self.selected, self.active = name, selected, active
        self.setCursor(QtCore.Qt.PointingHandCursor); self.setMinimumHeight(48)
        lay = QtWidgets.QHBoxLayout(self); lay.setContentsMargins(14, 10, 14, 10); lay.setSpacing(10)
        self.lbl = QtWidgets.QLabel(name); self.lbl.setStyleSheet("font-size:14px; font-weight:600; color:#e7e7ea;"); lay.addWidget(self.lbl); lay.addStretch(1)
        self.badge = QtWidgets.QLabel("Active" if active else ""); self.badge.setStyleSheet("padding:2px 8px; border-radius:9px; background:#064e3b; color:#a7f3d0; font-weight:600;")
        self.badge.setVisible(active); lay.addWidget(self.badge)
        self._apply_style(False)
    def setSelected(self, v): self.selected = v; self._apply_style(False)
    def setActive(self, v): self.active = v; self.badge.setVisible(v); self.badge.setText("Active" if v else ""); self._apply_style(False)
    def enterEvent(self, e): self._apply_style(True);  super().enterEvent(e)
    def leaveEvent(self, e): self._apply_style(False); super().leaveEvent(e)
    def mouseReleaseEvent(self, e):
        if e.button() == QtCore.Qt.LeftButton: self.clicked.emit()
        super().mouseReleaseEvent(e)
    def _apply_style(self, hover):
        base, hoverc, selectedc, activec, border = "#1a1f29", "#202735", "#273244", "#22303f", "#2a3242"
        bg = activec if self.active else (selectedc if self.selected else (hoverc if hover else base))
        self.setStyleSheet(f"QFrame {{ background:{bg}; border:1px solid {border}; border-radius:12px; }}")

class BaseDialog(QtWidgets.QDialog):
    def _strip_icons(self, box: QtWidgets.QDialogButtonBox):
        for std in (QtWidgets.QDialogButtonBox.Ok, QtWidgets.QDialogButtonBox.Cancel):
            btn = box.button(std)
            if btn: btn.setIcon(QtGui.QIcon())
    def center_on_screen(self):
        geo = self.frameGeometry(); geo.moveCenter(self.screen().availableGeometry().center()); self.move(geo.topLeft())

class AddEnvDialog(BaseDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add Environment"); self.setWindowIcon(make_app_icon())
        self.setModal(True); self.setMinimumSize(680, 220)
        f = QtWidgets.QFormLayout(self); f.setHorizontalSpacing(16); f.setVerticalSpacing(12)
        self.name = QtWidgets.QLineEdit(); self.url = QtWidgets.QLineEdit()
        self.name.setPlaceholderText("e.g., CCSTG"); self.url.setPlaceholderText("https://host:443")
        f.addRow("Name", self.name); f.addRow("Management URL", self.url)
        btns = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept); btns.rejected.connect(self.reject); f.addRow(btns); self._strip_icons(btns)
        QtCore.QTimer.singleShot(0, self.center_on_screen)
    def get(self): return self.name.text().strip(), self.url.text().strip()

class EditEnvDialog(BaseDialog):
    def __init__(self, name: str, url: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Edit {name}"); self.setWindowIcon(make_app_icon())
        self.setModal(True); self.setMinimumSize(680, 220)
        f = QtWidgets.QFormLayout(self); f.setHorizontalSpacing(16); f.setVerticalSpacing(12)
        self.name_label = QtWidgets.QLabel(name); self.url = QtWidgets.QLineEdit(url); self.url.setPlaceholderText("https://host:443")
        f.addRow("Name", self.name_label); f.addRow("Management URL", self.url)
        btns = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept); btns.rejected.connect(self.reject); f.addRow(btns); self._strip_icons(btns)
        QtCore.QTimer.singleShot(0, self.center_on_screen)
    def get(self): return self.url.text().strip()

# ---------- safe message boxes ----------
def ask_yes_no(parent, title, text, default_yes=True):
    b = QtWidgets.QMessageBox(parent); b.setWindowTitle(title); b.setText(text); b.setWindowIcon(make_app_icon()); b.setIcon(QtWidgets.QMessageBox.NoIcon)
    b.setStandardButtons(QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No)
    b.setDefaultButton(QtWidgets.QMessageBox.Yes if default_yes else QtWidgets.QMessageBox.No)
    b.setStyleSheet("QLabel{color:#e5e7eb;} QMessageBox{background:#0d1117;}"); return b.exec()
def info_box(parent, title, text):
    b = QtWidgets.QMessageBox(parent); b.setWindowTitle(title); b.setText(text); b.setWindowIcon(make_app_icon()); b.setIcon(QtWidgets.QMessageBox.NoIcon)
    b.setStyleSheet("QLabel{color:#e5e7eb;} QMessageBox{background:#0d1117;}"); b.setStandardButtons(QtWidgets.QMessageBox.Ok); return b.exec()
def warn_box(parent, title, text):
    b = QtWidgets.QMessageBox(parent); b.setWindowTitle(title); b.setText(text); b.setWindowIcon(make_app_icon()); b.setIcon(QtWidgets.QMessageBox.NoIcon)
    b.setStyleSheet("QLabel{color:#e5e7eb;} QMessageBox{background:#0d1117;}"); b.setStandardButtons(QtWidgets.QMessageBox.Ok); return b.exec()

# ---------- UI Bus (signals to main thread) ----------
class UIBus(QtCore.QObject):
    log = QtCore.Signal(str)
    pill = QtCore.Signal(str, str)          # text, color
    set_active = QtCore.Signal(object)      # name | None
    set_enabled = QtCore.Signal(bool)
    rebuild = QtCore.Signal()

# ---------- Main window ----------
class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("NetBird Switcher"); self.setWindowIcon(make_app_icon())
        self.resize(1040, 700)
        self.selected_name = None
        self.active_name = None
        self.bus = UIBus()
        self._apply_dark_palette(); self._build(); self._wire_bus()
        self._load_envs_initial()

    # wire signals
    def _wire_bus(self):
        self.bus.log.connect(self._log)
        self.bus.pill.connect(self._set_pill)
        self.bus.set_active.connect(self._set_active_name)
        self.bus.set_enabled.connect(self._set_controls_enabled)
        self.bus.rebuild.connect(self._rebuild_cards)

    def _set_controls_enabled(self, enabled: bool):
        for b in (self.btn_connect, self.btn_disconnect, self.btn_status,
                  self.btn_add, self.btn_edit, self.btn_remove, self.btn_refresh):
            b.setEnabled(enabled)

    def _set_active_name(self, name):
        self.active_name = name; self._rebuild_cards()

    def _apply_dark_palette(self):
        pal = QtGui.QPalette()
        pal.setColor(QtGui.QPalette.Window, QtGui.QColor("#0d1117"))
        pal.setColor(QtGui.QPalette.Base, QtGui.QColor("#0d1117"))
        pal.setColor(QtGui.QPalette.AlternateBase, QtGui.QColor("#0f141b"))
        pal.setColor(QtGui.QPalette.Button, QtGui.QColor("#11161d"))
        pal.setColor(QtGui.QPalette.ToolTipBase, QtGui.QColor("#11161d"))
        pal.setColor(QtGui.QPalette.ToolTipText, QtGui.QColor("#e5e7eb"))
        pal.setColor(QtGui.QPalette.Text, QtGui.QColor("#e5e7eb"))
        pal.setColor(QtGui.QPalette.WindowText, QtGui.QColor("#e5e7eb"))
        pal.setColor(QtGui.QPalette.Highlight, QtGui.QColor("#164e3f"))
        pal.setColor(QtGui.QPalette.HighlightedText, QtGui.QColor("#ffffff"))
        self.setPalette(pal)
        self.setStyleSheet("""
            QLabel { color:#e5e7eb; }
            QLineEdit, QDialog QLineEdit { background:#0f141b; color:#e5e7eb; border:1px solid #2a3242; border-radius:8px; padding:10px; }
            QPlainTextEdit { background:#0f141b; color:#cfd5dc; border:1px solid #2a3242; border-radius:10px; }
            QPushButton { background:#11161d; color:#e5e7eb; border:1px solid #2a3242; border-radius:10px; padding:10px 14px; }
            QPushButton:hover { background:#151b24; }
            QDialog { background:#0d1117; }

            /* Ensure scroll area, its viewport and content are all dark */
            QScrollArea { border:1px solid #2a3242; border-radius:10px; background:#0f141b; }
            QScrollArea > QWidget { background:#0f141b; }                 /* viewport */
            QScrollArea > QWidget > QWidget { background:#0f141b; }       /* inner host */
        """)

    def _build(self):
        w = QtWidgets.QWidget(); self.setCentralWidget(w)
        outer = QtWidgets.QVBoxLayout(w); outer.setContentsMargins(14, 14, 14, 14); outer.setSpacing(14)

        header = QtWidgets.QHBoxLayout()
        logo = QtWidgets.QLabel("NB"); logo.setAlignment(QtCore.Qt.AlignCenter); logo.setFixedSize(28, 28)
        logo.setStyleSheet("background:#1a1f29; color:#10b981; border-radius:6px; font-weight:900; letter-spacing:0.5px;")
        title = QtWidgets.QLabel("NetBird Environment Switcher"); title.setStyleSheet("font-size:18px; font-weight:700;")
        self.pill = QtWidgets.QLabel(" Ready "); self.pill.setStyleSheet("background:#374151; color:#e5e7eb; padding:6px 12px; border-radius:12px; font-weight:600;")
        header.addWidget(logo); header.addSpacing(8); header.addWidget(title); header.addStretch(1); header.addWidget(self.pill)
        outer.addLayout(header)

        # Search
        search_row = QtWidgets.QHBoxLayout()
        search_lbl = QtWidgets.QLabel("Search")
        self.search = QtWidgets.QLineEdit(); self.search.setPlaceholderText("Type to filter environments…"); self.search.textChanged.connect(self._on_filter)
        search_row.addWidget(search_lbl); search_row.addSpacing(8); search_row.addWidget(self.search, 1); outer.addLayout(search_row)

        # Middle
        middle = QtWidgets.QHBoxLayout(); middle.setSpacing(14)
        self.cards_container = QtWidgets.QWidget()
        self.cards_container.setStyleSheet("background:#0f141b;")
        self.cards_layout = QtWidgets.QVBoxLayout(self.cards_container); self.cards_layout.setContentsMargins(6, 6, 6, 6); self.cards_layout.setSpacing(10)
        scroll = QtWidgets.QScrollArea(); scroll.setWidgetResizable(True); scroll.setWidget(self.cards_container)
        middle.addWidget(scroll, 1)

        right = QtWidgets.QVBoxLayout()
        # Connection actions
        self.btn_connect = QtWidgets.QPushButton("Connect"); self.btn_connect.setStyleSheet("QPushButton{background:#0d382e; color:#a7f3d0; border:1px solid #164e3f; font-weight:700; padding:14px 18px; border-radius:12px;} QPushButton:hover{background:#115e49;}")
        self.btn_disconnect = QtWidgets.QPushButton("Disconnect")
        self.btn_status = QtWidgets.QPushButton("Status")
        self.btn_connect.clicked.connect(self.on_connect); self.btn_disconnect.clicked.connect(self.on_disconnect); self.btn_status.clicked.connect(self.on_status)
        for b in (self.btn_connect, self.btn_disconnect, self.btn_status): right.addWidget(b); right.addSpacing(8)

        sep = QtWidgets.QFrame(); sep.setFrameShape(QtWidgets.QFrame.HLine); sep.setStyleSheet("color:#2a3242;")
        right.addWidget(sep); right.addSpacing(4)

        # Manage envs
        manage_lbl = QtWidgets.QLabel("Manage environments"); manage_lbl.setStyleSheet("font-weight:700; color:#cbd5e1;")
        right.addWidget(manage_lbl)
        self.btn_add = QtWidgets.QPushButton("Add"); self.btn_edit = QtWidgets.QPushButton("Edit URL"); self.btn_remove = QtWidgets.QPushButton("Remove")
        self.btn_add.clicked.connect(self.on_add); self.btn_edit.clicked.connect(self.on_edit); self.btn_remove.clicked.connect(self.on_remove)
        right.addWidget(self.btn_add); right.addSpacing(6); right.addWidget(self.btn_edit); right.addSpacing(6); right.addWidget(self.btn_remove)

        # Networks
        right.addSpacing(10)
        nets_lbl = QtWidgets.QLabel("Networks"); nets_lbl.setStyleSheet("font-weight:700; color:#cbd5e1;"); right.addWidget(nets_lbl)
        self.btn_refresh = QtWidgets.QPushButton("Refresh Networks"); self.btn_refresh.setToolTip("Select all networks then refresh")
        self.btn_refresh.clicked.connect(self.on_refresh_networks); right.addWidget(self.btn_refresh)

        right.addStretch(1); middle.addLayout(right, 0)
        outer.addLayout(middle, 1)

        outer.addWidget(QtWidgets.QLabel("Activity Log"))
        self.log = QtWidgets.QPlainTextEdit(); self.log.setReadOnly(True); outer.addWidget(self.log, 2)

        QtGui.QShortcut(QtGui.QKeySequence("Return"), self, activated=self.on_connect)
        QtGui.QShortcut(QtGui.QKeySequence("Ctrl+F"), self, activated=self.search.setFocus)

    # ----- load/render -----
    def _load_envs_initial(self):
        try:
            self.envs = load_envs(ENVS_PATH)
        except Exception as e:
            warn_box(self, "envs.json error", str(e)); ENVS_PATH.write_text("[]", encoding="utf-8"); self.envs = []
        self.filtered = list(self.envs); self._rebuild_cards()
        if not self.envs: info_box(self, "Empty list", f"No environments found.\nUse 'Add' to create entries in:\n{ENVS_PATH}")

    def _rebuild_cards(self):
        while self.cards_layout.count():
            it = self.cards_layout.takeAt(0); w = it.widget()
            if w: w.deleteLater()
        for env in self.filtered:
            name = env["name"]
            card = EnvCard(name, selected=(name == self.selected_name), active=(name == self.active_name))
            card.clicked.connect(lambda e=env: self._select_env(e))
            self.cards_layout.addWidget(card)
        self.cards_layout.addStretch(1)

    def _select_env(self, env):
        self.selected_name = env["name"]; self._rebuild_cards()

    def _on_filter(self, text: str):
        q = text.strip().lower()
        self.filtered = [e for e in self.envs if q in e["name"].lower()] if q else list(self.envs)
        self._rebuild_cards()

    # slots (main thread)
    @QtCore.Slot(str)
    def _log(self, text: str):
        self.log.appendPlainText(text); self.log.verticalScrollBar().setValue(self.log.verticalScrollBar().maximum())

    @QtCore.Slot(str, str)
    def _set_pill(self, text: str, color: str):
        self.pill.setText(f" {text} "); self.pill.setStyleSheet(f"background:{color}; color:#0b1220; padding:6px 12px; border-radius:12px; font-weight:700;")

    # helpers
    def _ensure_down_quick(self, max_wait=2.0, step=0.2):
        rc0, out0, _ = nb_status(True)
        if rc0 == 0 and parse_mgmt_url(out0) is None: return
        nb_down()
        t_end = time.time() + max_wait
        while time.time() < t_end:
            rc, out, _ = nb_status(True)
            if rc != 0 or parse_mgmt_url(out) is None: break
            time.sleep(step)

    def _run_bg(self, fn):
        self.bus.set_enabled.emit(False)
        def wrapper():
            try:
                fn()
            finally:
                self.bus.set_enabled.emit(True)
        threading.Thread(target=wrapper, daemon=True).start()

    # ----- manage envs (UI thread) -----
    def on_add(self):
        dlg = AddEnvDialog(self)
        if dlg.exec() == QtWidgets.QDialog.Accepted:
            name, url = dlg.get()
            if not name or not url or not re.match(r"^https?://", url):
                warn_box(self, "Invalid", "Please enter a name and a valid Management URL (http/https)."); return
            exists = next((e for e in self.envs if e["name"].lower() == name.lower()), None)
            if exists:
                if ask_yes_no(self, "Overwrite?", f"Environment '{name}' exists. Overwrite its URL?", default_yes=False) != QtWidgets.QMessageBox.Yes:
                    return
                exists["management_url"] = url
            else:
                self.envs.append({"name": name, "management_url": url})
            try:
                save_envs(ENVS_PATH, self.envs); self._log(f"✓ Saved '{name}' to {ENVS_PATH}")
                self._on_filter(self.search.text())
            except Exception as e:
                warn_box(self, "Save failed", str(e))

    def on_edit(self):
        if not self.selected_name: info_box(self, "Select", "Pick an environment card first."); return
        env = next(e for e in self.envs if e["name"] == self.selected_name)
        dlg = EditEnvDialog(env["name"], env["management_url"], self)
        if dlg.exec() == QtWidgets.QDialog.Accepted:
            new_url = dlg.get()
            if not new_url or not re.match(r"^https?://", new_url):
                warn_box(self, "Invalid", "Please enter a valid Management URL (http/https)."); return
            env["management_url"] = new_url
            try:
                save_envs(ENVS_PATH, self.envs); self._log(f"✓ Updated '{env['name']}' URL in {ENVS_PATH}")
                self._on_filter(self.search.text())
            except Exception as e:
                warn_box(self, "Save failed", str(e))

    def on_remove(self):
        if not self.selected_name: info_box(self, "Select", "Pick an environment card first."); return
        name = self.selected_name
        if ask_yes_no(self, "Remove environment", f"Delete '{name}' from the list?", default_yes=False) != QtWidgets.QMessageBox.Yes:
            return
        self.envs = [e for e in self.envs if e["name"] != name]
        try:
            save_envs(ENVS_PATH, self.envs); self._log(f"✓ Removed '{name}' from {ENVS_PATH}")
            if self.active_name == name: self.active_name = None
            self.selected_name = None; self.filtered = list(self.envs); self._rebuild_cards()
        except Exception as e:
            warn_box(self, "Save failed", str(e))

    # ----- networks (WORKER via _run_bg) -----
    def on_refresh_networks(self):
        def work():
            self.bus.pill.emit("Refreshing…", "#0ea5a0")
            self.bus.log.emit("Selecting all networks…")
            cmd, rc, out, err = networks_select_all()
            if rc == 0:
                self.bus.log.emit(f"✓ Networks selected via: {cmd}")
                if out: self.bus.log.emit(out)
            else:
                self.bus.log.emit(f"! Network select failed via: {cmd} (rc={rc})")
                self.bus.log.emit(err or out or "no output")
            self.bus.log.emit("Refreshing networks…")
            rc2, out2, err2 = networks_refresh()
            if rc2 == 0:
                self.bus.log.emit("✓ Networks refreshed")
                if out2: self.bus.log.emit(out2)
                self.bus.pill.emit("Refreshed", "#10b981")
            else:
                self.bus.log.emit(f"! Network refresh failed (rc={rc2})")
                self.bus.log.emit(err2 or out2 or "no output")
                self.bus.pill.emit("Refresh failed", "#ef4444")
        self._run_bg(work)

    # ----- status/connect/disconnect (WORKER) -----
    def on_status(self):
        def work():
            self.bus.pill.emit("Checking…", "#f59e0b")
            rc, out, err = nb_status(True)
            if rc == 0:
                mgmt = parse_mgmt_url(out)
                if mgmt:
                    self.bus.pill.emit("Connected", "#10b981")
                    self.bus.log.emit(out); self.bus.log.emit(f"✓ Management: {mgmt}")
                else:
                    self.bus.pill.emit("Disconnected", "#6b7280"); self.bus.log.emit("i Not connected.")
            else:
                self.bus.pill.emit("Error", "#ef4444"); self.bus.log.emit(f"status failed (rc={rc}): {err or out}")
        self._run_bg(work)

    def on_disconnect(self):
        if not self.selected_name: info_box(self, "Select", "Pick an environment card first."); return
        def work():
            self.bus.pill.emit("Disconnecting…", "#f59e0b")
            rc, out, err = nb_down()
            self.bus.set_active.emit(None)   # clear active
            if rc == 0:
                self.bus.pill.emit("Disconnected", "#6b7280"); self.bus.log.emit("✓ Disconnected.")
            else:
                self.bus.pill.emit("Error", "#ef4444"); self.bus.log.emit(f"down failed (rc={rc}): {err or out}")
        self._run_bg(work)

    def on_connect(self):
        if not self.selected_name: info_box(self, "Select", "Pick an environment card first."); return
        env = next(e for e in self.envs if e["name"] == self.selected_name)
        name, url = env["name"], env["management_url"]
        def work():
            self.bus.pill.emit("Connecting…", "#0ea5a0"); self.bus.log.emit(f"Connecting to {name} ...")

            # Try to start the service (may require root on some setups)
            rc, out, err = nb_service_start()
            if rc == 0:
                self.bus.log.emit("✓ Service started (or already running).")
            else:
                self.bus.log.emit("i Could not start service as normal user (this is OK if it's already running).")
                if err or out:
                    self.bus.log.emit((err or out))
                self.bus.log.emit("i If needed, start it manually: sudo netbird service start")

            self.bus.log.emit("Resetting session...")
            self._ensure_down_quick(max_wait=2.0, step=0.2)

            # Launch `up` without waiting so the browser can open
            proc = nb_up_async(url)
            if not proc:
                self.bus.pill.emit("Error", "#ef4444")
                self.bus.log.emit("! Failed to launch `netbird up`.")
                return

            # start output streaming in background
            threading.Thread(target=_pump_proc_output, args=(proc, self.bus), daemon=True).start()
            # Poll up to 3 minutes for connection
            mgmt = None
            for _ in range(180):
                time.sleep(1)
                rc2, out2, err2 = nb_status(True)
                if rc2 == 0:
                    mgmt = parse_mgmt_url(out2)
                    if mgmt: break

            # Best-effort: drain any output from the `up` command if it ended
            try:
                if proc.poll() is not None:
                    out_up, err_up = proc.communicate(timeout=0.25)
                    if out_up: self.bus.log.emit(out_up)
                    if err_up: self.bus.log.emit(err_up)
            except Exception:
                pass

            if mgmt:
                self.bus.pill.emit("Connected", "#10b981"); self.bus.log.emit(f"✓ Connected to: {mgmt}")
                self.bus.set_active.emit(self.selected_name)
            else:
                self.bus.pill.emit("Connected?", "#f59e0b")
                self.bus.log.emit("i No management URL detected yet. If your browser didn't open, run the same command in a terminal:")
                self.bus.log.emit(f'netbird up --management-url "{url}"')

        self._run_bg(work)

def main():
    app = QtWidgets.QApplication(sys.argv)
    app.setWindowIcon(make_app_icon())
    _require_linux_or_exit()   # Linux-only; no root requirement
    win = MainWindow(); win.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
