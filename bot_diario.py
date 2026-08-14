import requests
import statsapi
from datetime import datetime
from engine import ejecutar_prediccion_ml, obtener_stats_pitcher_api

TELEGRAM_TOKEN = "8817380632:AAGiNy9jvg5g1-0TNPkqOpMqdfntV1UQEP8"
TELEGRAM_CHAT_ID = "8689508146"

def enviar_a_telegram(mensaje):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": mensaje, "parse_mode": "Markdown"}
    requests.post(url, json=payload)

def obtener_stats_equipo(team_id):
    try:
        stats = statsapi.team_stats(team_id, "hitting", "season")
        return {'R': float(stats.get('runs', 4.0)), 'G': float(stats.get('gamesPlayed', 100))}
    except:
        return {'R': 4.0, 'G': 100}

def main():
    hoy_str = datetime.now().strftime('%Y-%m-%d')
    partidos = statsapi.schedule(date=hoy_str)
    
    reporte = f"📊 *Predicciones y Mercados MLB - {hoy_str}*\n"
    reporte += "```text\n"
    reporte += "Juego       | Moneyline     | Total (O/U)\n"
    reporte += "----------------------------------------\n"
    
    juegos_procesados = 0

    for juego in partidos:
        game_pk = juego.get('game_id')
        local = juego.get('home_name', 'Local')
        visit = juego.get('away_name', 'Visit')
        
        try:
            home_id = juego.get('home_id')
            away_id = juego.get('away_id')
            
            # 1. Obtener datos de lanzadores de forma segura
            game_data = statsapi.get('game', {'gamePk': game_pk})
            box = game_data.get('liveData', {}).get('boxscore', {})
            
            home_pitchers = box.get('teams', {}).get('home', {}).get('pitchers', [])
            away_pitchers = box.get('teams', {}).get('away', {}).get('pitchers', [])
            
            p_local = home_pitchers[0] if home_pitchers else 0
            p_visit = away_pitchers[0] if away_pitchers else 0
            
            # 2. Extraer estadísticas avanzadas de pitchers y equipos
            stats_loc_pitcher = obtener_stats_pitcher_api(p_local)
            stats_vis_pitcher = obtener_stats_pitcher_api(p_visit)
            stats_loc_team = obtener_stats_equipo(home_id)
            stats_vis_team = obtener_stats_equipo(away_id)
            
            # 3. Calcular probabilidad de victoria con tu motor (Moneyline) con decimales reales
            prob_local = ejecutar_prediccion_ml(
                stats_local=stats_loc_team,
                stats_visit=stats_vis_team,
                pitcher_local_info=stats_loc_pitcher,
                pitcher_visit_info=stats_vis_pitcher,
                factor_estadio=1.0,
                lambda_local=1.0,
                lambda_visit=1.0,
                nombre_local=local,
                nombre_visitante=visit
            )
            
            prob_visit = 1.0 - prob_local
            
            # Asignar el nombre real del equipo ganador y mostrar porcentaje con decimales reales
            if prob_local > prob_visit:
                pick = local[:3]
                prob_max = prob_local * 100
            else:
                pick = visit[:3]
                prob_max = prob_visit * 100
            
            # 4. Cálculo para el mercado de Totales (Over / Under con porcentaje)
            prom_carreras_liga = 4.5 
            ajuste_pitchteo = ((stats_loc_pitcher['era'] + stats_vis_pitcher['era']) - 8.0) * 0.2
            total_ou = round((prom_carreras_liga * 2) + ajuste_pitchteo, 1)
            total_ou = max(min(total_ou, 14.5), 6.5)
            
            linea_referencia = 8.5
            if total_ou > linea_referencia:
                ou_pick = f"Over {linea_referencia}"
                ou_prob = min(50.0 + abs(total_ou - linea_referencia) * 12, 85.0)
            else:
                ou_pick = f"Under {linea_referencia}"
                ou_prob = min(50.0 + abs(linea_referencia - total_ou) * 12, 85.0)

            match_str = f"{visit[:3]} @ {local[:3]}"
            # Cambiado a 1 decimal ({prob_max:.1f}%) para evitar que se queden en números cerrados como 50%
            reporte += f"{match_str:<11} | {pick:<5} ({prob_max:.1f}%) | {ou_pick} ({ou_prob:.0f}%)\n"
            juegos_procesados += 1
            
        except Exception as e:
            print(f"Error procesando el juego {game_pk} ({visit} @ {local}): {e}")
            continue
            
    if juegos_procesados == 0:
        reporte += "No se pudieron procesar partidos hoy.\n"
        
    reporte += "```\n"
    reporte += "🎯 *Generado automáticamente por tu IA*"
    
    enviar_a_telegram(reporte)

if __name__ == "__main__":
    main()