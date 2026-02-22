#!/usr/bin/env python3
"""
ATLAS R6-SCRIPT - UNIFIED APP
One app that does EVERYTHING:
- Serves the recoil GUI at /
- Provides key validation API at /api/validate
- Admin panel at /admin
- All in one service!
"""

import os
import json
import secrets
import hashlib
import time
from datetime import datetime, timedelta
from flask import Flask, render_template, jsonify, request, session, redirect, url_for
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

def load_keys():
    """Load keys from file if exists"""
    global KEYS
    try:
        if os.path.exists(KEY_FILE):
            with open(KEY_FILE, 'r') as f:
                KEYS = json.load(f)
            print(f"✅ Loaded {len(KEYS)} keys")
        else:
            # Create default keys
            create_default_keys()
    except Exception as e:
        print(f"❌ Error loading keys: {e}")
        KEYS = {}

def save_keys():
    """Save keys to file"""
    try:
        with open(KEY_FILE, 'w') as f:
            json.dump(KEYS, f, indent=2)
        return True
    except:
        return False

def create_default_keys():
    """Create some default keys for testing"""
    global KEYS
    KEYS = {
        "7D21-9A4F-8E67-3B2C-1D5F-9A8E": {
            "expiry": (datetime.now() + timedelta(days=7)).isoformat(),
            "used": False,
            "hwid": None,
            "created": datetime.now().isoformat(),
            "duration": "7days"
        },
        "30D1-8C4F-2E7B-9A3D-5F6C-1B9E": {
            "expiry": (datetime.now() + timedelta(days=30)).isoformat(),
            "used": False,
            "hwid": None,
            "created": datetime.now().isoformat(),
            "duration": "30days"
        },
        "365D-1A2B-3C4D-5E6F-7A8B-9C0D": {
            "expiry": (datetime.now() + timedelta(days=365)).isoformat(),
            "used": False,
            "hwid": None,
            "created": datetime.now().isoformat(),
            "duration": "365days"
        }
    }
    save_keys()

# Load keys on startup
load_keys()

# ============================================================================
# LOGIN DECORATOR FOR ADMIN
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
# PUBLIC ROUTES (No login required)
# ============================================================================

@app.route('/')
def index():
    """Main GUI - Your recoil menu"""
    try:
        return render_template('index.html')
    except Exception as e:
        return f"Error loading template: {e}"

@app.route('/api/status')
def status():
    """API status check"""
    return jsonify({
        'status': 'online',
        'time': datetime.now().isoformat(),
        'keys_loaded': len(KEYS)
    })

@app.route('/api/validate', methods=['POST'])
def validate_key():
    """Key validation API - Used by your local app"""
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
        save_keys()
    
    return jsonify({
        'valid': True,
        'message': 'Key valid',
        'expiry': key_data['expiry']
    })

# ============================================================================
# ADMIN ROUTES (Login required)
# ============================================================================

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Admin login page"""
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

@app.route('/admin')
@login_required
def admin_panel():
    """Admin panel - Key management"""
    return render_template_string(ADMIN_HTML)

# ============================================================================
# ADMIN API (Login required)
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
    days = int(data.get('days', 7))
    
    new_keys = []
    expiry = (datetime.now() + timedelta(days=days)).isoformat()
    
    for i in range(count):
        key = '-'.join([secrets.token_hex(2).upper() for _ in range(6)])
        KEYS[key] = {
            'expiry': expiry,
            'used': False,
            'hwid': None,
            'created': datetime.now().isoformat(),
            'duration': f"{days}days"
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

@app.route('/admin/api/stats', methods=['GET'])
@login_required
def admin_stats():
    total = len(KEYS)
    used = sum(1 for k in KEYS if KEYS[k].get('used', False))
    expired = sum(1 for k in KEYS if datetime.fromisoformat(KEYS[k]['expiry']) < datetime.now())
    return jsonify({'total': total, 'used': used, 'available': total - used, 'expired': expired})

# ============================================================================
# ADMIN HTML
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
            grid-template-columns: repeat(4,1fr);
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
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🔑 ATLAS KEY ADMIN</h1>
            <a href="/logout" class="logout-btn">Logout</a>
        </div>
        
        <div class="stats" id="stats">
            <div class="stat-card"><div class="stat-value" id="total">0</div><div>Total Keys</div></div>
            <div class="stat-card"><div class="stat-value" id="used">0</div><div>Used</div></div>
            <div class="stat-card"><div class="stat-value" id="available">0</div><div>Available</div></div>
            <div class="stat-card"><div class="stat-value" id="expired">0</div><div>Expired</div></div>
        </div>
        
        <div class="panel">
            <h2>⚡ Generate Keys</h2>
            <input type="number" id="count" value="5" min="1" max="100">
            <select id="days">
                <option value="7">7 Days</option>
                <option value="30">30 Days</option>
                <option value="365">1 Year</option>
            </select>
            <button onclick="generate()">Generate Keys</button>
            <div id="generated" class="generated" style="display:none;"></div>
        </div>
        
        <div class="panel">
            <h2>📋 All Keys</h2>
            <div class="key-list" id="keyList"></div>
        </div>
    </div>
    
    <script>
        async function loadStats() {
            const res = await fetch('/admin/api/stats');
            const data = await res.json();
            document.getElementById('total').textContent = data.total;
            document.getElementById('used').textContent = data.used;
            document.getElementById('available').textContent = data.available;
            document.getElementById('expired').textContent = data.expired;
        }
        
        async function loadKeys() {
            const res = await fetch('/admin/api/keys');
            const keys = await res.json();
            const list = document.getElementById('keyList');
            list.innerHTML = '';
            
            Object.entries(keys).sort((a,b) => new Date(b[1].created) - new Date(a[1].created)).forEach(([key, data]) => {
                const div = document.createElement('div');
                div.className = 'key-item';
                
                const status = data.used ? 'USED' : 'AVAILABLE';
                const statusColor = data.used ? '#ffaa00' : '#00ff00';
                const expiryDate = new Date(data.expiry).toLocaleDateString();
                
                div.innerHTML = `
                    <div>
                        <div style="color:#00ffff; font-family:monospace; font-size:16px;">${key}</div>
                        <div style="margin-top:5px;">
                            <span style="color:${statusColor};">${status}</span>
                            <span style="color:#a0b0c0; margin-left:10px;">Exp: ${expiryDate}</span>
                            ${data.hwid ? `<span style="color:#ffaa00; margin-left:10px;">HWID: ${data.hwid.substring(0,8)}...</span>` : ''}
                        </div>
                    </div>
                    <button onclick="deleteKey('${key}')" style="background:#ff6464;">Delete</button>
                `;
                list.appendChild(div);
            });
        }
        
        async function generate() {
            const count = document.getElementById('count').value;
            const days = document.getElementById('days').value;
            
            const res = await fetch('/admin/api/generate', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({count: parseInt(count), days: parseInt(days)})
            });
            
            const data = await res.json();
            const generatedDiv = document.getElementById('generated');
            generatedDiv.style.display = 'block';
            generatedDiv.innerHTML = '✅ Generated ' + data.keys.length + ' keys:<br>' + data.keys.join('<br>');
            
            loadStats();
            loadKeys();
            
            setTimeout(() => {
                generatedDiv.style.display = 'none';
            }, 10000);
        }
        
        async function deleteKey(key) {
            if (confirm('Permanently delete this key?')) {
                await fetch('/admin/api/delete/' + key, {method: 'DELETE'});
                loadKeys();
                loadStats();
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
    print(f"🚀 ATLAS UNIFIED APP")
    print(f"{'='*50}")
    print(f"🌐 GUI: http://localhost:{port}/")
    print(f"🔑 API: http://localhost:{port}/api/validate")
    print(f"👑 Admin: http://localhost:{port}/login")
    print(f"📁 Keys loaded: {len(KEYS)}")
    print(f"{'='*50}\n")
    app.run(host='0.0.0.0', port=port, debug=False)