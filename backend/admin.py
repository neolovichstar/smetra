import sys
from app import db, migrate, audit

if len(sys.argv) != 2:
    raise SystemExit('Usage: python backend/admin.py admin@example.com')
migrate()
with db() as con:
    row = con.execute('SELECT id FROM users WHERE email=?',(sys.argv[1].strip().lower(),)).fetchone()
    if not row: raise SystemExit('Register the user first')
    con.execute("UPDATE users SET role='admin' WHERE id=?",(row['id'],))
    audit(con,None,'admin.promoted',row['id'])
print('Admin role granted')
