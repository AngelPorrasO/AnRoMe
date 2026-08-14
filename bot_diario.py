import os
import requests
import statsapi
from datetime import datetime, timedelta
import sqlite3
from engine import ejecutar_prediccion_ml

# Credenciales de Telegram configuradas
TELEGRAM_TOKEN = "8817380632:AAGiNy9jvg5g1-0TNPkqOpMqdfntV1UQEP8"
TELEGRAM_CHAT_ID = "8689508146"

def enviar_a_telegram(mensaje):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": mensaje,
        "parse_mode": "Markdown"
    }
    try:
        response = requests.post(url, json=payload)
        return response.json()
    except Exception as e:
        print(f"Error al enviar mensaje a Telegram: {e}")

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

def main():
    print("Iniciando proceso diario de MLB...")
    
    # 1. Evaluar resultados de ayer y actualizar BD
    print("Evaluando partidos de ayer...")
    try:
        evaluar_partidos_ayer()
    except Exception as e:
        print(f"Error evaluando ayer: {e}")
    
    # 2. Obtener partidos de hoy con depuración
    hoy_str = datetime.now().strftime('%Y-%m-%d')
    print(f"Buscando partidos en statsapi para la fecha: {hoy_str}")
    
    partidos_hoy = statsapi.schedule(date=hoy_str)
    print(f"Partidos encontrados crudos: {len(partidos_hoy) if partidos_hoy else 0}")
    
    if not partidos_hoy:
        enviar_a_telegram(f"🤖 *Reporte MLB ({hoy_str})*\n\nNo se encontraron partidos programados o la API no devolvió datos para hoy.")
        return

    # 3. Generar predicciones y armar la tabla para Telegram
    reporte = f"📊 *Predicciones MLB - {hoy_str}*\n"
    reporte += "```text\n"
    reporte += "Juego              | Pick      | Prob\n"
    reporte += "-----------------------------------\n"
    
    juegos_agregados = 0
    for juego in partidos_hoy:
        game_pk = juego.get('game_id')
        local = juego.get('home_name', 'Local')
        visitante = juego.get('away_name', 'Visitante')
        
        try:
            p_loc, p_vis, carreras_esp = ejecutar_prediccion_ml(game_pk)
            pick = "Local" if p_loc > p_vis else "Visitante"
            prob_max = max(p_loc, p_vis) * 100
            
            match_str = f"{visitante[:3]} @ {local[:3]}"
            reporte += f"{match_str:<18} | {pick:<9} | {prob_max:.1f}%\n"
            juegos_agregados += 1
        except Exception as e:
            print(f"Error prediciendo juego {game_pk} ({visitante} @ {local}): {e}")
            
    if juegos_agregados == 0:
        reporte += "No se pudieron calcular picks para los juegos de hoy.\n"
        
    reporte += "```\n"
    reporte += "🎯 *Generado automáticamente por tu IA*"
    
    # 4. Enviar a Telegram
    enviar_a_telegram(reporte)
    print("Reporte enviado con éxito a Telegram.")

if __name__ == "__main__":
    main()