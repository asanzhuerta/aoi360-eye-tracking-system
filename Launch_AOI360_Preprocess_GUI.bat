@echo off
setlocal

set "REPO_ROOT=%~dp0"
pushd "%REPO_ROOT%"

if exist "python\offline\.venv\Scripts\python.exe" (
    "python\offline\.venv\Scripts\python.exe" "python\offline\scripts\preprocess_gui.py"
) else (
    py -3 "python\offline\scripts\preprocess_gui.py"
)

popd
endlocal
