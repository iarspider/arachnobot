@echo off
REM set PYTHONASYNCIODEBUG=1
if exist bot.db.1 copy bot.db.1 bot.db.2
copy bot.db bot.db.1
pipenv run python -X tracemalloc bot.py
pause