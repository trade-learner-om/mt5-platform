import ctypes
import os
from ctypes import wintypes


def find_running_terminal_processes() -> list[dict[str, object]]:
    if os.name != "nt":
        return []

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    psapi = ctypes.WinDLL("psapi", use_last_error=True)

    enum_processes = psapi.EnumProcesses
    enum_processes.argtypes = [ctypes.POINTER(wintypes.DWORD), wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
    enum_processes.restype = wintypes.BOOL

    open_process = kernel32.OpenProcess
    open_process.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    open_process.restype = wintypes.HANDLE

    query_image_name = kernel32.QueryFullProcessImageNameW
    query_image_name.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
    query_image_name.restype = wintypes.BOOL

    process_ids = (wintypes.DWORD * 4096)()
    bytes_returned = wintypes.DWORD()
    if not enum_processes(process_ids, ctypes.sizeof(process_ids), ctypes.byref(bytes_returned)):
        return []

    terminals: list[dict[str, object]] = []
    process_query_limited_information = 0x1000
    count = bytes_returned.value // ctypes.sizeof(wintypes.DWORD)

    for pid in process_ids[:count]:
        if not pid:
            continue
        handle = open_process(process_query_limited_information, False, pid)
        if not handle:
            continue
        try:
            buffer_size = wintypes.DWORD(4096)
            buffer = ctypes.create_unicode_buffer(buffer_size.value)
            if not query_image_name(handle, 0, buffer, ctypes.byref(buffer_size)):
                continue
            path = buffer.value
            name = os.path.basename(path).lower()
            if name in {"terminal.exe", "terminal64.exe"}:
                terminals.append({"pid": int(pid), "path": path})
        finally:
            kernel32.CloseHandle(handle)

    return terminals


def find_running_terminal_paths() -> list[str]:
    paths: list[str] = []
    for terminal in find_running_terminal_processes():
        path = str(terminal.get("path") or "")
        if path and path not in paths:
            paths.append(path)
    return paths
