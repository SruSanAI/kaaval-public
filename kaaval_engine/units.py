"""units.py — physical-plausibility audit of sky130 SPICE netlists (check family 1; deterministic, no model).

The sky130 ngspice library sets `.option scale=1.0u`, so every geometric instance parameter (W, L, area, perim) is read
in micrometres. A value written for another convention then simulates as a different device, silently:
  - the stock xschem diode symbol writes area=1e12 perim=4e6 (picometre units) -> 1e12 um^2 = a 1 m^2 diode
    (measured 27 Oct 2026, open_pdks c6d73a35: 21.4 A at +0.5 V, 14.8 uA reverse leakage at -1 V);
  - SI-style W=1u -> 1e-6 um, far below any drawable device.
This audit converts each device to the silicon it implies and compares it with the design rules and the chip area
the project actually has (a Tiny Tapeout tile), so a device that could never fit is reported with its numbers.

    python -m kaaval_engine.units <repo_dir> [--tiles 1x2] [--json out.json]
"""
import argparse, json, os, re, sys

# Tiny Tapeout tile in um (TT06+ analog template); a project with tiles "AxB" has A x B of these
TILE_W, TILE_H = 161.0, 111.52
SUFFIX = {"t": 1e12, "g": 1e9, "meg": 1e6, "k": 1e3, "m": 1e-3, "u": 1e-6, "n": 1e-9, "p": 1e-12, "f": 1e-15}
NUM = re.compile(r"^([+-]?(?:\d+\.?\d*|\.\d+)(?:e[+-]?\d+)?)(meg|[tgkmunpf])?[a-z]*$", re.I)
MODEL = re.compile(r"sky130_fd_pr__(\w+)", re.I)
PARAM = re.compile(r"(\w+)\s*=\s*('[^']*'|\{[^}]*\}|\S+)")
NETLIST_EXT = (".spice", ".sp", ".cir", ".net", ".spi")


def num(s):
    """SPICE number -> float, None for expressions or names."""
    m = NUM.match(s.strip().strip("'{}"))
    if not m:
        return None
    return float(m.group(1)) * SUFFIX.get((m.group(2) or "").lower(), 1.0)


def logical_lines(path):
    """(line_no, text) with '+' continuations joined and comments dropped."""
    out, buf, start = [], "", 0
    with open(path, errors="replace") as f:
        for i, raw in enumerate(f, 1):
            line = raw.rstrip("\n")
            s = line.strip()
            if s.startswith("+"):
                buf += " " + s[1:]
                continue
            if buf:
                out.append((start, buf))
            buf, start = ("" if not s or s.startswith("*") else s), i
            buf = buf.split(";")[0] if buf else buf
        if buf:
            out.append((start, buf))
    return out


def family(model):
    m = model.lower()
    if "fet" in m:
        return "mos"
    if "diode" in m:
        return "diode"
    if m.startswith("cap_mim") or m.startswith("cap_var"):
        return "cap"
    if m.startswith("res_"):
        return "res"
    return None


def audit_file(path, chip_area_um2):
    return audit_lines(logical_lines(path), path, chip_area_um2)


def audit_lines(lines, path, chip_area_um2):
    """lines: (line_no, logical SPICE line) pairs; returns (findings, device count)."""
    findings, devices, scale_lines = [], 0, []
    for ln, text in lines:
        low = text.lower()
        if low.startswith(".option") and "scale" in low:
            scale_lines.append((ln, text))
            continue
        if not text[0].lower() in "xmdrc":
            continue
        mm = MODEL.search(text)
        if not mm:
            continue
        fam = family(mm.group(1))
        if not fam:
            continue
        devices += 1
        name = text.split()[0]
        p = {k.lower(): v for k, v in PARAM.findall(text[mm.end():])}
        vals = {k: num(v) for k, v in p.items()}

        def flag(rule, sev, msg, **kw):
            findings.append(dict(file=path, line=ln, device=name, model=mm.group(0), rule=rule, severity=sev,
                                 message=msg, **kw))

        if fam == "diode":
            a, per = vals.get("area"), vals.get("perim") or vals.get("pj")
            if a is not None and a > chip_area_um2:
                flag("diode_area_vs_chip", "fail",
                     f"area={p['area']} reads as {a:.3g} um^2 under the PDK's 1 um scale "
                     f"({a * 1e-12:.3g} m^2); the whole project is {chip_area_um2:.0f} um^2. Written in picometre "
                     f"units? -> area={a / 1e12:.3g} perim={(per or 0) / 1e6:.3g} (um^2 / um)",
                     implied_um2=a, chip_um2=chip_area_um2,
                     fix={"area": f"{a / 1e12:.6g}", "perim": f"{(per or 0) / 1e6:.6g}"} if per else None)
            elif a is not None and 0 < a < 1e-6:
                flag("diode_area_tiny", "fail", f"area={p['area']} reads as {a:.3g} um^2 (SI m^2 under a 1 um scale?)",
                     implied_um2=a)
        elif fam == "mos":
            w, l = vals.get("w"), vals.get("l")
            for k, v in (("W", w), ("L", l)):
                if v is None:
                    continue
                if 0 < v < 1e-3:
                    flag("mos_si_units", "fail", f"{k}={p[k.lower()]} reads as {v:.3g} um under the 1 um scale "
                         f"(written in metres?); min drawn L is 0.15 um", value_um=v)
                elif v > 2 * max(TILE_W, TILE_H) * 4:
                    flag("mos_too_large", "fail", f"{k}={p[k.lower()]} um cannot fit the project area", value_um=v)
            mult, m = vals.get("mult"), vals.get("m")
            if mult and m and mult > 1 and m > 1 and "mult" in p and "m" in p:
                flag("mos_mult_and_m", "info", f"both mult={p['mult']} and m={p['m']}; check the device count is "
                     f"{int(m)} and not {int(m * mult)} in your simulator/PDK version", m=m, mult=mult)
        elif fam in ("cap", "res"):
            for k in ("w", "l"):
                v = vals.get(k)
                if v is None:
                    continue
                if 0 < v < 1e-3:
                    flag(f"{fam}_si_units", "fail", f"{k.upper()}={p[k]} reads as {v:.3g} um (metres?)", value_um=v)
                elif fam == "cap" and v > max(TILE_W, TILE_H) * 4:
                    flag("cap_too_large", "fail", f"{k.upper()}={p[k]} um cannot fit the project area", value_um=v)
    if len(scale_lines) > 1:
        findings.append(dict(file=path, line=scale_lines[1][0], device="", model="", rule="scale_redefined",
                             severity="warn", message="more than one `.option scale`; ngspice >= 35 keeps only the first",
                             lines=[x[0] for x in scale_lines]))
    own = [num(m.group(1)) for _, t in scale_lines for m in [re.search(r"scale\s*=\s*(\S+)", t, re.I)] if m]
    own = [s for s in own if s and abs(s - 1e-6) > 1e-12]
    if own:
        # the file sizes its devices in its own units; which scale wins depends on include order (ngspice >= 35 keeps
        # the first), so a device can be read 1 um/scale times too large. Report the conflict once, with both readings,
        # and do not count the size checks as failures: under the file's own scale they may be right.
        ratio = 1e-6 / own[0]
        for x in findings:
            if x["severity"] == "fail" and x["rule"] != "scale_redefined":
                x["severity"], x["message"] = "warn", x["message"] + f" [file sets its own scale={own[0]:g}]"
        findings.append(dict(file=path, line=scale_lines[0][0], device="", model="", rule="scale_conflict",
                             severity="warn", message=f"file sets `.option scale={own[0]:g}` but the sky130 library sets "
                             f"scale=1u; ngspice >= 35 keeps the FIRST one, so if the PDK library is loaded first every "
                             f"size here is read {ratio:g}x larger (e.g. W=45 -> 45 um instead of {45 * own[0] * 1e6:g} um)",
                             file_scale=own[0]))
    return findings, devices


def audit_repo(root, tiles="1x2"):
    a, b = (int(x) for x in re.findall(r"\d+", tiles)[:2]) if re.search(r"\d+x\d+", tiles or "") else (1, 2)
    chip = a * TILE_W * b * TILE_H
    findings, files, devices = [], 0, 0
    for d, dirs, fs in os.walk(root):
        dirs[:] = [x for x in dirs if not x.startswith(".")]
        for f in fs:
            if f.lower().endswith(NETLIST_EXT) or f.endswith(".sch"):
                path = os.path.join(d, f)
                if f.endswith(".sch"):
                    from kaaval_engine import sch
                    fd, nd = audit_lines(sch.device_lines(path), path, chip)
                else:
                    fd, nd = audit_file(path, chip)
                files += 1
                devices += nd
                for x in fd:
                    x["file"] = os.path.relpath(x["file"], root)
                findings += fd
    return dict(root=root, tiles=tiles, chip_um2=round(chip), netlists=files, devices=devices, findings=findings)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("repo")
    ap.add_argument("--tiles", default="1x2")
    ap.add_argument("--json")
    a = ap.parse_args(argv)
    r = audit_repo(a.repo, a.tiles)
    if a.json:
        json.dump(r, open(a.json, "w"), indent=1)
    for x in r["findings"]:
        print(f"{x['severity'].upper():5} {x['file']}:{x['line']} {x['device']} {x['rule']}: {x['message']}")
    print(f"{r['netlists']} netlists, {r['devices']} sky130 devices, {len(r['findings'])} findings")


if __name__ == "__main__":
    sys.exit(main())


def correct_circuit(circuit, chip_area_um2=TILE_W * 2 * TILE_H):
    """The circuit with its units traps corrected, for simulating what the silicon actually is, and the list of
    corrections made. Today: diode area / perimeter written in picometre units (area > the whole chip) are read back as
    um^2 / um (area / 1e12, perimeter / 1e6), the same correction the units audit proposes. Lines without a trap are
    left untouched."""
    out, changes = [], []
    for line in circuit.splitlines():
        mm = MODEL.search(line)
        if mm and family(mm.group(1)) == "diode" and line.split() and line.split()[0][0].lower() in "xd":
            p = {k.lower(): v for k, v in PARAM.findall(line[mm.end():])}
            a = num(p.get("area", ""))
            if a is not None and a > chip_area_um2:
                new = re.sub(r"(?i)\barea\s*=\s*\S+", f"area={a / 1e12:.6g}", line)
                for key in ("perim", "pj"):
                    v = num(p.get(key, ""))
                    if v is not None:
                        new = re.sub(rf"(?i)\b{key}\s*=\s*\S+", f"{key}={v / 1e6:.6g}", new)
                changes.append(dict(device=line.split()[0], before=f"area={p['area']}", after=f"area={a / 1e12:.6g}"))
                line = new
        out.append(line)
    return "\n".join(out), changes
