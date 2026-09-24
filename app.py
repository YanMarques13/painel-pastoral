import os, re
from pathlib import Path
from flask import Flask, request, jsonify, send_file, session
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.dialects.postgresql import JSONB
from werkzeug.middleware.proxy_fix import ProxyFix

BASE_DIR = Path(__file__).resolve().parent
app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'troque-esta-chave-em-producao')
url = os.environ.get('DATABASE_URL', 'sqlite:///painel_local.db')
if url.startswith('postgres://'):
    url = 'postgresql://' + url[len('postgres://'):]
app.config['SQLALCHEMY_DATABASE_URI'] = url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE'] = os.environ.get('COOKIE_SECURE','1') == '1'
db = SQLAlchemy(app)

class Acompanhamento(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(180), unique=True, nullable=False, index=True)
    membros = db.Column(JSONB().with_variant(db.JSON(), 'sqlite'), nullable=False, default=list)

with app.app_context():
    db.create_all()

def emails_autorizados():
    texto=(BASE_DIR/'painel.html').read_text(encoding='utf-8')
    return {x.lower() for x in re.findall(r'email:"([^"]+)"', texto)}

@app.get('/')
def index():
    return send_file(BASE_DIR/'painel.html')

@app.get('/health')
def health():
    return {'status':'ok'}

@app.post('/api/login')
def login():
    data=request.get_json(silent=True) or {}
    email=str(data.get('email','')).strip().lower()
    senha=str(data.get('senha',''))
    senha_inicial=os.environ.get('INITIAL_PASTOR_PASSWORD','123456')
    if email not in emails_autorizados() or senha != senha_inicial:
        return jsonify({'detail':'Credenciais inválidas'}),401
    session['email']=email
    return {'ok':True,'email':email}

@app.post('/api/logout')
def logout():
    session.clear(); return {'ok':True}

def email_logado():
    return session.get('email')

@app.get('/api/acompanhamento')
def get_acompanhamento():
    email=email_logado()
    if not email: return jsonify({'detail':'Não autenticado'}),401
    row=Acompanhamento.query.filter_by(email=email).first()
    return {'membros': row.membros if row else []}

@app.put('/api/acompanhamento')
def put_acompanhamento():
    email=email_logado()
    if not email: return jsonify({'detail':'Não autenticado'}),401
    data=request.get_json(silent=True) or {}
    membros=data.get('membros')
    if not isinstance(membros,list): return jsonify({'detail':'Formato inválido'}),400
    row=Acompanhamento.query.filter_by(email=email).first()
    if not row:
        row=Acompanhamento(email=email,membros=membros); db.session.add(row)
    else: row.membros=membros
    db.session.commit()
    return {'ok':True}

if __name__ == '__main__':
    app.run(host='0.0.0.0',port=int(os.environ.get('PORT','8000')))
