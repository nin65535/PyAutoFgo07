@echo off
setlocal
set "PROJECT_ROOT=%~dp0"
set "PYTHON=%PROJECT_ROOT%.venv\Scripts\python.exe"

if not exist "%PYTHON%" (
    echo Project virtual environment was not found: "%PYTHON%"
    exit /b 1
)

echo Show the battle screen in LDPlayer with the Attack button visible.
echo Keep the LDPlayer window unobstructed, then press any key to capture.
pause >nul

"%PYTHON%" -c "import os,sys,uuid; from datetime import datetime; from pathlib import Path; root=Path(os.environ['PROJECT_ROOT']); sys.path.insert(0,str(root/'backend'/'src')); import pyautogui; from autofgo.game_automation import ATTACK,REFERENCE_WIDTH,REFERENCE_HEIGHT,WindowsWindowLocator; target=root/'backend'/'src'/'autofgo'/'assets'/'legacy'/'attack.png'; window=WindowsWindowLocator().find('LDPlayer'); assert abs(window.width-REFERENCE_WIDTH)<=4 and abs(window.height-REFERENCE_HEIGHT)<=4, f'Unexpected LDPlayer size: {window.width}x{window.height}'; image=pyautogui.screenshot(region=(window.left+ATTACK.left,window.top+ATTACK.top,ATTACK.width,ATTACK.height)); staged=target.with_name('attack.new.'+uuid.uuid4().hex+'.png'); image.save(staged); backup=target.with_name('attack.'+datetime.now().strftime('%%Y%%m%%d-%%H%%M%%S')+'.'+uuid.uuid4().hex[:8]+'.png'); target.rename(backup) if target.exists() else None; staged.replace(target); print('Saved:',target); print('Previous sample:',backup if backup.exists() else '(none)')"
if errorlevel 1 (
    echo Capture failed. Check attack.png and any timestamped backup in the same folder.
    exit /b 1
)
echo Check the new attack.png before running automation.
endlocal
