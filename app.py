# -*- coding: utf-8 -*-
import random
from flask import Flask, render_template, request, redirect, url_for, flash, session, make_response, jsonify, abort
import paramiko
import re
import io
import math
from fpdf import FPDF
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from datetime import datetime, timedelta
import os
import subprocess
import threading
import shlex
import signal
import tempfile
import select
import struct
from werkzeug.utils import secure_filename
from flask_socketio import SocketIO, emit

# ── PTY conditionally available (Linux only) ──
try:
    import pty
    import fcntl
    import termios
    _HAS_PTY = True
except ImportError:
    _HAS_PTY = False

# ── Fix Flask 3.x compat: RequestContext.session has no setter ──
from flask.ctx import RequestContext
if not hasattr(RequestContext, '_session_setter'):
    def _session_setter(self, value):
        object.__setattr__(self, '_session', value)
    RequestContext.session = property(RequestContext.session.fget, _session_setter)
    RequestContext._session_setter = True

app = Flask(__name__)
app.secret_key = 'cluster_nidtec_secret'

# ── Tiempo de sesión ────────────────────────────────────────────────
# Admin: 20 min | Usuario normal: 40 min
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=2)  # techo duro
SESSION_ADMIN_MIN = 20
SESSION_USER_MIN = 40
WARNING_SECONDS = 60  # mostrar advertencia 1 min antes

UPLOAD_FOLDER = 'static/uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Configuración de base de datos (PostgreSQL)
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://postgres:123@localhost:5432/CLUSTER_NIDTEC'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# FUERZA LA CODIFICACIÓN A UTF8 PARA EVITAR EL UNICODEDECODEERROR
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    "connect_args": {
        "options": "-c client_encoding=utf8"
    }
}

db = SQLAlchemy(app)
bcrypt = Bcrypt(app)
socketio = SocketIO(app, cors_allowed_origins="*")

# ── Almacén de terminales activas (sid -> {master_fd, pid, thread}) ──
_active_terminals = {}
_active_terminals_lock = threading.Lock()

# --- Modelos ---
class Usuario(db.Model):
    __tablename__ = 'usuarios'
    id_usuario = db.Column(db.Integer, primary_key=True)
    nombre_apellido = db.Column(db.String(255), nullable=False)
    correo_electronico = db.Column(db.String(255), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    es_administrador = db.Column(db.Boolean, default=False)
    foto_perfil = db.Column(db.String(255), default='default_avatar.png')

    def __init__(self, nombre_apellido, correo_electronico, password_hash, es_administrador=False, foto_perfil='default_avatar.png'):
        self.nombre_apellido = nombre_apellido
        self.correo_electronico = correo_electronico
        self.password_hash = password_hash
        self.es_administrador = es_administrador
        self.foto_perfil = foto_perfil

class Solicitud(db.Model):
    __tablename__ = 'solicitudes'
    id_solicitud = db.Column(db.Integer, primary_key=True)
    id_usuario_solicitante = db.Column(db.Integer, db.ForeignKey('usuarios.id_usuario'), nullable=False)
    facultad = db.Column(db.String(255))
    carrera = db.Column(db.String(255))
    nombre_proyecto = db.Column(db.String(255))
    asignatura_modulo = db.Column(db.String(255))
    profesor_tutor = db.Column(db.String(255))
    software_requerido = db.Column(db.Text)
    fecha_solicitud = db.Column(db.Date, default=db.func.current_date())
    fecha_inicio = db.Column(db.Date)
    fecha_finalizacion_estimada = db.Column(db.Date)
    estado = db.Column(db.String(50), default='PENDIENTE')
    observaciones = db.Column(db.Text)
    usuario_creado = db.Column(db.Boolean, default=False)
    acceso_nodos = db.Column(db.Boolean, default=False)
    maquina_virtual = db.Column(db.Boolean, default=False)
    detalles_mv = db.Column(db.Text)
    autorizado_por = db.Column(db.String(255))
    nombre_solicitante = db.Column(db.String(255))
    correo_solicitante = db.Column(db.String(255))
    
    usuario = db.relationship('Usuario', backref='solicitudes')

    def __init__(self, id_usuario_solicitante, facultad, carrera, nombre_proyecto, asignatura_modulo, profesor_tutor, software_requerido, fecha_inicio, fecha_finalizacion_estimada, observaciones, fecha_solicitud, nombre_solicitante, correo_solicitante, estado='PENDIENTE', usuario_creado=False, acceso_nodos=False, maquina_virtual=False, detalles_mv=None, autorizado_por=None):
        self.id_usuario_solicitante = id_usuario_solicitante
        self.facultad = facultad
        self.carrera = carrera
        self.nombre_proyecto = nombre_proyecto
        self.asignatura_modulo = asignatura_modulo
        self.profesor_tutor = profesor_tutor
        self.software_requerido = software_requerido
        self.fecha_inicio = fecha_inicio
        self.fecha_finalizacion_estimada = fecha_finalizacion_estimada
        self.observaciones = observaciones
        self.fecha_solicitud = fecha_solicitud
        self.nombre_solicitante = nombre_solicitante
        self.correo_solicitante = correo_solicitante
        self.estado = estado
        self.usuario_creado = usuario_creado
        self.acceso_nodos = acceso_nodos
        self.maquina_virtual = maquina_virtual
        self.detalles_mv = detalles_mv
        self.autorizado_por = autorizado_por

class SolicitudAprobada(db.Model):
    __tablename__ = 'solicitudes_aprobadas'
    id_solicitud_aprobada = db.Column(db.Integer, primary_key=True)
    id_solicitud_origen = db.Column(db.Integer, db.ForeignKey('solicitudes.id_solicitud'))
    fecha_aprobacion = db.Column(db.DateTime, default=datetime.utcnow)
    resolucion_numero = db.Column(db.String(50), nullable=True)
    estado_aprobacion = db.Column(db.String(50), default='ACTIVO')
     
    # ---- AGREGAR ESTA RELACIÓN ----
    # Nos permite hacer: aprobacion.solicitud para ir a la solicitud madre
    solicitud = db.relationship('Solicitud', backref=db.backref('aprobacion', uselist=False))

class Proyecto(db.Model):
    __tablename__ = 'proyectos'
    id_proyecto = db.Column(db.Integer, primary_key=True)
    id_solicitud_aprobada = db.Column(db.Integer, db.ForeignKey('solicitudes_aprobadas.id_solicitud_aprobada'))
    id_administrador_autorizante = db.Column(db.Integer, db.ForeignKey('usuarios.id_usuario'))
    usuario_sistema_creado = db.Column(db.String(50), nullable=True)
    acceso_nodos_fisicos = db.Column(db.Boolean, default=False)  # Verifica el nombre exacto en tu SQL
    requiere_maquina_virtual = db.Column(db.Boolean, default=False)
    observaciones = db.Column(db.Text, nullable=True)

    # ---- AGREGAR ESTA RELACIÓN ----
    # Nos permite hacer: p.solicitud_aprobada para ir a la tabla del medio
    solicitud_aprobada = db.relationship('SolicitudAprobada', backref=db.backref('proyecto', uselist=False))

class Notificacion(db.Model):
    __tablename__ = 'notificaciones'
    id_notificacion = db.Column(db.Integer, primary_key=True)
    id_usuario_destino = db.Column(db.Integer, db.ForeignKey('usuarios.id_usuario'), nullable=False)
    mensaje = db.Column(db.String(500), nullable=False)
    fecha = db.Column(db.DateTime, default=datetime.now)
    leida = db.Column(db.Boolean, default=False)
    tipo = db.Column(db.String(50)) # 'SOLICITUD', 'ESTADO'

    usuario = db.relationship('Usuario', backref='notificaciones')

    def __init__(self, id_usuario_destino, mensaje, tipo, leida=False):
        self.id_usuario_destino = id_usuario_destino
        self.mensaje = mensaje
        self.tipo = tipo
        self.leida = leida

class Noticia(db.Model):
    __tablename__ = 'noticias'
    id_noticia = db.Column(db.Integer, primary_key=True)
    titulo = db.Column(db.String(255), nullable=False)
    descripcion = db.Column(db.Text, nullable=False)
    fecha_creacion = db.Column(db.DateTime, default=datetime.now)
    fecha_evento = db.Column(db.Date)
    autor_id = db.Column(db.Integer, db.ForeignKey('usuarios.id_usuario'))
    
    autor = db.relationship('Usuario')

    def __init__(self, titulo, descripcion, fecha_evento, autor_id):
        self.titulo = titulo
        self.descripcion = descripcion
        self.fecha_evento = fecha_evento
        self.autor_id = autor_id

# ── Before request: verificar expiración de sesión ──────────────────
@app.before_request
def verificar_sesion_expirada():
    if 'user_id' in session and request.endpoint not in ('login', 'index', 'registro', 'recuperar_password', 'extender_sesion', 'tiempo_sesion', 'static'):
        expira = session.get('session_expires_at')
        if expira and datetime.now().timestamp() > expira:
            session.clear()
            flash('Tu sesión ha expirado por inactividad. Inicia sesión nuevamente.', 'warning')
            return redirect(url_for('index'))
    # Pasar el tiempo restante a todas las plantillas protegidas
    if 'user_id' in session:
        expira = session.get('session_expires_at')
        if expira:
            remainder = int(expira - datetime.now().timestamp())
            session['_session_remaining'] = max(0, remainder)

# ── Helper para tiempo de sesión ────────────────────────────────────
def get_session_timeout_minutes(is_admin):
    return SESSION_ADMIN_MIN if is_admin else SESSION_USER_MIN

# --- Rutas ---

# ==========================================
#          RUTAS DE ACCESO PRINCIPAL
# ==========================================

@app.route('/')
def index():
    """Renderiza la Landing Page institucional del Cluster NIDTEC."""
    return render_template('index.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        # 1. Validar Captcha Matemático
        try:
            user_answer = int(request.form.get('captcha_answer', 0))
        except ValueError:
            user_answer = 0

        correct_answer = session.get('captcha_result')

        if correct_answer is None or user_answer != correct_answer:
            flash('Captcha incorrecto. Por favor, resuelva la suma.', 'danger')
            return redirect(url_for('login'))

        # 2. Lógica de Autenticación Real usando SQLAlchemy y Bcrypt
        correo = request.form.get('correo')
        password = request.form.get('password')

        # Buscamos al usuario en la base de datos de PostgreSQL
        usuario = Usuario.query.filter_by(correo_electronico=correo).first()

        # Verificamos si existe y si el hash de la contraseña coincide
        if usuario and bcrypt.check_password_hash(usuario.password_hash, password):
            # Guardamos los datos críticos en la sesión de Flask
            session.permanent = True
            session['user_id'] = usuario.id_usuario
            session['user_name'] = usuario.nombre_apellido
            session['is_admin'] = usuario.es_administrador
            timeout_min = get_session_timeout_minutes(usuario.es_administrador)
            session['session_expires_at'] = (datetime.now() + timedelta(minutes=timeout_min)).timestamp()

            # Limpiamos el captcha usado de la sesión
            session.pop('captcha_result', None)

            flash(f'¡Bienvenido de vuelta, {usuario.nombre_apellido}!', 'success')
            return redirect(url_for('dashboard'))
        else:
            # Si las credenciales fallan, generamos números nuevos para evitar ataques de fuerza bruta
            flash('Correo electrónico o contraseña incorrectos.', 'danger')

            num1 = random.randint(1, 9)
            num2 = random.randint(1, 9)
            session['captcha_result'] = num1 + num2
            return render_template('login.html', num1=num1, num2=num2)

    # Flujo normal GET (Cuando cargan la página de login por primera vez)
    num1 = random.randint(1, 9)
    num2 = random.randint(1, 9)
    session['captcha_result'] = num1 + num2

    return render_template('login.html', num1=num1, num2=num2)

@app.route('/recuperar_password', methods=['GET', 'POST'])
def recuperar_password():
    if request.method == 'POST':
        correo = request.form.get('correo')
        # Aquí irá tu lógica futura para enviar correo o restablecer token en PostgreSQL
        flash('Si el correo existe en el sistema, se han enviado las instrucciones de recuperación.', 'info')
        return redirect(url_for('login'))
        
    return render_template('recuperar_password.html')


@app.route('/registro', methods=['GET', 'POST'])
def registro():
    if request.method == 'POST':
        nombre = request.form.get('nombre')
        correo = request.form.get('correo')
        password = request.form.get('password')
        es_admin = True if request.form.get('es_admin') else False
        
        # Verificar si el correo ya existe
        if Usuario.query.filter_by(correo_electronico=correo).first():
            flash('El correo ya está registrado', 'danger')
            return redirect(url_for('registro'))
        
        hashed_pw = bcrypt.generate_password_hash(password).decode('utf-8')
        nuevo_usuario = Usuario(
            nombre_apellido=nombre,
            correo_electronico=correo,
            password_hash=hashed_pw,
            es_administrador=es_admin
        )
        db.session.add(nuevo_usuario)
        db.session.commit()
        
        flash('Cuenta creada con éxito. Ya puedes iniciar sesión.', 'success')
        return redirect(url_for('index'))
    
    return render_template('registro.html')

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('index'))
    
    user_id = session.get('user_id')
    is_admin = session.get('is_admin')
    
    # Obtener solicitudes reales de la base de datos y convertirlas a diccionarios
    if is_admin:
        db_solicitudes_raw = Solicitud.query.order_by(Solicitud.id_solicitud.desc()).all()
    else:
        db_solicitudes_raw = Solicitud.query.filter_by(id_usuario_solicitante=user_id).order_by(Solicitud.id_solicitud.desc()).all()
    
    db_solicitudes = []
    for s in db_solicitudes_raw:
        # Lógica de estado FINALIZADO basado en la fecha
        estado_mostrar = s.estado
        if s.estado == 'ACEPTADA' and s.fecha_finalizacion_estimada and s.fecha_finalizacion_estimada < datetime.now().date():
            estado_mostrar = 'FINALIZADO'

        db_solicitudes.append({
            'id_solicitud': s.id_solicitud,
            'nombre_solicitante': s.nombre_solicitante,
            'correo_solicitante': s.correo_solicitante,
            'nombre_proyecto': s.nombre_proyecto,
            'facultad': s.facultad,
            'carrera': s.carrera,
            'asignatura_modulo': s.asignatura_modulo,
            'profesor_tutor': s.profesor_tutor,
            'software_requerido': s.software_requerido,
            'observaciones': s.observaciones,
            'fecha_inicio': s.fecha_inicio,
            'fecha_finalizacion_estimada': s.fecha_finalizacion_estimada,
            'estado': estado_mostrar,
            'acceso_nodos': s.acceso_nodos,
            'maquina_virtual': s.maquina_virtual,
            'detalles_mv': s.detalles_mv,
            'autorizado_por': s.autorizado_por,
            'fecha_solicitud': s.fecha_solicitud,
            'usuario': {
                'id_usuario': s.usuario.id_usuario,
                'nombre_apellido': s.usuario.nombre_apellido,
                'correo_electronico': s.usuario.correo_electronico,
                'es_administrador': s.usuario.es_administrador
            } if s.usuario else None
        })
    
    # Notificaciones unread count
    unread_count = Notificacion.query.filter_by(id_usuario_destino=user_id, leida=False).count()
    unread_notifs = Notificacion.query.filter_by(id_usuario_destino=user_id, leida=False).order_by(Notificacion.fecha.desc()).limit(5).all()
    
    # Usuario actual para el sidebar
    user = Usuario.query.get(user_id)

    # Noticias para la columna lateral (Próximos 7 días)
    fecha_limite = (datetime.now() + timedelta(days=7)).date()
    noticias_sidebar = Noticia.query.filter(Noticia.fecha_evento <= fecha_limite, Noticia.fecha_evento >= datetime.now().date()).order_by(Noticia.fecha_evento.asc()).all()

    return render_template('dashboard.html', solicitudes=db_solicitudes, is_admin=is_admin, unread_count=unread_count, unread_notifs=unread_notifs, noticias_sidebar=noticias_sidebar, session_remaining=session.get('_session_remaining', 0), user=user)

# ── Extender sesión ────────────────────────────────────────────────
@app.route('/extender-sesion', methods=['POST'])
def extender_sesion():
    if 'user_id' not in session:
        return jsonify({'ok': False, 'error': 'no_session'}), 401
    is_admin = session.get('is_admin', False)
    timeout_min = get_session_timeout_minutes(is_admin)
    session['session_expires_at'] = (datetime.now() + timedelta(minutes=timeout_min)).timestamp()
    return jsonify({'ok': True, 'remaining': timeout_min * 60})

# ── Consultar tiempo restante ──────────────────────────────────────
@app.route('/tiempo-sesion')
def tiempo_sesion():
    if 'user_id' not in session:
        return jsonify({'ok': False, 'error': 'no_session'}), 401
    expira = session.get('session_expires_at')
    if not expira:
        return jsonify({'ok': False, 'error': 'no_expiry'}), 400
    remaining = int(expira - datetime.now().timestamp())
    return jsonify({'ok': True, 'remaining': max(0, remaining)})

@app.route('/solicitud', methods=['GET', 'POST'])
def nueva_solicitud():
    if 'user_id' not in session:
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        try:
            nueva = Solicitud(
                id_usuario_solicitante=session['user_id'],
                facultad=request.form.get('facultad'),
                carrera=request.form.get('carrera'),
                nombre_proyecto=request.form.get('proyecto'),
                asignatura_modulo=request.form.get('asignatura'),
                profesor_tutor=request.form.get('tutor'),
                software_requerido=request.form.get('software'),
                fecha_inicio=datetime.strptime(request.form.get('fecha_inicio'), '%Y-%m-%d').date(),
                fecha_finalizacion_estimada=datetime.strptime(request.form.get('fecha_fin'), '%Y-%m-%d').date(),
                observaciones=request.form.get('observaciones'),
                fecha_solicitud=datetime.strptime(request.form.get('fecha_solicitud'), '%Y-%m-%d').date() if session.get('is_admin') and request.form.get('fecha_solicitud') else datetime.now().date(),
                nombre_solicitante=request.form.get('nombre_solicitante'),
                correo_solicitante=request.form.get('correo_solicitante'),
                estado='PENDIENTE',
                usuario_creado=request.form.get('usuario_creado') == 'on',
                acceso_nodos=request.form.get('acceso_nodos') == 'on',
                maquina_virtual=request.form.get('maquina_virtual') == 'on',
                detalles_mv=request.form.get('detalles_mv'),
                autorizado_por=request.form.get('autorizado_por')
            )
            db.session.add(nueva)
            db.session.commit()

            # Notificar a los administradores
            admins = Usuario.query.filter_by(es_administrador=True).all()
            for admin in admins:
                notif = Notificacion(
                    id_usuario_destino=admin.id_usuario,
                    mensaje=f"Nueva solicitud de recursos: {nueva.nombre_proyecto} de {nueva.nombre_solicitante or session.get('user_name')}",
                    tipo='SOLICITUD'
                )
                db.session.add(notif)
            db.session.commit()

            flash('Solicitud enviada correctamente', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Error al enviar solicitud: {str(e)}', 'danger')
            
        return redirect(url_for('dashboard'))
    
    user = Usuario.query.get(session['user_id'])
    user_id = session.get('user_id')
    unread_count, unread_notifs = get_unread_notifications(user_id)
    return render_template('solicitud.html', 
                         now=datetime.now(), 
                         user_email=user.correo_electronico,
                         is_admin=session.get('is_admin', False),
                         unread_count=unread_count, unread_notifs=unread_notifs)

@app.route('/solicitud/<int:id>/aceptar', methods=['POST'])
def aceptar_solicitud(id):
    if 'user_id' not in session or not session.get('is_admin'):
        flash('Acceso no autorizado', 'danger')
        return redirect(url_for('index'))

    solicitud = Solicitud.query.get_or_404(id)
    
    try:
        # 1. Actualizar la solicitud madre
        solicitud.estado = 'ACEPTADA'
        solicitud.acceso_nodos = True if request.form.get('acceso_nodos') else False
        solicitud.maquina_virtual = True if request.form.get('maquina_virtual') else False
        solicitud.detalles_mv = request.form.get('detalles_mv')
        solicitud.autorizado_por = session.get('user_name')

        # 2. Crear el registro en solicitudes_aprobadas
        # Generamos un número de resolución ficticio o secuencial para la auditoría
        num_resolucion = f"RES-{datetime.now().year}-{solicitud.id_solicitud:03d}"
        
        aprobacion = SolicitudAprobada(
            id_solicitud_origen=solicitud.id_solicitud,
            fecha_aprobacion=datetime.now(),
            resolucion_numero=num_resolucion,
            estado_aprobacion='PROCESADA'
        )
        db.session.add(aprobacion)
        db.session.flush() # Esto genera el id_solicitud_aprobada sin cerrar la transacción

        # 3. Crear el proyecto formal amarrado a la aprobación
        nuevo_proyecto = Proyecto(
            id_solicitud_aprobada=aprobacion.id_solicitud_aprobada,
            id_administrador_autorizante=session.get('user_id'),
            usuario_sistema_creado=f"usr_{solicitud.id_solicitud}", # Nombre de usuario para el cluster
            acceso_nodos_fisicos=solicitud.acceso_nodos,
            requiere_maquina_virtual=solicitud.maquina_virtual,
            observaciones=solicitud.observaciones
        )
        db.session.add(nuevo_proyecto)

        # 4. Crear la notificación para el alumno/investigador
        notif = Notificacion(
            id_usuario_destino=solicitud.id_usuario_solicitante,
            mensaje=f"Tu solicitud para '{solicitud.nombre_proyecto}' ha sido ACEPTADA y se ha creado el proyecto.",
            tipo='ESTADO'
        )
        db.session.add(notif)

        # Guardamos todo en la base de datos de forma atómica
        db.session.commit()
        flash(f'Solicitud #{id} aceptada. Registros creados en solicitudes_aprobadas y proyectos.', 'success')

    except Exception as e:
        db.session.rollback()
        flash(f'Error en la base de datos al procesar la aprobación: {str(e)}', 'danger')

    return redirect(url_for('dashboard'))

@app.route('/solicitud/<int:id>/rechazar')
def rechazar_solicitud(id):
    if 'user_id' not in session or not session.get('is_admin'):
        flash('Acceso no autorizado', 'danger')
        return redirect(url_for('index'))
    
    solicitud = Solicitud.query.get_or_404(id)
    solicitud.estado = 'RECHAZADA'
    db.session.commit()

    # Notificar al usuario
    notif = Notificacion(
        id_usuario_destino=solicitud.id_usuario_solicitante,
        mensaje=f"Tu solicitud para '{solicitud.nombre_proyecto}' ha sido RECHAZADA.",
        tipo='ESTADO'
    )
    db.session.add(notif)
    db.session.commit()

    flash(f'Solicitud #{id} rechazada', 'warning')
    return redirect(url_for('dashboard'))

@app.route('/solicitud/<int:id>/borrar', methods=['POST'])
def borrar_solicitud(id):
    if 'user_id' not in session:
        flash('Acceso no autorizado', 'danger')
        return redirect(url_for('index'))
    
    solicitud = Solicitud.query.get_or_404(id)
    # Admin puede borrar cualquiera; usuario solo la suya si está PENDIENTE
    is_admin = session.get('is_admin', False)
    is_owner = solicitud.id_usuario_solicitante == session['user_id']
    if not is_admin and not (is_owner and solicitud.estado == 'PENDIENTE'):
        flash('No tiene permisos para eliminar esta solicitud', 'danger')
        return redirect(url_for('dashboard'))

    # Eliminar registros relacionados antes de borrar la solicitud
    aprobacion = SolicitudAprobada.query.filter_by(id_solicitud_origen=solicitud.id_solicitud).first()
    if aprobacion:
        Proyecto.query.filter_by(id_solicitud_aprobada=aprobacion.id_solicitud_aprobada).delete()
        db.session.delete(aprobacion)
    db.session.delete(solicitud)
    db.session.commit()
    flash(f'Solicitud #{id} eliminada permanentemente', 'info')
    return redirect(url_for('dashboard'))

@app.route('/solicitud/<int:id>/editar', methods=['POST'])
def editar_solicitud(id):
    if 'user_id' not in session:
        flash('Acceso no autorizado', 'danger')
        return redirect(url_for('index'))

    solicitud = Solicitud.query.get_or_404(id)
    is_admin = session.get('is_admin', False)
    is_owner = solicitud.id_usuario_solicitante == session['user_id']
    if not is_admin and not (is_owner and solicitud.estado == 'PENDIENTE'):
        flash('No tiene permisos para editar esta solicitud', 'danger')
        return redirect(url_for('dashboard'))

    try:
        solicitud.nombre_proyecto = request.form.get('nombre_proyecto', solicitud.nombre_proyecto)
        solicitud.facultad = request.form.get('facultad', solicitud.facultad)
        solicitud.carrera = request.form.get('carrera', solicitud.carrera)
        solicitud.asignatura_modulo = request.form.get('asignatura_modulo', solicitud.asignatura_modulo)
        solicitud.profesor_tutor = request.form.get('profesor_tutor', solicitud.profesor_tutor)
        solicitud.software_requerido = request.form.get('software_requerido', solicitud.software_requerido)
        solicitud.observaciones = request.form.get('observaciones', solicitud.observaciones)
        fecha_inicio_str = request.form.get('fecha_inicio')
        fecha_fin_str = request.form.get('fecha_finalizacion_estimada')
        if fecha_inicio_str:
            solicitud.fecha_inicio = datetime.strptime(fecha_inicio_str, '%Y-%m-%d').date()
        if fecha_fin_str:
            solicitud.fecha_finalizacion_estimada = datetime.strptime(fecha_fin_str, '%Y-%m-%d').date()
        db.session.commit()
        flash(f'Solicitud #{id} actualizada correctamente', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error al editar solicitud: {str(e)}', 'danger')

    return redirect(url_for('dashboard'))

@app.route('/arquitectura')
def arquitectura():
    if 'user_id' not in session:
        return redirect(url_for('index'))
    
    is_admin = session.get('is_admin', False)
    return render_template('arquitectura.html', is_admin=is_admin)

@app.route('/solicitud/<int:id>/pdf')
def solicitud_pdf(id):
    if 'user_id' not in session:
        return redirect(url_for('index'))
    
    s = Solicitud.query.get_or_404(id)
    
    # Verificar que el usuario tenga acceso a esta solicitud
    if not session.get('is_admin') and s.id_usuario_solicitante != session.get('user_id'):
        flash('Acceso no autorizado', 'danger')
        return redirect(url_for('dashboard'))
    
    pdf = FPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=20)
    
    # Colores institucionales
    azul = (26, 54, 104)
    gris = (100, 116, 139)
    negro = (30, 41, 59)
    
    # Encabezado con logo
    logo_path = os.path.join(app.root_path, 'static', 'img', 'logo-FNC.png')
    pdf.set_fill_color(*azul)
    pdf.rect(0, 0, 210, 35, 'F')
    if os.path.exists(logo_path):
        pdf.image(logo_path, x=12, y=4, w=22)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font('Helvetica', 'B', 18)
    pdf.set_xy(10, 8)
    pdf.cell(0, 10, 'FNOGUERA CLUSTER', align='C')
    pdf.set_font('Helvetica', '', 9)
    pdf.set_xy(10, 20)
    pdf.cell(0, 6, 'Nucleo de Investigacion y Desarrollo Tecnologico - NIDTEC', align='C')
    pdf.set_xy(10, 27)
    pdf.cell(0, 6, 'Facultad Politecnica - Universidad Nacional de Asuncion', align='C')
    
    # Título del documento
    pdf.ln(40)
    pdf.set_text_color(*azul)
    pdf.set_font('Helvetica', 'B', 14)
    pdf.cell(0, 10, f'Detalle de Solicitud #{s.id_solicitud}', align='C')
    pdf.ln(10)
    pdf.set_draw_color(200, 200, 200)
    pdf.set_line_width(0.3)
    pdf.line(30, pdf.get_y(), 180, pdf.get_y())
    pdf.ln(10)
    
    # Información principal
    pdf.set_text_color(*negro)
    pdf.set_font('Helvetica', 'B', 11)
    
    def put_row(label, value):
        pdf.set_font('Helvetica', 'B', 10)
        pdf.set_text_color(*gris)
        pdf.cell(50, 7, label, border=0)
        pdf.set_font('Helvetica', '', 10)
        pdf.set_text_color(*negro)
        pdf.cell(0, 7, str(value or 'N/A'), border=0)
        pdf.ln(7)
    
    put_row('Solicitante:', s.nombre_solicitante or s.usuario.nombre_apellido)
    put_row('Correo:', s.correo_solicitante or s.usuario.correo_electronico)
    put_row('Fecha Solicitud:', s.fecha_solicitud.strftime('%d/%m/%Y') if s.fecha_solicitud else 'N/A')
    put_row('Facultad:', s.facultad)
    put_row('Carrera:', s.carrera)
    put_row('Proyecto:', s.nombre_proyecto)
    put_row('Asignatura/Modulo:', s.asignatura_modulo)
    put_row('Tutor:', s.profesor_tutor)
    
    pdf.ln(5)
    pdf.set_draw_color(200, 200, 200)
    pdf.set_line_width(0.2)
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.ln(5)
    
    put_row('Periodo:', f"{s.fecha_inicio.strftime('%d/%m/%Y')} - {s.fecha_finalizacion_estimada.strftime('%d/%m/%Y')}")
    put_row('Estado:', s.estado)
    
    pdf.ln(5)
    pdf.set_draw_color(200, 200, 200)
    pdf.set_line_width(0.2)
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.ln(5)
    
    # Software requerido
    pdf.set_font('Helvetica', 'B', 10)
    pdf.set_text_color(*gris)
    pdf.cell(0, 7, 'Software Requerido:', border=0)
    pdf.ln(7)
    pdf.set_font('Helvetica', '', 10)
    pdf.set_text_color(*negro)
    pdf.multi_cell(0, 6, s.software_requerido or 'N/A')
    pdf.ln(3)
    
    # Observaciones
    pdf.set_font('Helvetica', 'B', 10)
    pdf.set_text_color(*gris)
    pdf.cell(0, 7, 'Observaciones:', border=0)
    pdf.ln(7)
    pdf.set_font('Helvetica', '', 10)
    pdf.set_text_color(*negro)
    pdf.multi_cell(0, 6, s.observaciones or 'Sin observaciones')
    
    # Información de autorización (si aceptada)
    if s.estado == 'ACEPTADA':
        pdf.ln(5)
        pdf.set_draw_color(200, 200, 200)
        pdf.set_line_width(0.2)
        pdf.line(10, pdf.get_y(), 200, pdf.get_y())
        pdf.ln(5)
        pdf.set_text_color(*azul)
        pdf.set_font('Helvetica', 'B', 12)
        pdf.cell(0, 10, 'Informacion de Autorizacion', align='C')
        pdf.ln(10)
        
        pdf.set_text_color(*negro)
        pdf.set_font('Helvetica', '', 10)
        put_row('Acceso a Nodos:', 'SI' if s.acceso_nodos else 'NO')
        put_row('Maquina Virtual:', 'SI' if s.maquina_virtual else 'NO')
        put_row('Autorizado por:', s.autorizado_por or 'Admin')
        if s.detalles_mv:
            pdf.set_font('Helvetica', 'B', 10)
            pdf.set_text_color(*gris)
            pdf.cell(0, 7, 'Detalles de Recursos:', border=0)
            pdf.ln(7)
            pdf.set_font('Helvetica', '', 10)
            pdf.set_text_color(*negro)
            pdf.multi_cell(0, 6, s.detalles_mv)
    
    # Footer
    pdf.ln(10)
    pdf.set_draw_color(200, 200, 200)
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.ln(3)
    pdf.set_font('Helvetica', '', 7)
    pdf.set_text_color(*gris)
    pdf.cell(0, 5, f'Documento generado el {datetime.now().strftime("%d/%m/%Y %H:%M")} - FNOGUERA CLUSTER NIDTEC', align='C')
    
    # Generar respuesta
    pdf_output = bytes(pdf.output())
    response = make_response(pdf_output)
    response.headers['Content-Type'] = 'application/pdf'
    # ?preview=1 → inline (vista previa en el navegador), sin ?preview → attachment (descarga directa)
    is_preview = request.args.get('preview') == '1'
    disposition = 'inline' if is_preview else 'attachment'
    response.headers['Content-Disposition'] = f'{disposition}; filename=solicitud_{s.id_solicitud}.pdf'
    return response

@app.route('/proyectos')
def proyectos():
    if 'user_id' not in session:
        return redirect(url_for('index'))

    is_admin = session.get('is_admin', False)

    # Consulta relacional real usando JOINs
    proyectos_reales = db.session.query(Proyecto).join(SolicitudAprobada).join(Solicitud).all()
    
    db_proyectos = []
    for p in proyectos_reales:
        # Recuperamos la solicitud original escalando por las relaciones del ORM
        s = p.solicitud_aprobada.solicitud 
        
        estado_mostrar = 'Activo'
        if s.fecha_finalizacion_estimada and s.fecha_finalizacion_estimada < datetime.now().date():
            estado_mostrar = 'Finalizado'

        db_proyectos.append({
            'id': s.id_solicitud,
            'nombre': s.nombre_proyecto,
            'investigador': s.nombre_solicitante or (s.usuario.nombre_apellido if s.usuario else "Usuario Desconocido"),
            'recursos': s.detalles_mv or 'Recursos asignados',
            'estado': estado_mostrar,
            'fecha_fin': s.fecha_finalizacion_estimada.strftime('%Y-%m-%d') if s.fecha_finalizacion_estimada else 'N/A'
        })

    user_id = session.get('user_id')
    unread_count, unread_notifs = get_unread_notifications(user_id)
    return render_template('proyectos.html', is_admin=is_admin, proyectos=db_proyectos, unread_count=unread_count, unread_notifs=unread_notifs)

@app.route('/recursos')
def recursos():
    if 'user_id' not in session:
        return redirect(url_for('index'))
    
    is_admin = session.get('is_admin', False)
    user_id = session.get('user_id')
    user = Usuario.query.get(user_id)
    ssh_config = get_user_ssh_config(user.correo_electronico) if user else None
    
    # Valores por defecto (evitan división por cero)
    recursos_data = {
        'nodos': [
            {'nombre': 'nodo-01', 'cpu_uso': 0, 'ram_uso': 0, 'estado': 'Offline'},
            {'nombre': 'nodo-02', 'cpu_uso': 0, 'ram_uso': 0, 'estado': 'Offline'},
            {'nombre': 'nodo-03', 'cpu_uso': 0, 'ram_uso': 0, 'estado': 'Offline'},
            {'nombre': 'nodo-gpu-01', 'cpu_uso': 0, 'ram_uso': 0, 'estado': 'Offline'}
        ],
        'total_cpu': 1,
        'uso_cpu': 0,
        'total_ram': 1,
        'uso_ram': 0,
        'total_gpu': 1,
        'uso_gpu': 0
    }
    
    # Intentar obtener datos reales via SSH
    if ssh_config:
        try:
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(
                hostname=ssh_config['host'],
                username=ssh_config['username'],
                password=ssh_config['password'],
                timeout=10
            )
            
            # Obtener uso de CPU (carga promedio)
            stdin, stdout, stderr = ssh.exec_command("top -bn1 | grep 'Cpu(s)' | awk '{print $2}'", timeout=10)
            cpu_str = stdout.read().decode().strip()
            uso_cpu_porcentaje = float(cpu_str) if cpu_str else 0
            
            # Obtener uso de RAM
            stdin, stdout, stderr = ssh.exec_command("free -m | awk 'NR==2{print $3, $2}'", timeout=10)
            ram_line = stdout.read().decode().strip().split()
            uso_ram = int(ram_line[0]) if len(ram_line) > 0 else 0
            total_ram = int(ram_line[1]) if len(ram_line) > 1 else 1
            
            # Obtener número de núcleos CPU
            stdin, stdout, stderr = ssh.exec_command("nproc", timeout=10)
            total_cpu = int(stdout.read().decode().strip() or 1)
            
            # Obtener hostname del nodo
            stdin, stdout, stderr = ssh.exec_command("hostname", timeout=10)
            hostname = stdout.read().decode().strip()
            
            ssh.close()
            
            # Distribuir la carga entre los nodos de forma realista
            # Si el hostname coincide con algún nodo, usamos datos reales; si no, 
            # asignamos los datos reales al primer nodo y simulamos variación en los demás
            uso_ram_porcentaje = int(uso_ram / max(total_ram, 1) * 100)
            
            asignado = False
            for nodo in recursos_data['nodos']:
                if hostname and (nodo['nombre'] == hostname or nodo['nombre'].endswith(hostname[-2:])):
                    nodo['cpu_uso'] = min(int(uso_cpu_porcentaje), 100)
                    nodo['ram_uso'] = min(uso_ram_porcentaje, 100)
                    nodo['estado'] = 'Online'
                    asignado = True
                else:
                    # Variación simulada para los demás nodos basada en datos reales
                    nodo['cpu_uso'] = min(max(0, int(uso_cpu_porcentaje) + (-10 + (ord(nodo['nombre'][-1]) % 21))), 100)
                    nodo['ram_uso'] = min(max(0, uso_ram_porcentaje + (-5 + (ord(nodo['nombre'][-1]) % 11))), 100)
                    nodo['estado'] = 'Online' if int(uso_cpu_porcentaje) > 0 or uso_ram_porcentaje > 0 else 'Offline'
            
            if not asignado and int(uso_cpu_porcentaje) > 0:
                recursos_data['nodos'][0]['cpu_uso'] = min(int(uso_cpu_porcentaje), 100)
                recursos_data['nodos'][0]['ram_uso'] = min(uso_ram_porcentaje, 100)
                recursos_data['nodos'][0]['estado'] = 'Online'
            
            recursos_data['total_cpu'] = total_cpu
            recursos_data['uso_cpu'] = int(total_cpu * uso_cpu_porcentaje / 100)
            recursos_data['total_ram'] = total_ram
            recursos_data['uso_ram'] = uso_ram
            recursos_data['total_gpu'] = 4
            recursos_data['uso_gpu'] = 1
            
        except Exception:
            pass  # Si falla SSH, quedan los valores por defecto
    
    # Notificaciones sin leer
    unread_count, unread_notifs = get_unread_notifications(user_id)
    
    return render_template('recursos.html', is_admin=is_admin, recursos=recursos_data, unread_count=unread_count, unread_notifs=unread_notifs)

from flask import session, redirect, url_for, abort  # Asegúrate de importar abort si no lo tienes

@app.route('/terminal')
def terminal():
    if 'user_id' not in session:
        return redirect(url_for('index'))
    is_admin = session.get('is_admin', False)
    user_id = session.get('user_id')
    user = Usuario.query.get(user_id)
    ssh_config = get_user_ssh_config(user.correo_electronico) if user else None
    unread_count, unread_notifs = get_unread_notifications(user_id)
    return render_template('terminal.html', is_admin=is_admin, ssh_config=ssh_config, unread_count=unread_count, unread_notifs=unread_notifs)

@app.route('/perfil')
def perfil():
    if 'user_id' not in session:
        return redirect(url_for('login'))
        
    user_id = session.get('user_id')
    user = Usuario.query.get(user_id)
    unread_count, unread_notifs = get_unread_notifications(user_id)
    is_admin = session.get('is_admin', False)
    
    return render_template('perfil.html', user=user, is_admin=is_admin, unread_count=unread_count, unread_notifs=unread_notifs)

@app.route('/actualizar_perfil', methods=['POST'])
def actualizar_perfil():
    if 'user_id' not in session:
        return redirect(url_for('index'))
    
    user = Usuario.query.get(session['user_id'])
    user.nombre_apellido = request.form.get('nombre')
    user.correo_electronico = request.form.get('correo')
    
    try:
        db.session.commit()
        session['user_name'] = user.nombre_apellido # Actualizar sesión
        flash('Información de perfil actualizada', 'success')
    except:
        db.session.rollback()
        flash('Error: El correo electrónico ya está en uso', 'danger')
        
    return redirect(url_for('perfil'))

@app.route('/usuarios')
def lista_usuarios():
    if 'user_id' not in session or not session.get('is_admin'):
        flash('Acceso no autorizado', 'danger')
        return redirect(url_for('index'))

    # Obtener usuarios reales de la base de datos y convertirlos a diccionarios
    db_usuarios_raw = Usuario.query.all()
    db_usuarios = []
    for u in db_usuarios_raw:
        db_usuarios.append({
            'id_usuario': u.id_usuario,
            'nombre_apellido': u.nombre_apellido,
            'correo_electronico': u.correo_electronico,
            'es_administrador': u.es_administrador,
            'foto_perfil': u.foto_perfil
        })
    
    user_id = session.get('user_id')
    unread_count, unread_notifs = get_unread_notifications(user_id)
    return render_template('usuarios.html', usuarios=db_usuarios, is_admin=True, unread_count=unread_count, unread_notifs=unread_notifs)

@app.route('/promover/<int:id>')
def promover_usuario(id):
    if 'user_id' not in session or not session.get('is_admin'):
        flash('Acceso no autorizado', 'danger')
        return redirect(url_for('index'))
    
    user = Usuario.query.get_or_404(id)
    if user.es_administrador:
        flash(f'{user.nombre_apellido} ya es administrador', 'warning')
        return redirect(url_for('lista_usuarios'))
    
    user.es_administrador = True
    db.session.commit()
    
    # Si el usuario promovido es el mismo de la sesión, actualizar la sesión
    if user.id_usuario == session.get('user_id'):
        session['is_admin'] = True
    
    flash(f'✓ {user.nombre_apellido} ahora es administrador', 'success')
    return redirect(url_for('lista_usuarios'))

@app.route('/degradar/<int:id>')
def degradar_usuario(id):
    if 'user_id' not in session or not session.get('is_admin'):
        flash('Acceso no autorizado', 'danger')
        return redirect(url_for('index'))
    
    # Prevenir que el usuario se quite el admin a sí mismo
    if id == session['user_id']:
        flash('No puedes quitarte el rol de administrador a ti mismo', 'warning')
        return redirect(url_for('lista_usuarios'))
    
    user = Usuario.query.get_or_404(id)
    if not user.es_administrador:
        flash(f'{user.nombre_apellido} no es administrador', 'warning')
        return redirect(url_for('lista_usuarios'))
    
    user.es_administrador = False
    db.session.commit()
    
    # Si el usuario degradado es el mismo de la sesión, actualizar sesión
    if user.id_usuario == session.get('user_id'):
        session['is_admin'] = False
    
    flash(f'✓ Rol de administrador removido para {user.nombre_apellido}', 'info')
    return redirect(url_for('lista_usuarios'))

@app.route('/cambiar_password', methods=['POST'])
def cambiar_password():
    if 'user_id' not in session:
        return redirect(url_for('index'))
    
    current_pw = request.form.get('current_password')
    new_pw = request.form.get('new_password')
    
    user = Usuario.query.get(session['user_id'])
    
    if bcrypt.check_password_hash(user.password_hash, current_pw):
        user.password_hash = bcrypt.generate_password_hash(new_pw).decode('utf-8')
        db.session.commit()
        flash('Contraseña actualizada con éxito', 'success')
    else:
        flash('La contraseña actual es incorrecta', 'danger')
        
    return redirect(url_for('perfil'))

# --- SSH Credentials ---
SSH_CREDENTIALS = {
    'fernandogustavonogueratorres@fpuna.edu.py': {
        'host': '192.168.1.9',
        'username': 'fnoguera',
        'password': '.fnoguera2026.'
    }
}

def get_user_ssh_config(user_email):
    return SSH_CREDENTIALS.get(user_email)


def get_unread_notifications(user_id):
    """Retorna (unread_count, unread_notifs) para un usuario dado."""
    count = Notificacion.query.filter_by(id_usuario_destino=user_id, leida=False).count()
    notifs = Notificacion.query.filter_by(id_usuario_destino=user_id, leida=False).order_by(Notificacion.fecha.desc()).limit(5).all()
    return count, notifs

@app.route('/terminal/exec', methods=['POST'])
def terminal_exec():
    if 'user_id' not in session:
        return jsonify({'error': 'No autorizado'}), 401
    
    user = Usuario.query.get(session['user_id'])
    if not user:
        return jsonify({'error': 'Usuario no encontrado'}), 404
    
    ssh_config = get_user_ssh_config(user.correo_electronico)
    if not ssh_config:
        return jsonify({'error': 'No tienes acceso SSH asignado'}), 403
    
    command = request.json.get('command', '')
    if not command.strip():
        return jsonify({'output': ''})
    
    # Comandos peligrosos bloqueados
    blocked = ['rm -rf', 'mkfs', 'dd if=', 'shutdown', 'reboot', 'init 0', 'init 6']
    if any(cmd in command.lower() for cmd in blocked):
        return jsonify({'output': 'Comando bloqueado por seguridad\n'})
    
    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(
            hostname=ssh_config['host'],
            username=ssh_config['username'],
            password=ssh_config['password'],
            timeout=10
        )
        
        stdin, stdout, stderr = ssh.exec_command(command, timeout=30)
        output = stdout.read().decode('utf-8', errors='replace')
        error = stderr.read().decode('utf-8', errors='replace')
        ssh.close()
        
        if error:
            output += error
        
        if not output.strip():
            output = 'Comando ejecutado correctamente (sin salida)\n'
        
        return jsonify({'output': output})
    except paramiko.AuthenticationException:
        return jsonify({'output': 'Error: Autenticación SSH fallida\n'})
    except paramiko.SSHException as e:
        return jsonify({'output': f'Error SSH: {str(e)}\n'})
    except Exception as e:
        return jsonify({'output': f'Error de conexión: {str(e)}\n'})

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/actualizar_foto', methods=['POST'])
def actualizar_foto():
    if 'user_id' not in session:
        return redirect(url_for('index'))
    
    if 'foto' not in request.files:
        flash('No se seleccionó ninguna imagen', 'danger')
        return redirect(url_for('perfil'))
    
    file = request.files['foto']
    if file.filename == '':
        flash('No se seleccionó ninguna imagen', 'danger')
        return redirect(url_for('perfil'))
    
    if file and allowed_file(file.filename):
        filename = secure_filename(f"user_{session['user_id']}_{file.filename}")
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        
        user = Usuario.query.get(session['user_id'])
        user.foto_perfil = filename
        db.session.commit()
        
        flash('Foto de perfil actualizada', 'success')
    else:
        flash('Formato de archivo no permitido', 'danger')
        
    return redirect(url_for('perfil'))

@app.after_request
def no_cache(response):
    if 'user_id' in session:
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
    return response

@app.route('/logout')
def logout():
    # 1. Limpiamos la sesión del usuario PRIMERO en el servidor
    session.clear()

    # 2. Construimos la respuesta redirigiendo a la Landing Page ('index')
    # Esto cargará tu index.html institucional de manera limpia
    resp = make_response(redirect(url_for('index')))

    # 3. Forzamos la destrucción de la caché en el navegador por seguridad
    resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0, post-check=0, pre-check=0'
    resp.headers['Pragma'] = 'no-cache'
    resp.headers['Expires'] = '0'

    return resp

@app.route('/notificaciones/limpiar')
def limpiar_notificaciones():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    Notificacion.query.filter_by(id_usuario_destino=session['user_id']).update({Notificacion.leida: True})
    db.session.commit()
    return redirect(request.referrer or url_for('dashboard'))

@app.context_processor
def inject_globals():
    ctx = {}
    if 'user_id' in session:
        user = Usuario.query.get(session['user_id'])
        ctx['user'] = user
        ctx['is_admin'] = user.es_administrador if user else False
        notifs = Notificacion.query.filter_by(id_usuario_destino=session['user_id'], leida=False).order_by(Notificacion.fecha.desc()).limit(5).all()
        count = Notificacion.query.filter_by(id_usuario_destino=session['user_id'], leida=False).count()
        ctx['unread_notifs'] = notifs
        ctx['unread_count'] = count
    else:
        ctx['user'] = None
        ctx['is_admin'] = False
        ctx['unread_notifs'] = []
        ctx['unread_count'] = 0
    return ctx


@app.route('/noticias')
def noticias():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    todas_noticias = Noticia.query.order_by(Noticia.fecha_creacion.desc()).all()
    user = Usuario.query.get(session['user_id'])
    is_admin = user.es_administrador if user else False
    
    unread_count = Notificacion.query.filter_by(id_usuario_destino=session['user_id'], leida=False).count()
    unread_notifs = Notificacion.query.filter_by(id_usuario_destino=session['user_id'], leida=False).order_by(Notificacion.fecha.desc()).limit(5).all()

    return render_template('noticias.html', noticias=todas_noticias, is_admin=is_admin, unread_count=unread_count, unread_notifs=unread_notifs)

@app.route('/noticias/crear', methods=['POST'])
def crear_noticia():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    user = Usuario.query.get(session['user_id'])
    if not user or not user.es_administrador:
        flash('No tiene permisos para realizar esta acción.', 'danger')
        return redirect(url_for('noticias'))

    titulo = request.form.get('titulo')
    descripcion = request.form.get('descripcion')
    fecha_evento_str = request.form.get('fecha_evento')
    
    fecha_evento = None
    if fecha_evento_str:
        fecha_evento = datetime.strptime(fecha_evento_str, '%Y-%m-%d').date()

    nueva_noticia = Noticia(titulo=titulo, descripcion=descripcion, fecha_evento=fecha_evento, autor_id=session['user_id'])
    db.session.add(nueva_noticia)
    db.session.commit()

    if fecha_evento:
        dias_para_evento = (fecha_evento - datetime.now().date()).days
        if dias_para_evento <= 7:
            usuarios = Usuario.query.all()
            for u in usuarios:
                notif = Notificacion(
                    id_usuario_destino=u.id_usuario,
                    mensaje=f'RECORDATORIO: {titulo} - {descripcion[:50]}...',
                    tipo='NOTICIA'
                )
                db.session.add(notif)
            db.session.commit()

    flash('Noticia creada correctamente.', 'success')
    return redirect(url_for('noticias'))

@app.route('/noticias/eliminar/<int:id>')
def eliminar_noticia(id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    user = Usuario.query.get(session['user_id'])
    if not user or not user.es_administrador:
        flash('No tiene permisos.', 'danger')
        return redirect(url_for('noticias'))

    noticia = Noticia.query.get(id)
    if noticia:
        db.session.delete(noticia)
        db.session.commit()
        flash('Noticia eliminada.', 'success')
    
    return redirect(url_for('noticias'))

# ═══════════════════════════════════════════════════════════════════════
#   OPEN CODE ADMIN PANEL — Job Submission + Embedded Terminal
# ═══════════════════════════════════════════════════════════════════════

@app.route('/admin/open-code')
@app.route('/administracion')
def admin_open_code():
    """Renderiza el panel de administración Open Code con formulario y terminal."""
    if 'user_id' not in session or not session.get('is_admin'):
        flash('Acceso no autorizado', 'danger')
        return redirect(url_for('index'))
    user_id = session.get('user_id')
    unread_count, unread_notifs = get_unread_notifications(user_id)
    return render_template(
        'administracion.html',
        is_admin=True,
        unread_count=unread_count,
        unread_notifs=unread_notifs
    )

@app.route('/api/submit-job', methods=['POST'])
def submit_job():
    """Recibe datos del formulario, genera script SBATCH y ejecuta sbatch."""
    if 'user_id' not in session or not session.get('is_admin'):
        return jsonify({'error': 'No autorizado'}), 401

    data = request.get_json()
    if not data:
        return jsonify({'error': 'Datos JSON requeridos'}), 400

    # Validar campos obligatorios
    required = ['job_name', 'partition', 'nodes', 'ntasks_per_node', 'memory', 'walltime']
    for field in required:
        if field not in data or not str(data[field]).strip():
            return jsonify({'error': f'Campo requerido: {field}'}), 400

    job_name  = str(data['job_name']).strip()
    partition = str(data['partition']).strip()
    nodes     = str(data['nodes']).strip()
    ntasks    = str(data['ntasks_per_node']).strip()
    memory    = str(data['memory']).strip()
    walltime  = str(data['walltime']).strip()
    script_content = data.get('script_content', '').strip()

    # Validar valores numéricos
    try:
        ni = int(nodes); nti = int(ntasks); mi = int(memory)
        if ni < 1 or nti < 1 or mi < 1: raise ValueError
    except ValueError:
        return jsonify({'error': 'Nodos, tareas por nodo y memoria deben ser enteros positivos'}), 400

    # Validar walltime HH:MM:SS
    if not re.match(r'^\d{2}:\d{2}:\d{2}$', walltime):
        return jsonify({'error': 'Walltime debe tener formato HH:MM:SS'}), 400

    # Validar partición (solo alfanumérico + guiones)
    if not re.match(r'^[a-zA-Z0-9_\-]+$', partition):
        return jsonify({'error': 'Partición contiene caracteres no válidos'}), 400

    # Validar nombre del job
    if not re.match(r'^[a-zA-Z0-9_\-.\s]+$', job_name):
        return jsonify({'error': 'Nombre del job contiene caracteres no válidos'}), 400

    # ── Generar script SBATCH de forma segura ──
    sbatch_lines = [
        '#!/bin/bash',
        f'#SBATCH --job-name={shlex.quote(job_name)}',
        f'#SBATCH --partition={shlex.quote(partition)}',
        f'#SBATCH --nodes={ni}',
        f'#SBATCH --ntasks-per-node={nti}',
        f'#SBATCH --mem={mi}M',
        f'#SBATCH --time={shlex.quote(walltime)}',
        '#SBATCH --output=%j.out',
        '#SBATCH --error=%j.err',
        '',
        'echo "Job iniciado en $(hostname) a las $(date)"',
        'echo "SLURM_JOB_ID=$SLURM_JOB_ID"',
        'echo "SLURM_NODELIST=$SLURM_NODELIST"',
        '',
    ]

    if script_content:
        sbatch_lines.append('# === Script del usuario ===')
        sbatch_lines.append(script_content)
    else:
        sbatch_lines.append('# === Comando por defecto ===')
        sbatch_lines.append('echo "No se proporcionó script."')
        sbatch_lines.append('hostname')
        sbatch_lines.append('scontrol show job $SLURM_JOB_ID')

    full_script = '\n'.join(sbatch_lines)

    # Escribir a archivo temporal y ejecutar sbatch
    try:
        with tempfile.NamedTemporaryFile(mode='w', suffix='.sh', delete=False, encoding='utf-8') as f:
            f.write(full_script)
            tmp_path = f.name

        result = subprocess.run(
            ['sbatch', tmp_path],
            capture_output=True, text=True, timeout=30, cwd='/tmp'
        )

        try:
            os.unlink(tmp_path)
        except Exception:
            pass

        if result.returncode != 0:
            return jsonify({'error': f'sbatch falló: {result.stderr.strip()}'}), 500

        m = re.search(r'Submitted batch job (\d+)', result.stdout)
        job_id = m.group(1) if m else 'desconocido'

        return jsonify({
            'success': True,
            'job_id': job_id,
            'message': f'Job {job_name} enviado (ID: {job_id})'
        })

    except subprocess.TimeoutExpired:
        return jsonify({'error': 'sbatch timed out (30s)'}), 504
    except FileNotFoundError:
        return jsonify({'error': 'sbatch no encontrado. ¿Slurm instalado?'}), 500
    except Exception as e:
        return jsonify({'error': f'Error interno: {str(e)}'}), 500


# ── Terminal WebSocket Handlers ──────────────────────────────────────

def _pty_read_loop(sid, master_fd, pid):
    """Hilo lector del PTY → envía salida al cliente vía SocketIO."""
    try:
        while True:
            r, _, _ = select.select([master_fd], [], [], 0.1)
            if r:
                try:
                    out = os.read(master_fd, 4096)
                except OSError:
                    break
                if not out:
                    break
                socketio.emit('terminal:output', {'data': out.decode('utf-8', errors='replace')}, to=sid)
    except Exception:
        pass
    finally:
        _cleanup_terminal(sid)

def _cleanup_terminal(sid):
    """Limpia recursos de una terminal activa."""
    with _active_terminals_lock:
        entry = _active_terminals.pop(sid, None)
    if entry:
        mfd, pid = entry['master_fd'], entry['pid']
        try:
            os.kill(pid, signal.SIGKILL)
        except Exception:
            pass
        try:
            os.close(mfd)
        except Exception:
            pass
        try:
            os.waitpid(pid, 0)
        except Exception:
            pass

@socketio.on('connect')
def ws_connect():
    """Solo admins pueden conectar WebSocket."""
    if 'user_id' not in session or not session.get('is_admin'):
        return False

@socketio.on('terminal:start')
def ws_terminal_start(data):
    """Inicia una sesión de terminal PTY con bash."""
    if not _HAS_PTY:
        emit('terminal:output', {'data': 'Error: PTY no disponible (solo Linux)\n'})
        return

    sid = request.sid
    _cleanup_terminal(sid)

    try:
        cols = max(10, min(200, int(data.get('cols', 80))))
        rows = max(5,  min(100, int(data.get('rows', 24))))
    except (ValueError, TypeError):
        cols, rows = 80, 24

    try:
        mfd, sfd = pty.openpty()

        try:
            fcntl.ioctl(mfd, termios.TIOCSWINSZ, struct.pack('HHHH', rows, cols, 0, 0))
        except Exception:
            pass

        pid = os.fork()
        if pid == 0:
            # ── Hijo ──
            os.close(mfd)
            os.setsid()
            for fd in (0, 1, 2):
                os.dup2(sfd, fd)
            if sfd > 2:
                os.close(sfd)
            try:
                os.chdir(os.environ.get('HOME', '/root'))
            except Exception:
                pass
            os.execve('/bin/bash', ['/bin/bash', '--login'], os.environ)

        # ── Padre ──
        os.close(sfd)

        with _active_terminals_lock:
            _active_terminals[sid] = {'master_fd': mfd, 'pid': pid}

        t = threading.Thread(target=_pty_read_loop, args=(sid, mfd, pid), daemon=True)
        with _active_terminals_lock:
            _active_terminals[sid]['thread'] = t
        t.start()

        emit('terminal:started', {'ok': True})

    except Exception as e:
        emit('terminal:output', {'data': f'Error al iniciar terminal: {str(e)}\n'})

@socketio.on('terminal:input')
def ws_terminal_input(data):
    """Escribe la entrada del usuario al PTY."""
    sid = request.sid
    with _active_terminals_lock:
        entry = _active_terminals.get(sid)
    if entry:
        try:
            os.write(entry['master_fd'], data['data'].encode())
        except Exception:
            _cleanup_terminal(sid)

@socketio.on('terminal:resize')
def ws_terminal_resize(data):
    """Ajusta el tamaño de la terminal PTY."""
    sid = request.sid
    with _active_terminals_lock:
        entry = _active_terminals.get(sid)
    if entry:
        try:
            c = max(10, min(200, int(data.get('cols', 80))))
            r = max(5,  min(100, int(data.get('rows', 24))))
            fcntl.ioctl(entry['master_fd'], termios.TIOCSWINSZ, struct.pack('HHHH', r, c, 0, 0))
        except Exception:
            pass

@socketio.on('disconnect')
def ws_disconnect():
    """Limpia la terminal al desconectarse."""
    _cleanup_terminal(request.sid)


if __name__ == '__main__':
    socketio.run(app, debug=True, port=5000, allow_unsafe_werkzeug=True)
