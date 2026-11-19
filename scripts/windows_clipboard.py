"""Windows CF_UNICODETEXT for the local form. Never logs clipboard contents."""
import ctypes
from ctypes import wintypes


class ClipboardFailure(Exception):
    pass


def api():
    user = ctypes.WinDLL('user32',use_last_error=True)
    kernel = ctypes.WinDLL('kernel32',use_last_error=True)
    for name,args,result in (
        ('OpenClipboard',[wintypes.HWND],wintypes.BOOL),
        ('CloseClipboard',[],wintypes.BOOL),
        ('EmptyClipboard',[],wintypes.BOOL),
        ('IsClipboardFormatAvailable',[wintypes.UINT],wintypes.BOOL),
        ('GetClipboardData',[wintypes.UINT],wintypes.HANDLE),
        ('SetClipboardData',[wintypes.UINT,wintypes.HANDLE],wintypes.HANDLE),
    ):
        function = getattr(user,name)
        function.argtypes,function.restype = args,result
    for name,args,result in (
        ('GlobalAlloc',[wintypes.UINT,ctypes.c_size_t],wintypes.HGLOBAL),
        ('GlobalLock',[wintypes.HGLOBAL],ctypes.c_void_p),
        ('GlobalUnlock',[wintypes.HGLOBAL],wintypes.BOOL),
        ('GlobalSize',[wintypes.HGLOBAL],ctypes.c_size_t),
        ('GlobalFree',[wintypes.HGLOBAL],wintypes.HGLOBAL),
    ):
        function = getattr(kernel,name)
        function.argtypes,function.restype = args,result
    return user,kernel


def read_text():
    user,kernel = api()
    if not user.OpenClipboard(None):
        raise ClipboardFailure('CLIPBOARD_BUSY')
    try:
        if not user.IsClipboardFormatAvailable(13):
            raise ClipboardFailure('NO_UNICODE_TEXT')
        handle = user.GetClipboardData(13)
        if not handle:
            raise ClipboardFailure('CLIPBOARD_UNAVAILABLE')
        size = kernel.GlobalSize(handle)
        if size < 2 or size > 1024*1024 or size % 2:
            raise ClipboardFailure('CLIPBOARD_TEXT_SIZE')
        pointer = kernel.GlobalLock(handle)
        if not pointer:
            raise ClipboardFailure('CLIPBOARD_UNAVAILABLE')
        try:
            return ctypes.wstring_at(pointer,size//2).split('\0',1)[0]
        finally:
            kernel.GlobalUnlock(handle)
    finally:
        user.CloseClipboard()


def write_text(hwnd, text):
    user,kernel = api()
    data = (text+'\0').encode('utf-16-le')
    handle = kernel.GlobalAlloc(0x0002,len(data))
    if not handle:
        raise ClipboardFailure('CLIPBOARD_UNAVAILABLE')
    transferred = False
    try:
        pointer = kernel.GlobalLock(handle)
        if not pointer:
            raise ClipboardFailure('CLIPBOARD_UNAVAILABLE')
        try:
            ctypes.memmove(pointer,data,len(data))
        finally:
            kernel.GlobalUnlock(handle)
        if not user.OpenClipboard(hwnd):
            raise ClipboardFailure('CLIPBOARD_BUSY')
        try:
            if not user.EmptyClipboard() or not user.SetClipboardData(13,handle):
                raise ClipboardFailure('CLIPBOARD_UNAVAILABLE')
            transferred = True  # Windows owns the movable memory from now on.
        finally:
            user.CloseClipboard()
    finally:
        if not transferred:
            kernel.GlobalFree(handle)
