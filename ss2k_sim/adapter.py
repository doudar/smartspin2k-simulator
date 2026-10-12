"""Explicit, recorded import boundary to the firmware-owned native adapter.

No native firmware/controller sources are vendored in this project. Adapter
Python executes locally, so provide only a firmware checkout you trust.
"""
import hashlib
import importlib.util
from pathlib import Path
import subprocess
import sys
import types

ADAPTER_FILES = ('bridge.py', 'native.cpp', 'virtual_ble.py', 'virtual_ble_facade.h',
                 'virtual_ble_runtime.inc', 'virtual_ftms.py', 'virtual_ftms.hpp')


def file_fingerprint(root, files):
    digest = hashlib.sha256()
    for path in sorted(files):
        path = Path(path)
        digest.update(str(path.relative_to(root)).encode()+b'\0'+path.read_bytes()+b'\0')
    return digest.hexdigest()


def revision(root):
    return subprocess.check_output(['git', '-C', str(root), 'rev-parse', 'HEAD'], text=True).strip()


def source_provenance(root):
    root = Path(root).resolve()
    files = [p for folder in ('src', 'include', 'lib/SS2K', 'lib/ArduinoCompat')
             for p in (root/folder).rglob('*') if p.is_file()]
    if not (root/'src/ERG_Mode.cpp').is_file() or not files:
        raise ValueError(f'Not a SmartSpin2k firmware source checkout: {root}')
    return {'root': str(root), 'commit': revision(root),
            'source_sha256': file_fingerprint(root, files),
            'dirty': bool(subprocess.check_output(['git', '-C', str(root), 'status', '--porcelain'], text=True).strip())}


def load_adapter(firmware_root, expected_sha256=None):
    root = Path(firmware_root).resolve()
    folder = root/'scripts/erg_sim'
    paths = [folder/name for name in ADAPTER_FILES]
    missing = [str(p) for p in paths if not p.is_file()]
    if missing:
        raise ValueError('Firmware checkout lacks native packet adapter files: '+', '.join(missing))
    fingerprint = file_fingerprint(folder, paths)
    if expected_sha256 and fingerprint != expected_sha256:
        raise ValueError('Firmware adapter SHA-256 does not match --adapter-sha256')
    # An isolated package preserves bridge.py's relative imports without placing
    # the firmware checkout on sys.path or importing its simulator plant.
    package_name = '_ss2k_firmware_adapter_'+fingerprint
    package = types.ModuleType(package_name)
    package.__path__ = [str(folder)]
    sys.modules[package_name] = package
    module_name = package_name+'.bridge'
    spec = importlib.util.spec_from_file_location(module_name, folder/'bridge.py')
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    if not callable(getattr(module, 'build', None)) or not callable(getattr(module, 'Bridge', None)):
        raise ValueError('Firmware adapter must expose build() and Bridge')
    return module, {'firmware_root': str(root), 'sha256': fingerprint, 'files': list(ADAPTER_FILES)}
