"""inputs.py — understand whatever the user gives us as "the design".

Accepted:
  https://github.com/owner/repo                        whole repository, default branch
  https://github.com/owner/repo/tree/<ref>/<path>      a branch / tag / commit, optionally a sub-folder
  https://github.com/owner/repo/blob/<ref>/<file>      one file (its folder is reviewed, the file is the focus)
  https://github.com/owner/repo/commit/<sha>           one commit
  https://github.com/owner/repo/pull/<n>               a pull request's head
  owner/repo                                           GitHub shorthand
  any https git URL (GitLab, Codeberg, self-hosted)    default branch
  a .zip upload of a project folder                    (handled by unpack_zip)
"""
import os, re, shutil, zipfile
from dataclasses import dataclass

GH = re.compile(r"^(?:https?://)?(?:www\.)?github\.com/([\w.-]+)/([\w.-]+?)(?:\.git)?(?:/(tree|blob|commit|pull)/(.+?))?/?$")
SHORT = re.compile(r"^([\w.-]+)/([\w.-]+)$")
GIT_URL = re.compile(r"^https://[\w.-]+(?::\d+)?/[\w./~-]+?(?:\.git)?/?$")
MAX_ZIP_MB, MAX_FILES = 300, 20000


@dataclass
class Source:
    kind: str            # github | git | zip
    url: str = ""        # clone URL
    ref: str = ""        # branch / tag / sha / refs/pull/N/head ('' = default branch)
    path: str = ""       # sub-folder to review ('' = whole repo)
    focus: str = ""      # a file the user pointed at
    label: str = ""      # what to show the user

    def describe(self):
        bits = [self.label or self.url]
        if self.ref:
            bits.append(f"@ {self.ref}")
        if self.path:
            bits.append(f"/{self.path}")
        return " ".join(bits)


def parse(text):
    """Source for a pasted string, or raise ValueError with a message the user can act on."""
    s = (text or "").strip()
    if not s:
        raise ValueError("Paste a repository link, owner/repo, or drop a .zip of the project.")
    m = GH.match(s)
    if m:
        owner, repo, kind, rest = m.groups()
        url, label = f"https://github.com/{owner}/{repo}", f"{owner}/{repo}"
        if not kind:
            return Source("github", url, label=label)
        if kind == "pull":
            n = rest.split("/")[0]
            if not n.isdigit():
                raise ValueError("That pull-request link has no number.")
            return Source("github", url, ref=f"refs/pull/{n}/head", label=f"{label} #{n}")
        if kind == "commit":
            return Source("github", url, ref=rest.split("/")[0], label=label)
        ref, _, path = rest.partition("/")
        if kind == "blob":
            return Source("github", url, ref=ref, path=os.path.dirname(path), focus=path, label=label)
        return Source("github", url, ref=ref, path=path, label=label)
    if SHORT.match(s) and "." not in s.split("/")[0][:1]:
        o, r = SHORT.match(s).groups()
        return Source("github", f"https://github.com/{o}/{r}", label=f"{o}/{r}")
    if GIT_URL.match(s):
        return Source("git", s.rstrip("/"), label=re.sub(r"^https://", "", s.rstrip("/")).removesuffix(".git"))
    raise ValueError("That doesn't look like a repository. Try https://github.com/owner/repo, owner/repo, "
                     "a GitLab/any https git link, or drop a .zip.")


def unpack_zip(path, dest):
    """Safely extract an uploaded project zip: no absolute paths, no '..', no symlinks, size and count capped."""
    with zipfile.ZipFile(path) as z:
        infos = z.infolist()
        if len(infos) > MAX_FILES:
            raise ValueError(f"The zip has {len(infos)} files; the limit is {MAX_FILES}.")
        if sum(i.file_size for i in infos) > MAX_ZIP_MB * 1e6:
            raise ValueError(f"The zip expands beyond {MAX_ZIP_MB} MB.")
        root = os.path.realpath(dest)
        for i in infos:
            name = i.filename
            if name.startswith("/") or ".." in name.split("/"):
                continue
            if (i.external_attr >> 16) & 0o170000 == 0o120000:      # symlink
                continue
            target = os.path.realpath(os.path.join(dest, name))
            if not target.startswith(root + os.sep) and target != root:
                continue
            if i.is_dir():
                os.makedirs(target, exist_ok=True)
                continue
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with z.open(i) as src, open(target, "wb") as out:
                shutil.copyfileobj(src, out)
    # a zip of one top folder: review inside it
    kids = [k for k in os.listdir(dest) if not k.startswith(("__MACOSX", "."))]
    return os.path.join(dest, kids[0]) if len(kids) == 1 and os.path.isdir(os.path.join(dest, kids[0])) else dest
