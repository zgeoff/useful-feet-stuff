"""HidChannel over the Windows HID API (hid.dll + setupapi.dll), through ctypes.

Import this module only on Windows.
"""

import ctypes as C
import ctypes.wintypes as W
import time

from pedals.hid import DeviceNotFound, NoAnswer

INTERFACE = "vid_1095&pid_0400&mi_01"
REPORT_LEN = 65  # report ID + 64 bytes

_DIGCF_PRESENT_INTERFACE = 0x12
_GENERIC_RW = 0xC0000000
_SHARE_RW = 3
_OPEN_EXISTING = 3
_FLAG_OVERLAPPED = 0x40000000
_ERROR_IO_PENDING = 997
_WAIT_OBJECT_0 = 0
_INVALID_HANDLE = {None, 0xFFFFFFFF, 0xFFFFFFFFFFFFFFFF}


class _Guid(C.Structure):
    _fields_ = [("a", C.c_ulong), ("b", C.c_ushort), ("c", C.c_ushort), ("d", C.c_ubyte * 8)]


class _InterfaceData(C.Structure):
    _fields_ = [("cb", W.DWORD), ("guid", _Guid), ("flags", W.DWORD), ("reserved", C.c_void_p)]


class _Overlapped(C.Structure):
    _fields_ = [
        ("internal", C.c_void_p),
        ("internal_high", C.c_void_p),
        ("offset", W.DWORD),
        ("offset_high", W.DWORD),
        ("event", C.c_void_p),
    ]


_hid = C.WinDLL("hid")
_setupapi = C.WinDLL("setupapi")
_kernel32 = C.WinDLL("kernel32", use_last_error=True)
_setupapi.SetupDiGetClassDevsW.restype = C.c_void_p
_kernel32.CreateFileW.restype = C.c_void_p
_kernel32.CreateEventW.restype = C.c_void_p


def _find_interface_path() -> str:
    guid = _Guid()
    _hid.HidD_GetHidGuid(C.byref(guid))
    devs = C.c_void_p(
        _setupapi.SetupDiGetClassDevsW(C.byref(guid), None, None, _DIGCF_PRESENT_INTERFACE)
    )
    try:
        index = 0
        while True:
            data = _InterfaceData()
            data.cb = C.sizeof(_InterfaceData)
            if not _setupapi.SetupDiEnumDeviceInterfaces(devs, None, C.byref(guid), index, C.byref(data)):
                raise DeviceNotFound(f"no {INTERFACE} interface present")
            index += 1
            need = W.DWORD()
            _setupapi.SetupDiGetDeviceInterfaceDetailW(devs, C.byref(data), None, 0, C.byref(need), None)
            detail = C.create_string_buffer(need.value)
            C.cast(detail, C.POINTER(W.DWORD))[0] = 8  # cbSize of SP_DEVICE_INTERFACE_DETAIL_DATA_W on x64
            _setupapi.SetupDiGetDeviceInterfaceDetailW(devs, C.byref(data), detail, need, None, None)
            path = C.wstring_at(C.addressof(detail) + 4)
            if INTERFACE in path.lower():
                return path
    finally:
        _setupapi.SetupDiDestroyDeviceInfoList(devs)


class WindowsHid:
    def __init__(self, handle: C.c_void_p, event: C.c_void_p):
        self._handle = handle
        self._event = event

    @classmethod
    def open(cls) -> "WindowsHid":
        path = _find_interface_path()
        handle = _kernel32.CreateFileW(
            path, _GENERIC_RW, _SHARE_RW, None, _OPEN_EXISTING, _FLAG_OVERLAPPED, None
        )
        if handle in _INVALID_HANDLE:
            raise DeviceNotFound(f"cannot open {INTERFACE}: error {C.get_last_error()}")
        return cls(C.c_void_p(handle), C.c_void_p(_kernel32.CreateEventW(None, 1, 0, None)))

    def close(self) -> None:
        _kernel32.CloseHandle(self._event)
        _kernel32.CloseHandle(self._handle)

    def send(self, payload: bytes) -> None:
        if len(payload) > REPORT_LEN - 1:
            raise ValueError(f"payload of {len(payload)} bytes; the limit is 64")
        report = (C.c_ubyte * REPORT_LEN)(0, *payload)
        if not _hid.HidD_SetOutputReport(self._handle, report, REPORT_LEN):
            raise NoAnswer(f"HidD_SetOutputReport failed: error {C.get_last_error()}")

    def recv(self, want: set[int], timeout_s: float = 2.0) -> bytes:
        deadline = time.monotonic() + timeout_s
        while (left := deadline - time.monotonic()) > 0:
            report = self._read_one(left)
            if report is None:
                break
            if report[0] in want:
                return report
        raise NoAnswer(f"no {sorted(hex(w) for w in want)} report within {timeout_s} s")

    def _read_one(self, timeout_s: float) -> bytes | None:
        buf = (C.c_ubyte * REPORT_LEN)()
        overlapped = _Overlapped(event=self._event.value)
        _kernel32.ResetEvent(self._event)
        read = W.DWORD()
        if not _kernel32.ReadFile(self._handle, buf, REPORT_LEN, C.byref(read), C.byref(overlapped)):
            if C.get_last_error() != _ERROR_IO_PENDING:
                raise NoAnswer(f"ReadFile failed: error {C.get_last_error()}")
            if _kernel32.WaitForSingleObject(self._event, max(1, int(timeout_s * 1000))) != _WAIT_OBJECT_0:
                _kernel32.CancelIo(self._handle)
                return None
        return bytes(buf)[1:]
