from flask import Flask, jsonify, request
from flask_cors import CORS
from supabase import create_client
from dotenv import load_dotenv
import os
# Testing boto3
import boto3
from botocore.client import Config

load_dotenv('../.env')

app = Flask(__name__)
CORS(app)

supabase = create_client(
    os.getenv('SUPABASE_URL'),
    os.getenv('SUPABASE_KEY')
)

# ── R2 client ──────────────────────────────────────────────────
r2 = boto3.client(
    's3',
    endpoint_url=os.getenv('R2_ENDPOINT'),
    aws_access_key_id=os.getenv('R2_ACCESS_KEY_ID'),
    aws_secret_access_key=os.getenv('R2_SECRET_ACCESS_KEY'),
    config=Config(signature_version='s3v4')
)
R2_BUCKET = os.getenv('R2_BUCKET')

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

# ── Upload lease document ───────────────────────────────────────
@app.route('/api/apartments/<int:id>/upload', methods=['POST'])
def upload_lease(id):
    user_id = get_user_id()
    if not user_id:
        return jsonify({'error': 'Unauthorized'}), 401
    file = request.files.get('file')
    if not file:
        return jsonify({'error': 'No file provided'}), 400

    from datetime import datetime
    import json

    file_path = f"{user_id}/{id}/{file.filename}"
    file_bytes = file.read()

    r2.put_object(
        Bucket=R2_BUCKET,
        Key=file_path,
        Body=file_bytes,
        ContentType=file.content_type
    )

    # Get current lease_docs array
    apt = supabase.table('apartments').select('lease_docs, tenant').eq('id', id).eq('user_id', user_id).execute()
    lease_docs = apt.data[0].get('lease_docs') or []
    tenant = apt.data[0].get('tenant', '—')

    # Append new document
    lease_docs.append({
        'filename': file.filename,
        'path': file_path,
        'uploaded': datetime.utcnow().strftime('%Y-%m-%d'),
        'tenant': tenant
    })

    supabase.table('apartments').update({
        'lease_doc': file_path,
        'lease_docs': lease_docs
    }).eq('id', id).eq('user_id', user_id).execute()

    return jsonify({'success': True, 'path': file_path, 'lease_docs': lease_docs})

# ── Delete lease document ───────────────────────────────────────
@app.route('/api/apartments/<int:id>/lease', methods=['DELETE'])
def delete_lease(id):
    user_id = get_user_id()
    if not user_id:
        return jsonify({'error': 'Unauthorized'}), 401

    file_path = request.json.get('path')
    if not file_path:
        return jsonify({'error': 'No path provided'}), 400

    # Delete from R2
    r2.delete_object(Bucket=R2_BUCKET, Key=file_path)

    # Update lease_docs array in Supabase
    apt = supabase.table('apartments').select('lease_docs').eq('id', id).eq('user_id', user_id).execute()
    lease_docs = apt.data[0].get('lease_docs') or []
    lease_docs = [d for d in lease_docs if d['path'] != file_path]

    supabase.table('apartments').update({
        'lease_docs': lease_docs
    }).eq('id', id).eq('user_id', user_id).execute()

    return jsonify({'success': True})

# ── Get lease download URL ──────────────────────────────────────
@app.route('/api/apartments/<int:id>/lease')
def get_lease(id):
    user_id = get_user_id()
    if not user_id:
        return jsonify({'error': 'Unauthorized'}), 401

    file_path = request.args.get('path')
    if not file_path:
        response = supabase.table('apartments').select('lease_doc').eq('id', id).eq('user_id', user_id).execute()
        if not response.data or not response.data[0].get('lease_doc'):
            return jsonify({'error': 'No document found'}), 404
        file_path = response.data[0]['lease_doc']

    url = r2.generate_presigned_url(
        'get_object',
        Params={'Bucket': R2_BUCKET, 'Key': file_path},
        ExpiresIn=300
    )
    return jsonify({'url': url})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=False, host='0.0.0.0', port=port)
