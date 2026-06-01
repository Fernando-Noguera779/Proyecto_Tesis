from PIL import Image, ImageDraw, ImageFont
import os

W, H = 1600, 1150
img = Image.new('RGB', (W, H), (15, 23, 42))
draw = ImageDraw.Draw(img)

AZUL       = (26, 54, 104)
AZUL_CLARO = (60, 100, 170)
VERDE      = (16, 185, 129)
ROJO       = (239, 68, 68)
NARANJA    = (255, 165, 0)
GRIS       = (100, 116, 139)
GRIS_CLARO = (200, 210, 220)
BLANCO     = (255, 255, 255)
FONDO_CARD = (30, 41, 59)

try:
    font_title = ImageFont.truetype("arial.ttf", 28)
    font_h2    = ImageFont.truetype("arial.ttf", 18)
    font_h3    = ImageFont.truetype("arial.ttf", 14)
    font_body  = ImageFont.truetype("arial.ttf", 11)
    font_small = ImageFont.truetype("arial.ttf", 10)
except:
    font_title = font_h2 = font_h3 = font_body = font_small = ImageFont.load_default()

def card(x, y, w, h, fill=FONDO_CARD, border=AZUL_CLARO):
    draw.rounded_rectangle([x, y, x+w, y+h], radius=10, fill=fill, outline=border, width=1)

def headered_card(x, y, w, h, header_color, title):
    card(x, y, w, h)
    draw.rounded_rectangle([x, y, x+w, y+26], radius=10, fill=header_color)
    draw.rectangle([x, y+17, x+w, y+26], fill=header_color)
    tw = draw.textbbox((0, 0), title, font=font_h3)[2]
    draw.text((x + w//2 - tw//2, y+4), title, fill=BLANCO, font=font_h3)

def center_text(text, font, color, y, x_center=W//2):
    tw = draw.textbbox((0, 0), text, font=font)[2]
    draw.text((x_center - tw//2, y), text, fill=color, font=font)

def arrow(x1, y1, x2, y2, color=AZUL_CLARO, label=""):
    draw.line([x1, y1, x2, y2], fill=color, width=2)
    dx, dy = x2 - x1, y2 - y1
    d = max(1, (dx*dx + dy*dy)**0.5)
    ux, uy = dx/d, dy/d
    ax, ay = x2 - 8*ux, y2 - 8*uy
    draw.polygon([(ax-4*uy, ay+4*ux), (x2, y2), (ax+4*uy, ay-4*ux)], fill=color)
    if label:
        mx, my = (x1+x2)//2, (y1+y2)//2
        tw = draw.textbbox((0, 0), label, font=font_small)[2]
        draw.text((mx - tw//2, my-12), label, fill=color, font=font_small)

def rarrow(x1, y1, x2, y2, color, label=""):
    """Route arrow with right-angle bend: horizontal then vertical."""
    mx = (x1 + x2) // 2
    draw.line([x1, y1, mx, y1], fill=color, width=2)
    draw.line([mx, y1, mx, y2], fill=color, width=2)
    draw.line([mx, y2, x2, y2], fill=color, width=2)
    dx, dy = 0, y2 - y1
    d = max(1, abs(dx) + abs(dy))
    ux, uy = 0, 1 if dy > 0 else -1
    ax, ay = x2 - 8*ux, y2 - 8*uy
    draw.polygon([(ax-4*uy, ay+4*ux), (x2, y2), (ax+4*uy, ay-4*ux)], fill=color)
    if label:
        tw = draw.textbbox((0, 0), label, font=font_small)[2]
        draw.text((mx - tw//2, (y1+y2)//2 - 12), label, fill=color, font=font_small)

# ═══ HEADER ═══
draw.rectangle([0, 0, W, 60], fill=AZUL)
center_text("FNOGUERA CLUSTER — FLUJO DE NAVEGACIÓN ENTRE TEMPLATES", font_title, BLANCO, 12)
center_text("Diagrama de interacción de páginas para Administradores e Investigadores", font_small, GRIS_CLARO, 44)

# ═══ LEGEND ═══
lx, ly = 40, 74
draw.rectangle([lx, ly, lx+12, ly+12], fill=AZUL_CLARO)
draw.text((lx+18, ly-1), "Ruta pública", fill=GRIS_CLARO, font=font_small)
draw.rectangle([lx+150, ly, lx+162, ly+12], fill=VERDE)
draw.text((lx+168, ly-1), "Ruta usuario", fill=GRIS_CLARO, font=font_small)
draw.rectangle([lx+300, ly, lx+312, ly+12], fill=NARANJA)
draw.text((lx+318, ly-1), "Ruta admin", fill=GRIS_CLARO, font=font_small)
draw.line([lx+470, ly+6, lx+510, ly+6], fill=AZUL_CLARO, width=2)
draw.text((lx+516, ly-1), "Navegación", fill=GRIS_CLARO, font=font_small)

# ════════════════════════════════════════════════════════
#  COLUMN 1 — USER FLOW (left)
# ════════════════════════════════════════════════════════
c1x, c1w = 40, 200

# index.html (public)
headered_card(c1x, 105, c1w, 80, AZUL_CLARO, "index.html")
draw.text((c1x+12, 138), "Landing page · Presentación\nBotones: Ingresar | Registrarse", fill=GRIS_CLARO, font=font_small)

# login.html
headered_card(c1x, 210, c1w, 75, AZUL_CLARO, "login.html")
draw.text((c1x+12, 242), "Formulario de inicio\nde sesión", fill=GRIS_CLARO, font=font_small)

# registro.html
headered_card(c1x, 310, c1w, 75, AZUL_CLARO, "registro.html")
draw.text((c1x+12, 342), "Formulario de\nregistro de cuenta", fill=GRIS_CLARO, font=font_small)

# Arrows within column 1
arrow(c1x + c1w//2, 185, c1x + c1w//2, 210, AZUL_CLARO, "Ingresar")
arrow(c1x + c1w//2, 185, c1x + c1w//2, 310, AZUL_CLARO, "Registrarse")

# ════════════════════════════════════════════════════════
#  COLUMN 2 — INVESTIGATOR (center)
# ════════════════════════════════════════════════════════
c2x, c2w = 310, 440
center_text("FLUJO — INVESTIGADOR", font_h2, VERDE, 100, x_center=c2x + c2w//2)

# User pages — dashboard as hub, others in collapsed rows underneath
# Calculate layout: dashboard is the hub above
dhx, dhw = c2x + (c2w - 310) // 2, 310
dhy = 130
headered_card(dhx, dhy, dhw, 100, VERDE, "dashboard.html")
draw.text((dhx+15, dhy+34), "Panel principal — Solicitudes activas — Notificaciones", fill=GRIS_CLARO, font=font_small)

# Login arrow pointing to dashboard
arrow(c1x + c1w, 247, dhx, 247 + 20, VERDE, "Login exitoso")

# Other user pages in a 3x2 grid below dashboard
user_pages = [
    "noticias.html", "proyectos.html", "solicitud.html",
    "recursos.html",  "terminal.html",  "perfil.html",
]
descs = [
    "Noticias y eventos\ndel sistema",
    "Proyectos de\ninvestigación asignados",
    "Solicitar recursos\ndel cluster",
    "Estado de recursos\ndel cluster (SSH)",
    "Terminal SSH\ninteractivo",
    "Editar perfil y\ncambiar contraseña",
]
ucols = 3
urows = 2
uw, uh = 130, 100
ugx, ugy = 15, 15
u_start_y = dhy + 100 + 40

for idx, (page, desc) in enumerate(zip(user_pages, descs)):
    col = idx % ucols
    row = idx // ucols
    ux = c2x + col * (uw + ugx)
    uy = u_start_y + row * (uh + ugy)
    headered_card(ux, uy, uw, uh, VERDE, page)
    for j, line in enumerate(desc.split('\n')):
        draw.text((ux+8, uy+33+j*16), "▸ " + line, fill=GRIS_CLARO, font=font_small)

# Draw hub arrows: from dashboard to each user page
for idx in range(6):
    col = idx % ucols
    row = idx // ucols
    ux = c2x + col * (uw + ugx)
    uy = u_start_y + row * (uh + ugy)
    # top-center of card
    tx, ty = ux + uw//2, uy
    # bottom-center of dashboard
    bx, by = dhx + dhw//2, dhy + 100
    # Route: down from dashboard, then horizontal, then down
    mx = tx
    draw.line([bx, by, bx, by + 10 + row*20], fill=VERDE, width=1)
    draw.line([bx, by + 10 + row*20, tx, by + 10 + row*20], fill=VERDE, width=1)
    draw.line([tx, by + 10 + row*20, tx, ty], fill=VERDE, width=1)
    # arrowhead at ty
    draw.polygon([(tx-3, ty+6), (tx, ty), (tx+3, ty+6)], fill=VERDE)

# ════════════════════════════════════════════════════════
#  COLUMN 3 — ADMIN (right)
# ════════════════════════════════════════════════════════
c3x, c3w = 830, 340
center_text("FLUJO — ADMINISTRADOR", font_h2, NARANJA, 100, x_center=c3x + c3w//2)

# Admin gets the same dashboard (but with more privileges)
ahx, ahw = c3x + (c3w - 310) // 2, 310
ahy = 130
headered_card(ahx, ahy, ahw, 100, NARANJA, "dashboard.html (Admin)")
draw.text((ahx+15, ahy+34), "Panel principal — Gestiona TODAS las solicitudes", fill=GRIS_CLARO, font=font_small)
draw.text((ahx+15, ahy+54), "Acepta y rechaza solicitudes de recursos", fill=GRIS_CLARO, font=font_small)

# Admin arrow from user dashboard
arrow(dhx + dhw, 180, ahx, 180, NARANJA, "Admin: ve todo")

# Admin-specific pages
admin_pages = [
    ("usuarios.html", "CRUD de usuarios\nPromover/Degradar roles", "Naranja"),
    ("noticias-admin.html", "Crear, editar y\neliminar noticias", "Naranja"),
]
aw, ah = 150, 90
agx = 20
a_start_y = ahy + 100 + 30

for idx, (page, desc, _) in enumerate(admin_pages):
    ax = c3x + idx * (aw + agx)
    ay = a_start_y
    headered_card(ax, ay, aw, ah, NARANJA, page)
    for j, line in enumerate(desc.split('\n')):
        draw.text((ax+10, ay+33+j*16), "▸ " + line, fill=GRIS_CLARO, font=font_small)
    # arrow from admin dashboard
    tx2, ty2 = ax + aw//2, ay
    draw.line([ahx + ahw//2, ahy+100, ahx + ahw//2, ahy+100+10], fill=NARANJA, width=1)
    draw.line([ahx + ahw//2, ahy+100+10, tx2, ahy+100+10], fill=NARANJA, width=1)
    draw.line([tx2, ahy+100+10, tx2, ty2], fill=NARANJA, width=1)
    draw.polygon([(tx2-3, ty2+6), (tx2, ty2), (tx2+3, ty2+6)], fill=NARANJA)

# Admin also has access to all user pages
center_text("El administrador también accede a:", font_body, GRIS_CLARO, a_start_y + ah + 25, x_center=c3x + c3w//2)

user_pages2 = [
    "noticias.html", "proyectos.html", "solicitud.html",
    "recursos.html",  "terminal.html",  "perfil.html",
]
uw2, uh2 = 105, 85
ugx2, ugy2 = 10, 12
u2_start_y = a_start_y + ah + 35

for idx, page in enumerate(user_pages2):
    col = idx % 3
    row = idx // 3
    ux2 = c3x + col * (uw2 + ugx2)
    uy2 = u2_start_y + row * (uh2 + ugy2)
    headered_card(ux2, uy2, uw2, uh2, VERDE, page)
    draw.text((ux2+8, uy2+34), "▸ Misma vista\n  que usuario", fill=GRIS_CLARO, font=font_small)

# ════════════════════════════════════════════════════════
#  LOGOUT FLOW (bottom)
# ════════════════════════════════════════════════════════
logout_y = 760
draw.rectangle([40, logout_y, W-40, logout_y+140], fill=FONDO_CARD, outline=ROJO, width=1)
center_text("FLUJO DE CIERRE DE SESIÓN", font_h2, ROJO, logout_y + 10)

# 3 boxes in a row
logout_items = [
    ("Cualquier página\nprotegida", 250),
    ("Clic en 'Salir'\nen el sidebar", 620),
    ("/logout limpia\nla sesión (session.pop)", 990),
    ("Redirige a\nindex.html", 1360),
]
for label, lx in logout_items:
    bw, bh = 160, 55
    card(lx - bw//2, logout_y + 45, bw, bh, border=ROJO)
    for j, line in enumerate(label.split('\n')):
        center_text(line, font_body, GRIS_CLARO, logout_y + 52 + j*18, x_center=lx)

# Arrows connecting them
arrow(330, logout_y + 72, 540, logout_y + 72, ROJO)
arrow(700, logout_y + 72, 910, logout_y + 72, ROJO)
arrow(1070, logout_y + 72, 1280, logout_y + 72, ROJO)

# Also show logout arrow from each protected page zone
# From investigator section
draw.line([dhx + dhw//2, logout_y, dhx + dhw//2, logout_y - 5], fill=ROJO, width=1)
# Label at top of logout box
center_text("La barra lateral (sidebar) está presente en todas las páginas protegidas", font_small, GRIS_CLARO, logout_y - 18)
center_text("y contiene el enlace de 'Salir' para cerrar sesión desde cualquier página.", font_small, GRIS_CLARO, logout_y - 8)

# ═══ FOOTER ═══
draw.rectangle([0, 920, W, H], fill=AZUL)
center_text("© 2026 Facultad Politécnica - UNA · NIDTEC · FNOGUERA CLUSTER", font_small, GRIS_CLARO, 940)
center_text("Colores: Azul = público · Verde = usuario (investigador) · Naranja = administrador. Las flechas indican navegación entre templates.", font_small, GRIS_CLARO, 960)
center_text("Todas las rutas protegidas redirigen al login si no hay sesión activa. El sidebar está presente en todas las páginas con sesión.", font_small, GRIS_CLARO, 980)

# Save
out = os.path.join(os.path.dirname(__file__), 'flujo_templates.png')
img.save(out, 'PNG')
print(f"PNG generado: {out}")
