#!/usr/bin/env python3
"""
ATLAS R6-SCRIPT - INDESTRUCTIBLE CLOUD SERVER
Features:
- Multi-layer backup (Redis, JSON, timestamped backups)
- Auto-save daemon (saves every 5 minutes)
- Recovery on startup from any available source
- Emergency recovery endpoints
- Connection retry logic for Redis
- 50 backup rotation
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
import redis

# ============================================================================
# INIT
# ============================================================================
app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', secrets.token_hex(32))
CORS(app)

# ============================================================================
# REDIS MANAGER (LAYER 1: CLOUD BACKUP)
# ============================================================================
class RedisManager:
    def __init__(self):
        self.client = None
        self.connect()
    
    def connect(self):
        """Establish Redis connection with retry logic"""
        try:
            self.client = redis.Redis(
                host=os.environ.get('UPSTASH_REDIS_HOST', ''),
                port=int(os.environ.get('UPSTASH_REDIS_PORT', 6379)),
                password=os.environ.get('UPSTASH_REDIS_PASSWORD', ''),
                ssl=True,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5,
                retry_on_timeout=True
            )
            # Test connection
            self.client.ping()
            print("✅ Redis connected successfully")
        except Exception as e:
            print(f"⚠️ Redis connection failed: {e}")
            self.client = None
    
    def get_keys(self):
        """Retrieve keys from Redis"""
        if not self.client:
            return None
        try:
            data = self.client.get('atlas_keys')
            return json.loads(data) if data else None
        except Exception as e:
            print(f"⚠️ Redis read failed: {e}")
            return None
    
    def save_keys(self, keys_dict):
        """Save keys to Redis with hourly backup"""
        if not self.client:
            return False
        try:
            # Save current state
            self.client.set('atlas_keys', json.dumps(keys_dict))
            # Save hourly backup (30 day retention)
            self.client.setex(
                f'atlas_keys_backup_{datetime.now().strftime("%Y%m%d_%H")}',
                2592000,  # 30 days
                json.dumps(keys_dict)
            )
            return True
        except Exception as e:
            print(f"⚠️ Redis save failed: {e}")
            return False

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
        
        # 4. Save to Redis
        redis_mgr.save_keys(KEYS)
        
        # 5. Also save profiles
        with open(PROFILES_FILE, 'w') as f:
            json.dump(USER_PROFILES, f, indent=2)
        
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
    
    # TRY SOURCE 1: REDIS (BEST)
    print("\n1️⃣ Checking Redis...")
    redis_keys = redis_mgr.get_keys()
    if redis_keys:
        KEYS = redis_keys
        print(f"✅ SUCCESS! Loaded {len(KEYS)} keys from Redis")
        # Also save locally
        with open(KEY_FILE, 'w') as f:
            json.dump(KEYS, f, indent=2)
        
        # Load profiles from Redis too
        redis_profiles = redis_mgr.client.get('atlas_profiles') if redis_mgr.client else None
        if redis_profiles:
            USER_PROFILES = json.loads(redis_profiles)
            print(f"✅ Loaded {len(USER_PROFILES)} profiles from Redis")
        return True
    
    # TRY SOURCE 2: MAIN JSON FILE
    print("\n2️⃣ Checking local keys.json...")
    if os.path.exists(KEY_FILE):
        try:
            with open(KEY_FILE, 'r') as f:
                KEYS = json.load(f)
            print(f"✅ SUCCESS! Loaded {len(KEYS)} keys from keys.json")
            
            # Try to restore Redis
            redis_mgr.save_keys(KEYS)
            
            # Load profiles
            if os.path.exists(PROFILES_FILE):
                with open(PROFILES_FILE, 'r') as f:
                    USER_PROFILES = json.load(f)
                print(f"✅ Loaded {len(USER_PROFILES)} profiles from profiles.json")
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
            
            # Restore Redis
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
        'backups_available': len(glob.glob('keys_backup_*.json'))
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
    
    # Save profiles to Redis too
    try:
        if redis_mgr.client:
            redis_mgr.client.set('atlas_profiles', json.dumps(USER_PROFILES))
    except:
        pass
    
    save_keys_comprehensive()  # This saves profiles too
    return jsonify({'success': True})

# ============================================================================
# ADMIN ROUTES (WITH ADDED RECOVERY OPTIONS)
# ============================================================================

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

# [REST OF YOUR EXISTING ADMIN ROUTES REMAIN THE SAME]
# (admin login, generate keys, delete, reset-expired, etc.)
# Just replace any save_keys() calls with save_keys_comprehensive()

# ============================================================================
# RUN
# ============================================================================
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    print("\n" + "="*50)
    print("🚀 ATLAS INDESTRUCTIBLE SERVER")
    print("="*50)
    print(f"🔑 Keys loaded: {len(KEYS)}")
    print(f"👤 Profiles loaded: {len(USER_PROFILES)}")
    print(f"💾 Backups available: {len(glob.glob('keys_backup_*.json'))}")
    print(f"🔄 Auto-save: Every 5 minutes")
    print(f"☁️ Redis: {'Connected' if redis_mgr.client else 'Disconnected'}")
    print(f"📊 Admin: https://atlas-r6-keys.onrender.com/admin")
    print("="*50 + "\n")
    app.run(host='0.0.0.0', port=port)