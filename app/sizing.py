"""sizing.py — a sizing fix for one headroom finding: Muse Spark proposes new transistor sizes, Kaaval's own engine
proves them.

Each round, Muse Spark reads the finding (the device, the conditions where it leaves saturation, its margins), the
block's schematic netlist and the operating point at nominal, and answers with a few W / L changes (SIZING_SCHEMA).
The changes are written into the block's schematic, the designer's testbench is simulated again at the same 45
conditions as the review, and the result is judged: the device saturated at all 45, and no finding that the original
design did not have. If a round fails, Muse Spark is told what was measured and tries again (ROUNDS at most). A fix is
only called verified when the simulation says so; Muse Spark's reasons are shown beside it, never instead of it.
"""
import re

from app import engine, planner

ROUNDS = 3
CORNERS = ("tt", "ss", "ff", "sf", "fs")
CONDS = [[t, v] for t in (-40, 27, 125) for v in (0.9, 1.0, 1.1)]
W_MIN, W_MAX, L_MIN, L_MAX = 0.42, 100.0, 0.15, 20.0

SIZING_SCHEMA = {"name": "kaaval_sizing", "schema": {
    "type": "object", "additionalProperties": False, "required": ["changes", "why"],
    "properties": {
        "changes": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["device", "W", "L"],
            "properties": {"device": {"type": "string"}, "W": {"type": "number"}, "L": {"type": "number"}}}},
        "why": {"type": "string"}}}}

SIZING_SYSTEM = """You are a senior analog designer sizing sky130 transistors (sky130_fd_pr nfet_01v8 / pfet_01v8).
One transistor leaves saturation (Vds below Vdsat) at some process / temperature / supply conditions. Propose the
smallest change of W and L (micrometres: sky130 reads W and L in um) that keeps it saturated at all 45 conditions
without moving the circuit's bias much. Rules:
- name devices exactly as the schematic's instances (M1, M2, ...), never invent one;
- keep matched devices matched: a differential pair, a mirror and its reference change together, by the same ratio;
- W between 0.42 and 100, L between 0.15 and 20; change at most 4 devices;
- headroom comes from overdrive: a device's Vdsat falls as W/L rises, and the devices stacked with it share the supply.
Every proposal is simulated at all 45 conditions; you will be told what was measured if it fails. Say why in "why", in
two or three sentences a designer can check."""


def _cell_of(dut_sch, device):
    """The instance name inside the block ('x2.xm1' -> 'M1')."""
    last = device.split(".")[-1]
    return last[1:].upper() if re.match(r"(?i)^x[mrcq]\w*$", last) else last.upper()


def apply(files, sch, changes):
    """files with the W / L of `changes` written into schematic `sch` (xschem text); (new files, what changed,
    errors). Only instances of that schematic change."""
    text = files.get(sch)
    if text is None:
        return files, [], [f"{sch} is not in the design"]
    done, errors = [], []
    for c in changes:
        name = _cell_of(sch, c["device"])
        w, l = float(c["W"]), float(c["L"])
        if not (W_MIN <= w <= W_MAX and L_MIN <= l <= L_MAX):
            errors.append(f"{name}: W={w} L={l} is outside W {W_MIN}..{W_MAX}, L {L_MIN}..{L_MAX}")
            continue
        pat = re.compile(r"(C \{[^}]*\}\s+\S+\s+\S+\s+\S+\s+\S+\s+\{)([^}]*)\}")
        hit = [False]

        def edit(m):
            attrs = m.group(2)
            if not re.search(rf"(?m)(^|\s)name={re.escape(name)}(\s|$)", attrs, re.I):
                return m.group(0)
            old = (re.search(r"(?<![\w])W=(\S+)", attrs), re.search(r"(?<![\w])L=(\S+)", attrs))
            if not all(old):
                return m.group(0)
            hit[0] = True
            done.append(dict(device=name, before=f"W={old[0].group(1)} L={old[1].group(1)}", after=f"W={w:g} L={l:g}"))
            attrs = re.sub(r"(?<![\w])W=\S+", f"W={w:g}", attrs, count=1)
            attrs = re.sub(r"(?<![\w])L=\S+", f"L={l:g}", attrs, count=1)
            return m.group(1) + attrs + "}"

        text = pat.sub(edit, text)
        if not hit[0]:
            errors.append(f"{name} is not an instance with W and L in {sch}")
    return dict(files, **{sch: text}), done, errors


def sweep(files, tb, fix_traps):
    """The review's 45-condition sweep of testbench `tb` on these files: (analyse result, testbench result)."""
    ws = engine.upload(files)
    r = engine.testbench(ws, tb, fix_traps)
    for k in CORNERS:
        engine.corner(ws, tb, k, CONDS, fix_traps)
    return engine.analyse(ws, tb), r


def _key(f):
    return f["rule"], f.get("device", "")


def fix(files, tb, finding, fix_traps=False, log=lambda *a, **k: None, arm="muse"):
    """The sizing loop for one headroom finding (its detail: device, worst, worst_margin, nominal_margin, conds).
    Returns {verified, by, rounds: [{changes, why, result}], changes, why, n_conditions, ...} for the bench."""
    if not planner.configured(arm):
        raise planner.PlannerError("Muse Spark is not connected: start Kaaval with its key set.")
    dev = finding["device"]
    before, tbr = sweep(files, tb, fix_traps)
    sch = tbr.get("dut") or ""
    if not sch or sch not in files:
        raise ValueError("the testbench's block schematic was not found, so there is nothing to resize")
    base = {_key(f) for f in before.get("findings", [])}
    cell = files[sch]
    netlist = "\n".join(l for l in cell.splitlines() if l.startswith("C {") and "sky130_fd_pr" in l or "name=" in l)[:6000]
    msgs = [{"role": "system", "content": SIZING_SYSTEM},
            {"role": "user", "content": (
                f"# The finding\n{finding.get('message') or finding.get('title', '')}\n"
                f"worst condition {finding.get('worst')}, worst margin {finding.get('worst_margin')} V, "
                f"nominal margin {finding.get('nominal_margin')} V, failing at {finding.get('conds')}\n\n"
                f"# The block: {sch} (the device is {dev} in the testbench, instance {_cell_of(sch, dev)} here)\n"
                f"{cell[:9000]}\n\n# The testbench\n{files.get(tb, '')[:4000]}\n\n"
                f"# Operating point at nominal (from the review)\n{str(tbr.get('nominal'))[:5000]}")}]
    rounds = []
    for i in range(ROUNDS):
        out, _ = planner._chat(arm, msgs, schema=SIZING_SCHEMA)
        changes, why = out.get("changes") or [], str(out.get("why", "")).strip()
        log(f"Muse Spark proposes (round {i + 1}): " + ", ".join(f"{c['device']} W={c['W']:g} L={c['L']:g}" for c in changes)
            + (f": {why}" if why else ""))
        new, done, errors = apply(files, sch, changes)
        if errors or not done:
            res = dict(ok=False, why="; ".join(errors) or "no change applied")
        else:
            an, _ = sweep(new, tb, fix_traps)
            fs = an.get("findings", [])
            still = next((f for f in fs if f["rule"].startswith("analog/headroom") and f.get("device") == dev), None)
            fresh = [f for f in fs if _key(f) not in base]
            res = dict(ok=still is None and not fresh, n_bad=(still or {}).get("n_bad", 0),
                       worst_margin=(still or {}).get("worst_margin"),
                       new=[f["message"][:200] for f in fresh][:4], failed=len(an.get("failed", [])))
        rounds.append(dict(changes=done or changes, why=why, result=res))
        if res["ok"]:
            log(f"Verified: {dev} saturated at all 45 conditions after {', '.join(c['device'] + ' ' + c['after'] for c in done)}, "
                "with no new finding", "info")
            return dict(verified=True, by="muse", changes=done, why=why, rounds=rounds, n_conditions=45,
                        margin_before=finding.get("worst_margin"), schematic=sch)
        said = (res.get("why") or (f"{dev} still leaves saturation at {res['n_bad']}/45 conditions (worst margin "
                f"{res['worst_margin']} V)" if res.get("n_bad") else f"{dev} is fixed, but new findings appear: "
                f"{' | '.join(res['new'])}"))
        log(f"Round {i + 1} not verified: {said}", "warn")
        msgs += [{"role": "assistant", "content": str(out)},
                 {"role": "user", "content": f"Simulated at all 45 conditions: {said}. Propose again."}]
    return dict(verified=False, by="muse", rounds=rounds, n_conditions=45, margin_before=finding.get("worst_margin"),
                schematic=sch, why=f"no proposal passed all 45 conditions in {ROUNDS} rounds")
