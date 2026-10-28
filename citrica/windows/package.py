"""MSIX identity, writable folders and StartupTask without importing WinRT in Python."""
from __future__ import annotations

import ctypes
import json
import subprocess
import sys
from ctypes import wintypes
from functools import lru_cache
from pathlib import Path

NO_PACKAGE = 15700  # APPMODEL_ERROR_NO_PACKAGE
INSUFFICIENT_BUFFER = 122
TASK_ID = 'CitricaStartup'
STATES = {'Disabled', 'DisabledByUser', 'Enabled', 'DisabledByPolicy', 'EnabledByPolicy'}


@lru_cache(maxsize=1)
def package_family_name():
    if sys.platform != 'win32':
        return None
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    function = getattr(kernel, 'GetCurrentPackageFamilyName', None)
    if function is None:
        return None
    function.argtypes = [ctypes.POINTER(wintypes.UINT), wintypes.LPWSTR]
    function.restype = wintypes.LONG
    length = wintypes.UINT(0)
    status = function(ctypes.byref(length), None)
    if status == NO_PACKAGE:
        return None
    if status != INSUFFICIENT_BUFFER or not 1 < length.value <= 256:
        raise RuntimeError(f'Não foi possível verificar a identidade MSIX ({status}).')
    buffer = ctypes.create_unicode_buffer(length.value)
    status = function(ctypes.byref(length), buffer)
    if status != 0 or not buffer.value:
        raise RuntimeError(f'Não foi possível ler a identidade MSIX ({status}).')
    return buffer.value


def _helper_path():
    return Path(sys.executable).resolve().with_name('citrica-package.exe')


def _request(*arguments):
    family = package_family_name()
    if family is None:
        raise RuntimeError('Esta operação requer a instalação MSIX do Cítrica.')
    helper = _helper_path()
    if not helper.is_file():
        raise RuntimeError('O componente nativo do pacote MSIX não foi encontrado.')
    try:
        result = subprocess.run([str(helper), *arguments], check=False, capture_output=True,
            text=True, encoding='utf-8', errors='strict', timeout=8,
            creationflags=0x08000000 if sys.platform == 'win32' else 0)
        data = json.loads(result.stdout)
    except (OSError, subprocess.TimeoutExpired, ValueError) as error:
        raise RuntimeError('Não foi possível consultar os recursos do pacote MSIX.') from error
    if not isinstance(data, dict) or result.returncode != 0 or data.get('ok') is not True:
        message = data.get('error') if isinstance(data, dict) else None
        raise RuntimeError(message or 'O componente do pacote MSIX retornou uma resposta inválida.')
    if data.get('package_family') != family:
        raise RuntimeError('O componente MSIX não herdou a identidade do aplicativo.')
    return data


@lru_cache(maxsize=1)
def application_paths():
    data = _request('--paths')
    paths = {}
    for key in ['local_folder', 'local_cache', 'temporary_folder']:
        value = data.get(key)
        if not isinstance(value, str) or not value or not Path(value).is_absolute():
            raise RuntimeError('O pacote MSIX não informou uma pasta de dados válida.')
        paths[key] = Path(value)
    return paths


def startup_task(action='query'):
    if action not in {'query', 'enable', 'disable'}:
        raise ValueError('Operação de inicialização inválida.')
    data = _request('--startup', action)
    if (data.get('task_id') != TASK_ID or data.get('state') not in STATES or
            type(data.get('enabled')) is not bool or type(data.get('blocked')) is not bool or
            type(data.get('changed')) is not bool or
            data['enabled'] != (data['state'] in {'Enabled', 'EnabledByPolicy'})):
        raise RuntimeError('O pacote retornou um estado de inicialização inválido.')
    return data
