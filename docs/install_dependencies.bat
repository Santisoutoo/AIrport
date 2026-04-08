@echo off
set PYTHON="C:\X-Plane 12\Resources\plugins\XPPython3\win_x64\pythonw.exe"

echo Installing AIrport dependencies

%PYTHON% -s -m pip install ^
    xplane-airports ^
    psycopg2-binary ^
    redis ^
    folium ^
    networkx ^
    matplotlib ^
    paho-mqtt ^
    imgui ^
    transformers ^
    influxdb-client

echo.
echo Hecho. Recarga los scripts en X-Plane: Plugins ^> XPPython3 ^> Reload Scripts
pause
