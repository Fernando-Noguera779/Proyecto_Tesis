from PIL import Image, ImageDraw, ImageFont
import os

W, H = 1600, 1100
img = Image.new('RGB', (W, H), (15, 23, 42))
draw = ImageDraw.Draw(img)

# Colors
AZUL = (26, 54, 104)
AZUL_CLARO = (60, 100, 170)
VERDE = (16, 185, 129)
ROJO = (239, 68, 68)
AMARILLO = (245, 158, 11)
GRIS = (100, 116, 139)
GRIS_CLARO = (200, 210, 220)
BLANCO = (255, 255, 255)
FONDO_CARD = (30, 41, 59)

try:
    font_title = ImageFont.truetype("arial.ttf", 32)
    font_h2 = ImageFont.truetype("arial.ttf", 22)
    font_h3 = ImageFont.truetype("arial.ttf", 16)
    font_body = ImageFont.truetype("arial.ttf", 13)
    font_small = ImageFont.truetype("arial.ttf", 11)
except:
    font_title = ImageFont.load_default()
    font_h2 = font_title
    font_h3 = font_title
    font_body = font_title
    font_small = font_title

def card(x, y, w, h, color_card=FONDO_CARD, border_color=AZUL_CLARO):
    draw.rounded_rectangle([x, y, x+w, y+h], radius=12, fill=color_card, outline=border_color, width=1)

def card_header(x, y, w, h, color):
    draw.rounded_rectangle([x, y, x+w, y+h], radius=12, fill=color)
    draw.rounded_rectangle([x, y+h-2, x+w, y+h], radius=[0,0,12,12], fill=color)

def center_text(text, font, color, y, x_center=W//2):
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    draw.text((x_center - tw//2, y), text, fill=color, font=font)

# ─── Header ───
draw.rectangle([0, 0, W, 70], fill=AZUL)
center_text("FNOGUERA CLUSTER — Sistema de Gestión", font_title, BLANCO, 18)
center_text("Núcleo de Investigación y Desarrollo Tecnológico · Facultad Politécnica UNA", font_small, GRIS_CLARO, 52)

# ─── Section: Arquitectura ───
center_text("ARQUITECTURA DEL SISTEMA", font_h2, BLANCO, 90)
draw.line([640, 108, 960, 108], fill=AZUL_CLARO, width=2)

# Layer boxes
layers = [
    ("CAPA WEB (Flask)", 60, 130, 340, 160, AZUL_CLARO,
     ["HTML · CSS · Bootstrap 5", "Jinja2 Templates", "JavaScript (Fetch API)", "Font Awesome Icons"]),
    ("CAPA DE APLICACIÓN", 440, 130, 340, 160, VERDE,
     ["Flask (Python)", "Session Auth", "Paramiko SSH", "FPDF Reports"]),
    ("CAPA DE DATOS", 820, 130, 340, 160, AMARILLO,
     ["PostgreSQL 16", "SQLAlchemy ORM", "Modelos: Usuario,", "Solicitud, Noticia"]),
    ("CAPA FÍSICA (SSH)", 1200, 130, 340, 160, ROJO,
     ["Servidor 192.168.1.9", "Cluster NIDTEC", "Nodos de cómputo", "GPUs / CPUs"]),
]

for name, x, y, w, h, color, lines in layers:
    card(x, y, w, h)
    draw.rounded_rectangle([x, y, x+w, y+32], radius=12, fill=color)
    draw.rectangle([x, y+20, x+w, y+32], fill=color)
    center_text(name, font_h3, BLANCO, y+6, x_center=x+w//2)
    for i, t in enumerate(lines):
        draw.text((x+20, y+45+i*25), "• " + t, fill=GRIS_CLARO, font=font_body)

# Arrows between layers
for x1, x2 in [(400, 440), (780, 820), (1160, 1200)]:
    mid_y = 210
    draw.line([x1, mid_y, x2, mid_y], fill=AZUL_CLARO, width=2)
    draw.polygon([(x2-10, mid_y-5), (x2, mid_y), (x2-10, mid_y+5)], fill=AZUL_CLARO)

# ─── Section: Módulos ───
center_text("MÓDULOS DEL SISTEMA", font_h2, BLANCO, 330)
draw.line([640, 348, 960, 348], fill=AZUL_CLARO, width=2)

modules = [
    ("Dashboard", "Panel principal con\nsolicitudes activas,\nestados y notificaciones\ndel sistema.", "📊"),
    ("Proyectos", "Lista de proyectos\nde investigación con\nrecursos asignados\ny estado en vivo.", "📁"),
    ("Solicitudes", "Formulario de solicitud\nde recursos con\nflujo de aprobación\n(Admin/User).", "📝"),
    ("Recursos", "Monitor de nodos:\nCPU, RAM, GPU\ncon datos obtenidos\nvía SSH en vivo.", "🖥️"),
    ("Terminal SSH", "Terminal interactivo\nque ejecuta comandos\nreales en el cluster\nvía Paramiko.", "💻"),
    ("Usuarios", "Gestión de miembros,\nroles administrador/\ninvestigador, y\npromoción de cuentas.", "👥"),
]

cols = 3
card_w = 220
card_h = 160
start_x = 70
start_y = 370
gap_x = (W - 2*start_x - cols*card_w) // (cols-1)

for i, (title, desc, icon) in enumerate(modules):
    col = i % cols
    row = i // cols
    x = start_x + col*(card_w + gap_x)
    y = start_y + row*(card_h + 25)
    card(x, y, card_w, card_h)
    draw.text((x+15, y+12), icon, fill=BLANCO, font=font_h2)
    draw.text((x+55, y+15), title, fill=BLANCO, font=font_h3)
    draw.line([x+15, y+48, x+card_w-15, y+48], fill=AZUL_CLARO, width=1)
    for j, line in enumerate(desc.split('\n')):
        draw.text((x+15, y+58+j*22), "▸ " + line, fill=GRIS_CLARO, font=font_small)

# ─── Section: Roles ───
center_text("ROLES DEL SISTEMA", font_h2, BLANCO, 710)
draw.line([640, 728, 960, 728], fill=AZUL_CLARO, width=2)

roles = [
    ("ADMINISTRADOR", AZUL_CLARO, ["Gestionar solicitudes", "Aprobar/rechazar recursos", "Administrar usuarios", "Promover/degradar roles", "Acceso total al sistema"]),
    ("INVESTIGADOR", VERDE, ["Crear solicitudes", "Ver estado de proyectos", "Acceder a terminal SSH", "Ver dashboard personal", "Editar perfil propio"]),
]

for i, (role, color, items) in enumerate(roles):
    x = 200 + i * 800
    y = 745
    card(x, y, 600, 150, border_color=color)
    draw.rounded_rectangle([x, y, x+150, y+150], radius=12, fill=color)
    center_text(role, font_h3, BLANCO, y+65, x_center=x+75)
    for j, item in enumerate(items):
        draw.text((x+175, y+18+j*24), "✓ " + item, fill=GRIS_CLARO, font=font_body)

# ─── Footer ───
draw.rectangle([0, 950, W, H], fill=AZUL)
center_text("© 2026 Facultad Politécnica - Universidad Nacional de Asunción · NIDTEC", font_small, GRIS_CLARO, 970)
center_text("Desarrollado con Flask · PostgreSQL · Paramiko · Bootstrap 5", font_small, GRIS_CLARO, 992)
center_text("Repositorio: github.com/fnogueracluster/gestion-cluster", font_small, GRIS_CLARO, 1014)

# Save
output_path = os.path.join(os.path.dirname(__file__), 'diseno_sistema.png')
img.save(output_path, 'PNG')
print(f"PNG generado: {output_path}")
