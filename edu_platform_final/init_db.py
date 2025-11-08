import sqlite3, os

DB_PATH = os.path.join('instance', 'db.sqlite')
os.makedirs('instance', exist_ok=True)

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

# === جدول المستخدمين ===
cursor.execute('''
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fullname TEXT,
    username TEXT UNIQUE,
    email TEXT UNIQUE,
    password TEXT,
    is_admin INTEGER DEFAULT 0
)
''')

# === جدول الدورات ===
cursor.execute('''
CREATE TABLE IF NOT EXISTS courses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title_ar TEXT,
    title_en TEXT,
    short_desc_ar TEXT,
    short_desc_en TEXT,
    full_desc_ar TEXT,
    full_desc_en TEXT,
    image TEXT
)
''')

# === جدول الدروس ===
cursor.execute('''
CREATE TABLE IF NOT EXISTS lessons (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    course_id INTEGER,
    title_ar TEXT,
    title_en TEXT,
    content_ar TEXT,
    content_en TEXT,
    position INTEGER,
    video TEXT,
    FOREIGN KEY(course_id) REFERENCES courses(id)
)
''')

# === جدول التسجيلات ===
cursor.execute('''
CREATE TABLE IF NOT EXISTS enrollments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    course_id INTEGER,
    UNIQUE(user_id, course_id),
    FOREIGN KEY(user_id) REFERENCES users(id),
    FOREIGN KEY(course_id) REFERENCES courses(id)
)
''')

# === جدول طلبات التسجيل ===
cursor.execute('''
CREATE TABLE IF NOT EXISTS enroll_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    course_id INTEGER,
    status TEXT DEFAULT 'pending',
    FOREIGN KEY(user_id) REFERENCES users(id),
    FOREIGN KEY(course_id) REFERENCES courses(id)
)
''')

# === جدول تقدم المستخدم ===
cursor.execute('''
CREATE TABLE IF NOT EXISTS user_progress (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    lesson_id INTEGER,
    completed INTEGER DEFAULT 0,
    FOREIGN KEY(user_id) REFERENCES users(id),
    FOREIGN KEY(lesson_id) REFERENCES lessons(id)
)
''')

# === جدول الإعجابات (إن استُخدم لاحقًا) ===
cursor.execute('''
CREATE TABLE IF NOT EXISTS likes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    course_id INTEGER,
    FOREIGN KEY(user_id) REFERENCES users(id),
    FOREIGN KEY(course_id) REFERENCES courses(id)
)
''')

conn.commit()
conn.close()
print("✅ تم إنشاء قاعدة البيانات وكل الجداول بنجاح — instance/db.sqlite")
