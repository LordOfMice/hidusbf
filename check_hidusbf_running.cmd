@echo off
sc query hidusbf | find "RUNNING" > nul
if not errorlevel 1 goto end
echo Hidusfbf is NOT running !!!  
pause 
:end
