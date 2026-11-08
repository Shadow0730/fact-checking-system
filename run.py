"""Start the whole project with one command: backend API + frontend UI.

    python run.py                 # installs what's missing, then starts both
    python run.py --offline       # force OFFLINE_MODE (no Sarvam key, no 2.3 GB model)
    python run.py --skip-install  # don't check/install dependencies
    python run.py --no-browser    # don't open the browser

Ctrl+C stops both. Needs Python 3.12+ and Node 20+. No database or Docker is needed:
without DATABASE_URL the corpus is loaded into memory and checks are saved under data/checks/.
"""
import argparse
import hashlib
import os
import shutil
import signal
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"
VENV = BACKEND / ".venv"
WIN = os.name == "nt"
VENV_PY = VENV / ("Scripts/python.exe" if WIN else "bin/python")
NPM = shutil.which("npm.cmd" if WIN else "npm") or "npm"


def say(msg: str) -> None:
    print(f"\033[1;36m[run]\033[0m {msg}", flush=True)


def fail(msg: str) -> None:
    print(f"\033[1;31m[run] {msg}\033[0m", flush=True)
    sys.exit(1)


def read_env(path: Path) -> dict[str, str]:
    env = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def check_tools() -> None:
    if sys.version_info < (3, 12):  # noqa: UP036  (run.py runs on whatever python the user has)
        fail(f"Python 3.12+ is required (this is {sys.version.split()[0]}).")
    if not shutil.which("node"):
        fail("Node.js 20+ is required: https://nodejs.org")


def ensure_env_files() -> None:
    if not (ROOT / ".env").exists():
        shutil.copy(ROOT / ".env.example", ROOT / ".env")
        say("Created .env from .env.example. Put your SARVAM_API_KEY in it for real results.")
    local = FRONTEND / ".env.local"
    if not local.exists():
        shutil.copy(FRONTEND / ".env.local.example", local)


def install_backend(with_model: bool) -> None:
    if not VENV_PY.exists():
        say("Creating backend/.venv ...")
        subprocess.run([sys.executable, "-m", "venv", str(VENV)], check=True)
    import tomllib  # imported here so old Pythons reach the friendly version check first

    py = tomllib.loads((BACKEND / "pyproject.toml").read_text(encoding="utf-8"))
    deps = list(py["project"]["dependencies"]) + list(py.get("dependency-groups", {}).get("dev", []))
    if not with_model:  # the hashing embedder needs no torch / sentence-transformers
        deps = [d for d in deps if not d.startswith("sentence-transformers")]
    stamp = VENV / ".deps-stamp"
    digest = hashlib.sha256("\n".join(sorted(deps)).encode()).hexdigest()
    if stamp.exists() and stamp.read_text() == digest:
        return
    say(f"Installing backend packages ({'with' if with_model else 'without'} sentence-transformers) ...")
    subprocess.run([str(VENV_PY), "-m", "pip", "install", "--disable-pip-version-check", "-q", *deps], check=True)
    stamp.write_text(digest)


def install_frontend() -> None:
    stamp = FRONTEND / "node_modules" / ".deps-stamp"
    digest = hashlib.sha256((FRONTEND / "package.json").read_bytes()).hexdigest()
    if stamp.exists() and stamp.read_text() == digest:
        return
    say("Installing frontend packages (npm install) ...")
    subprocess.run([NPM, "install", "--no-fund", "--no-audit"], cwd=FRONTEND, check=True)
    stamp.write_text(digest)


def pump(proc: subprocess.Popen, tag: str, colour: str) -> None:
    for line in iter(proc.stdout.readline, ""):
        print(f"\033[{colour}m[{tag}]\033[0m {line.rstrip()}", flush=True)


def start(cmd: list[str], cwd: Path, env: dict, tag: str, colour: str) -> subprocess.Popen:
    flags = subprocess.CREATE_NEW_PROCESS_GROUP if WIN else 0
    proc = subprocess.Popen(cmd, cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                            encoding="utf-8", errors="replace", bufsize=1, creationflags=flags,
                            start_new_session=not WIN)
    threading.Thread(target=pump, args=(proc, tag, colour), daemon=True).start()
    return proc


def stop(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    if WIN:  # kill the whole tree (npm -> node -> next)
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True)
    else:
        os.killpg(proc.pid, signal.SIGTERM)


def wait_for(url: str, procs: list[subprocess.Popen], timeout: float) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        if any(p.poll() is not None for p in procs):
            return False
        try:
            with urllib.request.urlopen(url, timeout=2):
                return True
        except Exception:
            time.sleep(1)
    return False


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--offline", action="store_true", help="run without a Sarvam key (results not meaningful)")
    ap.add_argument("--skip-install", action="store_true", help="don't check or install dependencies")
    ap.add_argument("--no-browser", action="store_true", help="don't open the browser")
    args = ap.parse_args()

    if WIN:
        os.system("")  # enable ANSI colours in the Windows console
    for stream in (sys.stdout, sys.stderr):  # Next.js prints "▲" etc.; never crash on the console's codepage
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass
    check_tools()
    ensure_env_files()
    dotenv = read_env(ROOT / ".env")

    env = dict(os.environ)
    offline = args.offline or dotenv.get("OFFLINE_MODE", "").lower() == "true"
    if not offline and not dotenv.get("SARVAM_API_KEY"):
        say("SARVAM_API_KEY is empty in .env, so starting in OFFLINE mode (heuristics, results not meaningful).")
        offline = True
    if offline:
        env["OFFLINE_MODE"] = "true"
        if dotenv.get("EMBEDDING_MODEL", "BAAI/bge-m3") != "hash" and "EMBEDDING_MODEL" not in os.environ:
            env["EMBEDDING_MODEL"] = "hash"   # skip the 2.3 GB model too
    model = env.get("EMBEDDING_MODEL") or dotenv.get("EMBEDDING_MODEL", "BAAI/bge-m3")

    if not args.skip_install:
        install_backend(with_model=model != "hash")
        install_frontend()
    elif not VENV_PY.exists() or not (FRONTEND / "node_modules").exists():
        fail("Dependencies are missing; run without --skip-install once.")

    api_port = dotenv.get("API_PORT", "8000")
    env["PYTHONUNBUFFERED"] = "1"
    say(f"Starting backend on http://localhost:{api_port}  (embeddings: {model}"
        f"{', first start downloads ~2.3 GB' if model != 'hash' else ''})")
    api = start([str(VENV_PY), "-m", "uvicorn", "app.main:app", "--port", api_port, "--host", "127.0.0.1"],
                BACKEND, env, "api", "1;35")
    say("Starting frontend on http://localhost:3000")
    web = start([NPM, "run", "dev"], FRONTEND, env, "web", "1;32")
    procs = [api, web]

    try:
        if wait_for(f"http://127.0.0.1:{api_port}/health", procs, timeout=900) and \
                wait_for("http://localhost:3000", procs, timeout=180):
            say(f"Ready:  UI http://localhost:3000   API docs http://localhost:{api_port}/docs   (Ctrl+C to stop)")
            if not args.no_browser:
                webbrowser.open("http://localhost:3000")
        while all(p.poll() is None for p in procs):
            time.sleep(0.5)
        say("A process exited; stopping the other one.")
    except KeyboardInterrupt:
        say("Stopping ...")
    finally:
        for p in procs:
            stop(p)
    sys.exit(next((p.returncode for p in procs if p.returncode), 0))


if __name__ == "__main__":
    main()
