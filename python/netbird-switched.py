#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NetBird Environment Switcher
"""

import os, sys, re, json, subprocess, threading, time, shutil
from pathlib import Path
from PySide6 import QtCore, QtGui, QtWidgets

APP_DIR = Path(sys.argv[0]).resolve().parent
ENVS_PATH = APP_DIR / "envs.json"
ELEVATION_FLAG = "--elevated"

# Silence noisy Qt painter warnings
def _qt_msg_handler(mode, context, message):
    if message.startswith("QPainter::"):
        return
    sys.stderr.write(message + "\n")
QtCore.qInstallMessageHandler(_qt_msg_handler)

QtWidgets.QApplication.setStyle("Fusion")

# ---------------- privilege helpers ----------------
def is_admin():
    if sys.platform.startswith("win"):
        try:
            import ctypes
            return bool(ctypes.windll.shell32.IsUserAnAdmin())
        except Exception:
            return False
    else:
        try:
            return os.geteuid() == 0
        except AttributeError:
            return False

def elevate_self():
    script = str(Path(sys.argv[0]).resolve())
    args = [a for a in sys.argv[1:] if a != ELEVATION_FLAG] + [ELEVATION_FLAG]

    if sys.platform.startswith("win"):
        try:
            import ctypes
            params = " ".join(f'"{a}"' for a in [script] + args)
            ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, params, None, 1)
            return True
        except Exception:
            return False

    if sys.platform == "darwin":
        py = sys.executable.replace('"', '\\"'); sc = script.replace('"', '\\"')
        arg_str = " ".join(a.replace('"', '\\"') for a in args)
        osa = f'do shell script "{py} \\"{sc}\\" {arg_str}" with administrator privileges'
        try:
            subprocess.Popen(["osascript", "-e", osa]); return True
        except Exception:
            return False

    pk = shutil.which("pkexec")
    if pk:
        try:
            subprocess.Popen([pk, sys.executable, script] + args); return True
        except Exception:
            return False
    return False

# ---------------- CLI helpers ----------------
def run_cmd(cmd: str, timeout: int = 60):
    try:
        p = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return p.returncode, p.stdout.strip(), p.stderr.strip()
    except Exception as e:
        return 255, "", str(e)

def nb_service_start(): return run_cmd("netbird service start")
def nb_down(): return run_cmd("netbird down")
def nb_up(url: str): return run_cmd(f'netbird up --management-url "{url}"')
def nb_status(detail: bool = True):
    flag = " -d" if detail else ""
    return run_cmd(f"netbird status{flag}")

def parse_mgmt_url(text: str):
    m = re.search(r"Management:\s*Connected(?:\s*to)?\s*(https?://[^\s]+)", text, re.IGNORECASE)
    return m.group(1) if m else None

# Try a list of candidate commands; return first success, else last attempt
def try_cmds(candidates):
    last = None
    for c in candidates:
        rc, out, err = run_cmd(c)
        last = (c, rc, out, err)
        if rc == 0:
            return last
    return last

# -------- routes + networks helpers (best-effort across platforms/versions)
def routes_select_all():
    # Try common variations; logs will show which one hit
    return try_cmds([
        "netbird routes select --all",
        "netbird route select --all",
        "netbird routes enable --all",
        "netbird route enable --all",
        "netbird routes set --all",
    ])

def networks_refresh():
    return try_cmds([
        "netbird networks refresh",
        "netbird network refresh",
        "netbird networks reload",
        "netbird network reload",
        "netbird reload",
    ])

# ---------------- Data I/O ----------------
def ensure_envs_file(path: Path):
    if not path.exists():
        path.write_text("[]", encoding="utf-8")

def load_envs(path: Path):
    ensure_envs_file(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("envs.json must be a JSON array [] of {name, management_url}")
    for i, e in enumerate(data):
        if not isinstance(e, dict) or "name" not in e or "management_url" not in e:
            raise ValueError(f"Item #{i+1} must have 'name' and 'management_url'")
    return data

def save_envs(path: Path, envs: list):
    path.write_text(json.dumps(envs, indent=2), encoding="utf-8")

# ---------------- App icon generator ----------------
def make_app_icon(size=128) -> QtGui.QIcon:
    if getattr(make_app_icon, "_icon", None):
        return make_app_icon._icon
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
        p.setPen(QtGui.QPen(QtGui.QColor("#e5e7eb"))); p.drawText(r, QtCore.Qt.AlignCenter, "NB"); p.end()
    icon = QtGui.QIcon(QtGui.QPixmap.fromImage(img)); make_app_icon._icon = icon; return icon

# ---------------- Env card ----------------
class EnvCard(QtWidgets.QFrame):
    clicked = QtCore.Signal()
    def __init__(self, name: str, selected=False, active=False, parent=None):
        super().__init__(parent)
        self.name, self.selected, self.active = name, selected, active
        self.setCursor(QtCore.Qt.PointingHandCursor)
        self.setMinimumHeight(48)
        self._apply_style(hover=False)
        lay = QtWidgets.QHBoxLayout(self); lay.setContentsMargins(14, 10, 14, 10); lay.setSpacing(10)
        self.lbl = QtWidgets.QLabel(name); self.lbl.setStyleSheet("font-size:14px; font-weight:600; color:#e7e7ea;")
        lay.addWidget(self.lbl); lay.addStretch(1)
        self.badge = QtWidgets.QLabel("Active" if active else "")
        self.badge.setStyleSheet("padding:2px 8px; border-radius:9px; background:#064e3b; color:#a7f3d0; font-weight:600;")
        self.badge.setVisible(active); lay.addWidget(self.badge)
    def setSelected(self, v: bool): self.selected = v; self._apply_style(False)
    def setActive(self, v: bool):
        self.active = v; self.badge.setVisible(v); self.badge.setText("Active" if v else ""); self._apply_style(False)
    def enterEvent(self, e): self._apply_style(True);  return super().enterEvent(e)
    def leaveEvent(self, e): self._apply_style(False); return super().leaveEvent(e)
    def mouseReleaseEvent(self, e):
        if e.button() == QtCore.Qt.LeftButton: self.clicked.emit()
        return super().mouseReleaseEvent(e)
    def _apply_style(self, hover: bool):
        base, hoverc, selectedc, activec, border = "#1a1f29", "#202735", "#273244", "#22303f", "#2a3242"
        bg = activec if self.active else (selectedc if self.selected else (hoverc if hover else base))
        self.setStyleSheet(f"QFrame {{ background:{bg}; border:1px solid {border}; border-radius:12px; }}")

# ---------------- Add/Edit dialogs ----------------
class BaseDialog(QtWidgets.QDialog):
    def _strip_icons(self, button_box: QtWidgets.QDialogButtonBox):
        for std in (QtWidgets.QDialogButtonBox.Ok, QtWidgets.QDialogButtonBox.Cancel):
            btn = button_box.button(std)
            if btn: btn.setIcon(QtGui.QIcon())
    def center_on_screen(self):
        geo = self.frameGeometry(); center = self.screen().availableGeometry().center()
        geo.moveCenter(center); self.move(geo.topLeft())

class AddEnvDialog(BaseDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add Environment"); self.setWindowIcon(make_app_icon())
        self.setModal(True); self.setMinimumSize(680, 220)
        layout = QtWidgets.QFormLayout(self); layout.setHorizontalSpacing(16); layout.setVerticalSpacing(12)
        self.name = QtWidgets.QLineEdit(); self.url = QtWidgets.QLineEdit()
        self.name.setPlaceholderText("e.g., CCSTG"); self.url.setPlaceholderText("https://host:443")
        layout.addRow("Name", self.name); layout.addRow("Management URL", self.url)
        btns = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept); btns.rejected.connect(self.reject); layout.addRow(btns); self._strip_icons(btns)
        QtCore.QTimer.singleShot(0, self.center_on_screen)
    def get(self): return self.name.text().strip(), self.url.text().strip()

class EditEnvDialog(BaseDialog):
    def __init__(self, name: str, current_url: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Edit {name}"); self.setWindowIcon(make_app_icon())
        self.setModal(True); self.setMinimumSize(680, 220)
        layout = QtWidgets.QFormLayout(self); layout.setHorizontalSpacing(16); layout.setVerticalSpacing(12)
        self.name_label = QtWidgets.QLabel(name); self.url = QtWidgets.QLineEdit(current_url); self.url.setPlaceholderText("https://host:443")
        layout.addRow("Name", self.name_label); layout.addRow("Management URL", self.url)
        btns = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept); btns.rejected.connect(self.reject); layout.addRow(btns); self._strip_icons(btns)
        QtCore.QTimer.singleShot(0, self.center_on_screen)
    def get(self): return self.url.text().strip()

# ---------------- Icon-less message boxes ----------------
def ask_yes_no(parent, title, text, default_yes=True):
    box = QtWidgets.QMessageBox(parent); box.setWindowTitle(title); box.setText(text)
    box.setWindowIcon(make_app_icon()); box.setIcon(QtWidgets.QMessageBox.NoIcon)
    box.setStandardButtons(QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No)
    box.setDefaultButton(QtWidgets.QMessageBox.Yes if default_yes else QtWidgets.QMessageBox.No)
    box.setStyleSheet("QLabel{color:#e5e7eb;} QMessageBox{background:#0d1117;}"); return box.exec()
def info_box(parent, title, text):
    b = QtWidgets.QMessageBox(parent); b.setWindowTitle(title); b.setText(text)
    b.setWindowIcon(make_app_icon()); b.setIcon(QtWidgets.QMessageBox.NoIcon)
    b.setStyleSheet("QLabel{color:#e5e7eb;} QMessageBox{background:#0d1117;}"); b.setStandardButtons(QtWidgets.QMessageBox.Ok); return b.exec()
def warn_box(parent, title, text):
    b = QtWidgets.QMessageBox(parent); b.setWindowTitle(title); b.setText(text)
    b.setWindowIcon(make_app_icon()); b.setIcon(QtWidgets.QMessageBox.NoIcon)
    b.setStyleSheet("QLabel{color:#e5e7eb;} QMessageBox{background:#0d1117;}"); b.setStandardButtons(QtWidgets.QMessageBox.Ok); return b.exec()

# ---------------- UI bus ----------------
class UIBus(QtCore.QObject):
    log = QtCore.Signal(str)
    pill = QtCore.Signal(str, str)
    set_active = QtCore.Signal(object)   # name or None
    set_enabled = QtCore.Signal(bool)
    rebuild = QtCore.Signal()

# ---------------- Main window ----------------
class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("NetBird Switcher"); self.setWindowIcon(make_app_icon())
        self.resize(1040, 700)
        self.selected_name = None; self.active_name = None; self.busy = False

        self._apply_dark_palette(); self._build()
        self.bus = UIBus(); self._wire_bus()
        self._maybe_prompt_elevate(); self._load_envs_initial()

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
        self.cards_layout = QtWidgets.QVBoxLayout(self.cards_container); self.cards_layout.setContentsMargins(6, 6, 6, 6); self.cards_layout.setSpacing(10)
        scroll = QtWidgets.QScrollArea(); scroll.setWidgetResizable(True); scroll.setWidget(self.cards_container); scroll.setStyleSheet("QScrollArea{border:1px solid #2a3242; border-radius:10px; background:#0f141b;}")
        middle.addWidget(scroll, 1)

        right = QtWidgets.QVBoxLayout()
        # Connection actions
        self.btn_connect = QtWidgets.QPushButton("Connect"); self.btn_connect.setStyleSheet("QPushButton{background:#0d382e; color:#a7f3d0; border:1px solid #164e3f; font-weight:700; padding:14px 18px; border-radius:12px;} QPushButton:hover{background:#115e49;}")
        self.btn_disconnect = QtWidgets.QPushButton("Disconnect"); self.btn_status = QtWidgets.QPushButton("Status")
        self.btn_connect.clicked.connect(self.on_connect); self.btn_disconnect.clicked.connect(self.on_disconnect); self.btn_status.clicked.connect(self.on_status)
        for b in (self.btn_connect, self.btn_disconnect, self.btn_status): right.addWidget(b); right.addSpacing(8)

        # Separator
        sep = QtWidgets.QFrame(); sep.setFrameShape(QtWidgets.QFrame.HLine); sep.setStyleSheet("color:#2a3242;")
        right.addWidget(sep); right.addSpacing(4)

        # Manage environments
        manage_lbl = QtWidgets.QLabel("Manage environments"); manage_lbl.setStyleSheet("font-weight:700; color:#cbd5e1;")
        right.addWidget(manage_lbl)
        self.btn_add = QtWidgets.QPushButton("Add")
        self.btn_edit = QtWidgets.QPushButton("Edit URL")
        self.btn_remove = QtWidgets.QPushButton("Remove")
        self.btn_add.clicked.connect(self.on_add); self.btn_edit.clicked.connect(self.on_edit); self.btn_remove.clicked.connect(self.on_remove)
        right.addWidget(self.btn_add); right.addSpacing(6); right.addWidget(self.btn_edit); right.addSpacing(6); right.addWidget(self.btn_remove)

        # Networks tools
        right.addSpacing(10)
        nets_lbl = QtWidgets.QLabel("Networks"); nets_lbl.setStyleSheet("font-weight:700; color:#cbd5e1;")
        right.addWidget(nets_lbl)
        self.btn_refresh = QtWidgets.QPushButton("Refresh Networks")
        self.btn_refresh.setToolTip("Select all routes then refresh networks")
        self.btn_refresh.clicked.connect(self.on_refresh_networks)
        right.addWidget(self.btn_refresh)

        right.addStretch(1); middle.addLayout(right, 0)
        outer.addLayout(middle, 1)

        # Log
        outer.addWidget(QtWidgets.QLabel("Activity Log"))
        self.log = QtWidgets.QPlainTextEdit(); self.log.setReadOnly(True); outer.addWidget(self.log, 2)

        # Shortcuts
        QtGui.QShortcut(QtGui.QKeySequence("Return"), self, activated=self.on_connect)
        QtGui.QShortcut(QtGui.QKeySequence("Ctrl+F"), self, activated=self.search.setFocus)

    def _maybe_prompt_elevate(self):
        if ELEVATION_FLAG in sys.argv or is_admin(): return
        msg = ("To manage the NetBird service, elevated privileges are recommended.\n\n"
               "Relaunch the app with admin/root privileges?")
        ret = ask_yes_no(self, "Administrator privileges", msg, default_yes=True)
        if ret == QtWidgets.QMessageBox.Yes:
            if elevate_self():
                QtCore.QTimer.singleShot(50, QtWidgets.QApplication.instance().quit)
            else:
                warn_box(self, "Relaunch failed", "Auto-elevation is not available. Please reopen as admin/root.")

    # ----- load & render -----
    def _load_envs_initial(self):
        try:
            self.envs = load_envs(ENVS_PATH)
        except Exception as e:
            warn_box(self, "envs.json error", str(e))
            try:
                ENVS_PATH.write_text("[]", encoding="utf-8"); self.envs = []
            except Exception:
                sys.exit(2)
        self.filtered = list(self.envs); self._rebuild_cards()
        if not self.envs:
            info_box(self, "Empty list", f"No environments found.\nUse 'Add' to create entries in:\n{ENVS_PATH}")

    def _rebuild_cards(self):
        while self.cards_layout.count():
            item = self.cards_layout.takeAt(0); w = item.widget()
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

    @QtCore.Slot(str)
    def _log(self, text: str):
        self.log.appendPlainText(text)
        self.log.verticalScrollBar().setValue(self.log.verticalScrollBar().maximum())

    @QtCore.Slot(str, str)
    def _set_pill(self, text: str, color: str):
        self.pill.setText(f" {text} ")
        self.pill.setStyleSheet(f"background:{color}; color:#0b1220; padding:6px 12px; border-radius:12px; font-weight:700;")

    # ----- manage -----
    def on_add(self):
        dlg = AddEnvDialog(self)
        if dlg.exec() == QtWidgets.QDialog.Accepted:
            name, url = dlg.get()
            if not name or not url or not re.match(r"^https?://", url):
                warn_box(self, "Invalid", "Please enter a name and a valid Management URL (http/https)."); return
            exists = next((e for e in self.envs if e["name"].lower() == name.lower()), None)
            if exists:
                ret = ask_yes_no(self, "Overwrite?", f"Environment '{name}' exists. Overwrite its URL?", default_yes=False)
                if ret != QtWidgets.QMessageBox.Yes: return
                exists["management_url"] = url
            else:
                self.envs.append({"name": name, "management_url": url})
            try:
                save_envs(ENVS_PATH, self.envs); self._log(f"✓ Saved '{name}' to {ENVS_PATH}")
                self._on_filter(self.search.text())
            except Exception as e:
                warn_box(self, "Save failed", str(e))

    def on_edit(self):
        if not self.selected_name:
            info_box(self, "Select", "Pick an environment card first."); return
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
        if not self.selected_name:
            info_box(self, "Select", "Pick an environment card first."); return
        name = self.selected_name
        ret = ask_yes_no(self, "Remove environment", f"Delete '{name}' from the list?", default_yes=False)
        if ret != QtWidgets.QMessageBox.Yes: return
        # Remove
        before = len(self.envs)
        self.envs = [e for e in self.envs if e["name"] != name]
        try:
            save_envs(ENVS_PATH, self.envs)
            self._log(f"✓ Removed '{name}' from {ENVS_PATH}")
            if self.active_name == name: self.active_name = None
            self.selected_name = None
            self.filtered = list(self.envs)
            self._rebuild_cards()
        except Exception as e:
            warn_box(self, "Save failed", str(e))
        if len(self.envs) == before:
            self._log("i Nothing removed (name not found).")

    # ----- helpers -----
    def _ensure_down_quick(self, max_wait=2.0, step=0.2):
        rc0, out0, err0 = nb_status(True)
        if rc0 == 0 and parse_mgmt_url(out0) is None:
            return
        nb_down()
        t_end = time.time() + max_wait
        while time.time() < t_end:
            rc, out, err = nb_status(True)
            if rc != 0 or parse_mgmt_url(out) is None:
                break
            time.sleep(step)

    def _run_bg(self, fn):
        if self.busy: return
        self.busy = True; self.bus.set_enabled.emit(False)
        def wrapper():
            try:
                fn()
            finally:
                self.bus.set_enabled.emit(True)
                self.busy = False
        threading.Thread(target=wrapper, daemon=True).start()

    # ----- networks refresh -----
    def on_refresh_networks(self):
        def work():
            self.bus.pill.emit("Refreshing…", "#0ea5a0")
            self.bus.log.emit("Selecting all routes…")
            cmd, rc, out, err = routes_select_all()
            if rc == 0:
                self.bus.log.emit(f"✓ Routes selected via: {cmd}")
                if out: self.bus.log.emit(out)
            else:
                self.bus.log.emit(f"! Route select failed via: {cmd} (rc={rc})")
                self.bus.log.emit(err or out or "no output")
            self.bus.log.emit("Refreshing networks…")
            cmd2, rc2, out2, err2 = networks_refresh()
            if rc2 == 0:
                self.bus.log.emit(f"✓ Networks refreshed via: {cmd2}")
                if out2: self.bus.log.emit(out2)
                self.bus.pill.emit("Refreshed", "#10b981")
            else:
                self.bus.log.emit(f"! Network refresh failed via: {cmd2} (rc={rc2})")
                self.bus.log.emit(err2 or out2 or "no output")
                self.bus.pill.emit("Refresh failed", "#ef4444")
        self._run_bg(work)

    # ----- connect/status actions -----
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
        if not self.selected_name:
            info_box(self, "Select", "Pick an environment card first."); return
        def work():
            self.bus.pill.emit("Disconnecting…", "#f59e0b")
            rc, out, err = nb_down()
            self.bus.set_active.emit(None)
            if rc == 0:
                self.bus.pill.emit("Disconnected", "#6b7280"); self.bus.log.emit("✓ Disconnected.")
            else:
                self.bus.pill.emit("Error", "#ef4444"); self.bus.log.emit(f"down failed (rc={rc}): {err or out}")
        self._run_bg(work)

    def on_connect(self):
        if not self.selected_name:
            info_box(self, "Select", "Pick an environment card first."); return
        env = next(e for e in self.envs if e["name"] == self.selected_name)
        name, url = env["name"], env["management_url"]
        def work():
            self.bus.pill.emit("Connecting…", "#0ea5a0")
            self.bus.log.emit(f"Connecting to {name} ...")
            rc, out, err = nb_service_start()
            if rc == 0: self.bus.log.emit("✓ Service started (or already running).")
            elif "already running" in (err or out): self.bus.log.emit("i Service is already running.")
            else: self.bus.log.emit(f"service start (rc={rc}): {err or out}")
            self.bus.log.emit("Resetting session...")
            self._ensure_down_quick(max_wait=2.0, step=0.2)
            rc, out, err = nb_up(url)
            if rc == 0:
                self.bus.log.emit("✓ up OK. Waiting for authentication/handshake...")
                mgmt = None
                for _ in range(60):
                    time.sleep(1)
                    rc2, out2, err2 = nb_status(True)
                    if rc2 == 0:
                        mgmt = parse_mgmt_url(out2)
                        if mgmt: break
                if mgmt:
                    self.bus.pill.emit("Connected", "#10b981")
                    self.bus.log.emit(f"✓ Connected to: {mgmt}")
                    self.bus.set_active.emit(self.selected_name)
                else:
                    self.bus.pill.emit("Connected?", "#f59e0b")
                    self.bus.log.emit("i No management URL detected yet. Sign-in window may still be open.")
            else:
                self.bus.pill.emit("Error", "#ef4444"); self.bus.log.emit(f"up failed (rc={rc}): {err or out}")
        self._run_bg(work)

def main():
    app = QtWidgets.QApplication(sys.argv)
    app.setWindowIcon(make_app_icon())
    win = MainWindow(); win.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()

