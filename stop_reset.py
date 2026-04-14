"""Stop pipeline, do full project reset, then verify API is clean."""
import urllib.request, json, sys, time
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

API = "http://localhost:8000/api/v1"
KEY = "1298184555b8ccefd070eef9b4b8bac5"

def api(path, method="GET"):
    req = urllib.request.Request(f"{API}{path}", method=method)
    req.add_header("X-API-Key", KEY)
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return r.status, json.loads(r.read())
    except Exception as e:
        return 0, str(e)

# 1. Stop pipeline first
print("1. Stopping pipeline...")
s, r = api("/stop", "POST")
print(f"   -> {s}: {r}")

# 2. Wait for it to stop
time.sleep(5)

# 3. Full project reset 
print("2. Full project reset...")
s, r = api("/project", "DELETE")
print(f"   -> {s}: {r}")

# 4. Verify clean state
time.sleep(2)
print("3. Verifying clean state...")
s, r = api("/status")
if s == 200:
    p = r.get("pipeline", {})
    print(f"   running={p.get('is_running')} iter={p.get('current_iteration')}")
else:
    print(f"   ERROR: {s}")

print("\nBackend needs restart. Use: python start.py")
