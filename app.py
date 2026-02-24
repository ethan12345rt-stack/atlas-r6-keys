#!/usr/bin/env python3
"""
ATLAS R6-SCRIPT - CLOUD SERVER WITH DAY KEY + 2 MIN TEST KEY
"""

import os
import json
import secrets
import hashlib
from datetime import datetime, timedelta
from flask import Flask, render_template, render_template_string, jsonify, request, session, redirect, url_for
from flask_cors import CORS
from functools import wraps

# ============================================================================
# INIT
# ============================================================================
app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', secrets.token_hex(32))
CORS(app)

# ============================================================================
# KEY DATABASE
# ============================================================================
KEYS = {}
KEY_FILE = 'keys.json'

# ============================================================================
# PROFILES DATABASE - Store user profiles by HWID
# ============================================================================
USER_PROFILES = {}
PROFILES_FILE = 'profiles.json'

def load_keys():
    global KEYS
    try:
        if os.path.exists(KEY_FILE):
            with open(KEY_FILE, 'r') as f:
                KEYS = json.load(f)
            print(f"✅ Loaded {len(KEYS)} keys")
        else:
            create_default_keys()
    except Exception as e:
        print(f"❌ Error loading keys: {e}")
        KEYS = {}

def save_keys():
    try:
        with open(KEY_FILE, 'w') as f:
            json.dump(KEYS, f, indent=2)
        return True
    except:
        return False

def load_profiles():
    """Load user profiles from file"""
    global USER_PROFILES
    try:
        if os.path.exists(PROFILES_FILE):
            with open(PROFILES_FILE, 'r') as f:
                USER_PROFILES = json.load(f)
            print(f"✅ Loaded profiles for {len(USER_PROFILES)} users")
        else:
            USER_PROFILES = {}
    except Exception as e:
        print(f"❌ Error loading profiles: {e}")
        USER_PROFILES = {}

def save_profiles():
    """Save user profiles to file"""
    try:
        with open(PROFILES_FILE, 'w') as f:
            json.dump(USER_PROFILES, f, indent=2)
        return True
    except Exception as e:
        print(f"❌ Error saving profiles: {e}")
        return False

def create_default_keys():
    global KEYS
    KEYS = {
        # 7 Day Key
        "7D21-9A4F-8E67-3B2C-1D5F-9A8E": {
            "expiry": (datetime.now() + timedelta(days=7)).isoformat(),
            "used": False,
            "hwid": None,
            "created": datetime.now().isoformat(),
            "duration": "7days"
        },
        # 30 Day Key
        "30D1-8C4F-2E7B-9A3D-5F6C-1B9E": {
            "expiry": (datetime.now() + timedelta(days=30)).isoformat(),
            "used": False,
            "hwid": None,
            "created": datetime.now().isoformat(),
            "duration": "30days"
        },
        # 1 Year Key
        "365D-1A2B-3C4D-5E6F-7A8B-9C0D": {
            "expiry": (datetime.now() + timedelta(days=365)).isoformat(),
            "used": False,
            "hwid": None,
            "created": datetime.now().isoformat(),
            "duration": "365days"
        }
    }
    save_keys()

# Load data on startup
load_keys()
load_profiles()

# ============================================================================
# LOGIN DECORATOR
# ============================================================================
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "atlas2026"

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# ============================================================================
# PUBLIC ROUTES
# ============================================================================

@app.route('/')
def home():
    return "ATLAS Key Server Online!"

@app.route('/api/status')
def status():
    return jsonify({
        'status': 'online',
        'time': datetime.now().isoformat(),
        'keys_loaded': len(KEYS)
    })

@app.route('/api/validate', methods=['POST'])
def validate_key():
    data = request.json
    key = data.get('key', '').strip().upper()
    hwid = data.get('hwid', '')
    
    if key not in KEYS:
        return jsonify({'valid': False, 'message': 'Invalid key'})
    
    key_data = KEYS[key]
    expiry = datetime.fromisoformat(key_data['expiry'])
    
    if expiry < datetime.now():
        return jsonify({'valid': False, 'message': 'Key expired'})
    
    if key_data['used'] and key_data['hwid'] != hwid:
        return jsonify({'valid': False, 'message': 'Key already in use'})
    
    if not key_data['used']:
        key_data['used'] = True
        key_data['hwid'] = hwid
        key_data['activated_date'] = datetime.now().isoformat()
        key_data['activation_count'] = key_data.get('activation_count', 0) + 1
        save_keys()
    
    return jsonify({
        'valid': True,
        'message': 'Key valid',
        'expiry': key_data['expiry']
    })

# ============================================================================
# PROFILE API
# ============================================================================

@app.route('/api/profiles/<hwid>', methods=['GET'])
def get_profiles(hwid):
    """Get all profiles for a user"""
    if hwid in USER_PROFILES:
        return jsonify(USER_PROFILES[hwid])
    return jsonify({})

@app.route('/api/profiles/<hwid>/save', methods=['POST'])
def save_profile(hwid):
    """Save a profile for a user"""
    data = request.json
    name = data.get('name')
    profile_data = data.get('data')
    
    if not name or not profile_data:
        return jsonify({'success': False, 'error': 'Missing data'}), 400
    
    if hwid not in USER_PROFILES:
        USER_PROFILES[hwid] = {}
    
    USER_PROFILES[hwid][name] = {
        'data': profile_data,
        'created': datetime.now().isoformat(),
        'updated': datetime.now().isoformat()
    }
    
    save_profiles()
    return jsonify({'success': True})

@app.route('/api/profiles/<hwid>/delete', methods=['POST'])
def delete_profile(hwid):
    """Delete a profile"""
    data = request.json
    name = data.get('name')
    
    if hwid in USER_PROFILES and name in USER_PROFILES[hwid]:
        del USER_PROFILES[hwid][name]
        save_profiles()
        return jsonify({'success': True})
    
    return jsonify({'success': False}), 404

# ============================================================================
# ADMIN LOGIN ROUTES
# ============================================================================

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            session['logged_in'] = True
            return redirect(url_for('admin_panel'))
        else:
            return '''
            <html>
            <head><title>Login Failed</title></head>
            <body style="background:#0a0f1e; color:#ff0000; font-family:monospace; padding:20px;">
                <h1>❌ Login Failed</h1>
                <a href="/login" style="color:#00ffff;">Try again</a>
            </body>
            </html>
            '''
    
    # Login form
    return '''
    <!DOCTYPE html>
    <html>
    <head>
        <title>ATLAS Admin Login</title>
        <style>
            * { margin:0; padding:0; box-sizing:border-box; font-family:monospace; }
            body { 
                background: linear-gradient(135deg, #0a0f1e 0%, #001520 100%);
                min-height: 100vh;
                display: flex;
                justify-content: center;
                align-items: center;
            }
            .login-box { 
                background: rgba(10, 20, 30, 0.98);
                border: 2px solid #00ffff;
                border-radius: 10px;
                padding: 40px;
                width: 400px;
                box-shadow: 0 0 50px rgba(0, 255, 255, 0.5);
            }
            h1 { 
                color: #00ffff;
                text-align: center;
                margin-bottom: 30px;
            }
            input { 
                width: 100%;
                padding: 12px;
                margin: 10px 0;
                background: #1a2a30;
                border: 1px solid #00ffff;
                color: #00ffff;
                border-radius: 4px;
                font-size: 16px;
            }
            button { 
                width: 100%;
                padding: 12px;
                background: #00ffff;
                color: #0a0f1e;
                border: none;
                border-radius: 4px;
                font-size: 18px;
                font-weight: bold;
                cursor: pointer;
                margin-top: 20px;
            }
            button:hover {
                background: #ffffff;
                box-shadow: 0 0 20px #00ffff;
            }
        </style>
    </head>
    <body>
        <div class="login-box">
            <h1>🔐 ATLAS ADMIN</h1>
            <form method="POST">
                <input type="text" name="username" placeholder="Username" required>
                <input type="password" name="password" placeholder="Password" required>
                <button type="submit">Login</button>
            </form>
        </div>
    </body>
    </html>
    '''

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    return redirect(url_for('login'))

# ============================================================================
# ADMIN PANEL
# ============================================================================

@app.route('/admin')
@login_required
def admin_panel():
    return render_template_string(ADMIN_HTML)

# ============================================================================
# ADMIN API
# ============================================================================

@app.route('/admin/api/keys', methods=['GET'])
@login_required
def admin_get_keys():
    return jsonify(KEYS)

@app.route('/admin/api/generate', methods=['POST'])
@login_required
def admin_generate_keys():
    data = request.json
    count = int(data.get('count', 5))
    duration = data.get('duration', '7days')  # '2min', '1day', '7days', '30days', '365days'
    
    new_keys = []
    
    # Set expiry based on duration
    if duration == '2min':
        expiry = (datetime.now() + timedelta(minutes=2)).isoformat()
    elif duration == '1day':
        expiry = (datetime.now() + timedelta(days=1)).isoformat()
    elif duration == '7days':
        expiry = (datetime.now() + timedelta(days=7)).isoformat()
    elif duration == '30days':
        expiry = (datetime.now() + timedelta(days=30)).isoformat()
    elif duration == '365days':
        expiry = (datetime.now() + timedelta(days=365)).isoformat()
    else:
        expiry = (datetime.now() + timedelta(days=7)).isoformat()
    
    for i in range(count):
        key = '-'.join([secrets.token_hex(2).upper() for _ in range(6)])
        KEYS[key] = {
            'expiry': expiry,
            'used': False,
            'hwid': None,
            'created': datetime.now().isoformat(),
            'duration': duration
        }
        new_keys.append(key)
    
    save_keys()
    return jsonify({'success': True, 'keys': new_keys})

@app.route('/admin/api/delete/<key>', methods=['DELETE'])
@login_required
def admin_delete_key(key):
    if key in KEYS:
        del KEYS[key]
        save_keys()
        return jsonify({'success': True})
    return jsonify({'success': False}), 404

@app.route('/admin/api/reset-all', methods=['POST'])
@login_required
def admin_reset_all():
    """Reset ALL keys - emergency use"""
    data = request.json
    confirm = data.get('confirm', '')
    
    if confirm != 'DELETE ALL':
        return jsonify({'success': False, 'message': 'Confirmation required'}), 400
    
    count = len(KEYS)
    KEYS.clear()
    save_keys()
    
    return jsonify({
        'success': True,
        'message': f'All {count} keys have been deleted'
    })

@app.route('/admin/api/reset-expired', methods=['POST'])
@login_required
def admin_reset_expired():
    """Delete all expired keys"""
    now = datetime.now()
    expired = []
    
    for key, data in list(KEYS.items()):
        try:
            expiry = datetime.fromisoformat(data['expiry'])
            if expiry < now:
                expired.append(key)
                del KEYS[key]
        except:
            pass
    
    save_keys()
    
    return jsonify({
        'success': True,
        'message': f'Deleted {len(expired)} expired keys',
        'count': len(expired)
    })

@app.route('/admin/api/stats', methods=['GET'])
@login_required
def admin_stats():
    total = len(KEYS)
    used = sum(1 for k in KEYS if KEYS[k].get('used', False))
    expired = sum(1 for k in KEYS if datetime.fromisoformat(KEYS[k]['expiry']) < datetime.now())
    
    # Count by duration
    duration_counts = {}
    for key, data in KEYS.items():
        dur = data.get('duration', 'unknown')
        duration_counts[dur] = duration_counts.get(dur, 0) + 1
    
    return jsonify({
        'total': total,
        'used': used,
        'available': total - used,
        'expired': expired,
        'duration_counts': duration_counts
    })

# ============================================================================
# ADMIN HTML - UPDATED WITH NEW KEY TYPES
# ============================================================================

ADMIN_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>ATLAS Admin</title>
    <style>
        * { margin:0; padding:0; box-sizing:border-box; font-family:monospace; }
        body { 
            background: linear-gradient(135deg, #0a0f1e 0%, #001520 100%);
            padding:20px;
            min-height: 100vh;
        }
        .container { max-width:1200px; margin:0 auto; }
        .header { 
            background: rgba(0,255,255,0.1);
            border: 2px solid #00ffff;
            border-radius: 10px;
            padding: 20px;
            margin-bottom: 20px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        h1 { color:#00ffff; }
        .stats { 
            display: grid;
            grid-template-columns: repeat(5,1fr);
            gap: 15px;
            margin-bottom: 20px;
        }
        .stat-card { 
            background: rgba(0,255,255,0.05);
            border: 1px solid #00ffff;
            border-radius: 8px;
            padding: 20px;
            text-align: center;
        }
        .stat-value { 
            color:#00ffff; 
            font-size:32px; 
            font-weight:bold;
        }
        .panel { 
            background: rgba(0,0,0,0.5);
            border: 1px solid #00ffff;
            border-radius: 8px;
            padding: 20px;
            margin-bottom: 20px;
        }
        h2 { color:#00ffff; margin-bottom: 15px; }
        input, select { 
            width: 100%;
            padding: 10px;
            margin: 10px 0;
            background: #1a2a30;
            border: 1px solid #00ffff;
            color: #00ffff;
            border-radius: 4px;
        }
        button { 
            background: #00ffff;
            color: #0a0f1e;
            border: none;
            padding: 10px 20px;
            border-radius: 4px;
            cursor: pointer;
            font-weight: bold;
            margin: 5px;
        }
        button:hover {
            background: #ffffff;
            box-shadow: 0 0 20px #00ffff;
        }
        button.danger {
            background: #ff6464;
        }
        button.warning {
            background: #ffaa00;
        }
        .key-list { 
            max-height:400px; 
            overflow-y:auto; 
            border:1px solid #00ffff40;
            border-radius: 4px;
        }
        .key-item { 
            display:flex; 
            justify-content:space-between; 
            align-items:center;
            padding:15px; 
            border-bottom:1px solid #00ffff20; 
            color:#fff;
        }
        .key-item:hover {
            background: rgba(0,255,255,0.1);
        }
        .key-item.test-key {
            border-left: 4px solid #ffaa00;
            background: rgba(255,170,0,0.05);
        }
        .key-item.day-key {
            border-left: 4px solid #00ff00;
            background: rgba(0,255,0,0.05);
        }
        .badge {
            display: inline-block;
            padding: 3px 8px;
            border-radius: 4px;
            font-size: 11px;
            font-weight: bold;
            margin-left: 10px;
        }
        .badge.test { background: #ffaa00; color: #000; }
        .badge.day { background: #00ff00; color: #000; }
        .badge.week { background: #00ffff; color: #000; }
        .badge.month { background: #aa00ff; color: #fff; }
        .badge.year { background: #ff00ff; color: #fff; }
        .logout-btn { 
            background: #ff6464;
            color: #0a0f1e;
            text-decoration: none;
            padding: 10px 20px;
            border-radius: 4px;
            font-weight: bold;
        }
        .generated {
            margin-top: 10px;
            padding: 10px;
            background: rgba(0,255,0,0.1);
            border: 1px solid #00ff00;
            border-radius: 4px;
            color: #00ff00;
            max-height: 200px;
            overflow-y: auto;
        }
        .flex-row {
            display: flex;
            gap: 10px;
            align-items: center;
        }
        .duration-stats {
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
            margin-top: 10px;
        }
        .duration-badge {
            padding: 5px 10px;
            border-radius: 20px;
            font-size: 12px;
            font-weight: bold;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🔑 ATLAS KEY ADMIN</h1>
            <div>
                <span style="color:#00ffff; margin-right:15px;">2min test keys now available!</span>
                <a href="/logout" class="logout-btn">Logout</a>
            </div>
        </div>
        
        <div class="stats" id="stats">
            <div class="stat-card"><div class="stat-value" id="total">0</div><div>Total Keys</div></div>
            <div class="stat-card"><div class="stat-value" id="used">0</div><div>Used Keys</div></div>
            <div class="stat-card"><div class="stat-value" id="available">0</div><div>Available</div></div>
            <div class="stat-card"><div class="stat-value" id="expired">0</div><div>Expired</div></div>
            <div class="stat-card"><div class="stat-value" id="testKeys">0</div><div>Test Keys</div></div>
        </div>
        
        <div class="panel">
            <h2>⚡ Generate Keys</h2>
            <input type="number" id="count" value="5" min="1" max="100">
            <select id="duration">
                <option value="2min">⏱️ 2 Minutes (TEST KEY)</option>
                <option value="1day">📅 1 Day</option>
                <option value="7days">📅 7 Days</option>
                <option value="30days">📅 30 Days</option>
                <option value="365days">📅 1 Year</option>
            </select>
            <button onclick="generateKeys()">Generate Keys</button>
            <div id="generated" class="generated" style="display:none;"></div>
        </div>
        
        <div class="panel">
            <h2>🔧 Maintenance</h2>
            <div class="flex-row">
                <button class="warning" onclick="resetExpired()">🗑️ Delete Expired Keys</button>
                <button class="danger" onclick="resetAllKeys()">⚠️ DELETE ALL KEYS</button>
            </div>
            <p style="color:#a0b0c0; margin-top:10px;">Use "DELETE ALL" with caution - requires confirmation</p>
        </div>
        
        <div class="panel">
            <h2>📋 All Keys <span style="color:#a0b0c0; font-size:14px;" id="keyCount"></span></h2>
            <div class="key-list" id="keyList"></div>
        </div>
    </div>
    
    <script>
        async function loadStats() {
            try {
                const res = await fetch('/admin/api/stats');
                const data = await res.json();
                document.getElementById('total').textContent = data.total;
                document.getElementById('used').textContent = data.used;
                document.getElementById('available').textContent = data.available;
                document.getElementById('expired').textContent = data.expired;
                
                // Count test keys (2min duration)
                const testCount = data.duration_counts ? (data.duration_counts['2min'] || 0) : 0;
                document.getElementById('testKeys').textContent = testCount;
            } catch (e) {
                console.error('Failed to load stats', e);
            }
        }
        
        async function loadKeys() {
            try {
                const res = await fetch('/admin/api/keys');
                const keys = await res.json();
                const list = document.getElementById('keyList');
                list.innerHTML = '';
                
                let keyCount = 0;
                
                Object.entries(keys).sort((a,b) => new Date(b[1].created) - new Date(a[1].created)).forEach(([key, data]) => {
                    const div = document.createElement('div');
                    div.className = 'key-item';
                    
                    // Add class based on duration
                    if (data.duration === '2min') div.classList.add('test-key');
                    else if (data.duration === '1day') div.classList.add('day-key');
                    
                    const status = data.used ? 'USED' : 'AVAILABLE';
                    const statusColor = data.used ? '#ffaa00' : '#00ff00';
                    const expiryDate = new Date(data.expiry).toLocaleString();
                    
                    // Add badge
                    let badge = '';
                    if (data.duration === '2min') badge = '<span class="badge test">2min TEST</span>';
                    else if (data.duration === '1day') badge = '<span class="badge day">1 DAY</span>';
                    else if (data.duration === '7days') badge = '<span class="badge week">7 DAYS</span>';
                    else if (data.duration === '30days') badge = '<span class="badge month">30 DAYS</span>';
                    else if (data.duration === '365days') badge = '<span class="badge year">1 YEAR</span>';
                    
                    div.innerHTML = `
                        <div>
                            <div style="color:#00ffff; font-family:monospace; font-size:16px;">
                                ${key} ${badge}
                            </div>
                            <div style="margin-top:5px;">
                                <span style="color:${statusColor};">${status}</span>
                                <span style="color:#a0b0c0; margin-left:10px;">Exp: ${expiryDate}</span>
                            </div>
                            ${data.hwid ? `<div style="color:#ffaa00; font-size:11px;">HWID: ${data.hwid.substring(0,16)}...</div>` : ''}
                        </div>
                        <button onclick="deleteKey('${key}')" style="background:#ff6464;">Delete</button>
                    `;
                    list.appendChild(div);
                    keyCount++;
                });
                
                document.getElementById('keyCount').textContent = `(${keyCount} keys)`;
            } catch (e) {
                console.error('Failed to load keys', e);
            }
        }
        
        async function generateKeys() {
            try {
                const count = document.getElementById('count').value;
                const duration = document.getElementById('duration').value;
                
                const res = await fetch('/admin/api/generate', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({count: parseInt(count), duration: duration})
                });
                
                const data = await res.json();
                const generatedDiv = document.getElementById('generated');
                generatedDiv.style.display = 'block';
                
                let durationText = '';
                if (duration === '2min') durationText = '2 MINUTE TEST KEYS';
                else if (duration === '1day') durationText = '1 DAY KEYS';
                else if (duration === '7days') durationText = '7 DAY KEYS';
                else if (duration === '30days') durationText = '30 DAY KEYS';
                else if (duration === '365days') durationText = '1 YEAR KEYS';
                
                generatedDiv.innerHTML = '✅ Generated ' + data.keys.length + ' ' + durationText + ':<br>' + data.keys.join('<br>');
                
                loadStats();
                loadKeys();
                
                setTimeout(() => {
                    generatedDiv.style.display = 'none';
                }, 10000);
            } catch (e) {
                console.error('Failed to generate keys', e);
            }
        }
        
        async function deleteKey(key) {
            if (confirm('Delete this key?')) {
                try {
                    await fetch('/admin/api/delete/' + key, {method: 'DELETE'});
                    loadKeys();
                    loadStats();
                } catch (e) {
                    console.error('Failed to delete key', e);
                }
            }
        }
        
        async function resetExpired() {
            if (confirm('Delete all expired keys?')) {
                try {
                    const res = await fetch('/admin/api/reset-expired', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'}
                    });
                    const data = await res.json();
                    alert(`✅ Deleted ${data.count} expired keys`);
                    loadKeys();
                    loadStats();
                } catch (e) {
                    console.error('Failed to reset expired keys', e);
                }
            }
        }
        
        async function resetAllKeys() {
            const confirmText = prompt('Type "DELETE ALL" to confirm deleting ALL keys:');
            if (confirmText === 'DELETE ALL') {
                try {
                    const res = await fetch('/admin/api/reset-all', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({confirm: 'DELETE ALL'})
                    });
                    const data = await res.json();
                    if (data.success) {
                        alert(`✅ ${data.message}`);
                        loadKeys();
                        loadStats();
                    } else {
                        alert('❌ ' + data.message);
                    }
                } catch (e) {
                    console.error('Failed to reset all keys', e);
                }
            } else {
                alert('❌ Confirmation failed - no keys deleted');
            }
        }
        
        // Load everything
        loadStats();
        loadKeys();
        
        // Refresh every 30 seconds
        setInterval(() => {
            loadStats();
            loadKeys();
        }, 30000);
    </script>
</body>
</html>
"""

# ============================================================================
# RUN
# ============================================================================

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    print(f"\n{'='*50}")
    print(f"🚀 ATLAS CLOUD SERVER")
    print(f"{'='*50}")
    print(f"🔑 Keys loaded: {len(KEYS)}")
    print(f"📁 Profiles loaded: {len(USER_PROFILES)}")
    print(f"👑 Admin login: https://atlas-r6-keys.onrender.com/login")
    print(f"📊 Admin panel: https://atlas-r6-keys.onrender.com/admin")
    print(f"⏱️  2min test keys: AVAILABLE")
    print(f"📅 1 day keys: AVAILABLE")
    print(f"{'='*50}\n")
    app.run(host='0.0.0.0', port=port)