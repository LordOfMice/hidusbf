"""XInput reader + polling-rate sampler."""
import ctypes
import ctypes.wintypes as wt
import statistics
import threading
import time


class XINPUT_GAMEPAD(ctypes.Structure):
    _fields_ = [("wButtons", wt.WORD), ("bLeftTrigger", ctypes.c_ubyte), ("bRightTrigger", ctypes.c_ubyte),
                ("sThumbLX", ctypes.c_short), ("sThumbLY", ctypes.c_short),
                ("sThumbRX", ctypes.c_short), ("sThumbRY", ctypes.c_short)]


class XINPUT_STATE(ctypes.Structure):
    _fields_ = [("dwPacketNumber", wt.DWORD), ("Gamepad", XINPUT_GAMEPAD)]


class XINPUT_VIBRATION(ctypes.Structure):
    _fields_ = [("wLeftMotorSpeed", wt.WORD), ("wRightMotorSpeed", wt.WORD)]


class XINPUT_BATTERY_INFORMATION(ctypes.Structure):
    _fields_ = [("BatteryType", ctypes.c_ubyte), ("BatteryLevel", ctypes.c_ubyte)]


BUTTONS = {
    "up": 0x0001, "down": 0x0002, "left": 0x0004, "right": 0x0008,
    "start": 0x0010, "back": 0x0020, "ls": 0x0040, "rs": 0x0080,
    "lb": 0x0100, "rb": 0x0200, "guide": 0x0400,
    "a": 0x1000, "b": 0x2000, "x": 0x4000, "y": 0x8000,
}

_dll = None
for name in ("xinput1_4", "xinput1_3", "xinput9_1_0"):
    try:
        _dll = ctypes.WinDLL(name)
        break
    except OSError:
        pass

_get_state = None
if _dll is not None:
    try:
        _get_state = _dll[100]  # XInputGetStateEx: same as GetState but includes the Guide button
    except (AttributeError, OSError):
        _get_state = _dll.XInputGetState
    _get_state.argtypes = [wt.DWORD, ctypes.POINTER(XINPUT_STATE)]
    _get_state.restype = wt.DWORD

AVAILABLE = _get_state is not None


def get_state(user):
    s = XINPUT_STATE()
    if not AVAILABLE or _get_state(user, ctypes.byref(s)) != 0:
        return None
    return s


def vibrate(user, left, right):
    if not AVAILABLE:
        return
    v = XINPUT_VIBRATION(int(left * 65535), int(right * 65535))
    _dll.XInputSetState(user, ctypes.byref(v))


def battery(user):
    """Returns (kind, level 0-3) or None."""
    if not AVAILABLE or not hasattr(_dll, "XInputGetBatteryInformation"):
        return None
    b = XINPUT_BATTERY_INFORMATION()
    if _dll.XInputGetBatteryInformation(user, 0, ctypes.byref(b)) != 0:
        return None
    kinds = {0: None, 1: "wired", 2: "battery", 3: "battery", 0xFF: "unknown"}
    kind = kinds.get(b.BatteryType, "unknown")
    return (kind, b.BatteryLevel) if kind else None


class Sampler:
    """
    Background thread that keeps the latest state of every slot. During a rate
    test it spins as fast as it can on one slot and timestamps each new packet
    (XInput bumps dwPacketNumber whenever the controller reports a change, so
    spinning a stick makes nearly every USB report a new packet).
    """

    def __init__(self):
        self.states = [None] * 4
        self.lock = threading.Lock()
        self._test = None  # dict while a test is running
        self.result = None
        self._stop = False
        self.paused = False  # hidden in tray: poll slowly to save CPU
        self._live_stamps = []
        self._live_slot = 0
        threading.Thread(target=self._run, daemon=True).start()

    def stop(self):
        self._stop = True

    def set_live_slot(self, slot):
        self._live_slot = slot

    def start_test(self, slot, seconds=5.0):
        with self.lock:
            self.result = None
            self._test = {"slot": slot, "end": time.perf_counter() + seconds, "stamps": [],
                          "start": time.perf_counter(), "seconds": seconds}

    @property
    def testing(self):
        return self._test is not None

    def test_progress(self):
        t = self._test
        if not t:
            return None
        return min(1.0, (time.perf_counter() - t["start"]) / t["seconds"]), len(t["stamps"])

    def live_rate(self):
        """Rough rate from the last ~0.5 s of packets on the selected slot."""
        now = time.perf_counter()
        stamps = [s for s in self._live_stamps if now - s < 0.5]
        self._live_stamps = stamps
        if len(stamps) < 10:
            return None
        return _rate_from_stamps(stamps)

    def _run(self):
        last_pkt = [None] * 4
        next_full_scan = 0.0
        while not self._stop:
            now = time.perf_counter()
            test = self._test
            if test:
                slot = test["slot"]
                s = get_state(slot)
                if s is not None:
                    if s.dwPacketNumber != last_pkt[slot]:
                        last_pkt[slot] = s.dwPacketNumber
                        test["stamps"].append(time.perf_counter())
                    self.states[slot] = s
                if now >= test["end"]:
                    self.result = summarize(test["stamps"])
                    self._test = None
                continue  # no sleep: sample as fast as possible

            if self.paused:
                time.sleep(0.25)
                continue

            # normal mode: watch the selected slot closely, scan the rest occasionally
            slot = self._live_slot
            s = get_state(slot)
            self.states[slot] = s
            if s is not None and s.dwPacketNumber != last_pkt[slot]:
                last_pkt[slot] = s.dwPacketNumber
                self._live_stamps.append(now)
                if len(self._live_stamps) > 4000:
                    self._live_stamps = self._live_stamps[-2000:]
            if now >= next_full_scan:
                for i in range(4):
                    if i != slot:
                        self.states[i] = get_state(i)
                next_full_scan = now + 0.5
            time.sleep(0.0002)


def _rate_from_stamps(stamps):
    gaps = [b - a for a, b in zip(stamps, stamps[1:]) if b > a]
    if not gaps:
        return None
    return 1.0 / statistics.median(gaps)


def summarize(stamps):
    if len(stamps) < 50:
        return {"ok": False, "packets": len(stamps)}
    gaps = sorted(b - a for a, b in zip(stamps, stamps[1:]) if b > a)
    # ignore pauses (stick briefly still) when computing the average
    med = statistics.median(gaps)
    moving = [g for g in gaps if g < med * 3]
    avg = 1.0 / (sum(moving) / len(moving))
    p10 = gaps[max(0, len(gaps) // 10)]  # 10th percentile gap -> near-peak rate
    return {"ok": True, "packets": len(stamps), "median_hz": 1.0 / med,
            "avg_hz": avg, "peak_hz": 1.0 / p10}


def nearest_standard(hz):
    return min((125, 250, 500, 1000, 2000, 4000, 8000), key=lambda r: abs(r - hz))
