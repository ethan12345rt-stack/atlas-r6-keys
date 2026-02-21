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

# Load keys from file or use default
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
            # Create default keys if none exist
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
    """Create 3 default keys for testing"""
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
# PUBLIC API ENDPOINTS (for your recoil app)
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
    
    # Check expiry
    expiry = datetime.fromisoformat(key_data['expiry'])
    if expiry < datetime.now():
        return jsonify({'valid': False, 'message': 'Key expired'})
    
    # Check if already used
    if key_data['used']:
        if key_data['hwid'] == hwid:
            return jsonify({
                'valid': True,
                'message': 'Key valid',
                'expiry': key_data['expiry']
            })
        else:
            return jsonify({'valid': False, 'message': 'Key already in use on another PC'})
    
    # First time use - activate
    key_data['used'] = True
    key_data['hwid'] = hwid
    key_data['activated_date'] = datetime.now().isoformat()
    save_keys()
    
    return jsonify({
        'valid': True,
        'message': 'Key activated successfully',
        'expiry': key_data['expiry']
    })

# ============================================================================
# ADMIN API ENDPOINTS (for key management)
# ============================================================================

@app.route('/admin', methods=['GET'])
def admin_panel():
    """Admin web interface"""
    return render_template_string(ADMIN_HTML)

@app.route('/admin/api/keys', methods=['GET'])
def admin_get_keys():
    """Get all keys (admin only)"""
    return jsonify(KEYS)

@app.route('/admin/api/generate', methods=['POST'])
def admin_generate_keys():
    """Generate new keys"""
    data = request.json
    count = int(data.get('count', 5))
    days = int(data.get('days', 7))
    
    new_keys = {}
    expiry = (datetime.now() + timedelta(days=days)).isoformat()
    
    for i in range(count):
        # Generate random key
        key = '-'.join([secrets.token_hex(2).upper() for _ in range(6)])
        new_keys[key] = {
            'expiry': expiry,
            'used': False,
            'hwid': None,
            'created': datetime.now().isoformat(),
            'duration': f"{days}days"
        }
        KEYS[key] = new_keys[key]
    
    save_keys()
    return jsonify({
        'success': True,
        'keys': list(new_keys.keys()),
        'count': count,
        'days': days
    })

@app.route('/admin/api/delete/<key>', methods=['DELETE'])
def admin_delete_key(key):
    """Delete a key"""
    if key in KEYS:
        del KEYS[key]
        save_keys()
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': 'Key not found'}), 404

@app.route('/admin/api/reset/<key>', methods=['POST'])
def admin_reset_key(key):
    """Reset a key (make it unused again)"""
    if key in KEYS:
        KEYS[key]['used'] = False
        KEYS[key]['hwid'] = None
        if 'activated_date' in KEYS[key]:
            del KEYS[key]['activated_date']
        save_keys()
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': 'Key not found'}), 404

@app.route('/admin/api/stats', methods=['GET'])
def admin_stats():
    """Get key statistics"""
    total = len(KEYS)
    used = sum(1 for k in KEYS if KEYS[k].get('used', False))
    expired = sum(1 for k in KEYS if datetime.fromisoformat(KEYS[k]['expiry']) < datetime.now())
    
    return jsonify({
        'total': total,
        'used': used,
        'available': total - used,
        'expired': expired
    })

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
            max-width: 1200px;
            margin: 0 auto;
        }
        .header {
            background: rgba(0, 255, 255, 0.1);
            border: 2px solid #00ffff;
            border-radius: 10px;
            padding: 20px;
            margin-bottom: 20px;
            box-shadow: 0 0 30px rgba(0, 255, 255, 0.3);
        }
        h1 {
            color: #00ffff;
            font-size: 32px;
            text-shadow: 0 0 15px #00ffff;
        }
        .subtitle {
            color: #ffffff;
            margin-top: 5px;
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
        input, select {
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
        .key-info {
            flex: 1;
        }
        .key-code {
            font-family: monospace;
            font-size: 14px;
            color: #00ffff;
        }
        .key-status {
            font-size: 12px;
            margin-left: 10px;
        }
        .status-used {
            color: #ff6464;
        }
        .status-available {
            color: #64ff64;
        }
        .status-expired {
            color: #ffaa00;
        }
        .key-actions {
            display: flex;
            gap: 5px;
        }
        .action-btn {
            padding: 5px 10px;
            font-size: 12px;
            cursor: pointer;
            border: none;
            border-radius: 3px;
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
            padding: 10px;
            background: rgba(0, 255, 0, 0.1);
            border: 1px solid #00ff00;
            border-radius: 4px;
            color: #00ff00;
            font-family: monospace;
            white-space: pre-wrap;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🔑 ATLAS KEY SERVER - ADMIN PANEL</h1>
            <div class="subtitle">Manage your license keys</div>
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
            <h2>⚡ GENERATE NEW KEYS</h2>
            <div class="form-group">
                <label>Number of Keys:</label>
                <input type="number" id="keyCount" min="1" max="100" value="5">
            </div>
            <div class="form-group">
                <label>Duration:</label>
                <select id="keyDuration">
                    <option value="7">7 Days</option>
                    <option value="30">30 Days</option>
                    <option value="365">1 Year</option>
                </select>
            </div>
            <button onclick="generateKeys()">Generate Keys</button>
            <div id="generatedKeys" class="generated-keys" style="display: none;"></div>
        </div>
        
        <div class="panel">
            <h2>📋 KEY MANAGEMENT</h2>
            <div class="key-list" id="keyList"></div>
        </div>
    </div>
    
    <script>
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
                const keys = await res.json();
                
                const keyList = document.getElementById('keyList');
                keyList.innerHTML = '';
                
                // Sort keys by creation date (newest first)
                const sortedKeys = Object.entries(keys).sort((a, b) => {
                    return new Date(b[1].created) - new Date(a[1].created);
                });
                
                for (const [key, data] of sortedKeys) {
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
                    
                    div.innerHTML = `
                        <div class="key-info">
                            <span class="key-code">${key}</span>
                            <span class="key-status ${statusClass}">${statusText}</span>
                            <div style="font-size: 11px; color: #a0b0c0; margin-top: 3px;">
                                Exp: ${new Date(data.expiry).toLocaleDateString()}
                                ${data.hwid ? ' | HWID: ' + data.hwid.substring(0, 8) + '...' : ''}
                            </div>
                        </div>
                        <div class="key-actions">
                            ${data.used ? `<button class="action-btn reset-btn" onclick="resetKey('${key}')">Reset</button>` : ''}
                            <button class="action-btn delete-btn" onclick="deleteKey('${key}')">Delete</button>
                        </div>
                    `;
                    
                    keyList.appendChild(div);
                }
            } catch (e) {
                console.error('Failed to load keys', e);
            }
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
            
            const generatedDiv = document.getElementById('generatedKeys');
            generatedDiv.style.display = 'block';
            generatedDiv.innerHTML = '✅ Generated ' + data.count + ' keys:<br>' + data.keys.join('<br>');
            
            loadStats();
            loadKeys();
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
        
        // Load everything on page load
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
    port = int(os.environ.get('PORT', 10000))
    print(f"\n{'='*50}")
    print(f"🚀 ATLAS KEY SERVER STARTING")
    print(f"{'='*50}")
    print(f"📊 Admin panel: http://localhost:{port}/admin")
    print(f"🔑 API endpoint: http://localhost:{port}/api/validate")
    print(f"📁 Keys loaded: {len(KEYS)}")
    print(f"{'='*50}\n")
    app.run(host='0.0.0.0', port=port)