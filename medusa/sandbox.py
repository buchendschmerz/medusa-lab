"""Constrained execution of simulation code (LLM-generated or recipe scripts).

Defence in depth — none of these layers is a perfect sandbox on its own:

1. **Static screening** (:func:`screen_code`): an AST check with an import
   allow-list and a ban on dynamic/introspective builtins (as calls *and* as
   aliases), dunder access (as names *and* as string literals, so ``__builtins__``
   can't be reached by subscript) and file/OS/ctypes/socket/pickle-style
   attributes. It stops accidental and easy-to-write misuse early with a readable
   error the Coder can fix, but a deny-list can never be complete against the full
   numpy/scipy/networkx surface — treat it as a speed bump, not the boundary.
2. **Process isolation** (:class:`Sandbox`): a fresh working directory, an
   environment with *no* secrets, ``python -I``, resource limits (CPU time,
   memory, file size, open files, no core dumps) and a hard wall-clock timeout.
   The *child's* environment is scrubbed, but in basic mode the child shares the
   parent's uid and could otherwise read the parent's ``/proc/<pid>/environ``
   (which still holds the exec-time secrets even after ``os.environ`` is edited),
   so constructing a :class:`Sandbox` marks this process non-dumpable on Linux —
   that hands ``/proc/<pid>`` to root and denies the same-uid read. This is
   best-effort defence in depth; basic mode is for development, and any run that
   holds real secrets should use strict mode (below) with ``require_isolation``.
3. **strict mode** (recommended on CI): additionally runs the process in a new
   network namespace (no network at all) as the unprivileged ``nobody`` user
   via ``unshare`` + ``setpriv`` (needs root or passwordless ``sudo``). Running
   as another user also keeps the code away from the parent's
   ``/proc/<pid>/environ`` (API keys) and the job's files.
"""

from __future__ import annotations

import ast
import contextlib
import ctypes
import logging
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger("medusa.sandbox")

ALLOWED_IMPORTS = frozenset({
    "math", "cmath", "random", "statistics", "itertools", "functools", "collections", "heapq",
    "bisect", "fractions", "decimal", "dataclasses", "typing", "json", "csv", "array", "copy",
    "operator", "string", "enum", "numbers", "time", "datetime", "re", "textwrap", "abc",
    "medusa_sim", "numpy", "scipy", "networkx",
})
BANNED_CALLS = frozenset({
    "eval", "exec", "compile", "__import__", "open", "input", "breakpoint", "globals", "locals",
    "vars", "getattr", "setattr", "delattr", "memoryview", "exit", "quit", "help",
})
# attribute / imported names that reach the file system, processes, the network,
# serialisation, frame introspection or string-based attribute lookup.
# The screener is defence layer 1: it stops naive and easy-to-write payloads with a
# readable error, but it can never be a complete deny-list against the full numpy/
# scipy/networkx surface — the real containment is the OS isolation of strict mode.
BANNED_ATTRS = frozenset({
    "load", "loads", "loadtxt", "save", "savez", "savez_compressed", "savetxt", "savefig", "fromfile",
    "tofile", "genfromtxt", "fromregex", "memmap", "DataSource", "ctypes", "ctypeslib", "dump", "dumps",
    "system", "popen", "fork", "forkpty", "kill", "killpg", "remove", "unlink", "rmdir", "mkdir", "makedirs",
    "rename", "chmod", "chown", "environ", "environb", "getenv", "getenvb", "putenv", "unsetenv",
    "listdir", "scandir", "walk", "fwalk", "imread", "imsave", "readwrite", "datasets",
    # low-level file/descriptor and process primitives (os.*, ctypes.*)
    "open", "openat", "read", "write", "pread", "pwrite", "fdopen", "fdatasync", "fsync", "dup", "dup2",
    "pipe", "pipe2", "mkfifo", "mknod", "symlink", "link", "readlink", "truncate", "ftruncate", "sendfile",
    "access", "stat", "lstat", "fstat", "statvfs", "getppid", "getpid", "getuid", "geteuid", "setuid",
    "chdir", "chroot", "fchdir", "getcwd", "getcwdb", "execv", "execve", "execvp", "execvpe", "execl",
    "execle", "execlp", "posix_spawn", "posix_spawnp", "startfile", "device_encoding",
    "dlopen", "LoadLibrary", "CDLL", "WinDLL", "OleDLL", "PyDLL", "cast", "string_at", "wstring_at",
    "addressof", "memmove", "memset", "POINTER", "pointer", "create_string_buffer", "mmap",
    # sockets / urllib
    "socket", "socketpair", "create_connection", "connect", "urlopen", "urlretrieve",
    # frame / code / function introspection
    "attrgetter", "methodcaller", "get_type_hints", "ForwardRef", "f_globals", "f_locals",
    "f_builtins", "f_back", "gi_frame", "gi_code", "cr_frame", "ag_frame", "tb_frame", "tb_next", "co_code",
    "func_globals", "__reduce__", "__reduce_ex__",
})
BANNED_ATTR_PREFIXES = ("read_", "write_", "load_", "save_", "open_", "to_pickle", "from_pickle", "spawn",
                        "system")
BANNED_SUBMODULES = frozenset({"io", "ctypeslib", "lib", "testing", "distutils", "f2py", "_core", "datasets",
                               "readwrite", "misc"})
_DUNDER_STR = re.compile(r"^__\w+__$")  # e.g. "__builtins__", "__globals__", "__subclasses__"
SIM_MODULE = "medusa_sim"

# Runs inside the child before the script: resource limits, umask, then the script itself.
BOOTSTRAP = r"""
import os, sys
try:
    import resource
    def _lim(name, value, hard_extra=0):
        try:
            resource.setrlimit(getattr(resource, name), (value, value + hard_extra))
        except (ValueError, OSError, AttributeError):
            pass
    _lim("RLIMIT_CPU", int(os.environ.get("MEDUSA_CPU_SEC", "300")), 2)  # SIGXCPU first, then SIGKILL
    _mem = int(os.environ.get("MEDUSA_MEM_MB", "0"))
    if _mem > 0:
        _lim("RLIMIT_AS", _mem * 1024 * 1024)
    _lim("RLIMIT_FSIZE", 256 * 1024 * 1024)
    _lim("RLIMIT_CORE", 0)
    _lim("RLIMIT_NOFILE", 256)
except ImportError:
    pass
os.umask(0)
sys.path.insert(0, os.getcwd())
sys.argv = sys.argv[1:]
import runpy
runpy.run_path(sys.argv[0], run_name="__main__")
"""


class ScreeningError(ValueError):
    def __init__(self, problems: list[str]) -> None:
        super().__init__("; ".join(problems))
        self.problems = problems


_HARDENED = False


def _harden_process() -> None:
    """Mark this (trusted parent) process non-dumpable so a same-uid sandbox child
    cannot read its ``/proc/<pid>/environ`` (API keys). Linux-only, best-effort, once."""
    global _HARDENED
    if _HARDENED or not sys.platform.startswith("linux"):
        return
    _HARDENED = True
    try:  # PR_SET_DUMPABLE = 4, SUID_DUMP_DISABLE = 0
        libc = ctypes.CDLL("libc.so.6", use_errno=True)
        libc.prctl(4, 0, 0, 0, 0)
    except (OSError, AttributeError, ValueError) as exc:  # pragma: no cover - platform dependent
        log.debug("could not set the process non-dumpable: %s", exc)


def _attr_banned(name: str) -> bool:
    if name.startswith("__") and name.endswith("__"):
        return True
    return name in BANNED_ATTRS or name.lower().startswith(BANNED_ATTR_PREFIXES)


def screen_code(source: str, extra_allowed: frozenset[str] = frozenset()) -> list[str]:
    """Return a list of problems (empty = passed)."""
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return [f"syntax error at line {exc.lineno}: {exc.msg}"]
    allowed = ALLOWED_IMPORTS | extra_allowed
    problems: list[str] = []
    sim_aliases = {SIM_MODULE}

    def where(node: ast.AST) -> str:
        return f"line {getattr(node, 'lineno', '?')}"

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                parts = alias.name.split(".")
                if root not in allowed:
                    problems.append(f"{where(node)}: import of '{alias.name}' is not allowed")
                elif any(p in BANNED_SUBMODULES or _attr_banned(p) for p in parts[1:]):
                    problems.append(f"{where(node)}: submodule '{alias.name}' is not allowed")
                if alias.name == SIM_MODULE:
                    sim_aliases.add(alias.asname or SIM_MODULE)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            root = module.split(".")[0]
            if node.level or root not in allowed:
                problems.append(f"{where(node)}: import from '{module or '.'}' is not allowed")
                continue
            if any(p in BANNED_SUBMODULES or _attr_banned(p) for p in module.split(".")[1:]):
                problems.append(f"{where(node)}: submodule '{module}' is not allowed")
            if module != SIM_MODULE:
                for alias in node.names:
                    if alias.name == "*" or alias.name in BANNED_SUBMODULES or _attr_banned(alias.name):
                        problems.append(f"{where(node)}: importing '{alias.name}' from '{module}' is not allowed")
        elif isinstance(node, ast.Name):
            # catch both calls and aliasing (e.g. ``e = eval``); a call's callee is also a Name node
            if node.id in BANNED_CALLS:
                problems.append(f"{where(node)}: use of '{node.id}' is not allowed")
            elif node.id.startswith("__") and node.id != "__name__":
                problems.append(f"{where(node)}: access to '{node.id}' is not allowed")
        elif isinstance(node, ast.Constant) and isinstance(node.value, str) and _DUNDER_STR.match(node.value):
            # a dunder string reaches builtins/globals/type internals via subscript or getattr
            problems.append(f"{where(node)}: the string {node.value!r} is not allowed")
        elif isinstance(node, ast.Attribute):
            if isinstance(node.value, ast.Name) and node.value.id in sim_aliases:
                if node.attr.startswith("_"):
                    problems.append(f"{where(node)}: private helper '{node.attr}' is not allowed")
                continue
            if _attr_banned(node.attr) or node.attr in BANNED_SUBMODULES:
                problems.append(f"{where(node)}: attribute '.{node.attr}' is not allowed")
    # de-duplicate while keeping order
    seen: set[str] = set()
    return [p for p in problems if not (p in seen or seen.add(p))]  # type: ignore[func-returns-value]


@dataclass
class SandboxResult:
    returncode: int
    stdout: str
    stderr: str
    timed_out: bool
    runtime_sec: float
    isolation: str
    notes: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.returncode == 0 and not self.timed_out

    def tail(self, n: int = 40) -> str:
        text = (self.stdout + ("\n" if self.stdout and self.stderr else "") + self.stderr).strip()
        return "\n".join(text.splitlines()[-n:])


_STRICT_PROBE: dict[str, list[str] | None] = {}


class Sandbox:
    def __init__(self, *, mode: str = "basic", timeout_sec: float = 300, memory_mb: int = 2048,
                 python: str | None = None, require_isolation: bool = False) -> None:
        self.mode = mode
        self.timeout = float(timeout_sec)
        self.memory_mb = int(memory_mb)
        self.python = python or sys.executable
        self.require_isolation = require_isolation
        _harden_process()

    # ------------------------------------------------------------------ strict mode
    def _strict_prefix(self) -> list[str] | None:
        """Command prefix for netns + nobody isolation, or None if unavailable."""
        if self.python in _STRICT_PROBE:
            return _STRICT_PROBE[self.python]
        prefix: list[str] | None = None
        if sys.platform.startswith("linux") and shutil.which("unshare") and shutil.which("setpriv"):
            candidates = [[]] if os.geteuid() == 0 else ([["sudo", "-n"]] if shutil.which("sudo") else [])
            for sudo in candidates:
                trial = [*sudo, "unshare", "--net", "--", "setpriv", "--reuid=65534", "--regid=65534",
                         "--clear-groups", "--no-new-privs", "--"]
                try:
                    probe = subprocess.run([*trial, self.python, "-I", "-c", "import os; print(os.getuid())"],
                                           capture_output=True, text=True, timeout=20)
                except (OSError, subprocess.TimeoutExpired):
                    continue
                if probe.returncode == 0 and probe.stdout.strip() == "65534":
                    prefix = trial
                    break
                log.debug("strict sandbox probe failed: %s", probe.stderr.strip())
        _STRICT_PROBE[self.python] = prefix
        return prefix

    def isolation_level(self) -> str:
        if self.mode == "strict" and self._strict_prefix() is not None:
            return "strict (no network, uid nobody)"
        return "basic (scrubbed env, rlimits)"

    # ------------------------------------------------------------------ run
    def execute(self, files: dict[str, str | bytes], entry: str, dest: Path, *,
                on_line: Callable[[str], None] | None = None,
                collect_suffixes: tuple[str, ...] = (".json", ".dat", ".csv", ".txt")) -> SandboxResult:
        """Run ``entry`` in a throw-away directory holding only ``files``; copy outputs to ``dest``.

        Only regular files (never symlinks) with an allowed suffix and a sane size are copied back,
        so a script cannot smuggle other files of the host into the published outputs.
        """
        tmp = Path(tempfile.mkdtemp(prefix="medusa-sim-"))
        try:
            for name, content in files.items():
                target = tmp / name
                target.parent.mkdir(parents=True, exist_ok=True)
                if isinstance(content, bytes):
                    target.write_bytes(content)
                else:
                    target.write_text(content, encoding="utf-8")
            (tmp / "data").mkdir(exist_ok=True)
            result = self.run(entry, tmp, on_line=on_line)
            dest = Path(dest)
            dest.mkdir(parents=True, exist_ok=True)
            copied = 0
            for path in sorted(tmp.rglob("*")):
                rel = path.relative_to(tmp)
                if rel.as_posix() in files or path.is_symlink() or not path.is_file():
                    continue
                if path.suffix not in collect_suffixes or path.stat().st_size > 20 * 1024 * 1024:
                    result.notes.append(f"skipped output {rel.as_posix()}")
                    continue
                if copied >= 200:
                    result.notes.append("too many output files; the rest were skipped")
                    break
                out = dest / rel
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_bytes(path.read_bytes())
                copied += 1
            return result
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def run(self, script: str, workdir: Path, *, extra_env: dict[str, str] | None = None,
            on_line: Callable[[str], None] | None = None) -> SandboxResult:
        """Run ``script`` (a file inside ``workdir``); ``on_line`` receives stdout lines live.

        In strict mode ``workdir`` must be reachable by the ``nobody`` user (see :meth:`execute`).
        """
        workdir = Path(workdir).resolve()
        env = {
            "PATH": "/usr/local/bin:/usr/bin:/bin",
            "HOME": str(workdir),
            "TMPDIR": str(workdir),
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
            "PYTHONHASHSEED": "0",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONIOENCODING": "utf-8",
            "MPLBACKEND": "Agg",
            "OMP_NUM_THREADS": "2",
            "OPENBLAS_NUM_THREADS": "1",
            "MKL_NUM_THREADS": "2",
            "MEDUSA_CPU_SEC": str(int(self.timeout) + 5),
            "MEDUSA_MEM_MB": str(self.memory_mb),
            **(extra_env or {}),
        }
        base_cmd = [self.python, "-I", "-B", "-c", BOOTSTRAP, script]
        notes: list[str] = []
        prefix: list[str] | None = None
        if self.mode == "strict":
            prefix = self._strict_prefix()
            if prefix is None:
                if self.require_isolation:
                    raise RuntimeError("strict sandbox requested but unshare/setpriv isolation is unavailable")
                notes.append("strict isolation unavailable; fell back to basic sandbox")
                log.warning("strict sandbox unavailable — falling back to basic isolation")
        if prefix is not None:
            os.chmod(workdir, 0o777)
            for path in workdir.rglob("*"):
                os.chmod(path, 0o777 if path.is_dir() else 0o666)
            env_args = ["env", "-i", *[f"{k}={v}" for k, v in env.items()]]
            timeout_args = ["timeout", "-k", "5", str(int(self.timeout))] if shutil.which("timeout") else []
            if prefix[:2] == ["sudo", "-n"]:
                cmd = [*prefix[:2], *env_args, *timeout_args, *prefix[2:], *base_cmd]
            else:
                cmd = [*env_args, *timeout_args, *prefix, *base_cmd]
            isolation = "strict"
            popen_env = None
        else:
            cmd = base_cmd
            isolation = "basic"
            popen_env = env

        start = time.monotonic()
        proc = subprocess.Popen(cmd, cwd=workdir, env=popen_env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                stdin=subprocess.DEVNULL, text=True, errors="replace", start_new_session=True)
        out_lines: deque[str] = deque(maxlen=4000)
        err_lines: deque[str] = deque(maxlen=4000)

        def pump(stream, sink: deque[str], callback: Callable[[str], None] | None) -> None:  # type: ignore[no-untyped-def]
            for line in stream:
                sink.append(line)
                if callback is not None:
                    try:
                        callback(line.rstrip("\n"))
                    except Exception:  # a UI callback must never kill the run
                        log.exception("sandbox line callback failed")

        readers = [threading.Thread(target=pump, args=(proc.stdout, out_lines, on_line), daemon=True),
                   threading.Thread(target=pump, args=(proc.stderr, err_lines, None), daemon=True)]
        for t in readers:
            t.start()
        timed_out = False
        grace = 15 if isolation == "strict" else 2  # strict mode is enforced by coreutils `timeout` first
        try:
            proc.wait(timeout=self.timeout + grace)
        except subprocess.TimeoutExpired:
            timed_out = True
            _terminate(proc)
            proc.wait()
        for t in readers:
            t.join(timeout=5)
        runtime = time.monotonic() - start
        rc = proc.returncode
        if isolation == "strict" and rc == 124:  # coreutils `timeout` exit code
            timed_out = True
        if rc is not None and rc < 0 and -rc in (signal.SIGXCPU, signal.SIGKILL) \
                and runtime >= self.timeout:
            timed_out = True
        return SandboxResult(returncode=rc if rc is not None else -1, stdout="".join(out_lines),
                             stderr="".join(err_lines), timed_out=timed_out, runtime_sec=round(runtime, 3),
                             isolation=isolation, notes=notes)


def _terminate(proc: subprocess.Popen[str]) -> None:
    with contextlib.suppress(ProcessLookupError, PermissionError):
        os.killpg(proc.pid, signal.SIGTERM)
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            proc.kill()
