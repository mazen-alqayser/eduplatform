# reset_admin_password.py
import sqlite3
from werkzeug.security import generate_password_hash

DB = "instance/db.sqlite"   # تأكد من المسار الصحيح
ADMIN_USERNAME = "admin@example.com"  # استبدل باسم مستخدم المشرف الفعلي
NEW_PASSWORD = "NewStrongP@ssw0rd"    # ضع هنا كلمة مرور جديدة قوية

hashed = generate_password_hash(NEW_PASSWORD)

conn = sqlite3.connect(DB)
cur = conn.cursor()
cur.execute("UPDATE users SET password = ? WHERE username = ?", (hashed, ADMIN_USERNAME))
conn.commit()
print("Password updated for", ADMIN_USERNAME)
conn.close()
