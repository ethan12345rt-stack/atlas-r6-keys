#!/usr/bin/env python3
"""
ATLAS KEY SYSTEM - ENHANCED VERSION
Features: Better UI, 1-day keys, improved validation, stats dashboard
"""

import os
import json
import secrets
import hashlib
import threading
import time
from datetime import datetime, timedelta
from flask import Flask, render_template, render_template_string, jsonify, request, session, redirect
from flask_cors import CORS
from functools import wraps

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', secrets.token_hex(32))
CORS(app)

# ============================================================================
# DATA STORAGE
# ============================================================================
KEYS_FILE = 'keys.json'
PROFILES_FILE = 'profiles.json'
STATS_FILE = 'stats.json'

KEYS = {}
USER_PROFILES = {}
STATS = {'validations': 0, 'generations': 0, 'last_reset': datetime.now().isoformat()}

ADMIN_USER = "admin"
ADMIN_PASS = os.environ.get('ADMIN_PASSWORD', 'atlas2024')

# ============================================================================
# LOAD/SAVE FUNCTIONS
# ============================================================================
def load_data():
    global KEYS, USER_PROFILES, STATS
    try:
        if os.path.exists(KEYS_FILE):
            with open(KEYS_FILE, 'r') as f:
                KEYS = json.load(f)
        if os.path.exists(PROFILES_FILE):
            with open(PROFILES_FILE, 'r') as f:
                USER_PROFILES = json.load(f)
        if os.path.exists(STATS_FILE):
            with open(STATS_FILE, 'r') as f:
                STATS = json.load(f)
    except Exception as e:
        print(f"Load error: {e}")

def save_data():
    try:
        with open(KEYS_FILE, 'w') as f:
            json.dump(KEYS, f, indent=2)
        with open(PROFILES_FILE, 'w') as f:
            json.dump(USER_PROFILES, f, indent=2)
        with open(STATS_FILE, 'w') as f:
            json.dump(STATS, f, indent=2)
    except Exception as e:
        print(f"Save error: {e}")

# Auto-save every 2 minutes
def auto_save():
    while True:
        time.sleep(120)
        save_data()
        print(f"[{datetime.now().strftime('%H:%M')}] Auto-saved")

threading.Thread(target=auto_save, daemon=True).start()
load_data()

# ============================================================================
# KEY FUNCTIONS
# ============================================================================
def generate_key(duration='7days'):
    """Generate new key with specified duration"""
    key = '-'.join([secrets.token_hex(2).upper() for _ in range(4)])
    
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
    save_data()
    return key

def validate_key(key, hwid):
    """Validate and activate key"""
    key = key.strip().upper()
    
    if key not in KEYS:
        return {'valid': False, 'message': 'Invalid key'}
    
    data = KEYS[key]
    now = datetime.now()
    expiry = datetime.fromisoformat(data['expiry'])
    
    # Check expiry
    if expiry < now:
        return {'valid': False, 'message': 'Key expired'}
    
    # Check if used by different HWID
    if data['used'] and data['hwid'] and data['hwid'] != hwid:
        return {'valid': False, 'message': 'Key in use on another device'}
    
    # First activation or reactivation
    if not data['used']:
        data['used'] = True
        data['activated'] = now.isoformat()
    
    data['hwid'] = hwid
    data['activations'] += 1
    
    STATS['validations'] += 1
    save_data()
    
    days_left = (expiry - now).days
    hours_left = (expiry - now).seconds // 3600
    
    return {
        'valid': True,
        'message': 'Key activated',
        'expiry': data['expiry'],
        'duration': data['duration'],
        'days_left': days_left,
        'hours_left': hours_left if days_left == 0 else None,
        'activations': data['activations']
    }

# ============================================================================
# ROUTES
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
        'validations': STATS.get('validations', 0)
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
    data = request.json
    USER_PROFILES[hwid] = data
    save_data()
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
    expired = 0
    for k, v in KEYS.items():
        if datetime.fromisoformat(v['expiry']) < now:
            expired += 1
    
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
    auth = request.authorization
    if not auth or auth.username != ADMIN_USER or auth.password != ADMIN_PASS:
        return jsonify({'error': 'Unauthorized'}), 401
    
    if key in KEYS:
        del KEYS[key]
        save_data()
        return jsonify({'success': True})
    return jsonify({'success': False}), 404

# ============================================================================
# MODERN UI TEMPLATES
# ============================================================================

INDEX_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ATLAS | Key System</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
            font-family: 'SF Pro Display', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
        }

        :root {
            --primary: #6366f1;
            --primary-dark: #4f46e5;
            --bg: #0a0a0f;
            --surface: #141418;
            --surface-hover: #1a1a20;
            --text: #f1f1f4;
            --text-muted: #6b6b7b;
            --success: #22c55e;
            --error: #ef4444;
            --warning: #f59e0b;
        }

        body {
            background: var(--bg);
            color: var(--text);
            min-height: 100vh;
            display: flex;
            justify-content: center;
            align-items: center;
            padding: 20px;
            line-height: 1.6;
        }

        .container {
            width: 100%;
            max-width: 480px;
            background: var(--surface);
            border-radius: 24px;
            border: 1px solid rgba(255,255,255,0.06);
            overflow: hidden;
            box-shadow: 0 25px 50px -12px rgba(0,0,0,0.5);
        }

        .header {
            background: linear-gradient(135deg, var(--primary) 0%, var(--primary-dark) 100%);
            padding: 40px 30px;
            text-align: center;
            position: relative;
        }

        .header::after {
            content: '';
            position: absolute;
            bottom: 0;
            left: 0;
            right: 0;
            height: 1px;
            background: linear-gradient(90deg, transparent, rgba(255,255,255,0.3), transparent);
        }

        .logo {
            font-size: 32px;
            font-weight: 800;
            letter-spacing: 4px;
            margin-bottom: 8px;
        }

        .tagline {
            font-size: 12px;
            opacity: 0.8;
            letter-spacing: 2px;
            text-transform: uppercase;
        }

        .content {
            padding: 30px;
        }

        .status-bar {
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 8px;
            padding: 12px;
            background: rgba(34, 197, 94, 0.1);
            border-radius: 12px;
            margin-bottom: 24px;
            font-size: 12px;
            color: var(--success);
        }

        .status-bar.offline {
            background: rgba(239, 68, 68, 0.1);
            color: var(--error);
        }

        .status-dot {
            width: 8px;
            height: 8px;
            background: currentColor;
            border-radius: 50%;
            animation: pulse 2s infinite;
        }

        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.5; }
        }

        .section {
            margin-bottom: 24px;
        }

        .section-title {
            font-size: 11px;
            text-transform: uppercase;
            letter-spacing: 2px;
            color: var(--text-muted);
            margin-bottom: 12px;
            font-weight: 600;
        }

        .input-group {
            position: relative;
        }

        .key-input {
            width: 100%;
            padding: 16px 20px;
            background: var(--bg);
            border: 1px solid rgba(255,255,255,0.1);
            border-radius: 16px;
            color: var(--text);
            font-size: 18px;
            letter-spacing: 4px;
            text-align: center;
            text-transform: uppercase;
            transition: all 0.3s;
            outline: none;
        }

        .key-input:focus {
            border-color: var(--primary);
            box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.1);
        }

        .key-input::placeholder {
            color: var(--text-muted);
            letter-spacing: 2px;
            font-size: 14px;
        }

        .btn {
            width: 100%;
            padding: 16px;
            background: var(--primary);
            color: white;
            border: none;
            border-radius: 16px;
            font-size: 14px;
            font-weight: 600;
            letter-spacing: 1px;
            cursor: pointer;
            transition: all 0.3s;
            margin-top: 12px;
            text-transform: uppercase;
        }

        .btn:hover {
            background: var(--primary-dark);
            transform: translateY(-2px);
            box-shadow: 0 10px 20px -5px rgba(99, 102, 241, 0.4);
        }

        .btn:disabled {
            opacity: 0.5;
            cursor: not-allowed;
            transform: none;
        }

        .message {
            margin-top: 16px;
            padding: 16px;
            border-radius: 12px;
            font-size: 13px;
            text-align: center;
            display: none;
        }

        .message.show {
            display: block;
            animation: slideIn 0.3s ease;
        }

        @keyframes slideIn {
            from { opacity: 0; transform: translateY(-10px); }
            to { opacity: 1; transform: translateY(0); }
        }

        .message.success {
            background: rgba(34, 197, 94, 0.1);
            color: var(--success);
            border: 1px solid rgba(34, 197, 94, 0.2);
        }

        .message.error {
            background: rgba(239, 68, 68, 0.1);
            color: var(--error);
            border: 1px solid rgba(239, 68, 68, 0.2);
        }

        .key-info {
            background: var(--bg);
            border-radius: 16px;
            padding: 20px;
            margin-top: 16px;
            display: none;
        }

        .key-info.show {
            display: block;
            animation: slideIn 0.3s ease;
        }

        .info-row {
            display: flex;
            justify-content: space-between;
            padding: 8px 0;
            border-bottom: 1px solid rgba(255,255,255,0.05);
            font-size: 13px;
        }

        .info-row:last-child {
            border-bottom: none;
        }

        .info-label {
            color: var(--text-muted);
        }

        .info-value {
            color: var(--text);
            font-weight: 600;
        }

        .info-value.highlight {
            color: var(--success);
        }

        .footer {
            text-align: center;
            padding: 20px;
            font-size: 11px;
            color: var(--text-muted);
            border-top: 1px solid rgba(255,255,255,0.05);
        }

        .spinner {
            display: inline-block;
            width: 16px;
            height: 16px;
            border: 2px solid rgba(255,255,255,0.3);
            border-top-color: white;
            border-radius: 50%;
            animation: spin 0.8s linear infinite;
            margin-right: 8px;
            vertical-align: middle;
        }

        @keyframes spin {
            to { transform: rotate(360deg); }
        }
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
                <div class="input-group">
                    <input type="text" class="key-input" id="keyInput" placeholder="XXXX-XXXX-XXXX-XXXX" maxlength="19">
                </div>
                <button class="btn" id="validateBtn" onclick="validateKey()">
                    <span id="btnText">Validate Key</span>
                </button>
                
                <div class="message" id="message"></div>
                
                <div class="key-info" id="keyInfo">
                    <div class="info-row">
                        <span class="info-label">Status</span>
                        <span class="info-value highlight" id="infoStatus">Active</span>
                    </div>
                    <div class="info-row">
                        <span class="info-label">Duration</span>
                        <span class="info-value" id="infoDuration">7 Days</span>
                    </div>
                    <div class="info-row">
                        <span class="info-label">Time Remaining</span>
                        <span class="info-value highlight" id="infoTime">6 days</span>
                    </div>
                    <div class="info-row">
                        <span class="info-label">Activations</span>
                        <span class="info-value" id="infoActivations">1</span>
                    </div>
                    <div class="info-row">
                        <span class="info-label">Expires</span>
                        <span class="info-value" id="infoExpiry">2024-12-31</span>
                    </div>
                </div>
            </div>
        </div>
        
        <div class="footer">
            Secure Cloud Authentication • HWID Protected
        </div>
    </div>

    <script>
        // Auto-format key input
        const keyInput = document.getElementById('keyInput');
        keyInput.addEventListener('input', (e) => {
            let value = e.target.value.replace(/-/g, '').toUpperCase();
            let formatted = '';
            for (let i = 0; i < value.length && i < 16; i++) {
                if (i > 0 && i % 4 === 0) formatted += '-';
                formatted += value[i];
            }
            e.target.value = formatted;
        });

        // Check server status
        async function checkStatus() {
            try {
                const res = await fetch('/api/status');
                const data = await res.json();
                document.getElementById('statusBar').className = 'status-bar';
                document.getElementById('statusText').textContent = `Server Online • ${data.keys_total} keys loaded`;
            } catch {
                document.getElementById('statusBar').className = 'status-bar offline';
                document.getElementById('statusText').textContent = 'Server Offline';
            }
        }
        checkStatus();
        setInterval(checkStatus, 10000);

        // Validate key
        async function validateKey() {
            const key = keyInput.value.trim();
            const btn = document.getElementById('validateBtn');
            const btnText = document.getElementById('btnText');
            const msg = document.getElementById('message');
            const info = document.getElementById('keyInfo');

            if (key.length < 19) {
                showMessage('Please enter a complete key', 'error');
                return;
            }

            btn.disabled = true;
            btnText.innerHTML = '<span class="spinner"></span>Validating...';

            try {
                // Generate HWID
                const hwid = Math.random().toString(36).substring(2, 15);
                
                const res = await fetch('/api/validate', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({key: key, hwid: hwid})
                });
                
                const data = await res.json();
                
                if (data.valid) {
                    showMessage('✓ Key validated successfully', 'success');
                    showKeyInfo(data);
                } else {
                    showMessage('✗ ' + data.message, 'error');
                    info.classList.remove('show');
                }
            } catch (err) {
                showMessage('✗ Connection failed', 'error');
            }

            btn.disabled = false;
            btnText.textContent = 'Validate Key';
        }

        function showMessage(text, type) {
            const msg = document.getElementById('message');
            msg.textContent = text;
            msg.className = 'message ' + type + ' show';
            setTimeout(() => msg.classList.remove('show'), 5000);
        }

        function showKeyInfo(data) {
            const info = document.getElementById('keyInfo');
            
            const durationMap = {
                '1hour': '1 Hour',
                '1day': '1 Day',
                '7days': '7 Days',
                '30days': '30 Days',
                '365days': '1 Year',
                'lifetime': 'Lifetime'
            };
            
            document.getElementById('infoDuration').textContent = durationMap[data.duration] || data.duration;
            
            let timeText = '';
            if (data.days_left > 0) {
                timeText = data.days_left + ' days';
            } else if (data.hours_left) {
                timeText = data.hours_left + ' hours';
            } else {
                timeText = 'Expired';
            }
            document.getElementById('infoTime').textContent = timeText;
            document.getElementById('infoActivations').textContent = data.activations;
            document.getElementById('infoExpiry').textContent = new Date(data.expiry).toLocaleDateString();
            
            info.classList.add('show');
        }

        // Enter key to submit
        keyInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') validateKey();
        });
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
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
            font-family: 'SF Pro Display', -apple-system, sans-serif;
        }
        
        body {
            background: #0a0a0f;
            color: #f1f1f4;
            padding: 20px;
            line-height: 1.6;
        }
        
        .container {
            max-width: 1200px;
            margin: 0 auto;
        }
        
        h1 {
            font-size: 28px;
            margin-bottom: 8px;
            background: linear-gradient(135deg, #6366f1, #8b5cf6);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }
        
        .subtitle {
            color: #6b6b7b;
            margin-bottom: 30px;
        }
        
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 16px;
            margin-bottom: 30px;
        }
        
        .stat-card {
            background: #141418;
            border: 1px solid rgba(255,255,255,0.06);
            border-radius: 16px;
            padding: 24px;
            text-align: center;
        }
        
        .stat-value {
            font-size: 36px;
            font-weight: 700;
            color: #6366f1;
            margin-bottom: 4px;
        }
        
        .stat-label {
            font-size: 12px;
            color: #6b6b7b;
            text-transform: uppercase;
            letter-spacing: 1px;
        }
        
        .panel {
            background: #141418;
            border: 1px solid rgba(255,255,255,0.06);
            border-radius: 16px;
            padding: 24px;
            margin-bottom: 20px;
        }
        
        .panel h2 {
            font-size: 14px;
            text-transform: uppercase;
            letter-spacing: 2px;
            color: #6b6b7b;
            margin-bottom: 20px;
        }
        
        .form-row {
            display: flex;
            gap: 12px;
            margin-bottom: 16px;
            flex-wrap: wrap;
        }
        
        input, select {
            flex: 1;
            min-width: 150px;
            padding: 12px 16px;
            background: #0a0a0f;
            border: 1px solid rgba(255,255,255,0.1);
            border-radius: 12px;
            color: #f1f1f4;
            font-size: 14px;
            outline: none;
        }
        
        input:focus, select:focus {
            border-color: #6366f1;
        }
        
        button {
            padding: 12px 24px;
            background: #6366f1;
            color: white;
            border: none;
            border-radius: 12px;
            font-size: 14px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s;
        }
        
        button:hover {
            background: #4f46e5;
            transform: translateY(-2px);
        }
        
        button.secondary {
            background: rgba(255,255,255,0.1);
        }
        
        button.secondary:hover {
            background: rgba(255,255,255,0.15);
        }
        
        button.danger {
            background: #ef4444;
        }
        
        button.danger:hover {
            background: #dc2626;
        }
        
        .key-list {
            max-height: 500px;
            overflow-y: auto;
            border-radius: 12px;
            background: #0a0a0f;
        }
        
        .key-item {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 16px;
            border-bottom: 1px solid rgba(255,255,255,0.05);
        }
        
        .key-item:hover {
            background: rgba(255,255,255,0.02);
        }
        
        .key-info {
            flex: 1;
        }
        
        .key-code {
            font-family: monospace;
            font-size: 16px;
            color: #6366f1;
            margin-bottom: 4px;
        }
        
        .key-meta {
            font-size: 12px;
            color: #6b6b7b;
        }
        
        .badge {
            display: inline-block;
            padding: 4px 12px;
            border-radius: 20px;
            font-size: 11px;
            font-weight: 600;
            text-transform: uppercase;
            margin-left: 8px;
        }
        
        .badge-unused {
            background: rgba(34, 197, 94, 0.2);
            color: #22c55e;
        }
        
        .badge-used {
            background: rgba(245, 158, 11, 0.2);
            color: #f59e0b;
        }
        
        .badge-expired {
            background: rgba(239, 68, 68, 0.2);
            color: #ef4444;
        }
        
        .badge-1hour { background: rgba(99, 102, 241, 0.2); color: #6366f1; }
        .badge-1day { background: rgba(34, 197, 94, 0.2); color: #22c55e; }
        .badge-7days { background: rgba(59, 130, 246, 0.2); color: #3b82f6; }
        .badge-30days { background: rgba(139, 92, 246, 0.2); color: #8b5cf6; }
        .badge-365days { background: rgba(236, 72, 153, 0.2); color: #ec4899; }
        
        .generated-keys {
            background: #0a0a0f;
            border-radius: 12px;
            padding: 16px;
            margin-top: 16px;
            font-family: monospace;
            font-size: 14px;
            line-height: 2;
            display: none;
        }
        
        .generated-keys.show {
            display: block;
        }
        
        .copy-btn {
            padding: 6px 12px;
            font-size: 12px;
            background: rgba(255,255,255,0.1);
        }
        
        ::-webkit-scrollbar {
            width: 8px;
        }
        
        ::-webkit-scrollbar-track {
            background: #0a0a0f;
        }
        
        ::-webkit-scrollbar-thumb {
            background: #2a2a30;
            border-radius: 4px;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>ATLAS Admin</h1>
        <p class="subtitle">Key Management Dashboard</p>
        
        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-value" id="statTotal">0</div>
                <div class="stat-label">Total Keys</div>
            </div>
            <div class="stat-card">
                <div class="stat-value" id="statUsed">0</div>
                <div class="stat-label">Used</div>
            </div>
            <div class="stat-card">
                <div class="stat-value" id="statAvailable">0</div>
                <div class="stat-label">Available</div>
            </div>
            <div class="stat-card">
                <div class="stat-value" id="statExpired">0</div>
                <div class="stat-label">Expired</div>
            </div>
        </div>
        
        <div class="panel">
            <h2>Generate Keys</h2>
            <div class="form-row">
                <input type="number" id="genCount" value="5" min="1" max="100" placeholder="Count">
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
            <h2>All Keys</h2>
            <div class="form-row">
                <button class="secondary" onclick="loadKeys()">Refresh</button>
                <button class="danger" onclick="deleteExpired()">Delete Expired</button>
            </div>
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
        
        async function loadKeys() {
            const res = await fetch('/admin/api/keys');
            const keys = await res.json();
            const list = document.getElementById('keyList');
            
            list.innerHTML = Object.entries(keys).sort((a,b) => {
                return new Date(b[1].created) - new Date(a[1].created);
            }).map(([key, data]) => {
                const now = new Date();
                const expiry = new Date(data.expiry);
                const isExpired = expiry < now;
                
                let status = 'unused';
                let statusText = 'Unused';
                if (data.used) {
                    if (isExpired) {
                        status = 'expired';
                        statusText = 'Expired';
                    } else {
                        status = 'used';
                        statusText = 'Active';
                    }
                }
                
                const durationBadge = `badge-${data.duration}`;
                
                return `
                    <div class="key-item">
                        <div class="key-info">
                            <div class="key-code">
                                ${key}
                                <span class="badge ${durationBadge}">${data.duration}</span>
                                <span class="badge badge-${status}">${statusText}</span>
                            </div>
                            <div class="key-meta">
                                Created: ${new Date(data.created).toLocaleDateString()} | 
                                ${data.used ? `Activated: ${new Date(data.activated).toLocaleDateString()}` : 'Not activated'} |
                                Expires: ${expiry.toLocaleDateString()}
                            </div>
                        </div>
                        <button class="danger" onclick="deleteKey('${key}')">Delete</button>
                    </div>
                `;
            }).join('');
        }
        
        async function deleteKey(key) {
            if (!confirm('Delete this key?')) return;
            await fetch('/admin/api/delete/' + key, {method: 'DELETE'});
            loadKeys();
            loadStats();
        }
        
        async function deleteExpired() {
            if (!confirm('Delete all expired keys?')) return;
            await fetch('/admin/api/reset-expired', {method: 'POST'});
            loadKeys();
            loadStats();
        }
        
        loadStats();
        loadKeys();
        setInterval(() => {
            loadStats();
            loadKeys();
        }, 30000);
    </script>
</body>
</html>
"""

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    print(f"\n🚀 ATLAS Key System starting on port {port}")
    print(f"📊 Admin panel: http://localhost:{port}/admin")
    print(f"🔑 Default admin: {ADMIN_USER} / {ADMIN_PASS[:4]}****")
    app.run(host='0.0.0.0', port=port)