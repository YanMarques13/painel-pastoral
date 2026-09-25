from datetime import datetime
import os, re, json, urllib.request
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
    departamento = db.Column(db.String(180), nullable=True, index=True)
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




class ProcessoVotacao(db.Model):
    __tablename__='processo_votacao'
    id=db.Column(db.Integer,primary_key=True)
    titulo=db.Column(db.String(240),nullable=False)
    descricao=db.Column(db.Text,nullable=True)
    status=db.Column(db.String(40),nullable=False,default='Indicações abertas',index=True)
    minimo_indicacoes=db.Column(db.Integer,nullable=False,default=2)
    max_votos=db.Column(db.Integer,nullable=False,default=1)
    voto_secreto=db.Column(db.Boolean,nullable=False,default=True)
    form_indicacao_url=db.Column(db.Text,nullable=True)
    form_votacao_url=db.Column(db.Text,nullable=True)
    criado_por=db.Column(db.String(180),nullable=False)
    criado_em=db.Column(db.DateTime,nullable=False,default=datetime.utcnow)

class IndicacaoVotacao(db.Model):
    __tablename__='indicacao_votacao'
    id=db.Column(db.Integer,primary_key=True)
    processo_id=db.Column(db.Integer,db.ForeignKey('processo_votacao.id'),nullable=False,index=True)
    nome=db.Column(db.String(220),nullable=False,index=True)
    indicado_por=db.Column(db.String(180),nullable=True)
    criado_em=db.Column(db.DateTime,nullable=False,default=datetime.utcnow)

class VotoComissao(db.Model):
    __tablename__='voto_comissao'
    id=db.Column(db.Integer,primary_key=True)
    processo_id=db.Column(db.Integer,db.ForeignKey('processo_votacao.id'),nullable=False,index=True)
    candidato=db.Column(db.String(220),nullable=False,index=True)
    eleitor_hash=db.Column(db.String(128),nullable=True,index=True)
    criado_em=db.Column(db.DateTime,nullable=False,default=datetime.utcnow)


class PowerBIConfig(db.Model):
    __tablename__ = 'powerbi_config'
    id = db.Column(db.Integer, primary_key=True)
    titulo = db.Column(db.String(240), nullable=False, default='Painel Power BI')
    embed_url = db.Column(db.Text, nullable=True)
    ativo = db.Column(db.Boolean, nullable=False, default=True)
    atualizado_por = db.Column(db.String(180), nullable=True)
    atualizado_em = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

# Inicialização segura — V11.9
with app.app_context():
    db.create_all()
    # Migração compatível com bancos já publicados: adiciona Departamento sem apagar dados.
    try:
        with db.engine.begin() as c:
            if db.engine.dialect.name=='postgresql':
                c.exec_driver_sql('ALTER TABLE solicitacao_material ADD COLUMN IF NOT EXISTS departamento VARCHAR(180)')
            else:
                cols=[r[1] for r in c.exec_driver_sql('PRAGMA table_info(solicitacao_material)').fetchall()]
                if 'departamento' not in cols:c.exec_driver_sql('ALTER TABLE solicitacao_material ADD COLUMN departamento VARCHAR(180)')
    except Exception as e:
        print('Aviso migração departamento:',e)
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


def serializar_solicitacao_material(x):
    return {
        'id':x.id,'distritoId':x.distrito_id,'pastorEmail':x.pastor_email,'pastorNome':x.pastor_nome,
        'igreja':x.igreja,'departamento':x.departamento or '','material':x.material,'quantidade':x.quantidade,'finalidade':x.finalidade or '',
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
        igreja=str(data.get('igreja') or '').strip(),departamento=str(data.get('departamento') or '').strip(),material=material,quantidade=quantidade,
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
        x.material=material;x.quantidade=q;x.igreja=str(data.get('igreja') or '').strip();x.departamento=str(data.get('departamento') or '').strip()
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


def _admin():
    u=usuario_logado(); return u if u and u.role=='admin' else None

def _google_form(tipo, processo, candidatos=None):
    """Integração real opcional via Google Apps Script Web App. Configure GOOGLE_FORMS_WEBAPP_URL."""
    endpoint=os.environ.get('GOOGLE_FORMS_WEBAPP_URL','').strip()
    if not endpoint:return None
    payload={'tipo':tipo,'processoId':processo.id,'titulo':processo.titulo,'descricao':processo.descricao or '',
             'candidatos':candidatos or [],'maxVotos':processo.max_votos}
    req=urllib.request.Request(endpoint,data=json.dumps(payload).encode(),headers={'Content-Type':'application/json'},method='POST')
    with urllib.request.urlopen(req,timeout=20) as resp:
        out=json.loads(resp.read().decode())
    return out.get('url') or out.get('publishedUrl')

def _proc(x):
    inds=IndicacaoVotacao.query.filter_by(processo_id=x.id).all()
    cont={}
    for i in inds:
        k=i.nome.strip(); cont[k]=cont.get(k,0)+1
    candidatos=[{'nome':n,'indicacoes':q} for n,q in sorted(cont.items(),key=lambda z:(-z[1],z[0]))]
    votos=VotoComissao.query.filter_by(processo_id=x.id).all(); vc={}
    for v in votos:vc[v.candidato]=vc.get(v.candidato,0)+1
    return {'id':x.id,'titulo':x.titulo,'descricao':x.descricao or '','status':x.status,'minimoIndicacoes':x.minimo_indicacoes,
      'maxVotos':x.max_votos,'votoSecreto':x.voto_secreto,'formIndicacaoUrl':x.form_indicacao_url or '',
      'formVotacaoUrl':x.form_votacao_url or '','candidatos':candidatos,'resultados':[{'nome':n,'votos':q} for n,q in sorted(vc.items(),key=lambda z:-z[1])]}

@app.get('/api/votacoes')
def listar_votacoes():
    if not usuario_logado():return jsonify({'detail':'Não autenticado'}),401
    return {'itens':[_proc(x) for x in ProcessoVotacao.query.order_by(ProcessoVotacao.criado_em.desc()).all()]}

@app.post('/api/votacoes')
def criar_votacao():
    u=_admin()
    if not u:return jsonify({'detail':'Somente administrador'}),403
    d=request.get_json(silent=True) or {}; titulo=str(d.get('titulo') or '').strip()
    if not titulo:return jsonify({'detail':'Título obrigatório'}),400
    x=ProcessoVotacao(titulo=titulo,descricao=str(d.get('descricao') or '').strip(),minimo_indicacoes=max(1,int(d.get('minimoIndicacoes') or 2)),max_votos=max(1,int(d.get('maxVotos') or 1)),voto_secreto=bool(d.get('votoSecreto',True)),criado_por=u.email)
    db.session.add(x);db.session.commit()
    try:x.form_indicacao_url=_google_form('indicacao',x);db.session.commit()
    except Exception as e:print('Google Forms:',e)
    return _proc(x),201

@app.post('/api/votacoes/<int:pid>/indicacoes')
def indicar_nome(pid):
    u=usuario_logado(); x=ProcessoVotacao.query.get_or_404(pid)
    if not u:return jsonify({'detail':'Não autenticado'}),401
    if x.status!='Indicações abertas':return jsonify({'detail':'Indicações encerradas'}),409
    nome=str((request.get_json(silent=True) or {}).get('nome') or '').strip()
    if not nome:return jsonify({'detail':'Nome obrigatório'}),400
    db.session.add(IndicacaoVotacao(processo_id=pid,nome=nome,indicado_por=u.email));db.session.commit();return _proc(x),201

@app.post('/api/votacoes/<int:pid>/abrir-votacao')
def abrir_votacao(pid):
    if not _admin():return jsonify({'detail':'Somente administrador'}),403
    x=ProcessoVotacao.query.get_or_404(pid); dados=_proc(x); nomes=[c['nome'] for c in dados['candidatos'] if c['indicacoes']>=x.minimo_indicacoes]
    if not nomes:return jsonify({'detail':'Nenhum nome atingiu o mínimo de indicações'}),409
    x.status='Votação aberta'
    try:x.form_votacao_url=_google_form('votacao',x,nomes)
    except Exception as e:print('Google Forms:',e)
    db.session.commit();return _proc(x)

@app.post('/api/votacoes/<int:pid>/votos')
def votar(pid):
    import hashlib
    u=usuario_logado();x=ProcessoVotacao.query.get_or_404(pid)
    if not u:return jsonify({'detail':'Não autenticado'}),401
    if x.status!='Votação aberta':return jsonify({'detail':'Votação não está aberta'}),409
    nomes=(request.get_json(silent=True) or {}).get('nomes') or []
    if not isinstance(nomes,list) or not nomes or len(nomes)>x.max_votos:return jsonify({'detail':'Quantidade de votos inválida'}),400
    eleg=[c['nome'] for c in _proc(x)['candidatos'] if c['indicacoes']>=x.minimo_indicacoes]
    if any(n not in eleg for n in nomes):return jsonify({'detail':'Candidato inválido'}),400
    h=hashlib.sha256((str(pid)+'|'+u.email+'|'+app.config['SECRET_KEY']).encode()).hexdigest()
    if VotoComissao.query.filter_by(processo_id=pid,eleitor_hash=h).first():return jsonify({'detail':'Participante já votou'}),409
    for n in nomes:db.session.add(VotoComissao(processo_id=pid,candidato=n,eleitor_hash=h))
    db.session.commit();return {'ok':True}

@app.post('/api/votacoes/<int:pid>/encerrar')
def encerrar_votacao(pid):
    if not _admin():return jsonify({'detail':'Somente administrador'}),403
    x=ProcessoVotacao.query.get_or_404(pid);x.status='Finalizada';db.session.commit();return _proc(x)

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


@app.get('/api/powerbi-config')
def get_powerbi_config():
    u=usuario_logado()
    if not u:
        return jsonify({'detail':'Não autenticado'}),401
    row=PowerBIConfig.query.order_by(PowerBIConfig.id.asc()).first()
    if not row:
        return {'titulo':'Painel Power BI','embedUrl':'','ativo':True,'podeEditar':u.role=='admin'}
    return {'titulo':row.titulo,'embedUrl':row.embed_url or '','ativo':bool(row.ativo),'podeEditar':u.role=='admin'}

@app.put('/api/powerbi-config')
def put_powerbi_config():
    u=usuario_logado()
    if not u:
        return jsonify({'detail':'Não autenticado'}),401
    if u.role!='admin':
        return jsonify({'detail':'Somente o administrador pode configurar o Power BI'}),403
    d=request.get_json(silent=True) or {}
    titulo=str(d.get('titulo') or 'Painel Power BI').strip() or 'Painel Power BI'
    url=str(d.get('embedUrl') or '').strip()
    if url and not (url.startswith('https://app.powerbi.com/') or url.startswith('https://msit.powerbi.com/')):
        return jsonify({'detail':'Informe um link HTTPS de incorporação do Power BI'}),400
    row=PowerBIConfig.query.order_by(PowerBIConfig.id.asc()).first()
    if not row:
        row=PowerBIConfig()
        db.session.add(row)
    row.titulo=titulo
    row.embed_url=url
    row.ativo=bool(d.get('ativo',True))
    row.atualizado_por=u.email
    row.atualizado_em=datetime.utcnow()
    db.session.commit()
    return {'ok':True,'titulo':row.titulo,'embedUrl':row.embed_url or '','ativo':bool(row.ativo)}

if __name__ == '__main__':
    app.run(host='0.0.0.0',port=int(os.environ.get('PORT','8000')))
