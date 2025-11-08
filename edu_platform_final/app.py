from flask import (
    Flask, render_template, redirect, url_for, request, flash, g,
    send_from_directory, abort, session
)
from flask_login import (
    LoginManager, login_user, logout_user, login_required,
    current_user, UserMixin
)

import sqlite3, os, urllib.parse
import werkzeug.utils as utils
from functools import wraps
import os

# === المسارات الأساسية ===
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DB_PATH = os.path.join(BASE_DIR, 'instance', 'db.sqlite')
UPLOAD_DIR = os.path.join(BASE_DIR, 'instance', 'uploads')
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(os.path.join(BASE_DIR, 'instance'), exist_ok=True)

# === إعداد التطبيق ===
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'replace-with-secure-key')
app.config['DATABASE'] = DB_PATH
app.config['UPLOAD_FOLDER'] = UPLOAD_DIR
ADMIN_PHONE = os.environ.get('ADMIN_PHONE', '+201124592083')  # رقم واتساب المدير

# === إعداد تسجيل الدخول ===
login_manager = LoginManager()
login_manager.login_view = 'login'
login_manager.init_app(app)

# === نموذج المستخدم ===
class User(UserMixin):
    def __init__(self, id, username, fullname, is_admin=False):
        self.id = id
        self.username = username
        self.fullname = fullname
        self.is_admin = bool(is_admin)

@login_manager.user_loader
def load_user(user_id):
    conn = get_db()
    cur = conn.execute('SELECT id, username, fullname, is_admin FROM users WHERE id = ?', (user_id,))
    row = cur.fetchone()
    if row:
        return User(row['id'], row['username'], row['fullname'], row['is_admin'])
    return None

# === إدارة قاعدة البيانات ===
def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(app.config['DATABASE'])
        db.row_factory = sqlite3.Row
    return db


@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

# ⚠️ إضافة دالة تهيئة قاعدة البيانات لإنشاء الجداول المفقودة لمرة واحدة
def init_db():
    conn = get_db() 
    print("Initializing database (Checking for tables)...")
    
    # 1. إنشاء جدول المستخدمين (للتأكد من وجود الجداول الأساسية)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            fullname TEXT,
            email TEXT UNIQUE,
            is_admin BOOLEAN DEFAULT 0
        );
    """)

    # 2. إنشاء جدول الشرائح (Hero Slides) - الذي كان مفقوداً
    conn.execute("""
        CREATE TABLE IF NOT EXISTS hero_slides (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            image_path TEXT NOT NULL,
            title_ar TEXT NOT NULL,
            title_en TEXT NOT NULL,
            desc_ar TEXT,
            desc_en TEXT
        );
    """)

    # 3. إنشاء جدول الدورات (للتأكد) - إذا كان مفقوداً
    conn.execute("""
        CREATE TABLE IF NOT EXISTS courses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title_ar TEXT NOT NULL,
            title_en TEXT NOT NULL,
            short_desc_ar TEXT,
            short_desc_en TEXT,
            full_desc_ar TEXT,
            full_desc_en TEXT,
            image TEXT
        );
    """)

    # 4. إنشاء جدول الدروس (للتأكد) - إذا كان مفقوداً
    conn.execute("""
        CREATE TABLE IF NOT EXISTS lessons (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            course_id INTEGER NOT NULL,
            title_ar TEXT NOT NULL,
            title_en TEXT NOT NULL,
            content_ar TEXT,
            content_en TEXT,
            position INTEGER DEFAULT 0,
            video TEXT,
            FOREIGN KEY(course_id) REFERENCES courses(id)
        );
    """)

    # 5. جدول طلبات التسجيل (للتأكد)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS enroll_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            course_id INTEGER NOT NULL,
            status TEXT DEFAULT 'pending', -- accepted, rejected
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id),
            FOREIGN KEY(course_id) REFERENCES courses(id),
            UNIQUE(user_id, course_id)
        );
    """)

    # 6. جدول الالتحاق المقبول (للتأكد)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS enrollments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            course_id INTEGER NOT NULL,
            approved BOOLEAN DEFAULT 0,
            UNIQUE(user_id, course_id),
            FOREIGN KEY(user_id) REFERENCES users(id),
            FOREIGN KEY(course_id) REFERENCES courses(id)
        );
    """)
    
    # 7. جدول تقدم المستخدم (للتأكد)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS user_progress (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            lesson_id INTEGER NOT NULL,
            completed BOOLEAN DEFAULT 0,
            UNIQUE(user_id, lesson_id),
            FOREIGN KEY(user_id) REFERENCES users(id),
            FOREIGN KEY(lesson_id) REFERENCES lessons(id)
        );
    """)

    conn.commit()
    print("✅ Database initialization complete.")
# نهاية دالة init_db

# === دالة مساعدة لتحديد الملفات المسموح بها ===
def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in {'png', 'jpg', 'jpeg', 'gif'}
@app.route('/')
def landing():
    # ✅ تحديد اللغة وتخزينها في الجلسة
    lang = request.args.get('lang', session.get('lang', 'ar'))
    session['lang'] = lang

    conn = get_db()

    # 🛑 التعديل لحل خطأ "Object of type Row is not JSON serializable"
    # جلب الشرائح من قاعدة البيانات (Hero Section)
    raw_hero_slides = conn.execute('SELECT * FROM hero_slides ORDER BY id ASC').fetchall()
    
    # تحويل كائنات الصفوف إلى قواميس لضمان إمكانية تحويلها إلى JSON في القالب
    hero_slides = [dict(slide) for slide in raw_hero_slides]
    hero_slides = hero_slides if hero_slides else [] 

    # ✅ جلب الدورات بناءً على حالة المستخدم
    if current_user.is_authenticated:
        raw_courses = conn.execute("""
            SELECT id,
                   CASE WHEN ?='en' THEN title_en ELSE title_ar END AS title,
                   CASE WHEN ?='en' THEN short_desc_en ELSE short_desc_ar END AS short_desc,
                   image
            FROM courses
            WHERE id NOT IN (
                SELECT course_id FROM enrollments WHERE user_id=? AND approved=1
            )
        """, (lang, lang, current_user.id)).fetchall()
    else:
        raw_courses = conn.execute("""
            SELECT id,
                   CASE WHEN ?='en' THEN title_en ELSE title_ar END AS title,
                   CASE WHEN ?='en' THEN short_desc_en ELSE short_desc_ar END AS short_desc,
                   image
            FROM courses
        """, (lang, lang)).fetchall()
    
    # 🛑 تحويل الدورات إلى قواميس أيضاً
    courses = [dict(course) for course in raw_courses]


    # ✅ النصوص الترويجية
    promos = (
        ['تعلّم من الخبراء', 'دورات عملية', 'انضم لآلاف المتعلمين']
        if lang == 'ar'
        else ['Learn from experts', 'Hands-on courses', 'Join thousands']
    )

    # ✅ تمرير البيانات للقالب
    return render_template(
        'landing.html',
        lang=lang,
        promos=promos,
        courses=courses,
        hero_slides=hero_slides
    )

# === التسجيل ===
# (بقية دوال التسجيل والدخول والمستخدمين لم تتغير)
@app.route('/register', methods=['GET', 'POST'])
def register():
    lang = request.args.get('lang', 'ar')
    if request.method == 'POST':
        fullname = request.form.get('fullname', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '').strip()
        confirm = request.form.get('confirm', '').strip()

        if password != confirm:
            flash('Passwords do not match' if lang == 'en' else 'كلمتا المرور غير متطابقتين')
            return redirect(url_for('register', lang=lang))

        conn = get_db()
        try:
            conn.execute('INSERT INTO users (username, password, fullname, email) VALUES (?, ?, ?, ?)',
                         (email, password, fullname, email))
            conn.commit()
        except Exception:
            flash('Email already used' if lang == 'en' else 'البريد مستخدم')
            return redirect(url_for('register', lang=lang))

        flash('Account created' if lang == 'en' else 'تم إنشاء الحساب')
        return redirect(url_for('login', lang=lang))

    return render_template('register.html', lang=lang)

# === تسجيل الدخول ===
@app.route('/login', methods=['GET', 'POST'])
def login():
    lang = request.args.get('lang', 'ar')
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '').strip()
        conn = get_db()

        user = conn.execute('SELECT id, username, fullname, password, is_admin FROM users WHERE username = ? OR email = ?', (email, email)).fetchone()
        if user and password == user['password']:
            user_obj = User(user['id'], user['username'], user['fullname'], user['is_admin'])
            login_user(user_obj)

            # ✅ توجيه المشرف إلى لوحة الإدارة
            if user['is_admin']:
                flash('Welcome Admin' if lang == 'en' else 'مرحباً أيها المشرف')
                return redirect(url_for('admin_index'))

            # ✅ توجيه المستخدم العادي إلى صفحته
            flash('Logged in' if lang == 'en' else 'تم تسجيل الدخول')
            return redirect(url_for('profile', lang=lang))

        flash('Invalid credentials' if lang == 'en' else 'خطأ في البيانات')

    return render_template('login.html', lang=lang)

@app.route('/logout')
@login_required
def logout():
    lang = request.args.get('lang', 'ar')
    logout_user()
    flash('Logged out' if lang == 'en' else 'تم تسجيل الخروج')
    return redirect(url_for('landing', lang=lang))

@app.route('/profile')
@login_required
def profile():
    lang = request.args.get('lang', 'ar')
    conn = get_db()

    # جلب الدورات التي تم قبول طلب التسجيل فيها فقط
    enrolled_courses = conn.execute('''
        SELECT c.id, 
               CASE WHEN ?='en' THEN c.title_en ELSE c.title_ar END AS title,
               c.image,
               CASE WHEN ?='en' THEN c.short_desc_en ELSE c.short_desc_ar END AS short_desc
        FROM enrollments e
        JOIN courses c ON e.course_id = c.id
        WHERE e.user_id = ? 
          AND e.approved = 1
    ''', (lang, lang, current_user.id)).fetchall()

    # جلب الدروس فقط في الدورات المقبولة
    courses_with_lessons = []
    for course in enrolled_courses:
        lessons = conn.execute('''
             SELECT l.id,
                    CASE WHEN ?='en' THEN l.title_en ELSE l.title_ar END AS title,
                    up.completed
             FROM lessons l
             LEFT JOIN user_progress up ON up.lesson_id = l.id AND up.user_id = ?
             WHERE l.course_id = ?
             ORDER BY l.position ASC
          ''', (lang, current_user.id, course['id'])).fetchall()
        courses_with_lessons.append({
            'course': course,
            'lessons': lessons
        })

    return render_template('profile.html', lang=lang, courses=courses_with_lessons)

#@app.route("/course/<int:course_id>")
# تم تعريف course_page في الأسفل مع إزالة التعليق
# @login_required 
# def course_page(course_id): 
# (موجودة في الأسفل)

@app.route('/lesson/<int:lesson_id>')
@login_required
def lesson_page(lesson_id):
    conn = get_db()
    lesson = conn.execute("SELECT * FROM lessons WHERE id = ?", (lesson_id,)).fetchone()
    if not lesson:
        abort(404)
        
    # التحقق من أن المستخدم مسجل في الدورة (approved=1)
    course_id = lesson['course_id']
    enrollment = conn.execute("""
          SELECT * FROM enrollments 
          WHERE user_id=? AND course_id=? AND approved=1
      """, (current_user.id, course_id)).fetchone()
    
    if not enrollment:
        flash("❌ يجب أن تكون مسجلاً ومقبولاً في الدورة للوصول لهذا الدرس.", "error")
        return redirect(url_for('course_page', course_id=course_id))

    # جلب اللغة من query param أولاً ثم session
    lang = request.args.get('lang', session.get('lang', 'ar'))
    session['lang'] = lang

    # استخدام index للوصول إلى الأعمدة
    if lang == 'en':
        title = lesson['title_en'] if 'title_en' in lesson.keys() else lesson['title_ar']
        description = lesson['content_en'] if 'content_en' in lesson.keys() else lesson['content_ar']
    else:
        title = lesson['title_ar'] if 'title_ar' in lesson.keys() else lesson['title_en']
        description = lesson['content_ar'] if 'content_ar' in lesson.keys() else lesson['content_en']
        
    # جلب حالة مشاهدة الدرس
    progress = conn.execute("SELECT completed FROM user_progress WHERE user_id=? AND lesson_id=?", (current_user.id, lesson_id)).fetchone()
    is_completed = progress['completed'] if progress else 0

    return render_template(
        'lesson_page.html',
        lesson=lesson,
        title=title,
        description=description,
        lang=lang,
        is_completed=is_completed
    )

# === طلب التسجيل في دورة ===
@app.route('/course/<int:course_id>/enroll', methods=['POST'])
@login_required
def enroll(course_id):
    lang = request.args.get('lang', 'ar')
    conn = get_db()
    course = conn.execute('SELECT title_ar, title_en FROM courses WHERE id=?', (course_id,)).fetchone()
    if not course:
        flash("❌ الدورة غير موجودة.", "error")
        return redirect(url_for('landing'))
        
    title = course['title_en'] if lang == 'en' else course['title_ar']
    
    # التحقق مما إذا كان الطلب موجود بالفعل
    existing_request = conn.execute('SELECT * FROM enroll_requests WHERE user_id=? AND course_id=?', (current_user.id, course_id)).fetchone()
    if existing_request:
        if existing_request['status'] == 'accepted':
            flash("✅ أنت مسجل ومقبول بالفعل في هذه الدورة.", "info")
            return redirect(url_for('course_page', course_id=course_id))
        else:
            flash("⏳ تم إرسال طلبك مسبقاً، يرجى الانتظار للموافقة.", "info")
            
    else:
        # إرسال طلب جديد
        conn.execute('INSERT INTO enroll_requests (user_id, course_id, status) VALUES (?, ?, ?)', (current_user.id, course_id, 'pending'))
        conn.commit()
        flash("✅ تم إرسال طلب التسجيل بنجاح. سيتم توجيهك إلى واتساب للتواصل مع المدير.", "success")
        
    # بناء رابط واتساب
    text = f"Hello Admin, I am requesting enrollment for the course: {title}. My username is {current_user.username}." if lang == 'en' else f"مرحباً أيها المشرف، أطلب التسجيل في الدورة: {title}. اسم المستخدم الخاص بي هو {current_user.username}."
    wa_url = f"https://wa.me/{ADMIN_PHONE.lstrip('+')}?text=" + urllib.parse.quote(text)
    
    return redirect(wa_url)


# === علامة مشاهدة الدرس ===
@app.route('/lesson/<int:lesson_id>/mark_watched', methods=['POST'])
@login_required
def mark_watched(lesson_id):
    conn = get_db()
    
    # التأكد من وجود الدرس
    lesson = conn.execute("SELECT course_id FROM lessons WHERE id = ?", (lesson_id,)).fetchone()
    if not lesson:
        return ('', 404)
        
    # التأكد من أن المستخدم مسجل ومقبول في الدورة
    enrollment = conn.execute("""
          SELECT * FROM enrollments 
          WHERE user_id=? AND course_id=? AND approved=1
      """, (current_user.id, lesson['course_id'])).fetchone()
      
    if not enrollment:
        return ('', 403) # Forbidden
        
    # تحديث حالة التقدم إلى مكتمل (completed=1)
    conn.execute('''
        INSERT INTO user_progress (user_id, lesson_id, completed)
        VALUES (?, ?, 1)
        ON CONFLICT(user_id, lesson_id) DO UPDATE SET completed=1
    ''', (current_user.id, lesson_id))
    conn.commit()
    return ('', 204)

# === طلب شهادة ===
@app.route('/course/<int:course_id>/request_certificate')
@login_required
def request_certificate(course_id):
    lang = request.args.get('lang', 'ar')
    conn = get_db()
    
    # التحقق من التسجيل
    enrollment = conn.execute("SELECT * FROM enrollments WHERE user_id=? AND course_id=? AND approved=1", (current_user.id, course_id)).fetchone()
    if not enrollment:
        flash("❌ يجب أن تكون مسجلاً ومقبولاً في الدورة لطلب الشهادة.", "error")
        return redirect(url_for('course_page', course_id=course_id))

    # التحقق من إكمال جميع الدروس (اختياري، يمكن أن تعتمد على منطق آخر)
    lessons_count = conn.execute("SELECT COUNT(*) FROM lessons WHERE course_id=?", (course_id,)).fetchone()[0]
    completed_count = conn.execute("SELECT COUNT(*) FROM user_progress WHERE user_id=? AND lesson_id IN (SELECT id FROM lessons WHERE course_id = ?) AND completed=1", (current_user.id, course_id)).fetchone()[0]

    if completed_count < lessons_count:
        flash("❌ يجب إكمال جميع الدروس في الدورة أولاً لطلب الشهادة.", "error")
        return redirect(url_for('course_page', course_id=course_id))

    course = conn.execute('SELECT title_ar, title_en FROM courses WHERE id=?', (course_id,)).fetchone()
    title = course['title_en'] if lang == 'en' else course['title_ar']
    text = f"Requesting certificate for course: {title} (user: {current_user.username})" if lang == 'en' else f"أطلب شهادة الدورة: {title} (المستخدم: {current_user.username})"
    wa_url = f"https://wa.me/{ADMIN_PHONE.lstrip('+')}?text=" + urllib.parse.quote(text)
    
    flash("✅ تم تجهيز طلب الشهادة، يرجى إرسال رسالة الواتساب للمتابعة.", "success")
    return redirect(wa_url)

# === صلاحيات المدير ===
def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated or not getattr(current_user, 'is_admin', False):
            flash('Access denied')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return wrapper

# -----------------------------------------------
# 🌟 قسم لوحات الإدارة المعدل 🌟
# -----------------------------------------------

# === لوحات الإدارة الرئيسية ===
@app.route('/admin')
@login_required
@admin_required
def admin_index():
    lang = request.args.get('lang', session.get('lang', 'ar'))
    conn = get_db()
    courses = conn.execute('SELECT * FROM courses ORDER BY id DESC').fetchall()
    # ⬅️ جلب بيانات الشرائح لإدارتها في لوحة المشرف
    hero_slides = conn.execute('SELECT * FROM hero_slides ORDER BY id ASC').fetchall()
    return render_template('admin/index.html', courses=courses, lang=lang, hero_slides=hero_slides)
# -----------------------------------------------
# 🖼️ دوال إدارة شرائح الشريط الرئيسي (Hero Slides)
# -----------------------------------------------
# تأكد من وجود الاستيرادات التالية في بداية ملف app.py
import os
# import werkzeug.utils as utils 
# from flask import flash, redirect, url_for, request, session, current_app as app
from flask_wtf.csrf import generate_csrf
# يجب أن تكون الدوال الأخرى مثل get_db, allowed_file, login_required, admin_required, utils, app, os, موجودة ومعرفة.

# دالة إدارة إضافة شريحة جديدة
@app.route('/admin/slider/new', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_slider_new():
    lang = request.args.get('lang', session.get('lang', 'ar'))
    if request.method == 'POST':
        # جلب البيانات
        title_ar = request.form.get('title_ar', '').strip()
        title_en = request.form.get('title_en', '').strip()
        desc_ar = request.form.get('desc_ar', '').strip()
        desc_en = request.form.get('desc_en', '').strip()
        # اسم الحقل 'new_image'
        img = request.files.get('new_image')
        img_name = None

        if not title_ar or not title_en:
            flash('يجب توفير العنوانين والوصفين.', 'error')
            return redirect(url_for('admin_slider_new', lang=lang))
            
        # التحقق من وجود الصورة فقط عند الإضافة
        if not img or not img.filename:
            flash('يجب توفير صورة للشريحة الجديدة.', 'error')
            return redirect(url_for('admin_slider_new', lang=lang))


        if img and img.filename and allowed_file(img.filename):
            img_name = utils.secure_filename(img.filename)
            try:
                img.save(os.path.join(app.config['UPLOAD_FOLDER'], img_name))
            except Exception as e:
                flash(f'فشل حفظ الصورة: {e}', 'error')
                return redirect(url_for('admin_slider_new', lang=lang))
        else:
            flash('صيغة الصورة غير مدعومة.', 'error')
            return redirect(url_for('admin_slider_new', lang=lang))
            
        conn = get_db()
        try:
            conn.execute('''
                INSERT INTO hero_slides (image_path, title_ar, title_en, desc_ar, desc_en)
                VALUES (?, ?, ?, ?, ?)
            ''', (img_name, title_ar, title_en, desc_ar, desc_en))
            conn.commit()
            flash('✅ تم إضافة شريحة جديدة بنجاح', 'success')
            return redirect(url_for('admin_index', lang=lang))
        except Exception as e:
            conn.rollback()
            flash(f'فشل إضافة الشريحة: {e}', 'error')
            return redirect(url_for('admin_slider_new', lang=lang))

    # GET -> عرض النموذج
    # 🎯 تم تمرير csrf_token هنا لحل الخطأ
    return render_template('admin/slider_form.html', 
                           slide=None, 
                           lang=lang,
                           csrf_token=generate_csrf())

# دالة إدارة تعديل شريحة موجودة
@app.route('/admin/slider/edit/<int:slide_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_slider_edit(slide_id):
    lang = request.args.get('lang', session.get('lang', 'ar'))
    conn = get_db()
    
    if request.method == 'POST':
        slide = conn.execute('SELECT * FROM hero_slides WHERE id = ?', (slide_id,)).fetchone()
        if not slide:
            flash('Slide not found' if lang == 'en' else 'لم يتم العثور على الشريحة', 'error')
            return redirect(url_for('admin_index', lang=lang))

        title_ar = request.form.get('title_ar', '').strip()
        title_en = request.form.get('title_en', '').strip()
        desc_ar = request.form.get('desc_ar', '').strip()
        desc_en = request.form.get('desc_en', '').strip()

        img = request.files.get('new_image')
        img_name = slide['image_path']  

        if img and img.filename and allowed_file(img.filename):
            new_name = utils.secure_filename(img.filename)
            
            # حذف الملف القديم
            if slide['image_path']:
                old_path = os.path.join(app.config['UPLOAD_FOLDER'], slide['image_path'])
                if os.path.exists(old_path):
                    os.remove(old_path)
            
            # حفظ الملف الجديد
            try:
                img.save(os.path.join(app.config['UPLOAD_FOLDER'], new_name))
                img_name = new_name
            except Exception as e:
                flash(f'فشل حفظ الصورة الجديدة: {e}', 'error')
                return redirect(url_for('admin_slider_edit', slide_id=slide_id, lang=lang))

        # تحديث السجل في قاعدة البيانات
        try:
            conn.execute('''
                UPDATE hero_slides
                SET title_ar=?, title_en=?, desc_ar=?, desc_en=?, image_path=?
                WHERE id=?
            ''', (title_ar, title_en, desc_ar, desc_en, img_name, slide_id))
            conn.commit()
            
            flash('✅ تم تحديث الشريحة بنجاح', 'success')
            return redirect(url_for('admin_index', lang=lang))
        except Exception as e:
            conn.rollback()
            flash(f'فشل تحديث الشريحة: {e}', 'error')
            return redirect(url_for('admin_slider_edit', slide_id=slide_id, lang=lang))


    # GET -> عرض النموذج
    slide = conn.execute('SELECT * FROM hero_slides WHERE id = ?', (slide_id,)).fetchone()
    if not slide:
        flash('Slide not found' if lang == 'en' else 'لم يتم العثور على الشريحة', 'error')
        return redirect(url_for('admin_index', lang=lang))
        
    # 🎯 تم تمرير csrf_token هنا لحل الخطأ
    return render_template('admin/slider_form.html', 
                           slide=slide, 
                           lang=lang,
                           csrf_token=generate_csrf())

# دالة حذف الشريحة بالكامل (GET)
@app.route('/admin/slider/delete/<int:slide_id>', methods=['GET'])
@login_required
@admin_required
def admin_slider_delete(slide_id):
    lang = request.args.get('lang', session.get('lang', 'ar'))
    conn = get_db()
    slide = conn.execute('SELECT * FROM hero_slides WHERE id = ?', (slide_id,)).fetchone()
    if not slide:
        flash('Slide not found' if lang == 'en' else 'لم يتم العثور على الشريحة', 'error')
        return redirect(url_for('admin_index', lang=lang))

    try:
        if slide['image_path']:
            ipath = os.path.join(app.config['UPLOAD_FOLDER'], slide['image_path'])
            if os.path.exists(ipath):
                os.remove(ipath)

        conn.execute('DELETE FROM hero_slides WHERE id = ?', (slide_id,))
        conn.commit()
        flash('🗑️ تم حذف الشريحة بنجاح', 'info')
    except Exception:
        conn.rollback()
        app.logger.exception("Failed to delete slider item")
        flash('فشل الحذف' if lang == 'ar' else 'Delete failed', 'error')
        
    return redirect(url_for('admin_index', lang=lang))


# دالة حذف الصورة فقط (والاحتفاظ بالشريحة) (GET)
@app.route('/admin/slider/delete_image/<int:slide_id>', methods=['GET'])
@login_required
@admin_required
def admin_slider_delete_image(slide_id):
    lang = request.args.get('lang', session.get('lang', 'ar'))
    conn = get_db()
    slide = conn.execute('SELECT * FROM hero_slides WHERE id = ?', (slide_id,)).fetchone()
    if not slide:
        flash('Slide not found' if lang == 'en' else 'لم يتم العثور على الشريحة', 'error')
        return redirect(url_for('admin_index', lang=lang))
        
    if not slide['image_path']:
        flash('لا توجد صورة لحذفها.' if lang == 'ar' else 'No image to delete.', 'warning')
        return redirect(url_for('admin_slider_edit', slide_id=slide_id, lang=lang))
    
    try:
        ipath = os.path.join(app.config['UPLOAD_FOLDER'], slide['image_path'])
        if os.path.exists(ipath):
            os.remove(ipath)

        conn.execute('UPDATE hero_slides SET image_path = ? WHERE id = ?', (None, slide_id))
        conn.commit()
        
        flash('🖼️ تم حذف الصورة بنجاح. يمكنك رفع صورة جديدة الآن.', 'info')
    except Exception as e:
        conn.rollback()
        # يجب استخدام app.logger.exception إذا كانت app متاحة
        # app.logger.exception(f"Failed to delete slider image: {e}") 
        flash('فشل حذف الصورة.' if lang == 'ar' else 'Image deletion failed.', 'error')
        
    return redirect(url_for('admin_slider_edit', slide_id=slide_id, lang=lang))

# -----------------------------------------------
# 📚 دوال إدارة الدورات والدروس (لم تتغير)
# -----------------------------------------------

@app.route('/admin/course/new', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_course_new():
    # ... (بقية الدالة كما هي) ...
    if request.method == 'POST':
        title_ar = request.form.get('title_ar', '').strip()
        title_en = request.form.get('title_en', '').strip()
        img = request.files.get('image')
        img_name = None
        if img and img.filename and allowed_file(img.filename): # تم إضافة التحقق من allowed_file
            img_name = utils.secure_filename(img.filename)
            img.save(os.path.join(app.config['UPLOAD_FOLDER'], img_name))
        conn = get_db()
        conn.execute('''
            INSERT INTO courses (title_ar, title_en, short_desc_ar, short_desc_en, full_desc_ar, full_desc_en, image)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (title_ar, title_en, request.form.get('short_desc_ar'),
              request.form.get('short_desc_en'), request.form.get('full_desc_ar'),
              request.form.get('full_desc_en'), img_name))
        conn.commit()
        return redirect(url_for('admin_index'))
    return render_template('admin/course_form.html', course=None)


# 📝 إضافة درس جديد
@app.route('/admin/course/<int:course_id>/lesson/new', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_lesson_new(course_id):
    if request.method == 'POST':
        # 1. قراءة البيانات من النموذج
        title_ar = request.form.get('title_ar', '').strip()
        title_en = request.form.get('title_en', '').strip()
        content_ar = request.form.get('content_ar', '').strip()
        content_en = request.form.get('content_en', '').strip()
        pos = int(request.form.get('position', '0') or 0)
        
        # 🆕 قراءة رابط اليوتيوب الجديد
        video_url = request.form.get('video_embed_url', '').strip()
        
        video = request.files.get('video')
        video_filename = None
        
        # 2. معالجة تحميل الفيديو المحلي
        if video and video.filename:
            video_filename = utils.secure_filename(video.filename)
            # يجب التأكد من عمل هذه الدالة بشكل صحيح لحفظ الملف
            video.save(os.path.join(app.config['UPLOAD_FOLDER'], video_filename))
            
            # 💡 منطق تفضيل: إذا تم تحميل ملف، يتم إهمال رابط اليوتيوب
            video_url = None
        
        conn = get_db()
        
        # 3. تحديث استعلام الإضافة (إضافة حقل video_url)
        conn.execute('''
             INSERT INTO lessons (course_id, title_ar, title_en, content_ar, content_en, position, video, video_url)
             VALUES (?, ?, ?, ?, ?, ?, ?, ?)
           ''', (course_id, title_ar, title_en, content_ar,
                 content_en, pos, video_filename, video_url))
        conn.commit()
        
        flash("✅ تم إضافة الدرس بنجاح", "success")
        return redirect(url_for('admin_lessons', course_id=course_id))
        
    return render_template('admin/lesson_form.html', lesson=None, course_id=course_id)
# 📝 تعديل درس موجود
@app.route("/admin/course/<int:course_id>/lesson/<int:lesson_id>/edit", methods=["GET", "POST"])
@login_required
@admin_required
def admin_lesson_edit(course_id, lesson_id):
    conn = get_db()
    
    # 1. جلب بيانات الدرس. (يفترض أن lesson سيعود كقاموس أو صف)
    lesson = conn.execute("SELECT * FROM lessons WHERE id=? AND course_id=?", (lesson_id, course_id)).fetchone()
    
    if not lesson:
        flash("لم يتم العثور على الدرس", "error")
        return redirect(url_for("admin_lessons", course_id=course_id))

    if request.method == "POST":
        # 2. قراءة البيانات من النموذج
        title_ar = request.form.get("title_ar", "").strip()
        title_en = request.form.get("title_en", "").strip()
        content_ar = request.form.get("content_ar", "").strip()
        content_en = request.form.get("content_en", "").strip()
        position = int(request.form.get("position", "0") or 0)
        
        # ✅ التعديل الأول: قراءة رابط اليوتيوب باستخدام اسم الحقل الصحيح في النموذج (video_url)
        video_url_value = request.form.get("video_url", "").strip()
        # إذا كانت القيمة فارغة، نرسل None إلى قاعدة البيانات لتجنب تخزين سلسلة نصية فارغة
        if not video_url_value:
            video_url_value = None

        video = request.files.get("video")
        video_filename = lesson["video"] # الاحتفاظ بالاسم القديم للفيديو المحلي

        # 3. معالجة تحميل ملف جديد
        if video and video.filename:
            # حذف الفيديو القديم إذا وُجد
            if video_filename:
                old_path = os.path.join(app.config.get("UPLOAD_FOLDER", ''), video_filename)
                if os.path.exists(old_path) and os.path.isfile(old_path):
                    os.remove(old_path)
            # حفظ الفيديو الجديد
            video_filename = utils.secure_filename(video.filename)
            # video.save(os.path.join(app.config.get("UPLOAD_FOLDER", ''), video_filename))
            
            # منطق تفضيل: إذا تم تحميل ملف، يتم إهمال رابط اليوتيوب
            video_url_value = None 
            
        # 4. ✅ التعديل الثاني: تصحيح استعلام التحديث. 
        # يجب أن يتطابق اسم العمود في SQL مع ما هو موجود فعلياً في القاعدة (يفترض أنه video_url)
        conn.execute("""
             UPDATE lessons
             SET title_ar=?, title_en=?, content_ar=?, content_en=?, position=?, video=?, video_url=?
             WHERE id=? AND course_id=?
           """, (title_ar, title_en, content_ar, content_en, position, video_filename, video_url_value, lesson_id, course_id))
        conn.commit()

        flash("✅ تم تحديث بيانات الدرس بنجاح", "success")
        return redirect(url_for("admin_lessons", course_id=course_id))

    # تمرير البيانات الحالية للعرض في النموذج
    return render_template("admin/lesson_form.html", lesson=lesson, course_id=course_id)

@app.route("/admin/course/<int:course_id>/lesson/<int:lesson_id>/delete", methods=["POST", "GET"])
@login_required
@admin_required
def admin_lesson_delete(course_id, lesson_id):
    if request.method == "GET":
        flash("⚠️ لا يمكنك الوصول إلى هذا الرابط مباشرة")
        return redirect(url_for("admin_lessons", course_id=course_id))
    
    conn = get_db()
    lesson = conn.execute("SELECT * FROM lessons WHERE id=? AND course_id=?", (lesson_id, course_id)).fetchone()
    if not lesson:
        flash("لم يتم العثور على الدرس")
        return redirect(url_for("admin_lessons", course_id=course_id))

    # حذف الفيديو إذا موجود
    if lesson["video"]:
        video_path = os.path.join(app.config["UPLOAD_FOLDER"], lesson["video"])
        if os.path.exists(video_path):
            os.remove(video_path)

    conn.execute("DELETE FROM lessons WHERE id=? AND course_id=?", (lesson_id, course_id))
    conn.commit()
    flash("🗑️ تم حذف الدرس بنجاح", "info")
    return redirect(url_for("admin_lessons", course_id=course_id))


@app.route('/admin/course/<int:course_id>/lessons')
@login_required
@admin_required
def admin_lessons(course_id):
    conn = get_db()
    course = conn.execute('SELECT * FROM courses WHERE id=?', (course_id,)).fetchone()
    lessons = conn.execute('SELECT * FROM lessons WHERE course_id=? ORDER BY position', (course_id,)).fetchall()
    return render_template('admin/lessons.html', course=course, lessons=lessons)

# === تعديل دورة (Edit Course) ===
@app.route('/admin/course/<int:course_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_course_edit(course_id):
    conn = get_db()
    # جلب بيانات الدورة الحالية
    course = conn.execute('SELECT * FROM courses WHERE id = ?', (course_id,)).fetchone()
    if not course:
        flash('Course not found' if request.args.get('lang', 'ar') == 'en' else 'لم يتم العثور على الدورة')
        return redirect(url_for('admin_index'))

    if request.method == 'POST':
        title_ar = request.form.get('title_ar', '').strip()
        title_en = request.form.get('title_en', '').strip()
        short_desc_ar = request.form.get('short_desc_ar')
        short_desc_en = request.form.get('short_desc_en')
        full_desc_ar = request.form.get('full_desc_ar')
        full_desc_en = request.form.get('full_desc_en')

        img = request.files.get('image')
        img_name = course['image']  # default to existing

        if img and img.filename:
            # احفظ الصورة الجديدة واحذف القديمة إن وُجدت
            new_name = utils.secure_filename(img.filename)
            img.save(os.path.join(app.config['UPLOAD_FOLDER'], new_name))
            # احذف الملف القديم إذا كان موجوداً
            if course['image']:
                try:
                    old_path = os.path.join(app.config['UPLOAD_FOLDER'], course['image'])
                    if os.path.exists(old_path):
                        os.remove(old_path)
                except Exception:
                    app.logger.exception("Failed to remove old course image")
            img_name = new_name

        # تحديث السجل
        conn.execute('''
             UPDATE courses
             SET title_ar=?, title_en=?, short_desc_ar=?, short_desc_en=?, full_desc_ar=?, full_desc_en=?, image=?
             WHERE id=?
          ''', (title_ar, title_en, short_desc_ar, short_desc_en, full_desc_ar, full_desc_en, img_name, course_id))
        conn.commit()
        flash('Course updated' if request.args.get('lang', 'ar') == 'en' else 'تم تحديث الدورة')
        return redirect(url_for('admin_index'))

    # GET -> عرض النموذج مع البيانات الحالية
    return render_template('admin/course_form.html', course=course)


# === حذف دورة (Delete Course) ===
@app.route('/admin/course/<int:course_id>/delete', methods=['POST'])
@login_required
@admin_required
def admin_course_delete(course_id):
    conn = get_db()
    # اجلب بيانات الدورة وملفاتها
    course = conn.execute('SELECT * FROM courses WHERE id = ?', (course_id,)).fetchone()
    if not course:
        flash('Course not found' if request.args.get('lang', 'ar') == 'en' else 'لم يتم العثور على الدورة')
        return redirect(url_for('admin_index'))

    try:
        # حذف ملفات الفيديو والصورة المرتبطة بالدروس
        lessons = conn.execute('SELECT video FROM lessons WHERE course_id = ?', (course_id,)).fetchall()
        for l in lessons:
            if l['video']:
                try:
                    vpath = os.path.join(app.config['UPLOAD_FOLDER'], l['video'])
                    if os.path.exists(vpath):
                        os.remove(vpath)
                except Exception:
                    app.logger.exception("Failed to remove lesson video")

        # حذف ملف صورة الدورة إن وُجد
        if course['image']:
            try:
                ipath = os.path.join(app.config['UPLOAD_FOLDER'], course['image'])
                if os.path.exists(ipath):
                    os.remove(ipath)
            except Exception:
                app.logger.exception("Failed to remove course image")

        # حذف الصفوف المرتبطة: user_progress, lessons, enrollments, likes, enroll_requests (إن وجدت)
        conn.execute('DELETE FROM user_progress WHERE lesson_id IN (SELECT id FROM lessons WHERE course_id = ?)', (course_id,))
        conn.execute('DELETE FROM lessons WHERE course_id = ?', (course_id,))
        conn.execute('DELETE FROM enrollments WHERE course_id = ?', (course_id,))
        # conn.execute('DELETE FROM likes WHERE course_id = ?', (course_id,)) # (تم التعليق عليها لأن جدول Likes غير موجود في init_db)
        conn.execute('DELETE FROM enroll_requests WHERE course_id = ?', (course_id,))
        conn.execute('DELETE FROM courses WHERE id = ?', (course_id,))
        conn.commit()
        flash('Course deleted' if request.args.get('lang', 'ar') == 'en' else 'تم حذف الدورة')
    except Exception:
        conn.rollback()
        app.logger.exception("Failed to delete course")
        flash('Delete failed' if request.args.get('lang', 'ar') == 'en' else 'فشل الحذف')
    return redirect(url_for('admin_index'))

# === عرض طلبات التسجيل في الدورات (المعلقة فقط) ===
@app.route('/admin/enroll_requests')
@login_required
@admin_required
def admin_enroll_requests():
    conn = get_db()
    # عرض الطلبات التي لم يتم التعامل معها بعد (status=NULL أو 'pending')
    requests = conn.execute("""
             SELECT er.id, er.status, u.id AS user_id, u.fullname, u.username, 
                     c.id AS course_id, c.title_ar, c.title_en
             FROM enroll_requests er
             JOIN users u ON er.user_id = u.id
             JOIN courses c ON er.course_id = c.id
             WHERE er.status IS NULL OR er.status='pending'
             ORDER BY er.id DESC
          """).fetchall()
    return render_template('admin/enroll_requests.html', requests=requests)

# === قبول الطلب وتسجيل المستخدم في الدورة وتفعيل جميع الدروس ===
@app.route('/admin/enroll_requests/<int:request_id>/accept', methods=['POST'])
@login_required
@admin_required
def admin_accept_enroll_request(request_id):
    conn = get_db()
    
    # جلب الطلب
    req = conn.execute("SELECT * FROM enroll_requests WHERE id=?", (request_id,)).fetchone()
    if not req:
        flash("❌ لم يتم العثور على الطلب", "error")
        return redirect(url_for('admin_enroll_requests'))

    user_id = req['user_id']
    course_id = req['course_id']

    # إضافة أو تحديث سجل الالتحاق مع تفعيل approved=1
    conn.execute("""
             INSERT INTO enrollments (user_id, course_id, approved)
             VALUES (?, ?, 1)
             ON CONFLICT(user_id, course_id) DO UPDATE SET approved=1
          """, (user_id, course_id))

    # تفعيل جميع الدروس للمستخدم
    lessons = conn.execute("SELECT id FROM lessons WHERE course_id=?", (course_id,)).fetchall()
    for lesson in lessons:
        conn.execute("""
              INSERT OR IGNORE INTO user_progress (user_id, lesson_id, completed)
              VALUES (?, ?, 0)
          """, (user_id, lesson['id']))  # اجعل completed=0 لتبدأ الدروس مغلقة لكنها متاحة

    # تحديث حالة الطلب
    conn.execute("UPDATE enroll_requests SET status='accepted' WHERE id=?", (request_id,))
    conn.commit()

    flash("✅ تم قبول الطلب وتفعيل جميع دروس الدورة للمستخدم", "success")
    return redirect(url_for('admin_enroll_requests'))

# === رفض أو إيقاف الطلب ===
@app.route('/admin/enroll_requests/<int:request_id>/reject', methods=['POST'])
@login_required
@admin_required
def admin_reject_enroll_request(request_id):
    conn = get_db()

    # جلب الطلب
    req = conn.execute("SELECT * FROM enroll_requests WHERE id=?", (request_id,)).fetchone()
    if not req:
        flash("❌ لم يتم العثور على الطلب", "error")
        return redirect(url_for('admin_enroll_requests'))

    # حذف الطلب فقط دون تسجيل المستخدم
    conn.execute("DELETE FROM enroll_requests WHERE id=?", (request_id,))
    conn.commit()

    flash("🚫 تم رفض أو إيقاف الطلب", "info")
    return redirect(url_for('admin_enroll_requests'))

@app.route("/course/<int:course_id>/like", methods=["POST"])
@login_required
def like_course(course_id):
    # منطق تسجيل الإعجاب
    return redirect(request.referrer)


# === عرض الملفات المرفوعة (صور / فيديوهات) ===
@app.route('/uploads/<path:filename>')
def uploaded_file(filename):
    # تأمين المسار ضد محاولات ../
    safe_path = os.path.normpath(filename)
    if safe_path.startswith('..'):
        abort(404)
    full_path = os.path.join(app.config['UPLOAD_FOLDER'], safe_path)
    if not os.path.exists(full_path):
        abort(404)
    return send_from_directory(app.config['UPLOAD_FOLDER'], safe_path)

# === صفحة الدورة التفصيلية ===
@app.route('/course/<int:course_id>')
@login_required
def course_page(course_id):
    conn = get_db()
    lang = request.args.get('lang', session.get('lang', 'ar'))

    # جلب بيانات الدورة
    course_row = conn.execute("SELECT * FROM courses WHERE id=?", (course_id,)).fetchone()
    if not course_row:
        flash("❌ لم يتم العثور على الدورة", "error")
        # يفترض وجود مسار '/courses' لصفحة الدورات العامة
        # نستخدم 'landing' كبديل مؤقت
        return redirect(url_for('landing')) 

    # التحقق هل المستخدم مسجل ومقبول في الدورة
    enrollment = conn.execute("""
          SELECT * FROM enrollments
          WHERE user_id=? AND course_id=? AND approved=1
      """, (current_user.id, course_id)).fetchone()

    # جلب الدروس الخاصة بهذه الدورة
    lessons = conn.execute("""
        SELECT l.id,
               CASE WHEN ?='en' THEN l.title_en ELSE l.title_ar END AS title,
               l.position,
               up.completed
        FROM lessons l
        LEFT JOIN user_progress up ON up.lesson_id = l.id AND up.user_id = ?
        WHERE l.course_id = ?
        ORDER BY l.position ASC
    """, (lang, current_user.id, course_id)).fetchall()

    # تحديد حالة التسجيل
    is_enrolled = enrollment is not None

    # تهيئة بيانات الدورة للغة الحالية
    course = {
        'id': course_row['id'],
        'image': course_row['image'],
        'title': course_row['title_en'] if lang == 'en' else course_row['title_ar'],
        'short_desc': course_row['short_desc_en'] if lang == 'en' else course_row['short_desc_ar'],
        'full_desc': course_row['full_desc_en'] if lang == 'en' else course_row['full_desc_ar']
    }

    return render_template(
        'course_page.html',
        course=course,
        lessons=lessons,
        is_enrolled=is_enrolled,
        lang=lang
    )


# === تشغيل التطبيق ===
if __name__ == '__main__':
    # ⚠️ استدعاء الدالة لتهيئة الجداول (بما فيها hero_slides) لمرة واحدة فقط
    #with app.app_context():
        #init_db() 
        
    app.run()
