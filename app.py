# -*- coding: utf-8 -*-
from flask import Flask, render_template, request, redirect, url_for, flash, session
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
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://postgres:123@localhost/CLUSTER_NIDTEC'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

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
    return render_template('solicitud.html', 
                         now=datetime.now(), 
                         user_email=user.correo_electronico,
                         is_admin=session.get('is_admin', False))

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

    return render_template('proyectos.html', is_admin=is_admin, proyectos=db_proyectos)

@app.route('/recursos')
def recursos():
    if 'user_id' not in session:
        return redirect(url_for('index'))
    
    is_admin = session.get('is_admin', False)
    # Valores fijos de prueba
    recursos_data = {
        'nodos': [
            {'nombre': 'nodo-01', 'cpu_uso': 45, 'ram_uso': 60, 'estado': 'Online'},
            {'nombre': 'nodo-02', 'cpu_uso': 80, 'ram_uso': 85, 'estado': 'Online'},
            {'nombre': 'nodo-03', 'cpu_uso': 10, 'ram_uso': 15, 'estado': 'Online'},
            {'nombre': 'nodo-gpu-01', 'cpu_uso': 30, 'ram_uso': 40, 'estado': 'Online'}
        ],
        'total_cpu': 64,
        'uso_cpu': 38,
        'total_ram': 256,
        'uso_ram': 128,
        'total_gpu': 4,
        'uso_gpu': 1
    }
    return render_template('recursos.html', is_admin=is_admin, recursos=recursos_data)

@app.route('/terminal')
def terminal():
    if 'user_id' not in session:
        return redirect(url_for('index'))
    is_admin = session.get('is_admin', False)
    return render_template('terminal.html', is_admin=is_admin)

@app.route('/perfil')
def perfil():
    if 'user_id' not in session:
        return redirect(url_for('login'))
        
    user = Usuario.query.get(session['user_id'])
    is_admin = session.get('is_admin', False)
    
    return render_template('perfil.html', user=user, is_admin=is_admin)

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
    
    return render_template('usuarios.html', usuarios=db_usuarios, is_admin=True)

@app.route('/promover/<int:id>')
def promover_usuario(id):
    if 'user_id' not in session or not session.get('is_admin'):
        flash('Acceso no autorizado', 'danger')
        return redirect(url_for('index'))
    
    user = Usuario.query.get_or_404(id)
    user.es_administrador = True
    db.session.commit()
    flash(f'Usuario {user.nombre_apellido} promovido a administrador', 'success')
    return redirect(request.referrer or url_for('dashboard'))

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
    user.es_administrador = False
    db.session.commit()
    flash(f'Rol de administrador removido para {user.nombre_apellido}', 'info')
    return redirect(request.referrer or url_for('dashboard'))

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

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

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
