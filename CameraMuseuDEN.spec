# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path


bundled_assets = [
    (str(path), str(path.parent))
    for path in Path("assets").rglob("*")
    if path.is_file() and path.name.casefold() != "google_app_passwords_qr.png"
]


a = Analysis(
    ['camera_museu.py'],
    pathex=[],
    binaries=[],
    datas=bundled_assets,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='CameraMuseuDEN',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['assets\\icones\\camera_museu.ico'],
)
