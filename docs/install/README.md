# Instalación de XPPython3 y dependencias de AIrport

> **Guía mantenida (en inglés):**
> [X-Plane Plugin Setup](https://github.com/Santisoutoo/AIrport/wiki/X-Plane-Plugin-Setup)
> en la wiki del proyecto.

Scripts para instalar automáticamente el plugin XPPython3 en X-Plane 12 y las dependencias Python del proyecto.

## Archivos

| Archivo | Plataforma | Descripción |
|---|---|---|
| `install_xppython3.ps1` | Windows | Script principal (PowerShell) |
| `install_xppython3.sh` | macOS / Linux | Script principal (Bash) |
| `install_dependencies.bat` | Windows | Atajo que llama al `.ps1` |

## Uso

### Windows

Doble clic en `install_dependencies.bat`, o desde PowerShell:

```powershell
# Ruta por defecto: C:\X-Plane 12
.\install_xppython3.ps1

# Ruta personalizada
.\install_xppython3.ps1 -XPlanePath "D:\X-Plane 12"
```

### macOS / Linux

```bash
chmod +x install_xppython3.sh
./install_xppython3.sh

# Ruta personalizada
./install_xppython3.sh "/ruta/a/X-Plane 12"
```

## Qué hacen los scripts

1. Descargan el último release de XPPython3 desde GitHub
2. Extraen el plugin en `<X-Plane>/Resources/plugins/XPPython3/`
3. Instalan las dependencias pip de AIrport usando el Python embebido

Si XPPython3 ya está instalado, preguntan si actualizar antes de continuar.

## Después de instalar

Abre X-Plane 12 y recarga los scripts desde **Plugins > XPPython3 > Reload Scripts**.
