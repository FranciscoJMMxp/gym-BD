# app.py
import os
import psycopg2
from dotenv import load_dotenv
from flask import Flask, jsonify, request

# Cargar variables de entorno (solo para desarrollo local)
# Render usará las variables que configures directamente en su plataforma.
load_dotenv() 

app = Flask(__name__)

# --- Función de Conexión a la Base de Datos ---
def get_db_connection():
    # Usar la variable de entorno DATABASE_URL que obtuviste de Neon
    # y que configurarás en Render.
    db_url = os.environ.get('DATABASE_URL')
    if not db_url:
        # Esto debería fallar si no estás en Render y no tienes .env configurado
        raise Exception("DATABASE_URL no está configurada")
        
    conn = psycopg2.connect(db_url)
    return conn

# --- Rutas de la API (Endpoints) ---

## Ruta para OBTENER todos los Clientes (GET)
@app.route('/clientes', methods=['GET'])
def get_clientes():
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Ejecutar la consulta SQL
        query = """
            SELECT 
                p.nombre, p.apellido_paterno, c.fecha_registro
            FROM 
                Persona p 
            JOIN 
                Cliente c ON p.id_persona = c.persona_id;
        """
        cur.execute(query)
        
        # Obtener los resultados y sus nombres de columna
        column_names = [desc[0] for desc in cur.description]
        clientes = [dict(zip(column_names, row)) for row in cur.fetchall()]
        
        cur.close()
        return jsonify(clientes)

    except Exception as e:
        print(f"Error al obtener clientes: {e}")
        return jsonify({"error": "Error interno del servidor"}, 500)
    finally:
        if conn:
            conn.close()


## Ruta para AGREGAR una nueva Persona/Cliente (POST)
@app.route('/clientes', methods=['POST'])
def add_cliente():
    data = request.get_json()
    nombre = data.get('nombre')
    apellido_paterno = data.get('apellido_paterno')

    if not nombre:
        return jsonify({"error": "Se requiere el nombre"}, 400)

    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        # 1. Insertar en la tabla Persona
        insert_persona = "INSERT INTO Persona (nombre, apellido_paterno) VALUES (%s, %s) RETURNING id_persona;"
        cur.execute(insert_persona, (nombre, apellido_paterno))
        persona_id = cur.fetchone()[0]

        # 2. Insertar en la tabla Cliente (usando la llave generada)
        insert_cliente = "INSERT INTO Cliente (persona_id) VALUES (%s);"
        cur.execute(insert_cliente, (persona_id,))

        conn.commit() # Guardar los cambios en la DB
        cur.close()
        return jsonify({"message": "Cliente agregado exitosamente", "id": persona_id}, 201)

    except Exception as e:
        # Si algo falla, hacer rollback para deshacer la Persona si se insertó sola
        if conn:
            conn.rollback() 
        print(f"Error al agregar cliente: {e}")
        return jsonify({"error": "Error al procesar la solicitud"}, 500)
    finally:
        if conn:
            conn.close()

# --- Inicio del Servidor ---
if __name__ == '__main__':
    # Render usa la variable de entorno 'PORT'
    port = int(os.environ.get('PORT', 5000)) 
    app.run(debug=True, host='0.0.0.0', port=port)