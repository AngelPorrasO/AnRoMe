# bankroll_manager.py
import sqlite3

DB_NAME = "mlb_predictions.db"

def obtener_balance():
    conn = sqlite3.connect(DB_NAME)
    # Creamos la tabla si no existe al vuelo
    conn.execute("CREATE TABLE IF NOT EXISTS bankroll (id INTEGER PRIMARY KEY, balance REAL)")
    cursor = conn.execute("SELECT balance FROM bankroll WHERE id = 1")
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else 1000.0  # Balance inicial por defecto $1000

def registrar_apuesta(monto, tipo, resultado):
    conn = sqlite3.connect(DB_NAME)
    # Tabla para llevar registro de apuestas hechas
    conn.execute('''CREATE TABLE IF NOT EXISTS apuestas_historial (
        id INTEGER PRIMARY KEY AUTOINCREMENT, 
        monto REAL, tipo TEXT, resultado TEXT)''')
    conn.execute("INSERT INTO apuestas_historial (monto, tipo, resultado) VALUES (?, ?, ?)", 
                 (monto, tipo, resultado))
    
    # Actualizar balance
    if resultado == "Ganada":
        conn.execute("UPDATE bankroll SET balance = balance + ? WHERE id = 1", (monto*0.9,))
    else:
        conn.execute("UPDATE bankroll SET balance = balance - ? WHERE id = 1", (monto,))
    conn.commit()
    conn.close()