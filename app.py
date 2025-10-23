from flask import Flask, render_template, request, redirect, url_for, session
import sqlite3
import random
import string
import os
from werkzeug.utils import secure_filename
import csv
from flask import send_file, make_response
from io import StringIO

app = Flask(__name__)
app.secret_key = "super_secret_key"
DB = "users.db"

# Upload directory
UPLOAD_FOLDER = 'static/uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# ----------------------------
# DATABASE INITIALIZATION
# ----------------------------
def init_db():
    conn = sqlite3.connect(DB)
    c = conn.cursor()

    # Users table
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        fullname TEXT,
        username TEXT,
        email TEXT,
        phone TEXT,
        access_key TEXT,
        referral TEXT DEFAULT 'null',
        password TEXT,
        role TEXT DEFAULT 'user'
    )''')

    # Access keys table
    c.execute('''CREATE TABLE IF NOT EXISTS access_keys (
        key TEXT PRIMARY KEY,
        used BOOLEAN DEFAULT 0
    )''')

    # Balances table
    c.execute('''CREATE TABLE IF NOT EXISTS balances (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_email TEXT UNIQUE,
        task_earnings REAL DEFAULT 10000,
        referral_bonus REAL DEFAULT 0,
        ads_bonus REAL DEFAULT 0,
        total_downlines INTEGER DEFAULT 0
    )''')

    # Ads table
    c.execute('''CREATE TABLE IF NOT EXISTS ads (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_email TEXT,
        image_url TEXT,
        description TEXT,
        cost INTEGER DEFAULT 0,
        FOREIGN KEY (user_email) REFERENCES users(email)
    )''')

    # Insert random access keys if none exist
    c.execute('SELECT COUNT(*) FROM access_keys')
    if c.fetchone()[0] == 0:
        keys = set()
        while len(keys) < 100:
            key = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
            keys.add(key)
        c.executemany('INSERT INTO access_keys (key, used) VALUES (?, 0)', [(k,) for k in keys])
        print(f"[INIT] Added {len(keys)} access keys.")

    conn.commit()
    conn.close()

# ----------------------------
# ROUTES
# ----------------------------
@app.route('/')
def home():
    return redirect(url_for('signup'))

# ---------- SIGNUP ----------
@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        fullname = request.form['fullname']
        username = request.form['username']
        email = request.form['email']
        phone = request.form['phone']
        access_key = request.form['access_key']
        referral = request.form.get('referral', 'null')
        password = request.form['password']

        conn = sqlite3.connect(DB)
        c = conn.cursor()

        # Check access key validity
        c.execute('SELECT used FROM access_keys WHERE key=?', (access_key,))
        row = c.fetchone()
        if not row:
            conn.close()
            return "Invalid Access Key ❌"
        if row[0]:
            conn.close()
            return "Access Key Already Used ❌"

        # Insert new user
        c.execute('INSERT INTO users (fullname, username, email, phone, access_key, referral, password) VALUES (?, ?, ?, ?, ?, ?, ?)',
                  (fullname, username, email, phone, access_key, referral, password))

        # Mark access key as used
        c.execute('UPDATE access_keys SET used=1 WHERE key=?', (access_key,))

        # Create default balance record
        c.execute('INSERT OR IGNORE INTO balances (user_email) VALUES (?)', (email,))

        conn.commit()
        conn.close()
        return redirect(url_for('login'))

    return render_template('signup.html')

# ---------- LOGIN ----------
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        conn = sqlite3.connect(DB)
        c = conn.cursor()
        c.execute('SELECT * FROM users WHERE email=? AND password=?', (email, password))
        user = c.fetchone()
        conn.close()

        if user:
            session['user'] = {
                "fullname": user[1],
                "username": user[2],
                "email": user[3],
                "phone": user[4],
                "access_key": user[5],
                "referral": user[6],
                "password": user[7],
                "role": user[8]
            }
            if user[8] == 'admin':
                return redirect(url_for('admin_panel'))
            return redirect(url_for('dashboard'))
        else:
            return "Invalid Email or Password ❌"

    return render_template('login.html')

# ---------- DASHBOARD ----------
@app.route('/dashboard')
def dashboard():
    if 'user' not in session:
        return redirect(url_for('login'))

    user = session['user']
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute('SELECT task_earnings, referral_bonus, ads_bonus, total_downlines FROM balances WHERE user_email=?', (user['email'],))
    balances = c.fetchone()

    if not balances:
        c.execute('INSERT INTO balances (user_email) VALUES (?)', (user['email'],))
        conn.commit()
        c.execute('SELECT task_earnings, referral_bonus, ads_bonus, total_downlines FROM balances WHERE user_email=?', (user['email'],))
        balances = c.fetchone()

    conn.close()
    return render_template('dashboard.html', user=user, balances=balances)

# ---------- ADMIN ----------
@app.route('/admin')
def admin_panel():
    if 'user' not in session or session['user'].get('role') != 'admin':
        return "❌ Access Denied. Admins Only."

    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute('SELECT fullname, username, email, phone, access_key, referral, role FROM users')
    users = c.fetchall()
    c.execute('SELECT key, used FROM access_keys')
    keys = c.fetchall()
    conn.close()
    return render_template('admin.html', users=users, keys=keys)

# ---------- POST AD ----------
@app.route('/post_ad', methods=['GET'])
def post_ad():
    if 'user' not in session:
        return redirect(url_for('login'))

    user = session['user']

    # Fetch user's actual balance
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute('SELECT task_earnings FROM balances WHERE user_email=?', (user['email'],))
    balance = c.fetchone()
    conn.close()

    if not balance:
        balance = (0,)

    # Pass both user and real balance to the page
    return render_template('post_ad.html', user=user, balance=balance[0])


# ---------- SUBMIT AD ----------
@app.route('/submit_ad', methods=['POST'])
def submit_ad():
    if 'user' not in session:
        return redirect(url_for('login'))

    image = request.files['image']
    description = request.form['content']
    user_email = session['user']['email']

    conn = sqlite3.connect(DB)
    c = conn.cursor()

    # Check user’s current balance
    c.execute('SELECT task_earnings FROM balances WHERE user_email=?', (user_email,))
    balance = c.fetchone()

    # Validate balance
    if not balance or balance[0] < 7000:
        conn.close()
        return "❌ Insufficient balance. You need at least 7000 AVreX points (≈₦2800)."

    # Handle image upload
    if image:
        filename = secure_filename(image.filename)
        image_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        image.save(image_path)

        # Deduct points & store ad info
        c.execute('UPDATE balances SET task_earnings = task_earnings - 7000 WHERE user_email=?', (user_email,))
        c.execute('INSERT INTO ads (user_email, image_url, description, cost) VALUES (?, ?, ?, ?)',
                  (user_email, image_path, description, 7000))
        conn.commit()
        conn.close()

        return "✅ Ad posted successfully — 7000 AVreX points deducted!"
    else:
        conn.close()
        return "❌ Please upload an image."

# ---------- LOGOUT ----------
@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('login'))

# ---------- TASK ----------
@app.route('/task')
def task():
    return render_template('task.html')


# ---------- VIEW ADS (ADMIN) ----------
@app.route('/view_ads')
def view_ads():
    if 'user' not in session or session['user'].get('role') != 'admin':
        return "❌ Access Denied. Admins Only."

    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute('SELECT id, image_url, description, cost, user_email FROM ads ORDER BY id DESC')
    ads = c.fetchall()
    conn.close()

    total_ads = len(ads)
    return render_template('view_ads.html', ads=ads, total_ads=total_ads)


# ---------- DOWNLOAD ADS (CSV) ----------
@app.route('/download_ads')
def download_ads():
    if 'user' not in session or session['user'].get('role') != 'admin':
        return "❌ Access Denied. Admins Only."

    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute('SELECT id, user_email, image_url, description, cost FROM ads')
    ads = c.fetchall()
    conn.close()

    si = StringIO()
    cw = csv.writer(si)
    cw.writerow(['ID', 'User Email', 'Image URL', 'Description', 'Cost'])
    cw.writerows(ads)

    output = make_response(si.getvalue())
    output.headers["Content-Disposition"] = "attachment; filename=AVreX_Ads.csv"
    output.headers["Content-type"] = "text/csv"
    return output


# ---------- DELETE AD ----------
@app.route('/delete_ad/<int:ad_id>', methods=['POST'])
def delete_ad(ad_id):
    if 'user' not in session or session['user'].get('role') != 'admin':
        return "❌ Access Denied. Admins Only."

    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute('SELECT image_url FROM ads WHERE id=?', (ad_id,))
    ad = c.fetchone()

    if ad:
        image_path = ad[0]
        if os.path.exists(image_path):
            os.remove(image_path)
        c.execute('DELETE FROM ads WHERE id=?', (ad_id,))
        conn.commit()

    conn.close()
    return redirect(url_for('view_ads'))

# ---------- MAIN ----------
if __name__ == '__main__':
    init_db()
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
