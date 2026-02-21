from flask import Flask, request, jsonify, render_template_string
from flask_cors import CORS
import json
import hashlib
import secrets
from datetime import datetime, timedelta
import os

app = Flask(__name__)
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
            # Create default keys
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
    except Exception as e:
        print(f"❌ Error: {e}")
        KEYS = {}

def save_keys():
    try:
        with open(KEY_FILE, 'w') as f:
            json.dump(KEYS, f, indent=2)
        return True
    except:
        return False

load_keys()

# ============================================================================
# PUBLIC API
# ============================================================================

@app.route('/')
def home():
    return "ATLAS Key Server Online!"

@app.route('/api/status')
def status():
    return jsonify({'status': 'online'})

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
        return jsonify({'valid': False, 'message': 'Key already in use'})
    
    if not key_data['used']:
        key_data['used'] = True
        key_data['hwid'] = hwid
        key_data['activated_date'] = datetime.now().isoformat()
        save_keys()
    
    return jsonify({'valid': True, 'message': 'Key valid', 'expiry': key_data['expiry']})

# ============================================================================
# ADMIN PANEL - THIS IS WHAT YOU NEED!
# ============================================================================

@app.route('/admin')
def admin_panel():
    return render_template_string(ADMIN_HTML)

@app.route('/admin/api/keys', methods=['GET'])
def admin_get_keys():
    return jsonify(KEYS)

@app.route('/admin/api/generate', methods=['POST'])
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
def admin_delete_key(key):
    if key in KEYS:
        del KEYS[key]
        save_keys()
        return jsonify({'success': True})
    return jsonify({'success': False}), 404

@app.route('/admin/api/reset/<key>', methods=['POST'])
def admin_reset_key(key):
    if key in KEYS:
        KEYS[key]['used'] = False
        KEYS[key]['hwid'] = None
        save_keys()
        return jsonify({'success': True})
    return jsonify({'success': False}), 404

@app.route('/admin/api/stats', methods=['GET'])
def admin_stats():
    total = len(KEYS)
    used = sum(1 for k in KEYS if KEYS[k].get('used', False))
    expired = sum(1 for k in KEYS if datetime.fromisoformat(KEYS[k]['expiry']) < datetime.now())
    return jsonify({'total': total, 'used': used, 'available': total - used, 'expired': expired})

# ============================================================================
# ADMIN HTML INTERFACE
# ============================================================================

ADMIN_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>ATLAS Key Server - Admin</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; font-family: 'Segoe UI', monospace; }
        body {
            background: linear-gradient(135deg, #0a0f1e 0%, #001520 100%);
            min-height: 100vh;
            padding: 20px;
        }
        .container {
            max-width: 1200px;
            margin: 0 auto;
        }
        .header {
            background: rgba(0, 255, 255, 0.1);
            border: 2px solid #00ffff;
            border-radius: 10px;
            padding: 20px;
            margin-bottom: 20px;
        }
        h1 {
            color: #00ffff;
            font-size: 32px;
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
        }
        .form-group {
            margin-bottom: 15px;
        }
        label {
            color: #00ffff;
            display: block;
            margin-bottom: 5px;
        }
        input, select {
            width: 100%;
            padding: 10px;
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
            margin-right: 10px;
        }
        button:hover {
            background: #ffffff;
            box-shadow: 0 0 20px #00ffff;
        }
        .key-list {
            max-height: 400px;
            overflow-y: auto;
            border: 1px solid #00ffff40;
            border-radius: 4px;
        }
        .key-item {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 10px;
            border-bottom: 1px solid #00ffff20;
            color: #ffffff;
        }
        .key-item:hover {
            background: rgba(0, 255, 255, 0.1);
        }
        .key-code {
            font-family: monospace;
            color: #00ffff;
        }
        .status-used { color: #ff6464; }
        .status-available { color: #64ff64; }
        .generated-keys {
            margin-top: 15px;
            padding: 10px;
            background: rgba(0, 255, 0, 0.1);
            border: 1px solid #00ff00;
            border-radius: 4px;
            color: #00ff00;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🔑 ATLAS KEY SERVER - ADMIN</h1>
        </div>
        
        <div class="stats-grid" id="stats">
            <div class="stat-card"><div class="stat-value" id="totalKeys">0</div><div class="stat-label">TOTAL</div></div>
            <div class="stat-card"><div class="stat-value" id="usedKeys">0</div><div class="stat-label">USED</div></div>
            <div class="stat-card"><div class="stat-value" id="availableKeys">0</div><div class="stat-label">AVAILABLE</div></div>
            <div class="stat-card"><div class="stat-value" id="expiredKeys">0</div><div class="stat-label">EXPIRED</div></div>
        </div>
        
        <div class="panel">
            <h2>⚡ GENERATE KEYS</h2>
            <div class="form-group">
                <label>Count:</label>
                <input type="number" id="keyCount" value="5" min="1" max="100">
            </div>
            <div class="form-group">
                <label>Duration:</label>
                <select id="keyDuration">
                    <option value="7">7 Days</option>
                    <option value="30">30 Days</option>
                    <option value="365">1 Year</option>
                </select>
            </div>
            <button onclick="generateKeys()">Generate</button>
            <div id="generatedKeys" class="generated-keys" style="display: none;"></div>
        </div>
        
        <div class="panel">
            <h2>📋 KEY LIST</h2>
            <div class="key-list" id="keyList"></div>
        </div>
    </div>
    
    <script>
        async function loadStats() {
            const res = await fetch('/admin/api/stats');
            const data = await res.json();
            document.getElementById('totalKeys').textContent = data.total;
            document.getElementById('usedKeys').textContent = data.used;
            document.getElementById('availableKeys').textContent = data.available;
            document.getElementById('expiredKeys').textContent = data.expired;
        }
        
        async function loadKeys() {
            const res = await fetch('/admin/api/keys');
            const keys = await res.json();
            const list = document.getElementById('keyList');
            list.innerHTML = '';
            
            Object.entries(keys).forEach(([key, data]) => {
                const div = document.createElement('div');
                div.className = 'key-item';
                div.innerHTML = `
                    <div>
                        <span class="key-code">${key}</span>
                        <span class="${data.used ? 'status-used' : 'status-available'}">${data.used ? 'USED' : 'AVAILABLE'}</span>
                        <div style="font-size:11px;">Exp: ${new Date(data.expiry).toLocaleDateString()}</div>
                    </div>
                    <div>
                        ${data.used ? `<button onclick="resetKey('${key}')">Reset</button>` : ''}
                        <button onclick="deleteKey('${key}')">Delete</button>
                    </div>
                `;
                list.appendChild(div);
            });
        }
        
        async function generateKeys() {
            const count = document.getElementById('keyCount').value;
            const days = document.getElementById('keyDuration').value;
            
            const res = await fetch('/admin/api/generate', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({count: parseInt(count), days: parseInt(days)})
            });
            
            const data = await res.json();
            const div = document.getElementById('generatedKeys');
            div.style.display = 'block';
            div.innerHTML = '✅ Generated:<br>' + data.keys.join('<br>');
            loadStats();
            loadKeys();
        }
        
        async function resetKey(key) {
            if (confirm('Reset this key?')) {
                await fetch('/admin/api/reset/' + key, {method: 'POST'});
                loadKeys();
                loadStats();
            }
        }
        
        async function deleteKey(key) {
            if (confirm('Delete this key?')) {
                await fetch('/admin/api/delete/' + key, {method: 'DELETE'});
                loadKeys();
                loadStats();
            }
        }
        
        loadStats();
        loadKeys();
    </script>
</body>
</html>
"""

# ============================================================================
# START SERVER
# ============================================================================

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    print(f"\n{'='*50}")
    print(f"🚀 ATLAS KEY SERVER")
    print(f"{'='*50}")
    print(f"📊 Admin panel: https://atlas-r6-keys.onrender.com/admin")
    print(f"🔑 API: https://atlas-r6-keys.onrender.com/api/validate")
    print(f"📁 Keys loaded: {len(KEYS)}")
    print(f"{'='*50}\n")
    app.run(host='0.0.0.0', port=port)