param(
    [string]$XPlanePath = "C:\X-Plane 12"
)

$PluginsDir = "$XPlanePath\Resources\plugins"
$XPPDir     = "$PluginsDir\XPPython3"
$PythonExe  = "$XPPDir\win_x64\pythonw.exe"
$ApiUrl     = "https://api.github.com/repos/pbuckner/x-plane_plugins/releases/latest"

Write-Host "=== Instalador de XPPython3 para AIrport ===" -ForegroundColor Cyan

# 1. Verificar que X-Plane existe
if (-not (Test-Path $PluginsDir)) {
    Write-Error "No se encontro X-Plane en: $XPlanePath"
    Write-Host "Uso: .\install_xppython3.ps1 -XPlanePath 'D:\X-Plane 12'"
    exit 1
}

# 2. Descargar e instalar XPPython3 si no existe o si el usuario quiere actualizar
$install = $true
if (Test-Path $XPPDir) {
    $resp = Read-Host "XPPython3 ya esta instalado. Actualizar? (s/n)"
    $install = $resp -eq 's'
}

if ($install) {
    Write-Host "Obteniendo ultima version de XPPython3..." -ForegroundColor Yellow
    try {
        $release = Invoke-RestMethod -Uri $ApiUrl -Headers @{ "User-Agent" = "AIrport-installer" }
    } catch {
        Write-Error "No se pudo conectar a GitHub: $_"
        exit 1
    }

    # Buscar el asset ZIP
    $asset = $release.assets | Where-Object { $_.name -match "XPPython3.*\.zip" } | Select-Object -First 1
    if (-not $asset) {
        Write-Error "No se encontro el ZIP de XPPython3 en el release."
        exit 1
    }

    $zipPath = "$env:TEMP\XPPython3.zip"
    Write-Host "Descargando $($asset.name)..." -ForegroundColor Yellow
    Invoke-WebRequest -Uri $asset.browser_download_url -OutFile $zipPath -UseBasicParsing

    Write-Host "Extrayendo en $PluginsDir..." -ForegroundColor Yellow
    if (Test-Path $XPPDir) { Remove-Item $XPPDir -Recurse -Force }
    Expand-Archive -Path $zipPath -DestinationPath $PluginsDir -Force
    Remove-Item $zipPath

    Write-Host "XPPython3 instalado correctamente." -ForegroundColor Green
}

# 3. Instalar dependencias pip de AIrport
if (-not (Test-Path $PythonExe)) {
    Write-Error "No se encontro pythonw.exe en $PythonExe"
    exit 1
}

Write-Host "Instalando dependencias de AIrport..." -ForegroundColor Yellow
& $PythonExe -s -m pip install `
    xplane-airports `
    psycopg2-binary `
    redis `
    folium `
    networkx `
    matplotlib `
    paho-mqtt `
    imgui `
    transformers `
    influxdb-client

Write-Host ""
Write-Host "Listo. Recarga los scripts en X-Plane: Plugins > XPPython3 > Reload Scripts" -ForegroundColor Green
