import sqlite3
from datetime import datetime

def inicializar_bd_aprendizaje():
    conn = sqlite3.connect('mlb_aprendizaje.db')
    cursor = conn.cursor()
    
    # Tabla para registrar cada predicción hecha
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS predicciones_historicas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT,
            partido TEXT,
            equipo_elegido TEXT,
            probabilidad_modelo REAL,
            resultado_real TEXT DEFAULT 'PENDIENTE' -- 'ACIERTO', 'FALLO', 'PENDIENTE'
        )
    ''')
    
    # Tabla de confianza/calibración por equipo
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS factor_equipos (
            equipo TEXT PRIMARY KEY,
            aciertos INTEGER DEFAULT 0,
            fallos INTEGER DEFAULT 0,
            factor_confianza REAL DEFAULT 1.00
        )
    ''')
    conn.commit()
    conn.close()

def obtener_factor_equipo(equipo):
    """Obtiene el factor de calibración actual del equipo (aprende de sus aciertos/fallos)"""
    conn = sqlite3.connect('mlb_aprendizaje.db')
    cursor = conn.cursor()
    cursor.execute('SELECT factor_confianza FROM factor_equipos WHERE equipo = ?', (equipo,))
    resultado = cursor.fetchone()
    conn.close()
    
    if resultado:
        return resultado[0]
    return 1.00 # Factor neutral por defecto

def registrar_prediccion(partido, equipo_elegido, probabilidad):
    """Guarda la predicción del día para evaluarla después"""
    conn = sqlite3.connect('mlb_aprendizaje.db')
    cursor = conn.cursor()
    fecha_hoy = datetime.now().strftime('%Y-%m-%d')
    
    cursor.execute('''
        INSERT INTO predicciones_historicas (fecha, partido, equipo_elegido, probabilidad_modelo, resultado_real)
        VALUES (?, ?, ?, ?, 'PENDIENTE')
    ''', (fecha_hoy, partido, equipo_elegido, probabilidad))
    
    # Asegurarnos de que el equipo exista en la tabla de factores
    cursor.execute('''
        INSERT OR IGNORE INTO factor_equipos (equipo, aciertos, fallos, factor_confianza)
        VALUES (?, 0, 0, 1.00)
    ''', (equipo_elegido,))
    
    conn.commit()
    conn.close()

def actualizar_aprendizaje(prediccion_id, acerto: bool, equipo):
    """Actualiza la confianza del equipo basado en si el modelo acertó o falló"""
    conn = sqlite3.connect('mlb_aprendizaje.db')
    cursor = conn.cursor()
    
    resultado = 'ACIERTO' if acerto else 'FALLO'
    cursor.execute('UPDATE predicciones_historicas SET resultado_real = ? WHERE id = ?', (resultado, prediccion_id))
    
    # Ajustamos el factor de confianza del equipo gradualmente
    cursor.execute('SELECT aciertos, fallos, factor_confianza FROM factor_equipos WHERE equipo = ?', (equipo,))
    row = cursor.fetchone()
    
    if row:
        aciertos, fallos, factor = row
        if acerto:
            aciertos += 1
            factor = min(factor + 0.02, 1.25) # Sube confianza ligeramente (tope 1.25)
        else:
            fallos += 1
            factor = max(factor - 0.03, 0.75) # Baja confianza si falló (piso 0.75)
            
        cursor.execute('''
            UPDATE factor_equipos 
            SET aciertos = ?, fallos = ?, factor_confianza = ?
            WHERE equipo = ?
        ''', (aciertos, fallos, factor, equipo))
        
    conn.commit()
    conn.close()