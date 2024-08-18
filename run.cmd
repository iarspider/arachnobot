@echo off
SET PATH=e:\Python311;e:\Python311\Scripts;%PATH%
REM set PYTHONASYNCIODEBUG=1
if exist bot.db.1 copy bot.db.1 bot.db.2
copy bot.db bot.db.1
:START
pipenv run python bot.py
goto START
pause