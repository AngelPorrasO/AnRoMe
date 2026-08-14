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
    standings = statsapi.standings_data(leagueId="103,104", season=datetime.now().year)
    for league in standings.values():
        for division in league.values():
            for team in division:
                if team['team_id'] == team_id:
                    return {'R': float(team['runsScored']), 'G': float(team['gamesPlayed'])}
    return {'R': 4.0, 'G': 1} # Fallback mínimo de equipo

def main():
    hoy_str = datetime.now().strftime('%Y-%m-%d')
    partidos = statsapi.schedule(date=hoy_str)
    
    reporte = f"📊 *Predicciones MLB - {hoy_str}*\n```text\n"
    reporte += "Juego       | Pick    | Probabilidad\n------------------------------------\n"
    
    juegos_procesados = 0
    for juego in partidos:
        try:
            home_id = juego.get('home_id')
            away_id = juego.get('away_id')
            local = juego.get('home_name')
            visit = juego.get('away_name')
            
            # Intentar obtener stats de pitcher
            stats_loc_p = obtener_stats_pitcher_api(juego.get('home_probable_pitcher'))
            stats_vis_p = obtener_stats_pitcher_api(juego.get('away_probable_pitcher'))
            
            # Si el pitcher es None, usamos un valor neutro interno SOLO para el cálculo, 
            # pero el modelo se basa principalmente en los datos reales del equipo
            stats_loc_team = obtener_stats_equipo(home_id)
            stats_vis_team = obtener_stats_equipo(away_id)
            
            prob_local = ejecutar_prediccion_ml(
                stats_local=stats_loc_team,
                stats_visit=stats_vis_team,
                pitcher_local_info=stats_loc_p if stats_loc_p else {'era': 4.0, 'fip': 4.0},
                pitcher_visit_info=stats_vis_p if stats_vis_p else {'era': 4.0, 'fip': 4.0},
                factor_estadio=1.0,
                nombre_local=local,
                nombre_visitante=visit
            )
            
            pick = local[:3] if prob_local > 0.5 else visit[:3]
            prob = max(prob_local, 1-prob_local) * 100
            
            reporte += f"{visit[:3]} @ {local[:3]:<4} | {pick:<7} | {prob:.1f}%\n"
            juegos_procesados += 1
            
        except Exception:
            continue
            
    if juegos_procesados == 0:
        reporte += "No hay partidos disponibles hoy.\n"
        
    reporte += "```"
    enviar_a_telegram(reporte)

if __name__ == "__main__":
    main()