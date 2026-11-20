@echo off
chcp 65001 >nul
set L=%~1
if "%L%"=="" set L=monomials.mth
python server.py "%L%"
pause
