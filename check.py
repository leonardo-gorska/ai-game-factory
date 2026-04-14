"""Quick DB-only status check."""
import sqlite3, sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
conn = sqlite3.connect("backend/storage/factory.db")
conn.row_factory = sqlite3.Row

# Schema check
cols = [c[1] for c in conn.execute("PRAGMA table_info(iterations)").fetchall()]
has_error = "error" in cols
print(f"error column: {has_error}")

if has_error:
    rows = conn.execute("SELECT iteration_number, status, score, error FROM iterations ORDER BY iteration_number").fetchall()
else:
    rows = conn.execute("SELECT iteration_number, status, score FROM iterations ORDER BY iteration_number").fetchall()

if not rows:
    print("No iterations yet")
else:
    for r in rows:
        err = f" err={str(r['error'])[:100]}" if has_error and r['error'] else ""
        print(f"#{r['iteration_number']}: status={r['status']} score={r['score']}{err}")

conn.close()
