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
    """Extrae las carreras anotadas reales de la tabla de posiciones oficial."""
    standings = statsapi.standings_data(leagueId="103,104", season=datetime.now().year)
    for league_key, divisions in standings.items():
        for division_name, teams in divisions.items():
            for team in teams:
                if team['team_id'] == team_id:
                    return {
                        'R': float(team['runsScored']),
                        'G': float(team['gamesPlayed'])
                    }
    raise ValueError(f"No se encontraron estadísticas de equipo para el ID {team_id}")

def main():
    hoy_str = datetime.now().strftime('%Y-%m-%d')
    partidos = statsapi.schedule(date=hoy_str)
    
    reporte = f"📊 *Predicciones y Mercados MLB - {hoy_str}*\n"
    reporte += "```text\n"
    reporte += "Juego       | Moneyline     | Total (O/U)\n"
    reporte += "----------------------------------------\n"
    
    juegos_procesados = 0

    for juego in partidos:
        local = juego.get('home_name', 'Local')
        visit = juego.get('away_name', 'Visit')
        
        try:
            home_id = juego.get('home_id')
            away_id = juego.get('away_id')
            
            # SOLUCIÓN: Usamos los pitchers probables del calendario en lugar del boxscore
            p_local = juego.get('home_probable_pitcher', 'No anunciado')
            p_visit = juego.get('away_probable_pitcher', 'No anunciado')
            
            # Extraer stats con los lanzadores probables
            stats_loc_pitcher = obtener_stats_pitcher_api(p_local)
            stats_vis_pitcher = obtener_stats_pitcher_api(p_visit)
            stats_loc_team = obtener_stats_equipo(home_id)
            stats_vis_team = obtener_stats_equipo(away_id)
            
            # Calcular probabilidad real con el motor logístico
            prob_local = ejecutar_prediccion_ml(
                stats_local=stats_loc_team,
                stats_visit=stats_vis_team,
                pitcher_local_info=stats_loc_pitcher,
                pitcher_visit_info=stats_vis_pitcher,
                factor_estadio=1.0,
                nombre_local=local,
                nombre_visitante=visit
            )
            
            prob_visit = 1.0 - prob_local
            
            if prob_local > prob_visit:
                pick = local[:3]
                prob_max = prob_local * 100
            else:
                pick = visit[:3]
                prob_max = prob_visit * 100
            
            # Mercado de Totales
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
            reporte += f"{match_str:<11} | {pick:<5} ({prob_max:.1f}%) | {ou_pick} ({ou_prob:.0f}%)\n"
            juegos_procesados += 1
            
        except Exception as e:
            print(f"Juego omitido ({visit} @ {local}): {e}")
            continue
            
    if juegos_procesados == 0:
        reporte += "No hay partidos programados o con datos disponibles hoy.\n"
        
    reporte += "```\n"
    reporte += "🎯 *Generado automáticamente por tu IA*"
    
    enviar_a_telegram(reporte)

if __name__ == "__main__":
    main()