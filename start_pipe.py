"""Start pipeline and wait for first iteration to start."""
import urllib.request, json, sys, time
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

API = "http://localhost:8000/api/v1"
KEY = "1298184555b8ccefd070eef9b4b8bac5"

def api(path, method="GET"):
    req = urllib.request.Request(f"{API}{path}", method=method)
    req.add_header("X-API-Key", KEY)
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())

# Start pipeline
print("Starting pipeline (5 iterations)...")
r = api("/start?max_iterations=5", method="POST")
print(f"  Response: {r}")

# Wait for it to kick off
for i in range(10):
    time.sleep(3)
    s = api("/status")
    p = s.get("pipeline", {})
    running = p.get("is_running")
    it = p.get("current_iteration")
    agent = p.get("current_agent", "")
    print(f"  [{(i+1)*3}s] running={running} iter={it} agent={agent}")
    if running and it and it >= 1:
        print("  Pipeline is running!")
        break
