"""Read-only Windows facts via registry and Win32; no shell or policy changes."""
from __future__ import annotations

import ctypes
import os
from ctypes import wintypes


def _registry(path, names):
    import winreg
    values = {}
    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, path, 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as key:
        for name in names:
            try:
                values[name] = winreg.QueryValueEx(key, name)[0]
            except FileNotFoundError:
                values[name] = None
    return values


def _admin_token():
    api = ctypes.WinDLL("advapi32", use_last_error=True)
    create = api.CreateWellKnownSid
    create.argtypes = [ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(wintypes.DWORD)]
    create.restype = wintypes.BOOL
    check = api.CheckTokenMembership
    check.argtypes = [wintypes.HANDLE, ctypes.c_void_p, ctypes.POINTER(wintypes.BOOL)]
    check.restype = wintypes.BOOL
    buffer = ctypes.create_string_buffer(68)  # SECURITY_MAX_SID_SIZE
    size = wintypes.DWORD(len(buffer))
    if not create(26, None, buffer, ctypes.byref(size)):  # WinBuiltinAdministratorsSid
        raise ctypes.WinError(ctypes.get_last_error())
    member = wintypes.BOOL()
    if not check(None, buffer, ctypes.byref(member)):
        raise ctypes.WinError(ctypes.get_last_error())
    return bool(member.value)


def _appidsvc():
    api = ctypes.WinDLL("advapi32", use_last_error=True)
    open_manager = api.OpenSCManagerW
    open_manager.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD]
    open_manager.restype = wintypes.HANDLE
    open_service = api.OpenServiceW
    open_service.argtypes = [wintypes.HANDLE, wintypes.LPCWSTR, wintypes.DWORD]
    open_service.restype = wintypes.HANDLE
    close = api.CloseServiceHandle
    close.argtypes = [wintypes.HANDLE]
    close.restype = wintypes.BOOL

    class ServiceStatus(ctypes.Structure):
        _fields_ = [(name, wintypes.DWORD) for name in
                    ("service_type", "current_state", "controls", "exit_code", "specific_exit", "checkpoint", "wait_hint")]

    query = api.QueryServiceStatus
    query.argtypes = [wintypes.HANDLE, ctypes.POINTER(ServiceStatus)]
    query.restype = wintypes.BOOL
    manager = open_manager(None, None, 0x0001)  # SC_MANAGER_CONNECT only
    if not manager:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        service = open_service(manager, "AppIDSvc", 0x0004)  # SERVICE_QUERY_STATUS only
        if not service:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            state = ServiceStatus()
            if not query(service, ctypes.byref(state)):
                raise ctypes.WinError(ctypes.get_last_error())
            return {1: "STOPPED", 2: "START_PENDING", 3: "STOP_PENDING", 4: "RUNNING",
                    5: "CONTINUE_PENDING", 6: "PAUSE_PENDING", 7: "PAUSED"}.get(state.current_state, "UNKNOWN")
        finally:
            close(service)
    finally:
        close(manager)


def collect_capabilities():
    result = {"schema_version": "task09b-capabilities-draft-v2",
              "evaluation_type": "NATIVE_READ_ONLY_PROBE", "status": "BLOCKED",
              "live_status": "BLOCKED", "live_supported": False,
              "policy_writes": 0, "service_writes": 0, "errors": [],
              "os": None, "token_is_administrator": None, "appidsvc_status": "UNKNOWN",
              "vm_hint": "UNKNOWN_NOT_APPROVAL", "approved_vm": "NOT_ESTABLISHED",
              "effective_policy": {"status": "UNKNOWN", "sha256": None,
                                   "reason_code": "NATIVE_PROBE_DOES_NOT_READ_EFFECTIVE_POLICY"},
              "rollback_rehearsal": "NOT_RUN", "blockers": []}
    if os.name != "nt":
        result.update(status="UNSUPPORTED", reason_code="WINDOWS_REQUIRED", blockers=["WINDOWS_REQUIRED"])
        return result
    try:
        result["os"] = _registry(r"SOFTWARE\Microsoft\Windows NT\CurrentVersion",
                                 ["EditionID", "CurrentBuildNumber", "UBR", "DisplayVersion"])
    except OSError as exc:
        result["errors"].append({"check": "OS_REGISTRY_READ_FAILED", "winerror": getattr(exc, "winerror", None)})
    try:
        result["token_is_administrator"] = _admin_token()
    except OSError as exc:
        result["errors"].append({"check": "TOKEN_READ_FAILED", "winerror": getattr(exc, "winerror", None)})
    try:
        result["appidsvc_status"] = _appidsvc()
    except OSError as exc:
        result["errors"].append({"check": "APPIDSVC_READ_FAILED", "winerror": getattr(exc, "winerror", None)})
    try:
        bios = _registry(r"HARDWARE\DESCRIPTION\System\BIOS", ["SystemManufacturer", "SystemProductName"])
        hint = " ".join(str(value or "") for value in bios.values()).lower()
        result["vm_hint"] = ("VIRTUALIZATION_HINT_NOT_APPROVAL" if any(
            tag in hint for tag in ("virtual", "vmware", "qemu", "kvm", "xen")) else "NO_VM_HINT_NOT_PROOF")
    except OSError:
        result["errors"].append({"check": "VM_HINT_READ_FAILED"})
    if result["token_is_administrator"] is False:
        result["blockers"].append("INSUFFICIENT_PRIVILEGES_FOR_LIVE_POLICY_MANAGEMENT")
    elif result["token_is_administrator"] is None:
        result["blockers"].append("PRIVILEGES_UNKNOWN")
    if result["appidsvc_status"] != "RUNNING":
        result["blockers"].append("APPIDSVC_NOT_CONFIRMED_RUNNING")
    result["blockers"].extend(["EFFECTIVE_POLICY_UNKNOWN", "APPROVED_VM_NOT_ESTABLISHED",
                                "RECOVERY_NOT_REHEARSED", "USE_GUARDED_NATIVE_VM_BACKEND_FOR_LIVE"])
    result["reason_code"] = result["blockers"][0]
    return result
