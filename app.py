import os, re
from pathlib import Path
from flask import Flask, request, jsonify, send_file, session
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.dialects.postgresql import JSONB
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.security import generate_password_hash, check_password_hash

BASE_DIR = Path(__file__).resolve().parent
app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY') or os.environ.get('DJANGO_SECRET_KEY') or 'troque-esta-chave-em-producao'
url = os.environ.get('DATABASE_URL', 'sqlite:///painel_local.db')
if url.startswith('postgres://'):
    url = 'postgresql://' + url[len('postgres://'):]
app.config['SQLALCHEMY_DATABASE_URI'] = url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE'] = os.environ.get('COOKIE_SECURE','1') == '1'
db = SQLAlchemy(app)

class Usuario(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(180), unique=True, nullable=False, index=True)
    nome = db.Column(db.String(220), nullable=False)
    distrito_id = db.Column(db.String(120), nullable=True)
    role = db.Column(db.String(30), nullable=False, default='pastor')
    password_hash = db.Column(db.String(512), nullable=False)
    ativo = db.Column(db.Boolean, nullable=False, default=True)

class Acompanhamento(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(180), unique=True, nullable=False, index=True)
    membros = db.Column(JSONB().with_variant(db.JSON(), 'sqlite'), nullable=False, default=list)

def usuarios_do_painel():
    texto=(BASE_DIR/'painel.html').read_text(encoding='utf-8')
    padrao=r'\{id:(\d+),email:"([^"]+)",senha:"[^"]*",nome:"([^"]+)",distritoId:"([^"]+)"'
    return [dict(id=int(i), email=e.lower(), nome=n, distrito_id=d) for i,e,n,d in re.findall(padrao,texto)]

def bootstrap_usuarios():
    senha_inicial=os.environ.get('INITIAL_PASTOR_PASSWORD','123456')
    for item in usuarios_do_painel():
        u=Usuario.query.filter_by(email=item['email']).first()
        if not u:
            db.session.add(Usuario(email=item['email'], nome=item['nome'], distrito_id=item['distrito_id'], role='pastor', password_hash=generate_password_hash(senha_inicial)))
        else:
            u.nome=item['nome']; u.distrito_id=item['distrito_id']; u.role='pastor'; u.ativo=True
    admin_email=os.environ.get('INITIAL_ADMIN_EMAIL','admin@painelpastoral.local').strip().lower()
    admin_password=os.environ.get('INITIAL_ADMIN_PASSWORD','AdminPastoral2026!')
    admin=Usuario.query.filter_by(email=admin_email).first()
    if not admin:
        admin=Usuario(email=admin_email, nome='Administrador Geral', distrito_id=None, role='admin', password_hash=generate_password_hash(admin_password))
        db.session.add(admin)
    else:
        admin.nome='Administrador Geral'
        admin.distrito_id=None
        admin.role='admin'
        admin.ativo=True
        # V9.3: sincroniza a senha do administrador com a variável do Railway.
        # Isso corrige bancos Neon já existentes que guardavam um hash de senha anterior.
        admin.password_hash=generate_password_hash(admin_password)
    db.session.commit()

with app.app_context():
    db.create_all()
    bootstrap_usuarios()

@app.get('/')
def index():
    # V9.8: abrir o sistema sempre exige autenticação nova.
    # Nenhuma sessão anterior é reutilizada ao abrir/recarregar a raiz.
    session.clear()
    response = send_file(BASE_DIR/'painel.html')
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    return response

@app.get('/health')
def health():
    try:
        total=Usuario.query.count()
        return {'status':'ok','usuarios':total}
    except Exception:
        return {'status':'erro'},500

@app.post('/api/login')
def login():
    data=request.get_json(silent=True) or {}
    email=str(data.get('email','')).strip().lower()
    senha=str(data.get('senha',''))
    u=Usuario.query.filter_by(email=email, ativo=True).first()
    if not u or not check_password_hash(u.password_hash, senha):
        return jsonify({'detail':'Credenciais inválidas'}),401
    session.clear(); session['email']=u.email; session['role']=u.role
    return {'ok':True,'email':u.email,'nome':u.nome,'role':u.role,'distritoId':u.distrito_id}

@app.post('/api/logout')
def logout():
    session.clear(); return {'ok':True}

@app.get('/api/me')
def me():
    email=session.get('email')
    if not email: return jsonify({'detail':'Não autenticado'}),401
    u=Usuario.query.filter_by(email=email, ativo=True).first()
    if not u: session.clear(); return jsonify({'detail':'Não autenticado'}),401
    return {'email':u.email,'nome':u.nome,'role':u.role,'distritoId':u.distrito_id}

@app.get('/api/dashboard-context')
def dashboard_context():
    # V9.8: o dashboard só recebe autorização depois de uma sessão válida.
    email=session.get('email')
    if not email:
        return jsonify({'detail':'Não autenticado'}),401
    u=Usuario.query.filter_by(email=email, ativo=True).first()
    if not u:
        session.clear()
        return jsonify({'detail':'Não autenticado'}),401
    return {
        'ok': True,
        'email': u.email,
        'nome': u.nome,
        'role': u.role,
        'distritoId': u.distrito_id,
        'adminGeral': u.role == 'admin'
    }

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
    data=request.get_json(silent=True) or {}; membros=data.get('membros')
    if not isinstance(membros,list): return jsonify({'detail':'Formato inválido'}),400
    row=Acompanhamento.query.filter_by(email=email).first()
    if not row:
        row=Acompanhamento(email=email,membros=membros); db.session.add(row)
    else: row.membros=membros
    db.session.commit(); return {'ok':True}

if __name__ == '__main__':
    app.run(host='0.0.0.0',port=int(os.environ.get('PORT','8000')))
