#!/usr/bin/env python3
import os
import signal
import subprocess
import shlex
from datetime import datetime

from flask import Flask, jsonify, request, send_from_directory
from dotenv import load_dotenv
import psutil

load_dotenv()

# Configuration
API_TOKEN = os.getenv("ROY_PROCWATCH_TOKEN", "change-me-please")
BIND_HOST = os.getenv("ROY_PROCWATCH_HOST", "127.0.0.1")
BIND_PORT = int(os.getenv("ROY_PROCWATCH_PORT", "8088"))

app = Flask(__name__, static_url_path="", static_folder="static")

def require_token(func):
    from functools import wraps
    @wraps(func)
    def wrapper(*args, **kwargs):
        token = request.headers.get("X-Auth-Token")
        if token != API_TOKEN:
            return jsonify({"error": "Unauthorized"}), 401
        return func(*args, **kwargs)
    return wrapper

def proc_to_dict(p: psutil.Process, ports_map):
    try:
        with p.oneshot():
            pid = p.pid
            name = p.name()
            exe = ""
            try:
                exe = p.exe()
            except Exception:
                pass
            username = p.username()
            status = p.status()
            create_time = p.create_time()
            cpu = p.cpu_percent(interval=None)
            mem = p.memory_info().rss
            nice = p.nice()
            cmdline = p.cmdline()
            parent = p.ppid()
            open_files = []
            try:
                open_files = [f.path for f in p.open_files()]
            except Exception:
                pass

            ports = ports_map.get(pid, [])
            return {
                "pid": pid,
                "ppid": parent,
                "name": name,
                "exe": exe,
                "username": username,
                "status": status,
                "create_time": create_time,
                "create_time_iso": datetime.fromtimestamp(create_time).isoformat(),
                "cpu_percent": cpu,
                "memory_rss": mem,
                "nice": nice,
                "cmdline": cmdline,
                "ports": ports,
                "open_files_count": len(open_files),
            }
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
        return None

def build_ports_map():
    ports_map = {}
    for c in psutil.net_connections(kind='inet'):
        try:
            pid = c.pid
        except Exception:
            pid = None
        if not pid:
            continue
        local = f"{c.laddr.ip}:{c.laddr.port}" if c.laddr else None
        remote = f"{c.raddr.ip}:{c.raddr.port}" if c.raddr else None
        state = c.status
        entry = {"local": local, "remote": remote, "status": state, "family": str(c.family)}
        ports_map.setdefault(pid, []).append(entry)
    return ports_map

@app.route("/")
def root():
    return send_from_directory("static", "index.html")

@app.get("/api/health")
def health():
    return jsonify({"status": "ok", "time": datetime.utcnow().isoformat()})

@app.get("/api/processes")
@require_token
def list_processes():
    q = request.args.get("q", "").lower().strip()
    sort = request.args.get("sort", "cpu")  # cpu|mem|pid|name
    order = request.args.get("order", "desc")  # asc|desc

    ports_map = build_ports_map()
    procs = []
    for p in psutil.process_iter(attrs=[], ad_value=None):
        item = proc_to_dict(p, ports_map)
        if not item:
            continue
        if q:
            hay = " ".join([
                str(item.get("pid","")),
                item.get("name","") or "",
                " ".join(item.get("cmdline",[]) or []),
                item.get("username","") or "",
            ]).lower()
            if q not in hay:
                continue
        procs.append(item)

    def keyfunc(x):
        if sort == "cpu":
            return x["cpu_percent"]
        if sort == "mem":
            return x["memory_rss"]
        if sort == "name":
            return (x["name"] or "").lower()
        if sort == "pid":
            return x["pid"]
        return x["cpu_percent"]

    reverse = (order != "asc")
    procs.sort(key=keyfunc, reverse=reverse)
    return jsonify({"count": len(procs), "items": procs})

@app.post("/api/process/<int:pid>/signal")
@require_token
def send_signal(pid):
    data = request.get_json(silent=True) or {}
    sig_name = (data.get("signal") or "TERM").upper()
    sig_map = {
        "TERM": signal.SIGTERM,
        "KILL": signal.SIGKILL,
        "INT":  signal.SIGINT,
        "HUP":  signal.SIGHUP,
        "STOP": signal.SIGSTOP,
        "CONT": signal.SIGCONT,
    }
    if sig_name not in sig_map:
        return jsonify({"error": f"Unsupported signal {sig_name}"}), 400

    try:
        p = psutil.Process(pid)
        p.send_signal(sig_map[sig_name])
        return jsonify({"ok": True, "pid": pid, "signal": sig_name})
    except psutil.NoSuchProcess:
        return jsonify({"error": "Process not found"}), 404
    except psutil.AccessDenied:
        return jsonify({"error": "Access denied. Try running the server with sudo for root-owned processes."}), 403
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.post("/api/process/<int:pid>/renice")
@require_token
def renice(pid):
    data = request.get_json(silent=True) or {}
    value = int(data.get("nice", 0))
    try:
        p = psutil.Process(pid)
        p.nice(value)
        return jsonify({"ok": True, "pid": pid, "nice": value})
    except psutil.NoSuchProcess:
        return jsonify({"error": "Process not found"}), 404
    except psutil.AccessDenied:
        return jsonify({"error": "Access denied."}), 403
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.post("/api/process/<int:pid>/restart")
@require_token
def restart(pid):
    """
    Redémarrage best-effort:
    - lit cmdline/exe du process courant (si accessible)
    - envoie SIGTERM
    - relance via subprocess.Popen(cmdline) ou exe
    NOTE: ne fonctionne que pour des processus appartenant au même utilisateur
    et dont le binaire/cmdline est lisible.
    """
    try:
        p = psutil.Process(pid)
        cmdline = p.cmdline()
        exe = None
        try:
            exe = p.exe()
        except Exception:
            pass

        if not cmdline and not exe:
            return jsonify({"error": "Unable to determine command line to restart."}), 400

        # Stop
        try:
            p.terminate()
            p.wait(timeout=5)
        except Exception:
            pass

        # Relaunch
        new_proc = None
        try:
            if cmdline:
                new_proc = subprocess.Popen(cmdline)
            elif exe:
                new_proc = subprocess.Popen([exe])
        except FileNotFoundError:
            return jsonify({"error": "Executable not found."}), 400

        return jsonify({"ok": True, "old_pid": pid, "new_pid": new_proc.pid if new_proc else None})
    except psutil.NoSuchProcess:
        return jsonify({"error": "Process not found"}), 404
    except psutil.AccessDenied:
        return jsonify({"error": "Access denied."}), 403
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    print(f"[Roy ProcWatch] Running on http://{BIND_HOST}:{BIND_PORT}  (token: {API_TOKEN})")
    app.run(host=BIND_HOST, port=BIND_PORT, debug=False)
