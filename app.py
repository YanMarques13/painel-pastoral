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

class PlanejamentoDistrital(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    distrito_id = db.Column(db.String(120), unique=True, nullable=False, index=True)
    itinerario_pastoral = db.Column(JSONB().with_variant(db.JSON(), 'sqlite'), nullable=False, default=list)
    equipe_mordomia = db.Column(JSONB().with_variant(db.JSON(), 'sqlite'), nullable=False, default=list)
    itinerario_equipe = db.Column(JSONB().with_variant(db.JSON(), 'sqlite'), nullable=False, default=list)

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

def usuario_logado():
    email=session.get('email')
    if not email: return None
    return Usuario.query.filter_by(email=email, ativo=True).first()

def distrito_autorizado(distrito_solicitado):
    u=usuario_logado()
    if not u: return None, (jsonify({'detail':'Não autenticado'}),401)
    distrito=str(distrito_solicitado or '').strip()
    if not distrito: return None, (jsonify({'detail':'Distrito obrigatório'}),400)
    if u.role!='admin' and u.distrito_id!=distrito:
        return None, (jsonify({'detail':'Distrito não autorizado'}),403)
    return distrito, None

@app.get('/api/planejamento')
def get_planejamento():
    distrito,erro=distrito_autorizado(request.args.get('distrito'))
    if erro: return erro
    row=PlanejamentoDistrital.query.filter_by(distrito_id=distrito).first()
    return {
        'distritoId': distrito,
        'itinerarioPastoral': row.itinerario_pastoral if row else [],
        'equipeMordomia': row.equipe_mordomia if row else [],
        'itinerarioEquipe': row.itinerario_equipe if row else []
    }

@app.put('/api/planejamento')
def put_planejamento():
    data=request.get_json(silent=True) or {}
    distrito,erro=distrito_autorizado(data.get('distritoId'))
    if erro: return erro
    ip=data.get('itinerarioPastoral',[])
    em=data.get('equipeMordomia',[])
    ie=data.get('itinerarioEquipe',[])
    if not all(isinstance(x,list) for x in (ip,em,ie)):
        return jsonify({'detail':'Formato inválido'}),400
    row=PlanejamentoDistrital.query.filter_by(distrito_id=distrito).first()
    if not row:
        row=PlanejamentoDistrital(distrito_id=distrito)
        db.session.add(row)
    row.itinerario_pastoral=ip
    row.equipe_mordomia=em
    row.itinerario_equipe=ie
    db.session.commit()
    return {'ok':True}

if __name__ == '__main__':
    app.run(host='0.0.0.0',port=int(os.environ.get('PORT','8000')))
