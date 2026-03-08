#!/usr/bin/env python3
"""
ATLAS KEY SYSTEM - BULLETPROOF PERSISTENT VERSION
WITH FULL BACKUP MANAGEMENT
Features: Zero data loss, atomic writes, immediate saves, crash recovery
          Create backups, list backups, RESTORE from any backup
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
import glob
from datetime import datetime, timedelta
from flask import Flask, render_template, render_template_string, jsonify, request, session, redirect, send_file
from flask_cors import CORS
from functools import wraps
import zipfile
import io

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', secrets.token_hex(32))

# Enable CORS for all origins
CORS(app, resources={
    r"/api/*": {
        "origins": "*",
        "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
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
        print(f"[INIT] Created backup directory: {BACKUP_DIR}")

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

def get_backup_list():
    """Get list of all available backups"""
    ensure_dirs()
    backups = []
    
    # Get all backup files
    backup_files = glob.glob(os.path.join(BACKUP_DIR, "*.json.*"))
    
    for file in backup_files:
        filename = os.path.basename(file)
        # Parse timestamp from filename (format: filename.json.YYYYMMDD_HHMMSS)
        parts = filename.split('.')
        if len(parts) >= 3:
            timestamp_str = parts[-1]
            try:
                timestamp = datetime.strptime(timestamp_str, '%Y%m%d_%H%M%S')
                file_type = parts[0]  # keys, profiles, or stats
                
                # Check if this backup is part of a set
                base_name = '.'.join(parts[:-1])
                backups.append({
                    'filename': filename,
                    'filepath': file,
                    'type': file_type,
                    'timestamp': timestamp.isoformat(),
                    'timestamp_str': timestamp.strftime('%Y-%m-%d %H:%M:%S'),
                    'size': os.path.getsize(file)
                })
            except:
                continue
    
    # Group by timestamp
    grouped = {}
    for backup in backups:
        ts = backup['timestamp']
        if ts not in grouped:
            grouped[ts] = {
                'timestamp': backup['timestamp_str'],
                'files': [],
                'id': backup['timestamp'].replace(':', '').replace('-', '').replace('T', '_')
            }
        grouped[ts]['files'].append(backup)
    
    # Convert to list and sort by timestamp (newest first)
    backup_groups = list(grouped.values())
    backup_groups.sort(key=lambda x: x['timestamp'], reverse=True)
    
    return backup_groups

def create_backup():
    """Create timestamped backup of all data files"""
    ensure_dirs()
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    created_files = []

    for filename in ['keys.json', 'profiles.json', 'stats.json']:
        src = os.path.join(BASE_DIR, filename)
        if os.path.exists(src):
            dst = os.path.join(BACKUP_DIR, f"{filename}.{timestamp}")
            shutil.copy2(src, dst)
            created_files.append(dst)

    # Cleanup old backups
    cleanup_backups()
    
    if created_files:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] 📁 Backup created: {timestamp} with {len(created_files)} files")
        return {'success': True, 'timestamp': timestamp, 'files': created_files}
    else:
        return {'success': False, 'message': 'No files to backup'}

def restore_backup(timestamp):
    """Restore data from a specific backup timestamp"""
    try:
        restored_files = []
        
        # Find all backup files with this timestamp
        for filename in ['keys.json', 'profiles.json', 'stats.json']:
            backup_file = os.path.join(BACKUP_DIR, f"{filename}.{timestamp}")
            if os.path.exists(backup_file):
                # Create a backup of current files before restoring
                current_backup = os.path.join(BACKUP_DIR, f"pre_restore_{filename}.{datetime.now().strftime('%Y%m%d_%H%M%S')}")
                if os.path.exists(os.path.join(BASE_DIR, filename)):
                    shutil.copy2(os.path.join(BASE_DIR, filename), current_backup)
                
                # Restore from backup
                shutil.copy2(backup_file, os.path.join(BASE_DIR, filename))
                restored_files.append(filename)
        
        if restored_files:
            # Reload data into memory
            load_data()
            print(f"[{datetime.now().strftime('%H:%M:%S')}] 🔄 Restored from backup: {timestamp}")
            return {'success': True, 'restored': restored_files, 'timestamp': timestamp}
        else:
            return {'success': False, 'message': 'No backup files found for this timestamp'}
            
    except Exception as e:
        print(f"[ERROR] Restore failed: {e}")
        return {'success': False, 'message': str(e)}

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
                print(f"[CLEANUP] Removed old backup: {old}")
            except:
                pass

def auto_save_worker():
    """Auto-save data every 30 seconds if modified"""
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

def generate_hwid():
    """Generate a hardware ID from system info"""
    # In a real app, this would use actual hardware IDs
    # For demo, generate a unique ID
    import subprocess
    try:
        # Try to get a semi-unique machine ID
        if os.name == 'nt':  # Windows
            result = subprocess.run(['wmic', 'csproduct', 'get', 'uuid'], 
                                   capture_output=True, text=True)
            return hashlib.md5(result.stdout.encode()).hexdigest().upper()
        else:  # Linux/Mac
            with open('/etc/machine-id', 'r') as f:
                return hashlib.md5(f.read().encode()).hexdigest().upper()
    except:
        # Fallback to random but persistent ID
        import uuid
        return hashlib.md5(str(uuid.getnode()).encode()).hexdigest().upper()

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
    return jsonify({
        'name': 'ATLAS Key System',
        'status': 'online',
        'version': '2.0',
        'endpoints': ['/api/status', '/api/validate', '/api/profiles/<hwid>', '/admin']
    })

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
    hwid = data.get('hwid', generate_hwid())
    return jsonify(validate_key(key, hwid))

@app.route('/api/profiles/<hwid>', methods=['GET'])
def get_profiles(hwid):
    """Get profiles for a specific HWID"""
    return jsonify(USER_PROFILES.get(hwid, {
        'primary': {'v': 50, 'l': 0, 'r': 0, 'sens': 1.0},
        'secondary': {'v': 50, 'l': 0, 'r': 0, 'sens': 1.0}
    }))

@app.route('/api/profiles/<hwid>', methods=['POST'])
def save_profiles(hwid):
    """Save profiles for a specific HWID"""
    global _data_modified
    data = request.json
    
    # Validate the HWID has an active key
    has_valid_key = False
    for key_data in KEYS.values():
        if key_data.get('hwid') == hwid and key_data.get('used'):
            expiry = datetime.fromisoformat(key_data['expiry'])
            if expiry > datetime.now():
                has_valid_key = True
                break
    
    if not has_valid_key:
        return jsonify({'success': False, 'message': 'No valid key for this HWID'}), 403
    
    USER_PROFILES[hwid] = data
    _data_modified = True
    save_data(force=True)
    return jsonify({'success': True, 'message': 'Profiles saved'})

# ============================================================================
# ADMIN PANEL WITH FULL BACKUP MANAGEMENT
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

# ============================================================================
# NEW BACKUP MANAGEMENT ROUTES
# ============================================================================

@app.route('/admin/api/backup/list', methods=['GET'])
def admin_backup_list():
    """Get list of all backups"""
    auth = request.authorization
    if not auth or auth.username != ADMIN_USER or auth.password != ADMIN_PASS:
        return jsonify({'error': 'Unauthorized'}), 401
    
    backups = get_backup_list()
    return jsonify({'success': True, 'backups': backups})

@app.route('/admin/api/backup/create', methods=['POST'])
def admin_backup_create():
    """Create a new backup"""
    auth = request.authorization
    if not auth or auth.username != ADMIN_USER or auth.password != ADMIN_PASS:
        return jsonify({'error': 'Unauthorized'}), 401

    try:
        # Save current data first
        save_data(force=True)
        
        # Create backup
        result = create_backup()
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/admin/api/backup/restore/<timestamp>', methods=['POST'])
def admin_backup_restore(timestamp):
    """Restore from a specific backup"""
    auth = request.authorization
    if not auth or auth.username != ADMIN_USER or auth.password != ADMIN_PASS:
        return jsonify({'error': 'Unauthorized'}), 401
    
    try:
        # Create a pre-restore backup first (safety)
        create_backup()
        
        # Restore from specified backup
        result = restore_backup(timestamp)
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/admin/api/backup/download/<timestamp>', methods=['GET'])
def admin_backup_download(timestamp):
    """Download all backup files for a timestamp as ZIP"""
    auth = request.authorization
    if not auth or auth.username != ADMIN_USER or auth.password != ADMIN_PASS:
        return jsonify({'error': 'Unauthorized'}), 401
    
    try:
        # Create ZIP file in memory
        memory_file = io.BytesIO()
        with zipfile.ZipFile(memory_file, 'w', zipfile.ZIP_DEFLATED) as zf:
            # Find all backup files with this timestamp
            for filename in ['keys.json', 'profiles.json', 'stats.json']:
                backup_file = os.path.join(BACKUP_DIR, f"{filename}.{timestamp}")
                if os.path.exists(backup_file):
                    zf.write(backup_file, arcname=filename)
        
        memory_file.seek(0)
        
        return send_file(
            memory_file,
            download_name=f'atlas_backup_{timestamp}.zip',
            as_attachment=True,
            mimetype='application/zip'
        )
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ============================================================================
# UPDATED ADMIN HTML WITH BACKUP BROWSER
# ============================================================================

ADMIN_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>ATLAS Admin - Full Backup Management</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; font-family: 'SF Pro Display', -apple-system, sans-serif; }
        body { background: #0a0a0f; color: #f1f1f4; padding: 20px; line-height: 1.6; }
        .container { max-width: 1400px; margin: 0 auto; }
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
        
        button { padding: 12px 24px; background: #6366f1; color: white; border: none; border-radius: 12px; font-weight: 600; cursor: pointer; transition: all 0.2s; }
        button:hover { background: #4f46e5; transform: translateY(-2px); }
        button.secondary { background: #2a2a35; }
        button.secondary:hover { background: #3a3a45; }
        button.danger { background: #ef4444; }
        button.danger:hover { background: #dc2626; }
        button.success { background: #22c55e; }
        button.success:hover { background: #16a34a; }
        
        .key-list { max-height: 400px; overflow-y: auto; border-radius: 12px; background: #0a0a0f; }
        .key-item { display: flex; justify-content: space-between; align-items: center; padding: 16px; border-bottom: 1px solid rgba(255,255,255,0.05); }
        .key-code { font-family: monospace; font-size: 14px; color: #6366f1; }
        .key-meta { font-size: 12px; color: #6b6b7b; }
        
        .badge { display: inline-block; padding: 4px 12px; border-radius: 20px; font-size: 11px; font-weight: 600; margin-left: 8px; }
        .badge-unused { background: rgba(34, 197, 94, 0.2); color: #22c55e; }
        .badge-used { background: rgba(245, 158, 11, 0.2); color: #f59e0b; }
        .badge-expired { background: rgba(239, 68, 68, 0.2); color: #ef4444; }
        
        .generated-keys { background: #0a0a0f; border-radius: 12px; padding: 16px; margin-top: 16px; font-family: monospace; display: none; max-height: 200px; overflow-y: auto; }
        .generated-keys.show { display: block; }
        
        /* Backup browser styles */
        .backup-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 16px; margin-top: 20px; }
        .backup-card { background: #0a0a0f; border: 1px solid rgba(99, 102, 241, 0.3); border-radius: 12px; padding: 16px; transition: all 0.2s; }
        .backup-card:hover { border-color: #6366f1; box-shadow: 0 0 20px rgba(99, 102, 241, 0.2); transform: translateY(-2px); }
        .backup-timestamp { font-size: 16px; font-weight: 600; color: #6366f1; margin-bottom: 8px; }
        .backup-files { font-size: 12px; color: #6b6b7b; margin-bottom: 12px; }
        .backup-actions { display: flex; gap: 8px; }
        .backup-actions button { flex: 1; padding: 8px; font-size: 12px; }
        
        .status-message { padding: 12px; border-radius: 8px; margin-top: 12px; display: none; }
        .status-success { background: rgba(34, 197, 94, 0.2); color: #22c55e; border: 1px solid #22c55e; }
        .status-error { background: rgba(239, 68, 68, 0.2); color: #ef4444; border: 1px solid #ef4444; }
        .status-info { background: rgba(99, 102, 241, 0.2); color: #6366f1; border: 1px solid #6366f1; }
        
        .loading-spinner { display: inline-block; width: 16px; height: 16px; border: 2px solid #6366f1; border-top-color: transparent; border-radius: 50%; animation: spin 1s linear infinite; }
        @keyframes spin { to { transform: rotate(360deg); } }
    </style>
</head>
<body>
    <div class="container">
        <h1>⚡ ATLAS Admin v2.0</h1>
        <p class="subtitle">Complete Key & Backup Management System</p>
        
        <div class="stats-grid">
            <div class="stat-card"><div class="stat-value" id="statTotal">0</div><div class="stat-label">Total Keys</div></div>
            <div class="stat-card"><div class="stat-value" id="statUsed">0</div><div class="stat-label">Used</div></div>
            <div class="stat-card"><div class="stat-value" id="statAvailable">0</div><div class="stat-label">Available</div></div>
            <div class="stat-card"><div class="stat-value" id="statExpired">0</div><div class="stat-label">Expired</div></div>
        </div>
        
        <div class="panel">
            <h2>🔑 Generate Keys</h2>
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
            <h2>💾 Full Backup Management</h2>
            <div class="form-row">
                <button class="success" onclick="createBackup()">📀 Create New Backup</button>
                <button class="secondary" onclick="loadBackups()">🔄 Refresh Backup List</button>
            </div>
            <div id="backupStatus" class="status-message"></div>
            <div id="backupList" class="backup-grid">
                <!-- Backups will be loaded here -->
                <div style="grid-column: 1/-1; text-align: center; padding: 40px; color: #6b6b7b;">
                    Click refresh to load backups
                </div>
            </div>
        </div>
        
        <div class="panel">
            <h2>🔐 All Keys</h2>
            <div class="key-list" id="keyList"></div>
        </div>
    </div>
    
    <script>
        // ====================================================================
        // BACKUP MANAGEMENT
        // ====================================================================
        
        async function loadBackups() {
            const listDiv = document.getElementById('backupList');
            listDiv.innerHTML = '<div style="grid-column: 1/-1; text-align: center; padding: 40px;"><span class="loading-spinner"></span> Loading backups...</div>';
            
            try {
                const res = await fetch('/admin/api/backup/list');
                const data = await res.json();
                
                if (data.success && data.backups.length > 0) {
                    listDiv.innerHTML = data.backups.map(backup => `
                        <div class="backup-card">
                            <div class="backup-timestamp">📅 ${backup.timestamp}</div>
                            <div class="backup-files">
                                ${backup.files.map(f => `📄 ${f.type}`).join(' • ')}
                            </div>
                            <div class="backup-actions">
                                <button class="secondary" onclick="restoreBackup('${backup.id}')">🔄 Restore</button>
                                <button class="secondary" onclick="downloadBackup('${backup.id}')">⬇️ Download</button>
                            </div>
                        </div>
                    `).join('');
                } else {
                    listDiv.innerHTML = '<div style="grid-column: 1/-1; text-align: center; padding: 40px; color: #6b6b7b;">📁 No backups found. Create your first backup!</div>';
                }
            } catch (error) {
                listDiv.innerHTML = '<div style="grid-column: 1/-1; text-align: center; padding: 40px; color: #ef4444;">❌ Error loading backups</div>';
            }
        }
        
        async function createBackup() {
            const status = document.getElementById('backupStatus');
            status.className = 'status-message status-info';
            status.innerHTML = '<span class="loading-spinner"></span> Creating backup...';
            status.style.display = 'block';
            
            try {
                const res = await fetch('/admin/api/backup/create', {method: 'POST'});
                const data = await res.json();
                
                if (data.success) {
                    status.className = 'status-message status-success';
                    status.innerHTML = '✅ Backup created successfully!';
                    loadBackups(); // Refresh the list
                    setTimeout(() => status.style.display = 'none', 3000);
                } else {
                    status.className = 'status-message status-error';
                    status.innerHTML = '❌ ' + (data.message || 'Backup failed');
                }
            } catch (error) {
                status.className = 'status-message status-error';
                status.innerHTML = '❌ Connection error';
            }
        }
        
        async function restoreBackup(timestamp) {
            if (!confirm('⚠️ WARNING: This will overwrite CURRENT data with the backup. Continue?')) {
                return;
            }
            
            const status = document.getElementById('backupStatus');
            status.className = 'status-message status-info';
            status.innerHTML = '<span class="loading-spinner"></span> Restoring backup...';
            status.style.display = 'block';
            
            try {
                const res = await fetch(`/admin/api/backup/restore/${timestamp}`, {method: 'POST'});
                const data = await res.json();
                
                if (data.success) {
                    status.className = 'status-message status-success';
                    status.innerHTML = `✅ Restored ${data.restored.join(', ')} from backup!`;
                    loadStats();
                    loadKeys();
                    loadBackups();
                    setTimeout(() => status.style.display = 'none', 3000);
                } else {
                    status.className = 'status-message status-error';
                    status.innerHTML = '❌ ' + (data.message || 'Restore failed');
                }
            } catch (error) {
                status.className = 'status-message status-error';
                status.innerHTML = '❌ Connection error';
            }
        }
        
        async function downloadBackup(timestamp) {
            window.location.href = `/admin/api/backup/download/${timestamp}`;
        }
        
        // ====================================================================
        // KEY MANAGEMENT
        // ====================================================================
        
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
            box.innerHTML = data.keys.map(k => `<div style="color: #22c55e; padding: 4px;">✅ ${k}</div>`).join('');
            box.classList.add('show');
            
            loadStats();
            loadKeys();
        }
        
        async function loadKeys() {
            const res = await fetch('/admin/api/keys');
            const keys = await res.json();
            
            const list = document.getElementById('keyList');
            const now = new Date();
            
            list.innerHTML = Object.entries(keys)
                .sort((a, b) => new Date(b[1].created) - new Date(a[1].created))
                .map(([key, data]) => {
                    const expiry = new Date(data.expiry);
                    const isExpired = expiry < now;
                    let status = data.used ? (isExpired ? 'expired' : 'used') : 'unused';
                    let statusText = data.used ? (isExpired ? 'Expired' : 'Active') : 'Unused';
                    
                    return `
                        <div class="key-item">
                            <div>
                                <div class="key-code">
                                    ${key} 
                                    <span class="badge badge-${status}">${statusText}</span>
                                </div>
                                <div class="key-meta">
                                    Created: ${new Date(data.created).toLocaleString()} | 
                                    Expires: ${expiry.toLocaleString()}
                                    ${data.hwid ? ` | HWID: ${data.hwid.substring(0, 8)}...` : ''}
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
        
        // ====================================================================
        // INITIALIZATION
        // ====================================================================
        
        // Load everything on page load
        loadStats();
        loadKeys();
        loadBackups();
        
        // Auto-refresh every 30 seconds
        setInterval(() => {
            loadStats();
            loadKeys();
        }, 30000);
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
    print(f"\n🚀 ATLAS Key System (BACKUP EDITION) starting on port {port}")
    print(f"📊 Admin panel: http://localhost:{port}/admin")
    print(f"🔑 Default admin: {ADMIN_USER} / {'*' * len(ADMIN_PASS)}")
    print(f"💾 Data directory: {BASE_DIR}")
    print(f"📁 Backup directory: {BACKUP_DIR}")
    print(f"\n⚡ BACKUP FEATURES:")
    print(f"   ✓ Create backups with one click")
    print(f"   ✓ List all available backups")
    print(f"   ✓ RESTORE from any backup")
    print(f"   ✓ Download backups as ZIP")
    print(f"   ✓ Automatic cleanup (keep last 20)")
    print(f"\nPress Ctrl+C to stop (data will be saved)\n")

    try:
        app.run(host='0.0.0.0', port=port, threaded=True)
    except KeyboardInterrupt:
        emergency_save()