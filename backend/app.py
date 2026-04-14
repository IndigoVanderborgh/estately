from flask import Flask, jsonify, request
from flask_cors import CORS
from supabase import create_client
from dotenv import load_dotenv
import os

load_dotenv('../.env')

app = Flask(__name__)
CORS(app)

supabase = create_client(
    os.getenv('SUPABASE_URL'),
    os.getenv('SUPABASE_KEY')
)

def get_user_id():
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    if not token:
        return None
    try:
        user = supabase.auth.get_user(token)
        return user.user.id
    except:
        return None

# ── Test route ─────────────────────────────────────────────────
@app.route('/api/health')
def health():
    return jsonify({'status': 'ok', 'message': 'Estately backend is running!'})

# ── Get all apartments ─────────────────────────────────────────
@app.route('/api/apartments')
def get_apartments():
    user_id = get_user_id()
    if not user_id:
        return jsonify({'error': 'Unauthorized'}), 401
    response = supabase.table('apartments').select('*').eq('user_id', user_id).execute()
    return jsonify(response.data)

# ── Get single apartment ───────────────────────────────────────
@app.route('/api/apartments/<int:id>')
def get_apartment(id):
    user_id = get_user_id()
    if not user_id:
        return jsonify({'error': 'Unauthorized'}), 401
    response = supabase.table('apartments').select('*').eq('id', id).eq('user_id', user_id).execute()
    return jsonify(response.data[0] if response.data else {})

# ── Add apartment ──────────────────────────────────────────────
@app.route('/api/apartments', methods=['POST'])
def add_apartment():
    user_id = get_user_id()
    if not user_id:
        return jsonify({'error': 'Unauthorized'}), 401
    data = request.json
    data['user_id'] = user_id
    response = supabase.table('apartments').insert(data).execute()
    return jsonify(response.data)

# ── Update apartment ───────────────────────────────────────────
@app.route('/api/apartments/<int:id>', methods=['PUT'])
def update_apartment(id):
    user_id = get_user_id()
    if not user_id:
        return jsonify({'error': 'Unauthorized'}), 401
    data = request.json
    response = supabase.table('apartments').update(data).eq('id', id).eq('user_id', user_id).execute()
    return jsonify(response.data)

# ── Delete apartment ───────────────────────────────────────────
@app.route('/api/apartments/<int:id>', methods=['DELETE'])
def delete_apartment(id):
    user_id = get_user_id()
    if not user_id:
        return jsonify({'error': 'Unauthorized'}), 401
    response = supabase.table('apartments').delete().eq('id', id).eq('user_id', user_id).execute()
    return jsonify({'success': True})

# ── Login ──────────────────────────────────────────────────────
@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    email = data.get('email')
    password = data.get('password')
    try:
        response = supabase.auth.sign_in_with_password({
            "email": email,
            "password": password
        })
        return jsonify({'token': response.session.access_token})
    except Exception as e:
        return jsonify({'error': str(e)}), 401

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=False, host='0.0.0.0', port=port)