@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
call _env.bat || exit /b
echo ================================================================
echo Stage 09 - Hardware-in-the-loop stream/model test
echo ================================================================
echo Reads 100 real N6DF v2 frames by default and validates CRC, sensor frame
echo progression and the embedded Neural-ART result for that exact frame.
echo A fast RPS ON/RPS STATUS preflight rejects an old SRAM image or NPU init
echo failure before loading TensorFlow. Diagnostics are saved under reports.
echo The same input is run through host TFLite; class and raw int8 scores are
echo compared so this proves the NPU executed, not merely that the sensor works.
echo.
"%TRAINING_PY%" scripts\09_hil_validate.py %*
set "RESULT=%ERRORLEVEL%"
pause
exit /b %RESULT%
