import numpy as np
import statsapi
import sqlite3
from datetime import datetime

# ==========================================
# 1. SISTEMA DE AUTOAPRENDIZAJE Y CALIBRACIÓN
# ==========================================

def inicializar_bd_aprendizaje():
    """Inicializa la base de datos local para la memoria histórica de los equipos."""
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
    """Obtiene el factor de calibración real aprendido del historial del equipo."""
    inicializar_bd_aprendizaje()
    conn = sqlite3.connect('mlb_aprendizaje.db')
    cursor = conn.cursor()
    cursor.execute('SELECT factor_confianza FROM factor_equipos WHERE equipo = ?', (equipo,))
    resultado = cursor.fetchone()
    conn.close()
    
    if resultado:
        return resultado[0]
    return 1.00

def registrar_prediccion_bd(partido, equipo_elegido, probabilidad):
    """Registra la predicción real en la memoria de la IA."""
    inicializar_bd_aprendizaje()
    conn = sqlite3.connect('mlb_aprendizaje.db')
    cursor = conn.cursor()
    fecha_hoy = datetime.now().strftime('%Y-%m-%d')
    
    cursor.execute('''
        INSERT INTO predicciones_historicas (fecha, partido, equipo_elegido, probabilidad_modelo, resultado_real)
        VALUES (?, ?, ?, ?, 'PENDIENTE')
    ''', (fecha_hoy, partido, equipo_elegido, probabilidad))
    
    cursor.execute('''
        INSERT OR IGNORE INTO factor_equipos (equipo, aciertos, fallos, factor_confianza)
        VALUES (?, 0, 0, 1.00)
    ''', (equipo_elegido,))
    
    conn.commit()
    conn.close()


# ==========================================
# 2. MOTOR DE CÁLCULO Y MACHINE LEARNING
# ==========================================

def calcular_fip(hr, bb, hbp, so, ip):
    """
    Calcula el Fielding Independent Pitching (FIP) aproximado.
    Fórmula estándar: ((13 * HR) + (3 * (BB + HBP)) - (2 * SO)) / IP + FIP_constant
    Usamos una constante estándar de la liga de 3.20.
    """
    if ip <= 0:
        return 4.00 # Valor por defecto seguro
    fip_constant = 3.20
    fip = ((13 * hr) + (3 * (bb + hbp)) - (2 * so)) / ip + fip_constant
    return max(fip, 2.00) # Evitar valores negativos o irreales

def ejecutar_prediccion_ml(stats_local, stats_visit, pitcher_local_info, pitcher_visit_info, factor_estadio, lambda_local, lambda_visit, nombre_local="Local", nombre_visitante="Visitante"):
    """
    Motor de Machine Learning / Probabilístico mejorado con FIP, Monte Carlo y Autoaprendizaje por Equipo.
    """
    # 1. Ajuste de Lambda usando FIP si está disponible en la información del lanzador
    era_local = pitcher_local_info.get('era', 4.00)
    fip_local = pitcher_local_info.get('fip', era_local) # Si no hay FIP explícito, usa ERA
    
    era_visit = pitcher_visit_info.get('era', 4.00)
    fip_visit = pitcher_visit_info.get('fip', era_visit)
    
    # Combinamos ERA (70%) y FIP (30%) para tener una métrica de pitcheo robusta
    efectividad_ajustada_local = (era_local * 0.7) + (fip_local * 0.3)
    efectividad_ajustada_visit = (era_visit * 0.7) + (fip_visit * 0.3)
    
    # Recalcular lambdas con la efectividad ajustada
    factor_p_local = efectividad_ajustada_visit / 4.00
    factor_p_visit = efectividad_ajustada_local / 4.00
    
    # Promedio base ponderado por estadio usando datos reales
    juegos_local = max(stats_local.get('G', 1), 1)
    juegos_visit = max(stats_visit.get('G', 1), 1)
    
    carreras_base_local = (stats_local.get('R', 0) / juegos_local) * factor_p_local * factor_estadio
    carreras_base_visit = (stats_visit.get('R', 0) / juegos_visit) * factor_p_visit * factor_estadio
    
    # 2. Simulación de Monte Carlo (10,000 iteraciones) sin semilla fija para variabilidad real
    sims_local = np.random.poisson(max(carreras_base_local, 1.2), 10000)
    sims_visit = np.random.poisson(max(carreras_base_visit, 1.2), 10000)
    
    # Calcular porcentaje de victorias en la simulación
    victorias_local = np.sum(sims_local > sims_visit)
    empates = np.sum(sims_local == sims_visit)
    
    # Distribuir empates equitativamente
    prob_local = (victorias_local + (empates * 0.5)) / 10000.0
    
    # 3. Aplicar Calibración y Memoria de Autoaprendizaje Histórico por Equipo
    factor_apren_local = obtener_factor_equipo(nombre_local)
    factor_apren_visit = obtener_factor_equipo(nombre_visitante)
    
    prob_local_calibrada = prob_local * factor_apren_local
    prob_visit_calibrada = (1.0 - prob_local) * factor_apren_visit
    
    total_norm = prob_local_calibrada + prob_visit_calibrada
    if total_norm > 0:
        prob_local_final = prob_local_calibrada / total_norm
    else:
        prob_local_final = prob_local
    
    # Asegurar límites lógicos (entre 10% y 90%)
    prob_local_final = np.clip(prob_local_final, 0.10, 0.90)
    
    return float(prob_local_final)

def proyectar_ponches_lanzador(pitcher_k_per_9, innings_proyectados, rival_k_rate_promedio):
    """
    Proyecta los ponches esperados de un lanzador abridor.
    """
    if innings_proyectados <= 0:
        return 0.0
    
    k_segun_pitcher = (pitcher_k_per_9 / 9.0) * innings_proyectados
    factor_rival = rival_k_rate_promedio / 0.22
    ponches_esperados = k_segun_pitcher * factor_rival
    return round(ponches_esperados, 1)

def obtener_stats_pitcher_api(pitcher_input):
    """
    Busca al jugador en la API de la MLB por ID numérico o por Nombre y retorna sus stats.
    """
    try:
        # Si recibe un ID numérico directo de la boxscore
        if isinstance(pitcher_input, int) or (isinstance(pitcher_input, str) and pitcher_input.isdigit()):
            pid = int(pitcher_input)
            if pid == 0:
                return {"k9": 8.5, "era": 4.00, "fip": 4.00, "nombre": "TBD"}
            stats = statsapi.player_stat_data(pid, group="pitching", type="season")
            nombre_res = str(pid)
        else:
            # Si recibe un nombre en texto
            players = statsapi.lookup_player(pitcher_input)
            if not players:
                return {"k9": 8.5, "era": 4.00, "fip": 4.00, "nombre": str(pitcher_input)}
            pid = players[0]['id']
            stats = statsapi.player_stat_data(pid, group="pitching", type="season")
            nombre_res = players[0]['fullName']
        
        k9 = 8.5
        era = 4.00
        for s in stats.get('stats', []):
            if 'strikeOutsPer9Inn' in s.get('stats', {}):
                k9 = float(s['stats']['strikeOutsPer9Inn'])
            if 'earnedRunAverage' in s.get('stats', {}):
                era = float(s['stats']['earnedRunAverage'])
                
        return {"k9": round(k9, 2), "era": round(era, 2), "fip": era, "nombre": nombre_res}
    except:
        return {"k9": 8.5, "era": 4.00, "fip": 4.00, "nombre": str(pitcher_input)}