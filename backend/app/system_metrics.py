"""Read-only host telemetry. Standard library only; invoked without importing app.

CPU is a delta between successive OS counters, never load-average-as-percentage.
No OCR, CUDA context creation, package installation or project access.
"""
import csv
import io
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import time


def cpu_percent(previous, current):
    if not isinstance(previous, dict) or not current:
        return None
    total = current['total'] - previous.get('total', current['total'])
    idle = current['idle'] - previous.get('idle', current['idle'])
    if total <= 0 or idle < 0 or idle > total:
        return None
    return round(100 * (total - idle) / total, 1)


def windows_cpu():
    import ctypes as ct
    from ctypes import wintypes as wt
    kernel = ct.WinDLL('kernel32', use_last_error=True)
    kernel.GetSystemTimes.argtypes = [ct.POINTER(wt.FILETIME)] * 3
    kernel.GetSystemTimes.restype = wt.BOOL
    idle, system, user = wt.FILETIME(), wt.FILETIME(), wt.FILETIME()
    if not kernel.GetSystemTimes(ct.byref(idle), ct.byref(system), ct.byref(user)):
        raise ct.WinError(ct.get_last_error())
    ticks = lambda t: (t.dwHighDateTime << 32) + t.dwLowDateTime
    # GetSystemTimes kernel includes idle time; subtract idle exactly once.
    return {'idle': ticks(idle), 'total': ticks(system) + ticks(user)}


def physical_memory(total, available):
    if total <= 0 or available < 0 or available > total:
        raise ValueError('Physical memory counters are unavailable.')
    return {'total_bytes': total, 'available_bytes': available,
            'used_bytes': total - available, 'percent': round((total - available) * 100 / total, 1)}


def windows_memory():
    import ctypes as ct
    from ctypes import wintypes as wt
    class Memory(ct.Structure):
        _fields_ = [('length', wt.DWORD), ('load', wt.DWORD)] + [
            (n, ct.c_ulonglong) for n in ('total', 'available', 'total_page', 'available_page',
                                         'total_virtual', 'available_virtual', 'extended')]
    data = Memory(); data.length = ct.sizeof(data)
    kernel = ct.WinDLL('kernel32', use_last_error=True)
    kernel.GlobalMemoryStatusEx.argtypes = [ct.POINTER(Memory)]
    kernel.GlobalMemoryStatusEx.restype = wt.BOOL
    if not kernel.GlobalMemoryStatusEx(ct.byref(data)):
        raise ct.WinError(ct.get_last_error())
    return physical_memory(data.total, data.available)


def cpu_counters():
    if os.name == 'nt':
        return windows_cpu()
    if sys.platform.startswith('linux'):
        values = [int(v) for v in Path('/proc/stat').read_text().splitlines()[0].split()[1:9]]
        return {'total': sum(values), 'idle': values[3] + values[4]}
    raise OSError('CPU telemetry is unavailable on this platform.')


def memory_counters():
    if os.name == 'nt':
        return windows_memory()
    if sys.platform.startswith('linux'):
        rows = dict(line.split(':', 1) for line in Path('/proc/meminfo').read_text().splitlines())
        return physical_memory(int(rows['MemTotal'].split()[0]) * 1024,
                               int(rows['MemAvailable'].split()[0]) * 1024)
    raise OSError('RAM telemetry is unavailable on this platform.')


def numeric(value, lower=0, upper=None):
    try:
        result = float(value.strip())
        return result if result >= lower and (upper is None or result <= upper) else None
    except ValueError:
        return None


def parse_gpus(text):
    result = []
    for row in csv.reader(io.StringIO(text)):
        if len(row) != 7:
            continue
        index, uuid, name, usage, used, total, temperature = [s.strip() for s in row]
        memory_used, memory_total = numeric(used), numeric(total)
        result.append({'id': index, 'uuid': uuid, 'name': name, 'vendor': 'NVIDIA',
                       'utilization_percent': numeric(usage, upper=100),
                       'memory_used_bytes': int(memory_used * 2**20) if memory_used is not None else None,
                       'memory_total_bytes': int(memory_total * 2**20) if memory_total is not None else None,
                       'temperature_celsius': numeric(temperature, upper=150)})
    return result


def gpu_counters():
    binary = shutil.which('nvidia-smi')
    if not binary:
        return [], 'NVIDIA telemetry unavailable; AMD/Intel GPU counters are not implemented.'
    try:
        result = subprocess.run([binary, '--query-gpu=index,uuid,name,utilization.gpu,memory.used,memory.total,temperature.gpu',
                                 '--format=csv,noheader,nounits'], capture_output=True, text=True,
                                timeout=2, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        if result.returncode:
            return [], 'NVIDIA telemetry did not respond.'
        gpus = parse_gpus(result.stdout)
        return gpus, None if gpus else 'No readable NVIDIA GPU counters.'
    except (OSError, subprocess.TimeoutExpired):
        return [], 'NVIDIA telemetry timed out or is unavailable.'


def sample(previous=None):
    errors = {}; cpu = None; memory = None
    try:
        cpu = cpu_counters()
    except (OSError, ValueError, KeyError, IndexError) as exc:
        errors['cpu'] = str(exc)
    try:
        memory = memory_counters()
    except (OSError, ValueError, KeyError) as exc:
        errors['memory'] = str(exc)
    gpus, error = gpu_counters()
    if error:
        errors['gpu'] = error
    return {'scope': 'Host computer', 'platform': platform.system(), 'sampled_at': time.time(),
            'cpu': {'percent': cpu_percent(previous, cpu), 'logical_cores': os.cpu_count()},
            'memory': memory, 'gpus': gpus, 'errors': errors, '_cpu_counters': cpu}


if __name__ == '__main__':
    request = json.load(sys.stdin)
    print(json.dumps(sample(request.get('previous_cpu')), allow_nan=False))
