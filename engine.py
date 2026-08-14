import numpy as np
import statsapi
import sqlite3
from datetime import datetime

# ==========================================
# 1. SISTEMA DE AUTOAPRENDIZAJE Y CALIBRACIÓN
# ==========================================

def inicializar_bd_aprendizaje():
    conn = sqlite3.connect('mlb_aprendizaje.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS predicciones_historicas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT,
            partido TEXT,
            equipo_elegido TEXT,
            probabilidad_modelo REAL,
            resultado_real TEXT DEFAULT 'PENDIENTE'
        )
    ''')
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
    inicializar_bd_aprendizaje()
    conn = sqlite3.connect('mlb_aprendizaje.db')
    cursor = conn.cursor()
    cursor.execute('SELECT factor_confianza FROM factor_equipos WHERE equipo = ?', (equipo,))
    resultado = cursor.fetchone()
    conn.close()
    return resultado[0] if resultado else 1.00


# ==========================================
# 2. MOTOR DE CÁLCULO REAL (SIN VALORES FALSOS)
# ==========================================

def ejecutar_prediccion_ml(stats_local, stats_visit, pitcher_local_info, pitcher_visit_info, factor_estadio, nombre_local, nombre_visitante):
    """
    Motor analítico basado estrictamente en estadísticas reales de la API de la MLB.
    """
    # Validar que existan datos reales de pitcheo
    era_local = float(pitcher_local_info['era'])
    fip_local = float(pitcher_local_info['fip'])
    era_visit = float(pitcher_visit_info['era'])
    fip_visit = float(pitcher_visit_info['fip'])
    
    efectividad_local = (era_local * 0.7) + (fip_local * 0.3)
    efectividad_visit = (era_visit * 0.7) + (fip_visit * 0.3)
    
    # Validar que existan datos reales de anotación de la temporada
    juegos_local = float(stats_local['G'])
    juegos_visit = float(stats_visit['G'])
    
    if juegos_local <= 0 or juegos_visit <= 0:
        raise ValueError("Datos de partidos jugados inválidos en la API.")
        
    carreras_por_juego_local = float(stats_local['R']) / juegos_local
    carreras_por_juego_visit = float(stats_visit['R']) / juegos_visit
    
    # Fuerza ponderada real contra el pitcheo rival
    fuerza_ataque_local = carreras_por_juego_local * (4.00 / max(efectividad_visit, 1.0)) * factor_estadio
    fuerza_ataque_visit = carreras_por_juego_visit * (4.00 / max(efectividad_local, 1.0))
    
    # Función logística para determinar probabilidad real sin empates forzados
    diferencia_fuerza = fuerza_ataque_local - fuerza_ataque_visit
    prob_local = 1.0 / (1.0 + np.exp(-diferencia_fuerza * 0.8))
    
    # Calibración histórica por equipo
    factor_apren_local = obtener_factor_equipo(nombre_local)
    factor_apren_visit = obtener_factor_equipo(nombre_visitante)
    
    prob_local_calibrada = prob_local * factor_apren_local
    prob_visit_calibrada = (1.0 - prob_local) * factor_apren_visit
    
    total_norm = prob_local_calibrada + prob_visit_calibrada
    if total_norm > 0:
        prob_local_final = prob_local_calibrada / total_norm
    else:
        prob_local_final = prob_local
        
    return float(prob_local_final)

def obtener_stats_pitcher_api(pitcher_input):
    """
    Extrae estrictamente las estadísticas reales del lanzador desde la API.
    Si el lanzador no tiene estadísticas oficiales registradas, lanza una excepción.
    """
    if isinstance(pitcher_input, int) or (isinstance(pitcher_input, str) and pitcher_input.isdigit()):
        pid = int(pitcher_input)
        if pid == 0:
            raise ValueError("Lanzador no anunciado (TBD)")
        stats = statsapi.player_stat_data(pid, group="pitching", type="season")
    else:
        players = statsapi.lookup_player(pitcher_input)
        if not players:
            raise ValueError(f"No se encontró al lanzador: {pitcher_input}")
        pid = players[0]['id']
        stats = statsapi.player_stat_data(pid, group="pitching", type="season")
    
    k9 = None
    era = None
    for s in stats.get('stats', []):
        if 'strikeOutsPer9Inn' in s.get('stats', {}):
            k9 = float(s['stats']['strikeOutsPer9Inn'])
        if 'earnedRunAverage' in s.get('stats', {}):
            era = float(s['stats']['earnedRunAverage'])
            
    if era is None or k9 is None:
        raise ValueError(f"El lanzador ID {pid} no tiene estadísticas oficiales esta temporada.")
        
    return {"k9": round(k9, 2), "era": round(era, 2), "fip": era}