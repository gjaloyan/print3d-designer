"""Keep headless OpenGL chatter out of the scripts' output: import it before pyvista.

Without a display VTK tries X, then every EGL device, and Mesa prints a line
for each device it cannot open. On a server one render printed about 5 KB of
such warnings, which an agent reads in full: they filled its context and
buried the RESULT line. Errors still print.
"""

import os

os.environ.setdefault("EGL_LOG_LEVEL", "fatal")  # Mesa: "libEGL warning: failed to open /dev/dri/..."

from vtkmodules.vtkCommonCore import vtkLogger  # noqa: E402

# VTK: "bad X server connection", "EGL device index: 0 could not be initialized"
vtkLogger.SetStderrVerbosity(vtkLogger.VERBOSITY_ERROR)
