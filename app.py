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
from werkzeug.utils import secure_filename

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
    acceso_nodos = db.Column(db.Boolean, default=False)
    maquina_virtual = db.Column(db.Boolean, default=False)
    detalles_mv = db.Column(db.Text)
    autorizado_por = db.Column(db.String(255))
    nombre_solicitante = db.Column(db.String(255))
    correo_solicitante = db.Column(db.String(255))
    
    usuario = db.relationship('Usuario', backref='solicitudes')

    def __init__(self, id_usuario_solicitante, facultad, carrera, nombre_proyecto, asignatura_modulo, profesor_tutor, software_requerido, fecha_inicio, fecha_finalizacion_estimada, observaciones, fecha_solicitud, nombre_solicitante, correo_solicitante, estado='PENDIENTE'):
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
                estado='PENDIENTE'
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
    
    # Encabezado
    pdf.set_fill_color(*azul)
    pdf.rect(0, 0, 210, 35, 'F')
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

@app.route('/analisis-predictivo', methods=['GET', 'POST'])
def analisis_predictivo():
    # 1. Verificar si el usuario está logueado
    if 'user_id' not in session:
        return redirect(url_for('index'))

    # 2. Control de Acceso: Verificar si es Admin por rol o por correo específico
    is_admin = session.get('is_admin', False)
    user = Usuario.query.get(session['user_id'])

    if not is_admin and (user and user.correo_electronico != 'admin@nidtec.com'):
        abort(403)  # Lanza un error HTTP 403 Prohibido

    # 3. Inicialización y simulación de la infraestructura base (Nodos C1 a C4)
    # Especificaciones físicas del hardware:
    # 4 nodos: C1, C2, C3 (compartidos) y C4 (exclusivo)
    # Memoria: 128 GB c/u, Cores: 32 c/u, GPU: 1 c/u
    cpu_por_nodo = 32
    ram_por_nodo = 128
    gpu_por_nodo = 1
    num_nodos = 4

    # Estado de trabajos activos simulados en el clúster (para simulación de colas/backfill)
    trabajos_activos = [
        {'id': 101, 'usuario': 'lgarcia', 'nodo': 'C1', 'cpu': 12, 'ram': 48, 'gpu': 0, 'tiempo_restante': '00:15:00', 'min_restantes': 15},
        {'id': 102, 'usuario': 'mbenitez', 'nodo': 'C1', 'cpu': 8, 'ram': 32, 'gpu': 0, 'tiempo_restante': '00:45:00', 'min_restantes': 45},
        {'id': 103, 'usuario': 'jduarte', 'nodo': 'C2', 'cpu': 24, 'ram': 96, 'gpu': 1, 'tiempo_restante': '01:30:00', 'min_restantes': 90},
        {'id': 104, 'usuario': 'arojas', 'nodo': 'C3', 'cpu': 8, 'ram': 16, 'gpu': 0, 'tiempo_restante': '00:10:00', 'min_restantes': 10},
        {'id': 105, 'usuario': 'fnoguera', 'nodo': 'C4', 'cpu': 16, 'ram': 64, 'gpu': 1, 'tiempo_restante': '02:15:00', 'min_restantes': 135, 'exclusivo': True}
    ]

    # Crear lista de nodos y calcular su uso
    nodos_list = [
        {'nombre': 'C1', 'tipo': 'compartido', 'cpu_total': 32, 'ram_total': 128, 'gpu_total': 1, 'cpu_uso': 0, 'ram_uso': 0, 'gpu_uso': 0, 'estado': 'Online', 'trabajos': [], 'exclusivo_ocupado': False},
        {'nombre': 'C2', 'tipo': 'compartido', 'cpu_total': 32, 'ram_total': 128, 'gpu_total': 1, 'cpu_uso': 0, 'ram_uso': 0, 'gpu_uso': 0, 'estado': 'Online', 'trabajos': [], 'exclusivo_ocupado': False},
        {'nombre': 'C3', 'tipo': 'compartido', 'cpu_total': 32, 'ram_total': 128, 'gpu_total': 1, 'cpu_uso': 0, 'ram_uso': 0, 'gpu_uso': 0, 'estado': 'Online', 'trabajos': [], 'exclusivo_ocupado': False},
        {'nombre': 'C4', 'tipo': 'exclusivo', 'cpu_total': 32, 'ram_total': 128, 'gpu_total': 1, 'cpu_uso': 0, 'ram_uso': 0, 'gpu_uso': 0, 'estado': 'Online', 'trabajos': [], 'exclusivo_ocupado': False}
    ]

    for job in trabajos_activos:
        for nodo in nodos_list:
            if nodo['nombre'] == job['nodo']:
                nodo['trabajos'].append(job)
                nodo['cpu_uso'] += job['cpu']
                nodo['ram_uso'] += job['ram']
                nodo['gpu_uso'] += job['gpu']
                if job.get('exclusivo'):
                    nodo['exclusivo_ocupado'] = True

    # Calcular recursos disponibles para asignación de SLURM (teniendo en cuenta la exclusividad)
    for n in nodos_list:
        if n['exclusivo_ocupado']:
            n['cpu_disp'] = 0
            n['ram_disp'] = 0
            n['gpu_disp'] = 0
        else:
            n['cpu_disp'] = n['cpu_total'] - n['cpu_uso']
            n['ram_disp'] = n['ram_total'] - n['ram_uso']
            n['gpu_disp'] = n['gpu_total'] - n['gpu_uso']

    # Totales para uso general
    cpu_total = sum(n['cpu_total'] for n in nodos_list)
    cpu_uso = sum(n['cpu_uso'] for n in nodos_list)
    ram_total = sum(n['ram_total'] for n in nodos_list)
    ram_uso = sum(n['ram_uso'] for n in nodos_list)
    gpu_total = sum(n['gpu_total'] for n in nodos_list)
    gpu_uso = sum(n['gpu_uso'] for n in nodos_list)

    # 4. Conexión SSH opcional
    ssh_config = get_user_ssh_config(user.correo_electronico) if user else None
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
            
            # Obtener datos del servidor
            stdin, stdout, stderr = ssh.exec_command("top -bn1 | grep 'Cpu(s)' | awk '{print $2}'", timeout=10)
            cpu_str = stdout.read().decode().strip()
            uso_cpu_porcentaje = float(cpu_str) if cpu_str else 0
            
            stdin, stdout, stderr = ssh.exec_command("free -m | awk 'NR==2{print $3, $2}'", timeout=10)
            ram_line = stdout.read().decode().strip().split()
            uso_ram_val = int(ram_line[0]) if len(ram_line) > 0 else 0
            total_ram_val = int(ram_line[1]) if len(ram_line) > 1 else 1
            
            stdin, stdout, stderr = ssh.exec_command("hostname", timeout=10)
            hostname = stdout.read().decode().strip()
            ssh.close()

            # Si SSH responde, mapeamos su carga al primer nodo compartido y recalculamos totales
            # para no romper el modelo lógico del simulador
            for nodo in nodos_list:
                if nodo['nombre'].lower() == hostname.lower() or hostname[-2:] in nodo['nombre']:
                    nodo['cpu_uso'] = int(nodo['cpu_total'] * uso_cpu_porcentaje / 100)
                    nodo['ram_uso'] = int(nodo['ram_total'] * (uso_ram_val / total_ram_val))
                    nodo['cpu_disp'] = max(0, nodo['cpu_total'] - nodo['cpu_uso'])
                    nodo['ram_disp'] = max(0, nodo['ram_total'] - nodo['ram_uso'])
                    break
            else:
                nodos_list[0]['cpu_uso'] = int(nodos_list[0]['cpu_total'] * uso_cpu_porcentaje / 100)
                nodos_list[0]['ram_uso'] = int(nodos_list[0]['ram_total'] * (uso_ram_val / total_ram_val))
                nodos_list[0]['cpu_disp'] = max(0, nodos_list[0]['cpu_total'] - nodos_list[0]['cpu_uso'])
                nodos_list[0]['ram_disp'] = max(0, nodos_list[0]['ram_total'] - nodos_list[0]['ram_uso'])

            # Recalcular totales generales
            cpu_uso = sum(n['cpu_uso'] for n in nodos_list)
            ram_uso = sum(n['ram_uso'] for n in nodos_list)
        except Exception:
            pass

    # 5. Parámetros del formulario
    tasa = request.form.get('tasa', 5, type=float)
    meses = request.form.get('meses', 12, type=int)
    puertos = request.form.get('puertos', 24, type=int)

    cpu_pct = (cpu_uso / cpu_total * 100) if cpu_total else 0
    ram_pct = (ram_uso / ram_total * 100) if ram_total else 0
    gpu_pct = (gpu_uso / gpu_total * 100) if gpu_total else 0

    # 6. Cálculo de Proyecciones de Crecimiento
    growth_factor = 1 + (tasa / 100)
    proyecciones = []
    for mes in range(1, meses + 1):
        factor = growth_factor ** mes
        cpu_proj = cpu_uso * factor
        ram_proj = ram_uso * factor
        gpu_proj = gpu_uso * factor
        proyecciones.append({
            'mes': mes,
            'fecha': (datetime.now().replace(day=1) + timedelta(days=30 * mes)).strftime('%Y-%m'),
            'cpu_uso': round(cpu_proj, 1),
            'cpu_pct': min(round(cpu_proj / cpu_total * 100, 1) if cpu_total else 0, 100),
            'ram_uso': round(ram_proj, 1),
            'ram_pct': min(round(ram_proj / ram_total * 100, 1) if ram_total else 0, 100),
            'gpu_uso': round(gpu_proj, 1),
            'gpu_pct': min(round(gpu_proj / gpu_total * 100, 1) if gpu_total else 0, 100),
        })

    mes_agotar_cpu = next((p['mes'] for p in proyecciones if p['cpu_pct'] >= 100), None)
    mes_agotar_ram = next((p['mes'] for p in proyecciones if p['ram_pct'] >= 100), None)
    mes_agotar_gpu = next((p['mes'] for p in proyecciones if p['gpu_pct'] >= 100), None)

    # 7. Planificación de Equipos y Switch
    factor_12m = growth_factor ** min(meses, 12)
    cpu_deficit = max(0, cpu_uso * factor_12m - cpu_total)
    ram_deficit = max(0, ram_uso * factor_12m - ram_total)
    gpu_deficit = max(0, gpu_uso * factor_12m - gpu_total)

    nodos_cpu = math.ceil(cpu_deficit / cpu_por_nodo)
    nodos_ram = math.ceil(ram_deficit / ram_por_nodo)
    nodos_gpu = math.ceil(gpu_deficit / gpu_por_nodo)
    total_nuevos = max(nodos_cpu, nodos_ram, nodos_gpu)
    total_final = num_nodos + total_nuevos

    necesita_switch = total_final > puertos
    switches_req = max(1, math.ceil(total_final / puertos))
    puertos_libres = switches_req * puertos - total_final

    # --- [8. SIMULACIÓN DE ESTIMACIÓN DE PLANIFICACIÓN SLURM ADVANCED] ---
    req_cpu = request.form.get('req_cpu', 0, type=int)
    req_ram = request.form.get('req_ram', 0, type=int)
    req_gpu = request.form.get('req_gpu', 0, type=int)
    req_exclusivo = request.form.get('req_exclusivo', 'false') == 'true'
    req_mpi = request.form.get('req_mpi', 'false') == 'true'
    req_time = request.form.get('req_time', 2, type=int)

    slurm_estado = 'ejecucion_inmediata'
    slurm_motivo = ''
    slurm_nodo_sugerido = 'Ninguno'
    slurm_tiempo_espera = None
    slurm_error_code = 'STATUS: IDLE'

    # Validar si hay solicitud activa
    if req_cpu > 0 or req_ram > 0 or req_gpu > 0:
        if req_exclusivo:
            # Destinado a C4
            if req_cpu > cpu_por_nodo or req_ram > ram_por_nodo or req_gpu > gpu_por_nodo:
                slurm_estado = 'sin_recursos'
                slurm_motivo = (
                    f"La solicitud excede la capacidad física del nodo exclusivo C4 "
                    f"(Límites C4: {cpu_por_nodo} Cores, {ram_por_nodo} GB RAM, {gpu_por_nodo} GPU). "
                    f"Código SLURM: REASON_CAPACITY (PartitionNodeLimit)."
                )
                slurm_error_code = "FAILED (PartitionNodeLimit)"
            else:
                # Verificar si C4 está ocupado
                c4 = next(n for n in nodos_list if n['nombre'] == 'C4')
                if c4['exclusivo_ocupado']:
                    slurm_estado = 'en_cola'
                    # Obtener tiempo restante del trabajo en C4 (Job #105)
                    job_c4 = next(j for j in trabajos_activos if j['nodo'] == 'C4')
                    slurm_tiempo_espera = job_c4['tiempo_restante']
                    slurm_nodo_sugerido = "C4 (Exclusivo)"
                    slurm_motivo = (
                        f"El nodo exclusivo C4 está actualmente ocupado por el trabajo #{job_c4['id']} "
                        f"del usuario '{job_c4['usuario']}'. El trabajo debe esperar en la cola de la partición exclusiva."
                    )
                    slurm_error_code = "PENDING (Resources: NodeOccupied)"
                else:
                    slurm_estado = 'ejecucion_inmediata'
                    slurm_nodo_sugerido = "C4"
                    slurm_motivo = "Nodo exclusivo C4 disponible. Ejecución inmediata asignada."
                    slurm_error_code = "RUNNING (Allocated: C4)"
        else:
            # Destinado a partición compartida C1-C3
            if not req_mpi:
                # Mono-nodo: Debe caber en un único nodo compartido
                if req_cpu > cpu_por_nodo or req_ram > ram_por_nodo or req_gpu > gpu_por_nodo:
                    slurm_estado = 'sin_recursos'
                    slurm_motivo = (
                        f"La tarea excede el tamaño máximo para ejecución Mono-nodo "
                        f"({cpu_por_nodo} Cores, {ram_por_nodo} GB RAM, {gpu_por_nodo} GPU). "
                        f"Para ejecutar trabajos que superen estos límites, active la casilla 'Trabajo Multi-nodo (MPI)'."
                    )
                    slurm_error_code = "FAILED (PartitionNodeLimit)"
                else:
                    # Buscar nodo disponible
                    nodo_asignado = None
                    for n in nodos_list:
                        if n['tipo'] == 'compartido' and n['cpu_disp'] >= req_cpu and n['ram_disp'] >= req_ram and n['gpu_disp'] >= req_gpu:
                            nodo_asignado = n['nombre']
                            break
                    
                    if nodo_asignado:
                        slurm_estado = 'ejecucion_inmediata'
                        slurm_nodo_sugerido = nodo_asignado
                        slurm_motivo = f"Recursos concedidos en el nodo compartido {nodo_asignado} para ejecución inmediata."
                        slurm_error_code = f"RUNNING (Allocated: {nodo_asignado})"
                    else:
                        # No cabe en ningún nodo individual libre en este momento.
                        # Verificar si la suma total de recursos libres en C1-C3 es suficiente
                        total_cpu_disp_shared = sum(n['cpu_disp'] for n in nodos_list if n['tipo'] == 'compartido')
                        total_ram_disp_shared = sum(n['ram_disp'] for n in nodos_list if n['tipo'] == 'compartido')
                        total_gpu_disp_shared = sum(n['gpu_disp'] for n in nodos_list if n['tipo'] == 'compartido')
                        
                        slurm_estado = 'en_cola'
                        slurm_nodo_sugerido = "C1, C2 o C3 (Compartidos)"
                        
                        if total_cpu_disp_shared >= req_cpu and total_ram_disp_shared >= req_ram and total_gpu_disp_shared >= req_gpu:
                            # Fragmentación!
                            slurm_motivo = (
                                "El trabajo está en espera debido a FRAGMENTACIÓN de recursos. "
                                "Hay suficientes recursos libres en total, pero están divididos en diferentes nodos. "
                                "Dado que la tarea es Mono-nodo, debe esperar a que un nodo libre acumule la capacidad requerida."
                            )
                            slurm_error_code = "PENDING (Resources: Fragmentation)"
                        else:
                            slurm_motivo = (
                                "Recursos insuficientes en la partición compartida. "
                                "El trabajo queda en espera en la cola principal de SLURM."
                            )
                            slurm_error_code = "PENDING (Resources)"
                        
                        # Determinar tiempo de espera estimado basándose en los trabajos activos
                        if req_cpu <= 12:
                            slurm_tiempo_espera = "00:05:00"
                        elif req_cpu <= 24:
                            slurm_tiempo_espera = "00:10:00"
                        else:
                            slurm_tiempo_espera = "00:15:00"
            else:
                # Trabajo Multi-nodo (MPI)
                total_cpu_shared = sum(n['cpu_total'] for n in nodos_list if n['tipo'] == 'compartido')
                total_ram_shared = sum(n['ram_total'] for n in nodos_list if n['tipo'] == 'compartido')
                total_gpu_shared = sum(n['gpu_total'] for n in nodos_list if n['tipo'] == 'compartido')
                
                if req_cpu > total_cpu_shared or req_ram > total_ram_shared or req_gpu > total_gpu_shared:
                    slurm_estado = 'sin_recursos'
                    slurm_motivo = (
                        f"La solicitud MPI excede los límites físicos acumulados de la partición compartida "
                        f"({total_cpu_shared} Cores, {total_ram_shared} GB RAM, {total_gpu_shared} GPUs)."
                    )
                    slurm_error_code = "FAILED (PartitionLimit)"
                else:
                    # Evaluar si cabe en la suma total libre de C1-C3
                    total_cpu_disp = sum(n['cpu_disp'] for n in nodos_list if n['tipo'] == 'compartido')
                    total_ram_disp = sum(n['ram_disp'] for n in nodos_list if n['tipo'] == 'compartido')
                    total_gpu_disp = sum(n['gpu_disp'] for n in nodos_list if n['tipo'] == 'compartido')
                    
                    if req_cpu <= total_cpu_disp and req_ram <= total_ram_disp and req_gpu <= total_gpu_disp:
                        slurm_estado = 'ejecucion_inmediata'
                        nodos_sug = [n['nombre'] for n in nodos_list if n['tipo'] == 'compartido' and n['cpu_disp'] > 0]
                        slurm_nodo_sugerido = ", ".join(nodos_sug) + " (Distribuido)"
                        slurm_motivo = "Ejecución MPI distribuida aprobada en nodos compartidos con capacidad ociosa."
                        slurm_error_code = "RUNNING (MPI_Allocated)"
                    else:
                        slurm_estado = 'en_cola'
                        slurm_nodo_sugerido = "C1, C2, C3 (MPI)"
                        slurm_motivo = (
                            "La partición compartida no tiene suficientes recursos libres acumulados en este momento. "
                            "El trabajo MPI está esperando en la cola."
                        )
                        slurm_error_code = "PENDING (Resources: MPI)"
                        slurm_tiempo_espera = "00:15:00"

    # Generar curvas para el gráfico de estimación de colas y backfill de SLURM
    curva_mono_cpu = [1, 4, 8, 12, 16, 20, 24, 28, 32]
    curva_mono_wait = []
    for c in curva_mono_cpu:
        if c <= 12:
            curva_mono_wait.append(0)
        elif c <= 24:
            curva_mono_wait.append(0)
        elif c <= 28:
            curva_mono_wait.append(10)
        else:
            curva_mono_wait.append(10)

    curva_mpi_cpu = [4, 8, 16, 24, 32, 40, 48, 64, 80, 96]
    curva_mpi_wait = []
    for c in curva_mpi_cpu:
        if c <= 44:
            curva_mpi_wait.append(0)
        elif c <= 52:
            curva_mpi_wait.append(10)
        elif c <= 64:
            curva_mpi_wait.append(15)
        elif c <= 72:
            curva_mpi_wait.append(45)
        else:
            curva_mpi_wait.append(90)

    # Calcular fragmentación de CPUs en la partición compartida
    total_cpu_shared_disp = sum(n['cpu_disp'] for n in nodos_list if n['tipo'] == 'compartido')
    max_cpu_block = max(n['cpu_disp'] for n in nodos_list if n['tipo'] == 'compartido')
    fragmentacion_pct = round((1 - (max_cpu_block / total_cpu_shared_disp)) * 100, 1) if total_cpu_shared_disp else 0

    # 9. Estructurar el diccionario unificado final para Jinja2
    prediccion = {
        'proyecciones': proyecciones,
        'agotamiento': {
            'cpu': mes_agotar_cpu,
            'ram': mes_agotar_ram,
            'gpu': mes_agotar_gpu,
        },
        'equipos': {
            'cpu_por_nodo': cpu_por_nodo,
            'ram_por_nodo': ram_por_nodo,
            'gpu_por_nodo': gpu_por_nodo,
            'nodos_cpu': nodos_cpu,
            'nodos_ram': nodos_ram,
            'nodos_gpu': nodos_gpu,
            'total_nuevos': total_nuevos,
        },
        'switch': {
            'puertos_switch': puertos,
            'nodos_actuales': num_nodos,
            'total_final': total_final,
            'necesita_switch': necesita_switch,
            'switches_necesarios': switches_req,
            'puertos_libres': puertos_libres,
        },
        'uso_actual': {
            'cpu_pct': round(cpu_pct, 1),
            'ram_pct': round(ram_pct, 1),
            'gpu_pct': round(gpu_pct, 1),
            'cpu_uso': cpu_uso,
            'cpu_total': cpu_total,
            'ram_uso': ram_uso,
            'ram_total': ram_total,
            'gpu_uso': gpu_uso,
            'gpu_total': gpu_total,
        },
        'tasa': tasa,
        'meses': meses,
        'nodos': nodos_list,
        'fragmentacion_pct': fragmentacion_pct,
        'slurm': {
            'estado': slurm_estado,
            'motivo': slurm_motivo,
            'nodo_sugerido': slurm_nodo_sugerido,
            'tiempo_espera': slurm_tiempo_espera,
            'error_code': slurm_error_code,
            'req_cpu': req_cpu,
            'req_ram': req_ram,
            'req_gpu': req_gpu,
            'req_exclusivo': req_exclusivo,
            'req_mpi': req_mpi,
            'req_time': req_time,
            'curva_mono_cpu': curva_mono_cpu,
            'curva_mono_wait': curva_mono_wait,
            'curva_mpi_cpu': curva_mpi_cpu,
            'curva_mpi_wait': curva_mpi_wait
        }
    }

    user_id = session.get('user_id')
    unread_count, unread_notifs = get_unread_notifications(user_id)
    return render_template(
        'analisis_predictivo.html', 
        is_admin=is_admin, 
        prediccion=prediccion, 
        unread_count=unread_count, 
        unread_notifs=unread_notifs
    )

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
def inject_notifications():
    if 'user_id' in session:
        notifs = Notificacion.query.filter_by(id_usuario_destino=session['user_id'], leida=False).order_by(Notificacion.fecha.desc()).limit(5).all()
        count = Notificacion.query.filter_by(id_usuario_destino=session['user_id'], leida=False).count()
        return dict(unread_notifs=notifs, unread_count=count)
    return dict(unread_notifs=[], unread_count=0)


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

if __name__ == '__main__':
    app.run(debug=True, port=5000)
