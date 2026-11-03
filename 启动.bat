@echo off
chcp 65001 >nul
cd /d %~dp0
echo 正在启动【手机换新攻略】，请勿关闭本窗口...
echo 浏览器稍后会自动弹出；如果没有弹出，请手动打开 http://127.0.0.1:8000
echo.
"D:\Python\python.exe" app.py
pause
