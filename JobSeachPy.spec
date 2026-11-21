# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_submodules
from PyInstaller.utils.hooks import collect_all

datas = [('dist_obf/pyarmor_runtime_000000', 'pyarmor_runtime_000000')]
binaries = []
hiddenimports = ['openpyxl', 'pypdf', 'ui_panel', 'automation_worker', 'base_assistant', 'config_manager', 'linkedin_bot', 'job_extractor', 'ai_assistant', 'gemini_assistant', 'excel_tracker']
hiddenimports += collect_submodules('PySide6.QtWidgets')
hiddenimports += collect_submodules('PySide6.QtCore')
hiddenimports += collect_submodules('PySide6.QtGui')
hiddenimports += collect_submodules('playwright')
tmp_ret = collect_all('google')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('playwright_stealth')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    ['dist_obf\\JobSeachPy.py'],
    pathex=['dist_obf'],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['PySide6.Qt3D', 'PySide6.QtSensors', 'PySide6.QtQuick', 'PySide6.QtQml', 'PySide6.QtWebEngineCore', 'PySide6.QtWebEngineWidgets', 'PySide6.QtSql', 'PySide6.QtTest', 'PySide6.QtNetwork', 'PySide6.QtSvg', 'PySide6.QtOpenGL', 'PySide6.QtMultimedia', 'PySide6.QtWebEngineCore', 'PySide6.Qt3DCore', 'PySide6.QtVirtualKeyboard', 'matplotlib', 'numpy', 'pandas', 'tkinter', 'unittest', 'PIL', 'scipy', 'IPython'],
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
    name='JobSeachPy',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=['vcruntime140.dll'],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
