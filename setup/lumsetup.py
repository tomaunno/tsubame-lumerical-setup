# /// script
# requires-python = ">=3.11"
# ///
"""Lumerical-on-TSUBAME setup steps, driven by Claude Code following SETUP.md.

Needs tsubame-claude-setup to have been run first: the ssh alias, group and work
folder are read from the `tsubame` Claude skill it wrote. Every subcommand does one
step and ends with exactly one line `RESULT {json}` for the caller to parse.

    uv run --managed-python --python 3.12 setup/lumsetup.py <subcommand>

    check
    upload --file INSTALLER.tar.gz     then:  upload --wait
    install --server PORT@HOST [--dest DIR]   (or --watch)
    verify [--gpu]                     (or --watch)
    skill
    cleanup

Values found or chosen in one step are kept in setup/state.json for the next ones.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
from pathlib import Path

SETUP_DIR = "lumerical-setup"         # under the work folder on TSUBAME; removed by `cleanup`
DEFAULT_DEST = "apps/lumerical"       # under the work folder on TSUBAME; kept
DEFAULT_PORT = "1055"                 # the usual Ansys license (lmgrd) port
REMOTE_FILES = ("install_job.sh", "verify_job.sh", "make_cell.lsf", "read_t.py")
EXPECTED_T = 0.9941                   # make_cell.lsf solved with 2026 R1.4 (threads, MPI and GPU agree)
T_TOLERANCE = 0.01
INSTALL_RES, INSTALL_RT = "cpu_8=1", "1:00:00"
VERIFY_RES = {"cpu": "cpu_8=1", "gpu": "gpu_1=1"}
VERIFY_RT = "0:30:00"

REPO = Path(__file__).resolve().parent.parent
START = time.time()                   # waits count from here, so a step returns within its --minutes
HOME = Path.home()
IS_WIN = os.name == "nt"
NOISE = ("post-quantum", "store now", "upgraded", "openssh.com/pq", "conda", "your_shell", "please do")


# ---- small helpers ----------------------------------------------------------------
def result(status: str, **data) -> None:
    print("RESULT " + json.dumps({"status": status, **data}, ensure_ascii=True))


def run(argv: list[str], timeout: int | None = 120, **kw) -> subprocess.CompletedProcess:
    return subprocess.run(argv, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=timeout, **kw)


def clean(text: str) -> str:
    """Drop the banner lines every TSUBAME login prints."""
    return "\n".join(l for l in text.splitlines() if l.strip() and not any(n in l.lower() for n in NOISE))


def q(s: str) -> str:
    return shlex.quote(s)


class State:
    def __init__(self, path: Path):
        self.path = path
        self.data: dict = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}

    def __getitem__(self, k):
        return self.data[k]

    def get(self, k, default=None):
        return self.data.get(k, default)

    def set(self, **kw) -> None:
        self.data.update({k: v for k, v in kw.items() if v is not None})
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def skill_roots(st: State) -> list[Path]:
    """Folders an AI agent loads skills from: Claude Code, then Codex (ChatGPT).
    The `tsubame` skill of tsubame-claude-setup is looked for in each, and the new
    skill is written next to every one found, so it reaches the same agent(s)."""
    if st.get("skills_dir"):            # testing: one folder only
        return [Path(st["skills_dir"])]
    claude = Path(st.get("claude_dir") or os.environ.get("CLAUDE_CONFIG_DIR") or HOME / ".claude")
    return [claude / "skills", HOME / ".agents" / "skills"]


def undo_msys(path: str) -> str:
    """Git Bash turns '/gs/fs/x' into 'C:/.../Git/gs/fs/x' before Python sees it; undo that."""
    if not IS_WIN or "MSYSTEM" not in os.environ or not shutil.which("cygpath"):
        return path
    root = run([shutil.which("cygpath"), "-m", "/"]).stdout.strip().rstrip("/")
    norm = path.replace("\\", "/")
    return norm[len(root):] if root and norm.lower().startswith(root.lower() + "/") else path


def pid_alive(pid: int) -> bool:
    if IS_WIN:
        r = run(["tasklist", "/FI", f"PID eq {pid}", "/NH", "/FO", "CSV"])
        return f'"{pid}"' in r.stdout
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


# ---- what tsubame-claude-setup left ---------------------------------------------------
ROW_KEYS = {"ssh の接続名": "alias", "ログイン名": "user", "作業の置き場所": "workdir", "hpcjob": "hpcjob"}


def base_skills(st: State) -> list[Path]:
    """Every `tsubame` skill written by tsubame-claude-setup (one per agent)."""
    found = []
    for root in skill_roots(st):
        skill = root / "tsubame" / "SKILL.md"
        if skill.exists() and "tsubame-claude-setup" in skill.read_text(encoding="utf-8", errors="replace"):
            found.append(skill)
    return found


def base_values(st: State) -> dict:
    """Read the connection table of the first `tsubame` skill found."""
    skills = base_skills(st)
    if not skills:
        return {}
    text = skills[0].read_text(encoding="utf-8", errors="replace")
    out: dict = {}
    for line in text.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 2:
            continue
        vals = re.findall(r"`([^`]+)`", cells[1])
        if not vals:
            continue
        if cells[0] in ROW_KEYS:
            out[ROW_KEYS[cells[0]]] = vals[0]
        elif cells[0].startswith("グループ"):
            out["group"] = vals[0]
        elif cells[0] == "ssh / scp" and len(vals) >= 2:
            out["ssh"], out["scp"] = vals[0], vals[1]
    need = ("alias", "user", "group", "workdir", "ssh", "scp")
    return out if all(out.get(k) for k in need) else {}


def need_base(st: State) -> dict | None:
    base = base_values(st)
    if not base:
        result("no_base_setup", looked_in=[str(r / "tsubame" / "SKILL.md") for r in skill_roots(st)],
               hint="run tsubame-claude-setup first (https://github.com/tomaunno/tsubame-claude-setup)")
        return None
    st.set(**base)
    return base


def shared_dest(st: State, disk: str = "fs") -> str:
    return f"/gs/{disk}/{st['group']}/{DEFAULT_DEST}"


def wdir(st: State) -> str:
    return f'{st["workdir"].rstrip("/")}/{SETUP_DIR}'


def rsh(st: State, cmd: str, timeout: int = 120, stdin: str | None = None) -> subprocess.CompletedProcess:
    argv = [st["ssh"], "-o", "BatchMode=yes", "-o", "ConnectTimeout=20", st["alias"], cmd]
    if stdin is None:
        return run(argv, timeout=timeout)
    # Bytes, not text: a text pipe on Windows turns every \n into \r\n, and a job script
    # whose first line ends in \r cannot start ("execvp ... No such file or directory").
    r = subprocess.run(argv, capture_output=True, input=stdin.encode("utf-8"), timeout=timeout)
    return subprocess.CompletedProcess(argv, r.returncode, r.stdout.decode("utf-8", "replace"),
                                       r.stderr.decode("utf-8", "replace"))


def ssh_failed(r: subprocess.CompletedProcess) -> bool:
    return r.returncode == 255      # ssh itself failed (network, key); the remote command did not run


def ssh_error(r: subprocess.CompletedProcess) -> None:
    result("error", reason="ssh_failed", detail=clean(r.stderr)[-600:],
           hint="the `tsubame` skill (reference.md, 'Permission denied') says how to get back in")


# ---- check ---------------------------------------------------------------------------
def installer_candidates() -> list[dict]:
    pat = re.compile(r"lumerical.*\.tar\.gz$", re.I)
    seen, found = set(), []
    for d in (HOME / "Downloads", HOME / "Desktop", HOME / "OneDrive" / "Desktop", HOME):
        if not d.is_dir():
            continue
        try:                    # macOS asks before a program may list ~/Downloads or ~/Desktop
            for p in d.iterdir():
                if p.is_file() and pat.search(p.name) and p.resolve() not in seen:
                    seen.add(p.resolve())
                    found.append({"path": str(p), "size_gb": round(p.stat().st_size / 1e9, 2),
                                  "modified": f"{dt.datetime.fromtimestamp(p.stat().st_mtime):%Y-%m-%d}"})
        except OSError:
            continue
    return found


def license_hints() -> list[str]:
    """Where a Lumerical on this PC (if any) gets its license from."""
    hints = []
    env = os.environ.get("ANSYSLMD_LICENSE_FILE")
    if env:
        hints.append(f"ANSYSLMD_LICENSE_FILE={env}")
    inis = [Path("/Applications/ANSYS Inc/Shared Files/Licensing/ansyslmd.ini")]
    if IS_WIN:
        inis.insert(0, Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
                    / "ANSYS Inc" / "Shared Files" / "Licensing" / "ansyslmd.ini")
    if os.environ.get("APPDATA"):     # a stand-alone Lumerical: [license] ansysserver\host=1055@...
        inis.append(Path(os.environ["APPDATA"]) / "Lumerical" / "License.ini")
    for ini in inis:
        try:
            for line in ini.read_text(encoding="utf-8", errors="replace").splitlines():
                key = line.strip().lower()
                if key.startswith("server=") or key.startswith("ansysserver\\host="):
                    hints.append(f"{ini}: {line.strip()}")
        except OSError:
            pass
    return hints


def cmd_check(st: State, ns) -> None:
    base = need_base(st)
    if not base:
        return
    dest = st.get("dest") or f'{st["workdir"].rstrip("/")}/{DEFAULT_DEST}'
    probe = (f"echo LSOK; d={q(dest)}; r=$(ls -d \"$d\"/opt/lumerical/v* 2>/dev/null | sort -V | tail -1); "
             f"echo \"ROOT $r\"; [ -f \"$d/lumenv.sh\" ] && echo LUMENV; "
             f"[ -e \"$d\" ] && [ -n \"$(ls -A \"$d\" 2>/dev/null)\" ] && echo DEST_NOT_EMPTY; "
             f"ls {q(wdir(st))}/*.tar.gz 2>/dev/null | sed 's/^/UPLOADED /'; "
             f"t4-user-info disk group -g {q(st['group'])} 2>/dev/null | sed 's/^/DISK /'; "
             f"for b in fs bs; do [ -w /gs/$b/{q(st['group'])} ] && echo \"GROUP_WRITABLE $b\"; done; "
             # installs made by this setup anywhere on the group's disks (a lab shares one)
             f"timeout 60 find /gs/fs/{q(st['group'])} /gs/bs/{q(st['group'])} -maxdepth 5 -name lumenv.sh 2>/dev/null"
             " | while read -r f; do grep -q tsubame-lumerical-setup \"$f\" 2>/dev/null"
             " && echo \"SHARED $f $(stat -c %U \"$f\") $(sed -n 's/^# Written by tsubame-lumerical-setup on [0-9-]*\\. Lumerical \\(.*\\)\\.$/\\1/p' \"$f\")\"; done")
    r = rsh(st, probe)
    if "LSOK" not in r.stdout:
        return ssh_error(r)
    out = r.stdout.splitlines()
    root = next((l[5:].strip() for l in out if l.startswith("ROOT ")), "")
    info = {
        "alias": st["alias"], "user": st["user"], "group": st["group"], "workdir": st["workdir"],
        "dest": dest, "installed_root": root or None,
        "lumenv_written": "LUMENV" in out,
        "dest_not_empty_without_install": ("DEST_NOT_EMPTY" in out) and not root,
        "uploaded": [l[9:] for l in out if l.startswith("UPLOADED ")],
        "group_installs": [dict(zip(("lumenv", "owner", "version"), l[7:].split(" ", 2)))
                           for l in out if l.startswith("SHARED ")],
        # where a first install for the whole lab can go (the group folder is writable for members)
        "group_shared_dest": next((shared_dest(st, l.split()[1]) for l in out if l.startswith("GROUP_WRITABLE ")), None),
        "installers_on_this_pc": installer_candidates(),
        "license_hints": license_hints(),
        "group_disk": [l[5:] for l in out if l.startswith("DISK ")][:6],
        "agents_with_tsubame_skill": [str(s.parent.parent) for s in base_skills(st)],
        "skill_installed": all((s.parent.parent / "tsubame-lumerical" / "SKILL.md").exists() for s in base_skills(st)),
    }
    for k, v in info.items():
        print(f"{k}: {v}")
    result("ok", **info)


# ---- upload --------------------------------------------------------------------------
def sha256_local(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 22), b""):
            h.update(block)
    return h.hexdigest()


def remote_size(st: State, path: str) -> int:
    r = rsh(st, f"stat -c %s {q(path)} 2>/dev/null || echo 0")
    nums = re.findall(r"^\d+$", r.stdout, re.M)
    return int(nums[-1]) if nums else 0


def cmd_upload(st: State, ns) -> None:
    if not need_base(st):
        return
    if ns.wait or (st.get("upload_pid") and pid_alive(st["upload_pid"])):
        return upload_wait(st, ns.minutes)
    if not ns.file:
        raise SystemExit("upload: pass --file INSTALLER.tar.gz (or --wait)")
    f = Path(undo_msys(ns.file)).expanduser()
    if not f.is_file():
        return result("error", reason="file_not_found", file=str(f))
    if not f.name.lower().endswith(".tar.gz"):
        return result("error", reason="not_tar_gz", file=str(f),
                      hint="the Linux installer is a .tar.gz file (e.g. LUMERICAL_2026R1.04_LINX64.tar.gz)")
    size = f.stat().st_size
    remote = f"{wdir(st)}/{f.name}"
    r = rsh(st, f"mkdir -p {q(wdir(st))} && echo MK_OK")
    if "MK_OK" not in r.stdout:
        return ssh_error(r) if ssh_failed(r) else result("error", reason="workdir_unusable",
                                                         detail=clean(r.stderr)[-400:])
    st.set(local_installer=str(f), local_size=size, tarball=remote)
    if remote_size(st, remote) == size:
        print(f"already on TSUBAME: {remote}")
        return result("ok", tarball=remote, already=True)
    log = REPO / "setup" / "upload.log"
    argv = [st["scp"], "-q", "-o", "BatchMode=yes", "-o", "ConnectTimeout=20", str(f), f'{st["alias"]}:{remote}.part']
    if ns.foreground:   # for agents that stop background processes when a command ends
        print(f"copying {f} ({size / 1e9:.2f} GB) to {st['alias']}:{remote} ...", flush=True)
        r = run(argv, timeout=None)
        log.write_text(r.stdout + r.stderr, encoding="utf-8")
        st.set(upload_pid=0)
        return upload_wait(st, 0)
    with log.open("w", encoding="utf-8") as lf:
        if IS_WIN:      # detached: the copy keeps going after this command returns
            p = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=lf, stderr=subprocess.STDOUT,
                                 creationflags=0x00000008 | 0x00000200)   # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
        else:
            p = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=lf, stderr=subprocess.STDOUT,
                                 start_new_session=True)
    st.set(upload_pid=p.pid, upload_started=time.time())
    print(f"copying {f} ({size / 1e9:.2f} GB) to {st['alias']}:{remote}")
    result("uploading", pid=p.pid, size_gb=round(size / 1e9, 2), hint="run `upload --wait`")


def upload_wait(st: State, minutes: float) -> None:
    remote, size, pid = st.get("tarball"), st.get("local_size"), st.get("upload_pid")
    if not remote or not size:
        return result("error", reason="run `upload --file ...` first")
    if remote_size(st, remote) == size:
        return result("ok", tarball=remote, already=True)
    part = remote + ".part"
    deadline = START + minutes * 60
    while True:
        alive = bool(pid) and pid_alive(pid)
        got = remote_size(st, part)
        if not alive:
            break
        if time.time() > deadline:
            return result("still_uploading", percent=round(100 * got / size, 1), hint="run `upload --wait` again")
        print(f"{dt.datetime.now():%H:%M:%S} {100 * got / size:.1f} %", flush=True)
        time.sleep(max(1, min(30, deadline - time.time())))
    if got != size:
        log = REPO / "setup" / "upload.log"
        detail = clean(log.read_text(encoding="utf-8", errors="replace"))[-600:] if log.exists() else ""
        return result("error", reason="upload_failed", got_bytes=got, want_bytes=size, detail=detail,
                      hint="run `upload --file ...` again (it starts over)")
    print("comparing checksums ...", flush=True)
    local = sha256_local(Path(st["local_installer"]))
    r = rsh(st, f"sha256sum {q(part)}", timeout=600)
    if local not in r.stdout:
        return result("error", reason="checksum_mismatch", hint="run `upload --file ...` again")
    r = rsh(st, f"mv -f {q(part)} {q(remote)} && echo MV_OK")
    if "MV_OK" not in r.stdout:
        return result("error", reason="rename_failed", detail=clean(r.stderr)[-400:])
    st.set(upload_pid=0)
    result("ok", tarball=remote, sha256=local)


# ---- jobs ------------------------------------------------------------------------------
def push_remote_files(st: State) -> bool:
    """Copy the job scripts to the setup folder on TSUBAME (with LF line ends)."""
    for name in REMOTE_FILES:
        text = (REPO / "setup" / "remote" / name).read_text(encoding="utf-8").replace("\r\n", "\n")
        r = rsh(st, f"mkdir -p {q(wdir(st))} && cat > {q(wdir(st) + '/' + name)} && echo PUT_OK", stdin=text)
        if "PUT_OK" not in r.stdout:
            ssh_error(r)
            return False
    return True


def qsub(st: State, folder: str, resource: str, walltime: str, name: str, args: list[str]) -> str | None:
    cmd = (f"cd {q(folder)} && qsub -g {q(st['group'])} -S /bin/bash -l {resource} -l h_rt={walltime} "
           f"-N {name} {' '.join(q(a) for a in args)}")
    r = rsh(st, cmd)
    m = re.search(r"Your job (\d+)", r.stdout)
    if not m:
        result("error", reason="submit_failed", detail=clean(r.stdout + "\n" + r.stderr)[-800:],
               hint="a 'group' or 'point' message means the group or its points; see the `tsubame` skill")
        return None
    print(f"submitted {name}: job {m.group(1)}")
    return m.group(1)


def wait_jobs(st: State, jobids: list[str], minutes: float) -> bool | None:
    """True when none of the jobs is queued or running any more, False on timeout.
    None after printing a RESULT: ssh failed, or a job went into an error state."""
    deadline = START + minutes * 60
    while True:
        r = rsh(st, "qstat 2>/dev/null; echo QSTAT_DONE")
        if "QSTAT_DONE" not in r.stdout:
            ssh_error(r)
            return None
        left = [j for j in jobids if re.search(rf"^\s*{j}\s", r.stdout, re.M)]
        if not left:
            return True
        state = {j: (re.search(rf"^\s*{j}\s+\S+\s+\S+\s+\S+\s+(\S+)", r.stdout, re.M) or [None, "?"])[1] for j in left}
        broken = [j for j, s in state.items() if s.startswith("E")]
        if broken:              # Eqw never starts by itself: report why and remove it
            why = rsh(st, f"qstat -j {broken[0]} 2>&1 | grep -A1 'error reason' | head -3; qdel {' '.join(broken)}")
            result("error", reason="job_error_state", jobs=broken, detail=clean(why.stdout)[-600:])
            return None
        if time.time() > deadline:
            return False
        print(f"{dt.datetime.now():%H:%M:%S} waiting: {state}", flush=True)
        if deadline - time.time() < 60:
            return False
        time.sleep(60)          # TSUBAME asks not to poll qstat more often than this


def queued(st: State, jobids: list[str]) -> list[str]:
    """The jobs among these that qstat still lists (an ssh failure counts as none)."""
    r = rsh(st, "qstat 2>/dev/null")
    return [j for j in jobids if re.search(rf"^\s*{j}\s", r.stdout, re.M)]


def job_lines(st: State, folder: str, name: str, jobid: str) -> list[str] | None:
    r = rsh(st, f"cat {q(f'{folder}/{name}.o{jobid}')} 2>/dev/null; echo CAT_DONE")
    if "CAT_DONE" not in r.stdout:
        ssh_error(r)
        return None
    return r.stdout.splitlines()


# ---- install ---------------------------------------------------------------------------
def normalize_server(s: str) -> str | None:
    s = s.strip().replace(" ", "")
    if not s:
        return None
    if "," in s:                    # a redundant server triad (port@a,port@b,port@c): keep as given
        parts, sep = s.split(","), ","
    else:                           # a list to try in turn: ':' on Linux, ';' on Windows
        parts, sep = re.split(r"[:;]", s), ":"
    if not all(re.fullmatch(r"(\d+@)?[A-Za-z0-9._-]+", p) for p in parts):
        return None
    return sep.join(p if "@" in p else f"{DEFAULT_PORT}@{p}" for p in parts)


def parse_install(lines: list[str]) -> dict:
    kv: dict = {}
    out: dict = {"errors": [], "license_errors": [], "features": [], "aliases": [], "license_detail": [],
                 "lmdiag": {}}
    for line in lines:
        if not line.startswith("LS "):
            continue
        body = line[3:].strip()
        head, _, rest = body.partition(" ")
        if head == "ERROR":
            out["errors"].append(rest)
        elif head == "LICERR":
            out["license_errors"].append(rest)
        elif head == "LICDETAIL":
            out["license_detail"].append(rest)
        elif head == "FEATURE":
            f = rest.split()
            out["features"].append({"name": f[0], "total": f[1], "in_use": f[2]})
        elif head == "ALIAS":
            out["aliases"].append(rest)
        elif head == "LMDIAG":
            f = rest.split()
            out["lmdiag"][f[0]] = f[1]
        elif head.startswith("HOST="):
            kv.update(t.split("=", 1) for t in body.split() if "=" in t)
        elif "=" in head:
            k, _, v = body.partition("=")
            kv[k] = v
        elif head == "DONE":
            kv["DONE"] = rest
    out["kv"] = kv
    return out


def cmd_install(st: State, ns) -> None:
    if not need_base(st):
        return
    if ns.watch:
        jobid = st.get("install_jobid")
        if not jobid:
            return result("error", reason="nothing to watch; run `install --server ...` first")
        return install_watch(st, jobid, ns.minutes)
    if st.get("install_jobid") and queued(st, [st["install_jobid"]]):
        print("the install job is still queued or running; waiting for it")
        return install_watch(st, st["install_jobid"], ns.minutes)
    if not ns.server:
        raise SystemExit("install: pass --server PORT@HOST (or --watch)")
    server = normalize_server(ns.server)
    if not server:
        return result("error", reason="bad_server", server=ns.server, hint="the form is 1055@hostname or 1055@1.2.3.4")
    dest = undo_msys(ns.dest).rstrip("/") if ns.dest else st.get("dest") or f'{st["workdir"].rstrip("/")}/{DEFAULT_DEST}'
    if not dest.startswith("/"):
        return result("error", reason="dest_not_absolute", dest=dest)
    tarball = st.get("tarball") or "none"
    if not push_remote_files(st):
        return
    if dest in (shared_dest(st, "fs"), shared_dest(st, "bs")):   # the lab's shared apps folder: members may add versions next to it
        parent = dest.rsplit("/", 1)[0]
        rsh(st, f"[ -d {q(parent)} ] || {{ mkdir -p {q(parent)} && chmod 2775 {q(parent)}; }}")
    jobid = qsub(st, wdir(st), INSTALL_RES, INSTALL_RT, "lumsetup_install", ["install_job.sh", tarball, dest, server])
    if not jobid:
        return
    st.set(install_jobid=jobid, server=server, dest=dest)
    install_watch(st, jobid, ns.minutes)


def install_watch(st: State, jobid: str, minutes: float) -> None:
    done = wait_jobs(st, [jobid], minutes)
    if done is None:
        return
    if not done:
        return result("still_running", jobid=jobid, hint="run `install --watch` again")
    lines = job_lines(st, wdir(st), "lumsetup_install", jobid)
    if lines is None:
        return
    p = parse_install(lines)
    kv = p["kv"]
    common = {"jobid": jobid, "root": kv.get("ROOT"), "version": kv.get("VERSION"), "size": kv.get("SIZE"),
              "glut": kv.get("GLUT"), "missing_libs": kv.get("MISSING_LIBS"), "python": kv.get("PYTHON")}
    for k, v in common.items():
        print(f"{k}: {v}")
    if p["errors"]:
        reason = p["errors"][0].split()[0]
        return result("error", reason=reason, detail=p["errors"], **common)
    if "DONE" not in kv:
        tail = [l for l in lines if l.strip()][-12:]
        return result("error", reason="job_incomplete", detail=tail, **common,
                      hint="the job ended early (time limit or a crash); the log tail is in detail")
    lic = {"licfile": kv.get("LICFILE"), "server_host": kv.get("HOST"), "server_ip": kv.get("IP"),
           "server_dns_name": kv.get("DNSNAME"), "server_self_name": kv.get("SELFNAME"), "tcp": kv.get("TCP"),
           "aliases": p["aliases"], "lmstat": kv.get("LMSTAT"), "lmdiag": p["lmdiag"], "features": p["features"]}
    for k, v in lic.items():
        print(f"{k}: {v}")
    st.set(root=kv.get("ROOT"), version=kv.get("VERSION"))
    if p["license_errors"]:         # the server cannot be reached or named from TSUBAME
        # The job left any earlier lumenv.sh as it was, so the state keeps pointing at it too.
        return result("license_failed", reason=p["license_errors"][0].split()[0], license_errors=p["license_errors"],
                      **common, **lic)
    st.set(lumenv=kv.get("LUMENV"), licfile=kv.get("LICFILE"), features=p["features"], aliases=p["aliases"],
           lmstat_works=kv.get("LMSTAT") == "up")
    lum = [f for f in p["features"] if f["name"].startswith("lum_")]
    if kv.get("LMSTAT") == "up" and not lum:
        return result("license_failed", reason="no_lumerical_features", **common, **lic,
                      hint="the server answers but holds no lum_* licenses: probably not the Lumerical server")
    # lmstat cannot see a server whose own name TSUBAME cannot resolve (see install_job.sh);
    # `verify` then makes the real checkout and decides.
    check = "lmstat" if lum else "lmdiag" if "ok" in p["lmdiag"].values() else "unconfirmed"
    st.set(installed=True)
    result("ok", license_check=check, lumenv=kv.get("LUMENV"), **common, **lic)


# ---- use -------------------------------------------------------------------------------
def cmd_use(st: State, ns) -> None:
    """Take an install someone in the group already made with this setup, instead of
    uploading and unpacking another copy (a lab needs only one)."""
    if not need_base(st):
        return
    f = undo_msys(ns.lumenv)
    probe = (f"f={q(f)}; [ -r \"$f\" ] && grep -q tsubame-lumerical-setup \"$f\" && echo MARK; "
             "grep -E '^export (LUM_ROOT|ANSYSLMD_LICENSE_FILE)=' \"$f\" | sed 's/^export //'; "
             "sed -n 's/^# license counts readable from TSUBAME (lmstat): //p' \"$f\" | sed 's/^/LMSTAT=/'; "
             "sed -n 's/^# Written by tsubame-lumerical-setup on [0-9-]*\\. Lumerical \\(.*\\)\\.$/\\1/p' \"$f\" | sed 's/^/VERSION=/'; "
             "echo \"OWNER=$(stat -c %U \"$f\")\"; "
             "r=$(sed -n 's/^export LUM_ROOT=//p' \"$f\"); [ -x \"$r/bin/fdtd-engine\" ] && echo ENGINE_OK")
    r = rsh(st, probe)
    if ssh_failed(r):
        return ssh_error(r)
    kv = dict(l.split("=", 1) for l in r.stdout.splitlines() if "=" in l and not l.startswith(" "))
    if "MARK" not in r.stdout.splitlines() or "ENGINE_OK" not in r.stdout.splitlines():
        return result("error", reason="not_usable", lumenv=f,
                      hint="pass a lumenv.sh written by tsubame-lumerical-setup that this account can read")
    root = kv["LUM_ROOT"]
    st.set(lumenv=f, root=root, dest=f.rsplit("/", 1)[0], licfile=kv.get("ANSYSLMD_LICENSE_FILE"),
           version=f'{kv.get("VERSION", "")} ({root.rsplit("/", 1)[-1]})'.strip(), owner=kv.get("OWNER"),
           lmstat_works=kv.get("LMSTAT") == "up", features=[], installed=True)
    info = {"lumenv": f, "root": root, "licfile": st.get("licfile"), "version": st.get("version"),
            "owner": kv.get("OWNER"), "shared": kv.get("OWNER") != st["user"]}
    for k, v in info.items():
        print(f"{k}: {v}")
    result("ok", **info)


# ---- verify ----------------------------------------------------------------------------
def cmd_verify(st: State, ns) -> None:
    if not need_base(st):
        return
    if not st.get("installed") or not st.get("lumenv"):
        return result("error", reason="run `install` first (it has to end with ok)")
    if ns.watch:
        jobs = st.get("verify_jobs") or {}
        if not jobs:
            return result("error", reason="nothing to watch; run `verify` first")
    elif st.get("verify_jobs") and queued(st, list(st["verify_jobs"].values())):
        print("the verify jobs are still queued or running; waiting for them")
        jobs = st["verify_jobs"]
    else:
        if not push_remote_files(st):
            return
        jobs = {}
        for mode in ("cpu", "gpu") if ns.gpu else ("cpu",):
            folder = f"{wdir(st)}/verify_{mode}"
            r = rsh(st, f"mkdir -p {q(folder)} && cd {q(folder)} && rm -f *.fsp *.log *.out lumsetup_verify_* "
                        f"&& cp ../make_cell.lsf ../read_t.py ../verify_job.sh . && echo CP_OK")
            if "CP_OK" not in r.stdout:
                return ssh_error(r) if ssh_failed(r) else result(
                    "error", reason="workdir_unusable", detail=clean(r.stdout + r.stderr)[-400:])
            jobid = qsub(st, folder, VERIFY_RES[mode], VERIFY_RT, f"lumsetup_verify_{mode}",
                         ["verify_job.sh", st["lumenv"], mode])
            if not jobid:
                return
            jobs[mode] = jobid
        st.set(verify_jobs=jobs)
    done = wait_jobs(st, list(jobs.values()), ns.minutes)
    if done is None:
        return
    if not done:
        return result("still_running", jobs=jobs, hint="run `verify --watch` again")
    report, all_ok = {}, True
    for mode, jobid in jobs.items():
        lines = job_lines(st, f"{wdir(st)}/verify_{mode}", f"lumsetup_verify_{mode}", jobid)
        if lines is None:
            return
        ls = [l[3:].strip() for l in lines if l.startswith("LS ")]
        r = {"jobid": jobid, "cad": None, "solves": {}, "lumapi": None, "T": {}, "detail": []}
        for body in ls:
            head, _, rest = body.partition(" ")
            if body.startswith("CAD="):
                r["cad"] = body[4:]
            elif body.startswith("LUMAPI="):
                r["lumapi"] = body[7:]
            elif head == "SOLVE":
                f = rest.split()
                r["solves"][f[0]] = {"ok": f[1] == "ok", "info": " ".join(f[2:])}
            elif head == "T":
                f = rest.split(maxsplit=1)
                try:
                    r["T"][f[0]] = float(f[1])
                except (IndexError, ValueError):
                    r["T"][f[0]] = f[1] if len(f) > 1 else None
            elif head == "DETAIL":
                r["detail"].append(rest)
            elif head == "GPU":
                r["gpu"] = rest
        good_t = [v for v in r["T"].values() if isinstance(v, float) and abs(v - EXPECTED_T) <= T_TOLERANCE]
        r["ok"] = (r["cad"] == "ok" and bool(r["solves"]) and all(s["ok"] for s in r["solves"].values())
                   and len(good_t) == len(r["solves"]))
        if not ls:
            r["detail"] = [l for l in lines if l.strip()][-10:]
        all_ok &= r["ok"]
        report[mode] = r
        print(f"{mode}: {r}")
    st.set(verified={m: r["ok"] for m, r in report.items()})
    result("ok" if all_ok else "failed", expected_T=EXPECTED_T, report=report)


# ---- skill -------------------------------------------------------------------------------
def render(template: str, values: dict[str, str]) -> str:
    out = template
    for k, v in values.items():
        out = out.replace("{{" + k + "}}", v)
    left = re.findall(r"\{\{[A-Z_]+\}\}", out)
    if left:
        raise SystemExit(f"template placeholders left unfilled: {sorted(set(left))}")
    return out


def feature_text(features: list[dict]) -> str:
    lum = [f for f in features if f["name"].startswith("lum_")]
    if not lum:
        return "記録していない(下の「残りの見方」)"
    return "、".join(f'`{f["name"]}` {f["total"]} 本' for f in lum)


def license_count_text(st: State) -> str:
    if st.get("lmstat_works"):
        return ("ログインノードで数秒で終わる。\n"
                f"  `hpcjob run -- {st['root']}/licensingclient/linx64/lmutil lmstat -c {st['licfile']} -f lum_fdtd_solve`。\n"
                "  「Total of N licenses issued; Total of M licenses in use」が全体と使用中の本数。下に使っている人の名前も出るが、"
                "本人に伝えるのは本数だけにする。")
    return ("このライセンスサーバは、TSUBAME からは本数を数えられない。サーバが TSUBAME で通じない名前で名乗っていて、"
            "数える道具 `lmstat` はその名前の読み替え(`HOSTALIASES`)を使わないため(Lumerical の計算そのものは読み替えで借りられる)。\n"
            "  本数は研究室の Windows の PC で見る: `C:\\Program Files\\Lumerical\\v<版>\\licensingclient\\winx64\\lmutil.exe "
            f"lmstat -c {st['licfile']} -f lum_fdtd_solve`(研究室の PC ではサーバの名前が通じる)。")


def cmd_skill(st: State, ns) -> None:
    if not need_base(st):
        return
    if not st.get("installed"):
        return result("error", reason="run `install` first (it has to end with ok)")
    owner = st.get("owner") or st["user"]
    verified = st.get("verified") or {}
    said ={"cpu": "CPU(スレッドと Open MPI)", "gpu": "GPU(gpu_1 の H100)"}
    vtext = "、".join(said[m] + ("" if ok else "は失敗") for m, ok in verified.items()) or "まだ確かめていない"
    values = {
        "DATE": f"{dt.date.today()}", "USER": st["user"], "GROUP": st["group"], "ALIAS": st["alias"],
        "LUMENV": st["lumenv"], "LUM_ROOT": st["root"], "DEST": st["dest"], "LICFILE": st["licfile"],
        "VERSION": st.get("version") or Path(st["root"]).name, "FEATURES": feature_text(st.get("features", [])),
        "VERIFIED": vtext, "LICENSE_COUNT": license_count_text(st),
        "OWNER": "この人" if owner == st["user"] else f"`{owner}`(グループの共有。この人は使うだけ)",
        "REMOVE_NOTE": (f"`{st['dest']}` のフォルダと、このスキルのフォルダを消せば元どおり。グループのほかの人が"
                        "このフォルダの Lumerical を使っていないかを先に確かめる。" if owner == st["user"] else
                        f"このスキルのフォルダだけを消す。Lumerical 本体(`{st['dest']}`)は `{owner}` が入れた"
                        "グループの共有のものなので、消さない。"),
    }
    written = []
    for root in (s.parent.parent for s in base_skills(st)):     # next to each `tsubame` skill
        dest = root / "tsubame-lumerical"
        if dest.exists():
            skill = dest / "SKILL.md"
            ours = skill.exists() and "tsubame-lumerical-setup" in skill.read_text(encoding="utf-8", errors="replace")
            if ours:
                shutil.rmtree(dest)
            else:   # someone else's skill of the same name: keep it, outside skills/ so it stops loading
                backup = root.parent / f"tsubame-lumerical-skill-backup-{dt.datetime.now():%Y%m%d%H%M%S}"
                shutil.move(str(dest), str(backup))
                print(f"an existing 'tsubame-lumerical' skill was moved to {backup}")
        dest.mkdir(parents=True)
        for name in ("SKILL.md", "lum_job.sh"):
            text = (REPO / "skill" / name).read_text(encoding="utf-8")
            (dest / name).write_text(render(text, values), encoding="utf-8", newline="\n")
        print(f"skill written: {dest}")
        written.append(str(dest))
    result("ok", skills=written)


# ---- cleanup -----------------------------------------------------------------------------
def cmd_cleanup(st: State, ns) -> None:
    """Remove the setup folder on TSUBAME (job scripts, test models, logs, the uploaded
    installer). The install itself stays. This folder is deleted by the caller."""
    if not need_base(st):
        return
    d = wdir(st)
    test = (f"d={q(d)}; if [ -f \"$d/install_job.sh\" ]; then rm -rf \"$d\" && echo GONE; "
            f"elif [ -e \"$d\" ]; then echo FOREIGN; else echo ABSENT; fi")
    r = rsh(st, test, timeout=300)
    removed, kept = [], []
    if "GONE" in r.stdout:
        removed.append(f"tsubame:{d}")
    elif "FOREIGN" in r.stdout:
        kept.append(f"tsubame:{d} (not created by this setup)")
    elif "ABSENT" not in r.stdout:
        kept.append(f"tsubame:{d} (could not reach TSUBAME: {clean(r.stderr)[-200:]})")
    for line in removed:
        print(f"removed: {line}")
    for line in kept:
        print(f"kept: {line}")
    result("ok", removed=removed, kept=kept, install=st.get("dest"), setup_folder=str(REPO),
           local_installer=st.get("local_installer"))


# ---- main --------------------------------------------------------------------------------
def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(errors="replace")
    p = argparse.ArgumentParser(prog="lumsetup", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--state", default=str(REPO / "setup" / "state.json"), help="where found values are kept")
    p.add_argument("--claude-dir", help="Claude Code config dir (default: $CLAUDE_CONFIG_DIR or ~/.claude)")
    p.add_argument("--skills-dir", help="testing: look for the `tsubame` skill and write the new one only here")
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("check", help="read the TSUBAME connection, look for an install, an installer and license hints")
    u = sub.add_parser("upload", help="copy the Linux installer to TSUBAME in the background")
    u.add_argument("--file")
    u.add_argument("--wait", action="store_true", help="wait for the copy, then compare checksums")
    u.add_argument("--foreground", action="store_true", help="copy without a background process (returns when done)")
    u.add_argument("--minutes", type=float, default=7)
    i = sub.add_parser("install", help="unpack on a compute node and check the license server (one cpu_8 job)")
    i.add_argument("--server", help="license server, PORT@HOST (port 1055 when left out)")
    i.add_argument("--dest", help=f"install folder on TSUBAME (default: <work folder>/{DEFAULT_DEST})")
    i.add_argument("--watch", action="store_true", help="keep waiting for the install job")
    i.add_argument("--minutes", type=float, default=7)
    us = sub.add_parser("use", help="use an install made by this setup elsewhere in the group (no upload, no unpack)")
    us.add_argument("--lumenv", required=True, help="its lumenv.sh on TSUBAME")
    v = sub.add_parser("verify", help="build and solve a tiny model (cpu_8; with --gpu also gpu_1)")
    v.add_argument("--gpu", action="store_true")
    v.add_argument("--watch", action="store_true", help="keep waiting for the verify jobs")
    v.add_argument("--minutes", type=float, default=7)
    sub.add_parser("skill", help="write the Claude skill tsubame-lumerical")
    sub.add_parser("cleanup", help="remove the setup folder on TSUBAME (the install stays)")
    ns = p.parse_args()

    st = State(Path(ns.state))
    st.set(claude_dir=ns.claude_dir, skills_dir=ns.skills_dir)
    try:
        {"check": cmd_check, "upload": cmd_upload, "install": cmd_install, "use": cmd_use, "verify": cmd_verify,
         "skill": cmd_skill, "cleanup": cmd_cleanup}[ns.command](st, ns)
    except subprocess.TimeoutExpired as exc:     # the caller always gets a RESULT line to read
        result("error", reason="timeout", detail=f"{' '.join(map(str, exc.cmd))[:300]} took over {exc.timeout} s")
    except Exception as exc:
        result("error", reason="crash", detail=f"{type(exc).__name__}: {exc}"[-800:])
        raise
    return 0


if __name__ == "__main__":
    sys.exit(main())
