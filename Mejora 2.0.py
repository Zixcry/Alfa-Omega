import os
from datetime import datetime
import threading
from flask import Flask, render_template, jsonify, request
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///acceso_edificio.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

CAPACIDAD_MAXIMA = 100
ALERTA_CAPACIDAD = 80

lock = threading.Lock()

# ==========================================
# MODELOS DE LA BASE DE DATOS
# ==========================================

class Usuario(db.Model):
    __tablename__ = 'usuarios'
    cedula = db.Column(db.String(20), primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    departamento = db.Column(db.String(50))
    estado = db.Column(db.String(20), default='Activo')
    rol = db.Column(db.String(20), default='User')  # Superadmin, Admin, Supervisor, User, Guest
    
    accesos = db.relationship('Historial', backref='usuario', lazy=True)

class Historial(db.Model):
    __tablename__ = 'historial'
    id_log = db.Column(db.Integer, primary_key=True, autoincrement=True)
    cedula = db.Column(db.String(20), db.ForeignKey('usuarios.cedula'), nullable=False)
    fecha = db.Column(db.String(10), nullable=False)
    hora = db.Column(db.String(8), nullable=False)
    tipo_movimiento = db.Column(db.String(10), nullable=False)
    resultado = db.Column(db.String(100), nullable=False)
    aforo_restante = db.Column(db.Integer, nullable=False)

class Alerta(db.Model):
    __tablename__ = 'alertas'
    id_alerta = db.Column(db.Integer, primary_key=True, autoincrement=True)
    timestamp = db.Column(db.DateTime, default=datetime.now)
    tipo = db.Column(db.String(20), nullable=False)
    mensaje = db.Column(db.String(200), nullable=False)
    aforo_actual = db.Column(db.Integer, nullable=False)
    leida = db.Column(db.Boolean, default=False)

# ==========================================
# LÓGICA DE AFORO
# ==========================================

def obtener_aforo_actual():
    ultimo_registro = Historial.query.order_by(Historial.id_log.desc()).first()
    return ultimo_registro.aforo_restante if ultimo_registro else 0

def verificar_y_registrar_alerta(aforo_actual):
    porcentaje = (aforo_actual / CAPACIDAD_MAXIMA) * 100
    if aforo_actual >= CAPACIDAD_MAXIMA:
        nueva_alerta = Alerta(tipo='CRÍTICA', mensaje=f'¡AFORO MÁXIMO! {aforo_actual}/{CAPACIDAD_MAXIMA}', aforo_actual=aforo_actual)
        db.session.add(nueva_alerta)
    elif porcentaje >= ALERTA_CAPACIDAD:
        nueva_alerta = Alerta(tipo='ADVERTENCIA', mensaje=f'Aforo al {porcentaje:.0f}% ({aforo_actual}/{CAPACIDAD_MAXIMA})', aforo_actual=aforo_actual)
        db.session.add(nueva_alerta)
    db.session.commit()

# ==========================================
# RUTAS DE AUTENTICACIÓN Y CONTROL DE ACCESO
# ==========================================


# Muestra la pantalla de inicio de sesión al entrar a la raíz
@app.route('/')
def login():
    return render_template('login.html', error=None)

# Procesa el formulario del Login con tus reglas estrictas de contraseñas

@app.route('/login-auth', methods=['POST'])
def login_auth():
    rol_elegido = request.form.get('rol')
    password_ingresada = request.form.get('password', '').strip()
    
    # Regla 1: Roles de alta jerarquía requieren la clave "terminator"
    
    if rol_elegido in ['Superadmin', 'Admin']:
        if password_ingresada == 'terminator':
            
            # Éxito: Redirige al dashboard pasando el rol en la URL para configurar el monitor
            
            return render_template('index.html', rol_inicial=rol_elegido)
        else:
            # Falla: Clave incorrecta
            error_msg = f"Contraseña incorrecta para el perfil de {rol_elegido}."
            return render_template('login.html', error=error_msg)
            
            
    # Regla 2: Supervisor, User y Guest entran directo sin contraseña
    
    elif rol_elegido in ['Supervisor', 'User', 'Guest']:
        return render_template('index.html', rol_inicial=rol_elegido)
        
    else:
        return render_template('login.html', error="Rol no válido seleccionado.")

# Si alguien intenta entrar al dashboard directo sin pasar por el login principal

@app.route('/dashboard')
def dashboard_directo():
    return render_template('index.html', rol_inicial='Guest')



# 1. REGISTRO LIBRE: Se eliminó el candado del Superadmin autorizador

@app.route('/api/registrar-usuario', methods=['POST'])
def api_registrar_usuario():
    data = request.get_json()
    nueva_c = str(data.get('cedula', '')).strip()
    nuevo_n = data.get('nombre', '').strip()
    nuevo_d = data.get('departamento', '').strip()
    nuevo_r = data.get('rol', 'User').strip()
    
    if not nueva_c or not nuevo_n:
        return jsonify({"status": "error", "message": "Cédula y Nombre son obligatorios."}), 400

    if Usuario.query.filter_by(cedula=nueva_c).first():
        return jsonify({"status": "error", "message": "Esta cédula ya está registrada."}), 400
        
    nuevo_usuario = Usuario(cedula=nueva_c, nombre=nuevo_n, departamento=nuevo_d, rol=nuevo_r, estado='Activo')
    db.session.add(nuevo_usuario)
    db.session.commit()
    return jsonify({"status": "success", "message": f"¡Usuario {nuevo_n} registrado exitosamente como {nuevo_r}!"}), 201

# 2. PROCESAR ACCESOS (ENTRADAS / SALIDAS)

@app.route('/api/registrar-acceso', methods=['POST'])
def registrar_acceso():
    data = request.get_json()
    num_cedula = str(data.get('cedula', '')).strip()
    tipo_movimiento = data.get('tipo_movimiento', 'ENTRADA')
    
    ahora = datetime.now()
    fecha_str = ahora.strftime('%Y-%m-%d')
    hora_str = ahora.strftime('%H:%M:%S')
    
    user = Usuario.query.filter_by(cedula=num_cedula).first()
    
    if not user:
        return jsonify({"status": "error", "message": "Cédula no registrada."}), 404
        
    if user.estado != 'Activo':
        return jsonify({"status": "error", "message": f"Acceso Denegado: Credencial Inactiva."}), 403

    with lock:
        aforo_actual = obtener_aforo_actual()
        
        if tipo_movimiento == 'ENTRADA':
            # Solo Superadmin, Admin y Supervisor (perfiles altos) ignoran el tope de aforo si estuviera lleno
            
            es_staff = user.rol in ['Superadmin', 'Admin', 'Supervisor']
            if aforo_actual >= CAPACIDAD_MAXIMA and not es_staff:
                resultado = "DENEGADO: Aforo máximo alcanzado"
                nuevo_log = Historial(cedula=user.cedula, fecha=fecha_str, hora=hora_str, tipo_movimiento=tipo_movimiento, resultado=resultado, aforo_restante=aforo_actual)
                db.session.add(nuevo_log)
                db.session.commit()
                return jsonify({"status": "error", "message": " Edificio lleno. Acceso denegado."}), 403
            else:
                aforo_actual += 1
                resultado = f"PERMITIDO: {user.nombre} ({user.rol})"
                verificar_y_registrar_alerta(aforo_actual)
        else:
            if aforo_actual > 0:
                aforo_actual -= 1
                resultado = f"SALIDA: {user.nombre}"
            else:
                resultado = "CORRECCIÓN: Aforo negativo"

        nuevo_log = Historial(cedula=user.cedula, fecha=fecha_str, hora=hora_str, tipo_movimiento=tipo_movimiento, resultado=resultado, aforo_restante=aforo_actual)
        db.session.add(nuevo_log)
        db.session.commit()

    return jsonify({"status": "success", "message": f" {resultado}"}), 200

# 3. VER LA BASE DE DATOS Y STATUS (Superadmin, Admin, Supervisor pueden ver)

@app.route('/api/status-sistema', methods=['POST'])
def status_sistema():
    data = request.get_json() or {}
    # Capturamos el rol y lo limpiamos
    rol_operador = str(data.get('rol_operador', '')).strip()
    
    # === SOLUCIÓN: Convertimos a minúsculas para evitar errores de tipeo ===
    rol_minúscula = rol_operador.lower()
    
    # Validar Permisos usando minúsculas obligatorias
    if rol_minúscula not in ['superadmin', 'admin', 'supervisor']:
        return jsonify({
            "aforo_actual": obtener_aforo_actual(),
            "capacidad_maxima": CAPACIDAD_MAXIMA,
            "porcentaje": round((obtener_aforo_actual()/CAPACIDAD_MAXIMA)*100, 1),
            "historial": [],
            "error_permiso": f"Su perfil actual ({rol_operador}) no cuenta con autorización para auditar el historial de la base de datos."
        }), 200

    # Si pasa la auditoría (es Superadmin, Admin o Supervisor), extrae la información normalmente
    aforo = obtener_aforo_actual()
    porcentaje = (aforo / CAPACIDAD_MAXIMA) * 100
    logs = Historial.query.order_by(Historial.id_log.desc()).limit(7).all()
    
    historial_json = []
    for l in logs:
        u = Usuario.query.filter_by(cedula=l.cedula).first()
        historial_json.append({
            "cedula": l.cedula,
            "nombre": u.nombre if u else "Desconocido",
            "departamento": u.departamento if u else "N/A",
            "rol": u.rol if u else "N/A",
            "movimiento": l.tipo_movimiento,
            "hora": l.hora,
            "resultado": l.resultado
        })
        
    ultima_alerta = Alerta.query.filter_by(leida=False).order_by(Alerta.id_alerta.desc()).first()
    alerta_json = {"tipo": ultima_alerta.tipo, "mensaje": ultima_alerta.mensaje} if ultima_alerta else None

    return jsonify({
        "aforo_actual": aforo,
        "capacidad_maxima": CAPACIDAD_MAXIMA,
        "porcentaje": round(porcentaje, 1),
        "historial": historial_json,
        "alerta": alerta_json
    })

# 4. MODIFICAR REGISTROS (Solo Superadmin y Admin)

@app.route('/api/modificar-usuario', methods=['POST'])
def modificar_usuario():
    data = request.get_json()
    cedula_op = str(data.get('cedula_operador', '')).strip()
    target_cedula = str(data.get('target_cedula', '')).strip()
    nuevo_estado = data.get('nuevo_estado') # 'Activo' o 'Inactivo'
    
    operador = Usuario.query.filter_by(cedula=cedula_op).first()
    if not operador or operador.rol not in ['Superadmin', 'Admin']:
        return jsonify({"status": "error", "message": "No tiene permisos para modificar registros."}), 403
        
    user = Usuario.query.filter_by(cedula=target_cedula).first()
    if not user:
        return jsonify({"status": "error", "message": "Usuario no encontrado."}), 404
        
    user.estado = nuevo_estado
    db.session.commit()
    return jsonify({"status": "success", "message": f"Usuario {user.nombre} actualizado a {nuevo_estado}."})

# 5. BORRAR REGISTROS (Estrictamente Superadmin)

@app.route('/api/borrar-usuario', methods=['POST'])
def borrar_usuario():
    data = request.get_json()
    cedula_op = str(data.get('cedula_operador', '')).strip()
    target_cedula = str(data.get('target_cedula', '')).strip()
    
    operador = Usuario.query.filter_by(cedula=cedula_op).first()
    if not operador or operador.rol != 'Superadmin':
        return jsonify({"status": "error", "message": " ACCESO DENEGADO: Solo el Superadmin puede eliminar registros."}), 403
        
    user = Usuario.query.filter_by(cedula=target_cedula).first()
    if not user:
        return jsonify({"status": "error", "message": "Usuario no encontrado."}), 404
        
    # Borrar primero su historial por integridad de llaves foráneas
    

    Historial.query.filter_by(cedula=target_cedula).delete()
    db.session.delete(user)
    db.session.commit()
    return jsonify({"status": "success", "message": f" El usuario con cédula {target_cedula} ha sido eliminado físicamente del sistema."})

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)