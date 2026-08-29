"""XPPython3 loader for the AIrport plugin.

XPPython3 only loads ``PI_*.py`` files sitting at the root of
``<X-Plane>/Resources/plugins/PythonPlugins/``. Copy this file there and deploy
the repository as ``PythonPlugins/AIrport/`` (folder copy or junction) so the
package imports below resolve.
"""

from AIrport.xplane_plugin.airport_plugin.PI_userInterface import PythonInterface

__all__ = ["PythonInterface"]
