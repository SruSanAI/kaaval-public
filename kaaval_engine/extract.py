"""extract.py — a netlist from the layout, for designs committed as Magic layout only (no schematic, no netlist).

About one Tiny Tapeout analog repository in ten holds only Magic .mag files, so a review had nothing to simulate. Here
the open Magic VLSI tool reads the top cell named in info.yaml and writes its devices as SPICE (ext2spice lvs: devices
and connectivity, no parasitics), which the review then treats like any SPICE subcircuit.

Magic runs our own script in a fresh temporary folder: the repository's .magicrc and tcl scripts are never read or
run, only its .mag layout data. Nothing is written into the repository.

    text, note = extract.from_layout(root)      # (SPICE text or None, a sentence for the review)
"""
import os, re, shutil, subprocess, tempfile

from kaaval_engine.paths import PDK_ROOT

OUT = "kaaval_extracted"                     # where the extracted netlist appears in the review's file set
MAGICRC = os.path.join(PDK_ROOT, "libs.tech", "magic", "sky130A.magicrc")


def available():
    return bool(shutil.which("magic")) and os.path.isfile(MAGICRC)


def needed(files):
    """True when the file set {relative path: text} has layout but no schematic and no SPICE subcircuit."""
    if any(f.endswith(".sch") for f in files):
        return False
    if any(re.search(r"(?im)^\s*\.subckt\s", t) for f, t in files.items()
           if f.lower().endswith((".spice", ".sp", ".cir", ".spi"))):
        return False
    return any(f.endswith(".mag") for f in files)


def top_cell(root):
    """(top cell name, relative .mag path) from info.yaml's top_module, or (None, None)."""
    info = os.path.join(root, "info.yaml")
    if not os.path.isfile(info):
        return None, None
    m = re.search(r"""(?m)^\s*top_module\s*:\s*["']?([A-Za-z_]\w*)""", open(info, errors="replace").read())
    if not m:
        return None, None
    for d, dirs, fs in os.walk(root):
        dirs[:] = [x for x in dirs if not x.startswith(".")]
        if m.group(1) + ".mag" in fs:
            return m.group(1), os.path.relpath(os.path.join(d, m.group(1) + ".mag"), root)
    return m.group(1), None


def from_layout(root, timeout=120):
    """(SPICE text, note) for the top cell's layout, or (None, why not)."""
    if not available():
        return None, "Magic (layout extraction) is not installed on this server"
    top, rel = top_cell(root)
    if not rel:
        return None, (f"no layout of the top cell {top} in the repository" if top else
                      "info.yaml names no top_module, so the layout's top cell is unknown")
    text, err = cell(root, top, rel, timeout)
    if not text:
        return None, err
    head = (f"* {top}: netlist extracted by Kaaval from the layout {rel} with Magic (ext2spice lvs: devices and\n"
            "* connectivity, no parasitics). The repository holds no schematic or netlist of it.\n")
    return head + text, (f"No schematic or netlist in the repository: Kaaval extracted {top}'s netlist from its layout "
                         f"({rel}) with Magic, devices only (no parasitics), as {OUT}/{top}.spice.")


def cell(root, top, rel, timeout=120, parasitics=False, flat=False):
    """(SPICE text of one layout cell, or None, error): Magic's ext2spice lvs of `top`, whose layout is at `rel`.
    parasitics=True keeps the extracted wire and junction capacitances (every one, as Magic computes them; no wire
    resistance), the post-layout netlist a simulation compares with the schematic. flat=True writes one transistor-level
    cell (ext2spice hierarchy off), as a layout-vs-schematic comparison wants."""
    dirs = sorted({os.path.dirname(os.path.join(d, f)) for d, ds, fs in os.walk(root) for f in fs if f.endswith(".mag")
                   and not any(p.startswith(".") for p in os.path.relpath(d, root).split(os.sep))})
    with tempfile.TemporaryDirectory(prefix="kaaval_ext_") as t:
        mode = ("ext2spice lvs\next2spice cthresh 0\next2spice extresist off\n" if parasitics else "ext2spice lvs\n")
        mode += "ext2spice hierarchy off\next2spice subcircuit top on\n" if flat else ""
        script = ("".join(f"addpath {{{d}}}\n" for d in dirs) +
                  f"load {top}\nselect top cell\nextract path {{{t}}}\nextract all\n" + mode +
                  f"ext2spice -p {{{t}}} -o {{{os.path.join(t, top + '.spice')}}}\nquit -noprompt\n")
        open(os.path.join(t, "extract.tcl"), "w").write(script)
        env = dict(os.environ, PDK_ROOT=os.path.dirname(PDK_ROOT), PDK=os.path.basename(PDK_ROOT))
        try:
            p = subprocess.run(["magic", "-dnull", "-noconsole", "-rcfile", MAGICRC, os.path.join(t, "extract.tcl")],
                               cwd=t, env=env, capture_output=True, text=True, timeout=timeout, stdin=subprocess.DEVNULL)
        except subprocess.TimeoutExpired:
            return None, f"layout extraction of {top} took over {timeout} s"
        out = os.path.join(t, top + ".spice")
        if not os.path.isfile(out):
            tail = " ".join((p.stdout + p.stderr).split()[-30:])
            return None, f"layout extraction of {top} wrote no netlist ({tail})"
        return open(out, errors="replace").read(), None
