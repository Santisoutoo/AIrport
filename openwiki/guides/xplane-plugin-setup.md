# X-Plane Plugin Setup

The in-sim plugin is **not** installed automatically. It spawns/moves aircraft and speaks the
pilot readbacks inside X-Plane 12 via [XPPython3](https://xppython3.readthedocs.io/).

**What's what:** [`plugins/`](../../plugins/) holds the deployable files you copy into
X-Plane; [`xplane_plugin/`](../../xplane_plugin/) is the plugin's source/development tree —
see [X-Plane (module reference)](../xplane.md).

## Option A — scripted install (recommended)

The scripts in [`docs/install/`](../../docs/install/) download the latest XPPython3 release,
extract it into `<X-Plane 12>/Resources/plugins/`, and pip-install the AIrport dependencies
into the simulator's bundled Python (`xplane-airports`, `psycopg2-binary`, `redis`, `folium`,
`networkx`, `matplotlib`, `paho-mqtt`, `imgui`, `transformers`, `influxdb-client`).

**Windows** — double-click
[`docs/install/install_dependencies.bat`](../../docs/install/install_dependencies.bat), or run
the underlying script with a custom path (default `C:\X-Plane 12`):

```powershell
.\docs\install\install_xppython3.ps1 -XPlanePath "D:\X-Plane 12"
```

**macOS / Linux** (default `$HOME/X-Plane 12`):

```bash
./docs/install/install_xppython3.sh "/path/to/X-Plane 12"
```

If XPPython3 is already installed the scripts ask before updating it.

## Option B — manual install

1. Install [XPPython3](https://xppython3.readthedocs.io/) into X-Plane 12.
2. Copy into `<X-Plane 12>/Resources/plugins/PythonPlugins/`:
   - [`plugins/PI_spawn_obj.py`](../../plugins/PI_spawn_obj.py)
   - the entire [`plugins/GND/`](../../plugins/GND/) folder
3. Install the pip dependencies listed above into XPPython3's bundled Python
   (`<X-Plane 12>/Resources/plugins/XPPython3/win_x64/pythonw.exe -s -m pip install …` on
   Windows; `mac_x64/python3` / `lin_x64/python3` on macOS/Linux).

## Verify

1. Launch X-Plane 12 → the plugin appears under the **Plugins** menu.
   After copying new plugin files you can also use **Plugins → XPPython3 → Reload Scripts**.
2. Start the backend **before** flying: the plugin talks to the Orchestrator on the host at
   port `8007` (`docker compose up`).
3. Fly the [Quickstart](quickstart.md) — issue a taxi clearance and watch the aircraft move.

Plugin not showing up or aircraft not moving → [Troubleshooting](troubleshooting.md).

## Related

[Installation](installation.md) · [Quickstart](quickstart.md) · [X-Plane (module reference)](../xplane.md)
