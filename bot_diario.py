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
    reporte += "Juego       | Pick    | Prob  | O/U Proy\n"
    reporte += "----------------------------------------\n"
    
    for juego in partidos:
        game_pk = juego.get('game_id')
        home_id = juego.get('home_id')
        away_id = juego.get('away_id')
        local = juego.get('home_name', 'Local')
        visit = juego.get('away_name', 'Visit')
        
        try:
            # 1. Obtener datos de lanzadores reales de la API
            game_data = statsapi.get('game', {'gamePk': game_pk})
            box = game_data.get('liveData', {}).get('boxscore', {})
            
            p_local = box.get('teams', {}).get('home', {}).get('pitchers', [0])[0]
            p_visit = box.get('teams', {}).get('away', {}).get('pitchers', [0])[0]
            
            # 2. Extraer estadísticas avanzadas de pitchers y equipos
            stats_loc_pitcher = obtener_stats_pitcher_api(p_local)
            stats_vis_pitcher = obtener_stats_pitcher_api(p_visit)
            stats_loc_team = obtener_stats_equipo(home_id)
            stats_vis_team = obtener_stats_equipo(away_id)
            
            # 3. Calcular probabilidad de victoria con tu motor (Moneyline)
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
            pick = "Local" if prob_local > prob_visit else "Visit"
            prob_max = max(prob_local, prob_visit) * 100
            
            # 4. Cálculo estimado para el mercado de Totales (Over / Under Linea Proyectada)
            carreras_base_est = (stats_loc_team['R'] / max(stats_loc_team['G'], 1) + 
                                  stats_vis_team['R'] / max(stats_vis_team['G'], 1)) / 2.0
            fuerza_abridores = (stats_loc_pitcher['era'] + stats_vis_pitcher['era']) / 10.0
            total_ou = round(carreras_base_est + fuerza_abridores + 2.1, 1)
            
            match_str = f"{visit[:3]} @ {local[:3]}"
            reporte += f"{match_str:<11} | {pick:<7} | {prob_max:4.1f}% | {total_ou}\n"
        except Exception as e:
            print(f"Error en juego {game_pk}: {e}")
            
    reporte += "```\n"
    reporte += "🎯 *Generado automáticamente por tu IA*"
    
    enviar_a_telegram(reporte)

if __name__ == "__main__":
    main()