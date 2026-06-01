# -*- coding: utf-8 -*-
from flask import Flask, render_template, request, redirect, url_for, flash, session, make_response, jsonify
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

# --- Rutas ---

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        correo = request.form.get('correo')
        password = request.form.get('password')
        
        user = Usuario.query.filter_by(correo_electronico=correo).first()
        
        if user and bcrypt.check_password_hash(user.password_hash, password):
            session['user_id'] = user.id_usuario
            session['is_admin'] = user.es_administrador
            session['user_name'] = user.nombre_apellido
            return redirect(url_for('dashboard'))
        
        flash('Credenciales incorrectas', 'danger')
        return redirect(url_for('login'))
    
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return render_template('login.html')
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
            'profesor_tutor': s.profesor_tutor,
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
    
    # Noticias para la columna lateral (Próximos 7 días)
    fecha_limite = (datetime.now() + timedelta(days=7)).date()
    noticias_sidebar = Noticia.query.filter(Noticia.fecha_evento <= fecha_limite, Noticia.fecha_evento >= datetime.now().date()).order_by(Noticia.fecha_evento.asc()).all()

    return render_template('dashboard.html', solicitudes=db_solicitudes, is_admin=is_admin, unread_count=unread_count, unread_notifs=unread_notifs, noticias_sidebar=noticias_sidebar)

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
    solicitud.estado = 'ACEPTADA'
    solicitud.acceso_nodos = True if request.form.get('acceso_nodos') else False
    solicitud.maquina_virtual = True if request.form.get('maquina_virtual') else False
    solicitud.detalles_mv = request.form.get('detalles_mv')
    solicitud.autorizado_por = session.get('user_name')
    
    db.session.commit()

    # Notificar al usuario
    notif = Notificacion(
        id_usuario_destino=solicitud.id_usuario_solicitante,
        mensaje=f"Tu solicitud para '{solicitud.nombre_proyecto}' ha sido ACEPTADA.",
        tipo='ESTADO'
    )
    db.session.add(notif)
    db.session.commit()

    flash(f'Solicitud #{id} aceptada y autorizada', 'success')
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

@app.route('/solicitud/<int:id>/borrar')
def borrar_solicitud(id):
    if 'user_id' not in session or not session.get('is_admin'):
        flash('Acceso no autorizado', 'danger')
        return redirect(url_for('index'))
    
    solicitud = Solicitud.query.get_or_404(id)
    db.session.delete(solicitud)
    db.session.commit()
    flash(f'Solicitud #{id} eliminada permanentemente', 'info')
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
    response.headers['Content-Disposition'] = f'attachment; filename=solicitud_{s.id_solicitud}.pdf'
    return response

@app.route('/proyectos')
def proyectos():
    if 'user_id' not in session:
        return redirect(url_for('index'))
    
    is_admin = session.get('is_admin', False)
    
    # Obtener proyectos reales (solicitudes aceptadas)
    accepted_solicitudes = Solicitud.query.filter_by(estado='ACEPTADA').all()
    db_proyectos = []
    for s in accepted_solicitudes:
        # Lógica de finalización automática basada en la fecha
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

@app.route('/analisis-predictivo', methods=['GET', 'POST'])
def analisis_predictivo():
    if 'user_id' not in session:
        return redirect(url_for('index'))

    is_admin = session.get('is_admin', False)
    user = Usuario.query.get(session['user_id'])
    ssh_config = get_user_ssh_config(user.correo_electronico) if user else None

    recursos_data = {
        'nodos': [
            {'nombre': 'nodo-01', 'cpu_uso': 0, 'ram_uso': 0, 'estado': 'Offline'},
            {'nombre': 'nodo-02', 'cpu_uso': 0, 'ram_uso': 0, 'estado': 'Offline'},
            {'nombre': 'nodo-03', 'cpu_uso': 0, 'ram_uso': 0, 'estado': 'Offline'},
            {'nombre': 'nodo-gpu-01', 'cpu_uso': 0, 'ram_uso': 0, 'estado': 'Offline'}
        ],
        'total_cpu': 64, 'uso_cpu': 32,
        'total_ram': 128, 'uso_ram': 64,
        'total_gpu': 4, 'uso_gpu': 1
    }

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
            stdin, stdout, stderr = ssh.exec_command("top -bn1 | grep 'Cpu(s)' | awk '{print $2}'", timeout=10)
            cpu_str = stdout.read().decode().strip()
            uso_cpu_porcentaje = float(cpu_str) if cpu_str else 0
            stdin, stdout, stderr = ssh.exec_command("free -m | awk 'NR==2{print $3, $2}'", timeout=10)
            ram_line = stdout.read().decode().strip().split()
            uso_ram = int(ram_line[0]) if len(ram_line) > 0 else 0
            total_ram = int(ram_line[1]) if len(ram_line) > 1 else 1
            stdin, stdout, stderr = ssh.exec_command("nproc", timeout=10)
            total_cpu = int(stdout.read().decode().strip() or 1)
            stdin, stdout, stderr = ssh.exec_command("hostname", timeout=10)
            hostname = stdout.read().decode().strip()
            ssh.close()

            for nodo in recursos_data['nodos']:
                if nodo['nombre'] == f'nodo-{hostname[-2:]}' or nodo['nombre'] == hostname:
                    nodo['cpu_uso'] = int(uso_cpu_porcentaje)
                    nodo['ram_uso'] = int(uso_ram / max(total_ram, 1) * 100)
                    nodo['estado'] = 'Online'
                    break
            else:
                recursos_data['nodos'][0]['cpu_uso'] = int(uso_cpu_porcentaje)
                recursos_data['nodos'][0]['ram_uso'] = int(uso_ram / max(total_ram, 1) * 100)
                recursos_data['nodos'][0]['estado'] = 'Online'

            recursos_data['total_cpu'] = total_cpu
            recursos_data['uso_cpu'] = int(total_cpu * uso_cpu_porcentaje / 100)
            recursos_data['total_ram'] = total_ram
            recursos_data['uso_ram'] = uso_ram
            recursos_data['total_gpu'] = 4
            recursos_data['uso_gpu'] = 1
        except Exception:
            pass

    tasa = request.form.get('tasa', 5, type=float)
    meses = request.form.get('meses', 12, type=int)
    puertos = request.form.get('puertos', 24, type=int)

    cpu_total = recursos_data['total_cpu']
    cpu_uso = recursos_data['uso_cpu']
    ram_total = recursos_data['total_ram']
    ram_uso = recursos_data['uso_ram']
    gpu_total = recursos_data['total_gpu']
    gpu_uso = recursos_data['uso_gpu']

    cpu_pct = (cpu_uso / cpu_total * 100) if cpu_total else 0
    ram_pct = (ram_uso / ram_total * 100) if ram_total else 0
    gpu_pct = (gpu_uso / gpu_total * 100) if gpu_total else 0

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

    num_nodos = len(recursos_data['nodos'])
    cpu_por_nodo = max(1, cpu_total // max(num_nodos, 1))
    ram_por_nodo = max(1, ram_total // max(num_nodos, 1))
    num_nodos_gpu = max(1, sum(1 for n in recursos_data['nodos'] if 'gpu' in n['nombre']))
    gpu_por_nodo = max(1, gpu_total // num_nodos_gpu) if gpu_total > 0 else 0

    factor_12m = growth_factor ** min(meses, 12)
    cpu_deficit = max(0, cpu_uso * factor_12m - cpu_total)
    ram_deficit = max(0, ram_uso * factor_12m - ram_total)
    gpu_deficit = max(0, gpu_uso * factor_12m - gpu_total)

    nodos_cpu = math.ceil(cpu_deficit / cpu_por_nodo) if cpu_por_nodo > 0 else 0
    nodos_ram = math.ceil(ram_deficit / ram_por_nodo) if ram_por_nodo > 0 else 0
    nodos_gpu = math.ceil(gpu_deficit / gpu_por_nodo) if gpu_por_nodo > 0 else 0
    total_nuevos = max(nodos_cpu, nodos_ram, nodos_gpu)
    total_final = num_nodos + total_nuevos

    necesita_switch = total_final > puertos
    switches_req = max(1, math.ceil(total_final / puertos))
    puertos_libres = switches_req * puertos - total_final

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
    }

    user_id = session.get('user_id')
    unread_count, unread_notifs = get_unread_notifications(user_id)
    return render_template('analisis_predictivo.html', is_admin=is_admin, prediccion=prediccion, unread_count=unread_count, unread_notifs=unread_notifs)


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
    resp = make_response(redirect(url_for('index')))
    resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    resp.headers['Pragma'] = 'no-cache'
    resp.headers['Expires'] = '0'
    session.clear()
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
    app.run(debug=True, host='0.0.0.0', port=5000)
