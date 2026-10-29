"""paths.py — where the open tools live. Defaults suit a volare install on a workstation; a container sets the
environment instead (see Dockerfile).

    KAAVAL_PDK_ROOT     the sky130A folder (default ~/.volare/sky130A)
    KAAVAL_XSCHEM_LIB   xschem's own symbol library, devices/*.sym (default: first one found of the usual places)
"""
import os

PDK_ROOT = os.path.expanduser(os.environ.get("KAAVAL_PDK_ROOT", "~/.volare/sky130A"))
PDK_LIB = os.path.join(PDK_ROOT, "libs.tech", "ngspice", "sky130.lib.spice")
PDK_XSCHEM = os.path.join(PDK_ROOT, "libs.tech", "xschem")
_XSCHEM_CANDIDATES = [os.environ.get("KAAVAL_XSCHEM_LIB", ""), "~/xschem-macos/share/xschem/xschem_library",
                      "/usr/local/share/xschem/xschem_library", "/usr/share/xschem/xschem_library"]
XSCHEM_LIB = next((os.path.expanduser(p) for p in _XSCHEM_CANDIDATES if p and os.path.isdir(os.path.expanduser(p))),
                  os.path.expanduser("~/xschem-macos/share/xschem/xschem_library"))
SYMBOL_PATHS = [PDK_XSCHEM, XSCHEM_LIB]
