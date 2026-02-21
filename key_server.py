from flask import Flask, request, jsonify, render_template_string, session, redirect, url_for
from flask_cors import CORS
import json
import hashlib
import secrets
from datetime import datetime, timedelta
import os
from functools import wraps

app = Flask(__name__)
app.secret_key = secrets.token_hex(32)  # Secure session key
CORS(app)

# ============================================================================
# CONFIGURATION - CHANGE THESE!
# ============================================================================

ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "atlas2026"  # Change this!

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
            # Create default keys
            create_default_keys()
    except Exception as e:
        print(f"❌ Error loading keys: {e}")
        KEYS = {}

def save_keys():
    try:
        with open(KEY_FILE, 'w') as f:
            json.dump(KEYS, f, indent=2)
        print(f"✅ Saved {len(KEYS)} keys")
        return True
    except Exception as e:
        print(f"❌ Error saving keys: {e}")
        return False

def create_default_keys():
    global KEYS
    KEYS = {
        "7D21-9A4F-8E67-3B2C-1D5F-9A8E": {
            "expiry": (datetime.now() + timedelta(days=7)).isoformat(),
            "used": False,
            "hwid": None,
            "created": datetime.now().isoformat(),
            "duration": "7days",
            "notes": "Test key"
        },
        "30D1-8C4F-2E7B-9A3D-5F6C-1B9E": {
            "expiry": (datetime.now() + timedelta(days=30)).isoformat(),
            "used": False,
            "hwid": None,
            "created": datetime.now().isoformat(),
            "duration": "30days",
            "notes": "Test key"
        },
        "365D-1A2B-3C4D-5E6F-7A8B-9C0D": {
            "expiry": (datetime.now() + timedelta(days=365)).isoformat(),
            "used": False,
            "hwid": None,
            "created": datetime.now().isoformat(),
            "duration": "365days",
            "notes": "Test key"
        }
    }
    save_keys()

# ============================================================================
# LOGIN DECORATOR
# ============================================================================

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# ============================================================================
# PUBLIC API (No login required)
# ============================================================================

@app.route('/')
def home():
    return "ATLAS Key Server Online!"

@app.route('/api/status')
def status():
    return jsonify({'status': 'online', 'time': datetime.now().isoformat()})

@app.route('/api/validate', methods=['POST'])
def validate():
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
        return jsonify({'valid': False, 'message': 'Key already in use on another PC'})
    
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
                <p>Invalid username or password</p>
                <a href="/login" style="color:#00ffff;">Try again</a>
            </body>
            </html>
            '''
    
    # Login form
    return '''
    <!DOCTYPE html>
    <html>
    <head>
        <title>ATLAS Key Server - Login</title>
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; font-family: 'Segoe UI', monospace; }
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
            <h1>🔐 ADMIN LOGIN</h1>
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
# ADMIN PANEL (Login required)
# ============================================================================

@app.route('/admin')
@login_required
def admin_panel():
    return render_template_string(ADMIN_HTML)

# ============================================================================
# ADMIN API (All require login)
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
    notes = data.get('notes', '')
    
    new_keys = []
    expiry = (datetime.now() + timedelta(days=days)).isoformat()
    
    for i in range(count):
        key = '-'.join([secrets.token_hex(2).upper() for _ in range(6)])
        KEYS[key] = {
            'expiry': expiry,
            'used': False,
            'hwid': None,
            'created': datetime.now().isoformat(),
            'duration': f"{days}days",
            'notes': notes
        }
        new_keys.append(key)
    
    save_keys()
    return jsonify({'success': True, 'keys': new_keys})

@app.route('/admin/api/extend', methods=['POST'])
@login_required
def admin_extend_key():
    """Extend the expiry of a key"""
    data = request.json
    key = data.get('key', '').strip().upper()
    days = int(data.get('days', 30))
    
    if key not in KEYS:
        return jsonify({'success': False, 'error': 'Key not found'}), 404
    
    # Get current expiry
    current_expiry = datetime.fromisoformat(KEYS[key]['expiry'])
    
    # Add days
    new_expiry = current_expiry + timedelta(days=days)
    
    # Update key
    KEYS[key]['expiry'] = new_expiry.isoformat()
    KEYS[key]['extended_date'] = datetime.now().isoformat()
    KEYS[key]['extended_by'] = days
    
    save_keys()
    
    return jsonify({
        'success': True, 
        'message': f'Key extended by {days} days',
        'new_expiry': new_expiry.isoformat()
    })

@app.route('/admin/api/delete/<key>', methods=['DELETE'])
@login_required
def admin_delete_key(key):
    if key in KEYS:
        del KEYS[key]
        save_keys()
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': 'Key not found'}), 404

@app.route('/admin/api/reset/<key>', methods=['POST'])
@login_required
def admin_reset_key(key):
    if key in KEYS:
        KEYS[key]['used'] = False
        KEYS[key]['hwid'] = None
        if 'activated_date' in KEYS[key]:
            del KEYS[key]['activated_date']
        save_keys()
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': 'Key not found'}), 404

@app.route('/admin/api/stats', methods=['GET'])
@login_required
def admin_stats():
    total = len(KEYS)
    used = sum(1 for k in KEYS if KEYS[k].get('used', False))
    expired = sum(1 for k in KEYS if datetime.fromisoformat(KEYS[k]['expiry']) < datetime.now())
    
    return jsonify({
        'total': total,
        'used': used,
        'available': total - used,
        'expired': expired
    })

@app.route('/admin/api/change-password', methods=['POST'])
@login_required
def admin_change_password():
    """Change admin password"""
    global ADMIN_PASSWORD
    data = request.json
    old = data.get('old_password')
    new = data.get('new_password')
    
    if old != ADMIN_PASSWORD:
        return jsonify({'success': False, 'error': 'Old password incorrect'}), 401
    
    ADMIN_PASSWORD = new
    return jsonify({'success': True, 'message': 'Password changed'})

# ============================================================================
# ADMIN HTML INTERFACE
# ============================================================================

ADMIN_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>ATLAS Key Server - Admin</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; font-family: 'Segoe UI', monospace; }
        body {
            background: linear-gradient(135deg, #0a0f1e 0%, #001520 100%);
            min-height: 100vh;
            padding: 20px;
        }
        .container {
            max-width: 1400px;
            margin: 0 auto;
        }
        .header {
            background: rgba(0, 255, 255, 0.1);
            border: 2px solid #00ffff;
            border-radius: 10px;
            padding: 20px;
            margin-bottom: 20px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        h1 {
            color: #00ffff;
            font-size: 32px;
            text-shadow: 0 0 15px #00ffff;
        }
        .logout-btn {
            background: #ff6464;
            color: #0a0f1e;
            padding: 10px 20px;
            border-radius: 4px;
            text-decoration: none;
            font-weight: bold;
        }
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
            margin-bottom: 20px;
        }
        .stat-card {
            background: rgba(0, 255, 255, 0.05);
            border: 1px solid #00ffff;
            border-radius: 8px;
            padding: 20px;
            text-align: center;
        }
        .stat-value {
            color: #00ffff;
            font-size: 32px;
            font-weight: bold;
        }
        .stat-label {
            color: #ffffff;
            font-size: 12px;
            text-transform: uppercase;
            margin-top: 5px;
        }
        .panel {
            background: rgba(0, 0, 0, 0.5);
            border: 1px solid #00ffff;
            border-radius: 8px;
            padding: 20px;
            margin-bottom: 20px;
        }
        h2 {
            color: #00ffff;
            margin-bottom: 15px;
            border-bottom: 1px solid #00ffff40;
            padding-bottom: 5px;
        }
        .form-group {
            margin-bottom: 15px;
        }
        label {
            color: #00ffff;
            display: block;
            margin-bottom: 5px;
        }
        input, select, textarea {
            width: 100%;
            padding: 10px;
            background: #1a2a30;
            border: 1px solid #00ffff;
            color: #00ffff;
            border-radius: 4px;
            font-size: 14px;
        }
        button {
            background: #00ffff;
            color: #0a0f1e;
            border: none;
            padding: 10px 20px;
            border-radius: 4px;
            cursor: pointer;
            font-weight: bold;
            margin-right: 10px;
            font-size: 14px;
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
            max-height: 500px;
            overflow-y: auto;
            border: 1px solid #00ffff40;
            border-radius: 4px;
        }
        .key-item {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 15px;
            border-bottom: 1px solid #00ffff20;
            color: #ffffff;
        }
        .key-item:hover {
            background: rgba(0, 255, 255, 0.1);
        }
        .key-info {
            flex: 2;
        }
        .key-code {
            font-family: monospace;
            font-size: 16px;
            color: #00ffff;
            font-weight: bold;
        }
        .key-details {
            font-size: 12px;
            color: #a0b0c0;
            margin-top: 5px;
        }
        .key-status {
            font-size: 12px;
            font-weight: bold;
            margin-left: 10px;
        }
        .status-used {
            color: #ffaa00;
        }
        .status-available {
            color: #64ff64;
        }
        .status-expired {
            color: #ff6464;
        }
        .key-actions {
            display: flex;
            gap: 5px;
            flex-wrap: wrap;
        }
        .action-btn {
            padding: 8px 12px;
            font-size: 12px;
            cursor: pointer;
            border: none;
            border-radius: 3px;
            font-weight: bold;
        }
        .extend-btn {
            background: #00ffff;
            color: #0a0f1e;
        }
        .reset-btn {
            background: #ffaa00;
            color: #0a0f1e;
        }
        .delete-btn {
            background: #ff6464;
            color: #0a0f1e;
        }
        .generated-keys {
            margin-top: 15px;
            padding: 15px;
            background: rgba(0, 255, 0, 0.1);
            border: 1px solid #00ff00;
            border-radius: 4px;
            color: #00ff00;
            font-family: monospace;
            white-space: pre-wrap;
            max-height: 200px;
            overflow-y: auto;
        }
        .modal {
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
        }
        .modal-content {
            background: #0a1a20;
            border: 2px solid #00ffff;
            border-radius: 8px;
            padding: 30px;
            width: 400px;
            box-shadow: 0 0 50px #00ffff;
        }
        .modal-content h3 {
            color: #00ffff;
            margin-bottom: 20px;
        }
        .search-box {
            margin-bottom: 15px;
        }
        .search-box input {
            width: 100%;
            padding: 10px;
            background: #1a2a30;
            border: 1px solid #00ffff;
            color: #00ffff;
            border-radius: 4px;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🔑 ATLAS KEY SERVER - ADMIN</h1>
            <a href="/logout" class="logout-btn">Logout</a>
        </div>
        
        <div class="stats-grid" id="stats">
            <div class="stat-card">
                <div class="stat-value" id="totalKeys">0</div>
                <div class="stat-label">TOTAL KEYS</div>
            </div>
            <div class="stat-card">
                <div class="stat-value" id="usedKeys">0</div>
                <div class="stat-label">USED KEYS</div>
            </div>
            <div class="stat-card">
                <div class="stat-value" id="availableKeys">0</div>
                <div class="stat-label">AVAILABLE</div>
            </div>
            <div class="stat-card">
                <div class="stat-value" id="expiredKeys">0</div>
                <div class="stat-label">EXPIRED</div>
            </div>
        </div>
        
        <div class="panel">
            <h2>⚡ GENERATE KEYS</h2>
            <div class="form-group">
                <label>Number of Keys:</label>
                <input type="number" id="keyCount" min="1" max="100" value="5">
            </div>
            <div class="form-group">
                <label>Duration:</label>
                <select id="keyDuration">
                    <option value="7">7 Days</option>
                    <option value="30">30 Days</option>
                    <option value="90">90 Days</option>
                    <option value="365">1 Year</option>
                </select>
            </div>
            <div class="form-group">
                <label>Notes (optional):</label>
                <input type="text" id="keyNotes" placeholder="e.g., Customer name">
            </div>
            <button onclick="generateKeys()">Generate Keys</button>
            <div id="generatedKeys" class="generated-keys" style="display: none;"></div>
        </div>
        
        <div class="panel">
            <h2>📋 KEY MANAGEMENT</h2>
            <div class="search-box">
                <input type="text" id="keySearch" placeholder="Search keys..." onkeyup="filterKeys()">
            </div>
            <div class="key-list" id="keyList"></div>
        </div>
    </div>
    
    <!-- Extend Key Modal -->
    <div class="modal" id="extendModal">
        <div class="modal-content">
            <h3>⏰ Extend Key</h3>
            <p id="extendKeyCode" style="color:#00ffff; font-family:monospace;"></p>
            <div class="form-group">
                <label>Add Days:</label>
                <input type="number" id="extendDays" min="1" max="365" value="30">
            </div>
            <div style="display: flex; gap: 10px;">
                <button onclick="confirmExtend()">Extend</button>
                <button class="danger" onclick="closeModal()">Cancel</button>
            </div>
        </div>
    </div>
    
    <script>
        let currentExtendKey = null;
        let allKeys = [];
        
        async function loadStats() {
            try {
                const res = await fetch('/admin/api/stats');
                const data = await res.json();
                document.getElementById('totalKeys').textContent = data.total;
                document.getElementById('usedKeys').textContent = data.used;
                document.getElementById('availableKeys').textContent = data.available;
                document.getElementById('expiredKeys').textContent = data.expired;
            } catch (e) {
                console.error('Failed to load stats', e);
            }
        }
        
        async function loadKeys() {
            try {
                const res = await fetch('/admin/api/keys');
                allKeys = await res.json();
                displayKeys(allKeys);
            } catch (e) {
                console.error('Failed to load keys', e);
            }
        }
        
        function displayKeys(keys) {
            const keyList = document.getElementById('keyList');
            keyList.innerHTML = '';
            
            // Sort by creation date (newest first)
            const sorted = Object.entries(keys).sort((a, b) => {
                return new Date(b[1].created) - new Date(a[1].created);
            });
            
            for (const [key, data] of sorted) {
                const now = new Date();
                const expiry = new Date(data.expiry);
                const isExpired = expiry < now;
                
                const div = document.createElement('div');
                div.className = 'key-item';
                
                let statusClass = 'status-available';
                let statusText = 'AVAILABLE';
                
                if (data.used) {
                    statusClass = 'status-used';
                    statusText = 'USED';
                } else if (isExpired) {
                    statusClass = 'status-expired';
                    statusText = 'EXPIRED';
                }
                
                const expiryDate = expiry.toLocaleDateString();
                const createdDate = new Date(data.created).toLocaleDateString();
                
                div.innerHTML = `
                    <div class="key-info">
                        <div>
                            <span class="key-code">${key}</span>
                            <span class="key-status ${statusClass}">${statusText}</span>
                        </div>
                        <div class="key-details">
                            Created: ${createdDate} | Expires: ${expiryDate} | Duration: ${data.duration || 'unknown'}
                            ${data.notes ? ` | Notes: ${data.notes}` : ''}
                            ${data.hwid ? ` | HWID: ${data.hwid.substring(0,8)}...` : ''}
                        </div>
                    </div>
                    <div class="key-actions">
                        <button class="action-btn extend-btn" onclick="showExtendModal('${key}')">⏰ Extend</button>
                        ${data.used ? `<button class="action-btn reset-btn" onclick="resetKey('${key}')">↺ Reset</button>` : ''}
                        <button class="action-btn delete-btn" onclick="deleteKey('${key}')">✕ Delete</button>
                    </div>
                `;
                
                keyList.appendChild(div);
            }
        }
        
        function filterKeys() {
            const search = document.getElementById('keySearch').value.toUpperCase();
            if (!search) {
                displayKeys(allKeys);
                return;
            }
            
            const filtered = {};
            for (const [key, data] of Object.entries(allKeys)) {
                if (key.includes(search) || (data.notes && data.notes.toUpperCase().includes(search))) {
                    filtered[key] = data;
                }
            }
            displayKeys(filtered);
        }
        
        async function generateKeys() {
            const count = document.getElementById('keyCount').value;
            const days = document.getElementById('keyDuration').value;
            const notes = document.getElementById('keyNotes').value;
            
            const res = await fetch('/admin/api/generate', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    count: parseInt(count),
                    days: parseInt(days),
                    notes: notes
                })
            });
            
            const data = await res.json();
            
            const generatedDiv = document.getElementById('generatedKeys');
            generatedDiv.style.display = 'block';
            generatedDiv.innerHTML = '✅ Generated ' + data.keys.length + ' keys:<br>' + data.keys.join('<br>');
            
            loadStats();
            loadKeys();
        }
        
        function showExtendModal(key) {
            currentExtendKey = key;
            document.getElementById('extendKeyCode').textContent = key;
            document.getElementById('extendModal').style.display = 'flex';
        }
        
        async function confirmExtend() {
            const days = document.getElementById('extendDays').value;
            
            const res = await fetch('/admin/api/extend', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    key: currentExtendKey,
                    days: parseInt(days)
                })
            });
            
            const data = await res.json();
            
            if (data.success) {
                alert(`✅ Key extended by ${days} days!`);
                closeModal();
                loadStats();
                loadKeys();
            } else {
                alert('❌ Error: ' + data.error);
            }
        }
        
        function closeModal() {
            document.getElementById('extendModal').style.display = 'none';
            currentExtendKey = null;
        }
        
        async function resetKey(key) {
            if (confirm('Reset this key? It will become available again.')) {
                await fetch('/admin/api/reset/' + key, {method: 'POST'});
                loadKeys();
                loadStats();
            }
        }
        
        async function deleteKey(key) {
            if (confirm('Permanently delete this key?')) {
                await fetch('/admin/api/delete/' + key, {method: 'DELETE'});
                loadKeys();
                loadStats();
            }
        }
        
        // Close modal when clicking outside
        window.onclick = function(event) {
            const modal = document.getElementById('extendModal');
            if (event.target === modal) {
                closeModal();
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
# START SERVER
# ============================================================================

if __name__ == '__main__':
    # Load keys on startup
    load_keys()
    
    port = int(os.environ.get('PORT', 10000))
    print(f"\n{'='*50}")
    print(f"🚀 ATLAS KEY SERVER")
    print(f"{'='*50}")
    print(f"🔐 Admin login: https://atlas-r6-keys.onrender.com/login")
    print(f"   Username: {ADMIN_USERNAME}")
    print(f"   Password: {ADMIN_PASSWORD}")
    print(f"📊 Admin panel: https://atlas-r6-keys.onrender.com/admin")
    print(f"🔑 API: https://atlas-r6-keys.onrender.com/api/validate")
    print(f"📁 Keys loaded: {len(KEYS)}")
    print(f"{'='*50}\n")
    
    app.run(host='0.0.0.0', port=port)