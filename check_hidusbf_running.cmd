@echo off
sc query hidusbf | find /I "RUNNING" > nul
if not errorlevel 1 goto end
echo Hidusbf is NOT running !!!  
pause 
:end
