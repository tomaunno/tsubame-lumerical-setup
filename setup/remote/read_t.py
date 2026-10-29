"""tsubame-lumerical-setup: open each solved .fsp with lumapi and print the transmission
through monitor T as `LS T <file> <value>`. Run with the Python bundled with Lumerical."""
import sys

import numpy as np
import lumapi

with lumapi.FDTD(hide=True) as f:
    print("LS LUMAPI=ok", flush=True)
    for fn in sys.argv[1:]:
        try:
            f.load(fn)
            print(f"LS T {fn} {abs(float(np.ravel(f.transmission('T'))[0])):.6f}", flush=True)
        except Exception as exc:     # an unsolved file has no results; report it and go on
            print(f"LS T {fn} error {type(exc).__name__}: {exc}"[:300], flush=True)
