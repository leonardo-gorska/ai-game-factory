"""Start pipeline and monitor progress via direct DB reads."""
import urllib.request, json, sys, time, sqlite3
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

API = "http://localhost:8000/api/v1"
KEY = "1298184555b8ccefd070eef9b4b8bac5"
DB = "backend/storage/factory.db"

def api(path, method="GET"):
    req = urllib.request.Request(f"{API}{path}", method=method)
    req.add_header("X-API-Key", KEY)
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return r.status, json.loads(r.read())
    except Exception as e:
        return 0, str(e)

def db_status():
    """Read iteration status directly from DB (bypass API timeouts)."""
    try:
        conn = sqlite3.connect(DB)
        conn.row_factory = sqlite3.Row
        # Check if error column exists
        cols = [c[1] for c in conn.execute("PRAGMA table_info(iterations)").fetchall()]
        has_error = "error" in cols
        
        if has_error:
            rows = conn.execute("SELECT iteration_number, status, score, error FROM iterations ORDER BY iteration_number").fetchall()
        else:
            rows = conn.execute("SELECT iteration_number, status, score FROM iterations ORDER BY iteration_number").fetchall()
        conn.close()
        return rows, has_error
    except:
        return [], False

# 1. Start pipeline
print("=== STARTING PIPELINE (5 iterations) ===")
s, r = api("/start?max_iterations=5", method="POST")
print(f"  Response: {s} -> {r}")

# 2. Monitor via DB (avoids API timeout during heavy processing)
print("\n=== MONITORING (DB direct reads) ===")
start_time = time.time()
max_wait = 900  # 15 minutes max
last_count = 0

while time.time() - start_time < max_wait:
    time.sleep(15)
    elapsed = int(time.time() - start_time)
    
    rows, has_error = db_status()
    if not rows:
        print(f"  [{elapsed:4d}s] No iterations yet...")
        continue
    
    # Print new iterations
    if len(rows) > last_count:
        for r in rows[last_count:]:
            err = str(r['error'])[:80] if has_error and r['error'] else ""
            print(f"  [{elapsed:4d}s] #{r['iteration_number']}: status={r['status']} score={r['score']} {err}")
        last_count = len(rows)
    else:
        # Show last iteration status
        last = rows[-1]
        err = str(last['error'])[:80] if has_error and last['error'] else ""
        print(f"  [{elapsed:4d}s] #{last['iteration_number']}: status={last['status']} score={last['score']} {err}")
    
    # Check if pipeline is done (5 iterations completed/failed)
    completed = sum(1 for r in rows if r['status'] in ('completed', 'failed'))
    if completed >= 5:
        print(f"\n  All 5 iterations done!")
        break

# 3. Final summary
print("\n=== FINAL SUMMARY ===")
rows, has_error = db_status()
print(f"  Error column exists: {has_error}")
completed = 0
failed = 0
scores = []
for r in rows:
    err = str(r['error'])[:120] if has_error and r['error'] else ""
    print(f"  #{r['iteration_number']}: status={r['status']} score={r['score']} error={err}")
    if r['status'] == 'completed':
        completed += 1
        scores.append(r['score'])
    elif r['status'] == 'failed':
        failed += 1

print(f"\n  Completed: {completed}/5")
print(f"  Failed: {failed}/5")
if scores:
    print(f"  Scores: {scores}")
    print(f"  Avg score: {sum(scores)/len(scores):.1f}")
    print(f"  Score trend: {'ascending' if all(scores[i] <= scores[i+1] for i in range(len(scores)-1)) else 'mixed'}")

# Check roadmap via API
s, rm = api("/roadmap")
if s == 200:
    print(f"\n  Roadmap: {rm.get('progress_pct',0):.0f}% ({rm.get('completed_count',0)}/{rm.get('total_count',0)})")
    print(f"  Current task: {rm.get('current_task_name')}")

print("\nDone!")
