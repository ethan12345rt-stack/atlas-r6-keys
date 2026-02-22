#!/usr/bin/env python3
"""
ATLAS R6-SCRIPT - ADMIN PANEL WITH TABS AND EXTEND
"""

import os
import sys
import json
import secrets
import hashlib
from datetime import datetime, timedelta
from flask import Flask, render_template, render_template_string, jsonify, request, session, redirect, url_for
from flask_cors import CORS
from functools import wraps

# ============================================================================
# DEBUG INFO
# ============================================================================
print("\n" + "="*60)
print("🚀 ATLAS APP STARTING")
print("="*60)
print(f"📁 Current directory: {os.getcwd()}")

# Check templates
templates_path = os.path.join(os.getcwd(), 'templates')
print(f"📁 Templates path: {templates_path}")
print(f"📁 Templates exists: {os.path.exists(templates_path)}")

if os.path.exists(templates_path):
    print(f"📄 Files in templates: {os.listdir(templates_path)}")
print("="*60 + "\n")

# ============================================================================
# INIT FLASK
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
    global KEYS
    try:
        if os.path.exists(KEY_FILE):
            with open(KEY_FILE, 'r') as f:
                KEYS = json.load(f)
            print(f"✅ Loaded {len(KEYS)} keys")
        else:
            print("📄 Creating default keys")
            create_default_keys()
    except Exception as e:
        print(f"❌ Error: {e}")
        create_default_keys()

def save_keys():
    try:
        with open(KEY_FILE, 'w') as f:
            json.dump(KEYS, f, indent=2)
        return True
    except:
        return False

def create_default_keys():
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

load_keys()

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def get_keys_by_duration(days):
    """Get all keys with specific duration"""
    duration_str = f"{days}days"
    return {k: v for k, v in KEYS.items() if v.get('duration') == duration_str}

def extend_key(key, days):
    """Extend a key by specified days"""
    if key in KEYS:
        current_expiry = datetime.fromisoformat(KEYS[key]['expiry'])
        new_expiry = current_expiry + timedelta(days=days)
        KEYS[key]['expiry'] = new_expiry.isoformat()
        KEYS[key]['extended'] = KEYS[key].get('extended', 0) + days
        KEYS[key]['extended_date'] = datetime.now().isoformat()
        save_keys()
        return True
    return False

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
def index():
    try:
        return render_template('index.html')
    except Exception as e:
        return f"Error: {e}<br>Templates: {os.listdir('templates') if os.path.exists('templates') else 'No templates folder'}"

@app.route('/api/status')
def status():
    return jsonify({
        'status': 'online',
        'keys': len(KEYS),
        'templates': os.path.exists('templates')
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
        return jsonify({'valid': False, 'message': 'Key in use'})
    
    if not key_data['used']:
        key_data['used'] = True
        key_data['hwid'] = hwid
        save_keys()
    
    return jsonify({'valid': True, 'message': 'Valid', 'expiry': key_data['expiry']})

# ============================================================================
# ADMIN LOGIN
# ============================================================================

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        if request.form.get('username') == ADMIN_USERNAME and request.form.get('password') == ADMIN_PASSWORD:
            session['logged_in'] = True
            return redirect(url_for('admin'))
        return "Login failed", 401
    
    return '''
    <!DOCTYPE html>
    <html>
    <head>
        <title>ATLAS Login</title>
        <style>
            body { background:#0a0f1e; color:#00ffff; font-family:monospace; display:flex; justify-content:center; align-items:center; height:100vh; }
            .box { background:#1a2a30; padding:40px; border:2px solid #00ffff; border-radius:10px; }
            input { display:block; width:100%; padding:10px; margin:10px 0; background:#0a1a20; border:1px solid #00ffff; color:#00ffff; }
            button { width:100%; padding:10px; background:#00ffff; color:#0a0f1e; border:none; cursor:pointer; }
        </style>
    </head>
    <body>
        <div class="box">
            <h1>🔐 ATLAS ADMIN</h1>
            <form method="POST">
                <input type="text" name="username" placeholder="Username" value="admin">
                <input type="password" name="password" placeholder="Password" value="atlas2026">
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
# ADMIN API - EXTEND KEY
# ============================================================================

@app.route('/admin/api/extend', methods=['POST'])
@login_required
def admin_extend_key():
    """Extend a key by specified days"""
    data = request.json
    key = data.get('key', '').strip().upper()
    days = int(data.get('days', 30))
    
    if key not in KEYS:
        return jsonify({'success': False, 'error': 'Key not found'}), 404
    
    current_expiry = datetime.fromisoformat(KEYS[key]['expiry'])
    new_expiry = current_expiry + timedelta(days=days)
    
    KEYS[key]['expiry'] = new_expiry.isoformat()
    KEYS[key]['extended'] = KEYS[key].get('extended', 0) + days
    KEYS[key]['extended_date'] = datetime.now().isoformat()
    
    save_keys()
    
    return jsonify({
        'success': True,
        'message': f'Key extended by {days} days',
        'new_expiry': new_expiry.isoformat()
    })

# ============================================================================
# ADMIN API - GET KEYS BY DURATION
# ============================================================================

@app.route('/admin/api/keys/<int:days>', methods=['GET'])
@login_required
def admin_get_keys_by_duration(days):
    """Get keys with specific duration"""
    filtered = get_keys_by_duration(days)
    return jsonify(filtered)

# ============================================================================
# ADMIN PANEL - WITH TABS
# ============================================================================

@app.route('/admin')
@login_required
def admin():
    """Admin panel with tabs for different key durations"""
    return f'''
    <!DOCTYPE html>
    <html>
    <head>
        <title>ATLAS Admin</title>
        <style>
            * {{ margin:0; padding:0; box-sizing:border-box; font-family:monospace; }}
            body {{ 
                background: linear-gradient(135deg, #0a0f1e 0%, #001520 100%);
                padding:20px;
            }}
            .container {{ max-width:1400px; margin:0 auto; }}
            .header {{ 
                background: rgba(0,255,255,0.1);
                border: 2px solid #00ffff;
                border-radius: 10px;
                padding: 20px;
                margin-bottom: 20px;
                display: flex;
                justify-content: space-between;
                align-items: center;
            }}
            h1 {{ color:#00ffff; }}
            .stats {{ 
                display: grid;
                grid-template-columns: repeat(4,1fr);
                gap: 15px;
                margin-bottom: 20px;
            }}
            .stat-card {{ 
                background: rgba(0,255,255,0.05);
                border: 1px solid #00ffff;
                border-radius: 8px;
                padding: 20px;
                text-align: center;
            }}
            .stat-value {{ 
                color:#00ffff; 
                font-size:32px; 
                font-weight:bold;
            }}
            .panel {{ 
                background: rgba(0,0,0,0.5);
                border: 1px solid #00ffff;
                border-radius: 8px;
                padding: 20px;
                margin-bottom: 20px;
            }}
            h2 {{ color:#00ffff; margin-bottom: 15px; }}
            .tab-container {{
                display: flex;
                gap: 5px;
                margin-bottom: 20px;
                border-bottom: 1px solid #00ffff40;
            }}
            .tab-btn {{
                flex: 1;
                padding: 12px;
                background: transparent;
                border: none;
                color: #a0b0c0;
                cursor: pointer;
                font-size: 16px;
                font-weight: bold;
                text-transform: uppercase;
                transition: all 0.3s;
            }}
            .tab-btn:hover {{
                color: #00ffff;
            }}
            .tab-btn.active {{
                color: #00ffff;
                border-bottom: 2px solid #00ffff;
            }}
            .tab-content {{
                display: none;
            }}
            .tab-content.active {{
                display: block;
            }}
            .generate-section {{
                display: grid;
                grid-template-columns: 1fr 1fr auto;
                gap: 10px;
                margin-bottom: 20px;
            }}
            input, select {{ 
                padding: 10px;
                background: #1a2a30;
                border: 1px solid #00ffff;
                color: #00ffff;
                border-radius: 4px;
            }}
            button {{ 
                background: #00ffff;
                color: #0a0f1e;
                border: none;
                padding: 10px 20px;
                border-radius: 4px;
                cursor: pointer;
                font-weight: bold;
            }}
            button:hover {{
                background: #ffffff;
                box-shadow: 0 0 20px #00ffff;
            }}
            button.danger {{ background: #ff6464; }}
            button.warning {{ background: #ffaa00; }}
            .key-list {{ 
                max-height:400px; 
                overflow-y:auto; 
                border:1px solid #00ffff40;
                border-radius: 4px;
            }}
            .key-item {{ 
                display:flex; 
                justify-content:space-between; 
                align-items:center;
                padding:15px; 
                border-bottom:1px solid #00ffff20; 
                color:#fff;
            }}
            .key-item:hover {{
                background: rgba(0,255,255,0.1);
            }}
            .key-info {{
                flex: 1;
            }}
            .key-code {{
                color: #00ffff;
                font-size: 16px;
                font-family: monospace;
            }}
            .key-meta {{
                margin-top: 5px;
                font-size: 12px;
                color: #a0b0c0;
            }}
            .key-actions {{
                display: flex;
                gap: 5px;
            }}
            .status-used {{ color: #ffaa00; }}
            .status-available {{ color: #00ff00; }}
            .status-expired {{ color: #ff6464; }}
            .logout-btn {{ 
                background: #ff6464;
                color: #0a0f1e;
                text-decoration: none;
                padding: 10px 20px;
                border-radius: 4px;
                font-weight: bold;
            }}
            .generated {{
                margin-top: 10px;
                padding: 10px;
                background: rgba(0,255,0,0.1);
                border: 1px solid #00ff00;
                border-radius: 4px;
                color: #00ff00;
            }}
            .extend-modal {{
                display: none;
                position: fixed;
                top: 0;
                left: 0;
                width: 100%;
                height: 100%;
                background: rgba(0,0,0,0.8);
                justify-content: center;
                align-items: center;
                z-index: 1000;
            }}
            .modal-content {{
                background: #1a2a30;
                border: 2px solid #00ffff;
                border-radius: 8px;
                padding: 30px;
                width: 400px;
            }}
            .modal-content h3 {{
                color: #00ffff;
                margin-bottom: 20px;
            }}
            .modal-buttons {{
                display: flex;
                gap: 10px;
                margin-top: 20px;
            }}
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
                <div class="generate-section">
                    <input type="number" id="genCount" value="5" min="1" max="100">
                    <select id="genDuration">
                        <option value="7">7 Days</option>
                        <option value="30">30 Days</option>
                        <option value="365">1 Year</option>
                    </select>
                    <button onclick="generateKeys()">Generate</button>
                </div>
                <div id="generated" class="generated" style="display:none;"></div>
            </div>
            
            <div class="tab-container">
                <button class="tab-btn active" onclick="switchTab(7)">📅 7 DAYS</button>
                <button class="tab-btn" onclick="switchTab(30)">📅 30 DAYS</button>
                <button class="tab-btn" onclick="switchTab(365)">📅 365 DAYS</button>
                <button class="tab-btn" onclick="switchTab('all')">📋 ALL KEYS</button>
            </div>
            
            <div class="tab-content active" id="tab-7">
                <div class="key-list" id="keys-7"></div>
            </div>
            <div class="tab-content" id="tab-30">
                <div class="key-list" id="keys-30"></div>
            </div>
            <div class="tab-content" id="tab-365">
                <div class="key-list" id="keys-365"></div>
            </div>
            <div class="tab-content" id="tab-all">
                <div class="key-list" id="keys-all"></div>
            </div>
        </div>
        
        <!-- Extend Modal -->
        <div class="extend-modal" id="extendModal">
            <div class="modal-content">
                <h3>⏰ Extend Key</h3>
                <p id="extendKeyCode" style="color:#00ffff; font-family:monospace; margin-bottom:15px;"></p>
                <select id="extendDays">
                    <option value="7">+7 Days</option>
                    <option value="30">+30 Days</option>
                    <option value="90">+90 Days</option>
                    <option value="365">+1 Year</option>
                </select>
                <div class="modal-buttons">
                    <button onclick="confirmExtend()">Extend</button>
                    <button class="danger" onclick="closeModal()">Cancel</button>
                </div>
            </div>
        </div>
        
        <script>
            let currentExtendKey = null;
            
            async function loadStats() {{
                const res = await fetch('/admin/api/stats');
                const data = await res.json();
                document.getElementById('total').textContent = data.total;
                document.getElementById('used').textContent = data.used;
                document.getElementById('available').textContent = data.available;
                document.getElementById('expired').textContent = data.expired;
            }}
            
            async function loadKeys() {{
                // Load all keys
                const res = await fetch('/admin/api/keys');
                const keys = await res.json();
                displayKeys('all', keys);
                
                // Load keys by duration
                const durations = [7, 30, 365];
                for (const days of durations) {{
                    const res = await fetch(`/admin/api/keys/${{days}}`);
                    const keys = await res.json();
                    displayKeys(days, keys);
                }}
            }}
            
            function displayKeys(tabId, keys) {{
                const container = document.getElementById(`keys-${{tabId}}`);
                if (!container) return;
                
                container.innerHTML = '';
                
                Object.entries(keys).sort((a,b) => new Date(b[1].created) - new Date(a[1].created)).forEach(([key, data]) => {{
                    const now = new Date();
                    const expiry = new Date(data.expiry);
                    const isExpired = expiry < now;
                    
                    let statusClass = 'status-available';
                    let statusText = 'AVAILABLE';
                    
                    if (data.used) {{
                        statusClass = 'status-used';
                        statusText = 'USED';
                    }} else if (isExpired) {{
                        statusClass = 'status-expired';
                        statusText = 'EXPIRED';
                    }}
                    
                    const div = document.createElement('div');
                    div.className = 'key-item';
                    
                    div.innerHTML = `
                        <div class="key-info">
                            <div class="key-code">${{key}}</div>
                            <div class="key-meta">
                                <span class="${{statusClass}}">${{statusText}}</span>
                                <span style="margin-left:10px;">Exp: ${{expiry.toLocaleDateString()}}</span>
                                ${{data.hwid ? `<span style="margin-left:10px;">HWID: ${{data.hwid.substring(0,8)}}...</span>` : ''}}
                                ${{data.extended ? `<span style="margin-left:10px;">Extended: +${{data.extended}} days</span>` : ''}}
                            </div>
                        </div>
                        <div class="key-actions">
                            <button class="warning" onclick="showExtendModal('${{key}}')">⏰ Extend</button>
                            <button class="danger" onclick="deleteKey('${{key}}')">🗑️ Delete</button>
                        </div>
                    `;
                    
                    container.appendChild(div);
                }});
            }}
            
            function switchTab(days) {{
                // Update tab buttons
                document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));
                event.target.classList.add('active');
                
                // Hide all tabs
                document.querySelectorAll('.tab-content').forEach(tab => tab.classList.remove('active'));
                
                // Show selected tab
                if (days === 'all') {{
                    document.getElementById('tab-all').classList.add('active');
                }} else {{
                    document.getElementById(`tab-${{days}}`).classList.add('active');
                }}
            }}
            
            async function generateKeys() {{
                const count = document.getElementById('genCount').value;
                const days = document.getElementById('genDuration').value;
                
                const res = await fetch('/admin/api/generate', {{
                    method: 'POST',
                    headers: {{'Content-Type': 'application/json'}},
                    body: JSON.stringify({{count: parseInt(count), days: parseInt(days)}})
                }});
                
                const data = await res.json();
                const generatedDiv = document.getElementById('generated');
                generatedDiv.style.display = 'block';
                generatedDiv.innerHTML = '✅ Generated ' + data.keys.length + ' keys:<br>' + data.keys.join('<br>');
                
                loadStats();
                loadKeys();
                
                setTimeout(() => {{
                    generatedDiv.style.display = 'none';
                }}, 5000);
            }}
            
            function showExtendModal(key) {{
                currentExtendKey = key;
                document.getElementById('extendKeyCode').textContent = key;
                document.getElementById('extendModal').style.display = 'flex';
            }}
            
            async function confirmExtend() {{
                const days = document.getElementById('extendDays').value;
                
                const res = await fetch('/admin/api/extend', {{
                    method: 'POST',
                    headers: {{'Content-Type': 'application/json'}},
                    body: JSON.stringify({{key: currentExtendKey, days: parseInt(days)}})
                }});
                
                const data = await res.json();
                
                if (data.success) {{
                    alert(`✅ Key extended by ${{days}} days!`);
                    closeModal();
                    loadStats();
                    loadKeys();
                }} else {{
                    alert('❌ Error: ' + data.error);
                }}
            }}
            
            function closeModal() {{
                document.getElementById('extendModal').style.display = 'none';
                currentExtendKey = null;
            }}
            
            async function deleteKey(key) {{
                if (confirm('Permanently delete this key?')) {{
                    await fetch('/admin/api/delete/' + key, {{method: 'DELETE'}});
                    loadStats();
                    loadKeys();
                }}
            }}
            
            // Load everything
            loadStats();
            loadKeys();
            
            // Refresh every 30 seconds
            setInterval(() => {{
                loadStats();
                loadKeys();
            }}, 30000);
            
            // Close modal when clicking outside
            window.onclick = function(event) {{
                const modal = document.getElementById('extendModal');
                if (event.target === modal) {{
                    closeModal();
                }}
            }}
        </script>
    </body>
    </html>
    '''

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
# RUN
# ============================================================================

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    print(f"\n{'='*60}")
    print(f"🚀 ATLAS APP RUNNING")
    print(f"{'='*60}")
    print(f"🌐 GUI: https://atlas-r6-keys.onrender.com/")
    print(f"🔑 API: https://atlas-r6-keys.onrender.com/api/validate")
    print(f"👑 Login: https://atlas-r6-keys.onrender.com/login")
    print(f"📊 Admin: https://atlas-r6-keys.onrender.com/admin")
    print(f"📁 Keys: {len(KEYS)}")
    print(f"{'='*60}\n")
    
    app.run(host='0.0.0.0', port=port, debug=False)