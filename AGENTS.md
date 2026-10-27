# Earth Wallpaper - Agent Guidelines

## Project Overview
Windows desktop wallpaper application that renders real-time Earth globes with satellite cloud overlays using PyQt6.

## Build/Run/Test Commands

### Run Application
```bash
# Direct Python execution
python desktop_v0.1.py

# With virtual environment
venv\Scripts\activate
python desktop_v0.1.py
```

### Build Executable
```bash
# Build EarthWallpaper.exe
pyinstaller --noconfirm EarthWallpaper.spec

# Build DesktopEarth.exe
pyinstaller --noconfirm DesktopEarth.spec
```

### Test Commands
```bash
# Run individual test file
pytest EarthWallpaper.spec -v
pytest DesktopEarth.spec -v

# Run all tests
pytest -v

# Run with coverage
pytest --cov=. -v
```

## Code Style Guidelines

### Imports
- Standard library imports first (`sys`, `os`, `ctypes`, `json`, etc.)
- Third-party imports grouped with compatibility try/except blocks
- PyQt6 imports should be on lines 21-28 following project convention
```python
try:
    import ephem
    HAS_EPHEM = True
except ImportError:
    HAS_EPHEM = False
```

### Formatting
- Indentation: 4 spaces
- Maximum line length: ~130 characters (PyQt6 imports are long)
- Use blank lines to separate logical blocks
- K&R style braces for classes/functions

### Types
- Mix of annotated and unannotated Python
- PyQt6 signals use `pyqtSignal()`
- Return type annotations are optional

### Naming Conventions
- Classes: PascalCase (`EarthWallpaperApp`, `ResizeLabel`, `EarthRenderer`)
- Functions: snake_case (`update_wallpaper_process`, `set_wallpaper_style`)
- Variables: snake_case (`lat_spin`, `preview_label`, `cloud_file`)
- Constants: UPPER_CASE (`SPI_SETDESKWALLPAPER`, `CONFIG_FILE`)

### Error Handling
- Use try/except for Windows registry operations
- Graceful fallback for missing optional dependencies (ephem)
- UI-related errors caught silently (user experience priority)
```python
try:
    winreg.SetValueEx(key, "WallpaperStyle", 0, winreg.REG_SZ, wp_style)
except:
    pass
```

### PyQt6 Patterns
- Use `Qt.AlignmentFlag.AlignCenter` not `Qt.AlignCenter`
- Signals: `pyqtSignal()` for custom signals
- Timers: `QTimer` with `timeout.connect()`
- Lock files: `QLockFile` for singleton prevention

### UI Component Organization
1. Configuration labels
2. Spin boxes and sliders
3. Mode radio buttons
4. Progress indicators
5. Action buttons

### Comment Style
- Korean comments are project standard
- Use section dividers: `# ===== comment =====`
- Inline comments inline: `def foo():  # comment`
- Document changes: `[수정]`, `[신규]`

### File Handling
```python
# Config
CONFIG_FILE = "config.json"

# Use absolute paths with os.path
output_file = os.path.join(os.path.dirname(__file__), "current_earth.png")
```

### Windows Integration
- Use `ctypes.windll.user32` for SetWindowsHook
- Use `winreg` for registry operations
- Use `SPIF_UPDATEINIFILE | SPIF_SENDWININICHANGE` for wallpaper changes

### Image Processing (Pillow)
```python
from PIL import Image, ImageEnhance, ImageDraw

# Enhance operations
enhancer = ImageEnhance.Contrast(img)
img_output = enhancer.enhance(1.6)
```

## Architecture Patterns
- Single Application Instance using `QLockFile`
- QThread for background downloading
- QTimer for periodic updates
- Config file JSON for persistence

## Dependencies (virtualenv)
```
PyQt6
Pillow
requests
ephem (optional)
numpy
pyinstaller
pytest
```

## Configuration
Edit `config.json` for defaults:
- `mode`: "url" or "api"
- `lat`, `lon`: Earth center coordinates
- `tilt`: Globe tilt angle
- `zoom`: Image zoom level (40-100)
- `opa`: Opacity (0-100)
- `cont`: Contrast multiplier (100-200)
