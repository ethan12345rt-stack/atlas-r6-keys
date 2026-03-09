#!/usr/bin/env python3
"""
ATLAS KEY SYSTEM - ULTIMATE EDITION v4.0
Features:
- Individual key tabs with detailed views
- HWID reset capability
- Add time to existing keys
- Universal time display (UTC)
- Key status: used/expired/active
- Cloud backups stored on server
- Auto-backup rotation
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
from flask import Flask, render_template, render_template_string, jsonify, request, session, redirect, send_file, make_response
from flask_cors import CORS, cross_origin
from functools import wraps
import zipfile
import io

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', secrets.token_hex(32))

# Enhanced CORS configuration
CORS(app, resources={
    r"/api/*": {
        "origins": ["http://localhost", "http://127.0.0.1", "http://localhost:3000", 
                   "http://127.0.0.1:3000", "http://localhost:5000", "http://127.0.0.1:5000", "*"],
        "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        "allow_headers": ["Content-Type", "Authorization", "X-Requested-With"],
        "expose_headers": ["Content-Type", "Authorization"],
        "supports_credentials": True
    }
})

@app.after_request
def after_request(response):
    """Add CORS headers to all responses"""
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization,X-Requested-With')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
    response.headers.add('Access-Control-Allow-Credentials', 'true')
    response.headers.add('Access-Control-Max-Age', '3600')
    return response

# ============================================================================
# DATA STORAGE
# ============================================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
KEYS_FILE = os.path.join(BASE_DIR, 'keys.json')
PROFILES_FILE = os.path.join(BASE_DIR, 'profiles.json')
STATS_FILE = os.path.join(BASE_DIR, 'stats.json')
BACKUP_DIR = os.path.join(BASE_DIR, 'backups')
BACKUP_METADATA_FILE = os.path.join(BACKUP_DIR, 'backup_metadata.json')

KEYS = {}
USER_PROFILES = {}
STATS = {'validations': 0, 'generations': 0, 'hwid_resets': 0, 'time_additions': 0, 'last_reset': datetime.now().isoformat()}
BACKUP_METADATA = {}  # Stores info about each backup

ADMIN_USER = "admin"
ADMIN_PASS = os.environ.get('ADMIN_PASSWORD', 'atlas2024')

file_lock = threading.Lock()
_data_modified = False

# ============================================================================
# ENHANCED BACKUP FUNCTIONS - CLOUD STORAGE
# ============================================================================

def ensure_dirs():
    """Ensure all directories exist"""
    if not os.path.exists(BACKUP_DIR):
        os.makedirs(BACKUP_DIR)
        print(f"[INIT] Created backup directory: {BACKUP_DIR}")

def load_backup_metadata():
    """Load backup metadata"""
    global BACKUP_METADATA
    if os.path.exists(BACKUP_METADATA_FILE):
        try:
            with open(BACKUP_METADATA_FILE, 'r') as f:
                BACKUP_METADATA = json.load(f)
        except:
            BACKUP_METADATA = {}
    else:
        BACKUP_METADATA = {}

def save_backup_metadata():
    """Save backup metadata"""
    with file_lock:
        try:
            with open(BACKUP_METADATA_FILE, 'w') as f:
                json.dump(BACKUP_METADATA, f, indent=2)
        except Exception as e:
            print(f"[ERROR] Failed to save backup metadata: {e}")

def atomic_write(filepath, data):
    """ATOMIC FILE WRITE - Prevents corruption"""
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
    """Save all data to disk"""
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
                        print(f"[RECOVERED] Loaded from backup")
                        return data
                    except:
                        pass
                return default
        return default

    KEYS = load_file(KEYS_FILE, {})
    USER_PROFILES = load_file(PROFILES_FILE, {})
    STATS = load_file(STATS_FILE, {'validations': 0, 'generations': 0, 'hwid_resets': 0, 'time_additions': 0, 'last_reset': datetime.now().isoformat()})
    
    # Load backup metadata
    load_backup_metadata()

    print(f"[INFO] Loaded {len(KEYS)} keys, {len(USER_PROFILES)} profiles")
    return True

def get_key_stats():
    """Get detailed key statistics"""
    now = datetime.now()
    total = len(KEYS)
    used = sum(1 for k in KEYS if KEYS[k].get('used', False))
    
    expired = 0
    active = 0
    lifetime = 0
    for k, data in KEYS.items():
        try:
            expiry = datetime.fromisoformat(data['expiry'])
            if data.get('duration') == 'lifetime':
                lifetime += 1
            elif expiry < now:
                expired += 1
            elif data.get('used', False):
                active += 1
        except:
            pass
    
    return {
        'total': total,
        'used': used,
        'unused': total - used,
        'expired': expired,
        'active': active,
        'lifetime': lifetime
    }

def delete_all_keys():
    """Delete ALL keys from the system"""
    global KEYS, _data_modified
    count = len(KEYS)
    KEYS = {}
    _data_modified = True
    save_data(force=True)
    return count

# ============================================================================
# ENHANCED BACKUP FUNCTIONS
# ============================================================================

def create_backup(description=""):
    """Create timestamped backup with metadata - stored on server"""
    ensure_dirs()
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    created_files = []
    
    # Get stats before backup
    key_stats = get_key_stats()
    
    # Create backup files
    for filename in ['keys.json', 'profiles.json', 'stats.json']:
        src = os.path.join(BASE_DIR, filename)
        if os.path.exists(src):
            dst = os.path.join(BACKUP_DIR, f"{filename}.{timestamp}")
            shutil.copy2(src, dst)
            created_files.append(dst)
    
    if created_files:
        # Store metadata
        BACKUP_METADATA[timestamp] = {
            'timestamp': timestamp,
            'datetime': datetime.now().isoformat(),
            'description': description or f"Backup with {key_stats['total']} keys, {key_stats['active']} active",
            'files': [os.path.basename(f) for f in created_files],
            'key_stats': key_stats,
            'size': sum(os.path.getsize(f) for f in created_files)
        }
        save_backup_metadata()
        
        # Cleanup old backups (keep last 100)
        cleanup_backups(100)
        
        print(f"[{datetime.now().strftime('%H:%M:%S')}] 📁 Backup created: {timestamp} - {description}")
        return {'success': True, 'timestamp': timestamp, 'metadata': BACKUP_METADATA[timestamp]}
    else:
        return {'success': False, 'message': 'No files to backup'}

def get_backup_list():
    """Get list of all backups with metadata"""
    ensure_dirs()
    load_backup_metadata()
    
    backups = []
    for timestamp, metadata in BACKUP_METADATA.items():
        # Verify files still exist
        files_exist = all(
            os.path.exists(os.path.join(BACKUP_DIR, f)) 
            for f in metadata.get('files', [])
        )
        
        backups.append({
            'timestamp': timestamp,
            'datetime': metadata.get('datetime', ''),
            'description': metadata.get('description', 'No description'),
            'files': metadata.get('files', []),
            'key_stats': metadata.get('key_stats', {}),
            'size': metadata.get('size', 0),
            'files_exist': files_exist
        })
    
    # Sort by timestamp (newest first)
    backups.sort(key=lambda x: x['timestamp'], reverse=True)
    return backups

def restore_backup(timestamp):
    """Restore data from a specific backup timestamp"""
    try:
        restored_files = []
        
        # Find all backup files with this timestamp
        for filename in ['keys.json', 'profiles.json', 'stats.json']:
            backup_file = os.path.join(BACKUP_DIR, f"{filename}.{timestamp}")
            if os.path.exists(backup_file):
                # Create a pre-restore backup first (safety)
                pre_restore = os.path.join(BACKUP_DIR, f"pre_restore_{filename}.{datetime.now().strftime('%Y%m%d_%H%M%S')}")
                if os.path.exists(os.path.join(BASE_DIR, filename)):
                    shutil.copy2(os.path.join(BASE_DIR, filename), pre_restore)
                
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

def delete_backup(timestamp):
    """Delete a specific backup"""
    try:
        deleted_files = []
        
        # Find and delete all files with this timestamp
        for filename in ['keys.json', 'profiles.json', 'stats.json']:
            backup_file = os.path.join(BACKUP_DIR, f"{filename}.{timestamp}")
            if os.path.exists(backup_file):
                os.remove(backup_file)
                deleted_files.append(f"{filename}.{timestamp}")
        
        # Remove from metadata
        if timestamp in BACKUP_METADATA:
            del BACKUP_METADATA[timestamp]
            save_backup_metadata()
        
        if deleted_files:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] 🗑️ Deleted backup: {timestamp}")
            return {'success': True, 'deleted': deleted_files}
        else:
            return {'success': False, 'message': 'No backup files found'}
            
    except Exception as e:
        return {'success': False, 'message': str(e)}

def delete_all_backups():
    """Delete ALL backups"""
    try:
        # Get all backup files
        backup_files = glob.glob(os.path.join(BACKUP_DIR, "*.json.*"))
        count = len(backup_files)
        
        # Delete each file
        for file in backup_files:
            try:
                os.remove(file)
            except:
                pass
        
        # Clear metadata
        global BACKUP_METADATA
        BACKUP_METADATA = {}
        save_backup_metadata()
        
        print(f"[{datetime.now().strftime('%H:%M:%S')}] 🗑️ Deleted ALL backups ({count} files)")
        return {'success': True, 'deleted_count': count}
        
    except Exception as e:
        return {'success': False, 'message': str(e)}

def cleanup_backups(max_backups=100):
    """Keep only last N backups"""
    backups = get_backup_list()
    if len(backups) > max_backups:
        to_delete = backups[max_backups:]
        for backup in to_delete:
            delete_backup(backup['timestamp'])

# ============================================================================
# SHUTDOWN HANDLERS
# ============================================================================

def emergency_save():
    print("\n[SHUTDOWN] Saving data before exit...")
    save_data(force=True)
    create_backup("Auto-backup before shutdown")
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
    import uuid
    try:
        if os.name == 'nt':  # Windows
            import subprocess
            result = subprocess.run(['wmic', 'csproduct', 'get', 'uuid'], 
                                   capture_output=True, text=True)
            return hashlib.md5(result.stdout.encode()).hexdigest().upper()
        else:  # Linux/Mac
            with open('/etc/machine-id', 'r') as f:
                return hashlib.md5(f.read().encode()).hexdigest().upper()
    except:
        return hashlib.md5(str(uuid.getnode()).encode()).hexdigest().upper()

def parse_duration(duration_str):
    """Parse duration string to timedelta"""
    duration_map = {
        '1hour': timedelta(hours=1),
        '1day': timedelta(days=1),
        '7days': timedelta(days=7),
        '30days': timedelta(days=30),
        '365days': timedelta(days=365),
        'lifetime': timedelta(days=36500)  # 100 years
    }
    return duration_map.get(duration_str, timedelta(days=7))

def format_time_remaining(expiry_date):
    """Format time remaining in days/hours/minutes"""
    now = datetime.now()
    if expiry_date < now:
        return "EXPIRED"
    
    diff = expiry_date - now
    days = diff.days
    hours = diff.seconds // 3600
    minutes = (diff.seconds % 3600) // 60
    
    if days > 0:
        return f"{days}d {hours}h {minutes}m"
    elif hours > 0:
        return f"{hours}h {minutes}m"
    else:
        return f"{minutes}m"

def generate_key(duration='7days'):
    """Generate new key"""
    global _data_modified

    key = '-'.join([secrets.token_hex(2).upper() for _ in range(6)])
    expiry = datetime.now() + parse_duration(duration)

    KEYS[key] = {
        'created': datetime.now().isoformat(),
        'duration': duration,
        'expiry': expiry.isoformat(),
        'used': False,
        'hwid': None,
        'activated': None,
        'activations': 0,
        'status': 'unused'
    }

    STATS['generations'] += 1
    _data_modified = True
    save_data(force=True)
    return key

def validate_key(key, hwid):
    """Validate key and bind to HWID"""
    global _data_modified

    key = key.strip().upper()

    if key not in KEYS:
        return {'valid': False, 'message': 'Invalid key'}

    data = KEYS[key]
    now = datetime.now()
    expiry = datetime.fromisoformat(data['expiry'])

    if data.get('duration') == 'lifetime':
        # Lifetime keys never expire
        pass
    elif expiry < now:
        data['status'] = 'expired'
        _data_modified = True
        save_data(force=True)
        return {'valid': False, 'message': 'Key expired'}

    if data['used'] and data['hwid'] and data['hwid'] != hwid:
        return {'valid': False, 'message': 'Key in use on another device'}

    if not data['used']:
        data['used'] = True
        data['activated'] = now.isoformat()
        data['status'] = 'active'

    data['hwid'] = hwid
    data['activations'] = data.get('activations', 0) + 1

    STATS['validations'] += 1
    _data_modified = True
    save_data(force=True)

    time_remaining = format_time_remaining(expiry)

    return {
        'valid': True,
        'message': 'Key activated',
        'expiry': data['expiry'],
        'duration': data['duration'],
        'time_remaining': time_remaining,
        'status': data['status'],
        'activations': data['activations']
    }

def add_time_to_key(key, additional_time):
    """Add more time to an existing key"""
    global _data_modified
    
    if key not in KEYS:
        return {'success': False, 'message': 'Key not found'}
    
    data = KEYS[key]
    
    if data.get('duration') == 'lifetime':
        return {'success': False, 'message': 'Lifetime keys cannot be extended'}
    
    # Parse additional time (format: "7days", "30days", etc.)
    additional = parse_duration(additional_time)
    current_expiry = datetime.fromisoformat(data['expiry'])
    new_expiry = current_expiry + additional
    
    data['expiry'] = new_expiry.isoformat()
    data['duration'] = f"extended_{additional_time}"
    
    STATS['time_additions'] += 1
    _data_modified = True
    save_data(force=True)
    
    time_remaining = format_time_remaining(new_expiry)
    
    return {
        'success': True,
        'message': f'Added {additional_time} to key',
        'new_expiry': data['expiry'],
        'time_remaining': time_remaining
    }

def reset_key_hwid(key):
    """Reset HWID for a key (allows it to be used on another device)"""
    global _data_modified
    
    if key not in KEYS:
        return {'success': False, 'message': 'Key not found'}
    
    data = KEYS[key]
    data['hwid'] = None
    data['used'] = False
    data['status'] = 'unused'
    
    STATS['hwid_resets'] += 1
    _data_modified = True
    save_data(force=True)
    
    return {'success': True, 'message': 'HWID reset successfully'}

# ============================================================================
# FLASK ROUTES
# ============================================================================

@app.route('/')
def home():
    return jsonify({
        'name': 'ATLAS Key System',
        'status': 'online',
        'version': '4.0',
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
        'generations': STATS.get('generations', 0),
        'hwid_resets': STATS.get('hwid_resets', 0),
        'time_additions': STATS.get('time_additions', 0)
    })

# ============================================================================
# VALIDATE ENDPOINT
# ============================================================================
@app.route('/api/validate', methods=['POST', 'OPTIONS'])
@cross_origin()
def api_validate():
    """Validate license key and bind to HWID"""
    if request.method == 'OPTIONS':
        response = make_response()
        response.headers.add("Access-Control-Allow-Origin", "*")
        response.headers.add('Access-Control-Allow-Headers', "Content-Type,Authorization,X-Requested-With")
        response.headers.add('Access-Control-Allow-Methods', "POST, OPTIONS")
        response.headers.add('Access-Control-Allow-Credentials', "true")
        response.headers.add('Access-Control-Max-Age', "3600")
        return response
    
    try:
        data = request.get_json()
        if not data:
            return jsonify({'valid': False, 'message': 'No data provided'}), 400
            
        key = data.get('key', '').strip().upper()
        hwid = data.get('hwid', generate_hwid())
        
        print(f"[API] Validate attempt - Key: {key}, HWID: {hwid}")
        
        result = validate_key(key, hwid)
        print(f"[API] Result: {result}")
        
        return jsonify(result)
        
    except Exception as e:
        print(f"[API ERROR] {str(e)}")
        return jsonify({'valid': False, 'message': 'Server error'}), 500

# ============================================================================
# KEY MANAGEMENT ROUTES
# ============================================================================

@app.route('/api/key/<key>', methods=['GET'])
def get_key_details(key):
    """Get details for a specific key"""
    if key in KEYS:
        data = KEYS[key].copy()
        data['key'] = key
        expiry = datetime.fromisoformat(data['expiry'])
        data['time_remaining'] = format_time_remaining(expiry)
        return jsonify(data)
    return jsonify({'error': 'Key not found'}), 404

@app.route('/api/key/<key>/add-time', methods=['POST'])
def api_add_time(key):
    """Add time to a key"""
    auth = request.authorization
    if not auth or auth.username != ADMIN_USER or auth.password != ADMIN_PASS:
        return jsonify({'error': 'Unauthorized'}), 401
    
    data = request.json
    duration = data.get('duration', '7days')
    
    result = add_time_to_key(key, duration)
    return jsonify(result)

@app.route('/api/key/<key>/reset-hwid', methods=['POST'])
def api_reset_hwid(key):
    """Reset HWID for a key"""
    auth = request.authorization
    if not auth or auth.username != ADMIN_USER or auth.password != ADMIN_PASS:
        return jsonify({'error': 'Unauthorized'}), 401
    
    result = reset_key_hwid(key)
    return jsonify(result)

# ============================================================================
# PROFILE ENDPOINTS
# ============================================================================
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
            if key_data.get('duration') == 'lifetime' or expiry > datetime.now():
                has_valid_key = True
                break
    
    if not has_valid_key:
        return jsonify({'success': False, 'message': 'No valid key for this HWID'}), 403
    
    USER_PROFILES[hwid] = data
    _data_modified = True
    save_data(force=True)
    return jsonify({'success': True, 'message': 'Profiles saved'})

# ============================================================================
# ADMIN ROUTES
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

    key_stats = get_key_stats()
    
    return jsonify({
        **key_stats,
        'validations': STATS.get('validations', 0),
        'generations': STATS.get('generations', 0),
        'hwid_resets': STATS.get('hwid_resets', 0),
        'time_additions': STATS.get('time_additions', 0),
        'backup_count': len(get_backup_list())
    })

@app.route('/admin/api/keys', methods=['GET'])
def admin_get_keys():
    auth = request.authorization
    if not auth or auth.username != ADMIN_USER or auth.password != ADMIN_PASS:
        return jsonify({'error': 'Unauthorized'}), 401
    
    # Return keys with formatted time remaining
    keys_with_time = {}
    for key, data in KEYS.items():
        keys_with_time[key] = data.copy()
        if data.get('duration') != 'lifetime':
            expiry = datetime.fromisoformat(data['expiry'])
            keys_with_time[key]['time_remaining'] = format_time_remaining(expiry)
    
    return jsonify(keys_with_time)

@app.route('/admin/api/keys/delete-all', methods=['POST'])
def admin_delete_all_keys():
    auth = request.authorization
    if not auth or auth.username != ADMIN_USER or auth.password != ADMIN_PASS:
        return jsonify({'error': 'Unauthorized'}), 401
    
    count = delete_all_keys()
    create_backup(f"Auto-backup before deleting all keys ({count} keys)")
    return jsonify({'success': True, 'deleted_count': count})

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
# BACKUP ROUTES
# ============================================================================
@app.route('/admin/api/backup/list', methods=['GET'])
def admin_backup_list():
    auth = request.authorization
    if not auth or auth.username != ADMIN_USER or auth.password != ADMIN_PASS:
        return jsonify({'error': 'Unauthorized'}), 401
    
    backups = get_backup_list()
    return jsonify({'success': True, 'backups': backups})

@app.route('/admin/api/backup/create', methods=['POST'])
def admin_backup_create():
    auth = request.authorization
    if not auth or auth.username != ADMIN_USER or auth.password != ADMIN_PASS:
        return jsonify({'error': 'Unauthorized'}), 401

    data = request.json or {}
    description = data.get('description', 'Manual backup')
    
    try:
        save_data(force=True)
        result = create_backup(description)
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/admin/api/backup/restore/<timestamp>', methods=['POST'])
def admin_backup_restore(timestamp):
    auth = request.authorization
    if not auth or auth.username != ADMIN_USER or auth.password != ADMIN_PASS:
        return jsonify({'error': 'Unauthorized'}), 401
    
    try:
        create_backup(f"Pre-restore backup before restoring {timestamp}")
        result = restore_backup(timestamp)
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/admin/api/backup/delete/<timestamp>', methods=['DELETE'])
def admin_backup_delete(timestamp):
    auth = request.authorization
    if not auth or auth.username != ADMIN_USER or auth.password != ADMIN_PASS:
        return jsonify({'error': 'Unauthorized'}), 401
    
    result = delete_backup(timestamp)
    return jsonify(result)

@app.route('/admin/api/backup/delete-all', methods=['POST'])
def admin_backup_delete_all():
    auth = request.authorization
    if not auth or auth.username != ADMIN_USER or auth.password != ADMIN_PASS:
        return jsonify({'error': 'Unauthorized'}), 401
    
    result = delete_all_backups()
    return jsonify(result)

@app.route('/admin/api/backup/download/<timestamp>', methods=['GET'])
def admin_backup_download(timestamp):
    auth = request.authorization
    if not auth or auth.username != ADMIN_USER or auth.password != ADMIN_PASS:
        return jsonify({'error': 'Unauthorized'}), 401
    
    try:
        memory_file = io.BytesIO()
        with zipfile.ZipFile(memory_file, 'w', zipfile.ZIP_DEFLATED) as zf:
            for filename in ['keys.json', 'profiles.json', 'stats.json']:
                backup_file = os.path.join(BACKUP_DIR, f"{filename}.{timestamp}")
                if os.path.exists(backup_file):
                    zf.write(backup_file, arcname=filename)
            
            # Add metadata if available
            if timestamp in BACKUP_METADATA:
                metadata_file = os.path.join(BACKUP_DIR, f"metadata.{timestamp}.json")
                with open(metadata_file, 'w') as f:
                    json.dump(BACKUP_METADATA[timestamp], f, indent=2)
                zf.write(metadata_file, arcname='backup_info.json')
                os.remove(metadata_file)
        
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
# ADMIN HTML - UPDATED WITH KEY TABS AND MANAGEMENT
# ============================================================================

ADMIN_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>ATLAS Admin Ultimate v4.0</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; font-family: 'Inter', -apple-system, sans-serif; }
        body { background: #0a0a0f; color: #f1f1f4; padding: 20px; }
        .container { max-width: 1600px; margin: 0 auto; }
        
        h1 { font-size: 32px; background: linear-gradient(135deg, #9d4edd, #c77dff); -webkit-background-clip: text; -webkit-text-fill-color: transparent; margin-bottom: 8px; }
        .subtitle { color: #6b6b7b; margin-bottom: 30px; }
        
        /* Tab Navigation */
        .tabs {
            display: flex;
            gap: 4px;
            margin-bottom: 24px;
            background: #141418;
            padding: 6px;
            border-radius: 16px;
            border: 1px solid rgba(255,255,255,0.06);
        }
        .tab {
            flex: 1;
            padding: 14px;
            text-align: center;
            border-radius: 12px;
            cursor: pointer;
            font-weight: 600;
            color: #a0a0b0;
            transition: all 0.2s;
        }
        .tab:hover { background: rgba(255,255,255,0.05); color: white; }
        .tab.active {
            background: linear-gradient(135deg, #9d4edd20, #6b2d8f20);
            color: #c77dff;
            border: 1px solid #9d4edd40;
        }
        
        /* Panels */
        .panel {
            display: none;
            background: #141418;
            border: 1px solid rgba(255,255,255,0.06);
            border-radius: 24px;
            padding: 24px;
            margin-bottom: 20px;
        }
        .panel.active { display: block; }
        
        .panel h2 { 
            font-size: 18px; 
            margin-bottom: 20px; 
            color: white;
            display: flex;
            align-items: center;
            gap: 8px;
        }
        
        .stats-grid { 
            display: grid; 
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); 
            gap: 16px; 
            margin-bottom: 30px; 
        }
        .stat-card { 
            background: #0a0a0f; 
            border: 1px solid rgba(255,255,255,0.03); 
            border-radius: 16px; 
            padding: 20px; 
            text-align: center; 
        }
        .stat-value { 
            font-size: 32px; 
            font-weight: 700; 
            color: #9d4edd; 
            margin-bottom: 4px; 
        }
        .stat-label { 
            font-size: 12px; 
            color: #6b6b7b; 
            text-transform: uppercase; 
        }
        
        .action-bar {
            display: flex;
            gap: 12px;
            margin-bottom: 24px;
            flex-wrap: wrap;
            align-items: center;
        }
        
        button {
            padding: 12px 24px;
            border: none;
            border-radius: 12px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s;
            font-size: 14px;
        }
        button.primary { background: #9d4edd; color: white; }
        button.primary:hover { background: #6b2d8f; transform: translateY(-2px); }
        button.secondary { background: #2a2a35; color: white; }
        button.secondary:hover { background: #3a3a45; }
        button.success { background: #22c55e; color: white; }
        button.success:hover { background: #16a34a; }
        button.warning { background: #f59e0b; color: black; }
        button.warning:hover { background: #d97706; }
        button.danger { background: #ef4444; color: white; }
        button.danger:hover { background: #dc2626; }
        
        input, select {
            padding: 12px 16px;
            background: #0a0a0f;
            border: 1px solid rgba(255,255,255,0.1);
            border-radius: 12px;
            color: white;
            font-size: 14px;
            min-width: 150px;
        }
        
        /* Key Tabs */
        .key-tabs-container {
            margin-bottom: 20px;
        }
        
        .key-tabs-scroll {
            display: flex;
            gap: 8px;
            overflow-x: auto;
            padding: 8px 0;
            margin-bottom: 16px;
            scrollbar-width: thin;
            scrollbar-color: #9d4edd #2a2a35;
        }
        
        .key-tabs-scroll::-webkit-scrollbar {
            height: 6px;
        }
        
        .key-tabs-scroll::-webkit-scrollbar-track {
            background: #2a2a35;
            border-radius: 10px;
        }
        
        .key-tabs-scroll::-webkit-scrollbar-thumb {
            background: #9d4edd;
            border-radius: 10px;
        }
        
        .key-tab {
            padding: 10px 20px;
            background: #2a2a35;
            border-radius: 30px;
            cursor: pointer;
            white-space: nowrap;
            font-size: 13px;
            transition: all 0.2s;
            border: 1px solid transparent;
        }
        
        .key-tab:hover {
            background: #3a3a45;
        }
        
        .key-tab.active {
            background: #9d4edd;
            color: white;
            border-color: #c77dff;
        }
        
        .key-tab.used { border-left: 3px solid #f59e0b; }
        .key-tab.expired { border-left: 3px solid #ef4444; }
        .key-tab.active.used { border-left: 3px solid #f59e0b; }
        .key-tab.active.expired { border-left: 3px solid #ef4444; }
        
        /* Key Detail Panel */
        .key-detail-panel {
            background: #0a0a0f;
            border-radius: 16px;
            padding: 24px;
            border: 1px solid rgba(157, 78, 221, 0.3);
        }
        
        .key-detail-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 20px;
            padding-bottom: 15px;
            border-bottom: 1px solid rgba(255,255,255,0.1);
        }
        
        .key-detail-code {
            font-family: monospace;
            font-size: 24px;
            color: #9d4edd;
            font-weight: 600;
        }
        
        .key-detail-status {
            padding: 6px 16px;
            border-radius: 30px;
            font-size: 14px;
            font-weight: 600;
        }
        
        .status-unused { background: rgba(34, 197, 94, 0.2); color: #22c55e; }
        .status-used { background: rgba(245, 158, 11, 0.2); color: #f59e0b; }
        .status-active { background: rgba(99, 102, 241, 0.2); color: #818cf8; }
        .status-expired { background: rgba(239, 68, 68, 0.2); color: #ef4444; }
        .status-lifetime { background: rgba(157, 78, 221, 0.2); color: #c77dff; }
        
        .key-detail-grid {
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 20px;
            margin-bottom: 30px;
        }
        
        .key-detail-item {
            background: #141418;
            border-radius: 12px;
            padding: 16px;
        }
        
        .key-detail-label {
            color: #6b6b7b;
            font-size: 12px;
            margin-bottom: 8px;
        }
        
        .key-detail-value {
            font-size: 18px;
            font-weight: 600;
            color: white;
        }
        
        .key-detail-value.small {
            font-size: 14px;
            font-family: monospace;
        }
        
        .time-remaining {
            font-size: 24px;
            font-weight: 700;
            color: #22c55e;
        }
        
        .time-remaining.expired {
            color: #ef4444;
        }
        
        .key-action-buttons {
            display: flex;
            gap: 12px;
            margin-top: 20px;
        }
        
        .key-list { 
            max-height: 500px; 
            overflow-y: auto; 
            border-radius: 16px; 
            background: #0a0a0f; 
            display: none;
        }
        
        .key-item { 
            display: flex; 
            justify-content: space-between; 
            align-items: center; 
            padding: 16px; 
            border-bottom: 1px solid rgba(255,255,255,0.05); 
        }
        
        .key-code { 
            font-family: monospace; 
            font-size: 14px; 
            color: #9d4edd; 
            font-weight: 600;
        }
        
        .key-meta { 
            font-size: 12px; 
            color: #6b6b7b; 
            margin-top: 4px; 
        }
        
        .badge {
            display: inline-block;
            padding: 4px 12px;
            border-radius: 100px;
            font-size: 11px;
            font-weight: 600;
            margin-left: 8px;
        }
        .badge-unused { background: rgba(34, 197, 94, 0.2); color: #22c55e; }
        .badge-used { background: rgba(245, 158, 11, 0.2); color: #f59e0b; }
        .badge-active { background: rgba(99, 102, 241, 0.2); color: #818cf8; }
        .badge-expired { background: rgba(239, 68, 68, 0.2); color: #ef4444; }
        .badge-lifetime { background: rgba(157, 78, 221, 0.2); color: #c77dff; }
        
        .backup-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(350px, 1fr));
            gap: 16px;
            margin-top: 20px;
        }
        
        .backup-card {
            background: #0a0a0f;
            border: 1px solid rgba(157, 78, 221, 0.3);
            border-radius: 16px;
            padding: 16px;
            transition: all 0.2s;
        }
        
        .backup-card:hover {
            border-color: #9d4edd;
            box-shadow: 0 0 20px rgba(157, 78, 221, 0.2);
        }
        
        .backup-timestamp {
            font-size: 16px;
            font-weight: 600;
            color: #9d4edd;
            margin-bottom: 8px;
        }
        
        .backup-description {
            color: #d0d0e0;
            font-size: 14px;
            margin-bottom: 8px;
        }
        
        .backup-meta {
            font-size: 12px;
            color: #6b6b7b;
            margin-bottom: 12px;
        }
        
        .backup-actions {
            display: flex;
            gap: 8px;
        }
        
        .backup-actions button {
            flex: 1;
            padding: 8px;
            font-size: 12px;
        }
        
        .modal-overlay {
            display: none;
            position: fixed;
            top: 0; left: 0; width: 100%; height: 100%;
            background: rgba(0,0,0,0.8);
            backdrop-filter: blur(5px);
            justify-content: center;
            align-items: center;
            z-index: 1000;
        }
        
        .modal {
            background: #141418;
            border: 2px solid #9d4edd;
            border-radius: 24px;
            padding: 30px;
            max-width: 500px;
            width: 90%;
            text-align: center;
        }
        
        .modal p {
            color: white;
            font-size: 18px;
            margin-bottom: 24px;
        }
        
        .modal-actions {
            display: flex;
            gap: 12px;
            justify-content: center;
            flex-wrap: wrap;
        }
        
        .search-box {
            margin-bottom: 16px;
        }
        
        .search-box input {
            width: 100%;
        }
        
        .loading {
            display: inline-block;
            width: 16px;
            height: 16px;
            border: 2px solid #9d4edd;
            border-top-color: transparent;
            border-radius: 50%;
            animation: spin 1s linear infinite;
        }
        @keyframes spin { to { transform: rotate(360deg); } }
        
        .status-message {
            padding: 12px;
            border-radius: 8px;
            margin: 12px 0;
            display: none;
        }
        .status-success { background: rgba(34, 197, 94, 0.2); color: #22c55e; border: 1px solid #22c55e; }
        .status-error { background: rgba(239, 68, 68, 0.2); color: #ef4444; border: 1px solid #ef4444; }
        .status-info { background: rgba(157, 78, 221, 0.2); color: #c77dff; border: 1px solid #9d4edd; }
        
        .duration-selector {
            display: flex;
            gap: 10px;
            margin: 20px 0;
            flex-wrap: wrap;
            justify-content: center;
        }
        
        .duration-btn {
            padding: 8px 16px;
            background: #2a2a35;
            border: 1px solid transparent;
            border-radius: 30px;
            cursor: pointer;
            transition: all 0.2s;
        }
        
        .duration-btn:hover {
            background: #3a3a45;
        }
        
        .duration-btn.selected {
            background: #9d4edd;
            color: white;
            border-color: #c77dff;
        }
    </style>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
</head>
<body>
    <div class="container">
        <h1>⚡ ATLAS ADMIN ULTIMATE v4.0</h1>
        <p class="subtitle">Complete Key & Backup Management System</p>
        
        <!-- Tab Navigation -->
        <div class="tabs">
            <div class="tab active" onclick="switchTab('dashboard')">📊 DASHBOARD</div>
            <div class="tab" onclick="switchTab('keys')">🔑 KEYS</div>
            <div class="tab" onclick="switchTab('backups')">💾 BACKUPS</div>
        </div>
        
        <!-- DASHBOARD PANEL -->
        <div id="dashboardPanel" class="panel active">
            <h2>📊 System Overview</h2>
            <div class="stats-grid" id="dashboardStats">
                <div class="stat-card"><div class="stat-value" id="statTotal">0</div><div class="stat-label">Total Keys</div></div>
                <div class="stat-card"><div class="stat-value" id="statUsed">0</div><div class="stat-label">Used</div></div>
                <div class="stat-card"><div class="stat-value" id="statUnused">0</div><div class="stat-label">Available</div></div>
                <div class="stat-card"><div class="stat-value" id="statActive">0</div><div class="stat-label">Active</div></div>
                <div class="stat-card"><div class="stat-value" id="statExpired">0</div><div class="stat-label">Expired</div></div>
                <div class="stat-card"><div class="stat-value" id="statLifetime">0</div><div class="stat-label">Lifetime</div></div>
            </div>
            
            <div class="stats-grid">
                <div class="stat-card"><div class="stat-value" id="statValidations">0</div><div class="stat-label">Validations</div></div>
                <div class="stat-card"><div class="stat-value" id="statGenerations">0</div><div class="stat-label">Generations</div></div>
                <div class="stat-card"><div class="stat-value" id="statHwidResets">0</div><div class="stat-label">HWID Resets</div></div>
                <div class="stat-card"><div class="stat-value" id="statTimeAdditions">0</div><div class="stat-label">Time Additions</div></div>
                <div class="stat-card"><div class="stat-value" id="statBackups">0</div><div class="stat-label">Backups</div></div>
            </div>
            
            <div class="action-bar">
                <button class="primary" onclick="createBackup()">📀 Create Backup</button>
                <button class="secondary" onclick="refreshAll()">🔄 Refresh</button>
            </div>
        </div>
        
        <!-- KEYS PANEL -->
        <div id="keysPanel" class="panel">
            <h2>🔑 Key Management</h2>
            
            <div class="action-bar">
                <input type="number" id="genCount" value="5" min="1" max="100" style="width: 80px;">
                <select id="genDuration">
                    <option value="1hour">1 Hour</option>
                    <option value="1day">1 Day</option>
                    <option value="7days" selected>7 Days</option>
                    <option value="30days">30 Days</option>
                    <option value="365days">365 Days</option>
                    <option value="lifetime">Lifetime</option>
                </select>
                <button class="primary" onclick="generateKeys()">Generate Keys</button>
                <button class="danger" onclick="confirmDeleteAllKeys()">🗑️ Delete ALL Keys</button>
            </div>
            
            <div id="generatedKeys" style="background: #0a0a0f; border-radius: 12px; padding: 16px; margin-bottom: 20px; display: none;"></div>
            
            <!-- Key Tabs View -->
            <div class="key-tabs-container">
                <div class="key-tabs-scroll" id="keyTabs"></div>
                
                <!-- Key Detail Panel -->
                <div id="keyDetailPanel" class="key-detail-panel" style="display: none;">
                    <div class="key-detail-header">
                        <span class="key-detail-code" id="detailKeyCode"></span>
                        <span class="key-detail-status" id="detailKeyStatus"></span>
                    </div>
                    
                    <div class="key-detail-grid">
                        <div class="key-detail-item">
                            <div class="key-detail-label">Created</div>
                            <div class="key-detail-value small" id="detailCreated"></div>
                        </div>
                        <div class="key-detail-item">
                            <div class="key-detail-label">Expires (UTC)</div>
                            <div class="key-detail-value small" id="detailExpiry"></div>
                        </div>
                        <div class="key-detail-item">
                            <div class="key-detail-label">Duration</div>
                            <div class="key-detail-value" id="detailDuration"></div>
                        </div>
                        <div class="key-detail-item">
                            <div class="key-detail-label">Time Remaining</div>
                            <div class="time-remaining" id="detailTimeRemaining"></div>
                        </div>
                        <div class="key-detail-item">
                            <div class="key-detail-label">HWID</div>
                            <div class="key-detail-value small" id="detailHwid">None</div>
                        </div>
                        <div class="key-detail-item">
                            <div class="key-detail-label">Activations</div>
                            <div class="key-detail-value" id="detailActivations">0</div>
                        </div>
                    </div>
                    
                    <div class="key-action-buttons">
                        <button class="warning" onclick="showAddTimeModal()">⏱️ Add Time</button>
                        <button class="secondary" onclick="resetHwid()">🔄 Reset HWID</button>
                        <button class="danger" onclick="deleteCurrentKey()">🗑️ Delete Key</button>
                    </div>
                </div>
            </div>
            
            <!-- Legacy Key List (hidden by default) -->
            <div class="key-list" id="keyList"></div>
        </div>
        
        <!-- BACKUPS PANEL -->
        <div id="backupsPanel" class="panel">
            <h2>💾 Backup Management</h2>
            
            <div class="action-bar">
                <button class="primary" onclick="showCreateBackupModal()">📀 Create Backup</button>
                <button class="danger" onclick="confirmDeleteAllBackups()">🗑️ Delete ALL Backups</button>
                <button class="secondary" onclick="loadBackups()">🔄 Refresh</button>
            </div>
            
            <div id="backupStatus" class="status-message"></div>
            <div id="backupList" class="backup-grid"></div>
        </div>
    </div>
    
    <!-- Delete All Keys Confirmation Modal -->
    <div id="deleteAllKeysModal" class="modal-overlay">
        <div class="modal">
            <p>⚠️ Delete ALL keys?<br><span style="font-size: 14px; color: #ef4444;">This cannot be undone!</span></p>
            <div class="modal-actions">
                <button class="danger" onclick="deleteAllKeys()">YES, DELETE</button>
                <button class="secondary" onclick="closeModal()">CANCEL</button>
            </div>
        </div>
    </div>
    
    <!-- Delete All Backups Confirmation Modal -->
    <div id="deleteAllBackupsModal" class="modal-overlay">
        <div class="modal">
            <p>⚠️ Delete ALL backups?<br><span style="font-size: 14px; color: #ef4444;">This cannot be undone!</span></p>
            <div class="modal-actions">
                <button class="danger" onclick="deleteAllBackups()">YES, DELETE</button>
                <button class="secondary" onclick="closeModal()">CANCEL</button>
            </div>
        </div>
    </div>
    
    <!-- Create Backup Modal -->
    <div id="createBackupModal" class="modal-overlay">
        <div class="modal" style="max-width: 500px;">
            <p>📀 Create Backup</p>
            <input type="text" id="backupDescription" placeholder="Backup description (optional)" style="width: 100%; margin-bottom: 20px;">
            <div class="modal-actions">
                <button class="primary" onclick="createBackupWithDesc()">CREATE</button>
                <button class="secondary" onclick="closeModal()">CANCEL</button>
            </div>
        </div>
    </div>
    
    <!-- Add Time Modal -->
    <div id="addTimeModal" class="modal-overlay">
        <div class="modal" style="max-width: 500px;">
            <p>⏱️ Add Time to Key</p>
            <div class="duration-selector" id="durationSelector">
                <button class="duration-btn selected" data-duration="1hour">1 Hour</button>
                <button class="duration-btn" data-duration="1day">1 Day</button>
                <button class="duration-btn" data-duration="7days">7 Days</button>
                <button class="duration-btn" data-duration="30days">30 Days</button>
                <button class="duration-btn" data-duration="365days">365 Days</button>
            </div>
            <div class="modal-actions">
                <button class="success" onclick="addTimeToKey()">ADD TIME</button>
                <button class="secondary" onclick="closeModal()">CANCEL</button>
            </div>
        </div>
    </div>
    
    <script>
        let allKeys = {};
        let currentModal = null;
        let selectedKey = null;
        let selectedDuration = '1hour';
        
        // Tab switching
        function switchTab(tab) {
            document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
            document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
            
            if (tab === 'dashboard') {
                document.querySelector('.tabs div:nth-child(1)').classList.add('active');
                document.getElementById('dashboardPanel').classList.add('active');
                loadStats();
            } else if (tab === 'keys') {
                document.querySelector('.tabs div:nth-child(2)').classList.add('active');
                document.getElementById('keysPanel').classList.add('active');
                loadKeys();
            } else if (tab === 'backups') {
                document.querySelector('.tabs div:nth-child(3)').classList.add('active');
                document.getElementById('backupsPanel').classList.add('active');
                loadBackups();
            }
        }
        
        // Load stats
        async function loadStats() {
            const res = await fetch('/admin/api/stats');
            const data = await res.json();
            
            document.getElementById('statTotal').textContent = data.total || 0;
            document.getElementById('statUsed').textContent = data.used || 0;
            document.getElementById('statUnused').textContent = data.unused || 0;
            document.getElementById('statActive').textContent = data.active || 0;
            document.getElementById('statExpired').textContent = data.expired || 0;
            document.getElementById('statLifetime').textContent = data.lifetime || 0;
            document.getElementById('statValidations').textContent = data.validations || 0;
            document.getElementById('statGenerations').textContent = data.generations || 0;
            document.getElementById('statHwidResets').textContent = data.hwid_resets || 0;
            document.getElementById('statTimeAdditions').textContent = data.time_additions || 0;
            document.getElementById('statBackups').textContent = data.backup_count || 0;
        }
        
        // Load keys
        async function loadKeys() {
            const res = await fetch('/admin/api/keys');
            allKeys = await res.json();
            renderKeyTabs();
        }
        
        function renderKeyTabs() {
            const tabsContainer = document.getElementById('keyTabs');
            const now = new Date();
            
            tabsContainer.innerHTML = '';
            
            // Sort keys by created date (newest first)
            const sortedKeys = Object.entries(allKeys).sort((a, b) => 
                new Date(b[1].created) - new Date(a[1].created)
            );
            
            for (const [key, data] of sortedKeys) {
                const expiry = new Date(data.expiry);
                const isExpired = expiry < now && data.duration !== 'lifetime';
                
                let statusClass = '';
                if (data.duration === 'lifetime') statusClass = 'lifetime';
                else if (data.used) statusClass = isExpired ? 'expired' : 'used';
                else statusClass = 'unused';
                
                const tab = document.createElement('div');
                tab.className = `key-tab ${statusClass}`;
                tab.setAttribute('data-key', key);
                tab.onclick = () => selectKey(key);
                tab.innerHTML = `
                    ${key.substring(0, 14)}...
                    ${data.duration === 'lifetime' ? '∞' : ''}
                `;
                tabsContainer.appendChild(tab);
            }
            
            // Select first key by default if none selected
            if (sortedKeys.length > 0 && !selectedKey) {
                selectKey(sortedKeys[0][0]);
            }
        }
        
        function selectKey(key) {
            selectedKey = key;
            
            // Update tab active state
            document.querySelectorAll('.key-tab').forEach(tab => {
                if (tab.getAttribute('data-key') === key) {
                    tab.classList.add('active');
                } else {
                    tab.classList.remove('active');
                }
            });
            
            // Show detail panel
            document.getElementById('keyDetailPanel').style.display = 'block';
            
            // Populate details
            const data = allKeys[key];
            const expiry = new Date(data.expiry);
            const now = new Date();
            const isExpired = expiry < now && data.duration !== 'lifetime';
            
            document.getElementById('detailKeyCode').textContent = key;
            
            let statusText = '';
            if (data.duration === 'lifetime') statusText = 'LIFETIME';
            else if (data.used) statusText = isExpired ? 'EXPIRED' : 'ACTIVE';
            else statusText = 'UNUSED';
            
            const statusEl = document.getElementById('detailKeyStatus');
            statusEl.textContent = statusText;
            statusEl.className = `key-detail-status status-${data.duration === 'lifetime' ? 'lifetime' : (data.used ? (isExpired ? 'expired' : 'active') : 'unused')}`;
            
            document.getElementById('detailCreated').textContent = new Date(data.created).toLocaleString();
            document.getElementById('detailExpiry').textContent = data.duration === 'lifetime' ? 'Never' : new Date(data.expiry).toLocaleString();
            document.getElementById('detailDuration').textContent = data.duration;
            document.getElementById('detailHwid').textContent = data.hwid ? data.hwid.substring(0, 16) + '...' : 'None';
            document.getElementById('detailActivations').textContent = data.activations || 0;
            
            const timeRemainingEl = document.getElementById('detailTimeRemaining');
            if (data.duration === 'lifetime') {
                timeRemainingEl.textContent = '∞ LIFETIME';
                timeRemainingEl.className = 'time-remaining';
            } else if (isExpired) {
                timeRemainingEl.textContent = 'EXPIRED';
                timeRemainingEl.className = 'time-remaining expired';
            } else {
                timeRemainingEl.textContent = data.time_remaining || 'Calculating...';
                timeRemainingEl.className = 'time-remaining';
            }
        }
        
        function filterKeys() {
            const search = document.getElementById('keySearch').value.toLowerCase();
            if (!search) {
                renderKeyTabs();
                return;
            }
            
            // Filter and re-render tabs
            const filtered = Object.fromEntries(
                Object.entries(allKeys).filter(([key]) => 
                    key.toLowerCase().includes(search)
                )
            );
            
            // Temporarily replace allKeys for display
            const originalKeys = allKeys;
            allKeys = filtered;
            renderKeyTabs();
            allKeys = originalKeys;
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
            
            const box = document.getElementById('generatedKeys');
            box.innerHTML = '<div style="color: #22c55e; padding: 10px;">✅ Generated ' + data.keys.length + ' keys:</div>' +
                data.keys.map(k => `<div style="color: #9d4edd; padding: 4px; font-family: monospace;">${k}</div>`).join('');
            box.style.display = 'block';
            setTimeout(() => box.style.display = 'none', 10000);
            
            loadStats();
            loadKeys();
        }
        
        async function deleteKey(key) {
            if (!confirm(`Delete key ${key}?`)) return;
            await fetch('/admin/api/delete/' + key, {method: 'DELETE'});
            if (selectedKey === key) {
                selectedKey = null;
                document.getElementById('keyDetailPanel').style.display = 'none';
            }
            loadKeys();
            loadStats();
        }
        
        function deleteCurrentKey() {
            if (selectedKey) {
                deleteKey(selectedKey);
            }
        }
        
        // Reset HWID
        async function resetHwid() {
            if (!selectedKey) return;
            if (!confirm(`Reset HWID for key ${selectedKey.substring(0, 14)}...?`)) return;
            
            const res = await fetch(`/api/key/${selectedKey}/reset-hwid`, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'}
            });
            
            const data = await res.json();
            if (data.success) {
                alert('✅ HWID reset successfully');
                loadKeys();
            } else {
                alert('❌ ' + data.message);
            }
        }
        
        // Add Time functions
        function showAddTimeModal() {
            if (!selectedKey) return;
            currentModal = 'addTimeModal';
            document.getElementById('addTimeModal').style.display = 'flex';
            
            // Setup duration buttons
            document.querySelectorAll('.duration-btn').forEach(btn => {
                btn.addEventListener('click', function() {
                    document.querySelectorAll('.duration-btn').forEach(b => b.classList.remove('selected'));
                    this.classList.add('selected');
                    selectedDuration = this.getAttribute('data-duration');
                });
            });
        }
        
        async function addTimeToKey() {
            if (!selectedKey) return;
            
            const res = await fetch(`/api/key/${selectedKey}/add-time`, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({duration: selectedDuration})
            });
            
            const data = await res.json();
            closeModal();
            
            if (data.success) {
                alert(`✅ ${data.message}`);
                loadKeys();
                loadStats();
            } else {
                alert('❌ ' + data.message);
            }
        }
        
        // Delete ALL keys
        function confirmDeleteAllKeys() {
            currentModal = 'deleteAllKeysModal';
            document.getElementById('deleteAllKeysModal').style.display = 'flex';
        }
        
        async function deleteAllKeys() {
            closeModal();
            const res = await fetch('/admin/api/keys/delete-all', {method: 'POST'});
            const data = await res.json();
            
            if (data.success) {
                alert(`✅ Deleted ${data.deleted_count} keys`);
                selectedKey = null;
                document.getElementById('keyDetailPanel').style.display = 'none';
                loadStats();
                loadKeys();
            }
        }
        
        // Backup functions
        async function loadBackups() {
            const listDiv = document.getElementById('backupList');
            listDiv.innerHTML = '<div style="grid-column: 1/-1; text-align: center; padding: 40px;"><span class="loading"></span> Loading backups...</div>';
            
            const res = await fetch('/admin/api/backup/list');
            const data = await res.json();
            
            if (data.success && data.backups.length > 0) {
                listDiv.innerHTML = data.backups.map(backup => `
                    <div class="backup-card">
                        <div class="backup-timestamp">📅 ${new Date(backup.datetime).toLocaleString()}</div>
                        <div class="backup-description">${backup.description}</div>
                        <div class="backup-meta">
                            Files: ${backup.files.length} | 
                            Keys: ${backup.key_stats?.total || 0} (${backup.key_stats?.active || 0} active) |
                            Size: ${(backup.size / 1024).toFixed(1)} KB
                        </div>
                        <div class="backup-actions">
                            <button class="secondary" onclick="restoreBackup('${backup.timestamp}')">🔄 Restore</button>
                            <button class="secondary" onclick="downloadBackup('${backup.timestamp}')">⬇️ Download</button>
                            <button class="danger" onclick="deleteBackup('${backup.timestamp}')">🗑️ Delete</button>
                        </div>
                    </div>
                `).join('');
            } else {
                listDiv.innerHTML = '<div style="grid-column: 1/-1; text-align: center; padding: 40px; color: #6b6b7b;">📁 No backups found</div>';
            }
        }
        
        function showCreateBackupModal() {
            currentModal = 'createBackupModal';
            document.getElementById('createBackupModal').style.display = 'flex';
            document.getElementById('backupDescription').value = '';
        }
        
        async function createBackupWithDesc() {
            const description = document.getElementById('backupDescription').value;
            closeModal();
            
            const status = document.getElementById('backupStatus');
            status.className = 'status-message status-info';
            status.innerHTML = '<span class="loading"></span> Creating backup...';
            status.style.display = 'block';
            
            const res = await fetch('/admin/api/backup/create', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({description: description})
            });
            
            const data = await res.json();
            
            if (data.success) {
                status.className = 'status-message status-success';
                status.innerHTML = '✅ Backup created successfully!';
                loadBackups();
                loadStats();
                setTimeout(() => status.style.display = 'none', 3000);
            } else {
                status.className = 'status-message status-error';
                status.innerHTML = '❌ ' + (data.message || 'Backup failed');
            }
        }
        
        async function createBackup() {
            showCreateBackupModal();
        }
        
        async function restoreBackup(timestamp) {
            if (!confirm('⚠️ Restore this backup? Current data will be backed up automatically.')) return;
            
            const status = document.getElementById('backupStatus');
            status.className = 'status-message status-info';
            status.innerHTML = '<span class="loading"></span> Restoring...';
            status.style.display = 'block';
            
            const res = await fetch(`/admin/api/backup/restore/${timestamp}`, {method: 'POST'});
            const data = await res.json();
            
            if (data.success) {
                status.className = 'status-message status-success';
                status.innerHTML = '✅ Restored successfully!';
                loadStats();
                loadKeys();
                loadBackups();
                setTimeout(() => status.style.display = 'none', 3000);
            } else {
                status.className = 'status-message status-error';
                status.innerHTML = '❌ ' + (data.message || 'Restore failed');
            }
        }
        
        async function deleteBackup(timestamp) {
            if (!confirm('Delete this backup?')) return;
            
            const res = await fetch(`/admin/api/backup/delete/${timestamp}`, {method: 'DELETE'});
            const data = await res.json();
            
            if (data.success) {
                loadBackups();
            }
        }
        
        function confirmDeleteAllBackups() {
            currentModal = 'deleteAllBackupsModal';
            document.getElementById('deleteAllBackupsModal').style.display = 'flex';
        }
        
        async function deleteAllBackups() {
            closeModal();
            
            const res = await fetch('/admin/api/backup/delete-all', {method: 'POST'});
            const data = await res.json();
            
            if (data.success) {
                alert(`✅ Deleted ${data.deleted_count} backups`);
                loadBackups();
            }
        }
        
        function downloadBackup(timestamp) {
            window.location.href = `/admin/api/backup/download/${timestamp}`;
        }
        
        function closeModal() {
            document.querySelectorAll('.modal-overlay').forEach(m => m.style.display = 'none');
        }
        
        function refreshAll() {
            loadStats();
            loadKeys();
            loadBackups();
        }
        
        // Initial load
        loadStats();
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
    
    # Create initial backup on first run
    if len(get_backup_list()) == 0:
        create_backup("Initial system backup")

    # Start auto-save thread
    def auto_save_worker():
        while True:
            time.sleep(30)
            if _data_modified:
                save_data()
    
    threading.Thread(target=auto_save_worker, daemon=True).start()

    port = int(os.environ.get('PORT', 10000))
    print(f"\n🚀 ATLAS ULTIMATE v4.0 starting on port {port}")
    print(f"📊 Admin panel: http://localhost:{port}/admin")
    print(f"🔑 Default admin: {ADMIN_USER} / {'*' * len(ADMIN_PASS)}")
    print(f"\n⚡ FEATURES:")
    print(f"   ✓ Individual key tabs with detailed views")
    print(f"   ✓ HWID reset for each key")
    print(f"   ✓ Add time to existing keys")
    print(f"   ✓ Universal time display (UTC)")
    print(f"   ✓ Key status: used/expired/active")
    print(f"   ✓ Cloud backups stored on server")
    print(f"   ✓ Auto-backup rotation (keep last 100)")
    print(f"\nPress Ctrl+C to stop (data will be saved)\n")

    try:
        app.run(host='0.0.0.0', port=port, threaded=True)
    except KeyboardInterrupt:
        emergency_save()