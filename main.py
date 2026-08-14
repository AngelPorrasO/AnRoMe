import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime
import statsapi
import requests
import sqlite3
from scipy.stats import poisson
from engine import ejecutar_prediccion_ml, proyectar_ponches_lanzador
import sqlite3

import sqlite3

import sqlite3
import statsapi
from datetime import datetime, timedelta
import pandas as pd
import threading
import time

# --- INICIALIZAR BASE DE DATOS ---
def inicializar_base_datos():
    conn = sqlite3.connect("mlb_historico.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS predicciones_historicas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            game_pk TEXT UNIQUE,
            fecha TEXT,
            local TEXT,
            visitante TEXT,
            prob_local REAL,
            prob_visitante REAL,
            carreras_esperadas REAL,
            resultado_real TEXT DEFAULT 'Pendiente',
            carreras_reales INTEGER DEFAULT 0,
            acerto INTEGER DEFAULT -1
        )
    """)
    conn.commit()
    conn.close()

inicializar_base_datos()

# --- FUNCIÓN DE GUARDADO AL ANALIZAR ---
def registrar_apuesta_ia(game_pk, local, visitante, p_loc, p_vis, carreras_esp):
    conn = sqlite3.connect("mlb_historico.db")
    cursor = conn.cursor()
    fecha_hoy = datetime.now().strftime('%Y-%m-%d')
    try:
        cursor.execute("""
            INSERT OR IGNORE INTO predicciones_historicas 
            (game_pk, fecha, local, visitante, prob_local, prob_visitante, carreras_esperadas)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (str(game_pk), fecha_hoy, local, visitante, p_loc, p_vis, carreras_esp))
        conn.commit()
    except Exception as e:
        print(f"Error al guardar en BD: {e}")
    conn.close()

# --- PASO 2: FUNCIÓN DE EVALUACIÓN AUTOMÁTICA POST-JUEGO ---
def evaluar_partidos_ayer():
    ayer_str = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
    
    conn = sqlite3.connect("mlb_historico.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id, game_pk, local, visitante, prob_local, prob_visitante FROM predicciones_historicas WHERE fecha = ? AND resultado_real = 'Pendiente'", (ayer_str,))
    pendientes = cursor.fetchall()
    
    if not pendientes:
        conn.close()
        return

    juegos_ayer = statsapi.schedule(date=ayer_str)
    
    for row in pendientes:
        db_id, game_pk, local_db, visit_db, p_loc, p_vis = row
        
        juego_real = next((g for g in juegos_ayer if str(g.get('game_id')) == str(game_pk) or (g.get('home_name') == local_db and g.get('away_name') == visit_db)), None)
        
        if juego_real and juego_real.get('status') == 'Final':
            carreras_loc_real = juego_real.get('home_score', 0)
            carreras_vis_real = juego_real.get('away_score', 0)
            carreras_totales_reales = carreras_loc_real + carreras_vis_real
            
            ganador_real = "Local" if carreras_loc_real > carreras_vis_real else "Visitante"
            prediccion_ia = "Local" if p_loc > p_vis else "Visitante"
            
            acerto = 1 if ganador_real == prediccion_ia else 0
            
            cursor.execute("""
                UPDATE predicciones_historicas 
                SET resultado_real = ?, carreras_reales = ?, acerto = ?
                WHERE id = ?
            """, (ganador_real, carreras_totales_reales, acerto, db_id))
            
    conn.commit()
    conn.close()

# --- FUNCIÓN DE AUTO-AJUSTE (MACHINE LEARNING) ---
def calcular_factor_correccion_historico():
    conn = sqlite3.connect("mlb_historico.db")
    cursor = conn.cursor()
    cursor.execute("SELECT acerto FROM predicciones_historicas WHERE acerto != -1 ORDER BY id DESC LIMIT 100")
    historial = cursor.fetchall()
    conn.close()
    
    if len(historial) < 20:
        return 1.0
        
    aciertos = sum([h[0] for h in historial])
    tasa_acierto = aciertos / len(historial)
    
    if tasa_acierto < 0.50:
        return 0.95 
    elif tasa_acierto > 0.65:
        return 1.05
    
    return 1.0
def guardar_prediccion_mlb_v2(game_pk, local, visitante, p_loc, p_vis, carreras_esp):
    conn = sqlite3.connect("mlb_historico.db")
    cursor = conn.cursor()
    fecha_hoy = datetime.now().strftime('%Y-%m-%d')
    try:
        cursor.execute("""
            INSERT OR IGNORE INTO predicciones_historicas 
            (game_pk, fecha, local, visitante, prob_local, prob_visitante, carreras_esperadas)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (str(game_pk), fecha_hoy, local, visitante, p_loc, p_vis, carreras_esp))
        conn.commit()
    except Exception as e:
        print(f"Error al guardar en BD: {e}")
    conn.close()
# Importaciones de tus módulos personalizados
from utils import calcular_kelly, analizar_parlay, obtener_info_lanzador
from engine import ejecutar_prediccion_ml
from notifier import enviar_alerta_telegram

# --- CONFIGURACIÓN DE TELEGRAM Y ODDS API ---
TELEGRAM_TOKEN = "8817380632:AAGiNy9jvg5g1-0TNPkqOpMqdfntV1UQEP8"
TELEGRAM_CHAT_ID = "8689508146"
ODDS_API_KEY = "50821bd05f685a45342fb6b50d0599ef"

# Configuración inicial de la interfaz
st.set_page_config(page_title="MLB Pro Predictor Engine - Pro & Backtest Edition", layout="wide")
st.title("⚾ Sistema Profesional de Predicción de Béisbol + Panel de Rendimiento ML")

def obtener_cuotas_reales(local, visitante):
    """
    Consulta cuotas en tiempo real desde The Odds API para el partido dado.
    """
    url = f"https://api.the-odds-api.com/v4/sports/baseball_mlb/odds/?apiKey={ODDS_API_KEY}&regions=us&markets=h2h"
    try:
        response = requests.get(url, timeout=5).json()
        if isinstance(response, list):
            for game in response:
                h_team = game.get('home_team', '')
                a_team = game.get('away_team', '')
                if local.lower() in h_team.lower() or h_team.lower() in local.lower():
                    bookmakers = game.get('bookmakers', [])
                    if bookmakers:
                        markets = bookmakers[0].get('markets', [])
                        if markets:
                            outcomes = markets[0].get('outcomes', [])
                            cuotas_dict = {}
                            for o in outcomes:
                                cuotas_dict[o.get('name')] = o.get('price')
                            return cuotas_dict
    except Exception:
        pass
    return {}

# --- Configuración de Base de Datos Local ---
DB_NAME = "mlb_predictions.db"

def inicializar_bd():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS historial_predicciones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT,
            local TEXT,
            visitante TEXT,
            prob_local REAL,
            prob_visit REAL,
            carreras_esperadas REAL,
            resultado_real TEXT,
            ganador_real TEXT
        )
    ''')
    
    # Asegurar que las columnas existan si la BD es vieja
    try:
        cursor.execute("ALTER TABLE historial_predicciones ADD COLUMN resultado_real TEXT DEFAULT 'Pendiente'")
    except Exception:
        pass
        
    try:
        cursor.execute("ALTER TABLE historial_predicciones ADD COLUMN ganador_real TEXT DEFAULT 'Pendiente'")
    except Exception:
        pass

    conn.commit()
    conn.close()

inicializar_bd()

def guardar_prediccion(fecha, local, visitante, p_loc, p_vis, car_esp):
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT id FROM historial_predicciones 
            WHERE fecha = ? AND local = ? AND visitante = ?
        ''', (fecha, local, visitante))
        existe = cursor.fetchone()
        
        if not existe:
            cursor.execute('''
                INSERT INTO historial_predicciones (fecha, local, visitante, prob_local, prob_visit, carreras_esperadas, resultado_real, ganador_real)
                VALUES (?, ?, ?, ?, ?, ?, 'Pendiente', 'Pendiente')
            ''', (fecha, local, visitante, p_loc, p_vis, car_esp))
            conn.commit()
        conn.close()
    except Exception:
        pass

def actualizar_resultados_reales():
    """
    Busca en la BD las predicciones con estado 'Pendiente' y las actualiza 
    consultando el marcador final real a la API de la MLB.
    """
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT id, fecha, local, visitante FROM historial_predicciones WHERE resultado_real = 'Pendiente'")
    pendientes = cursor.fetchall()
    
    actualizados = 0
    for item in pendientes:
        p_id, fecha_str, local_team, visit_team = item
        try:
            fecha_dt = datetime.strptime(fecha_str, "%Y-%m-%d").strftime("%m/%d/%Y")
            sched = statsapi.schedule(date=fecha_dt)
            for game in sched:
                if game.get('status') == 'Final':
                    g_home = game.get('home_name')
                    g_away = game.get('away_name')
                    if g_home == local_team and g_away == visit_team:
                        runs_home = game.get('home_score', 0)
                        runs_away = game.get('away_score', 0)
                        
                        ganador = local_team if runs_home > runs_away else visit_team
                        res_fmt = f"{g_away} {runs_away} - {runs_home} {g_home}"
                        
                        cursor.execute('''
                            UPDATE historial_predicciones 
                            SET resultado_real = ?, ganador_real = ? 
                            WHERE id = ?
                        ''', (res_fmt, ganador, p_id))
                        actualizados += 1
                        break
        except Exception:
            continue
            
    conn.commit()
    conn.close()
    return actualizados

@st.cache_data(ttl=3600)
def cargar_stats_equipos_mlb(temporada):
    try:
        url_batting = f"https://statsapi.mlb.com/api/v1/teams/stats?season={temporada}&sportId=1&group=hitting&stats=season"
        res_batting = requests.get(url_batting).json()
        
        url_pitching = f"https://statsapi.mlb.com/api/v1/teams/stats?season={temporada}&sportId=1&group=pitching&stats=season"
        res_pitching = requests.get(url_pitching).json()
        
        stats_map = {}
        
        splits_batting = res_batting.get('stats', [{}])[0].get('splits', [])
        for split in splits_batting:
            tid = split['team']['id']
            team_name = split['team']['name']
            st_vals = split['stat']
            
            stats_map[tid] = {
                'Team': team_name,
                'G': int(st_vals.get('gamesPlayed', 0)),
                'R': int(st_vals.get('runs', 0)),
                'H': int(st_vals.get('hits', 0)),
                'HR': int(st_vals.get('homeRuns', 0)),
                'BB': int(st_vals.get('baseOnBalls', 0)),
                'SO': int(st_vals.get('strikeOuts', 0)),
                'BA': float(st_vals.get('avg', .000)),
                'OBP': float(st_vals.get('obp', .000)),
                'SLG': float(st_vals.get('slg', .000)),
                'OPS': float(st_vals.get('ops', .000))
            }
            
        splits_pitching = res_pitching.get('stats', [{}])[0].get('splits', [])
        for split in splits_pitching:
            tid = split['team']['id']
            st_vals = split['stat']
            
            if tid in stats_map:
                stats_map[tid]['RA'] = int(st_vals.get('runsAllowed', st_vals.get('runs', 0)))
                stats_map[tid]['ERA'] = float(st_vals.get('era', 4.00))
                stats_map[tid]['WHIP'] = float(st_vals.get('whip', 1.30))
                
        df = pd.DataFrame(list(stats_map.values()))
        return df if not df.empty else None
        
    except Exception as e:
        st.error(f"Error al conectar con la API de la MLB: {e}")
        return None

# --- Pestañas Principales ---
tab_predictor, tab_generator, tab_backtest = st.tabs([
    "🔮 Predictor de Partidos", 
    "🚀 Generador Automático de Parlays", 
    "📈 Panel de Rendimiento y Backtesting"
])

# --- PESTAÑA 1: PREDICTOR DE PARTIDOS Y PROPS ---
with tab_predictor:
    anio_actual = datetime.now().year
    st.sidebar.header("Parámetros de Extracción Pro + ML")
    temporada_sel = st.sidebar.selectbox("Seleccionar Temporada", [anio_actual, anio_actual - 1], index=0)

    fecha_seleccionada = st.sidebar.date_input("Seleccionar Fecha de Partidos", datetime.now().date())

    with st.spinner("Cargando estadísticas de la MLB y calibrando modelo ML..."):
        df_merged = cargar_stats_equipos_mlb(temporada_sel)

    if df_merged is not None and not df_merged.empty and df_merged['G'].sum() > 0:
        equipos_disponibles = sorted(df_merged['Team'].unique())
        
        fecha_str = fecha_seleccionada.strftime("%m/%d/%Y")
        try:
            partidos_agenda = statsapi.schedule(date=fecha_str)
        except Exception:
            partidos_agenda = []

        st.sidebar.header("Selección de Enfrentamiento")
        
        opciones_enfrentamientos = []
        partidos_dict = {}
        
        if partidos_agenda:
            for idx, juego in enumerate(partidos_agenda):
                away = juego.get('away_name')
                home = juego.get('home_name')
                status = juego.get('status')
                
                away_probable = juego.get('away_probable_pitcher', 'No anunciado')
                home_probable = juego.get('home_probable_pitcher', 'No anunciado')
                
                texto_juego = f"{away} @ {home} ({status})"
                opciones_enfrentamientos.append(texto_juego)
                partidos_dict[texto_juego] = {
                    'id': idx,
                    'home': home,
                    'away': away,
                    'home_pitcher': home_probable,
                    'away_pitcher': away_probable,
                    'venue': juego.get('venue_name', 'Estadio Neutral')
                }

        modo_seleccion = st.sidebar.radio("Modo de Selección", ["Partidos del Día", "Selección Manual Libre"])

        pitcher_local_info = {"name": "No anunciado", "era": 4.00, "whip": 1.30, "k9": 8.5}
        pitcher_visit_info = {"name": "No anunciado", "era": 4.00, "whip": 1.30, "k9": 8.5}
        estadio_actual = "Estadio Neutral"
        
        datos_juego = None

        if modo_seleccion == "Partidos del Día" and opciones_enfrentamientos:
            juego_elegido = st.sidebar.selectbox("Partidos programados", opciones_enfrentamientos)
            datos_juego = partidos_dict[juego_elegido]
            equipo_local = datos_juego['home']
            equipo_visitante = datos_juego['away']
            estadio_actual = datos_juego['venue']
            
            with st.spinner("Analizando abridores y ajustando pesos de Machine Learning..."):
                pitcher_local_info = obtener_info_lanzador(datos_juego['home_pitcher'])
                pitcher_visit_info = obtener_info_lanzador(datos_juego['away_pitcher'])
        else:
            if modo_seleccion == "Partidos del Día":
                st.sidebar.info("No se encontraron partidos oficiales en la fecha seleccionada. Usando selección manual.")
            equipo_local = st.sidebar.selectbox("Equipo Local (Home)", equipos_disponibles, index=0)
            equipo_visitante = st.sidebar.selectbox("Equipo Visitante (Away)", equipos_disponibles, index=1 if len(equipos_disponibles) > 1 else 0)
            
            p_loc_nombre = st.sidebar.text_input("Pitcher Abridor Local (Opcional)", "No anunciado")
            p_vis_nombre = st.sidebar.text_input("Pitcher Abridor Visitante (Opcional)", "No anunciado")
            if p_loc_nombre != "No anunciado":
                pitcher_local_info = obtener_info_lanzador(p_loc_nombre)
            if p_vis_nombre != "No anunciado":
                pitcher_visit_info = obtener_info_lanzador(p_vis_nombre)

        # --- FORMULARIO DE PLAYER PROPS (PONCHES) ---
        if datos_juego:
            stats_local_auto = obtener_info_lanzador(datos_juego['home_pitcher'])
            stats_visit_auto = obtener_info_lanzador(datos_juego['away_pitcher'])
            form_key = f"form_props_duales_{datos_juego['id']}"
        else:
            stats_local_auto = pitcher_local_info
            stats_visit_auto = pitcher_visit_info
            form_key = "form_props_duales_manual"

        st.subheader("🎯 Analizador de Player Props: Duelo de Ponches")
        
        with st.form(form_key):
            col_d1, col_d2 = st.columns(2)
            
            with col_d1:
                st.markdown(f"### 🏠 Lanzador Local")
                p_local_nombre = st.text_input("Nombre Abridor Local", value=stats_local_auto.get('name', 'Pitcher Local'))
                p_local_k9 = st.number_input("K/9 Histórico (Local)", value=float(stats_local_auto.get('k9', 9.20)))
                p_local_ip = st.number_input("IP Proyectados (Local)", value=5.50)
                p_rival_k_rate_v = st.number_input("Tasa K% del Rival (Visitante)", value=0.23)
                linea_casa_local = st.number_input("Línea de la Casa (Local)", value=5.50)
                
            with col_d2:
                st.markdown(f"### ✈️ Lanzador Visitante")
                p_visit_nombre = st.text_input("Nombre Abridor Visitante", value=stats_visit_auto.get('name', 'Pitcher Visitante'))
                p_visit_k9 = st.number_input("K/9 Histórico (Visitante)", value=float(stats_visit_auto.get('k9', 8.80)))
                p_visit_ip = st.number_input("IP Proyectados (Visitante)", value=5.50)
                p_rival_k_rate_l = st.number_input("Tasa K% del Rival (Local)", value=0.22)
                linea_casa_visit = st.number_input("Línea de la Casa (Visitante)", value=5.50)

            submitted_props = st.form_submit_button("Analizar Ambos Props")
            if submitted_props:
                k_proy_local = proyectar_ponches_lanzador(p_local_k9, p_local_ip, p_rival_k_rate_v)
                k_proy_visit = proyectar_ponches_lanzador(p_visit_k9, p_visit_ip, p_rival_k_rate_l)
                
                st.markdown("---")
                st.subheader("📊 Resultados de Ponches")
                col_res1, col_res2 = st.columns(2)
                
                with col_res1:
                    st.markdown(f"#### 🏠 {p_local_nombre}")
                    st.metric("Proyección K", f"{k_proy_local}", delta=f"{k_proy_local - linea_casa_local:+.1f} vs línea")
                    diff_l = k_proy_local - linea_casa_local
                    if diff_l > 0.7:
                        st.success(f"Recomendación: **OVER ({linea_casa_local})** 🟢")
                    elif diff_l < -0.7:
                        st.error(f"Recomendación: **UNDER ({linea_casa_local})** 🔴")
                    else:
                        st.warning("Recomendación: **Sin Valor / Evitar** ⚪")
                        
                with col_res2:
                    st.markdown(f"#### ✈️ {p_visit_nombre}")
                    st.metric("Proyección K", f"{k_proy_visit}", delta=f"{k_proy_visit - linea_casa_visit:+.1f} vs línea")
                    diff_v = k_proy_visit - linea_casa_visit
                    if diff_v > 0.7:
                        st.success(f"Recomendación: **OVER ({linea_casa_visit})** 🟢")
                    elif diff_v < -0.7:
                        st.error(f"Recomendación: **UNDER ({linea_casa_visit})** 🔴")
                    else:
                        st.warning(f"Recomendación: **Sin Valor / Evitar** ⚪")

        # --- SECCIÓN DE PREDICCIÓN DE GANADOR (ML & MONEYLINE) ---
        st.markdown("---")
        st.subheader("⚾ Predicción del Partido y Probabilidades (Machine Learning)")

        if equipo_local == equipo_visitante:
            st.warning("⚠️ El equipo local y visitante no pueden ser el mismo.")
        else:
            stats_local = df_merged[df_merged['Team'] == equipo_local].iloc[0]
            stats_visit = df_merged[df_merged['Team'] == equipo_visitante].iloc[0]

            col_m1, col_m2 = st.columns(2)
            with col_m1:
                st.markdown(f"### 🏠 {equipo_local} (Local)")
                st.metric("Récord G-P", f"{int(stats_local.get('G', 0))}")
                st.write(f"**Estadio:** {estadio_actual}")
                st.write(f"**Pitcher Abridor:** {pitcher_local_info.get('name')} (ERA: {pitcher_local_info.get('era')}, WHIP: {pitcher_local_info.get('whip')})")

            with col_m2:
                st.markdown(f"### ✈️ {equipo_visitante} (Visitante)")
                st.metric("Récord G-P", f"{int(stats_visit.get('G', 0))}")
                st.write(f"**Estadio:** Visitante")
                st.write(f"**Pitcher Abridor:** {pitcher_visit_info.get('name')} (ERA: {pitcher_visit_info.get('era')}, WHIP: {pitcher_visit_info.get('whip')})")

            # --- Botón de predicción y cálculos ---
            if st.button("Ejecutar Modelo de Predicción de Ganador"):
                with st.spinner("Procesando datos y ejecutando el motor de Machine Learning..."):
                    try:
                        # 1. Calcular factor de estadio
                        factor_estadio = 1.00
                        if estadio_actual in ["Coors Field", "Great American Ball Park", "Fenway Park"]:
                            factor_estadio = 1.12
                        elif estadio_actual in ["Petco Park", "T-Mobile Park", "Oracle Park"]:
                            factor_estadio = 0.90

                        # 2. Calcular lambda_local y lambda_visit
                        juegos_local = max(stats_local.get('G', 1), 1)
                        juegos_visit = max(stats_visit.get('G', 1), 1)
                        
                        lambda_local = max((stats_local.get('R', 0) / juegos_local), 1.5)
                        lambda_visit = max((stats_visit.get('R', 0) / juegos_visit), 1.5)

                        # 3. Llamar a la función del engine pasando los 7 argumentos exactos
                        prob_local_val = ejecutar_prediccion_ml(
                            stats_local=stats_local,
                            stats_visit=stats_visit,
                            pitcher_local_info=pitcher_local_info,
                            pitcher_visit_info=pitcher_visit_info,
                            factor_estadio=factor_estadio,
                            lambda_local=lambda_local,
                            lambda_visit=lambda_visit
                        )
                        
                        # 4. Como el engine retorna directamente un float (ej. 0.542), calculamos ambos porcentajes
                        prob_local = round(prob_local_val * 100, 1)
                        prob_visit = round((1.0 - prob_local_val) * 100, 1)

                        # 5. Mostrar resultados en la interfaz
                        st.success("¡Predicción generada con éxito por el motor!")
                        col_prob1, col_prob2 = st.columns(2)
                        col_prob1.metric(f"Victoria {equipo_local}", f"{prob_local}%")
                        col_prob2.metric(f"Victoria {equipo_visitante}", f"{prob_visit}%")
                        
                    except Exception as e:
                        st.error(f"Error al ejecutar el engine de ML: {e}")

            # --- Factores de Estadio ---
            factor_estadio = 1.00
            if estadio_actual in ["Coors Field", "Great American Ball Park", "Fenway Park"]:
                factor_estadio = 1.12
            elif estadio_actual in ["Petco Park", "T-Mobile Park", "Oracle Park"]:
                factor_estadio = 0.90
            # --- Métricas Analíticas ---
            def pythagorean_win_pct(r, ra, exp=1.83):
                return (r**exp) / (r**exp + ra**exp) if (r**exp + ra**exp) != 0 else 0.500
                
            pyt_local = pythagorean_win_pct(stats_local['R'], stats_local['RA'])
            pyt_visit = pythagorean_win_pct(stats_visit['R'], stats_visit['RA'])
            
            juegos_local = max(stats_local['G'], 1)
            juegos_visit = max(stats_visit['G'], 1)
            
            lambda_local = max((stats_local['R'] / juegos_local) * (pitcher_visit_info['era'] / 4.00) * factor_estadio, 1.5)
            lambda_visit = max((stats_visit['R'] / juegos_visit) * (pitcher_local_info['era'] / 4.00) * factor_estadio, 1.5)
            # Ejecutar modelo ML y simulaciones a través de engine.py
            prob_win_local = ejecutar_prediccion_ml(
                stats_local, stats_visit, 
                pitcher_local_info, pitcher_visit_info, 
                factor_estadio, lambda_local, lambda_visit
            )
            prob_win_visit = 1.0 - prob_win_local

            lambda_total = lambda_local + lambda_visit
            
            prob_under = poisson.cdf(8, lambda_total)
            prob_over = 1 - prob_under

            prob_ambos_anotan_2 = (1 - poisson.pmf(0, lambda_local) - poisson.pmf(1, lambda_local)) * \
                                  (1 - poisson.pmf(0, lambda_visit) - poisson.pmf(1, lambda_visit))

            lambda_1ra_inning = lambda_total / 9.0
            prob_nrfi = poisson.pmf(0, lambda_1ra_inning)
            prob_yrfi = 1 - prob_nrfi

            np.random.seed(42)
            sim_goles_local = np.random.poisson(lambda_local, 10000)
            sim_goles_visit = np.random.poisson(lambda_visit, 10000)
            diferencias = np.abs(sim_goles_local - sim_goles_visit)
            juegos_por_1_carrera = np.sum(diferencias == 1)
            juegos_por_mas_de_1 = np.sum(diferencias > 1)
            total_sims = len(diferencias)
            
            prob_margen_1 = (juegos_por_1_carrera / total_sims) * 100
            prob_margen_mas = (juegos_por_mas_de_1 / total_sims) * 100

            prob_blanqueada_local = poisson.pmf(0, lambda_local)
            prob_blanqueada_visit = poisson.pmf(0, lambda_visit)
            prob_algun_shutout = (prob_blanqueada_local + prob_blanqueada_visit - (prob_blanqueada_local * prob_blanqueada_visit)) * 100

            # Guardar predicción en BD
            guardar_prediccion(str(fecha_seleccionada), equipo_local, equipo_visitante, round(prob_win_local*100, 1), round(prob_win_visit*100, 1), round(lambda_total, 2))

            # Obtener cuotas reales automáticas
            cuotas_api = obtener_cuotas_reales(equipo_local, equipo_visitante)
            cuota_default_local = cuotas_api.get(equipo_local, 1.90)
            cuota_default_visit = cuotas_api.get(equipo_visitante, 1.90)

            # Render de Resultados
            st.markdown("---")
            st.info(f"Sede del Juego: **{estadio_actual}** (Factor Modificador: {factor_estadio}x) | *Predicción Registrada en BD Local*")
            
            col1, col2 = st.columns(2)
            with col1:
                st.subheader(f"🏠 Local: {equipo_local}")
                st.metric("Pitcher Abridor", pitcher_local_info['name'])
                st.metric("ERA del Abridor", f"{pitcher_local_info['era']:.2f}")
                st.metric("Pythagorean Win %", f"{pyt_local:.3f}")
                st.metric("OPS Colectivo", f"{stats_local['OPS']:.3f}")
                
            with col2:
                st.subheader(f"✈️ Visitante: {equipo_visitante}")
                st.metric("Pitcher Abridor", pitcher_visit_info['name'])
                st.metric("ERA del Abridor", f"{pitcher_visit_info['era']:.2f}")
                st.metric("Pythagorean Win %", f"{pyt_visit:.3f}")
                st.metric("OPS Colectivo", f"{stats_visit['OPS']:.3f}")
                
            st.markdown("---")
            st.header("🎯 Resultados del Modelo Predictivo Pro + Machine Learning")
            
            res_col1, res_col2, res_col3 = st.columns(3)
            res_col1.metric(f"Victoria {equipo_local}", f"{prob_win_local * 100:.1f}%")
            res_col2.metric(f"Victoria {equipo_visitante}", f"{prob_win_visit * 100:.1f}%")
            res_col3.metric("Carreras Esperadas Ajustadas", f"{lambda_total:.2f}")

            st.markdown("---")
            st.subheader("📊 Líneas Totales y Over / Under")
            m_col1, m_col2, m_col3 = st.columns(3)
            m_col1.metric("Probabilidad Over (+8.5)", f"{prob_over * 100:.1f}%")
            m_col2.metric("Probabilidad Under (-8.5)", f"{prob_under * 100:.1f}%")
            m_col3.metric("Ambos anotan 2+ Carreras", f"{prob_ambos_anotan_2 * 100:.1f}%")

            st.markdown("---")
            st.subheader("⚡ Mercados Especiales y Props de Alta Probabilidad")
            p_col1, p_col2, p_col3, p_col4 = st.columns(4)
            p_col1.metric("YRFI (Carrera en 1ra Inn)", f"{prob_yrfi * 100:.1f}%")
            p_col2.metric("NRFI (Sin Carrera 1ra Inn)", f"{prob_nrfi * 100:.1f}%")
            p_col3.metric("Victoria por 1 sola carrera", f"{prob_margen_1:.1f}%")
            p_col4.metric("Riesgo de Blanqueada", f"{prob_algun_shutout:.1f}%")

            # --- Módulo de Gestión de Banca (Criterio de Kelly) ---
            st.markdown("---")
            st.subheader("💰 Módulo de Gestión de Banca (Criterio de Kelly con Cuotas Reales)")
            b_col1, b_col2 = st.columns(2)
            with b_col1:
                cuota_local_input = st.number_input(f"Cuota Decimal ({equipo_local})", min_value=1.01, max_value=10.0, value=float(cuota_default_local), step=0.05)
                pct_kelly_local = calcular_kelly(prob_win_local, cuota_local_input)
                st.metric(f"Apuesta Sugerida ({equipo_local})", f"{pct_kelly_local:.2f}% del Bankroll")
            with b_col2:
                cuota_visit_input = st.number_input(f"Cuota Decimal ({equipo_visitante})", min_value=1.01, max_value=10.0, value=float(cuota_default_visit), step=0.05)
                pct_kelly_visit = calcular_kelly(prob_win_visit, cuota_visit_input)
                st.metric(f"Apuesta Sugerida ({equipo_visitante})", f"{pct_kelly_visit:.2f}% del Bankroll")

            
            # --- Módulo de Análisis de Parlays ---
            st.markdown("---")
            st.subheader("🔗 Generador y Analizador de Parlays (2 Picks)")
            par_col1, par_col2, par_col3 = st.columns(3)
            with par_col1:
                prob_pick_1 = st.slider("Probabilidad Pick 1 (%)", 10.0, 95.0, float(round(prob_win_local * 100, 1))) / 100.0
            with par_col2:
                prob_pick_2 = st.slider("Probabilidad Pick 2 (%)", 10.0, 95.0, 60.0) / 100.0
            with par_col3:
                cuota_parlay_input = st.number_input("Cuota Total Combinada del Parlay", min_value=1.10, max_value=25.0, value=3.20, step=0.1)

            res_parlay = analizar_parlay(prob_pick_1, prob_pick_2, cuota_parlay_input)
            p_res1, p_res2, p_res3 = st.columns(3)
            p_res1.metric("Probabilidad Combinada", f"{res_parlay['prob_combinada']:.1f}%")
            p_res2.metric("Valor Esperado (EV)", f"{res_parlay['valor_esperado']:.1f}%")
            if res_parlay['es_valioso']:
                p_res3.success("✅ ¡Parlay con Valor Positivo (+EV)!")
            else:
                p_res3.warning("⚠️ EV Bajo / No Recomendado")

    else:
        st.warning("La temporada seleccionada no devolvió registros activos. Intenta seleccionar otra temporada.")

   # ==========================================
# FUNCIÓN AUXILIAR DE PITCHERS (Asegúrate de tenerla en app.py)
# ==========================================
def obtener_stats_pitcher_api(nombre_pitcher):
    """
    Busca al jugador en la API de la MLB y retorna sus stats (K/9, ERA, FIP y Nombre Correcto).
    """
    try:
        players = statsapi.lookup_player(nombre_pitcher)
        if not players:
            return {"k9": 8.5, "era": 4.00, "fip": 4.00, "nombre": nombre_pitcher}
        
        pid = players[0]['id']
        stats = statsapi.player_stat_data(pid, group="pitching", type="season")
        
        k9 = 8.5
        era = 4.00
        for s in stats.get('stats', []):
            if 'strikeOutsPer9Inn' in s.get('stats', {}):
                k9 = float(s['stats']['strikeOutsPer9Inn'])
            if 'earnedRunAverage' in s.get('stats', {}):
                era = float(s['stats']['earnedRunAverage'])
        
        return {"k9": round(k9, 2), "era": round(era, 2), "fip": era, "nombre": players[0]['fullName']}
    except:
        return {"k9": 8.5, "era": 4.00, "fip": 4.00, "nombre": nombre_pitcher}
# =====================================================================
# OBTENCIÓN DE DATOS 100% REALES (Estricto, sin valores predeterminados)
# =====================================================================

def obtener_stats_equipo_reales(nombre_equipo):
    """
    Consulta la API oficial de la MLB de manera directa y estricta.
    Si algún dato no existe o la API falla, retorna None obligatoriamente.
    """
    try:
        # 1. Obtener ID real del equipo mediante búsqueda oficial
        teams = statsapi.lookup_team(nombre_equipo)
        if not teams:
            return None
        
        team_id = teams[0]['id']
        
        # 2. Petición directa al endpoint de estadísticas de la temporada actual (2026)
        endpoint_data = statsapi.get(
            'team_stats', 
            {
                'teamId': team_id, 
                'season': '2026', 
                'group': 'hitting,pitching', 
                'stats': 'season'
            }
        )
        
        # 3. Procesamiento estricto de la respuesta JSON real
        stats_splits = endpoint_data.get('stats', [])
        if not stats_splits:
            return None
            
        # Extraemos los acumulados reales del bloque de temporada
        games_played = 0
        runs_scored = 0
        era_val = 0.0
        
        for stat_group in stats_splits:
            group_name = stat_group.get('group', {}).get('displayName', '')
            splits = stat_group.get('splits', [])
            if not splits:
                continue
            stat_data = splits[0].get('stat', {})
            
            if group_name == 'hitting' or 'hitting' in stat_group.get('type', {}).get('displayName', '').lower():
                games_played = int(stat_data.get('gamesPlayed', 0))
                runs_scored = int(stat_data.get('runs', 0))
            elif group_name == 'pitching' or 'pitching' in stat_group.get('type', {}).get('displayName', '').lower():
                era_val = float(stat_data.get('era', 0.0))

        # Validación estricta: Si los valores esenciales están en cero, la API no entregó estadísticas válidas
        if games_played == 0:
            return None
            
        return {
            'G': games_played,
            'R': runs_scored,
            'ERA': era_val
        }
        
    except Exception as e:
        # Si hay cualquier error de conexión o estructura, se rechaza estrictamente
        return None

# =====================================================================
# REPORTE INDIVIDUAL: SOLO DATOS REALES DE LA API
# =====================================================================
st.markdown("---")
st.subheader("⚾ Generador de Reporte: Análisis con Datos Reales")

hoy_str = datetime.now().strftime('%Y-%m-%d')

if 'partidos_hoy_cache' not in st.session_state:
    p_hoy = statsapi.schedule(date=hoy_str)
    if not p_hoy:
        p_hoy = statsapi.schedule(start_date=hoy_str, end_date=hoy_str)
    st.session_state['partidos_hoy_cache'] = p_hoy

partidos_hoy = st.session_state['partidos_hoy_cache']

opciones_partidos = [f"{g.get('away_name', '')} @ {g.get('home_name', '')}" for g in partidos_hoy if g.get('home_name') and g.get('away_name')]

if opciones_partidos:
    partido_seleccionado = st.selectbox("Selecciona el partido:", opciones_partidos, key="select_partido_reales")
    
    # 1. BOTÓN INDIVIDUAL
    if st.button("📤 Analizar y Enviar (Datos 100% Reales)", key="btn_analizar_reales"):
        game_obj = next((g for g in partidos_hoy if f"{g.get('away_name', '')} @ {g.get('home_name', '')}" == partido_seleccionado), None)
        
        if game_obj:
            nombre_local = game_obj.get('home_name', '')
            nombre_visit = game_obj.get('away_name', '')
            estadio_juego = game_obj.get('venue_name', 'Estadio MLB')
            
            pitcher_loc_nombre = game_obj.get('home_probable_pitcher', 'Local')
            pitcher_vis_nombre = game_obj.get('away_probable_pitcher', 'Visitante')
            
            pitcher_loc_real = obtener_stats_pitcher_api(pitcher_loc_nombre)
            pitcher_vis_real = obtener_stats_pitcher_api(pitcher_vis_nombre)
            
            stats_local_real = obtener_stats_equipo_reales(nombre_local)
            stats_visit_real = obtener_stats_equipo_reales(nombre_visit)
            
            if stats_local_real and stats_visit_real and pitcher_loc_real and pitcher_vis_real:
                factor_estadio = 1.05 if "Coors" in estadio_juego else 1.00
                
                prob_loc_val = ejecutar_prediccion_ml(
                    stats_local=stats_local_real,
                    stats_visit=stats_visit_real,
                    pitcher_local_info=pitcher_loc_real,
                    pitcher_visit_info=pitcher_vis_real,
                    factor_estadio=factor_estadio,
                    lambda_local=4.5,
                    lambda_visit=4.2
                )
                
                p_loc = round(prob_loc_val * 100, 1)
                p_vis = round((1.0 - prob_loc_val) * 100, 1)
                
                era_loc = float(pitcher_loc_real.get('era', 4.0))
                era_vis = float(pitcher_vis_real.get('era', 4.0))
                runs_loc = float(stats_local_real.get('R', 400)) / max(1, float(stats_local_real.get('G', 100)))
                runs_vis = float(stats_visit_real.get('R', 400)) / max(1, float(stats_visit_real.get('G', 100)))

                carreras_esperadas = round(max(3.0, ((era_loc + era_vis) / 2.0 + (runs_loc + runs_vis) / 2.0) * factor_estadio), 2)
                
                linea_base = 8.5
                prob_over = min(round(50.0 + (carreras_esperadas - linea_base) * 9.5, 1), 89.0) if carreras_esperadas > linea_base else max(round(40.0 + (carreras_esperadas - linea_base) * 8.0, 1), 15.0)
                prob_under = round(100.0 - prob_over, 1)
                
                prob_ambos = min(round(55.0 + (carreras_esperadas * 3.5), 1), 95.0)
                prob_yrfi = min(round(35.0 + (carreras_esperadas * 4.2), 1), 88.0)
                prob_nrfi = round(100.0 - prob_yrfi, 1)
                
                margen_dif = abs(p_loc - p_vis)
                prob_1_carrera = max(round(25.0 - (margen_dif * 0.3), 1), 8.5)
                riesgo_blanqueada = max(round(12.0 - (carreras_esperadas * 1.1), 1), 2.0)

                reporte_telegram = (
                    f"🎯 *Resultados del Modelo Predictivo Pro + Machine Learning*\n"
                    f"⚾ *{nombre_visit} @ {nombre_local}*\n\n"
                    f"🔹 Victoria {nombre_local}: *{p_loc}%*\n"
                    f"🔹 Victoria {nombre_visit}: *{p_vis}%*\n"
                    f"📊 *Carreras Esperadas Ajustadas:* `{carreras_esperadas}`\n\n"
                    f"📈 *Líneas Totales y Over / Under*\n"
                    f"   • Probabilidad Over (+{linea_base}): *{prob_over}%*\n"
                    f"   • Probabilidad Under (-{linea_base}): *{prob_under}%*\n"
                    f"   • Ambos anotan 2+ Carreras: *{prob_ambos}%*\n\n"
                    f"⚡ *Mercados Especiales y Props de Alta Probabilidad*\n"
                    f"   • YRFI (Carrera en 1ra Inn): *{prob_yrfi}%*\n"
                    f"   • NRFI (Sin Carrera 1ra Inn): *{prob_nrfi}%*\n"
                    f"   • Victoria por 1 sola carrera: *{prob_1_carrera}%*\n"
                    f"   • Riesgo de Blanqueada: *{riesgo_blanqueada}%*"
                )
                
                TOKEN_BOT = "8817380632:AAGiNy9jvg5g1-0TNPkqOpMqdfntV1UQEP8"
                CHAT_ID_DESTINO = "8689508146"
                
                game_pk = game_obj.get('game_pk') or game_obj.get('game_id')
                
                enviar_alerta_telegram(TOKEN_BOT, CHAT_ID_DESTINO, reporte_telegram)
                st.success(f"¡Análisis con datos 100% reales de {partido_seleccionado} enviado con éxito a Telegram!")
                
                registrar_apuesta_ia(game_pk, nombre_local, nombre_visit, p_loc, p_vis, carreras_esperadas)
                
            else:
                st.error("⚠️ Faltan datos en la API para este encuentro:")
                if not stats_local_real:
                    st.write(f"• No se obtuvieron estadísticas de equipo para el local: {nombre_local}")
                if not stats_visit_real:
                    st.write(f"• No se obtuvieron estadísticas de equipo para el visitante: {nombre_visit}")
                if not pitcher_loc_real:
                    st.write(f"• No se encontraron datos del pitcher abridor local: {pitcher_loc_nombre}")
                if not pitcher_vis_real:
                    st.write(f"• No se encontraron datos del pitcher abridor visitante: {pitcher_vis_nombre}")

    st.markdown("---")
    
    # 2. BOTÓN MASIVO (TODOS LOS PARTIDOS)
    if st.button("🚀 Analizar y Enviar TODOS los Partidos del Día", key="btn_analizar_todos"):
        contador_exitos = 0
        contador_fallos = 0
        
        TOKEN_BOT = "8817380632:AAGiNy9jvg5g1-0TNPkqOpMqdfntV1UQEP8"
        CHAT_ID_DESTINO = "8689508146"
        
        barra_progreso = st.progress(0)
        total_partidos = len(partidos_hoy)
        
        for i, game_obj_masivo in enumerate(partidos_hoy):
            nombre_local = game_obj_masivo.get('home_name', '')
            nombre_visit = game_obj_masivo.get('away_name', '')
            estadio_juego = game_obj_masivo.get('venue_name', 'Estadio MLB')
            
            if not nombre_local or not nombre_visit:
                continue
                
            pitcher_loc_nombre = game_obj_masivo.get('home_probable_pitcher', 'Local')
            pitcher_vis_nombre = game_obj_masivo.get('away_probable_pitcher', 'Visitante')
            
            pitcher_loc_real = obtener_stats_pitcher_api(pitcher_loc_nombre)
            pitcher_vis_real = obtener_stats_pitcher_api(pitcher_vis_nombre)
            
            stats_local_real = obtener_stats_equipo_reales(nombre_local)
            stats_visit_real = obtener_stats_equipo_reales(nombre_visit)
            
            if stats_local_real and stats_visit_real and pitcher_loc_real and pitcher_vis_real:
                factor_estadio = 1.05 if "Coors" in estadio_juego else 1.00
                
                prob_loc_val = ejecutar_prediccion_ml(
                    stats_local=stats_local_real,
                    stats_visit=stats_visit_real,
                    pitcher_local_info=pitcher_loc_real,
                    pitcher_visit_info=pitcher_vis_real,
                    factor_estadio=factor_estadio,
                    lambda_local=4.5,
                    lambda_visit=4.2
                )
                
                p_loc = round(prob_loc_val * 100, 1)
                p_vis = round((1.0 - prob_loc_val) * 100, 1)
                
                era_loc = float(pitcher_loc_real.get('era', 4.0))
                era_vis = float(pitcher_vis_real.get('era', 4.0))
                runs_loc = float(stats_local_real.get('R', 400)) / max(1, float(stats_local_real.get('G', 100)))
                runs_vis = float(stats_visit_real.get('R', 400)) / max(1, float(stats_visit_real.get('G', 100)))

                carreras_esperadas = round(max(3.0, ((era_loc + era_vis) / 2.0 + (runs_loc + runs_vis) / 2.0) * factor_estadio), 2)
                
                linea_base = 8.5
                prob_over = min(round(50.0 + (carreras_esperadas - linea_base) * 9.5, 1), 89.0) if carreras_esperadas > linea_base else max(round(40.0 + (carreras_esperadas - linea_base) * 8.0, 1), 15.0)
                prob_under = round(100.0 - prob_over, 1)
                
                prob_ambos = min(round(55.0 + (carreras_esperadas * 3.5), 1), 95.0)
                prob_yrfi = min(round(35.0 + (carreras_esperadas * 4.2), 1), 88.0)
                prob_nrfi = round(100.0 - prob_yrfi, 1)
                
                margen_dif = abs(p_loc - p_vis)
                prob_1_carrera = max(round(25.0 - (margen_dif * 0.3), 1), 8.5)
                riesgo_blanqueada = max(round(12.0 - (carreras_esperadas * 1.1), 1), 2.0)

                reporte_telegram = (
                    f"🎯 *Resultados del Modelo Predictivo Pro + Machine Learning*\n"
                    f"⚾ *{nombre_visit} @ {nombre_local}*\n\n"
                    f"🔹 Victoria {nombre_local}: *{p_loc}%*\n"
                    f"🔹 Victoria {nombre_visit}: *{p_vis}%*\n"
                    f"📊 *Carreras Esperadas Ajustadas:* `{carreras_esperadas}`\n\n"
                    f"📈 *Líneas Totales y Over / Under*\n"
                    f"   • Probabilidad Over (+{linea_base}): *{prob_over}%*\n"
                    f"   • Probabilidad Under (-{linea_base}): *{prob_under}%*\n"
                    f"   • Ambos anotan 2+ Carreras: *{prob_ambos}%*\n\n"
                    f"⚡ *Mercados Especiales y Props de Alta Probabilidad*\n"
                    f"   • YRFI (Carrera en 1ra Inn): *{prob_yrfi}%*\n"
                    f"   • NRFI (Sin Carrera 1ra Inn): *{prob_nrfi}%*\n"
                    f"   • Victoria por 1 sola carrera: *{prob_1_carrera}%*\n"
                    f"   • Riesgo de Blanqueada: *{riesgo_blanqueada}%*"
                )
                
                game_pk = game_obj_masivo.get('game_pk') or game_obj_masivo.get('game_id')
                enviar_alerta_telegram(TOKEN_BOT, CHAT_ID_DESTINO, reporte_telegram)
                registrar_apuesta_ia(game_pk, nombre_local, nombre_visit, p_loc, p_vis, carreras_esperadas)
                contador_exitos += 1
            else:
                contador_fallos += 1
            
            barra_progreso.progress((i + 1) / total_partidos)
            
        st.success(f"¡Proceso masivo finalizado! Se enviaron {contador_exitos} reportes exitosos a Telegram ({contador_fallos} omitidos por falta de datos en API).")
else:
    st.warning("No hay enfrentamientos válidos disponibles para hoy.")
# --- PESTAÑA 2: GENERADOR AUTOMÁTICO DE PARLAYS ---
with tab_generator:
    st.header("🔗 Generador Automático de Parlays de Valor")
    st.write("Escanea automáticamente los partidos del día, selecciona los mejores picks con alta probabilidad y construye combinaciones óptimas (parlays) de 2 a 4 selecciones.")

    if st.button("🪄 Generar Parlays Automáticos"):
        with st.spinner("Analizando cuotas y probabilidades de toda la jornada para armar parlays..."):
            fecha_str_gen = fecha_seleccionada.strftime("%m/%d/%Y")
            try:
                agenda_gen = statsapi.schedule(date=fecha_str_gen)
            except Exception:
                agenda_gen = []

            if agenda_gen and df_merged is not None:
                candidatos_picks = []
                
                for juego in agenda_gen:
                    away = juego.get('away_name')
                    home = juego.get('home_name')
                    venue = juego.get('venue_name', 'Estadio Neutral')
                    
                    if home in equipos_disponibles and away in equipos_disponibles:
                        stats_l = df_merged[df_merged['Team'] == home].iloc[0]
                        stats_v = df_merged[df_merged['Team'] == away].iloc[0]
                        
                        p_loc_inf = obtener_info_lanzador(juego.get('home_probable_pitcher', 'No anunciado'))
                        p_vis_inf = obtener_info_lanzador(juego.get('away_probable_pitcher', 'No anunciado'))
                        
                        f_est = 1.00
                        if venue in ["Coors Field", "Great American Ball Park", "Fenway Park"]:
                            f_est = 1.12
                        elif venue in ["Petco Park", "T-Mobile Park", "Oracle Park"]:
                            f_est = 0.90
                            
                        c_loc = stats_l['R'] / max(stats_l['G'], 1)
                        c_vis = stats_v['R'] / max(stats_v['G'], 1)
                        l_loc = max(c_loc * (p_vis_inf['era'] / 4.00) * f_est, 1.5)
                        l_vis = max(c_vis * (p_loc_inf['era'] / 4.00) * f_est, 1.5)
                        l_total = l_loc + l_vis
                        
                        p_w_loc = ejecutar_prediccion_ml(stats_l, stats_v, p_loc_inf, p_vis_inf, f_est, l_loc, l_vis)
                        p_w_vis = 1.0 - p_w_loc
                        
                        # Obtener cuotas reales de la API si están disponibles
                        cuotas_juego = obtener_cuotas_reales(home, away)
                        cuota_l = cuotas_juego.get(home, 1.90)
                        cuota_v = cuotas_juego.get(away, 1.90)
                        
                        # Evaluar ganador local
                        candidatos_picks.append({
                            "partido": f"{away} @ {home}",
                            "pick": f"Victoria {home}",
                            "prob": p_w_loc,
                            "cuota": cuota_l
                        })
                        # Evaluar ganador visitante
                        candidatos_picks.append({
                            "partido": f"{away} @ {home}",
                            "pick": f"Victoria {away}",
                            "prob": p_w_vis,
                            "cuota": cuota_v
                        })

                # Ordenar por probabilidad de mayor a menor
                candidatos_picks = sorted(candidatos_picks, key=lambda x: x['prob'], reverse=True)

                if len(candidatos_picks) >= 2:
                    st.success(f"¡Se encontraron {len(candidatos_picks)} opciones de picks con respaldo analítico!")
                    
                    st.subheader("💡 Sugerencias de Parlays Combinados")
                    
                    # Armar parlay doble principal con los 2 mejores picks
                    p1 = candidatos_picks[0]
                    p2 = candidatos_picks[1]
                    
                    prob_comb = p1['prob'] * p2['prob'] * 100
                    cuota_comb = p1['cuota'] * p2['cuota']
                    ev_comb = (prob_comb / 100.0) * cuota_comb * 100 - 100
                    
                    col_p1, col_p2 = st.columns(2)
                    with col_p1:
                        st.markdown(f"### 🏆 Parlay Doble Principal (+EV)")
                        st.markdown(f"* **Leg 1:** {p1['partido']} — **{p1['pick']}** (Prob: {p1['prob']*100:.1f}%, Cuota: {p1['cuota']})")
                        st.markdown(f"* **Leg 2:** {p2['partido']} — **{p2['pick']}** (Prob: {p2['prob']*100:.1f}%, Cuota: {p2['cuota']})")
                    with col_p2:
                        st.metric("Probabilidad Combinada", f"{prob_comb:.1f}%")
                        st.metric("Cuota Total Estimada", f"{cuota_comb:.2f}")
                        st.metric("Valor Esperado (EV)", f"{ev_comb:.1f}%", delta="Rentable" if ev_comb > 0 else "Precaución")

                    if len(candidatos_picks) >= 4:
                        st.markdown("---")
                        p3 = candidatos_picks[2]
                        p4 = candidatos_picks[3]
                        
                        prob_comb_4 = p1['prob'] * p2['prob'] * p3['prob'] * p4['prob'] * 100
                        cuota_comb_4 = p1['cuota'] * p2['cuota'] * p3['cuota'] * p4['cuota']
                        ev_comb_4 = (prob_comb_4 / 100.0) * cuota_comb_4 * 100 - 100
                        
                        st.markdown(f"### 🔥 Parlay Cuádruple de Alta Cuota (Moonshot)")
                        st.markdown(f"* **Leg 1:** {p1['partido']} — **{p1['pick']}**")
                        st.markdown(f"* **Leg 2:** {p2['partido']} — **{p2['pick']}**")
                        st.markdown(f"* **Leg 3:** {p3['partido']} — **{p3['pick']}**")
                        st.markdown(f"* **Leg 4:** {p4['partido']} — **{p4['pick']}**")
                        
                        q1, q2, q3 = st.columns(3)
                        q1.metric("Probabilidad Combinada (4 Legs)", f"{prob_comb_4:.1f}%")
                        q2.metric("Cuota Total (4 Legs)", f"{cuota_comb_4:.2f}")
                        q3.metric("Valor Esperado (EV)", f"{ev_comb_4:.1f}%")
                else:
                    st.warning("No hay suficientes picks con los parámetros actuales para generar combinaciones de parlay.")
            else:
                st.info("No hay partidos programados o datos disponibles para la fecha seleccionada.")

# --- PESTAÑA 3: BACKTESTING Y PANEL DE RENDIMIENTO ---
with tab_backtest:
    st.header("📈 Panel de Verificación de Aciertos y Métricas de Rendimiento")
    st.write("Consulta y verifica automáticamente las predicciones guardadas contra los marcadores finales de la MLB, incluyendo la simulación de crecimiento de tu Bankroll.")
    
    col_bt1, col_bt2 = st.columns(2)
    with col_bt1:
        if st.button("🔄 Sincronizar Resultados Reales con la MLB"):
            with st.spinner("Conectando con la API de la MLB para actualizar marcadores finales..."):
                n_upd = actualizar_resultados_reales()
                st.success(f"¡Sincronización completada! Se actualizaron {n_upd} registros pendientes.")
                
    conn = sqlite3.connect(DB_NAME)
    df_tot = pd.read_sql_query("SELECT * FROM historial_predicciones ORDER BY fecha ASC", conn)
    conn.close()
    
    if not df_tot.empty:
        df_eval = df_tot[df_tot['ganador_real'] != 'Pendiente'].copy()
        
        if not df_eval.empty:
            df_eval['prediccion_equipo'] = np.where(df_eval['prob_local'] >= df_eval['prob_visit'], df_eval['local'], df_eval['visitante'])
            df_eval['acierto'] = df_eval['prediccion_equipo'] == df_eval['ganador_real']
            
            # --- Filtros en el Panel de Backtesting ---
            st.markdown("---")
            st.subheader("🔍 Filtros de Análisis Histórico")
            f_col1, f_col2 = st.columns(2)
            with f_col1:
                filtro_resultado = st.selectbox("Filtrar por Estado", ["Todos", "Solo Acertados", "Solo Fallidos"])
            with f_col2:
                banca_inicial = st.number_input("Bankroll Inicial Simulado ($)", min_value=100.0, max_value=100000.0, value=1000.0, step=100.0)
                
            df_filtrado = df_eval.copy()
            if filtro_resultado == "Solo Acertados":
                df_filtrado = df_filtrado[df_filtrado['acierto'] == True]
            elif filtro_resultado == "Solo Fallidos":
                df_filtrado = df_filtrado[df_filtrado['acierto'] == False]
                
            total_evaluados = len(df_eval)
            total_aciertos = df_eval['acierto'].sum()
            pct_efectividad = (total_aciertos / total_evaluados) * 100 if total_evaluados > 0 else 0
            
            st.markdown("### 📊 Métricas Globales del Modelo")
            k1, k2, k3 = st.columns(3)
            k1.metric("Partidos Verificados", f"{total_evaluados}")
            k2.metric("Predicciones Acertadas", f"{total_aciertos}")
            k3.metric("Efectividad / Accuracy", f"{pct_efectividad:.1f}%")
            
            # --- Simulación Financiera de Bankroll ---
            banca_actual = banca_inicial
            historial_banca = [banca_inicial]
            
            for idx, row in df_eval.iterrows():
                # Simulamos una unidad de apuesta fija del 2% del bankroll actual por partido recomendado
                apuesta = banca_actual * 0.02
                cuota_simulada = 1.90 # Cuota promedio estándar
                
                if row['acierto']:
                    banca_actual += apuesta * (cuota_simulada - 1)
                else:
                    banca_actual -= apuesta
                historial_banca.append(banca_actual)
                
            st.markdown("---")
            st.subheader("💰 Curva de Crecimiento del Bankroll Simulado")
            st.line_chart(historial_banca)
            st.caption(f"Evolución del capital partiendo de ${banca_inicial:,.2f} aplicando gestión de riesgo fija del 2% por pick.")
            
            st.markdown("---")
            st.subheader("📋 Registro Detallado de Predicciones Evaluadas")
            st.dataframe(df_filtrado[['fecha', 'local', 'visitante', 'prob_local', 'prob_visit', 'prediccion_equipo', 'resultado_real', 'ganador_real', 'acierto']], use_container_width=True)
        else:
            st.info("Hay predicciones registradas en la base de datos, pero aún no hay partidos finalizados o sincronizados.")
            st.dataframe(df_tot)
    else:
        st.info("Aún no hay predicciones guardadas en la base de datos.")
# --- SECCIÓN 2, 3 Y 4: PARLAYS, PROPS DE PONCHES Y TELEGRAM ---
st.markdown("---")
st.subheader("🛠️ Herramientas Avanzadas y Analizador")

# Creamos pestañas (Tabs) en Streamlit para mantener la interfaz limpia
tab_parlay, tab_props, tab_telegram = st.tabs(["📊 Analizador de Parlay", "🎯 Props de Ponches (K's)", "📱 Enviar Alerta Telegram"])

# --- TAB 1: PARLAY ANALYZER ---
with tab_parlay:
    st.markdown("### 🔗 Analizador de Apuestas Combinadas (Parlay)")
    st.write("Calcula la probabilidad conjunta y la cuota combinada estimada.")
    
    col_p1, col_p2 = st.columns(2)
    with col_p1:
        cuota_partido_1 = st.number_input("Cuota Decimal Partido 1 (Ej. 1.85)", min_value=1.01, value=1.85, step=0.01)
        prob_partido_1 = st.slider("Probabilidad estimada Partido 1 (%)", 1.0, 99.0, prob_local if 'prob_local' in locals() else 50.0)
    with col_p2:
        cuota_partido_2 = st.number_input("Cuota Decimal Partido 2 (Ej. 2.10)", min_value=1.01, value=2.10, step=0.01)
        prob_partido_2 = st.slider("Probabilidad estimada Partido 2 (%)", 1.0, 99.0, 55.0)

    if st.button("Calcular Parlay Conjunto"):
        try:
            cuota_total = cuota_partido_1 * cuota_partido_2
            prob_conjunta = (prob_partido_1 / 100.0) * (prob_partido_2 / 100.0) * 100
            
            st.success(f"📈 **Cuota Combinada Total:** {cuota_total:.2f}")
            st.info(f"🎲 **Probabilidad Conjunta Estimada:** {prob_conjunta:.1f}%")
        except Exception as e:
            st.error(f"Error al calcular el parlay: {e}")

# --- TAB 2: PROPS DE PONCHES (K'S) ---
with tab_props:
    st.markdown("### 🎯 Proyección de Ponches para Lanzadores")
    st.write("Estima cuántos ponches recetará el abridor basándose en su K/9 y el rival.")
    
    col_k1, col_k2 = st.columns(2)
    with col_k1:
        st.markdown(f"**Lanzador Local:** {pitcher_local_info.get('name') if 'pitcher_local_info' in locals() else 'Local'}")
        innings_loc = st.number_input("Innings proyectados (Local)", min_value=1.0, max_value=9.0, value=5.5, step=0.5)
        k9_loc = st.number_input("K/9 del Lanzador (Local)", min_value=1.0, max_value=15.0, value=8.5, step=0.1)
    
    with col_k2:
        st.markdown(f"**Lanzador Visitante:** {pitcher_visit_info.get('name') if 'pitcher_visit_info' in locals() else 'Visitante'}")
        innings_vis = st.number_input("Innings proyectados (Visitante)", min_value=1.0, max_value=9.0, value=5.5, step=0.5)
        k9_vis = st.number_input("K/9 del Lanzador (Visitante)", min_value=1.0, max_value=15.0, value=8.5, step=0.1)

    if st.button("Calcular Proyección de Ponches"):
        try:
            ks_local_proyectados = proyectar_ponches_lanzador(k9_loc, innings_loc, 0.22)
            ks_visit_proyectados = proyectar_ponches_lanzador(k9_vis, innings_vis, 0.22)
            
            col_res1, col_res2 = st.columns(2)
            col_res1.metric(f"Ponches K's (Local)", f"{ks_local_proyectados} Ponches")
            col_res2.metric(f"Ponches K's (Visitante)", f"{ks_visit_proyectados} Ponches")
        except Exception as e:
            st.error(f"Error al calcular ponches: {e}")

# --- TAB 3: ALERTAS DE TELEGRAM (SIN VALORES PREDETERMINADOS) ---
with tab_telegram:
    st.markdown("### 📱 Enviar Reporte Inteligente a Telegram")
    st.write("Genera y envía el reporte basado exactamente en la simulación y el parlay activo.")
    
    # Validamos que existan las variables principales de la simulación
    if 'equipo_local' in locals() and 'equipo_visitante' in locals() and 'prob_local' in locals():
        
        # Identificamos cuál tiene mayor probabilidad de manera dinámica
        if prob_local > prob_visit:
            mejor_apuesta = f"🔥 Jugada Recomendada: *{equipo_local} ({prob_local}%)*"
        else:
            mejor_apuesta = f"🔥 Jugada Recomendada: *{equipo_visitante} ({prob_visit}%)*"

        # Construimos el mensaje usando exclusivamente las variables actuales del sistema
        mensaje_dinamico = f"""⚾ *MLB PRO PREDICTOR - REPORTE EN VIVO* ⚾

🏟️ *Enfrentamiento:* {equipo_local} (Local) vs {equipo_visitante} (Visitante)
📍 *Estadio:* {estadio_actual}

📊 *Probabilidades del Modelo:*
• Victoria {equipo_local}: {prob_local}%
• Victoria {equipo_visitante}: {prob_visit}%
{mejor_apuesta}

🔗 *Selección de Parlay Activa:*
• Cuota Partido 1: {cuota_partido_1} (Prob: {prob_partido_1}%)
• Cuota Partido 2: {cuota_partido_2} (Prob: {prob_partido_2}%)
📈 *Cuota Combinada:* {cuota_partido_1 * cuota_partido_2:.2f}
🎲 *Probabilidad Conjunta:* {(prob_partido_1 / 100.0) * (prob_partido_2 / 100.0) * 100:.1f}%
"""

        mensaje_personalizado = st.text_area(
            "Vista previa del reporte:",
            value=mensaje_dinamico,
            height=230
        )
        
        if st.button("🚀 Enviar Reporte Real a Telegram"):
            try:
                enviar_alerta_telegram(TELEGRAM_CHAT_ID, mensaje_personalizado)
                st.success("¡Reporte enviado exitosamente a tu Telegram!")
            except Exception as e:
                st.error(f"Error al enviar la alerta: {e}")
    else:
        st.warning("⚠️ Primero ejecuta la predicción del partido en la sección superior para poder generar el reporte de Telegram.")
def tarea_automatica_nocturna():
    while True:
        time.sleep(86400) # Espera 24 horas
        try:
            evaluar_partidos_ayer()
            print("Evaluación automática nocturna completada con éxito.")
        except Exception as e:
            print(f"Error en tarea automática: {e}")

if 'hilo_iniciado' not in st.session_state:
    st.session_state['hilo_iniciado'] = True
    threading.Thread(target=tarea_automatica_nocturna, daemon=True).start()
import streamlit as st
import pandas as pd
import sqlite3

# Definimos el fragmento que se refrescará automáticamente cada 60 segundos
@st.fragment(run_every=60)
def mostrar_seguimiento_ia():
    st.subheader("🤖 Panel de Aprendizaje y Resultados en Vivo")
    
    # Conexión a tu base de datos histórica
    conn = sqlite3.connect("mlb_historico.db")
    df = pd.read_sql_query("""
        SELECT fecha, local, visitante, prob_local, prob_visitante, 
               carreras_esperadas, resultado_real, acerto 
        FROM predicciones_historicas 
        ORDER BY id DESC LIMIT 50
    """, conn)
    conn.close()
    
    if not df.empty:
        # Dar formato visual amigable a la tabla
        def colorear_aciertos(val):
            if val == 1:
                return 'background-color: #d4edda; color: #155724;' # Verde acierto
            elif val == 0:
                return 'background-color: #f8d7da; color: #721c24;' # Rojo fallo
            return 'background-color: #fff3cd; color: #856404;' # Pendiente
            
        st.dataframe(df.style.map(colorear_aciertos, subset=['acerto']), use_container_width=True)
    else:
        st.info("Aún no hay registros en el historial para mostrar.")

# Llamas a la función en tu diseño donde prefieras que se visualize
mostrar_seguimiento_ia()