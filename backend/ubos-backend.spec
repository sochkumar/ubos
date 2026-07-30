# PyInstaller spec for the UBOS desktop backend (onedir).
# Build:  pyinstaller ubos-backend.spec   (run from backend/)
# Output: dist/ubos-backend/ubos-backend.exe  (+ its dependency folder)
#
# Produced on GitHub Actions windows-latest; may need per-run tuning of
# hiddenimports/datas as the dependency set evolves.
from PyInstaller.utils.hooks import collect_submodules, collect_data_files

# uvicorn/motor/pymongo pull a lot in dynamically — collect their submodules.
hiddenimports = []
for pkg in ("uvicorn", "motor", "pymongo", "bson", "passlib", "email_validator",
            "anyio", "bcrypt"):
    hiddenimports += collect_submodules(pkg)
hiddenimports += ["passlib.handlers.bcrypt"]

# Runtime data files. Templates are loaded via __file__-relative paths, so they
# must live at modules/templates/library inside the bundle.
datas = [("modules/templates/library", "modules/templates/library")]
datas += collect_data_files("reportlab")

a = Analysis(
    ["desktop_entry.py"],
    pathex=["."],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ubos-backend",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="ubos-backend",
)
