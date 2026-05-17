import sqlite3
from datetime import datetime

# 1. Configuración de la Base de Datos
def inicializar_db():
    conn = sqlite3.connect('acceso_edificio.db')
    cursor = conn.cursor()
    
    # Tabla de Usuarios
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS usuarios (
            id_rfid TEXT PRIMARY KEY,
            nombre TEXT NOT NULL,
            departamento TEXT,
            estado TEXT DEFAULT 'Activo'
        )
    ''')
    
    # Tabla de Historial (Logs)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS historial (
            id_log INTEGER PRIMARY KEY AUTOINCREMENT,
            id_rfid TEXT,
            fecha DATE,
            hora TIME,
            resultado TEXT,
            FOREIGN KEY (id_rfid) REFERENCES usuarios(id_rfid)
        )
    ''')
    conn.commit()
    conn.close()

# 2. Función para Registrar Acceso (Tiempo Real)
def registrar_evento(id_rfid):
    conn = sqlite3.connect('acceso_edificio.db')
    cursor = conn.cursor()
    
    # Verificar si el usuario existe y está activo
    cursor.execute("SELECT nombre, departamento, estado FROM usuarios WHERE id_rfid = ?", (id_rfid,))
    usuario = cursor.fetchone()
    
    ahora = datetime.now()
    fecha = ahora.strftime('%Y-%m-%d')
    hora = ahora.strftime('%H:%M:%S')
    
    if usuario and usuario[2] == 'Activo':
        nombre, depto, _ = usuario
        resultado = f"PERMITIDO ({nombre} - {depto})"
        print(f"ACCESO CONCEDIDO: {nombre} en tiempo real.")
    else:
        resultado = "DENEGADO / DESCONOCIDO"
        print(f"ALERTA: Intento de acceso no autorizado con ID {id_rfid}")

    # Guardar en la base de datos
    cursor.execute("INSERT INTO historial (id_rfid, fecha, hora, resultado) VALUES (?, ?, ?, ?)", 
                   (id_rfid, fecha, hora, resultado))
    
    conn.commit()
    conn.close()

# 3. Generación de Reportes Filtrados
def generar_reporte(filtro_fecha=None, filtro_depto=None):
    conn = sqlite3.connect('acceso_edificio.db')
    cursor = conn.cursor()
    
    query = """
        SELECT h.fecha, h.hora, h.id_rfid, u.nombre, u.departamento, h.resultado 
        FROM historial h
        LEFT JOIN usuarios u ON h.id_rfid = u.id_rfid
        WHERE 1=1
    """
    params = []
    
    if filtro_fecha:
        query += " AND h.fecha = ?"
        params.append(filtro_fecha)
    
    if filtro_depto:
        query += " AND u.departamento = ?"
        params.append(filtro_depto)
        
    cursor.execute(query, params)
    reporte = cursor.fetchall()
    
    print("\n--- REPORTE DE AUDITORÍA ---")
    print(f"{'FECHA':<12} | {'HORA':<10} | {'USUARIO':<20} | {'DEPTO':<15} | {'RESULTADO'}")
    print("-" * 80)
    for fila in reporte:
        print(f"{fila[0]:<12} | {fila[1]:<10} | {str(fila[3]):<20} | {str(fila[4]):<15} | {fila[5]}")
    
    conn.close()

# --- PRUEBA DEL SISTEMA ---
inicializar_db()

# Agregar un usuario de prueba (Solo la primera vez)
def agregar_usuario_prueba():
    conn = sqlite3.connect('acceso_edificio.db')
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO usuarios VALUES ('123ABC', 'Carlos Auditor', 'Finanzas', 'Activo')")
        conn.commit()
    except: pass
    conn.close()

agregar_usuario_prueba()

# Simulación de uso
registrar_evento('123ABC')  # Usuario conocido
registrar_evento('999XYZ')  # Usuario desconocido

# Ver reporte de hoy
generar_reporte(filtro_fecha=datetime.now().strftime('%Y-%m-%d'))

from datetime import datetime, time

# Configuración de horario laboral (Ejemplo: 08:00 a 18:00)
HORA_APERTURA = time(8, 0)
HORA_CIERRE = time(18, 0)

def es_horario_permitido():
    ahora = datetime.now().time()
    return HORA_APERTURA <= ahora <= HORA_CIERRE

def registrar_evento_con_horario(id_rfid):
    conn = sqlite3.connect('acceso_edificio.db')
    cursor = conn.cursor()
    
    # 1. Verificar si el usuario existe
    cursor.execute("SELECT nombre, estado FROM usuarios WHERE id_rfid = ?", (id_rfid,))
    usuario = cursor.fetchone()
    
    ahora_dt = datetime.now()
    fecha = ahora_dt.strftime('%Y-%m-%d')
    hora = ahora_dt.strftime('%H:%M:%S')
    
    # 2. Lógica de validación
    if not usuario:
        resultado = "DENEGADO: ID Desconocido"
    elif usuario[1] != 'Activo':
        resultado = "DENEGADO: Credencial Inactiva"
    elif not es_horario_permitido():
        resultado = f"DENEGADO: Fuera de Horario ({usuario[0]})"
    else:
        resultado = f"PERMITIDO: {usuario[0]}"

    # 3. Registro en DB
    cursor.execute("INSERT INTO historial (id_rfid, fecha, hora, resultado) VALUES (?, ?, ?, ?)", 
                   (id_rfid, fecha, hora, resultado))
    
    conn.commit()
    conn.close()
    print(f"[{hora}] Resultado: {resultado}")