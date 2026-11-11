"""
Talks to Windows to install the hidusbf filter driver and set per-device USB
polling rates -- the same things hidusbf's own Setup.exe does:

  * driver service  : copy hidusbf.sys to System32\\drivers, create a kernel
                      service named "hidusbf" (demand start)
  * filter on device: add "hidusbf" to the device's LowerFilters property
  * rate            : write REG_DWORD "bInterval" in the device's driver (software)
                      key, Control\\Class\\{guid}\\NNNN -- hidusbf.sys opens it with
                      IoOpenDeviceRegistryKey(PLUGPLAY_REGKEY_DRIVER)
  * apply           : restart the device

Everything goes through cfgmgr32 so it works with admin rights (the Enum keys
are not directly writable even by administrators).
"""
import ctypes
import ctypes.wintypes as wt
import hashlib
import os
import re
import shutil
import subprocess
import sys
import uuid
import winreg

SERVICE = "hidusbf"
SERVICE_DISPLAY = "USB Mouse Rate Adjuster Lower Filter by SweetLow"

# polling rate (Hz) -> bInterval for Full/Low Speed USB devices (frames of 1 ms)
RATES = {1000: 1, 500: 2, 250: 4, 125: 8, 62: 16, 31: 32}
INTERVAL_TO_RATE = {v: k for k, v in RATES.items()}

CREATE_NO_WINDOW = 0x08000000

# --------------------------------------------------------------------------
# cfgmgr32 bindings
# --------------------------------------------------------------------------
_cm = ctypes.WinDLL("cfgmgr32")
_adv = ctypes.WinDLL("advapi32")

CR_SUCCESS = 0x00
CR_NO_SUCH_VALUE = 0x25
CR_BUFFER_SMALL = 0x1A
CM_GETIDLIST_FILTER_ENUMERATOR = 0x1
CM_GETIDLIST_FILTER_PRESENT = 0x100
CM_LOCATE_DEVNODE_NORMAL = 0
CM_LOCATE_DEVNODE_PHANTOM = 1
CM_REGISTRY_SOFTWARE = 1  # = the key hidusbf.sys reads (PLUGPLAY_REGKEY_DRIVER)
RegDisposition_OpenAlways = 0

CM_DRP_DEVICEDESC = 0x01
CM_DRP_SERVICE = 0x05
CM_DRP_CLASS = 0x08
CM_DRP_FRIENDLYNAME = 0x0D
CM_DRP_LOWERFILTERS = 0x13

DN_STARTED = 0x8
DN_HAS_PROBLEM = 0x400


class DEVPROPKEY(ctypes.Structure):
    _fields_ = [("fmtid", ctypes.c_ubyte * 16), ("pid", wt.ULONG)]


def _propkey(guid, pid):
    k = DEVPROPKEY()
    ctypes.memmove(k.fmtid, uuid.UUID(guid).bytes_le, 16)
    k.pid = pid
    return k


DEVPKEY_BusReportedDeviceDesc = _propkey("540b947e-8b40-45bc-a8a2-6a0b894cbda2", 4)

_cm.CM_Get_Device_ID_List_SizeW.argtypes = [ctypes.POINTER(wt.ULONG), wt.LPCWSTR, wt.ULONG]
_cm.CM_Get_Device_ID_ListW.argtypes = [wt.LPCWSTR, ctypes.c_void_p, wt.ULONG, wt.ULONG]
_cm.CM_Locate_DevNodeW.argtypes = [ctypes.POINTER(wt.DWORD), wt.LPCWSTR, wt.ULONG]
_cm.CM_Get_DevNode_Registry_PropertyW.argtypes = [
    wt.DWORD, wt.ULONG, ctypes.POINTER(wt.ULONG), ctypes.c_void_p, ctypes.POINTER(wt.ULONG), wt.ULONG]
_cm.CM_Set_DevNode_Registry_PropertyW.argtypes = [wt.DWORD, wt.ULONG, ctypes.c_void_p, wt.ULONG, wt.ULONG]
_cm.CM_Get_DevNode_PropertyW.argtypes = [
    wt.DWORD, ctypes.POINTER(DEVPROPKEY), ctypes.POINTER(wt.ULONG), ctypes.c_void_p,
    ctypes.POINTER(wt.ULONG), wt.ULONG]
_cm.CM_Open_DevNode_Key.argtypes = [
    wt.DWORD, wt.DWORD, wt.ULONG, wt.ULONG, ctypes.POINTER(wt.HKEY), wt.ULONG]
_cm.CM_Get_Parent.argtypes = [ctypes.POINTER(wt.DWORD), wt.DWORD, wt.ULONG]
_cm.CM_Get_Child.argtypes = [ctypes.POINTER(wt.DWORD), wt.DWORD, wt.ULONG]
_cm.CM_Get_Sibling.argtypes = [ctypes.POINTER(wt.DWORD), wt.DWORD, wt.ULONG]
_cm.CM_Get_Device_IDW.argtypes = [wt.DWORD, ctypes.c_wchar_p, wt.ULONG, wt.ULONG]
_cm.CM_Get_DevNode_Status.argtypes = [
    ctypes.POINTER(wt.ULONG), ctypes.POINTER(wt.ULONG), wt.DWORD, wt.ULONG]
_adv.RegCloseKey.argtypes = [wt.HKEY]


class CMError(OSError):
    pass


def _check(cr, what):
    if cr != CR_SUCCESS:
        raise CMError(f"{what} failed (CONFIGRET 0x{cr:02X})")


def list_device_ids(enumerator="USB", present_only=True):
    flags = CM_GETIDLIST_FILTER_ENUMERATOR | (CM_GETIDLIST_FILTER_PRESENT if present_only else 0)
    size = wt.ULONG()
    _check(_cm.CM_Get_Device_ID_List_SizeW(ctypes.byref(size), enumerator, flags), "list size")
    buf = ctypes.create_unicode_buffer(size.value + 1)
    _check(_cm.CM_Get_Device_ID_ListW(enumerator, buf, size.value, flags), "list devices")
    raw = ctypes.wstring_at(ctypes.addressof(buf), size.value)
    return [s for s in raw.split("\0") if s]


def locate(instance_id, phantom=False):
    dn = wt.DWORD()
    flag = CM_LOCATE_DEVNODE_PHANTOM if phantom else CM_LOCATE_DEVNODE_NORMAL
    _check(_cm.CM_Locate_DevNodeW(ctypes.byref(dn), instance_id, flag), f"locate {instance_id}")
    return dn.value


def _reg_prop(dn, prop):
    """Returns str, list[str] or None."""
    typ, size = wt.ULONG(), wt.ULONG(0)
    cr = _cm.CM_Get_DevNode_Registry_PropertyW(dn, prop, ctypes.byref(typ), None, ctypes.byref(size), 0)
    if cr == CR_NO_SUCH_VALUE or size.value == 0:
        return None
    buf = ctypes.create_string_buffer(size.value)
    cr = _cm.CM_Get_DevNode_Registry_PropertyW(dn, prop, ctypes.byref(typ), buf, ctypes.byref(size), 0)
    if cr != CR_SUCCESS:
        return None
    text = buf.raw[:size.value].decode("utf-16-le", "ignore")
    if typ.value == winreg.REG_MULTI_SZ:
        return [s for s in text.split("\0") if s]
    return text.split("\0", 1)[0]


def _set_multi_sz(dn, prop, values):
    if values:
        data = ("\0".join(values) + "\0\0").encode("utf-16-le")
        buf = ctypes.create_string_buffer(data, len(data))
        _check(_cm.CM_Set_DevNode_Registry_PropertyW(dn, prop, buf, len(data), 0), "set property")
    else:
        _check(_cm.CM_Set_DevNode_Registry_PropertyW(dn, prop, None, 0, 0), "clear property")


def _bus_desc(dn):
    typ, size = wt.ULONG(), wt.ULONG(0)
    key = DEVPKEY_BusReportedDeviceDesc
    _cm.CM_Get_DevNode_PropertyW(dn, ctypes.byref(key), ctypes.byref(typ), None, ctypes.byref(size), 0)
    if not size.value:
        return None
    buf = ctypes.create_string_buffer(size.value)
    if _cm.CM_Get_DevNode_PropertyW(dn, ctypes.byref(key), ctypes.byref(typ), buf, ctypes.byref(size), 0):
        return None
    return buf.raw.decode("utf-16-le", "ignore").split("\0", 1)[0] or None


def _device_id(dn):
    buf = ctypes.create_unicode_buffer(512)
    if _cm.CM_Get_Device_IDW(dn, buf, 512, 0):
        return None
    return buf.value


def _relative(dn, fn):
    out = wt.DWORD()
    return out.value if fn(ctypes.byref(out), dn, 0) == CR_SUCCESS else None


def _children(dn):
    c = _relative(dn, _cm.CM_Get_Child)
    while c is not None:
        yield c
        c = _relative(c, _cm.CM_Get_Sibling)


def _descendants(dn, depth=3):
    if depth <= 0:
        return
    for c in _children(dn):
        yield c
        yield from _descendants(c, depth - 1)


def _status(dn):
    st, prob = wt.ULONG(), wt.ULONG()
    if _cm.CM_Get_DevNode_Status(ctypes.byref(st), ctypes.byref(prob), dn, 0):
        return 0, 0
    return st.value, prob.value


class _DevKey:
    """Context manager around the device's driver (software) key."""

    def __init__(self, dn, write):
        self.dn, self.write, self.h = dn, write, None

    def __enter__(self):
        h = wt.HKEY()
        sam = winreg.KEY_READ | (winreg.KEY_SET_VALUE if self.write else 0)
        _check(_cm.CM_Open_DevNode_Key(self.dn, sam, 0, RegDisposition_OpenAlways,
                                       ctypes.byref(h), CM_REGISTRY_SOFTWARE), "open device key")
        self.h = h
        return h.value  # winreg accepts raw integer handles

    def __exit__(self, *exc):
        _adv.RegCloseKey(self.h)


def read_interval(dn):
    try:
        with _DevKey(dn, False) as k:
            val, typ = winreg.QueryValueEx(k, "bInterval")
            return int(val)
    except (OSError, ValueError):
        return None


# --------------------------------------------------------------------------
# Device model
# --------------------------------------------------------------------------
SKIP_SERVICES = {"usbhub", "usbhub3", "usbstor", "uaspstor", "usbccgp", "usbaudio", "usbaudio2",
                 "usbvideo", "winusb", "bthusb", "btha2dp", "netadaptercx", "rndismp"}
SKIP_CLASSES = {"usb", "media", "camera", "image", "bluetooth", "net", "diskdrive", "audioendpoint"}
CONTROLLER_RE = re.compile(
    r"controller|gamepad|game ?pad|joystick|xbox|dualsense|dualshock|"
    r"8bitdo|pro controller|flydigi|gamesir|scuf|razer wolverine|nacon|arcade|fight ?stick",
    re.I)
CONTROLLER_SERVICES = {"xusb22", "xboxgip", "dc1-controller", "xinputhid"}


class Device:
    def __init__(self, instance_id):
        self.instance_id = instance_id
        self.dn = locate(instance_id)
        self.service = (_reg_prop(self.dn, CM_DRP_SERVICE) or "").lower()
        self.dev_class = (_reg_prop(self.dn, CM_DRP_CLASS) or "").lower()
        own = _reg_prop(self.dn, CM_DRP_FRIENDLYNAME) or _reg_prop(self.dn, CM_DRP_DEVICEDESC) or ""
        own = own.split(";")[-1]
        self.parent_dn = _relative(self.dn, _cm.CM_Get_Parent)
        self.parent_service = (_reg_prop(self.parent_dn, CM_DRP_SERVICE) or "").lower() if self.parent_dn else ""
        self.parent_id = _device_id(self.parent_dn) if self.parent_dn else None
        bus = _bus_desc(self.dn)
        if self.is_composite_child and self.parent_dn:
            bus = _bus_desc(self.parent_dn) or bus
        self.name = bus or own or instance_id
        self.generic_name = own
        child_text = " ".join(
            (_reg_prop(c, CM_DRP_DEVICEDESC) or "") for c in _descendants(self.dn))
        self.is_controller = bool(
            self.service in CONTROLLER_SERVICES
            or self.dev_class in ("xnacomposite", "xboxcomposite")
            or "game controller" in child_text.lower()
            or CONTROLLER_RE.search(self.name)
            or CONTROLLER_RE.search(own))
        m = re.search(r"VID_([0-9A-F]{4})&PID_([0-9A-F]{4})", instance_id, re.I)
        self.vidpid = f"{m.group(1)}:{m.group(2)}".upper() if m else ""

    @property
    def is_composite_child(self):
        return self.parent_service == "usbccgp"

    def filter_target(self, use_parent):
        """The devnode the filter is applied to."""
        if use_parent and self.is_composite_child:
            return self.parent_dn, self.parent_id
        return self.dn, self.instance_id

    def current(self):
        """(has_filter, rate_hz or None, where) -- checks own node and composite parent."""
        for dn, where in ((self.dn, "device"), (self.parent_dn if self.is_composite_child else None, "parent")):
            if dn is None:
                continue
            filters = [f.lower() for f in (_reg_prop(dn, CM_DRP_LOWERFILTERS) or [])]
            if SERVICE in filters:
                iv = read_interval(dn)
                return True, INTERVAL_TO_RATE.get(iv), where
        return False, None, None

    def problem(self):
        st, prob = _status(self.dn)
        return prob if st & DN_HAS_PROBLEM else 0

    def listable(self):
        if self.service in SKIP_SERVICES or self.dev_class in SKIP_CLASSES:
            return False
        iid = self.instance_id.upper()
        if "ROOT_HUB" in iid or "&IG_" in iid:  # IG_ = virtual XInput child, not a real USB device
            return False
        if re.search(r"headset|headphone|audio|speaker|microphone", self.name, re.I):
            return False
        return True


def scan_devices():
    devs = []
    for iid in list_device_ids("USB"):
        try:
            d = Device(iid)
        except OSError:
            continue
        if d.listable():
            devs.append(d)
    devs.sort(key=lambda d: (not d.is_controller, d.name.lower()))
    return devs


# --------------------------------------------------------------------------
# Applying / removing a rate
# --------------------------------------------------------------------------
def set_filter(dn, rate_hz):
    """rate_hz=None removes the filter and the override."""
    filters = _reg_prop(dn, CM_DRP_LOWERFILTERS) or []
    others = [f for f in filters if f.lower() != SERVICE]
    if rate_hz is None:
        _set_multi_sz(dn, CM_DRP_LOWERFILTERS, others)
        try:
            with _DevKey(dn, True) as k:
                winreg.DeleteValue(k, "bInterval")
        except OSError:
            pass
        return
    with _DevKey(dn, True) as k:
        winreg.SetValueEx(k, "bInterval", 0, winreg.REG_DWORD, RATES[rate_hz])
    _set_multi_sz(dn, CM_DRP_LOWERFILTERS, others + [SERVICE])


_k32 = ctypes.WinDLL("kernel32", use_last_error=True)
_k32.CreateFileW.restype = wt.HANDLE
_k32.CreateFileW.argtypes = [wt.LPCWSTR, wt.DWORD, wt.DWORD, ctypes.c_void_p, wt.DWORD, wt.DWORD, wt.HANDLE]
_k32.DeviceIoControl.argtypes = [wt.HANDLE, wt.DWORD, ctypes.c_void_p, wt.DWORD, ctypes.c_void_p, wt.DWORD,
                                 ctypes.POINTER(wt.DWORD), ctypes.c_void_p]
_k32.CloseHandle.argtypes = [wt.HANDLE]
cm_iface_size = _cm.CM_Get_Device_Interface_List_SizeW
cm_iface_size.argtypes = [ctypes.POINTER(wt.ULONG), ctypes.c_void_p, wt.LPCWSTR, wt.ULONG]
cm_iface_list = _cm.CM_Get_Device_Interface_ListW
cm_iface_list.argtypes = [ctypes.c_void_p, wt.LPCWSTR, ctypes.c_void_p, wt.ULONG, wt.ULONG]
GUID_DEVINTERFACE_USB_HUB = uuid.UUID("f18a0e88-c30c-11d0-8815-00a0c906bed8").bytes_le
DEVPKEY_Device_Address = _propkey("a45c254e-df1c-4efd-8020-67d146a850e0", 30)
IOCTL_USB_HUB_CYCLE_PORT = 0x220444
INVALID_HANDLE = wt.HANDLE(-1).value


def _usb_device_node(instance_id):
    """The devnode plugged into a hub port (the composite parent for an interface node)."""
    dn = locate(instance_id)
    parent = _relative(dn, _cm.CM_Get_Parent)
    if parent and (_reg_prop(parent, CM_DRP_SERVICE) or "").lower() == "usbccgp":
        dn, parent = parent, _relative(parent, _cm.CM_Get_Parent)
    return dn, parent


def cycle_port(instance_id):
    """
    Power-cycles the device's USB port -- the software equivalent of unplugging and
    replugging. Unlike a normal restart, apps (XboxService, GameInput...) can't veto it.
    """
    dn, hub = _usb_device_node(instance_id)
    typ, size = wt.ULONG(), wt.ULONG(4)
    buf = ctypes.create_string_buffer(4)
    key = DEVPKEY_Device_Address
    if _cm.CM_Get_DevNode_PropertyW(dn, ctypes.byref(key), ctypes.byref(typ), buf, ctypes.byref(size), 0):
        raise CMError("could not read the device's USB port number")
    port = int.from_bytes(buf.raw, "little")
    hub_id = _device_id(hub)
    guid = (ctypes.c_ubyte * 16).from_buffer_copy(GUID_DEVINTERFACE_USB_HUB)
    n = wt.ULONG()
    _check(cm_iface_size(ctypes.byref(n), guid, hub_id, 0), "hub interface size")
    lb = ctypes.create_unicode_buffer(n.value + 1)
    _check(cm_iface_list(guid, hub_id, lb, n.value, 0), "hub interface")
    h = _k32.CreateFileW(lb.value, 0xC0000000, 3, None, 3, 0, None)  # read/write, shared
    if h in (None, INVALID_HANDLE):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        params = (ctypes.c_ulong * 2)(port, 0)  # USB_CYCLE_PORT_PARAMS {ConnectionIndex, StatusReturned}
        ret = wt.DWORD()
        if not _k32.DeviceIoControl(h, IOCTL_USB_HUB_CYCLE_PORT, params, 8, params, 8, ctypes.byref(ret), None):
            raise ctypes.WinError(ctypes.get_last_error())
    finally:
        _k32.CloseHandle(h)


def restart_device(instance_id):
    """Returns (ok, needs_reboot, message). Tries a port power-cycle first, then pnputil."""
    try:
        cycle_port(instance_id)
        return True, False, "USB port power-cycled"
    except OSError as e:
        cycle_err = str(e)
    try:
        p = subprocess.run(["pnputil", "/restart-device", instance_id], capture_output=True,
                           text=True, creationflags=CREATE_NO_WINDOW, timeout=60)
    except (OSError, subprocess.TimeoutExpired) as e:
        return False, False, str(e)
    out = (p.stdout + p.stderr).strip() + f"\n(port cycle failed: {cycle_err})"
    if p.returncode == 3010 or "reboot" in out.lower():
        return True, True, out
    return p.returncode == 0, False, out


def remove_from_all_devices():
    """Removes hidusbf from every USB device, including unplugged ones. Returns IDs touched."""
    touched = []
    for iid in list_device_ids("USB", present_only=False):
        try:
            dn = locate(iid, phantom=True)
        except OSError:
            continue
        filters = _reg_prop(dn, CM_DRP_LOWERFILTERS) or []
        if any(f.lower() == SERVICE for f in filters):
            try:
                set_filter(dn, None)
                touched.append(iid)
            except OSError:
                pass
    return touched


# --------------------------------------------------------------------------
# Driver service
# --------------------------------------------------------------------------
def resource_dir():
    return getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))


VARIANTS = {
    "nopatch": ("Standard", "Works with Memory Integrity on. Good for almost all controllers."),
    "patch1k": ("Patching (1 kHz)", "Needed for Low-Speed USB devices. Requires Memory Integrity OFF."),
}


def bundled_driver(variant):
    return os.path.join(resource_dir(), "drivers", variant, "hidusbf.sys")


def installed_driver_path():
    return os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "drivers", "hidusbf.sys")


def _md5(path):
    with open(path, "rb") as f:
        return hashlib.md5(f.read()).hexdigest()


def installed_variant():
    p = installed_driver_path()
    if not os.path.exists(p):
        return None
    h = _md5(p)
    for v in VARIANTS:
        if os.path.exists(bundled_driver(v)) and _md5(bundled_driver(v)) == h:
            return v
    return "other"


def _sc(*args):
    p = subprocess.run(["sc.exe", *args], capture_output=True, text=True,
                       creationflags=CREATE_NO_WINDOW)
    return p.returncode, (p.stdout + p.stderr)


def service_state():
    """'missing' | 'stopped' | 'running' | 'disabled'"""
    code, out = _sc("qc", SERVICE)
    if code == 1060 or "1060" in out:
        return "missing"
    if "DISABLED" in out.upper():
        return "disabled"
    code, out = _sc("query", SERVICE)
    return "running" if "RUNNING" in out.upper() else "stopped"


def memory_integrity_on():
    try:
        k = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                           r"SYSTEM\CurrentControlSet\Control\DeviceGuard\Scenarios\HypervisorEnforcedCodeIntegrity")
        val, _ = winreg.QueryValueEx(k, "Enabled")
        return bool(val)
    except OSError:
        return False


PENDING_DELETE_MSG = ("Windows is still finishing removing the previous driver install. "
                      "Restart the PC, then click Install driver again.")

LOAD_ERRORS = {
    577: "Windows rejected the driver signature (Secure Boot / signature policy).",
    193: "Memory Integrity is blocking the patching driver - use the Standard driver.",
    1275: "Windows blocked the driver from loading (security policy or anti-cheat).",
    1058: "The driver service is disabled.",
}


def install_service(variant):
    """Copies the driver and creates/updates the service. Returns (ok, message)."""
    src = bundled_driver(variant)
    dst = installed_driver_path()
    try:
        shutil.copyfile(src, dst)
    except OSError as e:
        return False, f"Could not copy the driver file ({e}). A reboot may be needed if it is in use."
    if service_state() == "missing":
        code, out = _sc("create", SERVICE, "type=", "kernel", "start=", "demand", "error=", "normal",
                        "binPath=", r"System32\drivers\hidusbf.sys", "DisplayName=", SERVICE_DISPLAY)
        if code != 0:
            return False, f"Could not create the driver service:\n{out.strip()}"
    else:
        code, out = _sc("config", SERVICE, "start=", "demand", "binPath=", r"System32\drivers\hidusbf.sys")
        if "1072" in out:  # ERROR_SERVICE_MARKED_FOR_DELETE
            return False, PENDING_DELETE_MSG

    # test-load the driver, like Setup.exe does
    code, out = _sc("start", SERVICE)
    m = re.search(r"FAILED (\d+)", out)
    if m and int(m.group(1)) != 1056:  # 1056 = already running
        err = int(m.group(1))
        if err in (1058, 1072) and service_state() != "disabled":
            return False, PENDING_DELETE_MSG
        return False, f"Driver installed, but Windows won't load it (error {err}).\n" + \
            LOAD_ERRORS.get(err, out.strip())
    return True, "Driver installed and loads correctly."


def uninstall_service():
    touched = remove_from_all_devices()
    for iid in touched:
        restart_device(iid)
    _sc("stop", SERVICE)
    _sc("delete", SERVICE)
    try:
        os.remove(installed_driver_path())
        file_msg = ""
    except FileNotFoundError:
        file_msg = ""
    except OSError:
        file_msg = "\nThe driver file is still in use and will be gone after a reboot."
    return (f"Removed the filter from {len(touched)} device(s) and uninstalled the driver.{file_msg}\n"
            "Restart the PC before installing the driver again.")


def is_admin():
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except OSError:
        return False
