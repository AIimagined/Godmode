"""Who can read or write the state home. Owner-only is the contract."""
from __future__ import annotations

import os
import stat
from pathlib import Path
from typing import Any

# Well-known SIDs whose grant on the state home means "not owner-only":
# Everyone, Authenticated Users, and the local Users group.
_WORLD_SIDS = {"S-1-1-0": "Everyone", "S-1-5-11": "Authenticated Users", "S-1-5-32-545": "Users"}

# ACCESS_MASK bits that constitute read or write access, generic and
# file-specific: GENERIC_READ/WRITE/ALL plus the FILE_* bits icacls sets
# for a plain (R)/(W) grant.
_GENERIC_ALL = 0x10000000
_READ_BITS = 0x80000000 | 0x00000001 | 0x00000008 | 0x00020000 | _GENERIC_ALL
# GENERIC_READ, FILE_READ_DATA, FILE_READ_EA, READ_CONTROL, GENERIC_ALL
_WRITE_BITS = (
    0x40000000 | 0x00000002 | 0x00000004 | 0x00000010 | 0x00000100 | 0x00010000 | _GENERIC_ALL
)
# GENERIC_WRITE, FILE_WRITE_DATA, FILE_APPEND_DATA, FILE_WRITE_EA,
# FILE_WRITE_ATTRIBUTES, DELETE, GENERIC_ALL

_ACCESS_ALLOWED_ACE_TYPE = 0
_ACL_SIZE_INFORMATION = 2  # AclSizeInformation


def _posix(path: Path) -> dict[str, Any]:
    mode = stat.S_IMODE(path.stat().st_mode)
    readers = [who for who, bit in (("group", stat.S_IRGRP), ("other", stat.S_IROTH)) if mode & bit]
    writers = [who for who, bit in (("group", stat.S_IWGRP), ("other", stat.S_IWOTH)) if mode & bit]
    execs_r = [who for who, bit in (("group", stat.S_IXGRP), ("other", stat.S_IXOTH)) if mode & bit]
    verdict = "permissive" if (mode & 0o077) else "tight"
    detail = f"mode {mode:04o}"
    if execs_r:
        detail += f"; executable by {', '.join(execs_r)}"
    return {"verdict": verdict, "detail": detail, "readers": readers, "writers": writers}


def _windows(path: Path) -> dict[str, Any]:  # pragma: no cover - exercised only on Windows
    import ctypes
    from ctypes import wintypes

    advapi = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    advapi.GetFileSecurityW.argtypes = [
        wintypes.LPCWSTR, wintypes.DWORD, wintypes.LPVOID, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)
    ]
    advapi.GetFileSecurityW.restype = wintypes.BOOL
    advapi.GetSecurityDescriptorDacl.argtypes = [
        wintypes.LPVOID, ctypes.POINTER(wintypes.BOOL), ctypes.POINTER(ctypes.c_void_p),
        ctypes.POINTER(wintypes.BOOL),
    ]
    advapi.GetSecurityDescriptorDacl.restype = wintypes.BOOL
    advapi.GetAclInformation.argtypes = [
        ctypes.c_void_p, wintypes.LPVOID, wintypes.DWORD, ctypes.c_int
    ]
    advapi.GetAclInformation.restype = wintypes.BOOL
    advapi.GetAce.argtypes = [ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(ctypes.c_void_p)]
    advapi.GetAce.restype = wintypes.BOOL
    advapi.ConvertSidToStringSidW.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_wchar_p)]
    advapi.ConvertSidToStringSidW.restype = wintypes.BOOL
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p

    DACL_SECURITY_INFORMATION = 0x4

    needed = wintypes.DWORD(0)
    advapi.GetFileSecurityW(str(path), DACL_SECURITY_INFORMATION, None, 0, ctypes.byref(needed))
    if needed.value == 0:
        return {
            "verdict": "unmeasured",
            "detail": f"GetFileSecurityW sizing failed: {ctypes.get_last_error()}",
            "readers": [], "writers": [],
        }
    buf = ctypes.create_string_buffer(needed.value)
    ok = advapi.GetFileSecurityW(str(path), DACL_SECURITY_INFORMATION, buf, needed, ctypes.byref(needed))
    if not ok:
        return {
            "verdict": "unmeasured",
            "detail": f"GetFileSecurityW failed: {ctypes.get_last_error()}",
            "readers": [], "writers": [],
        }

    present = wintypes.BOOL()
    defaulted = wintypes.BOOL()
    dacl = ctypes.c_void_p()
    if not advapi.GetSecurityDescriptorDacl(buf, ctypes.byref(present), ctypes.byref(dacl), ctypes.byref(defaulted)):
        return {
            "verdict": "unmeasured",
            "detail": f"GetSecurityDescriptorDacl failed: {ctypes.get_last_error()}",
            "readers": [], "writers": [],
        }
    if not present.value or not dacl.value:
        return {"verdict": "permissive", "detail": "no DACL (everyone has full access)",
                "readers": ["Everyone"], "writers": ["Everyone"]}

    class _AclSizeInformation(ctypes.Structure):
        _fields_ = [("AceCount", wintypes.DWORD), ("AclBytesInUse", wintypes.DWORD), ("AclBytesFree", wintypes.DWORD)]

    info = _AclSizeInformation()
    if not advapi.GetAclInformation(dacl, ctypes.byref(info), ctypes.sizeof(info), _ACL_SIZE_INFORMATION):
        return {
            "verdict": "unmeasured",
            "detail": f"GetAclInformation failed: {ctypes.get_last_error()}",
            "readers": [], "writers": [],
        }

    readers: list[str] = []
    writers: list[str] = []
    for index in range(info.AceCount):
        ace = ctypes.c_void_p()
        if not advapi.GetAce(dacl, index, ctypes.byref(ace)):
            continue
        # ACE_HEADER is {BYTE AceType; BYTE AceFlags; WORD AceSize;} = 4
        # bytes; ACCESS_ALLOWED_ACE is Header + ACCESS_MASK Mask (DWORD, 4
        # bytes) + SidStart - so the type byte sits at offset 0, the mask
        # DWORD at offset 4, and the embedded SID begins at offset 8.
        # Verified against a live `icacls /grant` ACE on this machine
        # (tests/test_state_home_acl.py's Windows cases), not assumed.
        header = ctypes.cast(ace, ctypes.POINTER(ctypes.c_ubyte * 8)).contents
        ace_type = header[0]
        if ace_type != _ACCESS_ALLOWED_ACE_TYPE:
            continue
        mask = ctypes.cast(ace.value + 4, ctypes.POINTER(wintypes.DWORD)).contents.value
        sid_ptr = ctypes.c_void_p(ace.value + 8)
        text = ctypes.c_wchar_p()
        if not advapi.ConvertSidToStringSidW(sid_ptr, ctypes.byref(text)):
            continue
        sid_text = text.value or ""
        kernel32.LocalFree(text)
        name = _WORLD_SIDS.get(sid_text)
        if not name:
            continue
        if mask & _READ_BITS:
            readers.append(f"{name} ({sid_text})")
        if mask & _WRITE_BITS:
            writers.append(f"{name} ({sid_text})")

    verdict = "permissive" if (readers or writers) else "tight"
    return {"verdict": verdict, "detail": f"{info.AceCount} ACE(s) examined", "readers": readers, "writers": writers}


def state_home_acl(path: Path) -> dict[str, Any]:
    """Report who can read or write `path` (the state home).

    Never raises: doctor calls this on the happy path, and a check that
    crashes doctor over a permissions question it was only asked to answer
    is worse than one that reports `unmeasured`.
    """
    try:
        return _windows(path) if os.name == "nt" else _posix(path)
    except Exception as exc:  # noqa: BLE001  # godmode: swallow-ok: the check reports, never crashes doctor
        return {"verdict": "unmeasured", "detail": f"{type(exc).__name__}: {exc}", "readers": [], "writers": []}
