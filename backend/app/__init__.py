import os, shutil, subprocess

if os.name == 'nt':
    # The Tesseract installer (winget UB-Mannheim.TesseractOCR) does not add itself to PATH.
    for _dir in (os.getenv('TESSERACT_DIR', ''), r'C:\Program Files\Tesseract-OCR', r'C:\Program Files (x86)\Tesseract-OCR'):
        if not shutil.which('tesseract') and _dir and os.path.isfile(os.path.join(_dir, 'tesseract.exe')):
            os.environ['PATH'] = _dir + os.pathsep + os.environ.get('PATH', '')

    # The server runs without a console (pythonw), so every console tool it calls (tclsh, tesseract,
    # kicad-cli, tasklist, ...) would otherwise pop up its own terminal window.
    _popen_init = subprocess.Popen.__init__

    def _no_console_window(self, *args, creationflags=0, **kwargs):
        _popen_init(self, *args, creationflags=creationflags | subprocess.CREATE_NO_WINDOW, **kwargs)

    subprocess.Popen.__init__ = _no_console_window
