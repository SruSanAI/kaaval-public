"""store.py — runs, their progress events and findings, in one SQLite file (~/.kaaval/kaaval.db)."""
import json, os, sqlite3, threading, time, uuid

DB = os.path.expanduser(os.environ.get("KAAVAL_DB", "~/.kaaval/kaaval.db"))
_lock = threading.Lock()


def _conn():
    os.makedirs(os.path.dirname(DB), exist_ok=True)
    c = sqlite3.connect(DB, check_same_thread=False)
    c.row_factory = sqlite3.Row
    c.executescript("""
    create table if not exists runs(id text primary key, repo text, commit_sha text, status text, stage text,
        created real, finished real, summary text);
    create table if not exists events(run_id text, ts real, stage text, level text, msg text);
    create table if not exists findings(run_id text, id text, rule text, severity text, title text, location text,
        data text);
    create table if not exists live(run_id text primary key, data text);
    create index if not exists ev_run on events(run_id, ts);
    create index if not exists fi_run on findings(run_id);
    """)
    return c


_c = _conn()


def new_run(repo):
    rid = uuid.uuid4().hex[:10]
    with _lock:
        _c.execute("insert into runs values(?,?,?,?,?,?,?,?)", (rid, repo, "", "queued", "queued", time.time(), None, "{}"))
        _c.commit()
    return rid


def update_run(rid, **kw):
    if "summary" in kw:
        kw["summary"] = json.dumps(kw["summary"])
    with _lock:
        _c.execute("update runs set " + ", ".join(f"{k}=?" for k in kw) + " where id=?", (*kw.values(), rid))
        _c.commit()


def event(rid, stage, msg, level="info"):
    with _lock:
        _c.execute("insert into events values(?,?,?,?,?)", (rid, time.time(), stage, level, msg))
        _c.commit()


def add_finding(rid, f):
    fid = uuid.uuid4().hex[:8]
    with _lock:
        _c.execute("insert into findings values(?,?,?,?,?,?,?)",
                   (rid, fid, f["rule"], f["severity"], f["title"], f.get("location", ""), json.dumps(f)))
        _c.commit()
    return fid


def set_live(rid, data):
    with _lock:
        _c.execute("insert or replace into live values(?,?)", (rid, json.dumps(data)))
        _c.commit()


def live(rid):
    r = _c.execute("select data from live where run_id=?", (rid,)).fetchone()
    return json.loads(r["data"]) if r else {}


def update_finding(rid, fid, **kw):
    with _lock:
        r = _c.execute("select data from findings where run_id=? and id=?", (rid, fid)).fetchone()
        if not r:
            return
        d = json.loads(r["data"])
        d.update(kw)
        _c.execute("update findings set data=? where run_id=? and id=?", (json.dumps(d), rid, fid))
        _c.commit()


def finding(rid, fid):
    r = _c.execute("select data from findings where run_id=? and id=?", (rid, fid)).fetchone()
    return json.loads(r["data"]) if r else None


def run(rid):
    r = _c.execute("select * from runs where id=?", (rid,)).fetchone()
    if not r:
        return None
    d = dict(r)
    d["summary"] = json.loads(d["summary"] or "{}")
    return d


def runs(limit=20):
    return [dict(r) for r in _c.execute("select id, repo, commit_sha, status, stage, created, finished, summary "
                                        "from runs order by created desc limit ?", (limit,))]


def events(rid, after=0.0):
    return [dict(r) for r in _c.execute("select ts, stage, level, msg from events where run_id=? and ts>? order by ts",
                                        (rid, after))]


def findings(rid):
    out = []
    for r in _c.execute("select id, rule, severity, title, location, data from findings where run_id=?", (rid,)):
        d = json.loads(r["data"])
        d.update(id=r["id"])
        out.append(d)
    return out
