@echo off
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0emulate-ec2.ps1" %*
exit /b %errorlevel%
