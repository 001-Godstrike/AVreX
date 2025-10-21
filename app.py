from flask import Flask, render_template, request, redirect, url_for, session
import sqlite3
import random
import string

app = Flask(__name__)
app.secret_key = "super_secret_key"  # Change this to something unique
DB = "users.db"

# ----------------------------
# DATABASE INITIALIZATION
# ----------------------------
def init_db():
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    # Create users table
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
    # Create access keys table
    c.execute('''CREATE TABLE IF NOT EXISTS access_keys (
        key TEXT PRIMARY KEY,
        used BOOLEAN DEFAULT 0
    )''')
    # Insert 100 random keys if empty
    c.execute('SELECT COUNT(*) FROM access_keys')
    if c.fetchone()[0] == 0:
        keys = set()
        while len(keys) < 100:
            key = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
            keys.add(key)
        c.executemany('INSERT INTO access_keys (key, used) VALUES (?, 0)', [(k,) for k in keys])
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

        # Insert user
        c.execute('INSERT INTO users (fullname, username, email, phone, access_key, referral, password) VALUES (?, ?, ?, ?, ?, ?, ?)',
                  (fullname, username, email, phone, access_key, referral, password))

        # Mark access key as used
        c.execute('UPDATE access_keys SET used=1 WHERE key=?', (access_key,))
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
    return render_template('dashboard.html', user=session['user'])


# ---------- ADMIN PANEL ----------
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


# ---------- ADD NEW KEYS ----------
@app.route('/add_keys', methods=['POST'])
def add_keys():
    try:
        num_keys = int(request.form['num_keys'])
    except ValueError:
        num_keys = 1

    new_keys = set()
    while len(new_keys) < num_keys:
        key = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
        new_keys.add(key)

    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.executemany('INSERT INTO access_keys (key, used) VALUES (?, 0)', [(k,) for k in new_keys])
    conn.commit()
    conn.close()

    print(f"[ADMIN] Added {num_keys} new access keys.")
    return redirect(url_for('admin_panel'))


# ---------- DELETE KEY ----------
@app.route('/delete_key/<key>', methods=['POST'])
def delete_key(key):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute('DELETE FROM access_keys WHERE key=?', (key,))
    conn.commit()
    conn.close()
    return redirect(url_for('admin_panel'))


# ---------- LOGOUT ----------
@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('login'))

# ---------- TASK ----------
@app.route('/task')
def task():
    return render_template('task.html')

# ----------------------------
# MAIN EXECUTION
# ----------------------------
if __name__ == '__main__':
    init_db()
    app.run(debug=True)
