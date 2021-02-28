@echo off
REM set PYTHONASYNCIODEBUG=1
pipenv run python -X tracemalloc bot.py
pause