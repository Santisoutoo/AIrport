#!/usr/bin/env bash
set -euo pipefail

XPLANE_PATH="${1:-$HOME/X-Plane 12}"
PLUGINS_DIR="$XPLANE_PATH/Resources/plugins"
XPP_DIR="$PLUGINS_DIR/XPPython3"
API_URL="https://api.github.com/repos/pbuckner/x-plane_plugins/releases/latest"

# Detectar plataforma
if [[ "$OSTYPE" == "darwin"* ]]; then
    PYTHON_BIN="$XPP_DIR/mac_x64/python3"
else
    PYTHON_BIN="$XPP_DIR/lin_x64/python3"
fi

echo "=== Instalador de XPPython3 para AIrport ==="

# 1. Verificar que X-Plane existe
if [[ ! -d "$PLUGINS_DIR" ]]; then
    echo "Error: No se encontro X-Plane en: $XPLANE_PATH"
    echo "Uso: ./install_xppython3.sh '/ruta/a/X-Plane 12'"
    exit 1
fi

# 2. Descargar e instalar XPPython3
INSTALL=true
if [[ -d "$XPP_DIR" ]]; then
    read -r -p "XPPython3 ya esta instalado. Actualizar? (s/n): " resp
    [[ "$resp" != "s" ]] && INSTALL=false
fi

if $INSTALL; then
    echo "Obteniendo ultima version de XPPython3..."
    RELEASE_JSON=$(curl -sL -H "User-Agent: AIrport-installer" "$API_URL")
    DOWNLOAD_URL=$(echo "$RELEASE_JSON" | python3 -c "
import sys, json
data = json.load(sys.stdin)
assets = [a for a in data['assets'] if 'XPPython3' in a['name'] and a['name'].endswith('.zip')]
print(assets[0]['browser_download_url'] if assets else '')
")

    if [[ -z "$DOWNLOAD_URL" ]]; then
        echo "Error: No se encontro el ZIP en el release de GitHub."
        exit 1
    fi

    ZIP_PATH="/tmp/XPPython3.zip"
    echo "Descargando..."
    curl -L -o "$ZIP_PATH" "$DOWNLOAD_URL"

    echo "Extrayendo en $PLUGINS_DIR..."
    [[ -d "$XPP_DIR" ]] && rm -rf "$XPP_DIR"
    unzip -q "$ZIP_PATH" -d "$PLUGINS_DIR"
    rm "$ZIP_PATH"

    echo "XPPython3 instalado correctamente."
fi

# 3. Instalar dependencias pip de AIrport
if [[ ! -f "$PYTHON_BIN" ]]; then
    echo "Error: No se encontro Python en $PYTHON_BIN"
    exit 1
fi

echo "Instalando dependencias de AIrport..."
"$PYTHON_BIN" -s -m pip install \
    xplane-airports \
    psycopg2-binary \
    redis \
    folium \
    networkx \
    matplotlib \
    paho-mqtt \
    imgui \
    transformers \
    influxdb-client

echo ""
echo "Listo. Recarga los scripts en X-Plane: Plugins > XPPython3 > Reload Scripts"
