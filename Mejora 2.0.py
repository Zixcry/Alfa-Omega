import os
from datetime import datetime
import threading
from flask import Flask, render_template, jsonify, request, session, redirect, url_for
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///acceso_edificio.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'clave_secreta_auditoria_safe_pass' 
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
    rol = db.Column(db.String(20), default='User')  # Superadmin, Admin, Supervisor, User
    
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
# RUTAS DE AUTENTICACIÓN (CON ACCESO USER POR CÉDULA)
# ==========================================

@app.route('/')
def login():
    return render_template('login.html', error=None)

@app.route('/login-auth', methods=['POST'])
def login_auth():
    rol_elegido = request.form.get('rol')
    password_ingresada = request.form.get('password', '').strip()
    
    # Regla 1: Roles de alta jerarquía (Superadmin y Admin)
    
    if rol_elegido in ['Superadmin', 'Admin']:
        if password_ingresada == 'terminator':
            session['rol'] = rol_elegido
            return redirect(url_for('dashboard'))
        else:
            error_msg = f"Contraseña incorrecta del {rol_elegido}."
            return render_template('login.html', error=error_msg)
            
    # Regla 2: Supervisor ahora requiere contraseña específica
    
    elif rol_elegido == 'Supervisor':
        if password_ingresada == 'superman1*':
            session['rol'] = rol_elegido
            return redirect(url_for('dashboard'))
        else:
            return render_template('login.html', error="Contraseña incorrecta para el Supervisor.")
        
    # Regla 3: User entra validando únicamente su Cédula
    
    elif rol_elegido == 'User':
        cedula_ingresada = request.form.get('cedula_user', '').strip()
        if not cedula_ingresada:
            return render_template('login.html', error="Por favor, ingrese su número de cédula.")
        
        usuario_existente = Usuario.query.filter_by(cedula=cedula_ingresada).first()
        if usuario_existente:
            session['rol'] = 'User'
            session['user_cedula'] = usuario_existente.cedula
            return redirect(url_for('dashboard'))
        else:
            return render_template('login.html', error="La cédula ingresada no se encuentra registrada en el sistema.")
        
    else:
        return render_template('login.html', error="Rol no válido seleccionado o acceso denegado.")

# Dashboard protegido que bifurca la vista según el rol
@app.route('/dashboard')
def dashboard():
    rol_actual = session.get('rol')
    
    # Si no hay un rol guardado en la sesión, los bota al login
    if not rol_actual:
        return render_template('login.html', error="Debe iniciar sesión para acceder al sistema.")
        
    # Si es un usuario común, le mostramos su estatus personal
    if rol_actual == 'User':
        cedula_user = session.get('user_cedula')
        usuario = Usuario.query.filter_by(cedula=cedula_user).first()
        if not usuario:
            session.clear()
            return render_template('login.html', error="Usuario no encontrado en la base de datos.")
        
        return render_template('perfil_user.html', usuario=usuario)
        
    # Si es operador (Superadmin, Admin, Supervisor), ve el panel de control
    return render_template('index.html', rol_inicial=rol_actual)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# ==========================================
# ENDPOINTS DE LA API (PERMISOS SEGUROS)
# ==========================================

@app.route('/api/registrar-usuario', methods=['POST'])
def api_registrar_usuario():
    data = request.get_json() or {}
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



@app.route('/api/registrar-acceso', methods=['POST'])
def registrar_acceso():
    try:
        data = request.json
        cedula = data.get('cedula', '').strip()
        tipo_movimiento = data.get('tipo_movimiento')  # 'ENTRADA' o 'SALIDA'

        if not cedula or not tipo_movimiento:
            return jsonify({'status': 'error', 'message': 'Datos incompletos.'}), 400

        # 1. Buscar si el usuario existe en el sistema
        usuario = Usuario.query.filter_by(cedula=cedula).first()
        if not usuario:
            return jsonify({'status': 'error', 'message': 'Usuario no registrado.'}), 404

        # 2. Verificar el estado del usuario (Debe estar Activo)
        if usuario.estado != 'Activo':
            return jsonify({'status': 'error', 'message': 'Acceso Denegado: El usuario se encuentra INACTIVO.'}), 403

        # 3. Buscar el ÚLTIMO movimiento exitoso de este usuario usando tus columnas reales
        ultimo_registro = Historial.query.filter_by(cedula=cedula, resultado='ACCESO CONCEDIDO')\
                                         .order_by(Historial.fecha.desc(), Historial.hora.desc())\
                                         .first()

        ultimo_estado = ultimo_registro.tipo_movimiento if ultimo_registro else 'SALIDA'
        ultima_hora_str = ultimo_registro.hora if ultimo_registro else datetime.now().strftime('%H:%M:%S')

        # 4. Obtener el aforo actual para calcular el 'aforo_restante'
        # (Ajusta este conteo si en tu app lo calculas de otra forma)
        
        personas_dentro = Usuario.query.filter_by(estado='Activo').count() # Ejemplo de conteo base

        # --- REGLAS DE VALIDACIÓN CONTRA DOBLES ACCESOS ---
        ahora = datetime.now()
        hora_actual_str = ahora.strftime('%H:%M:%S')

        if tipo_movimiento == 'ENTRADA' and ultimo_estado == 'ENTRADA':
            mensaje_alerta = f"El usuario {usuario.nombre} ya se encuentra dentro del edificio. Registró su entrada a las {ultima_hora_str}."
            
            # Guardamos el intento fallido con todas las columnas obligatorias rellenas
            intento_fallido = Historial(
                cedula=cedula,
                fecha=ahora,
                hora=hora_actual_str,
                tipo_movimiento='ENTRADA',
                resultado='DENEGADO: YA REGISTRO SU ENTRADA',
                aforo_restante=personas_dentro
            )
            db.session.add(intento_fallido)
            db.session.commit()
            return jsonify({'status': 'warning', 'message': mensaje_alerta})

        elif tipo_movimiento == 'SALIDA' and ultimo_estado == 'SALIDA':
            mensaje_alerta = f"El usuario {usuario.nombre} ya se encuentra fuera del edificio."
            
            intento_fallido = Historial(
                cedula=cedula,
                fecha=ahora,
                hora=hora_actual_str,
                tipo_movimiento='SALIDA',
                resultado='DENEGADO: YA REGISTRO SU SALIDA',
                aforo_restante=personas_dentro
            )
            db.session.add(intento_fallido)
            db.session.commit()
            return jsonify({'status': 'warning', 'message': mensaje_alerta})

        # 5. Si pasa las validaciones, calculamos el nuevo aforo y guardamos el acceso concedido
        if tipo_movimiento == 'ENTRADA':
            nuevo_aforo = personas_dentro + 1
        else:
            nuevo_aforo = max(0, personas_dentro - 1)

        nuevo_acceso = Historial(
            cedula=cedula,
            fecha=ahora,
            hora=hora_actual_str,
            tipo_movimiento=tipo_movimiento,
            resultado='ACCESO CONCEDIDO',
            aforo_restante=nuevo_aforo
        )
        db.session.add(nuevo_acceso)
        db.session.commit()

        return jsonify({
            'status': 'success',
            'message': f"¡Acceso Concedido! {tipo_movimiento} registrada para {usuario.nombre}."
        })

    except Exception as e:
        db.session.rollback()
        print(f"Error en base de datos: {str(e)}")
        return jsonify({'status': 'error', 'message': f"Error en base de datos: {str(e)}"}), 500
    
    
    
@app.route('/api/status-sistema', methods=['POST'])
def status_sistema():
    data = request.get_json() or {}
    rol_operador = data.get('rol_operador')
    
    if not rol_operador:
        rol_operador = session.get('rol', 'Invalido')

    rol_operador = str(rol_operador).strip().lower()
    
    if rol_operador not in ['superadmin', 'admin', 'supervisor']:
        return jsonify({
            "aforo_actual": obtener_aforo_actual(),
            "capacidad_maxima": CAPACIDAD_MAXIMA,
            "porcentaje": round((obtener_aforo_actual()/CAPACIDAD_MAXIMA)*100, 1),
            "historial": [],
            "error_permiso": f"Su perfil actual ({rol_operador}) no cuenta con autorización para auditar la base de datos."
        }), 200

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


# 4. MODIFICAR REGISTROS (Respaldo con session si falla el JS)

@app.route('/api/modificar-usuario', methods=['POST'])
def modificar_usuario():
    data = request.get_json() or {}
    rol_operador = data.get('rol_operador')
    
    if not rol_operador:
        rol_operador = session.get('rol', 'Invalido')
        
    rol_operador = str(rol_operador).strip().lower()
    target_cedula = str(data.get('target_cedula', '')).strip()
    nuevo_estado = data.get('nuevo_estado')
    
    if rol_operador not in ['superadmin', 'admin']:
        return jsonify({"status": "error", "message": f"No tiene permisos para modificar registros. Rol detectado: {rol_operador}"}), 403
        
    user = Usuario.query.filter_by(cedula=target_cedula).first()
    if not user:
        return jsonify({"status": "error", "message": "Usuario no encontrado."}), 404
        
    user.estado = nuevo_estado
    db.session.commit()
    return jsonify({"status": "success", "message": f"Usuario {user.nombre} actualizado a {nuevo_estado}."})


# 5. BORRAR REGISTROS 

@app.route('/api/borrar-usuario', methods=['POST'])
def borrar_usuario():
    data = request.get_json() or {}
    rol_operador = data.get('rol_operador')
    
    if not rol_operador:
        rol_operador = session.get('rol', 'Invalido')
        
    rol_operador = str(rol_operador).strip().lower()
    target_cedula = str(data.get('target_cedula', '')).strip()
    
    if rol_operador != 'superadmin':
        return jsonify({"status": "error", "message": "ACCESO DENEGADO"}), 403
        
    user = Usuario.query.filter_by(cedula=target_cedula).first()
    if not user:
        return jsonify({"status": "error", "message": "Usuario no encontrado."}), 404
        
    Historial.query.filter_by(cedula=target_cedula).delete()
    db.session.delete(user)
    db.session.commit()
    return jsonify({"status": "success", "message": f"El usuario con cédula {target_cedula} ha sido eliminado."})

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)