import os
import psycopg2
from dotenv import load_dotenv
from flask import Flask, jsonify, request
from flask_cors import CORS
# --- NUEVAS IMPORTACIONES PARA JWT ---
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity, JWTManager, get_jwt
from werkzeug.security import generate_password_hash, check_password_hash # Para manejar contraseñas seguras

load_dotenv() 

app = Flask(__name__)

# --- CONFIGURACIÓN DE JWT ---
# Necesitas una clave secreta fuerte. Render debe tener esta variable.
app.config["JWT_SECRET_KEY"] = os.environ.get("JWT_SECRET_KEY", "SUPER_SECRETA_FALLBACK") 
jwt = JWTManager(app)

CORS(app)

# --- Función de Conexión a la Base de Datos ---
def get_db_connection():
    db_url = os.environ.get('DATABASE_URL')
    if not db_url:
        raise Exception("DATABASE_URL no está configurada")
        
    conn = psycopg2.connect(db_url)
    return conn

# --- Funciones de Utilidad (Hashed Password) ---
def hash_password(password):
    # Genera un hash seguro de la contraseña
    return generate_password_hash(password)

# --- RUTAS DE AUTENTICACIÓN Y ROLES ---

## Ruta para CREAR un usuario de prueba (Solo para desarrollo)
## NOTA: En la aplicación final, esto se haría desde el panel de administración
@app.route('/register-test', methods=['POST'])
def register_test():
    data = request.get_json()
    nombre = data.get('nombre')
    email = data.get('email')
    password = data.get('password')
    rol = data.get('rol', 'cliente') # Por defecto es cliente

    if not all([nombre, email, password]):
        return jsonify({"error": "Faltan datos de registro"}, 400)

    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # 1. Insertar en Persona
        insert_persona = "INSERT INTO Persona (nombre) VALUES (%s) RETURNING id_persona;"
        cur.execute(insert_persona, (nombre,))
        persona_id = cur.fetchone()[0]
        
        # 2. Insertar en Cliente o Empleado
        if rol == 'cliente':
            cur.execute("INSERT INTO Cliente (persona_id) VALUES (%s);", (persona_id,))
        elif rol == 'empleado':
            cur.execute("INSERT INTO Empleado (persona_id) VALUES (%s);", (persona_id,))
        
        # 3. Insertar en Usuario_Login
        password_hash = hash_password(password)
        insert_login = "INSERT INTO Usuario_Login (persona_id, email, password_hash, rol) VALUES (%s, %s, %s, %s);"
        cur.execute(insert_login, (persona_id, email, password_hash, rol))
        
        conn.commit()
        return jsonify({"message": f"Usuario {rol} registrado exitosamente", "id": persona_id}), 201

    except psycopg2.errors.UniqueViolation:
        if conn: conn.rollback()
        return jsonify({"error": "El email ya está registrado."}, 409)
    except Exception as e:
        if conn: conn.rollback()
        print(f"Error al registrar usuario: {e}")
        return jsonify({"error": "Error interno al registrar"}, 500)
    finally:
        if conn: conn.close()


## Ruta de LOGIN (Genera el Token JWT)
@app.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    email = data.get('email')
    password = data.get('password')

    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        query = "SELECT persona_id, password_hash, rol FROM Usuario_Login WHERE email = %s;"
        cur.execute(query, (email,))
        user_record = cur.fetchone()
        
        if user_record and check_password_hash(user_record[1], password):
            persona_id, _, rol = user_record
            
            # Crear el token JWT, incluyendo el rol en los claims (datos extra del token)
            access_token = create_access_token(
                identity=persona_id, 
                additional_claims={'rol': rol, 'persona_id': persona_id}
            )
            return jsonify(access_token=access_token, rol=rol)
        else:
            return jsonify({"error": "Email o contraseña incorrectos"}, 401)
            
    except Exception as e:
        print(f"Error en login: {e}")
        return jsonify({"error": "Error interno del servidor"}, 500)
    finally:
        if conn: conn.close()


# --- RUTAS PROTEGIDAS ---

## Ruta para OBTENER todos los Clientes (Requiere Login)
@app.route('/clientes', methods=['GET'])
@jwt_required() # <--- Pone el requisito de tener un Token JWT
def get_clientes():
    current_user_claims = get_jwt()
    rol = current_user_claims['rol']
    
    # 1. Autorización: Si solo queremos que empleados y administradores vean la lista completa
    if rol not in ['empleado', 'administrador']:
        return jsonify({"error": "Acceso denegado. Solo Empleados pueden listar todos los clientes."}, 403)
    
    # ... (El código SQL existente sigue aquí) ...
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Ejecutar la consulta SQL (puedes usar la misma)
        query = """
            SELECT 
                p.nombre, p.apellido_paterno, c.fecha_registro
            FROM 
                Persona p 
            JOIN 
                Cliente c ON p.id_persona = c.persona_id;
        """
        cur.execute(query)
        
        column_names = [desc[0] for desc in cur.description]
        clientes = [dict(zip(column_names, row)) for row in cur.fetchall()]
        
        cur.close()
        return jsonify(clientes)

    except Exception as e:
        # ... (Manejo de errores) ...
        if conn:
            conn.rollback() 
        print(f"Error al obtener clientes: {e}")
        return jsonify({"error": "Error interno del servidor"}, 500)
    finally:
        if conn:
            conn.close()


## Ruta para ELIMINAR un Cliente por ID (Protegida)
@app.route('/clientes/<int:cliente_id>', methods=['DELETE'])
@jwt_required() # <--- Pone el requisito de tener un Token JWT
def delete_cliente(cliente_id):
    current_user_claims = get_jwt()
    rol = current_user_claims['rol']
    
    # 1. Autorización: Solo Empleados o Administradores pueden eliminar
    if rol not in ['empleado', 'administrador']:
        return jsonify({"error": "Acceso denegado. Rol insuficiente para eliminar."}, 403)
        
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        # Usamos ON DELETE CASCADE, así que borrar de Persona es suficiente
        delete_query = "DELETE FROM Persona WHERE id_persona = %s RETURNING id_persona;"
        cur.execute(delete_query, (cliente_id,))
        
        # Verificar si se eliminó alguna fila
        if cur.rowcount == 0:
            conn.rollback()
            return jsonify({"error": f"Cliente con ID {cliente_id} no encontrado."}, 404)

        conn.commit()
        cur.close()
        return jsonify({"message": f"Cliente con ID {cliente_id} eliminado exitosamente"}), 200

    except Exception as e:
        # ... (Manejo de errores) ...
        if conn:
            conn.rollback() 
        print(f"Error al eliminar cliente: {e}")
        return jsonify({"error": "Error interno del servidor al eliminar cliente"}, 500)
    finally:
        if conn:
            conn.close()

# ... (La ruta POST /clientes debe ser protegida también, te la dejo de tarea!) ...

# --- Inicio del Servidor ---
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000)) 
    app.run(debug=True, host='0.0.0.0', port=port)