#!/usr/bin/env python3
"""
ATLAS KEY SYSTEM - BULLETPROOF PERSISTENT VERSION
Features: Zero data loss, atomic writes, immediate saves, crash recovery
"""

import os
import json
import secrets
import hashlib
import threading
import time
import signal
import sys
import shutil
import atexit
from datetime import datetime, timedelta
from flask import Flask, render_template, render_template_string, jsonify, request, session, redirect
from flask_cors import CORS
from functools import wraps

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', secrets.token_hex(32))

# Enable CORS for all origins (needed for desktop clients)
CORS(app, resources={
    r"/api/*": {
        "origins": "*",
        "methods": ["GET", "POST", "OPTIONS"],
        "allow_headers": ["Content-Type", "Authorization"]
    }
})

# Also add CORS headers to all responses
@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
    return response

# ============================================================================
# DATA STORAGE - ABSOLUTE PATHS FOR RELIABILITY
# ============================================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
KEYS_FILE = os.path.join(BASE_DIR, 'keys.json')
PROFILES_FILE = os.path.join(BASE_DIR, 'profiles.json')
STATS_FILE = os.path.join(BASE_DIR, 'stats.json')
BACKUP_DIR = os.path.join(BASE_DIR, 'backups')

KEYS = {}
USER_PROFILES = {}
STATS = {'validations': 0, 'generations': 0, 'last_reset': datetime.now().isoformat()}

ADMIN_USER = "admin"
ADMIN_PASS = os.environ.get('ADMIN_PASSWORD', 'atlas2024')

# Thread lock for file operations
file_lock = threading.Lock()
_data_modified = False

# ============================================================================
# PERSISTENCE FUNCTIONS - BULLETPROOF
# ============================================================================

def ensure_dirs():
    """Ensure all directories exist"""
    if not os.path.exists(BACKUP_DIR):
        os.makedirs(BACKUP_DIR)

def atomic_write(filepath, data):
    """
    ATOMIC FILE WRITE - Prevents corruption even if PC crashes mid-write
    1. Write to temp file
    2. Force sync to disk
    3. Rename (atomic operation)
    """
    temp_file = filepath + '.tmp'
    try:
        with open(temp_file, 'w') as f:
            json.dump(data, f, indent=2)
            f.flush()
            os.fsync(f.fileno())

        if os.path.exists(filepath):
            backup_path = filepath + '.bak'
            shutil.copy2(filepath, backup_path)

        os.replace(temp_file, filepath)
        return True
    except Exception as e:
        print(f"[ERROR] Write failed {filepath}: {e}")
        if os.path.exists(temp_file):
            try:
                os.remove(temp_file)
            except:
                pass
        return False

def save_data(force=False):
    """Save all data to disk - THREAD SAFE"""
    global _data_modified

    with file_lock:
        try:
            success = True
            success &= atomic_write(KEYS_FILE, KEYS)
            success &= atomic_write(PROFILES_FILE, USER_PROFILES)
            success &= atomic_write(STATS_FILE, STATS)

            if success:
                _data_modified = False
                if force:
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] 💾 Data saved to disk")
            return success
        except Exception as e:
            print(f"[ERROR] Save failed: {e}")
            return False

def load_data():
    """Load data with automatic corruption recovery"""
    global KEYS, USER_PROFILES, STATS

    def load_file(filepath, default):
        if os.path.exists(filepath):
            try:
                with open(filepath, 'r') as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                print(f"[WARNING] {os.path.basename(filepath)} corrupted: {e}")
                bak_path = filepath + '.bak'
                if os.path.exists(bak_path):
                    try:
                        with open(bak_path, 'r') as f:
                            data = json.load(f)
                        print(f"[RECOVERED] Loaded from backup: {os.path.basename(filepath)}")
                        return data
                    except Exception as e2:
                        print(f"[ERROR] Backup also corrupted: {e2}")
                return default
        return default

    KEYS = load_file(KEYS_FILE, {})
    USER_PROFILES = load_file(PROFILES_FILE, {})
    STATS = load_file(STATS_FILE, {'validations': 0, 'generations': 0, 'last_reset': datetime.now().isoformat()})

    print(f"[INFO] Loaded {len(KEYS)} keys, {len(USER_PROFILES)} profiles")
    return True

def create_backup():
    """Create timestamped backup"""
    ensure_dirs()
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

    for filename in ['keys.json', 'profiles.json', 'stats.json']:
        src = os.path.join(BASE_DIR, filename)
        if os.path.exists(src):
            dst = os.path.join(BACKUP_DIR, f"{filename}.{timestamp}")
            shutil.copy2(src, dst)

    cleanup_backups()
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 📁 Backup created: {timestamp}")

def cleanup_backups():
    """Keep only last 20 backups of each file"""
    if not os.path.exists(BACKUP_DIR):
        return

    for prefix in ['keys.json', 'profiles.json', 'stats.json']:
        files = sorted([f for f in os.listdir(BACKUP_DIR) if f.startswith(prefix)])
        while len(files) > 20:
            old = os.path.join(BACKUP_DIR, files.pop(0))
            try:
                os.remove(old)
            except:
                pass

def auto_save_worker():
    global _data_modified
    while True:
        time.sleep(30)
        if _data_modified:
            save_data()
            print(f"[{datetime.now().strftime('%H:%M')}] Auto-saved")

# ============================================================================
# SHUTDOWN HANDLERS
# ============================================================================

def emergency_save():
    print("\n[SHUTDOWN] Saving data before exit...")
    save_data(force=True)
    create_backup()
    print("[SHUTDOWN] Data saved safely. Goodbye!")

def signal_handler(signum, frame):
    print(f"\n[SIGNAL] Received {signum}, saving...")
    emergency_save()
    sys.exit(0)

atexit.register(emergency_save)
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

# ============================================================================
# KEY FUNCTIONS
# ============================================================================

def generate_key(duration='7days'):
    """Generate new key - SAVES IMMEDIATELY"""
    global _data_modified

    key = '-'.join([secrets.token_hex(2).upper() for _ in range(6)])

    duration_map = {
        '1hour': timedelta(hours=1),
        '1day': timedelta(days=1),
        '7days': timedelta(days=7),
        '30days': timedelta(days=30),
        '365days': timedelta(days=365),
        'lifetime': timedelta(days=9999)
    }

    expiry = datetime.now() + duration_map.get(duration, timedelta(days=7))

    KEYS[key] = {
        'created': datetime.now().isoformat(),
        'duration': duration,
        'expiry': expiry.isoformat(),
        'used': False,
        'hwid': None,
        'activated': None,
        'activations': 0
    }

    STATS['generations'] += 1
    _data_modified = True
    save_data(force=True)
    return key

def validate_key(key, hwid):
    """Validate key - SAVES IMMEDIATELY on success"""
    global _data_modified

    key = key.strip().upper()

    if key not in KEYS:
        return {'valid': False, 'message': 'Invalid key'}

    data = KEYS[key]
    now = datetime.now()
    expiry = datetime.fromisoformat(data['expiry'])

    if expiry < now:
        return {'valid': False, 'message': 'Key expired'}

    if data['used'] and data['hwid'] and data['hwid'] != hwid:
        return {'valid': False, 'message': 'Key in use on another device'}

    if not data['used']:
        data['used'] = True
        data['activated'] = now.isoformat()

    data['hwid'] = hwid
    data['activations'] += 1

    STATS['validations'] += 1
    _data_modified = True
    save_data(force=True)

    days_left = (expiry - now).days
    hours_left = (expiry - now).seconds // 3600

    return {
        'valid': True,
        'message': 'Key activated',
        'expiry': data['expiry'],
        'duration': data['duration'],
        'days_left': max(0, days_left),
        'hours_left': hours_left if days_left == 0 else None,
        'activations': data['activations']
    }

# ============================================================================
# FLASK ROUTES
# ============================================================================

@app.route('/')
def home():
    return render_template_string(INDEX_HTML)

@app.route('/api/status')
def status():
    return jsonify({
        'online': True,
        'time': datetime.now().isoformat(),
        'keys_total': len(KEYS),
        'keys_used': sum(1 for k in KEYS if KEYS[k].get('used')),
        'validations': STATS.get('validations', 0),
        'generations': STATS.get('generations', 0)
    })

@app.route('/api/validate', methods=['POST'])
def api_validate():
    data = request.json
    key = data.get('key', '')
    hwid = data.get('hwid', 'unknown')
    return jsonify(validate_key(key, hwid))

@app.route('/api/profiles/<hwid>', methods=['GET'])
def get_profiles(hwid):
    return jsonify(USER_PROFILES.get(hwid, {}))

@app.route('/api/profiles/<hwid>', methods=['POST'])
def save_profiles(hwid):
    global _data_modified
    data = request.json
    USER_PROFILES[hwid] = data
    _data_modified = True
    save_data(force=True)
    return jsonify({'success': True})

# ============================================================================
# ADMIN PANEL
# ============================================================================

@app.route('/admin')
def admin_login():
    auth = request.authorization
    if not auth or auth.username != ADMIN_USER or auth.password != ADMIN_PASS:
        return ('Admin Access Required', 401, {
            'WWW-Authenticate': 'Basic realm="ATLAS Admin"'
        })
    return render_template_string(ADMIN_HTML)

@app.route('/admin/api/stats')
def admin_stats():
    auth = request.authorization
    if not auth or auth.username != ADMIN_USER or auth.password != ADMIN_PASS:
        return jsonify({'error': 'Unauthorized'}), 401

    now = datetime.now()
    expired = sum(1 for v in KEYS.values() if datetime.fromisoformat(v['expiry']) < now)

    return jsonify({
        'total': len(KEYS),
        'used': sum(1 for k in KEYS if KEYS[k].get('used')),
        'available': len(KEYS) - sum(1 for k in KEYS if KEYS[k].get('used')),
        'expired': expired,
        'validations': STATS.get('validations', 0),
        'generations': STATS.get('generations', 0)
    })

@app.route('/admin/api/keys', methods=['GET'])
def admin_get_keys():
    auth = request.authorization
    if not auth or auth.username != ADMIN_USER or auth.password != ADMIN_PASS:
        return jsonify({'error': 'Unauthorized'}), 401
    return jsonify(KEYS)

@app.route('/admin/api/generate', methods=['POST'])
def admin_generate():
    auth = request.authorization
    if not auth or auth.username != ADMIN_USER or auth.password != ADMIN_PASS:
        return jsonify({'error': 'Unauthorized'}), 401

    data = request.json
    count = min(int(data.get('count', 1)), 100)
    duration = data.get('duration', '7days')

    new_keys = [generate_key(duration) for _ in range(count)]
    return jsonify({'success': True, 'keys': new_keys, 'duration': duration})

@app.route('/admin/api/delete/<key>', methods=['DELETE'])
def admin_delete(key):
    global _data_modified
    auth = request.authorization
    if not auth or auth.username != ADMIN_USER or auth.password != ADMIN_PASS:
        return jsonify({'error': 'Unauthorized'}), 401

    if key in KEYS:
        del KEYS[key]
        _data_modified = True
        save_data(force=True)
        return jsonify({'success': True})
    return jsonify({'success': False}), 404

@app.route('/admin/api/backup', methods=['POST'])
def admin_backup():
    auth = request.authorization
    if not auth or auth.username != ADMIN_USER or auth.password != ADMIN_PASS:
        return jsonify({'error': 'Unauthorized'}), 401

    try:
        create_backup()
        save_data(force=True)
        return jsonify({'success': True, 'message': 'Backup created'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

# ============================================================================
# HTML TEMPLATES
# ============================================================================

INDEX_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ATLAS | Key System</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; font-family: 'SF Pro Display', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; }
        :root { --primary: #6366f1; --primary-dark: #4f46e5; --bg: #0a0a0f; --surface: #141418; --text: #f1f1f4; --text-muted: #6b6b7b; --success: #22c55e; --error: #ef4444; }
        body { background: var(--bg); color: var(--text); min-height: 100vh; display: flex; justify-content: center; align-items: center; padding: 20px; }
        .container { width: 100%; max-width: 480px; background: var(--surface); border-radius: 24px; border: 1px solid rgba(255,255,255,0.06); overflow: hidden; box-shadow: 0 25px 50px -12px rgba(0,0,0,0.5); }
        .header { background: linear-gradient(135deg, var(--primary) 0%, var(--primary-dark) 100%); padding: 40px 30px; text-align: center; }
        .logo { font-size: 32px; font-weight: 800; letter-spacing: 4px; margin-bottom: 8px; }
        .tagline { font-size: 12px; opacity: 0.8; letter-spacing: 2px; text-transform: uppercase; }
        .content { padding: 30px; }
        .status-bar { display: flex; align-items: center; justify-content: center; gap: 8px; padding: 12px; background: rgba(34, 197, 94, 0.1); border-radius: 12px; margin-bottom: 24px; font-size: 12px; color: var(--success); }
        .status-bar.offline { background: rgba(239, 68, 68, 0.1); color: var(--error); }
        .status-dot { width: 8px; height: 8px; background: currentColor; border-radius: 50%; animation: pulse 2s infinite; }
        @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.5; } }
        .section-title { font-size: 11px; text-transform: uppercase; letter-spacing: 2px; color: var(--text-muted); margin-bottom: 12px; font-weight: 600; }
        .key-input { width: 100%; padding: 16px 20px; background: var(--bg); border: 1px solid rgba(255,255,255,0.1); border-radius: 16px; color: var(--text); font-size: 18px; letter-spacing: 4px; text-align: center; text-transform: uppercase; transition: all 0.3s; outline: none; }
        .key-input:focus { border-color: var(--primary); box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.1); }
        .btn { width: 100%; padding: 16px; background: var(--primary); color: white; border: none; border-radius: 16px; font-size: 14px; font-weight: 600; cursor: pointer; margin-top: 12px; text-transform: uppercase; letter-spacing: 1px; }
        .btn:hover { background: var(--primary-dark); transform: translateY(-2px); }
        .btn:disabled { opacity: 0.5; cursor: not-allowed; }
        .message { margin-top: 16px; padding: 16px; border-radius: 12px; font-size: 13px; text-align: center; display: none; }
        .message.show { display: block; }
        .message.success { background: rgba(34, 197, 94, 0.1); color: var(--success); border: 1px solid rgba(34, 197, 94, 0.2); }
        .message.error { background: rgba(239, 68, 68, 0.1); color: var(--error); border: 1px solid rgba(239, 68, 68, 0.2); }
        .key-info { background: var(--bg); border-radius: 16px; padding: 20px; margin-top: 16px; display: none; }
        .key-info.show { display: block; }
        .info-row { display: flex; justify-content: space-between; padding: 8px 0; border-bottom: 1px solid rgba(255,255,255,0.05); font-size: 13px; }
        .info-label { color: var(--text-muted); }
        .info-value { color: var(--text); font-weight: 600; }
        .footer { text-align: center; padding: 20px; font-size: 11px; color: var(--text-muted); border-top: 1px solid rgba(255,255,255,0.05); }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div class="logo">ATLAS</div>
            <div class="tagline">Key Authentication System</div>
        </div>
        <div class="content">
            <div class="status-bar" id="statusBar">
                <div class="status-dot"></div>
                <span id="statusText">Connecting...</span>
            </div>
            <div class="section">
                <div class="section-title">Enter License Key</div>
                <input type="text" class="key-input" id="keyInput" placeholder="XXXX-XXXX-XXXX-XXXX-XXXX-XXXX" maxlength="35">
                <button class="btn" id="validateBtn" onclick="validateKey()">Validate Key</button>
                <div class="message" id="message"></div>
                <div class="key-info" id="keyInfo">
                    <div class="info-row"><span class="info-label">Status</span><span class="info-value" style="color: var(--success)">Active</span></div>
                    <div class="info-row"><span class="info-label">Duration</span><span class="info-value" id="infoDuration">7 Days</span></div>
                    <div class="info-row"><span class="info-label">Time Remaining</span><span class="info-value" id="infoTime">6 days</span></div>
                    <div class="info-row"><span class="info-label">Activations</span><span class="info-value" id="infoActivations">1</span></div>
                </div>
            </div>
        </div>
        <div class="footer">Secure Cloud Authentication • HWID Protected</div>
    </div>
    <script>
        const keyInput = document.getElementById('keyInput');
        keyInput.addEventListener('input', (e) => {
            let value = e.target.value.replace(/-/g, '').toUpperCase();
            let formatted = '';
            for (let i = 0; i < value.length && i < 24; i++) {
                if (i > 0 && i % 4 === 0) formatted += '-';
                formatted += value[i];
            }
            e.target.value = formatted;
        });
        async function checkStatus() {
            try {
                const res = await fetch('/api/status');
                const data = await res.json();
                document.getElementById('statusBar').className = 'status-bar';
                document.getElementById('statusText').textContent = `Server Online • ${data.keys_total} keys`;
            } catch {
                document.getElementById('statusBar').className = 'status-bar offline';
                document.getElementById('statusText').textContent = 'Server Offline';
            }
        }
        checkStatus();
        setInterval(checkStatus, 10000);
        async function validateKey() {
            const key = keyInput.value.trim();
            if (key.length < 24) {
                showMessage('Please enter complete key', 'error');
                return;
            }
            const hwid = Math.random().toString(36).substring(2, 15);
            const res = await fetch('/api/validate', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({key: key, hwid: hwid})
            });
            const data = await res.json();
            if (data.valid) {
                showMessage('✓ Key validated', 'success');
                showKeyInfo(data);
            } else {
                showMessage('✗ ' + data.message, 'error');
            }
        }
        function showMessage(text, type) {
            const msg = document.getElementById('message');
            msg.textContent = text;
            msg.className = 'message ' + type + ' show';
            setTimeout(() => msg.classList.remove('show'), 5000);
        }
        function showKeyInfo(data) {
            const info = document.getElementById('keyInfo');
            const durationMap = {'1hour': '1 Hour', '1day': '1 Day', '7days': '7 Days', '30days': '30 Days', '365days': '1 Year', 'lifetime': 'Lifetime'};
            document.getElementById('infoDuration').textContent = durationMap[data.duration] || data.duration;
            let timeText = data.days_left > 0 ? data.days_left + ' days' : (data.hours_left ? data.hours_left + ' hours' : 'Expired');
            document.getElementById('infoTime').textContent = timeText;
            document.getElementById('infoActivations').textContent = data.activations;
            info.classList.add('show');
        }
    </script>
</body>
</html>
"""

ADMIN_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>ATLAS Admin</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; font-family: 'SF Pro Display', -apple-system, sans-serif; }
        body { background: #0a0a0f; color: #f1f1f4; padding: 20px; line-height: 1.6; }
        .container { max-width: 1200px; margin: 0 auto; }
        h1 { font-size: 28px; background: linear-gradient(135deg, #6366f1, #8b5cf6); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
        .subtitle { color: #6b6b7b; margin-bottom: 30px; }
        .stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px; margin-bottom: 30px; }
        .stat-card { background: #141418; border: 1px solid rgba(255,255,255,0.06); border-radius: 16px; padding: 24px; text-align: center; }
        .stat-value { font-size: 36px; font-weight: 700; color: #6366f1; }
        .stat-label { font-size: 12px; color: #6b6b7b; text-transform: uppercase; }
        .panel { background: #141418; border: 1px solid rgba(255,255,255,0.06); border-radius: 16px; padding: 24px; margin-bottom: 20px; }
        .panel h2 { font-size: 14px; text-transform: uppercase; letter-spacing: 2px; color: #6b6b7b; margin-bottom: 20px; }
        .form-row { display: flex; gap: 12px; margin-bottom: 16px; flex-wrap: wrap; }
        input, select { flex: 1; min-width: 150px; padding: 12px 16px; background: #0a0a0f; border: 1px solid rgba(255,255,255,0.1); border-radius: 12px; color: #f1f1f4; }
        button { padding: 12px 24px; background: #6366f1; color: white; border: none; border-radius: 12px; font-weight: 600; cursor: pointer; }
        button:hover { background: #4f46e5; }
        button.secondary { background: rgba(255,255,255,0.1); }
        button.danger { background: #ef4444; }
        .key-list { max-height: 500px; overflow-y: auto; border-radius: 12px; background: #0a0a0f; }
        .key-item { display: flex; justify-content: space-between; align-items: center; padding: 16px; border-bottom: 1px solid rgba(255,255,255,0.05); }
        .key-code { font-family: monospace; font-size: 14px; color: #6366f1; }
        .key-meta { font-size: 12px; color: #6b6b7b; }
        .badge { display: inline-block; padding: 4px 12px; border-radius: 20px; font-size: 11px; font-weight: 600; margin-left: 8px; }
        .badge-unused { background: rgba(34, 197, 94, 0.2); color: #22c55e; }
        .badge-used { background: rgba(245, 158, 11, 0.2); color: #f59e0b; }
        .badge-expired { background: rgba(239, 68, 68, 0.2); color: #ef4444; }
        .generated-keys { background: #0a0a0f; border-radius: 12px; padding: 16px; margin-top: 16px; font-family: monospace; display: none; }
        .generated-keys.show { display: block; }
    </style>
</head>
<body>
    <div class="container">
        <h1>ATLAS Admin</h1>
        <p class="subtitle">Key Management Dashboard</p>
        <div class="stats-grid">
            <div class="stat-card"><div class="stat-value" id="statTotal">0</div><div class="stat-label">Total Keys</div></div>
            <div class="stat-card"><div class="stat-value" id="statUsed">0</div><div class="stat-label">Used</div></div>
            <div class="stat-card"><div class="stat-value" id="statAvailable">0</div><div class="stat-label">Available</div></div>
            <div class="stat-card"><div class="stat-value" id="statExpired">0</div><div class="stat-label">Expired</div></div>
        </div>
        <div class="panel">
            <h2>Generate Keys</h2>
            <div class="form-row">
                <input type="number" id="genCount" value="5" min="1" max="100">
                <select id="genDuration">
                    <option value="1hour">1 Hour</option>
                    <option value="1day">1 Day</option>
                    <option value="7days" selected>7 Days</option>
                    <option value="30days">30 Days</option>
                    <option value="365days">365 Days</option>
                    <option value="lifetime">Lifetime</option>
                </select>
                <button onclick="generateKeys()">Generate</button>
            </div>
            <div class="generated-keys" id="generatedBox"></div>
        </div>
        <div class="panel">
            <h2>Data Safety</h2>
            <div class="form-row">
                <button class="secondary" onclick="backupNow()">🛡️ Backup Now</button>
                <button class="secondary" onclick="loadKeys()">Refresh</button>
            </div>
            <div id="backupStatus" style="margin-top:10px;font-size:12px;color:#6b6b7b;"></div>
        </div>
        <div class="panel">
            <h2>All Keys</h2>
            <div class="key-list" id="keyList"></div>
        </div>
    </div>
    <script>
        async function loadStats() {
            const res = await fetch('/admin/api/stats');
            const data = await res.json();
            document.getElementById('statTotal').textContent = data.total;
            document.getElementById('statUsed').textContent = data.used;
            document.getElementById('statAvailable').textContent = data.available;
            document.getElementById('statExpired').textContent = data.expired;
        }
        async function generateKeys() {
            const count = document.getElementById('genCount').value;
            const duration = document.getElementById('genDuration').value;
            const res = await fetch('/admin/api/generate', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({count: parseInt(count), duration: duration})
            });
            const data = await res.json();
            const box = document.getElementById('generatedBox');
            box.innerHTML = data.keys.join('<br>');
            box.classList.add('show');
            loadStats();
            loadKeys();
        }
        async function backupNow() {
            const status = document.getElementById('backupStatus');
            status.textContent = 'Creating backup...';
            const res = await fetch('/admin/api/backup', {method: 'POST'});
            const data = await res.json();
            status.textContent = data.success ? '✅ Backup created!' : '❌ Backup failed';
            setTimeout(() => status.textContent = '', 3000);
        }
        async function loadKeys() {
            const res = await fetch('/admin/api/keys');
            const keys = await res.json();
            const list = document.getElementById('keyList');
            list.innerHTML = Object.entries(keys).sort((a,b) => new Date(b[1].created) - new Date(a[1].created)).map(([key, data]) => {
                const now = new Date();
                const expiry = new Date(data.expiry);
                const isExpired = expiry < now;
                let status = data.used ? (isExpired ? 'expired' : 'used') : 'unused';
                let statusText = data.used ? (isExpired ? 'Expired' : 'Active') : 'Unused';
                return `<div class="key-item"><div class="key-info"><div class="key-code">${key} <span class="badge badge-${status}">${statusText}</span></div><div class="key-meta">Created: ${new Date(data.created).toLocaleDateString()} | Expires: ${expiry.toLocaleDateString()}</div></div><button class="danger" onclick="deleteKey('${key}')">Delete</button></div>`;
            }).join('');
        }
        async function deleteKey(key) {
            if (!confirm('Delete this key?')) return;
            await fetch('/admin/api/delete/' + key, {method: 'DELETE'});
            loadKeys();
            loadStats();
        }
        loadStats();
        loadKeys();
        setInterval(() => { loadStats(); loadKeys(); }, 30000);
    </script>
</body>
</html>
"""

# ============================================================================
# STARTUP
# ============================================================================

if __name__ == '__main__':
    ensure_dirs()
    load_data()

    threading.Thread(target=auto_save_worker, daemon=True).start()

    port = int(os.environ.get('PORT', 10000))
    print(f"\n🚀 ATLAS Key System (BULLETPROOF) starting on port {port}")
    print(f"📊 Admin panel: http://localhost:{port}/admin")
    print(f"🔑 Default admin: {ADMIN_USER} / {'*' * len(ADMIN_PASS)}")
    print(f"💾 Data directory: {BASE_DIR}")
    print(f"📁 Backup directory: {BACKUP_DIR}")
    print(f"\n⚡ PERSISTENCE FEATURES:")
    print(f"   ✓ Immediate save on every change")
    print(f"   ✓ Atomic file writes (crash-proof)")
    print(f"   ✓ Automatic .bak files")
    print(f"   ✓ Graceful shutdown handling")
    print(f"   ✓ Corruption auto-recovery")
    print(f"\nPress Ctrl+C to stop (data will be saved)\n")

    try:
        app.run(host='0.0.0.0', port=port, threaded=True)
    except KeyboardInterrupt:
        emergency_save()