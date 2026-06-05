-- Esquema COMPLETO de CLUSTER_NIDTEC

-- --- Tabla: administradores ---
CREATE TABLE IF NOT EXISTS administradores (
    id_administrador SERIAL NOT NULL,
    id_usuario INTEGER NOT NULL,
    perfil_administrador CHARACTER VARYING(255)
);

-- --- Tabla: usuarios ---
CREATE TABLE IF NOT EXISTS usuarios (
    id_usuario SERIAL NOT NULL,
    nombre_apellido CHARACTER VARYING(255) NOT NULL,
    correo_electronico CHARACTER VARYING(255) NOT NULL,
    es_administrador BOOLEAN DEFAULT false,
    password_hash CHARACTER VARYING(255) NOT NULL,
    foto_perfil CHARACTER VARYING(255)
);

-- --- Tabla: solicitudes_aprobadas ---
CREATE TABLE IF NOT EXISTS solicitudes_aprobadas (
    id_solicitud_aprobada SERIAL NOT NULL,
    id_solicitud_origen INTEGER NOT NULL,
    fecha_aprobacion TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    resolucion_numero CHARACTER VARYING(50),
    estado_aprobacion CHARACTER VARYING(20) DEFAULT 'PROCESADA'::character varying
);

-- --- Tabla: proyectos ---
CREATE TABLE IF NOT EXISTS proyectos (
    id_proyecto SERIAL NOT NULL,
    id_solicitud_aprobada INTEGER NOT NULL,
    id_administrador_autorizante INTEGER NOT NULL,
    usuario_sistema_creado CHARACTER VARYING(100),
    acceso_nodos_fisicos BOOLEAN DEFAULT false,
    requiere_maquina_virtual BOOLEAN DEFAULT false,
    observaciones TEXT
);

-- --- Tabla: recursos ---
CREATE TABLE IF NOT EXISTS recursos (
    id_recurso SERIAL NOT NULL,
    id_proyecto INTEGER NOT NULL,
    tipo_caracteristica CHARACTER VARYING(100) NOT NULL,
    valor CHARACTER VARYING(100) NOT NULL
);

-- --- Tabla: solicitudes ---
CREATE TABLE IF NOT EXISTS solicitudes (
    id_solicitud SERIAL NOT NULL,
    id_usuario_solicitante INTEGER NOT NULL,
    fecha_solicitud TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    facultad CHARACTER VARYING(255) NOT NULL,
    carrera CHARACTER VARYING(255) NOT NULL,
    asignatura_modulo CHARACTER VARYING(255),
    profesor_tutor CHARACTER VARYING(255) NOT NULL,
    fecha_inicio DATE NOT NULL,
    fecha_finalizacion_estimada DATE NOT NULL,
    nombre_proyecto CHARACTER VARYING(255) NOT NULL,
    software_requerido TEXT,
    estado CHARACTER VARYING(20) DEFAULT 'PENDIENTE'::character varying,
    observaciones TEXT,
    acceso_nodos BOOLEAN DEFAULT false,
    maquina_virtual BOOLEAN DEFAULT false,
    detalles_mv TEXT,
    autorizado_por CHARACTER VARYING(255),
    nombre_solicitante CHARACTER VARYING(255),
    correo_solicitante CHARACTER VARYING(255)
);

-- --- Tabla: notificaciones ---
CREATE TABLE IF NOT EXISTS notificaciones (
    id_notificacion SERIAL NOT NULL,
    id_usuario_destino INTEGER NOT NULL,
    mensaje CHARACTER VARYING(500) NOT NULL,
    fecha TIMESTAMP WITHOUT TIME ZONE,
    leida BOOLEAN,
    tipo CHARACTER VARYING(50)
);

-- --- Tabla: noticias ---
CREATE TABLE IF NOT EXISTS noticias (
    id_noticia SERIAL NOT NULL,
    titulo CHARACTER VARYING(255) NOT NULL,
    descripcion TEXT NOT NULL,
    fecha_creacion TIMESTAMP WITHOUT TIME ZONE,
    fecha_evento DATE,
    autor_id INTEGER
);

