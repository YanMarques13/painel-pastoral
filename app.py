from datetime import datetime
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


class SolicitacaoMaterial(db.Model):
    __tablename__ = 'solicitacao_material'
    id = db.Column(db.Integer, primary_key=True)
    distrito_id = db.Column(db.String(120), nullable=False, index=True)
    pastor_email = db.Column(db.String(180), nullable=False, index=True)
    pastor_nome = db.Column(db.String(180), nullable=False)
    igreja = db.Column(db.String(180), nullable=True)
    material = db.Column(db.String(240), nullable=False)
    quantidade = db.Column(db.Integer, nullable=False, default=1)
    finalidade = db.Column(db.Text, nullable=True)
    observacao_pastor = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(40), nullable=False, default='Solicitado', index=True)
    observacao_admin = db.Column(db.Text, nullable=True)
    codigo_envio = db.Column(db.String(160), nullable=True)
    solicitado_em = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    atualizado_em = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    enviado_em = db.Column(db.DateTime, nullable=True)


class TreinamentoVideo(db.Model):
    __tablename__ = 'treinamento_video'
    id = db.Column(db.Integer, primary_key=True)
    titulo = db.Column(db.String(240), nullable=False)
    descricao = db.Column(db.Text, nullable=True)
    youtube_url = db.Column(db.String(500), nullable=False)
    categoria = db.Column(db.String(120), nullable=True)
    ativo = db.Column(db.Boolean, nullable=False, default=True)
    criado_por = db.Column(db.String(180), nullable=False)
    criado_em = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    atualizado_em = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    bootstrap_usuarios()

with app.app_context():
    db.create_all()

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


def serializar_solicitacao_material(x):
    return {
        'id':x.id,'distritoId':x.distrito_id,'pastorEmail':x.pastor_email,'pastorNome':x.pastor_nome,
        'igreja':x.igreja,'material':x.material,'quantidade':x.quantidade,'finalidade':x.finalidade or '',
        'observacaoPastor':x.observacao_pastor or '','status':x.status,'observacaoAdmin':x.observacao_admin or '',
        'codigoEnvio':x.codigo_envio or '',
        'solicitadoEm':x.solicitado_em.isoformat() if x.solicitado_em else None,
        'atualizadoEm':x.atualizado_em.isoformat() if x.atualizado_em else None,
        'enviadoEm':x.enviado_em.isoformat() if x.enviado_em else None
    }

@app.get('/api/materiais')
def listar_materiais():
    u=usuario_logado()
    if not u: return jsonify({'detail':'Não autenticado'}),401
    q=SolicitacaoMaterial.query
    if u.role!='admin': q=q.filter_by(pastor_email=u.email)
    distrito=request.args.get('distrito')
    if u.role=='admin' and distrito: q=q.filter_by(distrito_id=distrito)
    itens=q.order_by(SolicitacaoMaterial.solicitado_em.desc()).all()
    return {'itens':[serializar_solicitacao_material(x) for x in itens]}

@app.post('/api/materiais')
def criar_material():
    u=usuario_logado()
    if not u: return jsonify({'detail':'Não autenticado'}),401
    data=request.get_json(silent=True) or {}
    material=str(data.get('material') or '').strip()
    try: quantidade=max(1,int(data.get('quantidade') or 1))
    except: return jsonify({'detail':'Quantidade inválida'}),400
    if not material: return jsonify({'detail':'Material obrigatório'}),400
    distrito=(u.distrito_id if u.role!='admin' else str(data.get('distritoId') or '').strip())
    if not distrito: return jsonify({'detail':'Distrito obrigatório'}),400
    pastor_email=u.email
    pastor_nome=u.nome
    if u.role=='admin' and data.get('pastorEmail'):
        pu=Usuario.query.filter_by(email=str(data.get('pastorEmail')).lower(),ativo=True).first()
        if pu:
            pastor_email, pastor_nome, distrito=pu.email,pu.nome,pu.distrito_id
    x=SolicitacaoMaterial(
        distrito_id=distrito,pastor_email=pastor_email,pastor_nome=pastor_nome,
        igreja=str(data.get('igreja') or '').strip(),material=material,quantidade=quantidade,
        finalidade=str(data.get('finalidade') or '').strip(),observacao_pastor=str(data.get('observacaoPastor') or '').strip(),
        status='Solicitado'
    )
    db.session.add(x);db.session.commit()
    return serializar_solicitacao_material(x),201

@app.put('/api/materiais/<int:item_id>')
def editar_material(item_id):
    u=usuario_logado()
    if not u: return jsonify({'detail':'Não autenticado'}),401
    x=SolicitacaoMaterial.query.get_or_404(item_id)
    data=request.get_json(silent=True) or {}
    if u.role!='admin':
        if x.pastor_email!=u.email: return jsonify({'detail':'Não autorizado'}),403
        if x.status not in ('Solicitado','Em análise'):
            return jsonify({'detail':'Solicitação já processada pelo administrador'}),409
        material=str(data.get('material') or '').strip()
        if not material:return jsonify({'detail':'Material obrigatório'}),400
        try:q=max(1,int(data.get('quantidade') or 1))
        except:return jsonify({'detail':'Quantidade inválida'}),400
        x.material=material;x.quantidade=q;x.igreja=str(data.get('igreja') or '').strip()
        x.finalidade=str(data.get('finalidade') or '').strip();x.observacao_pastor=str(data.get('observacaoPastor') or '').strip()
    else:
        status=str(data.get('status') or x.status)
        permitidos=('Solicitado','Em análise','Separando','Enviado','Entregue','Cancelado')
        if status not in permitidos:return jsonify({'detail':'Status inválido'}),400
        x.status=status;x.observacao_admin=str(data.get('observacaoAdmin') or '').strip()
        x.codigo_envio=str(data.get('codigoEnvio') or '').strip()
        if status=='Enviado' and not x.enviado_em:x.enviado_em=datetime.utcnow()
    x.atualizado_em=datetime.utcnow();db.session.commit()
    return serializar_solicitacao_material(x)

@app.delete('/api/materiais/<int:item_id>')
def excluir_material(item_id):
    u=usuario_logado()
    if not u:return jsonify({'detail':'Não autenticado'}),401
    x=SolicitacaoMaterial.query.get_or_404(item_id)
    if u.role!='admin':
        if x.pastor_email!=u.email:return jsonify({'detail':'Não autorizado'}),403
        if x.status not in ('Solicitado','Em análise'):return jsonify({'detail':'Solicitação já processada e não pode ser excluída'}),409
    db.session.delete(x);db.session.commit()
    return {'ok':True}


def serializar_treinamento(x):
    return {'id':x.id,'titulo':x.titulo,'descricao':x.descricao or '','youtubeUrl':x.youtube_url,'categoria':x.categoria or 'Geral','ativo':bool(x.ativo),'criadoPor':x.criado_por,'criadoEm':x.criado_em.isoformat() if x.criado_em else None}

@app.get('/api/treinamentos')
def listar_treinamentos():
    u=usuario_logado()
    if not u:return jsonify({'detail':'Não autenticado'}),401
    q=TreinamentoVideo.query
    if u.role!='admin':q=q.filter_by(ativo=True)
    return {'itens':[serializar_treinamento(x) for x in q.order_by(TreinamentoVideo.criado_em.desc()).all()]}

@app.post('/api/treinamentos')
def criar_treinamento():
    u=usuario_logado()
    if not u:return jsonify({'detail':'Não autenticado'}),401
    if u.role!='admin':return jsonify({'detail':'Somente o administrador pode cadastrar treinamentos'}),403
    d=request.get_json(silent=True) or {}; titulo=str(d.get('titulo') or '').strip(); url=str(d.get('youtubeUrl') or '').strip()
    if not titulo or not url:return jsonify({'detail':'Título e link do YouTube são obrigatórios'}),400
    if 'youtube.com/' not in url and 'youtu.be/' not in url:return jsonify({'detail':'Informe um link válido do YouTube'}),400
    x=TreinamentoVideo(titulo=titulo,descricao=str(d.get('descricao') or '').strip(),youtube_url=url,categoria=str(d.get('categoria') or 'Geral').strip() or 'Geral',ativo=True,criado_por=u.email)
    db.session.add(x);db.session.commit();return serializar_treinamento(x),201

@app.put('/api/treinamentos/<int:item_id>')
def editar_treinamento(item_id):
    u=usuario_logado()
    if not u:return jsonify({'detail':'Não autenticado'}),401
    if u.role!='admin':return jsonify({'detail':'Somente o administrador pode editar treinamentos'}),403
    x=TreinamentoVideo.query.get_or_404(item_id); d=request.get_json(silent=True) or {}; titulo=str(d.get('titulo') or '').strip(); url=str(d.get('youtubeUrl') or '').strip()
    if not titulo or not url:return jsonify({'detail':'Título e link do YouTube são obrigatórios'}),400
    if 'youtube.com/' not in url and 'youtu.be/' not in url:return jsonify({'detail':'Informe um link válido do YouTube'}),400
    x.titulo=titulo;x.youtube_url=url;x.descricao=str(d.get('descricao') or '').strip();x.categoria=str(d.get('categoria') or 'Geral').strip() or 'Geral';x.ativo=bool(d.get('ativo',True));x.atualizado_em=datetime.utcnow()
    db.session.commit();return serializar_treinamento(x)

@app.delete('/api/treinamentos/<int:item_id>')
def excluir_treinamento(item_id):
    u=usuario_logado()
    if not u:return jsonify({'detail':'Não autenticado'}),401
    if u.role!='admin':return jsonify({'detail':'Somente o administrador pode excluir treinamentos'}),403
    x=TreinamentoVideo.query.get_or_404(item_id);db.session.delete(x);db.session.commit();return {'ok':True}

if __name__ == '__main__':
    app.run(host='0.0.0.0',port=int(os.environ.get('PORT','8000')))
