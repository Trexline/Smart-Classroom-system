from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash
import pymysql
pymysql.install_as_MySQLdb()
from flask_mysqldb import MySQL
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from datetime import datetime
import MySQLdb
import os
import uuid
import requests

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'change-this-in-production')

# ─── MySQL Config ────────────────────────────────────────────────
DB_HOST     = 'localhost'
DB_USER     = 'root'
DB_PASSWORD = 'trex1234'
DB_NAME     = 'iot_dashboard'

app.config['MYSQL_HOST']        = DB_HOST
app.config['MYSQL_USER']        = DB_USER
app.config['MYSQL_PASSWORD']    = DB_PASSWORD
app.config['MYSQL_DB']          = DB_NAME
app.config['MYSQL_CURSORCLASS'] = 'DictCursor'

mysql = MySQL(app)

# ─── Database Initialisation ──────────────────────────────────────
def init_db():
    """Create the database if missing, then all tables and default admin."""

    tmp = MySQLdb.connect(host=DB_HOST, user=DB_USER, password=DB_PASSWORD)
    tmp_cur = tmp.cursor()
    tmp_cur.execute(f"CREATE DATABASE IF NOT EXISTS {DB_NAME}")
    tmp.commit()
    tmp_cur.close()
    tmp.close()

    cur = mysql.connection.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id         INT AUTO_INCREMENT PRIMARY KEY,
            username   VARCHAR(80)  NOT NULL,
            email      VARCHAR(120) NOT NULL UNIQUE,
            password   VARCHAR(255) NOT NULL,
            role       ENUM('admin','pir','ultrasonic','ldr','esp32cam','dht22','pending')
                       DEFAULT 'pending',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS pir_data (
            id               INT AUTO_INCREMENT PRIMARY KEY,
            motion_detected  TINYINT(1) NOT NULL,
            timestamp        DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS ultrasonic_data (
            id           INT AUTO_INCREMENT PRIMARY KEY,
            distance_cm  FLOAT NOT NULL,
            timestamp    DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS ldr_data (
            id                INT AUTO_INCREMENT PRIMARY KEY,
            light_percentage  INT NOT NULL,
            timestamp         DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS dht22_data (
            id           INT AUTO_INCREMENT PRIMARY KEY,
            temperature  FLOAT NOT NULL,
            humidity     FLOAT NOT NULL,
            timestamp    DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS esp32cam_data (
            id         INT AUTO_INCREMENT PRIMARY KEY,
            image_url  VARCHAR(500),
            timestamp  DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("SELECT id FROM users WHERE role = 'admin' LIMIT 1")
    if not cur.fetchone():
        hashed = generate_password_hash('admin123')
        cur.execute(
            "INSERT INTO users (username, email, password, role) VALUES (%s, %s, %s, %s)",
            ('Admin', 'admin@iot.local', hashed, 'admin')
        )
        print("✅ Default admin created — email: admin@iot.local  password: admin123")
        print("⚠️  Change the admin password immediately after first login!")

    mysql.connection.commit()
    cur.close()

# ─── Valid Roles ─────────────────────────────────────────────────
VALID_ROLES = ['admin', 'pir', 'ultrasonic', 'ldr', 'esp32cam', 'dht22']
esp32_cam_ip = None
student_count = 0
last_pir_state = 0

# ─── Auth Decorators ─────────────────────────────────────────────
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in first.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

def role_required(*roles):
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if 'user_id' not in session:
                return redirect(url_for('login'))
            if session.get('role') not in roles:
                flash('Access denied. You do not have permission to view this page.', 'danger')
                return redirect(url_for('dashboard'))
            return f(*args, **kwargs)
        return decorated
    return decorator

# ─── Auth Routes ─────────────────────────────────────────────────
@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return render_template('home.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email    = request.form.get('email', '').strip()
        password = request.form.get('password', '')

        cur = mysql.connection.cursor()
        cur.execute("SELECT * FROM users WHERE email = %s", (email,))
        user = cur.fetchone()
        cur.close()

        if user and check_password_hash(user['password'], password):
            session['user_id']  = user['id']
            session['username'] = user['username']
            session['role']     = user['role']
            flash(f"Welcome back, {user['username']}!", 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid email or password.', 'danger')

    return render_template('login.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email    = request.form.get('email', '').strip()
        password = request.form.get('password', '')

        if not username or not email or not password:
            flash('All fields are required.', 'danger')
            return render_template('signup.html')

        cur = mysql.connection.cursor()
        cur.execute("SELECT id FROM users WHERE email = %s", (email,))
        if cur.fetchone():
            flash('Email already registered.', 'danger')
            cur.close()
            return render_template('signup.html')

        hashed = generate_password_hash(password)
        cur.execute(
            "INSERT INTO users (username, email, password, role) VALUES (%s, %s, %s, %s)",
            (username, email, hashed, 'pending')
        )
        mysql.connection.commit()
        cur.close()
        flash('Account created! Wait for the admin to assign your role.', 'success')
        return redirect(url_for('login'))

    return render_template('signup.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))

# ─── Dashboard Router ─────────────────────────────────────────────
@app.route('/dashboard')
@login_required
def dashboard():
    role = session.get('role')
    routes = {
        'admin':      'admin_dashboard',
        'pir':        'pir_dashboard',
        'ultrasonic': 'ultrasonic_dashboard',
        'ldr':        'ldr_dashboard',
        'esp32cam':   'esp32cam_dashboard',
        'dht22':      'dht22_dashboard',
    }
    if role in routes:
        return redirect(url_for(routes[role]))
    return render_template('pending.html')

# ─── Admin Dashboard ──────────────────────────────────────────────
@app.route('/admin')
@login_required
@role_required('admin')
def admin_dashboard():
    global esp32_cam_ip
    cur = mysql.connection.cursor()

    cur.execute("SELECT id, username, email, role, created_at FROM users WHERE role != 'admin' ORDER BY created_at DESC")
    users = cur.fetchall()

    cur.execute("SELECT * FROM pir_data        ORDER BY timestamp DESC LIMIT 5")
    pir_data = cur.fetchall()
    cur.execute("SELECT * FROM ultrasonic_data  ORDER BY timestamp DESC LIMIT 5")
    various_ultrasonic_data = cur.fetchall()
    cur.execute("SELECT * FROM ldr_data         ORDER BY timestamp DESC LIMIT 5")
    various_ldr_data = cur.fetchall()
    cur.execute("SELECT * FROM dht22_data       ORDER BY timestamp DESC LIMIT 5")
    dht22_data = cur.fetchall()
    cur.execute("SELECT * FROM esp32cam_data    ORDER BY timestamp DESC LIMIT 5")
    cam_data = cur.fetchall()

    cur.execute("SELECT temperature FROM dht22_data ORDER BY id DESC LIMIT 20")
    temp_history = [r['temperature'] for r in cur.fetchall()][::-1]

    cur.execute("SELECT humidity FROM dht22_data ORDER BY id DESC LIMIT 20")
    hum_history = [r['humidity'] for r in cur.fetchall()][::-1]

    # FIX: was r['light_value'] — correct column is light_percentage
    cur.execute("SELECT light_percentage FROM ldr_data ORDER BY id DESC LIMIT 20")
    ldr_history = [r['light_percentage'] for r in cur.fetchall()][::-1]

    cur.execute("SELECT distance_cm FROM ultrasonic_data ORDER BY id DESC LIMIT 20")
    dist_history = [r['distance_cm'] for r in cur.fetchall()][::-1]

    cur.execute("SELECT motion_detected FROM pir_data ORDER BY id DESC LIMIT 20")
    pir_history = [r['motion_detected'] for r in cur.fetchall()][::-1]

    cur.close()

    return render_template('admin.html',
        users=users,
        pir_data=pir_data,
        ultrasonic_data=various_ultrasonic_data,
        ldr_data=various_ldr_data,
        dht22_data=dht22_data,
        cam_data=cam_data,
        roles=VALID_ROLES,
        esp32_ip=esp32_cam_ip or '',
        sensor=None,
        live_count=0,
        temp_history=temp_history,
        hum_history=hum_history,
        ldr_history=ldr_history,
        dist_history=dist_history,
        pir_history=pir_history,
    )

@app.route('/admin/assign_role', methods=['POST'])
@login_required
@role_required('admin')
def assign_role():
    user_id  = request.form.get('user_id')
    new_role = request.form.get('role')
    if new_role not in VALID_ROLES + ['pending']:
        flash('Invalid role.', 'danger')
        return redirect(url_for('admin_dashboard'))

    cur = mysql.connection.cursor()
    cur.execute("UPDATE users SET role = %s WHERE id = %s", (new_role, user_id))
    mysql.connection.commit()
    cur.close()
    flash('Role updated successfully.', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/revoke/<int:user_id>', methods=['POST'])
@login_required
@role_required('admin')
def revoke_permission(user_id):
    cur = mysql.connection.cursor()
    cur.execute("UPDATE users SET role = 'pending' WHERE id = %s", (user_id,))
    mysql.connection.commit()
    cur.close()
    flash('Permission revoked.', 'warning')
    return redirect(url_for('admin_dashboard'))

# ─── Sensor Dashboards ────────────────────────────────────────────
@app.route('/dashboard/pir')
@login_required
@role_required('pir', 'admin')
def pir_dashboard():
    cur = mysql.connection.cursor()
    cur.execute("SELECT * FROM pir_data ORDER BY timestamp DESC LIMIT 50")
    data = cur.fetchall()
    cur.close()
    return render_template('pir.html', data=data)

@app.route('/dashboard/ultrasonic')
@login_required
@role_required('ultrasonic', 'admin')
def ultrasonic_dashboard():
    cur = mysql.connection.cursor()
    cur.execute("SELECT * FROM ultrasonic_data ORDER BY timestamp DESC LIMIT 50")
    data = cur.fetchall()
    cur.close()
    return render_template('ultrasonic.html', data=data)

@app.route('/dashboard/ldr')
@login_required
@role_required('ldr', 'admin')
def ldr_dashboard():
    cur = mysql.connection.cursor()
    cur.execute("SELECT * FROM ldr_data ORDER BY timestamp DESC LIMIT 50")
    data = cur.fetchall()
    cur.close()
    return render_template('ldr.html', data=data)

@app.route('/dashboard/dht22')
@login_required
@role_required('dht22', 'admin')
def dht22_dashboard():
    cur = mysql.connection.cursor()
    cur.execute("SELECT * FROM dht22_data ORDER BY timestamp DESC LIMIT 50")
    data = cur.fetchall()
    cur.close()
    return render_template('dht22.html', data=data)

@app.route('/dashboard/esp32cam')
@login_required
@role_required('esp32cam', 'admin')
def esp32cam_dashboard():
    cur = mysql.connection.cursor()
    cur.execute("SELECT * FROM esp32cam_data ORDER BY timestamp DESC LIMIT 20")
    data = cur.fetchall()
    cur.close()
    return render_template('esp32cam.html', data=data)

# ─── API Endpoints ────────────────────────────────────────────────

@app.route('/api/pir', methods=['POST'])
def api_pir():
    global esp32_cam_ip
    d = request.get_json(silent=True) or request.form

    motion = d.get('motion_detected')
    if motion is None:
        motion = 0
    else:
        motion = int(motion)

    cur = mysql.connection.cursor()
    cur.execute(
        "INSERT INTO pir_data (motion_detected, timestamp) VALUES (%s, %s)",
        (motion, datetime.now())
    )
    mysql.connection.commit()
    cur.close()

    if motion == 1 and esp32_cam_ip:
        try:
            requests.get(f"http://{esp32_cam_ip}/capture", timeout=5)
        except Exception as e:
            print(f"⚠️  Snapshot trigger failed: {e}")

    return jsonify({'status': 'ok'}), 201

@app.route('/api/set_cam_ip', methods=['POST'])
def set_cam_ip():
    global esp32_cam_ip
    d = request.get_json(silent=True) or request.form
    if not d or not d.get('ip'):
        return jsonify({'error': 'ip required'}), 400
    esp32_cam_ip = d['ip']
    print(f"📷 ESP32-CAM registered at {esp32_cam_ip}")
    return jsonify({'status': 'ok', 'ip': esp32_cam_ip}), 200

@app.route('/api/ultrasonic', methods=['POST'])
def api_ultrasonic():
    d = request.get_json(silent=True) or request.form
    distance = d.get('distance_cm')

    if distance is None:
        return jsonify({'error': 'Missing field: distance_cm'}), 400

    cur = mysql.connection.cursor()
    cur.execute(
        "INSERT INTO ultrasonic_data (distance_cm, timestamp) VALUES (%s, %s)",
        (float(distance), datetime.now())
    )
    mysql.connection.commit()
    cur.close()
    return jsonify({'status': 'ok'}), 201

@app.route('/api/ultrasonic_live')
def api_ultrasonic_live():
    cur = mysql.connection.cursor()

    cur.execute("SELECT distance_cm FROM ultrasonic_data ORDER BY id DESC LIMIT 1")
    latest = cur.fetchone()

    cur.execute("SELECT distance_cm FROM ultrasonic_data ORDER BY id DESC LIMIT 20")
    dist_history = [r['distance_cm'] for r in cur.fetchall()][::-1]

    cur.close()

    return jsonify({
        'dist': latest['distance_cm'] if latest else None,
        'dist_history': dist_history
    })

@app.route('/api/ldr', methods=['POST'])
def api_ldr():
    d = request.get_json(silent=True) or request.form
    raw_val = d.get('light_value')

    if raw_val is None:
        return jsonify({"error": "Missing light_value"}), 400

    try:
        raw_val = float(raw_val)
        # Convert 0–4095 ADC range to 0–100%
        percentage = round((raw_val / 4095.0) * 100)
        percentage = max(0, min(100, percentage))
    except ValueError:
        return jsonify({"error": "Invalid data format"}), 400

    cur = mysql.connection.cursor()
  
    cur.execute("INSERT INTO ldr_data (light_percentage) VALUES (%s)", (percentage,))
    mysql.connection.commit()
    cur.close()

    return jsonify({"status": "success", "value_saved": percentage}), 201


@app.route('/api/dht22', methods=['POST'])
def api_dht22():
    d = request.get_json(silent=True) or request.form
    temp = d.get('temperature')
    hum  = d.get('humidity')

    if temp is None or hum is None:
        return jsonify({'error': 'Missing fields: temperature or humidity'}), 400

    cur = mysql.connection.cursor()
    cur.execute(
        "INSERT INTO dht22_data (temperature, humidity, timestamp) VALUES (%s, %s, %s)",
        (float(temp), float(hum), datetime.now())
    )
    mysql.connection.commit()
    cur.close()
    return jsonify({'status': 'ok'}), 201

@app.route('/api/esp32cam', methods=['POST'])
def api_esp32cam():
    global esp32_cam_ip
    d = request.get_json(silent=True) or request.form
    if not d:
        return jsonify({'error': 'No data'}), 400

    if d.get('ip'):
        esp32_cam_ip = d.get('ip')

    img_url = d.get('image_url') or ''

    cur = mysql.connection.cursor()
    cur.execute(
        "INSERT INTO esp32cam_data (image_url, timestamp) VALUES (%s, %s)",
        (img_url, datetime.now())
    )
    mysql.connection.commit()
    cur.close()
    return jsonify({'status': 'ok'}), 201

@app.route('/api/esp32cam/snapshot', methods=['POST'])
def esp32cam_snapshot():
    if not request.data:
        return jsonify({'error': 'No image data'}), 400

    filename  = f"snapshot_{uuid.uuid4().hex}.jpg"
    save_dir  = os.path.join('static', 'snapshots')
    save_path = os.path.join(save_dir, filename)
    os.makedirs(save_dir, exist_ok=True)

    with open(save_path, 'wb') as f:
        f.write(request.data)

    image_url = f"{request.scheme}://{request.host}/static/snapshots/{filename}"

    cur = mysql.connection.cursor()
    cur.execute(
        "INSERT INTO esp32cam_data (image_url, timestamp) VALUES (%s, %s)",
        (image_url, datetime.now())
    )
    mysql.connection.commit()
    cur.close()

    print(f"📷 Snapshot saved: {filename}")
    return jsonify({'status': 'ok', 'image_url': image_url}), 201

@app.route('/end_session', methods=['POST'])
@login_required
@role_required('admin')
def end_session():
    global student_count, last_pir_state
    student_count  = 0
    last_pir_state = 0
    flash('Session ended. Student count reset.', 'info')
    return redirect(url_for('admin_dashboard'))

@app.route('/api/sensor_live')
def sensor_live():
    global student_count, last_pir_state

    cur = mysql.connection.cursor()

    cur.execute("SELECT temperature, humidity FROM dht22_data ORDER BY id DESC LIMIT 1")
    dht22 = cur.fetchone()

    cur.execute("SELECT light_percentage FROM ldr_data ORDER BY id DESC LIMIT 1")
    ldr = cur.fetchone()

    cur.execute("SELECT motion_detected FROM pir_data ORDER BY id DESC LIMIT 1")
    pir = cur.fetchone()

    cur.execute("SELECT distance_cm FROM ultrasonic_data ORDER BY id DESC LIMIT 1")
    ultrasonic = cur.fetchone()

    cur.execute("SELECT temperature FROM dht22_data ORDER BY id DESC LIMIT 20")
    temp_history = [r['temperature'] for r in cur.fetchall()][::-1]

    cur.execute("SELECT humidity FROM dht22_data ORDER BY id DESC LIMIT 20")
    hum_history = [r['humidity'] for r in cur.fetchall()][::-1]

    # FIX: was r['light_value'] — correct column is light_percentage
    cur.execute("SELECT light_percentage FROM ldr_data ORDER BY id DESC LIMIT 20")
    ldr_history = [r['light_percentage'] for r in cur.fetchall()][::-1]

    cur.execute("SELECT distance_cm FROM ultrasonic_data ORDER BY id DESC LIMIT 20")
    dist_history = [r['distance_cm'] for r in cur.fetchall()][::-1]

    cur.execute("SELECT motion_detected FROM pir_data ORDER BY id DESC LIMIT 20")
    pir_history = [r['motion_detected'] for r in cur.fetchall()][::-1]

    cur.close()

    current_pir = pir['motion_detected'] if pir else 0
    if current_pir == 1 and last_pir_state == 0:
        student_count += 1
    last_pir_state = current_pir

    return jsonify({
        'sensor': {
            'temp': dht22['temperature']      if dht22      else None,
            'hum':  dht22['humidity']         if dht22      else None,
            # FIX: was ldr['light_percentage'] accessed as 'light_value' in some places
            'ldr':  ldr['light_percentage']   if ldr        else None,
            'pir':  current_pir,
            'dist': ultrasonic['distance_cm'] if ultrasonic else None,
        },
        'live_count':   student_count,
        'temp_history': temp_history,
        'hum_history':  hum_history,
        'ldr_history':  ldr_history,
        'dist_history': dist_history,
        'pir_history':  pir_history,
    })

@app.route('/api/cam_ip')
@login_required
def cam_ip():
    global esp32_cam_ip
    return jsonify({'ip': esp32_cam_ip or ''})


# ─── Run ──────────────────────────────────────────────────────────
if __name__ == '__main__':
    with app.app_context():
        init_db()
    app.run(debug=True, host='0.0.0.0', port=5000)