"""
ControllerSupercharge by Christian Pruitt -- a friendly front end for SweetLow's hidusbf driver.

Tab 1 sets the USB polling rate of a controller.
Tab 2 shows the controller live and measures its real polling rate.
"""
import ctypes
import os
import sys
import webbrowser
import threading
import tkinter as tk
from tkinter import messagebox, ttk

import hidusbf_backend as hb
import xinput

try:
    import pystray
    from PIL import Image, ImageTk
except ImportError:  # tray is optional when running from source
    pystray = None

APP_NAME = "ControllerSupercharge"
AUTHOR = "Christian Pruitt"
REPO_URL = "https://github.com/SyncedCyberSoul/controllerSupercharge"

BG = "#1b1c1f"
PANEL = "#26282c"
PANEL2 = "#2f3237"
TEXT = "#ececec"
MUTED = "#9aa0a6"
ACCENT = "#4f8cff"
GOOD = "#3fb950"
BAD = "#f85149"
WARN = "#e3b341"
BODY = "#1f2023"
BODY_EDGE = "#3a3d42"
IDLE = "#55585e"
LIT = "#f2f2f2"

RATE_CHOICES = [("Default", None), ("125 Hz", 125), ("250 Hz", 250), ("500 Hz", 500), ("1000 Hz", 1000)]


def relaunch_as_admin():
    if getattr(sys, "frozen", False):
        exe, params = sys.executable, " ".join(f'"{a}"' for a in sys.argv[1:])
    else:
        exe, params = sys.executable, " ".join(f'"{a}"' for a in sys.argv)
    rc = ctypes.windll.shell32.ShellExecuteW(None, "runas", exe, params, None, 1)
    return rc > 32


def rrect_points(x1, y1, x2, y2, r):
    return [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2,
            x2 - r, y2, x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]


# ==========================================================================
# Tab 1: polling rate
# ==========================================================================
class RateTab(tk.Frame):
    def __init__(self, master, app):
        super().__init__(master, bg=BG)
        self.app = app
        self.devices = []
        self.busy = False

        # --- driver card ------------------------------------------------
        card = tk.Frame(self, bg=PANEL, padx=16, pady=12)
        card.pack(fill="x", padx=16, pady=(14, 8))
        tk.Label(card, text="1  Driver", bg=PANEL, fg=TEXT, font=("Segoe UI Semibold", 12)).grid(
            row=0, column=0, sticky="w")
        self.driver_lbl = tk.Label(card, text="Checking...", bg=PANEL, fg=MUTED, font=("Segoe UI", 10))
        self.driver_lbl.grid(row=1, column=0, sticky="w", pady=(2, 0))

        right = tk.Frame(card, bg=PANEL)
        right.grid(row=0, column=1, rowspan=2, sticky="e")
        card.columnconfigure(0, weight=1)
        self.variant = tk.StringVar(value="nopatch")
        self.variant_box = ttk.Combobox(right, state="readonly", width=20,
                                        values=[hb.VARIANTS[v][0] for v in hb.VARIANTS])
        self.variant_box.current(0)
        self.variant_box.bind("<<ComboboxSelected>>", self._variant_changed)
        self.variant_box.pack(side="left", padx=(0, 8))
        self.install_btn = ttk.Button(right, text="Install driver", style="Accent.TButton",
                                      command=self.install_driver)
        self.install_btn.pack(side="left", padx=(0, 6))
        self.uninstall_btn = ttk.Button(right, text="Remove all", command=self.uninstall_driver)
        self.uninstall_btn.pack(side="left")
        self.variant_hint = tk.Label(card, text=hb.VARIANTS["nopatch"][1], bg=PANEL, fg=MUTED,
                                     font=("Segoe UI", 9))
        self.variant_hint.grid(row=2, column=0, columnspan=2, sticky="w", pady=(6, 0))

        # --- device list --------------------------------------------------
        card2 = tk.Frame(self, bg=PANEL, padx=16, pady=12)
        card2.pack(fill="x", padx=16, pady=8)
        top = tk.Frame(card2, bg=PANEL)
        top.pack(fill="x")
        tk.Label(top, text="2  Pick the controller", bg=PANEL, fg=TEXT,
                 font=("Segoe UI Semibold", 12)).pack(side="left")
        ttk.Button(top, text="Refresh", command=self.refresh).pack(side="right")
        self.show_all = tk.BooleanVar(value=False)
        ttk.Checkbutton(top, text="Show all USB devices", variable=self.show_all,
                        command=self.populate, style="Panel.TCheckbutton").pack(side="right", padx=10)

        cols = ("rate", "id")
        self.tree = ttk.Treeview(card2, columns=cols, height=4, selectmode="browse")
        self.tree.heading("#0", text="Device")
        self.tree.heading("rate", text="Polling rate")
        self.tree.heading("id", text="VID:PID")
        self.tree.column("#0", width=430)
        self.tree.column("rate", width=170, anchor="center")
        self.tree.column("id", width=110, anchor="center")
        self.tree.pack(fill="x", pady=(8, 0))
        self.tree.bind("<<TreeviewSelect>>", lambda e: self._selection_changed())
        self.empty_lbl = tk.Label(card2, text="", bg=PANEL, fg=MUTED, font=("Segoe UI", 9))
        self.empty_lbl.pack(anchor="w", pady=(6, 0))

        # --- rate + apply ----------------------------------------------------
        card3 = tk.Frame(self, bg=PANEL, padx=16, pady=12)
        card3.pack(fill="x", padx=16, pady=(8, 14))
        tk.Label(card3, text="3  Choose a rate", bg=PANEL, fg=TEXT,
                 font=("Segoe UI Semibold", 12)).grid(row=0, column=0, sticky="w")
        seg = tk.Frame(card3, bg=PANEL)
        seg.grid(row=1, column=0, sticky="w", pady=(8, 4))
        self.rate = tk.StringVar(value="1000")
        for label, val in RATE_CHOICES:
            ttk.Radiobutton(seg, text=label, value=str(val), variable=self.rate,
                            style="Seg.Toolbutton").pack(side="left", padx=(0, 4))
        tk.Label(card3, text="Higher = less input delay (1000 Hz = 1 ms). 1000 Hz is the max for most controllers.",
                 bg=PANEL, fg=MUTED, font=("Segoe UI", 9)).grid(row=4, column=0, sticky="w", pady=(2, 0))
        self.composite = tk.BooleanVar(value=False)
        self.composite_chk = ttk.Checkbutton(
            card3, text="Apply to the whole composite device (try this if the rate doesn't change)",
            variable=self.composite, style="Panel.TCheckbutton")
        self.composite_chk.grid(row=5, column=0, sticky="w", pady=(6, 0))

        self.apply_btn = ttk.Button(card3, text="Apply", style="Big.TButton", command=self.apply)
        self.apply_btn.grid(row=0, column=1, rowspan=6, sticky="nse", padx=(12, 0))
        card3.columnconfigure(0, weight=1)
        self.status = tk.Label(card3, text="", bg=PANEL, fg=MUTED, font=("Segoe UI", 10),
                               justify="left", wraplength=int(900 * app.S), anchor="w")
        self.status.grid(row=6, column=0, columnspan=2, sticky="we", pady=(10, 0))

        tips = tk.Frame(self, bg=BG, padx=4)
        tips.pack(fill="x", padx=16, pady=(0, 10))
        tk.Label(tips, text="Tip: run the polling test on the Live Test tab before and after, to see the "
                            "difference.", bg=BG, fg=MUTED, font=("Segoe UI", 9)).pack(side="left")
        ttk.Button(tips, text="Open Live Test  →", command=lambda: master.select(1)).pack(side="right")

        if not hb.is_admin():
            self.say("Not running as administrator - you can look around, but changes are disabled.", WARN)
            for b in (self.install_btn, self.uninstall_btn, self.apply_btn):
                b.state(["disabled"])

        self.after(50, self.refresh)

    # ------------------------------------------------------------------ helpers
    def say(self, text, color=MUTED):
        self.status.config(text=text, fg=color)

    def run_bg(self, work, done):
        """Runs work() on a thread, then done(result) on the UI thread."""
        if self.busy:
            return
        self.busy = True
        self.app.config(cursor="watch")

        def wrapper():
            try:
                res = (True, work())
            except Exception as e:  # surface every failure to the user
                res = (False, e)
            self.after(0, finish, res)

        def finish(res):
            self.busy = False
            self.app.config(cursor="")
            ok, val = res
            if ok:
                done(val)
            else:
                self.say(f"Error: {val}", BAD)

        threading.Thread(target=wrapper, daemon=True).start()

    def _variant_changed(self, _=None):
        v = list(hb.VARIANTS)[self.variant_box.current()]
        self.variant.set(v)
        self.variant_hint.config(text=hb.VARIANTS[v][1])
        self.update_driver_status()

    # ------------------------------------------------------------------ driver
    def update_driver_status(self):
        def work():
            return hb.service_state(), hb.installed_variant(), hb.memory_integrity_on()

        def done(res):
            state, variant, hvci = res
            self.hvci = hvci
            if state == "missing" or variant is None:
                self.driver_lbl.config(text="Not installed yet - click Install driver.", fg=WARN)
                self.install_btn.config(text="Install driver")
            elif state == "disabled":
                self.driver_lbl.config(text="Installed but disabled. Click Reinstall.", fg=BAD)
                self.install_btn.config(text="Reinstall")
            else:
                name = hb.VARIANTS.get(variant, ("Unknown version",))[0]
                txt = f"Installed ({name})" + (" - loaded" if state == "running" else "")
                self.driver_lbl.config(text=txt, fg=GOOD)
                self.install_btn.config(
                    text="Reinstall" if variant == self.variant.get() else f"Switch to {hb.VARIANTS[self.variant.get()][0]}")
            if hvci and self.variant.get() != "nopatch":
                self.variant_hint.config(
                    text="Memory Integrity is ON on this PC - the patching driver won't load. Use Standard.",
                    fg=BAD)
            else:
                self.variant_hint.config(text=hb.VARIANTS[self.variant.get()][1], fg=MUTED)

        threading.Thread(target=lambda: self.after(0, done, work()), daemon=True).start()

    def install_driver(self):
        v = self.variant.get()
        self.say("Installing driver...")
        self.run_bg(lambda: hb.install_service(v), self._installed)

    def _installed(self, res):
        ok, msg = res
        self.say(msg, GOOD if ok else BAD)
        self.update_driver_status()

    def uninstall_driver(self):
        if not messagebox.askyesno(APP_NAME, "Remove the polling-rate filter from every device and "
                                             "uninstall the hidusbf driver?\n\nAll controllers go back "
                                             "to their default rate."):
            return
        self.say("Removing...")
        self.run_bg(hb.uninstall_service, lambda msg: (self.say(msg, GOOD), self.update_driver_status(),
                                                        self.refresh()))

    # ------------------------------------------------------------------ devices
    def refresh(self):
        self.update_driver_status()
        self.run_bg(lambda: [(d, d.current()) for d in hb.scan_devices()], self._scanned)

    def _scanned(self, items):
        self.devices = items
        self.populate()

    def populate(self):
        prev = self.tree.selection()
        self.tree.delete(*self.tree.get_children())
        shown = 0
        for i, (d, (has, rate, where)) in enumerate(self.devices):
            if not self.show_all.get() and not d.is_controller:
                continue
            if has:
                rtxt = f"{rate} Hz (boosted)" if rate else "Filter on (custom)"
            else:
                rtxt = "Default"
            name = d.name
            if d.generic_name and d.generic_name != d.name and self.show_all.get():
                name = f"{d.name}  -  {d.generic_name}"
            if d.problem():
                name += "   [device has a problem]"
            self.tree.insert("", "end", iid=str(i), text=("🎮  " if d.is_controller else "      ") + name,
                             values=(rtxt, d.vidpid))
            shown += 1
        if shown == 0:
            self.empty_lbl.config(text="No controllers found. Plug it in with a USB cable, then Refresh - "
                                       "or tick 'Show all USB devices'.")
        else:
            self.empty_lbl.config(text="Wireless dongles count too. Bluetooth connections can't be changed.")
        if prev and self.tree.exists(prev[0]):
            self.tree.selection_set(prev[0])
        elif shown:
            self.tree.selection_set(self.tree.get_children()[0])
        self._selection_changed()

    def selected(self):
        sel = self.tree.selection()
        return self.devices[int(sel[0])] if sel else (None, None)

    def _selection_changed(self):
        d, cur = self.selected()
        if d is None:
            return
        has, rate, where = cur
        self.composite.set(where == "parent")
        self.composite_chk.state(["!disabled"] if d.is_composite_child else ["disabled"])
        if has and rate:
            self.rate.set(str(rate))

    # ------------------------------------------------------------------ apply
    def apply(self):
        d, cur = self.selected()
        if d is None:
            self.say("Pick a device first.", WARN)
            return
        rate = None if self.rate.get() == "None" else int(self.rate.get())
        state = hb.service_state()
        if rate is not None and state in ("missing", "disabled"):
            if not messagebox.askyesno(APP_NAME, "The driver isn't installed yet. Install it now?"):
                return
            ok, msg = hb.install_service(self.variant.get())
            self.update_driver_status()
            if not ok:
                self.say(msg, BAD)
                return
        use_parent = self.composite.get() and d.is_composite_child

        def work():
            target_dn, _ = d.filter_target(use_parent)
            other_dn, _ = d.filter_target(not use_parent)
            if other_dn != target_dn:
                hb.set_filter(other_dn, None)  # never leave it on both levels
            hb.set_filter(target_dn, rate)
            restart_id = d.parent_id if d.is_composite_child else d.instance_id
            return hb.restart_device(restart_id)

        def done(res):
            ok, reboot, out = res
            what = "back to default" if rate is None else f"set to {rate} Hz"
            if ok and not reboot:
                self.say(f"Done - {d.name} is {what}. Run the test on the Live Test tab to confirm "
                         "(unplug and replug if it looks unchanged).", GOOD)
            elif ok:
                self.say(f"Saved ({what}). Windows needs a reboot - or unplug and replug the controller.", WARN)
            else:
                self.say(f"Saved ({what}), but the device couldn't be restarted automatically. "
                         "Unplug and replug the controller to apply.", WARN)
            self.refresh()

        self.say("Applying...")
        self.run_bg(work, done)


# ==========================================================================
# Tab 2: live controller view + polling test
# ==========================================================================
class LiveTab(tk.Frame):
    W, H = 980, 440
    LIFT = 40

    def __init__(self, master, app):
        super().__init__(master, bg=BG)
        self.app = app
        self.slot = 0
        self.sampler = xinput.Sampler()
        self.S = app.S
        self.c = tk.Canvas(self, width=int(self.W * self.S), height=int(self.H * self.S), bg=BG,
                           highlightthickness=0)
        self.c.pack(padx=8, pady=(8, 0))
        self._build_canvas()
        hdr = set(self.c.find_withtag("hdr"))
        for item in self.c.find_all():  # pull the controller graphic up under the header
            if item not in hdr:
                self.c.move(item, 0, -self.LIFT)
        self.c.scale("all", 0, 0, self.S, self.S)  # draw in logical units, then scale once

        bottom = tk.Frame(self, bg=PANEL, padx=16, pady=12)
        bottom.pack(fill="x", padx=16, pady=(4, 14))
        left = tk.Frame(bottom, bg=PANEL)
        left.pack(side="left", fill="x", expand=True)
        tk.Label(left, text="Polling rate test", bg=PANEL, fg=TEXT,
                 font=("Segoe UI Semibold", 12)).pack(anchor="w")
        tk.Label(left, text="Press Start, then spin a stick in fast circles for 5 seconds.",
                 bg=PANEL, fg=MUTED, font=("Segoe UI", 9)).pack(anchor="w")
        self.progress = ttk.Progressbar(left, length=420, mode="determinate", maximum=1.0)
        self.progress.pack(anchor="w", pady=(8, 4))
        self.result_lbl = tk.Label(left, text="", bg=PANEL, fg=MUTED, font=("Segoe UI", 10), justify="left")
        self.result_lbl.pack(anchor="w")
        self.prev_lbl = tk.Label(left, text="", bg=PANEL, fg=MUTED, font=("Segoe UI", 9))
        self.prev_lbl.pack(anchor="w")
        self.last_result = None

        mid = tk.Frame(bottom, bg=PANEL)
        mid.pack(side="left", padx=20)
        self.big_hz = tk.Label(mid, text="--", bg=PANEL, fg=TEXT, font=("Segoe UI Semibold", 30))
        self.big_hz.pack()
        self.big_sub = tk.Label(mid, text="live estimate", bg=PANEL, fg=MUTED, font=("Segoe UI", 9))
        self.big_sub.pack()

        right = tk.Frame(bottom, bg=PANEL)
        right.pack(side="right")
        self.test_btn = ttk.Button(right, text="Start 5-second test", style="Accent.TButton",
                                   command=self.start_test)
        self.test_btn.pack(fill="x", pady=(0, 6))
        ttk.Button(right, text="Rumble test", command=self.rumble).pack(fill="x")

        if not xinput.AVAILABLE:
            self.result_lbl.config(text="XInput isn't available on this PC.", fg=BAD)
        self._tick()

    # ---------------------------------------------------------------- drawing
    def _build_canvas(self):
        c = self.c
        cx = self.W // 2
        # slots
        self.slot_items = []
        c.create_text(110, 70, text="Connected controllers", fill=MUTED, font=("Segoe UI", 9), tags="hdr")
        for i in range(4):
            x = 38 + i * 48
            r = c.create_polygon(rrect_points(x, 18, x + 40, 52, 10), smooth=True, fill=PANEL2,
                                 outline=BODY_EDGE, width=2, tags="hdr")
            t = c.create_text(x + 20, 35, text=str(i + 1), fill=MUTED, font=("Segoe UI Semibold", 12), tags="hdr")
            for item in (r, t):
                c.tag_bind(item, "<Button-1>", lambda e, s=i: self.select_slot(s))
                c.tag_bind(item, "<Enter>", lambda e: c.config(cursor="hand2"))
                c.tag_bind(item, "<Leave>", lambda e: c.config(cursor=""))
            self.slot_items.append((r, t))
        self.title = c.create_text(cx, 30, text="Controller 1", fill=TEXT, font=("Segoe UI Light", 24), tags="hdr")
        self.subtitle = c.create_text(cx, 72, text="", fill=MUTED, font=("Segoe UI", 11), tags="hdr")
        self.batt = c.create_text(self.W - 40, 32, text="", fill=MUTED, font=("Segoe UI", 10), anchor="e", tags="hdr")

        # bumpers (behind body)
        self.lb = c.create_polygon(rrect_points(335, 168, 438, 196, 12), smooth=True, fill=IDLE)
        self.rb = c.create_polygon(rrect_points(542, 168, 645, 196, 12), smooth=True, fill=IDLE)
        c.create_text(386, 160, text="LB", fill=MUTED, font=("Segoe UI", 8))
        c.create_text(594, 160, text="RB", fill=MUTED, font=("Segoe UI", 8))

        body = [380, 186, 435, 180, 545, 180, 600, 186, 652, 204, 684, 255, 708, 345, 720, 420, 700, 458,
                656, 460, 618, 414, 588, 380, 392, 380, 362, 414, 324, 460, 280, 458, 260, 420, 272, 345,
                296, 255, 328, 204]
        c.create_polygon(body, smooth=True, fill=BODY, outline=BODY_EDGE, width=2)

        # sticks on the body
        self.ls_well = c.create_oval(*self._circ(400, 262, 32), fill="#141517", outline=BODY_EDGE)
        self.ls_cap = c.create_oval(*self._circ(400, 262, 22), fill=IDLE, outline="")
        self.rs_well = c.create_oval(*self._circ(538, 334, 32), fill="#141517", outline=BODY_EDGE)
        self.rs_cap = c.create_oval(*self._circ(538, 334, 22), fill=IDLE, outline="")

        # d-pad
        dx, dy = 442, 334
        self.dpad = {
            "up": c.create_rectangle(dx - 9, dy - 30, dx + 9, dy - 9, fill=IDLE, outline=""),
            "down": c.create_rectangle(dx - 9, dy + 9, dx + 9, dy + 30, fill=IDLE, outline=""),
            "left": c.create_rectangle(dx - 30, dy - 9, dx - 9, dy + 9, fill=IDLE, outline=""),
            "right": c.create_rectangle(dx + 9, dy - 9, dx + 30, dy + 9, fill=IDLE, outline=""),
        }
        c.create_rectangle(dx - 9, dy - 9, dx + 9, dy + 9, fill=IDLE, outline="")

        # face buttons
        fx, fy, o = 582, 262, 26
        self.face = {}
        face_def = {"y": (fx, fy - o, "#e3b341"), "b": (fx + o, fy, "#f85149"),
                    "a": (fx, fy + o, "#3fb950"), "x": (fx - o, fy, "#4f8cff")}
        for k, (x, y, col) in face_def.items():
            oval = c.create_oval(*self._circ(x, y, 13), fill=self._dim(col), outline="")
            c.create_text(x, y, text=k.upper(), fill="#101114", font=("Segoe UI Semibold", 9))
            self.face[k] = (oval, col)

        # back / start / guide
        self.back = c.create_oval(*self._circ(460, 252, 8), fill=IDLE, outline="")
        self.start = c.create_oval(*self._circ(520, 252, 8), fill=IDLE, outline="")
        self.guide = c.create_oval(*self._circ(490, 212, 15), fill=IDLE, outline=BODY_EDGE, width=2)

        # triggers
        self.trig = {}
        for key, x in (("lt", 236), ("rt", 744)):
            c.create_rectangle(x - 9, 150, x + 9, 400, outline=MUTED, width=1)
            fill = c.create_rectangle(x - 8, 399, x + 8, 399, fill=ACCENT, outline="")
            pct = c.create_text(x, 416, text="0%", fill=MUTED, font=("Segoe UI", 9))
            c.create_text(x, 138, text=key.upper(), fill=MUTED, font=("Segoe UI", 9))
            self.trig[key] = (fill, pct)

        # big stick visualizers
        self.vis = {}
        for key, x, title in (("l", 112, "Left stick"), ("r", 868, "Right stick")):
            c.create_text(x, 150, text=title, fill=TEXT, font=("Segoe UI", 12))
            c.create_oval(*self._circ(x, 290, 72), outline=MUTED, width=2)
            c.create_oval(*self._circ(x, 290, 72 * 0.24), outline=PANEL2, dash=(2, 3))  # ~deadzone
            c.create_line(x - 72, 290, x + 72, 290, fill=PANEL2)
            c.create_line(x, 218, x, 362, fill=PANEL2)
            trail = c.create_line(x, 290, x, 290, fill=ACCENT, width=2, smooth=True)
            dot = c.create_oval(*self._circ(x, 290, 7), fill=LIT, outline="")
            xy = c.create_text(x, 385, text="X 0%   ·   Y 0%", fill=MUTED, font=("Segoe UI", 10))
            self.vis[key] = {"x": x, "dot": dot, "xy": xy, "trail": trail, "pts": []}

        self.hint = c.create_text(cx, 448, text="", fill=MUTED, font=("Segoe UI", 10))

    def _co(self, item, *pts):
        """coords() in logical units."""
        self.c.coords(item, *[(p if i % 2 == 0 else p - self.LIFT) * self.S for i, p in enumerate(pts)])

    @staticmethod
    def _circ(x, y, r):
        return x - r, y - r, x + r, y + r

    @staticmethod
    def _dim(col):
        r, g, b = (int(col[i:i + 2], 16) for i in (1, 3, 5))
        return "#%02x%02x%02x" % (int(r * 0.35), int(g * 0.35), int(b * 0.35))

    # ---------------------------------------------------------------- actions
    def set_paused(self, paused):
        self.paused = paused
        self.sampler.paused = paused

    def select_slot(self, s):
        self.slot = s
        self.sampler.set_live_slot(s)
        for v in self.vis.values():
            v["pts"].clear()

    def start_test(self):
        if self.sampler.states[self.slot] is None:
            self.result_lbl.config(text="Connect a controller first.", fg=WARN)
            return
        self.sampler.start_test(self.slot, 5.0)
        self.test_btn.state(["disabled"])
        self.result_lbl.config(text="Spin a stick now!", fg=WARN)

    def rumble(self):
        xinput.vibrate(self.slot, 0.6, 0.6)
        self.after(600, lambda: xinput.vibrate(self.slot, 0, 0))

    # ---------------------------------------------------------------- frame
    def _tick(self):
        try:
            if not getattr(self, "paused", False):
                self._draw()
        finally:
            self.after(16, self._tick)

    def _draw(self):
        c = self.c
        states = self.sampler.states
        for i, (r, t) in enumerate(self.slot_items):
            on = states[i] is not None
            sel = i == self.slot
            c.itemconfig(r, fill=(GOOD if on else PANEL2) if sel or on else PANEL2,
                         outline=LIT if sel else BODY_EDGE)
            c.itemconfig(t, fill="#0b0c0d" if on else MUTED)

        s = states[self.slot]
        c.itemconfig(self.title, text=f"Controller {self.slot + 1}")
        if s is None:
            c.itemconfig(self.subtitle, text="(Not connected)", fill=MUTED)
            c.itemconfig(self.hint, text="Plug in an Xbox-style (XInput) controller. PlayStation pads need "
                                         "Steam Input or DS4Windows to show up here.")
            c.itemconfig(self.batt, text="")
            g = None
        else:
            c.itemconfig(self.subtitle, text="(Connected)", fill=GOOD)
            c.itemconfig(self.hint, text="")
            g = s.Gamepad
            if not hasattr(self, "_bt_next") or self._bt_next <= 0:
                b = xinput.battery(self.slot)
                if b is None:
                    btxt = ""
                elif b[0] == "wired":
                    btxt = "Wired"
                else:
                    btxt = "Battery: " + ["empty", "low", "medium", "full"][min(b[1], 3)]
                c.itemconfig(self.batt, text=btxt)
                self._bt_next = 60
            self._bt_next -= 1

        btn = g.wButtons if g else 0

        def pressed(name):
            return bool(btn & xinput.BUTTONS[name])

        for k, (oval, col) in self.face.items():
            c.itemconfig(oval, fill=col if pressed(k) else self._dim(col))
        for k, item in self.dpad.items():
            c.itemconfig(item, fill=LIT if pressed(k) else IDLE)
        c.itemconfig(self.lb, fill=LIT if pressed("lb") else IDLE)
        c.itemconfig(self.rb, fill=LIT if pressed("rb") else IDLE)
        c.itemconfig(self.back, fill=LIT if pressed("back") else IDLE)
        c.itemconfig(self.start, fill=LIT if pressed("start") else IDLE)
        c.itemconfig(self.guide, fill=LIT if pressed("guide") else IDLE)

        for key, val in (("lt", g.bLeftTrigger if g else 0), ("rt", g.bRightTrigger if g else 0)):
            fill, pct = self.trig[key]
            x = 236 if key == "lt" else 744
            top = 399 - int(val / 255 * 248)
            self._co(fill, x - 8, top, x + 8, 399)
            c.itemconfig(pct, text=f"{round(val / 255 * 100)}%")

        sticks = (("l", g.sThumbLX if g else 0, g.sThumbLY if g else 0, self.ls_cap, 400, 262, pressed("ls")),
                  ("r", g.sThumbRX if g else 0, g.sThumbRY if g else 0, self.rs_cap, 538, 334, pressed("rs")))
        for key, sx, sy, cap, bx, by, click in sticks:
            fx, fy = max(-1.0, sx / 32767), max(-1.0, sy / 32767)
            self._co(cap, *self._circ(bx + fx * 10, by - fy * 10, 22))
            c.itemconfig(cap, fill=LIT if click else IDLE)
            v = self.vis[key]
            px, py = v["x"] + fx * 72, 290 - fy * 72
            self._co(v["dot"], *self._circ(px, py, 7))
            c.itemconfig(v["dot"], fill=ACCENT if click else LIT)
            c.itemconfig(v["xy"], text=f"X {round(fx * 100)}%   ·   Y {round(fy * 100)}%")
            v["pts"].append((px, py))
            del v["pts"][:-24]
            flat = [n for p in v["pts"] for n in p]
            if len(flat) >= 4:
                self._co(v["trail"], *flat)

        # polling rate readouts
        prog = self.sampler.test_progress()
        if prog:
            self.progress["value"] = prog[0]
            self.big_sub.config(text=f"testing... {prog[1]} packets")
        elif self.sampler.result is not None:
            self._show_result(self.sampler.result)
            self.sampler.result = None
            self.test_btn.state(["!disabled"])
            self.progress["value"] = 1.0
        else:
            live = self.sampler.live_rate() if s is not None else None
            if live:
                self.big_hz.config(text=f"~{xinput.nearest_standard(live)} Hz")
                self.big_sub.config(text="live estimate (keep moving)")
            elif not getattr(self, "_has_result", False):
                self.big_hz.config(text="--")
                self.big_sub.config(text="move a stick")

    def _show_result(self, r):
        if not r["ok"]:
            self.result_lbl.config(text=f"Only {r['packets']} packets came in - spin the stick "
                                        "continuously during the test and try again.", fg=WARN)
            return
        self._has_result = True
        std = xinput.nearest_standard(r["median_hz"])
        if self.last_result:
            self.prev_lbl.config(text=f"Previous test: {self.last_result} Hz")
        self.last_result = std
        self.big_hz.config(text=f"{std} Hz")
        self.big_sub.config(text="test result")
        self.result_lbl.config(
            text=f"Typical: {r['median_hz']:.0f} Hz     Average: {r['avg_hz']:.0f} Hz     "
                 f"Peak: {r['peak_hz']:.0f} Hz     ({r['packets']} packets)",
            fg=TEXT)
        self.after(4000, lambda: setattr(self, "_has_result", False))


# ==========================================================================
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"{APP_NAME} by {AUTHOR}")
        self.configure(bg=BG)
        self.S = max(1.0, self.winfo_fpixels("1i") / 96.0)  # Windows display scaling
        try:
            self.iconbitmap(self._res("icon.ico"))
        except tk.TclError:
            pass
        self._style()

        header = tk.Frame(self, bg=BG)
        header.pack(fill="x", padx=20, pady=(14, 0))
        self._logo = None
        if pystray is not None:
            try:
                px = int(34 * self.S)
                self._logo = ImageTk.PhotoImage(Image.open(self._res("icon.png")).resize((px, px), Image.LANCZOS))
                tk.Label(header, image=self._logo, bg=BG).pack(side="left", padx=(0, 10))
            except OSError:
                pass
        tk.Label(header, text=APP_NAME, bg=BG, fg=TEXT, font=("Segoe UI Semibold", 18)).pack(side="left")
        tk.Label(header, text=f"  by {AUTHOR}", bg=BG, fg=ACCENT, font=("Segoe UI Semibold", 11)).pack(
            side="left", pady=(6, 0))
        if pystray is not None:
            ttk.Button(header, text="Minimize to tray", command=self.to_tray).pack(side="right")
        tk.Label(header, text="Polling-rate booster  ·  driver: hidusbf by SweetLow",
                 bg=BG, fg=MUTED, font=("Segoe UI", 10)).pack(side="right", padx=14, pady=(6, 0))

        footer = tk.Frame(self, bg=BG)
        footer.pack(side="bottom", fill="x", padx=20, pady=(0, 10))
        link = tk.Label(footer, text=REPO_URL.replace("https://", ""), bg=BG, fg=MUTED, cursor="hand2",
                        font=("Segoe UI", 9, "underline"))
        link.pack(side="right")
        link.bind("<Button-1>", lambda e: webbrowser.open(REPO_URL))
        tk.Label(footer, text="Changing USB polling rates is at your own risk. "
                              "'Remove all' puts every device back to normal.",
                 bg=BG, fg=MUTED, font=("Segoe UI", 9)).pack(side="left")

        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=8, pady=8)
        self.rate_tab = RateTab(nb, self)
        self.live_tab = LiveTab(nb, self)
        nb.add(self.rate_tab, text="  Polling Rate  ")
        nb.add(self.live_tab, text="  Live Test  ")
        self.protocol("WM_DELETE_WINDOW", self.on_close)

        self.tray = None
        self._tray_hint_shown = False
        self.bind("<Unmap>", self._on_unmap)  # the window's minimize button also goes to the tray
        self.after(10, self._dark_title_bar)

    @staticmethod
    def _res(name):
        return os.path.join(hb.resource_dir(), name)

    def _dark_title_bar(self):
        try:
            hwnd = ctypes.windll.user32.GetParent(self.winfo_id())
            on = ctypes.c_int(1)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(on), ctypes.sizeof(on))
            ctypes.windll.dwmapi.DwmSetWindowAttribute(  # caption color (Windows 11)
                hwnd, 35, ctypes.byref(ctypes.c_int(0x001F1C1B)), 4)
        except (AttributeError, OSError):
            pass

    # ------------------------------------------------------------------ tray
    def _on_unmap(self, event):
        if event.widget is self and pystray is not None and self.state() == "iconic":
            self.after(0, self.to_tray)

    def to_tray(self):
        if pystray is None:
            self.iconify()
            return
        self.withdraw()
        self.live_tab.set_paused(True)
        if self.tray is None:
            menu = pystray.Menu(
                pystray.MenuItem(f"Open {APP_NAME}", lambda: self.after(0, self.from_tray), default=True),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Quit", lambda: self.after(0, self.on_close)))
            self.tray = pystray.Icon(APP_NAME, Image.open(self._res("icon.png")),
                                     f"{APP_NAME} by {AUTHOR}", menu)
            self.tray.run_detached()
        else:
            self.tray.visible = True
        if not self._tray_hint_shown:
            self._tray_hint_shown = True
            self.after(600, lambda: self._notify("Still running in the tray. Double-click the icon to open."))

    def _notify(self, msg):
        try:
            self.tray.notify(msg, APP_NAME)
        except Exception:  # notifications are cosmetic
            pass

    def from_tray(self):
        if self.tray is not None:
            self.tray.visible = False
        self.live_tab.set_paused(False)
        self.deiconify()
        self.state("normal")
        self.lift()
        self.focus_force()

    def on_close(self):
        self.live_tab.sampler.stop()
        if self.tray is not None:
            self.tray.stop()
        self.destroy()

    def _style(self):
        st = ttk.Style(self)
        st.theme_use("clam")
        st.configure(".", background=BG, foreground=TEXT, fieldbackground=PANEL2, bordercolor=BODY_EDGE,
                     font=("Segoe UI", 10))
        flat = dict(bordercolor=BG, lightcolor=BG, darkcolor=BG)
        st.configure("TNotebook", background=BG, borderwidth=0, tabmargins=(12, 4, 0, 0), **flat)
        st.configure("TNotebook.Tab", background=BG, foreground=MUTED, padding=(18, 8), borderwidth=0,
                     font=("Segoe UI Semibold", 10), **flat)
        st.map("TNotebook.Tab", background=[("selected", PANEL), ("active", PANEL)],
               foreground=[("selected", TEXT)], lightcolor=[("selected", ACCENT)],
               expand=[("selected", (0, 0, 0, 0))])
        st.configure("TButton", background=PANEL2, foreground=TEXT, borderwidth=0, padding=(12, 6),
                     focuscolor=PANEL2)
        st.map("TButton", background=[("disabled", PANEL), ("active", "#3a3e44")],
               foreground=[("disabled", "#666a70")])
        st.configure("Accent.TButton", background=ACCENT, foreground="white")
        st.map("Accent.TButton", background=[("disabled", PANEL), ("active", "#6a9dff")])
        st.configure("Big.TButton", background=ACCENT, foreground="white", font=("Segoe UI Semibold", 13),
                     padding=(34, 14))
        st.map("Big.TButton", background=[("disabled", PANEL), ("active", "#6a9dff")])
        st.configure("Seg.Toolbutton", background=PANEL2, foreground=MUTED, padding=(14, 7), borderwidth=0)
        st.map("Seg.Toolbutton", background=[("selected", ACCENT), ("active", "#3a3e44")],
               foreground=[("selected", "white")])
        st.configure("Panel.TCheckbutton", background=PANEL, foreground=MUTED)
        st.map("Panel.TCheckbutton", background=[("active", PANEL)], foreground=[("disabled", "#55585e")])
        st.configure("Treeview", background=PANEL2, fieldbackground=PANEL2, foreground=TEXT, rowheight=int(30 * self.S),
                     borderwidth=0)
        st.map("Treeview", background=[("selected", ACCENT)], foreground=[("selected", "white")])
        st.configure("Treeview", bordercolor=PANEL2, lightcolor=PANEL2, darkcolor=PANEL2)
        st.configure("Treeview.Heading", background=PANEL, foreground=MUTED, borderwidth=0, relief="flat",
                     font=("Segoe UI Semibold", 9))
        st.map("Treeview.Heading", background=[("active", PANEL)])
        st.configure("TCombobox", fieldbackground=PANEL2, background=PANEL2, foreground=TEXT, arrowcolor=TEXT)
        st.configure("TCombobox", bordercolor=PANEL2, lightcolor=PANEL2, darkcolor=PANEL2, padding=(8, 5),
                     arrowsize=int(12 * self.S))
        st.map("TCombobox", fieldbackground=[("readonly", PANEL2)], foreground=[("readonly", TEXT)],
               background=[("readonly", PANEL2), ("active", "#3a3e44")],
               selectbackground=[("readonly", PANEL2)], selectforeground=[("readonly", TEXT)])
        st.configure("Panel.TCheckbutton", indicatorbackground=PANEL2, indicatorforeground=TEXT)
        st.configure("Horizontal.TProgressbar", background=ACCENT, troughcolor=PANEL2, borderwidth=0,
                     thickness=int(8 * self.S))
        self.option_add("*TCombobox*Listbox.background", PANEL2)
        self.option_add("*TCombobox*Listbox.foreground", TEXT)


def main():
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except (AttributeError, OSError):
        pass
    if "--list" in sys.argv:  # diagnostics, no GUI
        for d in hb.scan_devices():
            print(("[C] " if d.is_controller else "    ") + f"{d.name} | {d.instance_id} | svc={d.service} "
                  f"| parent={d.parent_service} | {d.current()}")
        return
    if not hb.is_admin() and "--no-admin" not in sys.argv:
        if relaunch_as_admin():
            return
    App().mainloop()


if __name__ == "__main__":
    main()
