"""Docker-mode experiment: starts the autoscaler and the Locust spike together, then analyses.

Prerequisite: `docker compose up -d --build` is running (see README).
  python experiments/run_docker.py --name docker-reactive --mode reactive
  python experiments/run_docker.py --name docker-prewarm  --mode prewarm --prewarm 30:10:130
  python experiments/run_docker.py --name docker-static   --mode static --initial 12
"""
import argparse
import os
import subprocess
import sys
import time

import redis

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = sys.executable


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", default="docker")
    ap.add_argument("--mode", default="reactive", choices=["static", "reactive", "prewarm"])
    ap.add_argument("--initial", type=int, default=4)
    ap.add_argument("--prewarm", default="")
    ap.add_argument("--host", default="http://localhost:8080")
    ap.add_argument("--redis", default="redis://localhost:6379/0")
    ap.add_argument("--warm", type=int, default=40)
    ap.add_argument("--ramp", type=int, default=20)
    ap.add_argument("--hold", type=int, default=40)
    ap.add_argument("--down", type=int, default=20)
    ap.add_argument("--tail", type=int, default=60)
    a = ap.parse_args()
    total = a.warm + a.ramp + a.hold + a.down + a.tail
    out = os.path.join(ROOT, "results", a.name)
    os.makedirs(out, exist_ok=True)

    r = redis.from_url(a.redis, decode_responses=True)
    r.ping()
    r.delete("orders", "orders:done", "orders:lat")   # keep stock:* keys (created once at app start)

    cmd = [PY, os.path.join(ROOT, "autoscaler", "autoscaler.py"), "--backend", "docker", "--mode", a.mode,
           "--initial", str(a.initial), "--redis", a.redis, "--timeline", os.path.join(out, "timeline.csv"),
           "--duration", str(total + 25)]
    if a.prewarm:
        cmd += ["--prewarm", a.prewarm]
    auto = subprocess.Popen(cmd, cwd=ROOT)
    print(f"[{a.name}] letting the initial fleet settle ...", flush=True)
    time.sleep(20)   # docker scale-up + container boot before traffic starts

    env = {**os.environ, "T_WARM": str(a.warm), "T_RAMP": str(a.ramp), "T_HOLD": str(a.hold),
           "T_DOWN": str(a.down), "T_TAIL": str(a.tail)}
    print(f"[{a.name}] load test running ({total}s) ...", flush=True)
    subprocess.run([PY, "-m", "locust", "-f", os.path.join("loadtest", "locustfile.py"), "--headless",
                    "--host", a.host, "--csv", os.path.join(out, "locust"), "--csv-full-history",
                    "--only-summary"], cwd=ROOT, env=env)
    time.sleep(3)
    done = int(r.get("orders:done") or 0)
    with open(os.path.join(out, "orders.txt"), "w") as f:
        f.write(f"done={done}\nleft={r.llen('orders')}\n")
    auto.wait()
    subprocess.run([PY, os.path.join("experiments", "analyze.py"), "--run", a.name, "--peak-start",
                    str(a.warm + a.ramp), "--peak-end", str(a.warm + a.ramp + a.hold)], cwd=ROOT, check=True)


if __name__ == "__main__":
    main()
