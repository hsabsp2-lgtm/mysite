from flask import Flask, render_template_string, request, redirect, url_for, session, flash
import sqlite3
import requests
import hashlib

app = Flask(__name__)
app.secret_key = 'smm_panel_super_secure_secret_key_2026_pro'

# تهيئة قاعدة البيانات والجداول الأساسية وتصفير الأرصدة الحالية
def init_db():
    conn = sqlite3.connect('database.db', timeout=10, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS users 
                      (id INTEGER PRIMARY KEY AUTOINCREMENT, email TEXT, username TEXT UNIQUE, password TEXT, balance REAL DEFAULT 0.0, is_admin INTEGER DEFAULT 0)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS services 
                      (id INTEGER PRIMARY KEY AUTOINCREMENT, category TEXT, name TEXT, rate REAL, min_q INTEGER, max_q INTEGER, description TEXT, api_service_id INTEGER DEFAULT 0)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS orders 
                      (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT, service_id INTEGER, link TEXT, quantity INTEGER, status TEXT, api_order_id TEXT)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS settings 
                      (key TEXT PRIMARY KEY, value TEXT)''')
    
    # التحقق من وجود الأعمدة وإضافتها تلقائياً إن لم تكن موجودة لتجنب أخطاء الشاشة البيضاء
    cursor.execute("PRAGMA table_info(users)")
    user_columns = [column[1] for column in cursor.fetchall()]
    if 'email' not in user_columns:
        cursor.execute("ALTER TABLE users ADD COLUMN email TEXT DEFAULT ''")

    cursor.execute("PRAGMA table_info(services)")
    services_columns = [column[1] for column in cursor.fetchall()]
    if 'api_service_id' not in services_columns:
        cursor.execute("ALTER TABLE services ADD COLUMN api_service_id INTEGER DEFAULT 0")

    cursor.execute("PRAGMA table_info(orders)")
    orders_columns = [column[1] for column in cursor.fetchall()]
    if 'api_order_id' not in orders_columns:
        cursor.execute("ALTER TABLE orders ADD COLUMN api_order_id TEXT DEFAULT '0'")

    # تصفير أرصدة جميع المستخدمين الحاليين (عدا المشرف الرئيسي إن أردت، أو الكل بناءً على طلبك)
    # إذا كنت تريد تصفير الجميع بما فيهم المشرف، احذف شرط WHERE is_admin = 0
    cursor.execute("UPDATE users SET balance = 0.0 WHERE is_admin = 0")
        
    conn.commit()
    conn.close()

init_db()

def get_setting(key, default=''):
    conn = sqlite3.connect('database.db', timeout=10, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row and row[0] is not None else default

# القالب المتكامل لواجهة الموقع ولوحة التحكم
TEMPLATE = """
<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ site_title }}</title>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        body { font-family: Tahoma, sans-serif; background: #0f172a; color: #f8fafc; margin: 0; padding: 0; }
        header { background: #1e293b; padding: 15px 20px; display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #334155; flex-wrap: wrap; gap: 10px; position: sticky; top: 0; z-index: 99; }
        .container { max-width: 900px; margin: 20px auto; background: #1e293b; padding: 25px; border-radius: 12px; box-shadow: 0 4px 20px rgba(0,0,0,0.5); }
        
        .menu-toggle-icon { font-size: 22px; cursor: pointer; color: #fff; background: #0f172a; border: 1px solid #334155; padding: 8px 12px; border-radius: 8px; display: inline-flex; align-items: center; justify-content: center; }
        .menu-toggle-icon:hover { background: #3b82f6; border-color: #3b82f6; }

        .sidebar { height: 100%; width: 280px; position: fixed; z-index: 2000; top: 0; right: -280px; background-color: #1e293b; overflow-y: auto; transition: 0.3s ease-in-out; box-shadow: -5px 0 25px rgba(0,0,0,0.8); border-left: 1px solid #334155; visibility: hidden; opacity: 0; }
        .sidebar.active { right: 0; visibility: visible; opacity: 1; }
        .sidebar-header { display: flex; align-items: center; justify-content: space-between; padding: 20px; background: #0f172a; border-bottom: 1px solid #334155; color: #fff; }
        .close-btn { font-size: 22px; cursor: pointer; color: #ef4444; }
        
        .sidebar-menu { list-style: none; padding: 0; margin: 0; }
        .sidebar-menu li a { padding: 14px 20px; display: flex; align-items: center; color: #cbd5e1; text-decoration: none; font-size: 14px; border-bottom: 1px solid #334155; transition: 0.2s; gap: 12px; }
        .sidebar-menu li a:hover { background-color: #0f172a; color: #3b82f6; }
        .sidebar-menu li a i { width: 20px; text-align: center; color: #94a3b8; }

        .sidebar-footer-box { padding: 20px; background: #0f172a; border-top: 1px solid #334155; text-align: center; }
        .balance-badge { background: #f59e0b; color: #000; padding: 6px 15px; border-radius: 20px; font-weight: bold; display: inline-block; margin-bottom: 10px; font-size: 15px; }

        .overlay { position: fixed; display: none; width: 100%; height: 100%; top: 0; left: 0; background: rgba(0,0,0,0.7); z-index: 1500; }
        .overlay.active { display: block; }

        .top-social-bar { display: flex; justify-content: center; gap: 15px; margin-bottom: 20px; flex-wrap: wrap; }
        .social-card { background: #1e293b; border: 1px solid #334155; padding: 10px 20px; border-radius: 12px; display: flex; align-items: center; gap: 10px; color: white; text-decoration: none; font-weight: bold; transition: 0.3s; }
        .social-card:hover { transform: translateY(-2px); border-color: #3b82f6; background: #2563eb; }

        .dashboard-cards { display: flex; gap: 15px; margin-bottom: 20px; flex-wrap: wrap; }
        .stat-card { flex: 1; min-width: 250px; background: #1e293b; border: 1px solid #334155; padding: 20px; border-radius: 16px; display: flex; justify-content: space-between; align-items: center; }
        .stat-card .info h3 { margin: 0; font-size: 22px; color: #f8fafc; }
        .stat-card .info p { margin: 5px 0 0 0; color: #94a3b8; font-size: 14px; }
        .stat-card .icon { font-size: 30px; background: #0f172a; padding: 12px; border-radius: 12px; border: 1px solid #334155; }

        .quick-actions { display: flex; gap: 10px; margin-bottom: 25px; justify-content: center; flex-wrap: wrap; }
        .action-btn { background: #1e293b; border: 1px solid #334155; padding: 12px 20px; border-radius: 12px; color: white; text-decoration: none; font-size: 14px; font-weight: bold; display: flex; align-items: center; gap: 8px; transition: 0.3s; }
        .action-btn:hover { background: #3b82f6; border-color: #3b82f6; }

        .instructions-box { background: #0f172a; border: 1px solid #334155; border-right: 4px solid #eab308; padding: 20px; border-radius: 10px; margin-top: 30px; line-height: 1.8; font-size: 14px; white-space: pre-line; }
        .instructions-box h3 { color: #facc15; margin-top: 0; display: flex; align-items: center; gap: 8px; font-size: 18px; }

        input, select, textarea, button { width: 100%; padding: 12px; margin: 8px 0; background: #0f172a; border: 1px solid #334155; color: white; border-radius: 6px; box-sizing: border-box; font-family: Tahoma, sans-serif; }
        textarea { resize: vertical; height: 100px; }
        button { background: #3b82f6; border: none; font-weight: bold; cursor: pointer; transition: 0.3s; }
        button:hover { background: #2563eb; }
        .alert { padding: 12px; margin-bottom: 15px; border-radius: 6px; background: #ef4444; color: white; text-align: center; }
        .success { background: #22c55e; }
        a { color: #60a5fa; text-decoration: none; }
        
        .platforms { display: flex; gap: 8px; justify-content: center; margin: 15px 0; flex-wrap: wrap; }
        .plat-btn { background: #0f172a; border: 1px solid #475569; padding: 9px 14px; border-radius: 8px; color: white; text-decoration: none; font-size: 13px; display: flex; align-items: center; gap: 6px; transition: 0.2s; }
        .plat-btn:hover, .plat-btn.active { background: #3b82f6; border-color: #3b82f6; }
        
        .desc-box { background: #0f172a; border: 1px solid #334155; padding: 15px; border-radius: 6px; margin: 10px 0; font-size: 13px; color: #cbd5e1; white-space: pre-line; }
        table { width: 100%; border-collapse: collapse; margin-top: 15px; }
        th, td { border: 1px solid #334155; padding: 10px; text-align: center; font-size: 13px; }
        th { background: #1e293b; }
        .nav-links { display: flex; gap: 15px; align-items: center; flex-wrap: wrap; }
        .info-card { background: #0f172a; border: 1px solid #334155; padding: 15px 20px; border-radius: 8px; margin-bottom: 12px; display: flex; justify-content: space-between; align-items: center; }
        
        .copy-username-badge {
            background: #0f172a;
            border: 1px dashed #3b82f6;
            color: #38bdf8;
            padding: 5px 12px;
            border-radius: 6px;
            font-size: 13px;
            cursor: pointer;
            display: inline-flex;
            align-items: center;
            gap: 6px;
            transition: 0.2s;
        }
        .copy-username-badge:hover {
            background: #3b82f6;
            color: #fff;
            border-style: solid;
        }
    </style>
</head>
<body>

    <header>
        <div style="display: flex; align-items: center; gap: 15px;">
            {% if session.get('user') %}
                <div class="menu-toggle-icon" id="menuToggle">
                    <i class="fas fa-bars"></i>
                </div>
            {% endif %}
            <h2>{{ site_brand }}</h2>
        </div>
        
        <div class="nav-links">
            {% if session.get('user') %}
                <div class="copy-username-badge" onclick="navigator.clipboard.writeText('{{ session.get(\'user\') }}'); alert('تم نسخ اسم المستخدم: {{ session.get(\'user\') }}');" title="اضغط للنسخ">
                    <i class="fas fa-user"></i> <span>{{ session.get('user') }}</span> <i class="fas fa-copy" style="font-size: 11px; opacity: 0.7;"></i>
                </div>
            {% endif %}

            {% if session.get('is_admin') == 1 %}
                <a href="/admin" style="background: #eab308; color: black; padding: 6px 10px; border-radius: 6px; font-weight: bold;">⚙️ لوحة المشرف</a>
            {% endif %}
            {% if not session.get('user') %}
                <a href="/login">دخول</a> | <a href="/register">حساب جديد</a>
            {% endif %}
        </div>
    </header>

    {% if session.get('user') %}
    <div class="overlay" id="overlay"></div>

    <div class="sidebar" id="sidebar">
        <div class="sidebar-header">
            <h3>قائمة التنقل</h3>
            <span class="close-btn" id="closeBtn">&times;</span>
        </div>

        <ul class="sidebar-menu">
            {% if nav_text_1 %}<li><a href="{{ nav_link_1 }}"><i class="{{ nav_icon_1 }}"></i> {{ nav_text_1 }}</a></li>{% endif %}
            {% if nav_text_2 %}<li><a href="{{ nav_link_2 }}"><i class="{{ nav_icon_2 }}"></i> {{ nav_text_2 }}</a></li>{% endif %}
            {% if nav_text_3 %}<li><a href="{{ nav_link_3 }}"><i class="{{ nav_icon_3 }}"></i> {{ nav_text_3 }}</a></li>{% endif %}
            {% if nav_text_4 %}<li><a href="{{ nav_link_4 }}"><i class="{{ nav_icon_4 }}"></i> {{ nav_text_4 }}</a></li>{% endif %}
            {% if nav_text_5 %}<li><a href="{{ nav_link_5 }}"><i class="{{ nav_icon_5 }}"></i> {{ nav_text_5 }}</a></li>{% endif %}
            {% if nav_text_6 %}<li><a href="{{ nav_link_6 }}"><i class="{{ nav_icon_6 }}"></i> {{ nav_text_6 }}</a></li>{% endif %}
            {% if nav_text_7 %}<li><a href="{{ nav_link_7 }}"><i class="{{ nav_icon_7 }}"></i> {{ nav_text_7 }}</a></li>{% endif %}
            {% if nav_text_8 %}<li><a href="{{ nav_link_8 }}"><i class="{{ nav_icon_8 }}"></i> {{ nav_text_8 }}</a></li>{% endif %}
            
            <li><a href="/api-key-page"><i class="fas fa-code" style="color: #60a5fa;"></i> مفتاح ربط الـ API</a></li>
            <li><a href="/logout" style="color: #ef4444;"><i class="fas fa-sign-out-alt"></i> تسجيل خروج</a></li>
        </ul>

        <div class="sidebar-footer-box">
            <div class="balance-badge">${{ "%.4f"|format(balance) }}</div>
            <div style="font-size: 13px; color: #94a3b8; margin-top: 5px;">المعرف: {{ session.get('user') }}</div>
        </div>
    </div>

    <script>
        const menuToggle = document.getElementById('menuToggle');
        const sidebar = document.getElementById('sidebar');
        const closeBtn = document.getElementById('closeBtn');
        const overlay = document.getElementById('overlay');
        
        function toggleMenu() {
            sidebar.classList.toggle('active');
            overlay.classList.toggle('active');
        }

        if(menuToggle) {
            menuToggle.addEventListener('click', toggleMenu);
            closeBtn.addEventListener('click', toggleMenu);
            overlay.addEventListener('click', toggleMenu);
        }

        document.querySelectorAll('a').forEach(link => {
            link.addEventListener('click', () => {
                if(sidebar) sidebar.classList.remove('active');
                if(overlay) overlay.classList.remove('active');
            });
        });
    </script>
    {% endif %}

    <div class="container">
        {% with messages = get_flashed_messages(with_categories=true) %}
            {% if messages %}
                {% for cat, msg in messages %}
                    <div class="alert {% if cat == 'success' %}success{% endif %}">{{ msg }}</div>
                {% endfor %}
            {% endif %}
        {% endwith %}

        <div class="top-social-bar">
            <a href="https://wa.me/{{ whatsapp_link }}" target="_blank" class="social-card"><span>🟢</span> واتساب</a>
            <a href="https://t.me/{{ telegram_link }}" target="_blank" class="social-card"><span>✈️</span> تليجرام</a>
            <a href="{{ auto_pay_link }}" target="_blank" class="social-card" style="border-color: #22c55e;"><span>💳</span> شحن تلقائي</a>
        </div>

        {% if page == 'home' %}
            {% if session.get('user') %}
                <div class="dashboard-cards">
                    <div class="stat-card">
                        <div class="info">
                            <h3>${{ "%.4f"|format(balance) }}</h3>
                            <p>رصيدك الحالي</p>
                        </div>
                        <div class="icon">💰</div>
                    </div>
                    <div class="stat-card">
                        <div class="info">
                            <h3>{{ completed_orders_count }}</h3>
                            <p>طلبات مكتملة</p>
                        </div>
                        <div class="icon">📊</div>
                    </div>
                </div>

                <div class="quick-actions">
                    <a href="/orders" class="action-btn">📜 سجل الطلبات</a>
                    <a href="{{ auto_pay_link }}" target="_blank" class="action-btn">💳 شحن الرصيد</a>
                    <a href="https://wa.me/{{ whatsapp_link }}" target="_blank" class="action-btn">🎧 الدعم الفني</a>
                </div>

                <h3 style="text-align: center; margin-top: 10px;">تقديم طلب رشق تلقائي</h3>
                
                <div class="platforms">
                    <a href="/?plat=free" class="plat-btn {% if plat == 'free' %}active{% endif %}" style="background: #22c55e; border-color: #22c55e;">🎁 خدمات مجانية</a>
                    <a href="/?plat=instagram" class="plat-btn {% if plat == 'instagram' %}active{% endif %}">📸 انستغرام</a>
                    <a href="/?plat=tiktok" class="plat-btn {% if plat == 'tiktok' %}active{% endif %}">🎵 تيك توك</a>
                    <a href="/?plat=snapchat" class="plat-btn {% if plat == 'snapchat' %}active{% endif %}">👻 سناب شات</a>
                    <a href="/?plat=telegram" class="plat-btn {% if plat == 'telegram' %}active{% endif %}">✈️ تليجرام</a>
                    <a href="/?plat=youtube" class="plat-btn {% if plat == 'youtube' %}active{% endif %}">▶️ يوتيوب</a>
                    <a href="/?plat=facebook" class="plat-btn {% if plat == 'facebook' %}active{% endif %}">📘 فيسبوك</a>
                    <a href="/?plat=whatsapp" class="plat-btn {% if plat == 'whatsapp' %}active{% endif %}">🟢 واتساب</a>
                    <a href="/?plat=likee" class="plat-btn {% if plat == 'likee' %}active{% endif %}">💛 لايكي</a>
                    <a href="/?plat=twitter" class="plat-btn {% if plat == 'twitter' %}active{% endif %}">❌ تويتر / X</a>
                    <a href="/?plat=packages" class="plat-btn {% if plat == 'packages' %}active{% endif %}">📦 بكجات متنوعة</a>
                    <a href="/?plat=services" class="plat-btn {% if plat == 'services' %}active{% endif %}">🔥 خدمات متنوعة</a>
                </div>

                <form method="POST" action="/order">
                    <input type="hidden" name="plat" value="{{ plat }}">
                    
                    <label>اختر الخدمة:</label>
                    <select name="service_id" id="serviceSelect" required onchange="updateServiceDetails()">
                        <option value="" data-min="0" data-max="0" data-rate="0" data-desc="">-- اضغط لاختيار الخدمة --</option>
                        {% for s in services %}
                            <option value="{{ s[0] }}" data-min="{{ s[4] }}" data-max="{{ s[5] }}" data-rate="{{ s[3] }}" data-desc="{{ s[6] }}">
                                [{{ s[0] }}] {{ s[2] }} - ${{ s[3] }} لكل 1000
                            </option>
                        {% endfor %}
                    </select>

                    <label>الوصف وتفاصيل الضمان:</label>
                    <div class="desc-box" id="serviceDesc">اختر خدمة لعرض التفاصيل هنا...</div>

                    <label>الرابط المستهدف:</label>
                    <input type="url" name="link" required placeholder="https://...">

                    <label>الكمية المطلوبة:</label>
                    <input type="number" name="quantity" id="qtyInput" required placeholder="أدخل الكمية" oninput="calculateTotal()">
                    <div style="display: flex; justify-content: space-between; font-size: 12px; color: #94a3b8; margin-top: -5px;">
                        <span id="limitsInfo">الحد الأدنى: 0 | الحد الأقصى: 0</span>
                        <span id="totalCost" style="color: #60a5fa; font-weight: bold;">التكلفة الإجمالية: $0.00</span>
                    </div>

                    <button type="submit" style="margin-top: 15px; background: #22c55e;">إرسال الطلب وتنفيذ تلقائي 🚀</button>
                </form>

                <script>
                    let currentRate = 0;
                    function updateServiceDetails() {
                        var select = document.getElementById('serviceSelect');
                        var option = select.options[select.selectedIndex];
                        var desc = option.getAttribute('data-desc') || 'لا يوجد وصف.';
                        var min = option.getAttribute('data-min') || '0';
                        var max = option.getAttribute('data-max') || '0';
                        currentRate = parseFloat(option.getAttribute('data-rate')) || 0;
                        
                        document.getElementById('serviceDesc').innerText = desc;
                        document.getElementById('limitsInfo').innerText = 'الحد الأدنى: ' + min + ' | الحد الأقصى: ' + max;
                        document.getElementById('qtyInput').min = min;
                        document.getElementById('qtyInput').max = max;
                        calculateTotal();
                    }
                    function calculateTotal() {
                        var qty = document.getElementById('qtyInput').value;
                        var total = (qty * currentRate) / 1000;
                        document.getElementById('totalCost').innerText = 'التكلفة الإجمالية: $' + total.toFixed(4);
                    }
                </script>

                <div class="instructions-box">
                    <h3>⚠️ تعليمات وشروط مهمة قبل الطلب</h3>
                    <div>{{ site_instructions | safe }}</div>
                </div>

            {% else %}
                <p style="text-align: center; padding: 20px;">الرجاء <a href="/login">تسجيل الدخول</a> أو <a href="/register">إنشاء حساب جديد</a> للوصول لخدمات الرشق.</p>
            {% endif %}

        {% elif page == 'account' %}
            <h2>معلومات الحساب الشخصي</h2>
            <p style="color: #94a3b8; margin-bottom: 20px;">هنا يمكنك الاطلاع على كافة معلومات حسابك المسجلة لدينا بشكل تلقائي.</p>
            
            <div class="info-card">
                <span>اسم المستخدم:</span>
                <b style="color: #38bdf8;">{{ user_info[2] }}</b>
            </div>
            <div class="info-card">
                <span>البريد الإلكتروني:</span>
                <b style="color: #38bdf8;">{{ user_info[1] if user_info[1] else 'غير متوفر' }}</b>
            </div>
            <div class="info-card">
                <span>كلمة المرور المسجلة:</span>
                <b style="color: #facc15;">{{ user_info[3] }}</b>
            </div>
            <div class="info-card">
                <span>الرصيد الحالي:</span>
                <b style="color: #22c55e;">${{ "%.4f"|format(user_info[4]) }}</b>
            </div>
            <div class="info-card">
                <span>نوع الحساب:</span>
                <b>{{ 'مشرف ⚙️ (Admin)' if user_info[5] == 1 else 'مستخدم عادي 👤' }}</b>
            </div>
            
            <p style="text-align: center; margin-top: 25px;"><a href="/">⬅ العودة للرئيسية</a></p>

        {% elif page == 'api_key_page' %}
            <h2>🔗 رابط ومفتاح ربط الـ API الخاص بك</h2>
            <p style="color: #94a3b8; margin-bottom: 20px;">يمكنك إعطاء هذه البيانات لبوت التليجرام الخاص بك لكي يتمكن من الرشق تلقائياً عبر حسابك وموقعك.</p>
            
            <div style="background: #0f172a; border: 1px solid #334155; padding: 20px; border-radius: 8px; margin-bottom: 15px;">
                <label style="color: #38bdf8; font-weight: bold;">رابط موقعك (API URL):</label>
                <input type="text" value="{{ site_custom_url if site_custom_url else site_api_url }}" readonly style="background: #1e293b; color: #facc15; font-family: monospace;" onclick="this.select(); document.execCommand('copy'); alert('تم نسخ رابط الموقع!');">
                <span style="font-size: 11px; color: #94a3b8;">اضغط داخل الحقل للنسخ السريع</span>
            </div>

            <div style="background: #0f172a; border: 1px solid #334155; padding: 20px; border-radius: 8px; margin-bottom: 20px;">
                <label style="color: #22c55e; font-weight: bold;">مفتاح الـ API الشخصي الخاص بك (API Key):</label>
                <input type="text" value="{{ user_api_key }}" readonly style="background: #1e293b; color: #22c55e; font-family: monospace;" onclick="this.select(); document.execCommand('copy'); alert('تم نسخ مفتاح الـ API!');">
                <span style="font-size: 11px; color: #94a3b8;">اضغط داخل الحقل للنسخ السريع</span>
            </div>

            <p style="text-align: center; margin-top: 25px;"><a href="/">⬅ العودة للرئيسية</a></p>

        {% elif page == 'orders' %}
            <h2>سجل طلباتك السابقة</h2>
            <table>
                <tr>
                    <th>رقم الطلب</th>
                    <th>الخدمة</th>
                    <th>الرابط</th>
                    <th>الكمية</th>
                    <th>الحالة</th>
                </tr>
                {% for o in my_orders %}
                <tr>
                    <td>#{{ o[0] }}</td>
                    <td>{{ o[1] }}</td>
                    <td style="max-width: 150px; overflow: hidden; text-overflow: ellipsis;"><a href="{{ o[2] }}" target="_blank">{{ o[2] }}</a></td>
                    <td>{{ o[3] }}</td>
                    <td><b style="color: {% if o[4] == 'Completed' or o[4] == 'مكتمل' %}#22c55e{% elif o[4] == 'Processing' or o[4] == 'قيد التنفيذ' %}#eab308{% else %}#60a5fa{% endif %};">{{ o[4] }}</b></td>
                </tr>
                {% endfor %}
            </table>
            <p style="text-align: center; margin-top: 20px;"><a href="/">⬅ العودة للرئيسية</a></p>

        {% elif page == 'terms' %}
            <h2>شروط الاستخدام والأحكام</h2>
            <div style="background: #0f172a; border: 1px solid #334155; padding: 25px; border-radius: 8px; line-height: 2; font-size: 16px; color: #e2e8f0; white-space: pre-line;">
                {{ terms_text }}
            </div>
            <p style="text-align: center; margin-top: 25px;"><a href="/">⬅ العودة للرئيسية</a></p>

        {% elif page == 'admin' %}
            <h2>لوحة التحكم والإدارة المركزية</h2>
            
            <form method="POST" action="/admin/save_site_settings" style="background: #0f172a; padding: 15px; border-radius: 8px; margin-bottom: 20px; border-right: 4px solid #f97316;">
                <h4 style="color: #fb923c; margin-top: 0;">🌐 إعدادات اسم وعنوان ورابط الموقع</h4>
                <label>عنوان الموقع الرئيسي (Title):</label>
                <input type="text" name="site_title" value="{{ site_title }}" placeholder="مثال: FA1S SMM Panel - لوحة الخدمات الاحترافية">
                <label>اسم العلامة التجارية البارز (Brand):</label>
                <input type="text" name="site_brand" value="{{ site_brand }}" placeholder="مثال: 🚀 FA1S Panel">
                <label>رابط الموقع الحالي (Domain / URL):</label>
                <input type="text" name="site_custom_url" value="{{ site_custom_url }}" placeholder="https://yourdomain.com/">
                <button type="submit" style="background: #f97316; margin-top: 10px;">💾 حفظ إعدادات العنوان والموقع</button>
            </form>

            <form method="POST" action="/admin/save_api_settings" style="background: #0f172a; padding: 15px; border-radius: 8px; margin-bottom: 20px; border-right: 4px solid #22c55e;">
                <h4 style="color: #22c55e; margin-top: 0;">🔗 إعدادات ربط الموقع ومفتاح الـ API الخارجي</h4>
                <label>رابط منصة الـ API الأساسي:</label>
                <input type="text" name="api_url" value="{{ api_url }}" placeholder="https://api-provider.com/api/v2">
                <label>مفتاح الـ API (Key):</label>
                <input type="text" name="api_key" value="{{ api_key }}" placeholder="أدخل مفتاح المصادقة الخاص بالـ API...">
                <button type="submit" style="background: #22c55e; margin-top: 10px;">💾 حفظ إعدادات الربط والمفتاح</button>
            </form>

            <form method="POST" action="/admin/add_service" style="background: #0f172a; padding: 15px; border-radius: 8px; margin-bottom: 20px; border-right: 4px solid #3b82f6;">
                <h4 style="color: #38bdf8; margin-top: 0;">➕ إضافة خدمة رشق جديدة (تيك توك، انستغرام، إلخ)</h4>
                <div style="display: flex; gap: 10px;">
                    <div style="flex: 1;">
                        <label>القسم / المنصة:</label>
                        <select name="category" required>
                            <option value="free">🎁 خدمات مجانية</option>
                            <option value="instagram">📸 انستغرام</option>
                            <option value="tiktok">🎵 تيك توك</option>
                            <option value="snapchat">👻 سناب شات</option>
                            <option value="telegram">✈️ تليجرام</option>
                            <option value="youtube">▶️ يوتيوب</option>
                            <option value="facebook">📘 فيسبوك</option>
                            <option value="whatsapp">🟢 واتساب</option>
                            <option value="likee">💛 لايكي</option>
                            <option value="twitter">❌ تويتر / X</option>
                            <option value="packages">📦 بكجات متنوعة</option>
                            <option value="services">🔥 خدمات متنوعة</option>
                        </select>
                    </div>
                    <div style="flex: 1;">
                        <label>رقم الخدمة بالـ API الخارجي:</label>
                        <input type="number" name="api_service_id" value="0" placeholder="0 إذا كانت يدوية">
                    </div>
                </div>
                <label>اسم الخدمة:</label>
                <input type="text" name="name" required placeholder="مثال: متابعين تيك توك ضمان 30 يوم">
                <div style="display: flex; gap: 10px;">
                    <div style="flex: 1;"><label>السعر لكل 1000 ($):</label><input type="number" step="0.0001" name="rate" required placeholder="مثال: 1.5"></div>
                    <div style="flex: 1;"><label>الحد الأدنى:</label><input type="number" name="min_q" value="10" required></div>
                    <div style="flex: 1;"><label>الحد الأقصى:</label><input type="number" name="max_q" value="10000" required></div>
                </div>
                <label>وصف الخدمة والتفاصيل:</label>
                <textarea name="description" placeholder="اكتب تفاصيل الخدمة والضمان هنا..."></textarea>
                <button type="submit" style="background: #3b82f6; margin-top: 10px;">🚀 إضافة الخدمة للبوت</button>
            </form>

            <form method="POST" action="/admin/save_sidebar_full" style="background: #0f172a; padding: 15px; border-radius: 8px; margin-bottom: 20px; border-right: 4px solid #a855f7;">
                <h4 style="color: #c084fc; margin-top: 0;">🧭 إدارة وتغيير عناصر قائمة التنقل بالكامل (الأسماء، الروابط، الأيقونات)</h4>
                <p style="font-size: 12px; color: #94a3b8; margin-top: -5px;">يمكنك هنا تغيير أي زر في القائمة الجانبية بالكامل أو تركه فارغاً ليختفي.</p>
                
                {% for i in range(1, 9) %}
                <div style="background: #1e293b; padding: 10px; border-radius: 6px; margin-bottom: 10px; border: 1px solid #334155;">
                    <div style="font-weight: bold; color: #38bdf8; margin-bottom: 5px; font-size: 13px;">الزر رقم ({{ i }})</div>
                    <div style="display: flex; gap: 8px; flex-wrap: wrap;">
                        <input type="text" name="nav_text_{{ i }}" value="{{ nav_data['nav_text_' ~ i] }}" placeholder="اسم الزر (مثل: حسابي)" style="flex: 1; min-width: 120px;">
                        <input type="text" name="nav_link_{{ i }}" value="{{ nav_data['nav_link_' ~ i] }}" placeholder="الرابط (مثل: /account أو https://...)" style="flex: 1.5; min-width: 150px;">
                        <input type="text" name="nav_icon_{{ i }}" value="{{ nav_data['nav_icon_' ~ i] }}" placeholder="أيقونة FontAwesome (مثل: fas fa-user)" style="flex: 1; min-width: 120px;">
                    </div>
                </div>
                {% endfor %}

                <button type="submit" style="background: #a855f7; margin-top: 10px;">💾 حفظ وتحديث قائمة التنقل بالكامل</button>
            </form>

            <form method="POST" action="/admin/save_instructions" style="background: #0f172a; padding: 15px; border-radius: 8px; margin-bottom: 20px; border-right: 4px solid #eab308;">
                <h4 style="color: #facc15; margin-top: 0;">⚠️ تعديل تعليمات وشروط الموقع</h4>
                <textarea name="site_instructions" required>{{ site_instructions }}</textarea>
                <button type="submit" style="background: #eab308; color: black; margin-top: 10px;">💾 حفظ التعليمات</button>
            </form>

            <form method="POST" action="/admin/manage_balance" style="background: #0f172a; padding: 15px; border-radius: 8px; margin-bottom: 20px; border-right: 4px solid #3b82f6;">
                <h4 style="color: #38bdf8; margin-top: 0;">💳 إدارة رصيد مستخدم (حصري للمشرف)</h4>
                <label>اسم المستخدم الدقيق:</label>
                <input type="text" name="username" required placeholder="اكتب اسم المستخدم هنا...">
                <label>المبلغ ($):</label>
                <input type="number" step="0.01" name="amount" required placeholder="مثال: 5.0">
                <div style="display: flex; gap: 10px; margin-top: 10px;">
                    <button type="submit" name="action_type" value="add" style="background: #22c55e; flex: 1;">➕ إضافة رصيد</button>
                    <button type="submit" name="action_type" value="subtract" style="background: #ef4444; flex: 1;">➖ سحب رصيد</button>
                </div>
            </form>

            <h4 style="margin-top: 25px;">إدارة الخدمات الحالية:</h4>
            <table>
                <tr>
                    <th>الرقم</th>
                    <th>التطبيق / القسم</th>
                    <th>الاسم</th>
                    <th>السعر</th>
                    <th>تحكم</th>
                </tr>
                {% for s in all_services %}
                <tr>
                    <td>{{ s[0] }}</td>
                    <td>{{ s[1] }}</td>
                    <td>{{ s[2] }}</td>
                    <td>${{ s[3] }}</td>
                    <td><a href="/admin/delete/{{ s[0] }}" style="color: #ef4444;">حذف</a></td>
                </tr>
                {% endfor %}
            </table>

            <h4 style="margin-top: 35px; color: #38bdf8; border-top: 1px solid #334155; padding-top: 20px;">👥 قائمة جميع الأعضاء المسجلين ({{ all_users|length }})</h4>
            <table>
                <tr>
                    <th>المعرف (ID)</th>
                    <th>اسم المستخدم</th>
                    <th>البريد الإلكتروني</th>
                    <th>الرصيد الحالي</th>
                    <th>نوع الحساب</th>
                </tr>
                {% for u in all_users %}
                <tr>
                    <td>#{{ u[0] }}</td>
                    <td><b style="color: #38bdf8;">{{ u[2] }}</b></td>
                    <td>{{ u[1] if u[1] else 'بدون' }}</td>
                    <td style="color: #22c55e;">${{ "%.2f"|format(u[3]) }}</td>
                    <td>{{ 'مشرف ⚙️' if u[4] == 1 else 'عضو 👤' }}</td>
                </tr>
                {% endfor %}
            </table>

            <p style="text-align: center; margin-top: 30px;"><a href="/">⬅ العودة للرئيسية</a></p>

        {% elif page == 'login' %}
            <h2>تسجيل الدخول</h2>
            <form method="POST">
                <input type="text" name="username" placeholder="اسم المستخدم" required>
                <input type="password" name="password" placeholder="كلمة المرور" required>
                <button type="submit">دخول</button>
            </form>
            <p style="text-align: center; margin-top: 10px;">ليس لديك حساب؟ <a href="/register">انشئ حساباً جديداً</a></p>

        {% elif page == 'register' %}
            <h2>إنشاء حساب جديد</h2>
            <form method="POST">
                <label>البريد الإلكتروني:</label>
                <input type="email" name="email" placeholder="example@gmail.com" required>
                <label>اسم المستخدم:</label>
                <input type="text" name="username" placeholder="username" required>
                <label>كلمة المرور:</label>
                <input type="password" name="password" placeholder="كلمة المرور الآمنة" required>
                <button type="submit" style="background: #22c55e; margin-top: 15px;">إنشاء الحساب والتسجيل 🚀</button>
            </form>
            <p style="text-align: center; margin-top: 10px;">لديك حساب بالفعل؟ <a href="/login">تسجيل الدخول</a></p>
        {% endif %}
    </div>
</body>
</html>
"""

def get_sidebar_settings():
    defaults = {
        1: ('حسابي ومعلوماتي', '/account', 'fas fa-user-circle'),
        2: ('طلب جديد', '/', 'fas fa-plus-circle'),
        3: ('سجل الطلبات', '/orders', 'fas fa-history'),
        4: ('برامج تيك توك وانستا', 'https://t.me/', 'fas fa-store'),
        5: ('شحن الرصيد', 'https://t.me/', 'fas fa-credit-card'),
        6: ('الدعم الفني', 'https://t.me/nsnn1', 'fas fa-headset'),
        7: ('شروط الاستخدام', '/terms', 'fas fa-file-alt'),
        8: ('', '', '')
    }
    
    data = {}
    for i in range(1, 9):
        data[f'nav_text_{i}'] = get_setting(f'nav_text_{i}', defaults[i][0])
        data[f'nav_link_{i}'] = get_setting(f'nav_link_{i}', defaults[i][1])
        data[f'nav_icon_{i}'] = get_setting(f'nav_icon_{i}', defaults[i][2])
    return data

@app.route('/')
def home():
    balance = 0.0
    completed_orders_count = 0
    services = []
    user_api_key = ""
    plat = request.args.get('plat', 'free')
    
    conn = sqlite3.connect('database.db', timeout=10, check_same_thread=False)
    cursor = conn.cursor()
    
    if 'user' in session:
        cursor.execute("SELECT balance, password FROM users WHERE username = ?", (session['user'],))
        row = cursor.fetchone()
        if row:
            balance = row[0]
            user_api_key = hashlib.md5((session['user'] + str(row[1])).encode()).hexdigest()
            
        cursor.execute("SELECT COUNT(*) FROM orders WHERE username = ? AND (status = 'Completed' OR status = 'مكتمل')", (session['user'],))
        c_row = cursor.fetchone()
        if c_row:
            completed_orders_count = c_row[0]
        
        cursor.execute("SELECT id, category, name, rate, min_q, max_q, description, api_service_id FROM services WHERE category = ?", (plat,))
        services = cursor.fetchall()
        
    conn.close()
        
    whatsapp_link = get_setting('whatsapp_link', '9647800000000')
    telegram_link = get_setting('telegram_link', 'nsnn1')
    auto_pay_link = get_setting('auto_pay_link', 'https://t.me/')
    site_title = get_setting('site_title', 'FA1S SMM Panel - لوحة الخدمات الاحترافية')
    site_brand = get_setting('site_brand', '🚀 FA1S Panel')
    site_instructions = get_setting('site_instructions', '• تأكد من أن الحساب عام وليس خاص.\n• لا تقم بطلب نفس الرابط مرتين لنفس الخدمة حتى ينتهي الطلب الأول.')
    
    nav_data = get_sidebar_settings()
        
    return render_template_string(TEMPLATE, page='home', balance=balance, completed_orders_count=completed_orders_count, 
                                  plat=plat, services=services,
                                  whatsapp_link=whatsapp_link, telegram_link=telegram_link, 
                                  auto_pay_link=auto_pay_link, site_title=site_title, site_brand=site_brand, site_instructions=site_instructions, 
                                  user_api_key=user_api_key, nav_data=nav_data, **nav_data)

@app.route('/account')
def account():
    if 'user' not in session:
        return redirect(url_for('login'))
        
    conn = sqlite3.connect('database.db', timeout=10, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("SELECT id, email, username, password, balance, is_admin FROM users WHERE username = ?", (session['user'],))
    user_info = cursor.fetchone()
    
    balance = user_info[4] if user_info else 0.0
    user_api_key = hashlib.md5((session['user'] + str(user_info[3])).encode()).hexdigest() if user_info else ""
    conn.close()
    
    site_title = get_setting('site_title', 'FA1S SMM Panel')
    site_brand = get_setting('site_brand', '🚀 FA1S Panel')
    whatsapp_link = get_setting('whatsapp_link', '9647800000000')
    telegram_link = get_setting('telegram_link', 'nsnn1')
    auto_pay_link = get_setting('auto_pay_link', 'https://t.me/')
    
    nav_data = get_sidebar_settings()
    
    return render_template_string(TEMPLATE, page='account', user_info=user_info, balance=balance, user_api_key=user_api_key, 
                                  site_title=site_title, site_brand=site_brand, whatsapp_link=whatsapp_link, 
                                  telegram_link=telegram_link, auto_pay_link=auto_pay_link, nav_data=nav_data, **nav_data)

@app.route('/api-key-page')
def api_key_page():
    if 'user' not in session:
        return redirect(url_for('login'))
        
    conn = sqlite3.connect('database.db', timeout=10, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("SELECT password, balance FROM users WHERE username = ?", (session['user'],))
    user = cursor.fetchone()
    conn.close()
    
    balance = user[1] if user else 0.0
    user_api_key = hashlib.md5((session['user'] + str(user[0])).encode()).hexdigest() if user else ""
    
    site_api_url = request.host_url.rstrip('/') + '/'
    site_custom_url = get_setting('site_custom_url', site_api_url)
    
    site_title = get_setting('site_title', 'FA1S SMM Panel')
    site_brand = get_setting('site_brand', '🚀 FA1S Panel')
    whatsapp_link = get_setting('whatsapp_link', '9647800000000')
    telegram_link = get_setting('telegram_link', 'nsnn1')
    auto_pay_link = get_setting('auto_pay_link', 'https://t.me/')
    
    nav_data = get_sidebar_settings()
    
    return render_template_string(TEMPLATE, page='api_key_page', user_api_key=user_api_key, site_api_url=site_api_url, site_custom_url=site_custom_url,
                                  balance=balance, site_title=site_title, site_brand=site_brand, 
                                  whatsapp_link=whatsapp_link, telegram_link=telegram_link, 
                                  auto_pay_link=auto_pay_link, nav_data=nav_data, **nav_data)

@app.route('/orders')
def orders():
    if 'user' not in session:
        return redirect(url_for('login'))
        
    conn = sqlite3.connect('database.db', timeout=10, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("SELECT o.id, s.name, o.link, o.quantity, o.status FROM orders o JOIN services s ON o.service_id = s.id WHERE o.username = ? ORDER BY o.id DESC", (session['user'],))
    my_orders = cursor.fetchall()
    
    cursor.execute("SELECT balance, password FROM users WHERE username = ?", (session['user'],))
    row = cursor.fetchone()
    balance = row[0] if row else 0.0
    user_api_key = hashlib.md5((session['user'] + str(row[1])).encode()).hexdigest() if row else ""
    conn.close()
    
    site_title = get_setting('site_title', 'FA1S SMM Panel - لوحة الخدمات الاحترافية')
    site_brand = get_setting('site_brand', '🚀 FA1S Panel')
    whatsapp_link = get_setting('whatsapp_link', '9647800000000')
    telegram_link = get_setting('telegram_link', 'nsnn1')
    auto_pay_link = get_setting('auto_pay_link', 'https://t.me/')
    
    nav_data = get_sidebar_settings()
    
    return render_template_string(TEMPLATE, page='orders', my_orders=my_orders, balance=balance, user_api_key=user_api_key, site_title=site_title, site_brand=site_brand,
                                  whatsapp_link=whatsapp_link, telegram_link=telegram_link, auto_pay_link=auto_pay_link, nav_data=nav_data, **nav_data)

@app.route('/terms')
def terms():
    site_title = get_setting('site_title', 'FA1S SMM Panel')
    site_brand = get_setting('site_brand', '🚀 FA1S Panel')
    terms_text = get_setting('terms_text', 'شروط الاستخدام الأساسية.')
    
    balance = 0.0
    user_api_key = ""
    if 'user' in session:
        conn = sqlite3.connect('database.db', timeout=10, check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute("SELECT balance, password FROM users WHERE username = ?", (session['user'],))
        row = cursor.fetchone()
        if row:
            balance = row[0]
            user_api_key = hashlib.md5((session['user'] + str(row[1])).encode()).hexdigest()
        conn.close()

    whatsapp_link = get_setting('whatsapp_link', '9647800000000')
    telegram_link = get_setting('telegram_link', 'nsnn1')
    auto_pay_link = get_setting('auto_pay_link', 'https://t.me/')
    nav_data = get_sidebar_settings()
    
    return render_template_string(TEMPLATE, page='terms', terms_text=terms_text, site_title=site_title, site_brand=site_brand,
                                  balance=balance, user_api_key=user_api_key, whatsapp_link=whatsapp_link, 
                                  telegram_link=telegram_link, auto_pay_link=auto_pay_link, nav_data=nav_data, **nav_data)

@app.route('/admin')
def admin():
    if session.get('is_admin') != 1:
        flash('غير مسموح لك بالدخول، يجب أن تكون مشرفاً', 'error')
        return redirect(url_for('home'))
        
    conn = sqlite3.connect('database.db', timeout=10, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("SELECT id, category, name, rate, min_q, max_q, description, api_service_id FROM services")
    all_services = cursor.fetchall()
    
    cursor.execute("SELECT id, email, username, balance, is_admin FROM users ORDER BY id DESC")
    all_users = cursor.fetchall()
    
    cursor.execute("SELECT balance, password FROM users WHERE username = ?", (session['user'],))
    row = cursor.fetchone()
    balance = row[0] if row else 0.0
    user_api_key = hashlib.md5((session['user'] + str(row[1])).encode()).hexdigest() if row else ""
    conn.close()
    
    whatsapp_link = get_setting('whatsapp_link', '9647800000000')
    telegram_link = get_setting('telegram_link', 'nsnn1')
    auto_pay_link = get_setting('auto_pay_link', 'https://t.me/')
    site_title = get_setting('site_title', 'FA1S SMM Panel - لوحة الخدمات الاحترافية')
    site_brand = get_setting('site_brand', '🚀 FA1S Panel')
    site_instructions = get_setting('site_instructions', '• تأكد من أن الحساب عام وليس خاص.')
    terms_text = get_setting('terms_text', 'شروط الاستخدام.')
    
    api_url = get_setting('api_url', '')
    api_key = get_setting('api_key', '')
    site_custom_url = get_setting('site_custom_url', request.host_url.rstrip('/') + '/')
    
    nav_data = get_sidebar_settings()
    
    return render_template_string(TEMPLATE, page='admin', all_services=all_services, all_users=all_users, balance=balance, user_api_key=user_api_key,
                                  whatsapp_link=whatsapp_link, telegram_link=telegram_link, auto_pay_link=auto_pay_link,
                                  site_title=site_title, site_brand=site_brand, site_instructions=site_instructions, terms_text=terms_text,
                                  api_url=api_url, api_key=api_key, site_custom_url=site_custom_url, nav_data=nav_data, **nav_data)

@app.route('/admin/save_site_settings', methods=['POST'])
def save_site_settings():
    if session.get('is_admin') != 1:
        return redirect(url_for('home'))
    site_title = request.form.get('site_title', '').strip()
    site_brand = request.form.get('site_brand', '').strip()
    site_custom_url = request.form.get('site_custom_url', '').strip()
    
    conn = sqlite3.connect('database.db', timeout=10, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('site_title', ?)", (site_title,))
    cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('site_brand', ?)", (site_brand,))
    cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('site_custom_url', ?)", (site_custom_url,))
    conn.commit()
    conn.close()
    flash('تم حفظ وتحديث إعدادات وعنوان الموقع بنجاح!', 'success')
    return redirect(url_for('admin'))

@app.route('/admin/save_api_settings', methods=['POST'])
def save_api_settings():
    if session.get('is_admin') != 1:
        return redirect(url_for('home'))
    api_url = request.form.get('api_url', '').strip()
    api_key = request.form.get('api_key', '').strip()
    
    conn = sqlite3.connect('database.db', timeout=10, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('api_url', ?)", (api_url,))
    cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('api_key', ?)", (api_key,))
    conn.commit()
    conn.close()
    flash('تم حفظ إعدادات الربط والمفتاح بنجاح!', 'success')
    return redirect(url_for('admin'))

@app.route('/admin/add_service', methods=['POST'])
def add_service():
    if session.get('is_admin') != 1:
        return redirect(url_for('home'))
    category = request.form.get('category', 'free')
    name = request.form.get('name', '').strip()
    rate = request.form.get('rate', '0')
    min_q = request.form.get('min_q', '10')
    max_q = request.form.get('max_q', '10000')
    description = request.form.get('description', '').strip()
    api_service_id = request.form.get('api_service_id', '0')
    
    try:
        rate = float(rate)
        min_q = int(min_q)
        max_q = int(max_q)
        api_service_id = int(api_service_id)
    except:
        flash('يرجى التأكد من إدخال أرقام صحيحة للسعر والكميات', 'error')
        return redirect(url_for('admin'))

    conn = sqlite3.connect('database.db', timeout=10, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO services (category, name, rate, min_q, max_q, description, api_service_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
                   (category, name, rate, min_q, max_q, description, api_service_id))
    conn.commit()
    conn.close()
    flash('تم إضافة الخدمة بنجاح!', 'success')
    return redirect(url_for('admin'))

@app.route('/admin/save_sidebar_full', methods=['POST'])
def save_sidebar_full():
    if session.get('is_admin') != 1:
        return redirect(url_for('home'))
        
    conn = sqlite3.connect('database.db', timeout=10, check_same_thread=False)
    cursor = conn.cursor()
    
    for i in range(1, 9):
        text = request.form.get(f'nav_text_{i}', '').strip()
        link = request.form.get(f'nav_link_{i}', '').strip()
        icon = request.form.get(f'nav_icon_{i}', '').strip()
        
        cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (f'nav_text_{i}', text))
        cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (f'nav_link_{i}', link))
        cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (f'nav_icon_{i}', icon))
        
    conn.commit()
    conn.close()
    flash('تم حفظ وتحديث عناصر قائمة التنقل بالكامل بنجاح!', 'success')
    return redirect(url_for('admin'))

@app.route('/admin/save_instructions', methods=['POST'])
def save_instructions():
    if session.get('is_admin') != 1:
        return redirect(url_for('home'))
    instructions = request.form.get('site_instructions', '').strip()
    
    conn = sqlite3.connect('database.db', timeout=10, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('site_instructions', ?)", (instructions,))
    conn.commit()
    conn.close()
    flash('تم حفظ التعليمات بنجاح!', 'success')
    return redirect(url_for('admin'))

@app.route('/admin/manage_balance', methods=['POST'])
def manage_balance():
    if session.get('is_admin') != 1:
        return redirect(url_for('home'))
    
    username = request.form.get('username', '').strip()
    amount_str = request.form.get('amount', '0')
    action_type = request.form.get('action_type', 'add')
    
    try:
        amount = float(amount_str)
    except:
        flash('المبلغ غير صالح', 'error')
        return redirect(url_for('admin'))
        
    conn = sqlite3.connect('database.db', timeout=10, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("SELECT balance FROM users WHERE username = ?", (username,))
    user = cursor.fetchone()
    if user:
        current_bal = user[0]
        if action_type == 'add':
            new_bal = current_bal + amount
            cursor.execute("UPDATE users SET balance = ? WHERE username = ?", (new_bal, username))
            conn.commit()
            flash(f'تم إضافة مبلغ ${amount} بنجاح للمستخدم: {username}', 'success')
        elif action_type == 'subtract':
            new_bal = max(0.0, current_bal - amount)
            cursor.execute("UPDATE users SET balance = ? WHERE username = ?", (new_bal, username))
            conn.commit()
            flash(f'تم سحب مبلغ ${amount} بنجاح من المستخدم: {username}', 'success')
    else:
        flash('اسم المستخدم غير موجود', 'error')
    conn.close()
    return redirect(url_for('admin'))

@app.route('/admin/delete/<int:id>')
def delete_service(id):
    if session.get('is_admin') != 1:
        return redirect(url_for('home'))
    conn = sqlite3.connect('database.db', timeout=10, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM services WHERE id = ?", (id,))
    conn.commit()
    conn.close()
    flash('تم حذف الخدمة بنجاح', 'success')
    return redirect(url_for('admin'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password']
        
        conn = sqlite3.connect('database.db', timeout=10, check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute("SELECT username, balance, is_admin FROM users WHERE username = ? AND password = ?", (username, password))
        user = cursor.fetchone()
        conn.close()
        
        if user:
            session['user'] = user[0]
            session['is_admin'] = user[2]
            flash('تم تسجيل الدخول بنجاح', 'success')
            return redirect(url_for('home'))
        else:
            flash('خطأ في اسم المستخدم أو كلمة المرور', 'error')
            
    site_title = get_setting('site_title', 'FA1S SMM Panel')
    site_brand = get_setting('site_brand', '🚀 FA1S Panel')
    return render_template_string(TEMPLATE, page='login', site_title=site_title, site_brand=site_brand)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        
        if not email or not username or not password:
            flash('الرجاء ملء جميع حقول التسجيل بشكل صحيح', 'error')
            return redirect(url_for('register'))

        conn = sqlite3.connect('database.db', timeout=10, check_same_thread=False)
        cursor = conn.cursor()
        
        cursor.execute("SELECT id FROM users WHERE username = ?", (username,))
        if cursor.fetchone():
            conn.close()
            flash('اسم المستخدم هذا مسجل مسبقاً، يرجى اختيار اسم غير مكرر', 'error')
            return redirect(url_for('register'))

        cursor.execute("SELECT COUNT(*) FROM users")
        count = cursor.fetchone()[0]
        is_admin = 1 if count == 0 else 0
        
        try:
            # الرصيد الافتراضي أصبح 0.0 ولن يتم منح رصيد هدية تلقائي بعد الآن
            cursor.execute("INSERT INTO users (email, username, password, balance, is_admin) VALUES (?, ?, ?, 0.0, ?)", 
                           (email, username, password, is_admin))
            conn.commit()
            session['user'] = username
            session['is_admin'] = is_admin
            flash('تم إنشاء الحساب بنجاح (رصيدك الحالي 0، بانتظار شحن الرصيد من المشرف)!', 'success')
            return redirect(url_for('home'))
        except Exception as e:
            flash(f'حدث خطأ أثناء التسجيل: {str(e)}', 'error')
        finally:
            conn.close()
            
    site_title = get_setting('site_title', 'FA1S SMM Panel')
    site_brand = get_setting('site_brand', '🚀 FA1S Panel')
    return render_template_string(TEMPLATE, page='register', site_title=site_title, site_brand=site_brand)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('home'))

@app.route('/order', methods=['POST'])
def order():
    if 'user' not in session:
        return redirect(url_for('login'))
        
    service_id = request.form.get('service_id')
    link = request.form.get('link')
    quantity = request.form.get('quantity')
    plat = request.form.get('plat', 'free')
    
    if not service_id or not link or not quantity:
        flash('يرجى ملء جميع الحقول المطلوبة', 'error')
        return redirect(url_for('home', plat=plat))
        
    try:
        quantity = int(quantity)
    except:
        flash('الكمية يجب أن تكون رقماً صحيحاً', 'error')
        return redirect(url_for('home', plat=plat))

    conn = sqlite3.connect('database.db', timeout=10, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("SELECT rate, min_q, max_q, api_service_id FROM services WHERE id = ?", (service_id,))
    service = cursor.fetchone()
    if not service:
        conn.close()
        flash('الخدمة المطلوبة غير موجودة', 'error')
        return redirect(url_for('home', plat=plat))
        
    rate, min_q, max_q, api_service_id = service
    
    if quantity < min_q or quantity > max_q:
        flash(f'الكمية يجب أن تكون بين {min_q} و {max_q}', 'error')
        conn.close()
        return redirect(url_for('home', plat=plat))
        
    total_cost = (quantity * rate) / 1000
    
    cursor.execute("SELECT balance FROM users WHERE username = ?", (session['user'],))
    user_row = cursor.fetchone()
    current_balance = user_row[0]
    
    if current_balance < total_cost:
        flash('رصيدك غير كافٍ لإتمام هذا الطلب', 'error')
        conn.close()
        return redirect(url_for('home', plat=plat))
        
    api_url = get_setting('api_url').strip()
    api_key = get_setting('api_key').strip()
    api_order_id = 'Free'
    order_status = 'قيد التنفيذ'
    
    if api_url and api_key and int(api_service_id) > 0:
        try:
            payload = {
                'key': api_key,
                'action': 'add',
                'service': int(api_service_id),
                'link': link,
                'quantity': quantity
            }
            response = requests.post(api_url, data=payload, timeout=20)
            res_data = response.json() if response.ok else {}
            if 'order' in res_data:
                api_order_id = str(res_data['order'])
                order_status = 'Processing'
        except:
            pass

    new_balance = current_balance - total_cost
    cursor.execute("UPDATE users SET balance = ? WHERE username = ?", (new_balance, session['user']))
    cursor.execute("INSERT INTO orders (username, service_id, link, quantity, status, api_order_id) VALUES (?, ?, ?, ?, ?, ?)",
                   (session['user'], service_id, link, quantity, order_status, api_order_id))
    conn.commit()
    conn.close()
    
    flash(f'تم إرسال طلبك بنجاح! (رقم الطلب: #{api_order_id})', 'success')
    return redirect(url_for('orders'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
