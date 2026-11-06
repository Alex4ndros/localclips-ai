"""Windows user-bound DPAPI storage. Secrets never enter job request/log files."""
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import uuid


class Blob(ctypes.Structure):
    _fields_=[('size',wintypes.DWORD),('data',ctypes.POINTER(ctypes.c_ubyte))]


def protect(value, decrypt=False):
    if os.name!='nt':
        raise RuntimeError('Archivio credenziali disponibile solo su Windows.')
    source=ctypes.create_string_buffer(value)
    incoming=Blob(len(value),ctypes.cast(source,ctypes.POINTER(ctypes.c_ubyte)))
    output=Blob()
    crypt=ctypes.WinDLL('crypt32',use_last_error=True)
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    function=crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
    function.argtypes=[ctypes.POINTER(Blob),ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,wintypes.DWORD,ctypes.POINTER(Blob)]
    function.restype=wintypes.BOOL
    if not function(ctypes.byref(incoming),None,None,None,None,1,ctypes.byref(output)):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        return ctypes.string_at(output.data,output.size)
    finally:
        kernel.LocalFree.argtypes=[ctypes.c_void_p]
        kernel.LocalFree(output.data)


def credential_path():
    path=Path(os.environ['LOCALAPPDATA'])/'LocalClipsAI'/'credentials.dpapi'
    path.parent.mkdir(parents=True,exist_ok=True)
    return path


def read():
    path=credential_path()
    if not path.exists():
        return {'host_id':'urn:uuid:'+str(uuid.uuid4()),'accounts':{},'active':''}
    return json.loads(protect(path.read_bytes(),True))


def write(value):
    path=credential_path()
    temporary=path.with_suffix('.'+uuid.uuid4().hex)
    try:
        temporary.write_bytes(protect(json.dumps(value).encode()))
        os.replace(temporary,path)
    finally:
        temporary.unlink(missing_ok=True)
