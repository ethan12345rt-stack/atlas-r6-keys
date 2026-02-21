from flask import Flask, request, jsonify
from flask_cors import CORS
from datetime import datetime
import os

app = Flask(__name__)
CORS(app)

# Your 75 keys
KEYS = {
    "7D21-9A4F-8E67-3B2C-1D5F-9A8E": {"expiry": "2026-12-31T23:59:59", "used": False, "hwid": None},
    "30D1-8C4F-2E7B-9A3D-5F6C-1B9E": {"expiry": "2026-12-31T23:59:59", "used": False, "hwid": None},
    "365D-1A2B-3C4D-5E6F-7A8B-9C0D": {"expiry": "2027-12-31T23:59:59", "used": False, "hwid": None}
}

@app.route('/')
def home():
    return "ATLAS Key Server Online!"

@app.route('/api/validate', methods=['POST'])
def validate():
    data = request.json
    key = data.get('key', '').upper()
    hwid = data.get('hwid', '')
    
    if key not in KEYS:
        return jsonify({'valid': False, 'message': 'Invalid key'})
    
    key_data = KEYS[key]
    
    # Check expiry
    expiry = datetime.fromisoformat(key_data['expiry'])
    if expiry < datetime.now():
        return jsonify({'valid': False, 'message': 'Key expired'})
    
    # Check if used
    if key_data['used'] and key_data['hwid'] != hwid:
        return jsonify({'valid': False, 'message': 'Key already in use'})
    
    # Activate if new
    if not key_data['used']:
        key_data['used'] = True
        key_data['hwid'] = hwid
    
    return jsonify({
        'valid': True,
        'message': 'Key valid',
        'expiry': key_data['expiry']
    })

@app.route('/api/status')
def status():
    return jsonify({'status': 'online'})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)