#!/usr/bin/env python3
"""
ATLAS R6-SCRIPT - INDESTRUCTIBLE CLOUD SERVER
Features:
- Multi-layer backup (Redis if available, JSON, timestamped backups)
- Auto-save daemon (saves every 5 minutes)
- Recovery on startup from any available source
- Emergency recovery endpoints
- Connection retry logic for Redis
- 50 backup rotation
- SAFE MODE: Runs perfectly even without Redis credentials
"""

import os
import json
import secrets
import hashlib
import threading
import time
import shutil
import glob
from datetime import datetime, timedelta
from flask import Flask, render_template, render_template_string, jsonify, request, session, redirect, url_for
from flask_cors import CORS
from functools import wraps

# Only import redis if available (prevents crash if not installed)
try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    print("⚠️ Redis module not installed - running in local-only mode")

# ============================================================================
# INIT
# ============================================================================
app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', secrets.token_hex(32))
CORS(app)

# ============================================================================
# REDIS MANAGER WITH SAFE FALLBACK (NO CRASH IF MISSING)
# ============================================================================
class RedisManager:
    def __init__(self):
        self.client = None
        self.enabled = False
        if REDIS_AVAILABLE:
            self.connect()
        else:
            print("⚠️ Redis not available - running in local-only mode")
    
    def connect(self):
        """Establish Redis connection only if credentials exist"""
        host = os.environ.get('UPSTASH_REDIS_HOST')
        port = os.environ.get('UPSTASH_REDIS_PORT')
        password = os.environ.get('UPSTASH_REDIS_PASSWORD')
        
        # Only try Redis if ALL credentials exist
        if not all([host, port, password]):
            print("⚠️ Redis credentials missing - running in local-only mode")
            self.enabled = False
            return
        
        try:
            self.client = redis.Redis(
                host=host,
                port=int(port) if port else 6379,
                password=password,
                ssl=True,
                decode_responses=True,
                socket_connect_timeout=3,
                socket_timeout=3,
                retry_on_timeout=True
            )
            # Test connection
            self.client.ping()
            self.enabled = True
            print("✅ Redis connected successfully")
        except Exception as e:
            print(f"⚠️ Redis connection failed: {e}")
            print("⚠️ Running in local-only mode (keys saved to disk only)")
            self.client = None
            self.enabled = False
    
    def get_keys(self):
        """Retrieve keys from Redis (if available)"""
        if not self.enabled or not self.client:
            return None
        try:
            data = self.client.get('atlas_keys')
            return json.loads(data) if data else None
        except Exception as e:
            print(f"⚠️ Redis read failed: {e}")
            return None
    
    def save_keys(self, keys_dict):
        """Save keys to Redis (if available)"""
        if not self.enabled or not self.client:
            return False
        try:
            self.client.set('atlas_keys', json.dumps(keys_dict))
            # Save hourly backup (30 day retention) - only if Redis is working
            try:
                self.client.setex(
                    f'atlas_keys_backup_{datetime.now().strftime("%Y%m%d_%H")}',
                    2592000,  # 30 days
                    json.dumps(keys_dict)
                )
            except:
                pass  # Non-critical if hourly backup fails
            return True
        except Exception as e:
            print(f"⚠️ Redis save failed: {e}")
            return False
    
    def get_profiles(self):
        """Retrieve profiles from Redis"""
        if not self.enabled or not self.client:
            return None
        try:
            data = self.client.get('atlas_profiles')
            return json.loads(data) if data else None
        except:
            return None
    
    def save_profiles(self, profiles_dict):
        """Save profiles to Redis"""
        if not self.enabled or not self.client:
            return False
        try:
            self.client.set('atlas_profiles', json.dumps(profiles_dict))
            return True
        except:
            return False

# Initialize Redis manager (won't crash if Redis isn't available)
redis_mgr = RedisManager()

# ============================================================================
# KEY DATABASE WITH MULTI-LAYER BACKUP
# ============================================================================
KEYS = {}
KEY_FILE = 'keys.json'
MAX_BACKUPS = 50  # Keep last 50 backups

# ============================================================================
# PROFILES DATABASE
# ============================================================================
USER_PROFILES = {}
PROFILES_FILE = 'profiles.json'

# ============================================================================
# AUTO-SAVE DAEMON (LAYER 2: AUTOMATIC BACKUPS)
# ============================================================================
def auto_save_daemon():
    """Background thread that saves keys every 5 minutes"""
    while True:
        time.sleep(300)  # 5 minutes
        if KEYS:  # Only save if we have keys
            try:
                save_keys_comprehensive()
                print(f"💾 Auto-saved {len(KEYS)} keys at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            except Exception as e:
                print(f"⚠️ Auto-save failed: {e}")

# ============================================================================
# COMPREHENSIVE SAVE FUNCTION (LAYER 3: MULTIPLE BACKUPS)
# ============================================================================
def save_keys_comprehensive():
    """Save keys with multiple backup strategies"""
    try:
        # 1. Primary JSON save
        with open(KEY_FILE, 'w') as f:
            json.dump(KEYS, f, indent=2)
        
        # 2. Timestamped backup
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file = f'keys_backup_{timestamp}.json'
        shutil.copy2(KEY_FILE, backup_file)
        
        # 3. Clean old backups (keep only MAX_BACKUPS)
        backups = sorted(glob.glob('keys_backup_*.json'))
        while len(backups) > MAX_BACKUPS:
            os.remove(backups.pop(0))
        
        # 4. Save to Redis (if available)
        redis_mgr.save_keys(KEYS)
        
        # 5. Also save profiles
        with open(PROFILES_FILE, 'w') as f:
            json.dump(USER_PROFILES, f, indent=2)
        
        # 6. Save profiles to Redis
        redis_mgr.save_profiles(USER_PROFILES)
        
        return True
    except Exception as e:
        print(f"❌ Comprehensive save failed: {e}")
        return False

# ============================================================================
# COMPREHENSIVE LOAD FUNCTION (LAYER 4: RECOVERY FROM ANY SOURCE)
# ============================================================================
def load_keys_comprehensive():
    """Load keys from multiple sources with fallback"""
    global KEYS, USER_PROFILES
    
    print("\n" + "="*50)
    print("🔄 ATTEMPTING KEY RECOVERY...")
    print("="*50)
    
    # TRY SOURCE 1: REDIS (BEST, IF AVAILABLE)
    print("\n1️⃣ Checking Redis...")
    redis_keys = redis_mgr.get_keys()
    if redis_keys:
        KEYS = redis_keys
        print(f"✅ SUCCESS! Loaded {len(KEYS)} keys from Redis")
        # Also save locally
        with open(KEY_FILE, 'w') as f:
            json.dump(KEYS, f, indent=2)
        
        # Load profiles from Redis too
        redis_profiles = redis_mgr.get_profiles()
        if redis_profiles:
            USER_PROFILES = redis_profiles
            print(f"✅ Loaded {len(USER_PROFILES)} profiles from Redis")
            with open(PROFILES_FILE, 'w') as f:
                json.dump(USER_PROFILES, f, indent=2)
        return True
    
    # TRY SOURCE 2: MAIN JSON FILE
    print("\n2️⃣ Checking local keys.json...")
    if os.path.exists(KEY_FILE):
        try:
            with open(KEY_FILE, 'r') as f:
                KEYS = json.load(f)
            print(f"✅ SUCCESS! Loaded {len(KEYS)} keys from keys.json")
            
            # Try to restore Redis (if available)
            redis_mgr.save_keys(KEYS)
            
            # Load profiles
            if os.path.exists(PROFILES_FILE):
                with open(PROFILES_FILE, 'r') as f:
                    USER_PROFILES = json.load(f)
                print(f"✅ Loaded {len(USER_PROFILES)} profiles from profiles.json")
                redis_mgr.save_profiles(USER_PROFILES)
            return True
        except Exception as e:
            print(f"⚠️ Failed to load keys.json: {e}")
    
    # TRY SOURCE 3: RECENT BACKUPS
    print("\n3️⃣ Checking backup files...")
    backups = sorted(glob.glob('keys_backup_*.json'))
    if backups:
        latest_backup = backups[-1]  # Most recent
        try:
            with open(latest_backup, 'r') as f:
                KEYS = json.load(f)
            print(f"✅ SUCCESS! Recovered {len(KEYS)} keys from: {latest_backup}")
            
            # Restore main file
            with open(KEY_FILE, 'w') as f:
                json.dump(KEYS, f, indent=2)
            
            # Restore Redis (if available)
            redis_mgr.save_keys(KEYS)
            return True
        except Exception as e:
            print(f"⚠️ Failed to load backup: {e}")
    
    # TRY SOURCE 4: ENVIRONMENT VARIABLE (EMERGENCY)
    print("\n4️⃣ Checking environment variables...")
    env_keys = os.environ.get('INITIAL_KEYS_JSON')
    if env_keys:
        try:
            KEYS = json.loads(env_keys)
            print(f"✅ SUCCESS! Loaded {len(KEYS)} keys from environment")
            save_keys_comprehensive()
            return True
        except:
            pass
    
    # EVERYTHING FAILED - START FRESH
    print("\n⚠️ NO KEYS FOUND! Starting with empty database.")
    KEYS = {}
    USER_PROFILES = {}
    return False

# ============================================================================
# START AUTO-SAVE DAEMON
# ============================================================================
auto_save_thread = threading.Thread(target=auto_save_daemon, daemon=True)
auto_save_thread.start()
print("✅ Auto-save daemon started (saves every 5 minutes)")

# ============================================================================
# LOAD DATA ON STARTUP
# ============================================================================
load_keys_comprehensive()

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
        'keys_loaded': len(KEYS),
        'backups_available': len(glob.glob('keys_backup_*.json')),
        'redis_enabled': redis_mgr.enabled
    })

@app.route('/api/validate', methods=['POST'])
def validate_key():
    data = request.json
    key = data.get('key', '').strip().upper()
    hwid = data.get('hwid', '')
    
    # Quick Redis sync before validation (get latest from other instances)
    redis_keys = redis_mgr.get_keys()
    if redis_keys:
        KEYS.update(redis_keys)
    
    if key not in KEYS:
        return jsonify({'valid': False, 'message': 'Invalid key'})
    
    key_data = KEYS[key]
    
    # Check if key is already used and activated
    if key_data.get('used', False):
        # Key is used - check if it's expired
        if 'expiry' in key_data:
            expiry = datetime.fromisoformat(key_data['expiry'])
            if expiry < datetime.now():
                return jsonify({'valid': False, 'message': 'Key expired'})
        
        # Check if it's bound to a different HWID
        if key_data.get('hwid') and key_data['hwid'] != hwid:
            return jsonify({'valid': False, 'message': 'Key already in use on another PC'})
        
        return jsonify({
            'valid': True,
            'message': 'Key valid',
            'expiry': key_data['expiry']
        })
    
    # Key is unused - FIRST ACTIVATION
    created = datetime.fromisoformat(key_data['created'])
    duration = key_data.get('duration', '7days')
    
    if duration == '2min':
        expiry = datetime.now() + timedelta(minutes=2)
    elif duration == '1day':
        expiry = datetime.now() + timedelta(days=1)
    elif duration == '7days':
        expiry = datetime.now() + timedelta(days=7)
    elif duration == '30days':
        expiry = datetime.now() + timedelta(days=30)
    elif duration == '365days':
        expiry = datetime.now() + timedelta(days=365)
    else:
        expiry = datetime.now() + timedelta(days=7)
    
    key_data['used'] = True
    key_data['hwid'] = hwid
    key_data['activated_date'] = datetime.now().isoformat()
    key_data['expiry'] = expiry.isoformat()
    key_data['activation_count'] = key_data.get('activation_count', 0) + 1
    
    save_keys_comprehensive()
    
    print(f"🔑 Key {key} activated - expires {expiry.isoformat()}")
    
    return jsonify({
        'valid': True,
        'message': 'Key activated successfully!',
        'expiry': key_data['expiry']
    })

# ============================================================================
# PROFILE API WITH BACKUP
# ============================================================================

@app.route('/api/profiles/<hwid>', methods=['GET'])
def get_profiles(hwid):
    if hwid in USER_PROFILES:
        return jsonify(USER_PROFILES[hwid])
    return jsonify({})

@app.route('/api/profiles/<hwid>/save', methods=['POST'])
def save_profile(hwid):
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
    
    save_keys_comprehensive()  # This saves profiles too
    return jsonify({'success': True})

@app.route('/api/profiles/<hwid>/delete', methods=['POST'])
def delete_profile(hwid):
    data = request.json
    name = data.get('name')
    
    if hwid in USER_PROFILES and name in USER_PROFILES[hwid]:
        del USER_PROFILES[hwid][name]
        save_keys_comprehensive()
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

@app.route('/admin/api/backups', methods=['GET'])
@login_required
def list_backups():
    """List all available backup files"""
    backups = sorted(glob.glob('keys_backup_*.json'))
    backup_info = []
    for backup in backups:
        try:
            with open(backup, 'r') as f:
                data = json.load(f)
            backup_info.append({
                'filename': backup,
                'date': backup.replace('keys_backup_', '').replace('.json', ''),
                'key_count': len(data),
                'size': os.path.getsize(backup)
            })
        except:
            pass
    return jsonify(backups=backup_info)

@app.route('/admin/api/recover', methods=['POST'])
@login_required
def admin_recover():
    """Emergency recovery from specific backup"""
    global KEYS
    data = request.json
    backup_file = data.get('backup_file')
    
    if backup_file and os.path.exists(backup_file):
        try:
            with open(backup_file, 'r') as f:
                KEYS = json.load(f)
            save_keys_comprehensive()
            return jsonify({
                'success': True,
                'message': f'Recovered {len(KEYS)} keys from {backup_file}'
            })
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 500
    
    # If no file specified, try Redis
    redis_keys = redis_mgr.get_keys()
    if redis_keys:
        KEYS = redis_keys
        save_keys_comprehensive()
        return jsonify({
            'success': True,
            'message': f'Recovered {len(KEYS)} keys from Redis'
        })
    
    return jsonify({'success': False, 'error': 'No recovery source found'}), 404

@app.route('/admin/api/generate', methods=['POST'])
@login_required
def admin_generate_keys():
    data = request.json
    count = int(data.get('count', 5))
    duration = data.get('duration', '7days')
    
    new_keys = []
    created_time = datetime.now().isoformat()
    
    for i in range(count):
        key = '-'.join([secrets.token_hex(2).upper() for _ in range(6)])
        KEYS[key] = {
            'used': False,
            'hwid': None,
            'created': created_time,
            'duration': duration,
            'expiry': None
        }
        new_keys.append(key)
    
    save_keys_comprehensive()
    return jsonify({'success': True, 'keys': new_keys})

@app.route('/admin/api/delete/<key>', methods=['DELETE'])
@login_required
def admin_delete_key(key):
    if key in KEYS:
        del KEYS[key]
        save_keys_comprehensive()
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
    save_keys_comprehensive()
    
    return jsonify({
        'success': True,
        'message': 'All {} keys have been deleted'.format(count)
    })

@app.route('/admin/api/reset-expired', methods=['POST'])
@login_required
def admin_reset_expired():
    """Delete all expired keys"""
    now = datetime.now()
    expired = []
    
    for key, data in list(KEYS.items()):
        if data.get('expiry'):
            try:
                expiry = datetime.fromisoformat(data['expiry'])
                if expiry < now:
                    expired.append(key)
                    del KEYS[key]
            except:
                pass
    
    save_keys_comprehensive()
    
    return jsonify({
        'success': True,
        'message': 'Deleted {} expired keys'.format(len(expired)),
        'count': len(expired)
    })

@app.route('/admin/api/stats', methods=['GET'])
@login_required
def admin_stats():
    total = len(KEYS)
    used = sum(1 for k in KEYS if KEYS[k].get('used', False))
    
    now = datetime.now()
    expired = 0
    for key, data in KEYS.items():
        if data.get('expiry'):
            try:
                expiry = datetime.fromisoformat(data['expiry'])
                if expiry < now:
                    expired += 1
            except:
                pass
    
    duration_counts = {}
    for key, data in KEYS.items():
        dur = data.get('duration', 'unknown')
        duration_counts[dur] = duration_counts.get(dur, 0) + 1
    
    return jsonify({
        'total': total,
        'used': used,
        'available': total - used,
        'expired': expired,
        'duration_counts': duration_counts,
        'redis_enabled': redis_mgr.enabled,
        'backups': len(glob.glob('keys_backup_*.json'))
    })

# ============================================================================
# ADMIN HTML - UPDATED WITH BACKUP INFO
# ============================================================================

ADMIN_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>ATLAS Admin - INDESTRUCTIBLE</title>
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
        .info-box {
            background: rgba(255,255,0,0.1);
            border: 1px solid #ffff00;
            border-radius: 8px;
            padding: 15px;
            margin-bottom: 20px;
            color: #ffff00;
        }
        .stats { 
            display: grid;
            grid-template-columns: repeat(6,1fr);
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
        button.success {
            background: #00ff00;
            color: #000;
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
        .key-item.unused {
            border-left: 4px solid #00ff00;
            background: rgba(0,255,0,0.05);
        }
        .key-item.used {
            border-left: 4px solid #ffaa00;
            background: rgba(255,170,0,0.05);
        }
        .key-item.expired {
            border-left: 4px solid #ff0000;
            background: rgba(255,0,0,0.05);
            opacity: 0.7;
        }
        .badge {
            display: inline-block;
            padding: 3px 8px;
            border-radius: 4px;
            font-size: 11px;
            font-weight: bold;
            margin-left: 10px;
        }
        .badge.unused { background: #00ff00; color: #000; }
        .badge.used { background: #ffaa00; color: #000; }
        .badge.expired { background: #ff0000; color: #fff; }
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
            flex-wrap: wrap;
        }
        .backup-list {
            max-height: 200px;
            overflow-y: auto;
            background: #1a2a30;
            padding: 10px;
            border-radius: 4px;
        }
        .backup-item {
            display: flex;
            justify-content: space-between;
            padding: 8px;
            border-bottom: 1px solid #00ffff20;
            color: #a0b0c0;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🔥 ATLAS INDESTRUCTIBLE KEY ADMIN</h1>
            <div>
                <span style="color:#00ffff; margin-right:15px;" id="redisStatus">🔄 Redis: Checking...</span>
                <a href="/logout" class="logout-btn">Logout</a>
            </div>
        </div>
        
        <div class="info-box">
            ⚡ <strong>INDESTRUCTIBLE MODE ACTIVE:</strong> Keys auto-save every 5 minutes + 50 backups + Redis cloud backup (if configured)
        </div>
        
        <div class="stats" id="stats">
            <div class="stat-card"><div class="stat-value" id="total">0</div><div>Total Keys</div></div>
            <div class="stat-card"><div class="stat-value" id="used">0</div><div>Used Keys</div></div>
            <div class="stat-card"><div class="stat-value" id="available">0</div><div>Available</div></div>
            <div class="stat-card"><div class="stat-value" id="expired">0</div><div>Expired</div></div>
            <div class="stat-card"><div class="stat-value" id="testKeys">0</div><div>Test Keys</div></div>
            <div class="stat-card"><div class="stat-value" id="backups">0</div><div>Backups</div></div>
        </div>
        
        <div class="panel">
            <h2>🔑 Generate Keys</h2>
            <input type="number" id="count" value="5" min="1" max="100">
            <select id="duration">
                <option value="2min">⏱️ 2 Minutes (TEST KEY)</option>
                <option value="1day">📅 1 Day</option>
                <option value="7days">📆 7 Days</option>
                <option value="30days">🗓️ 30 Days</option>
                <option value="365days">📅 1 Year</option>
            </select>
            <button onclick="generateKeys()">Generate Keys</button>
            <div id="generated" class="generated" style="display:none;"></div>
        </div>
        
        <div class="panel">
            <h2>🛡️ Emergency Recovery</h2>
            <div class="flex-row">
                <button class="success" onclick="showBackups()">📋 Show Available Backups</button>
                <button class="warning" onclick="recoverFromRedis()">☁️ Recover from Redis</button>
                <button class="warning" onclick="resetExpired()">🗑️ Delete Expired Keys</button>
                <button class="danger" onclick="resetAllKeys()">💀 DELETE ALL KEYS</button>
            </div>
            <div id="backupList" class="backup-list" style="display:none; margin-top:15px;"></div>
        </div>
        
        <div class="panel">
            <h2>📋 All Keys <span style="color:#a0b0c0; font-size:14px;" id="keyCount"></span></h2>
            <div class="key-list" id="keyList"></div>
        </div>
    </div>
    
    <script>
        let backupsData = [];
        
        async function loadStats() {
            try {
                const res = await fetch('/admin/api/stats');
                const data = await res.json();
                document.getElementById('total').textContent = data.total;
                document.getElementById('used').textContent = data.used;
                document.getElementById('available').textContent = data.available;
                document.getElementById('expired').textContent = data.expired;
                document.getElementById('backups').textContent = data.backups || 0;
                
                // Redis status
                const redisEl = document.getElementById('redisStatus');
                if (data.redis_enabled) {
                    redisEl.innerHTML = '✅ Redis: Connected';
                    redisEl.style.color = '#00ff00';
                } else {
                    redisEl.innerHTML = '⚠️ Redis: Local Only';
                    redisEl.style.color = '#ffaa00';
                }
                
                const testCount = data.duration_counts ? (data.duration_counts['2min'] || 0) : 0;
                document.getElementById('testKeys').textContent = testCount;
            } catch (e) {
                console.error('Failed to load stats', e);
            }
        }
        
        async function showBackups() {
            try {
                const res = await fetch('/admin/api/backups');
                const data = await res.json();
                backupsData = data.backups || [];
                
                const listDiv = document.getElementById('backupList');
                if (backupsData.length === 0) {
                    listDiv.innerHTML = '<div style="color:#ffaa00;">No backups found</div>';
                } else {
                    let html = '<h3 style="color:#00ffff;">Available Backups:</h3>';
                    backupsData.forEach(backup => {
                        html += `
                            <div class="backup-item">
                                <span>📁 ${backup.filename}</span>
                                <span>${backup.key_count} keys | ${(backup.size/1024).toFixed(2)} KB</span>
                                <button onclick="recoverFromBackup('${backup.filename}')" style="padding:2px 10px;">Recover</button>
                            </div>
                        `;
                    });
                    listDiv.innerHTML = html;
                }
                listDiv.style.display = 'block';
            } catch (e) {
                console.error('Failed to load backups', e);
            }
        }
        
        async function recoverFromBackup(filename) {
            if (confirm(`Recover keys from ${filename}? Current keys will be replaced.`)) {
                try {
                    const res = await fetch('/admin/api/recover', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({backup_file: filename})
                    });
                    const data = await res.json();
                    if (data.success) {
                        alert('✅ ' + data.message);
                        loadKeys();
                        loadStats();
                    } else {
                        alert('❌ ' + data.error);
                    }
                } catch (e) {
                    alert('Recovery failed');
                }
            }
        }
        
        async function recoverFromRedis() {
            if (confirm('Recover keys from Redis backup?')) {
                try {
                    const res = await fetch('/admin/api/recover', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({})
                    });
                    const data = await res.json();
                    if (data.success) {
                        alert('✅ ' + data.message);
                        loadKeys();
                        loadStats();
                    } else {
                        alert('❌ ' + data.error);
                    }
                } catch (e) {
                    alert('Recovery failed');
                }
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
                    
                    let status = 'UNUSED';
                    let statusClass = 'unused';
                    let expiryInfo = '';
                    
                    const now = new Date();
                    
                    if (data.used) {
                        if (data.expiry) {
                            const expiryDate = new Date(data.expiry);
                            if (expiryDate < now) {
                                status = 'EXPIRED';
                                statusClass = 'expired';
                                expiryInfo = ' | Expired: ' + expiryDate.toLocaleString();
                            } else {
                                status = 'ACTIVE';
                                statusClass = 'used';
                                const daysLeft = Math.round((expiryDate - now) / (1000 * 60 * 60 * 24));
                                const hoursLeft = Math.round((expiryDate - now) / (1000 * 60 * 60));
                                if (daysLeft > 0) {
                                    expiryInfo = ' | ' + daysLeft + ' days left';
                                } else {
                                    expiryInfo = ' | ' + hoursLeft + ' hours left';
                                }
                            }
                        } else {
                            status = 'ACTIVE';
                            statusClass = 'used';
                        }
                    }
                    
                    div.className = 'key-item ' + statusClass;
                    
                    let badge = '';
                    if (data.duration === '2min') badge = '<span class="badge test">2min</span>';
                    else if (data.duration === '1day') badge = '<span class="badge day">1d</span>';
                    else if (data.duration === '7days') badge = '<span class="badge week">7d</span>';
                    else if (data.duration === '30days') badge = '<span class="badge month">30d</span>';
                    else if (data.duration === '365days') badge = '<span class="badge year">365d</span>';
                    
                    const createdDate = new Date(data.created).toLocaleDateString();
                    
                    div.innerHTML = `
                        <div>
                            <div style="color:#00ffff; font-family:monospace; font-size:16px;">
                                ${key} ${badge}
                            </div>
                            <div style="margin-top:5px;">
                                <span style="color:${statusClass === 'unused' ? '#00ff00' : (statusClass === 'expired' ? '#ff0000' : '#ffaa00')};">${status}</span>
                                <span style="color:#a0b0c0; margin-left:10px;">Created: ${createdDate}</span>
                                ${expiryInfo ? `<span style="color:#ffaa00;">${expiryInfo}</span>` : ''}
                            </div>
                            ${data.hwid ? `<div style="color:#ffaa00; font-size:11px;">HWID: ${data.hwid.substring(0,16)}...</div>` : ''}
                            ${data.activated_date ? `<div style="color:#a0b0c0; font-size:11px;">Activated: ${new Date(data.activated_date).toLocaleDateString()}</div>` : ''}
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
                }, 15000);
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
                    alert('✅ Deleted ' + data.count + ' expired keys');
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
                        alert('✅ ' + data.message);
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
    print("\n" + "="*60)
    print("🚀 ATLAS INDESTRUCTIBLE SERVER V2.0")
    print("="*60)
    print(f"🔑 Keys loaded: {len(KEYS)}")
    print(f"👤 Profiles loaded: {len(USER_PROFILES)}")
    print(f"💾 Backups available: {len(glob.glob('keys_backup_*.json'))}")
    print(f"🔄 Auto-save: Every 5 minutes")
    print(f"☁️ Redis: {'CONNECTED' if redis_mgr.enabled else 'Local-Only Mode'}")
    if not redis_mgr.enabled:
        print("   ⚠️  Set UPSTASH_REDIS_HOST/PORT/PASSWORD to enable cloud backup")
    print(f"📊 Admin: https://atlas-r6-keys.onrender.com/admin")
    print("="*60 + "\n")
    app.run(host='0.0.0.0', port=port)