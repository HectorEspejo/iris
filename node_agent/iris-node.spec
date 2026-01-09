# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for Iris Node Agent

Build with:
    pyinstaller iris-node.spec

This creates a single executable for the current platform.
"""

import platform
import sys

# Determine platform-specific settings
system = platform.system().lower()
machine = platform.machine().lower()

# Normalize architecture names
if machine in ('x86_64', 'amd64'):
    arch = 'amd64'
elif machine in ('arm64', 'aarch64'):
    arch = 'arm64'
else:
    arch = machine

# Output name includes platform and architecture
name = f'iris-node-{system}-{arch}'

# Platform-specific hidden imports
hidden_imports = [
    'websockets',
    'httpx',
    'structlog',
    'cryptography',
    'pydantic',
    'yaml',
    'asyncio',
]

# Add NVIDIA support for Linux/Windows
if system in ('linux', 'windows'):
    hidden_imports.append('pynvml')

# Add WMI for Windows AMD GPU support
if system == 'windows':
    hidden_imports.append('wmi')

# Collect data files
datas = [
    ('../shared', 'shared'),
]

# Analysis
a = Analysis(
    ['standalone_main.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Exclude unnecessary large packages
        'tkinter',
        'matplotlib',
        'numpy',
        'pandas',
        'scipy',
        'PIL',
        'IPython',
        'jupyter',
        'notebook',
        'test',
        'tests',
        'unittest',
    ],
    noarchive=False,
    optimize=2,
)

# Remove unnecessary data
a.datas = [d for d in a.datas if not d[0].startswith('tcl')]
a.datas = [d for d in a.datas if not d[0].startswith('tk')]

pyz = PYZ(
    a.pure,
    a.zipped_data,
    cipher=None,
)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name=name,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,  # Add icon path here if desired: 'path/to/icon.ico'
)
