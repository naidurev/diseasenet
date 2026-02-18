from db import db
from db.models import Disease, Gene, UserSearch, User
from flask import Flask, render_template, request, jsonify, send_file, Response, stream_with_context, session, redirect, url_for
import os
import json
import csv
import threading
import queue
from io import StringIO
from datetime import datetime
from sqlalchemy import create_engine, MetaData, Table, Column, Integer, String, DateTime, Text
import bcrypt
from backend import (

    build_gene_receptor_ligand_table,
    fuzzy_search_kegg_disease
)

app = Flask(__name__)

app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-key-change-in-production')
app.config['SQLALCHEMY_DATABASE_URI'] = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'instance', 'diseasenet.db')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + app.config['SQLALCHEMY_DATABASE_URI']
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)

UPLOAD_FOLDER = 'uploads'
OUTPUT_FOLDER = 'outputs'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)
os.makedirs('instance/users', exist_ok=True)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['OUTPUT_FOLDER'] = OUTPUT_FOLDER

with app.app_context():
    db.create_all()

def get_user_db_path(username):
    base_dir = os.path.abspath(os.path.dirname(__file__))
    return os.path.join(base_dir, 'instance', 'users', f'{username}.db')

def init_user_db(username):
    db_path = get_user_db_path(username)
    engine = create_engine(f'sqlite:///{db_path}')
    metadata = MetaData()

    Table('user_search', metadata,
        Column('id', Integer, primary_key=True),
        Column('username', String(80), nullable=False),
        Column('disease_name', String(200), nullable=False),
        Column('searched_at', DateTime, default=datetime.utcnow)
    )

    metadata.create_all(engine)
    return db_path

def save_user_search(username, disease_name):
    init_user_db(username)
    engine = create_engine(f'sqlite:///{get_user_db_path(username)}')
    conn = engine.connect()
    from sqlalchemy import text
    conn.execute(
        text("INSERT INTO user_search (username, disease_name, searched_at) VALUES (:username, :disease, :time)"),
        {"username": username, "disease": disease_name, "time": datetime.utcnow()}
    )
    conn.commit()
    conn.close()

@app.route('/')
def home():
    return render_template('index.html', user=session.get('user'))

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        data = request.get_json()
        username = data.get('username', '').strip()
        password = data.get('password', '')
        
        if not username or not password:
            return jsonify({'success': False, 'error': 'Username and password required'}), 400
        
        if len(username) < 3:
            return jsonify({'success': False, 'error': 'Username must be at least 3 characters'}), 400
        
        if len(password) < 6:
            return jsonify({'success': False, 'error': 'Password must be at least 6 characters'}), 400
        
        existing_user = User.query.filter_by(username=username).first()
        if existing_user:
            return jsonify({'success': False, 'error': 'Username already exists'}), 400
        
        password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        
        new_user = User(username=username, password_hash=password_hash)
        db.session.add(new_user)
        db.session.commit()
        
        init_user_db(username)
        
        session['user'] = {'username': username}
        
        return jsonify({'success': True})
    
    return render_template('auth.html', mode='signup')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        data = request.get_json()
        username = data.get('username', '').strip()
        password = data.get('password', '')
        
        if not username or not password:
            return jsonify({'success': False, 'error': 'Username and password required'}), 400
        
        user = User.query.filter_by(username=username).first()
        
        if not user or not bcrypt.checkpw(password.encode('utf-8'), user.password_hash.encode('utf-8')):
            return jsonify({'success': False, 'error': 'Invalid username or password'}), 401
        
        session['user'] = {'username': username}
        
        return jsonify({'success': True})
    
    return render_template('auth.html', mode='login')

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect('/')

@app.route('/history')
def history():
    if 'user' not in session:
        return jsonify({'error': 'Not logged in'}), 401
    
    username = session['user']['username']
    db_path = get_user_db_path(username)
    
    if not os.path.exists(db_path):
        return jsonify([])
    
    engine = create_engine(f'sqlite:///{db_path}')
    conn = engine.connect()
    from sqlalchemy import text
    result = conn.execute(text("SELECT disease_name, searched_at FROM user_search ORDER BY searched_at DESC LIMIT 50"))
    searches = [{'disease': row[0], 'date': str(row[1])} for row in result]
    conn.close()
    
    return jsonify(searches)

@app.route('/suggest', methods=['POST'])
def suggest():
    data = request.get_json()
    disease_name = data.get('disease_name')
    
    if not disease_name:
        return jsonify({"error": "No disease name provided"}), 400
    
    suggestions = fuzzy_search_kegg_disease(disease_name)
    return jsonify(suggestions)

@app.route('/recent_searches', methods=['GET'])
def get_recent_searches():
    searches = Disease.query.order_by(Disease.kegg_disease_id.desc()).limit(10).all()
    return jsonify([{'name': s.disease_name, 'id': s.kegg_disease_id} for s in searches])

@app.route('/stream')
def stream():
    disease_name = request.args.get('disease_name', '').strip()
    if not disease_name:
        return jsonify({"error": "No disease name provided"}), 400

    result_queue = queue.Queue()
    current_user = session.get('user')

    def progress_callback(current, total, gene_symbol):
        result_queue.put(('progress', current, total, gene_symbol))

    def run_in_background():
        with app.app_context():
            table_data = build_gene_receptor_ligand_table(disease_name, progress_callback)
            if current_user:
                save_user_search(current_user['username'], disease_name)
        result_queue.put(('result', table_data))
        result_queue.put(('done', None))

    t = threading.Thread(target=run_in_background, daemon=True)
    t.start()

    def generate():
        while True:
            item = result_queue.get()
            event_type = item[0]

            if event_type == 'progress':
                _, current, total, gene_symbol = item
                payload = json.dumps({'current': current, 'total': total, 'gene': gene_symbol})
                yield f"event: progress\ndata: {payload}\n\n"

            elif event_type == 'result':
                _, table_data = item
                if not table_data:
                    suggestions = fuzzy_search_kegg_disease(disease_name)
                    payload = json.dumps({'error': 'No exact match found', 'suggestions': suggestions})
                else:
                    payload = json.dumps(table_data)
                yield f"event: result\ndata: {payload}\n\n"

            elif event_type == 'done':
                yield f"event: done\ndata: {{}}\n\n"
                break

    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'}
    )


@app.route('/process', methods=['POST'])
def process():
    data = request.get_json()
    disease_name = data.get('disease_name')
    
    if not disease_name:
        return jsonify({"error": "No disease name provided"}), 400
    
    table_data = build_gene_receptor_ligand_table(disease_name)
    
    if not table_data:
        suggestions = fuzzy_search_kegg_disease(disease_name)
        return jsonify({"error": "No exact match found", "suggestions": suggestions}), 404
    
    if 'user' in session:
        save_user_search(session['user']['username'], disease_name)
    
    return jsonify(table_data)

@app.route('/export_csv', methods=['POST'])
def export_csv():
    data = request.get_json()
    table_data = data.get('data')
    disease_name = data.get('disease_name', 'results')
    
    if not table_data:
        return jsonify({"error": "No data to export"}), 400
    
    output = StringIO()
    if table_data:
        headers = list(table_data[0].keys())
        writer = csv.DictWriter(output, fieldnames=headers)
        writer.writeheader()
        writer.writerows(table_data)
    
    filename = f"{disease_name.replace(' ', '_')}_results.csv"
    filepath = os.path.join(OUTPUT_FOLDER, filename)
    
    with open(filepath, 'w', newline='', encoding='utf-8') as f:
        f.write(output.getvalue())
    
    return send_file(filepath, as_attachment=True, download_name=filename)

if __name__ == '__main__':
    app.run(debug=True, threaded=True)
