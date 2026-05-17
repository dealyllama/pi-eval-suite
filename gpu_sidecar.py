#!/usr/bin/env python3
"""
Lightweight GPU metrics sidecar — run this on the Ollama host (WSL2).
Exposes nvidia-smi data over HTTP so remote benchmark harnesses can poll it.

Usage:
    python3 gpu_sidecar.py                  # default port 8765, all interfaces
    python3 gpu_sidecar.py --port 9000
    python3 gpu_sidecar.py --host 0.0.0.0 --port 8765

Endpoints:
    GET /gpu      — current GPU snapshot (JSON)
    GET /health   — liveness check

No external dependencies — pure Python stdlib only.

--- WSL2 setup notes ---
1. Run in background:
       nohup python3 gpu_sidecar.py &> gpu_sidecar.log &

2. Auto-start on WSL2 login — add to ~/.bashrc or ~/.profile:
       (pgrep -f gpu_sidecar.py || nohup python3 ~/gpu_sidecar.py &> ~/gpu_sidecar.log &)

3. Windows Firewall — allow inbound on chosen port from your LAN:
   In an admin PowerShell:
       netsh advfirewall firewall add rule name="GPU Sidecar" dir=in action=allow protocol=TCP localport=8765

4. WSL2 host IP changes on reboot. To get it from your tablet:
       ssh user@windows-host "wsl hostname -I"
   Or set a static IP via .wslconfig — see Microsoft docs.
"""

import argparse
import json
import subprocess
from http.server import BaseHTTPRequestHandler, HTTPServer
from datetime import datetime


def query_nvidia_smi():
    """Returns a dict of GPU metrics or {'error': reason} on failure."""
    try:
        out = subprocess.check_output(
            [
                "nvidia-smi",
                "--query-gpu=index,name,utilization.gpu,utilization.memory,"
                "memory.used,memory.total,temperature.gpu,power.draw",
                "--format=csv,noheader,nounits",
            ],
            timeout=5,
        ).decode().strip()

        gpus = []
        for line in out.splitlines():
            parts = [p.strip() for p in line.split(",")]
            if len(parts) < 8:
                continue
            index, name, gpu_util, mem_util, mem_used, mem_total, temp, power = parts
            gpus.append({
                "index":        int(index),
                "name":         name,
                "gpu_util_pct": int(gpu_util),
                "mem_util_pct": int(mem_util),
                "mem_used_mb":  int(mem_used),
                "mem_total_mb": int(mem_total),
                "temp_c":       int(temp),
                # power.draw may be "N/A" for some GPUs
                "power_w":      float(power) if power not in ("N/A", "[N/A]") else None,
            })
        return {"gpus": gpus, "timestamp": datetime.utcnow().isoformat() + "Z"}

    except FileNotFoundError:
        return {"error": "nvidia-smi not found"}
    except subprocess.TimeoutExpired:
        return {"error": "nvidia-smi timed out"}
    except Exception as e:
        return {"error": str(e)}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/gpu":
            payload = query_nvidia_smi()
            self._respond(200, payload)
        elif self.path == "/health":
            self._respond(200, {"status": "ok"})
        else:
            self._respond(404, {"error": "not found"})

    def _respond(self, code, data):
        body = json.dumps(data).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        # Suppress per-request access log noise; keep error output
        pass


def main():
    parser = argparse.ArgumentParser(description="GPU metrics HTTP sidecar")
    parser.add_argument("--host", default="0.0.0.0", help="Bind address (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8765, help="Port (default: 8765)")
    args = parser.parse_args()

    # Sanity-check nvidia-smi at startup
    result = query_nvidia_smi()
    if "error" in result:
        print(f"[warn] nvidia-smi check failed: {result['error']}")
        print("[warn] Server will start but /gpu will return errors until nvidia-smi is available.")
    else:
        for gpu in result["gpus"]:
            print(f"[ok]   GPU {gpu['index']}: {gpu['name']}  "
                  f"{gpu['mem_total_mb']}MB VRAM")

    server = HTTPServer((args.host, args.port), Handler)
    print(f"[gpu_sidecar] Listening on {args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[gpu_sidecar] Stopped.")


if __name__ == "__main__":
    main()
