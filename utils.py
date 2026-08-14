import requests
from scipy.stats import poisson
import numpy as np
from datetime import datetime
import statsapi

def calcular_kelly(prob_modelo, cuota_decimal):
    """Calcula el porcentaje óptimo de bankroll a arriesgar (Kelly Fraccional 25%)."""
    if cuota_decimal <= 1.0:
        return 0.0
    b = cuota_decimal - 1.0
    fraccion_kelly = (prob_modelo * (b + 1.0) - 1.0) / b
    apuesta_pct = max(0.0, fraccion_kelly * 0.25)
    return min(apuesta_pct, 0.05) * 100

def analizar_parlay(prob_pick1, prob_pick2, cuota_total):
    """Calcula probabilidad combinada y EV de un parlay."""
    prob_parlay = prob_pick1 * prob_pick2
    ev = (prob_parlay * cuota_total) - 1.0
    return {
        "prob_combinada": prob_parlay * 100,
        "valor_esperado": ev * 100,
        "es_valioso": ev > 0.05
    }

def obtener_info_lanzador(nombre_pitcher):
    if not nombre_pitcher or nombre_pitcher == "No anunciado":
        return {"name": "Por anunciar", "era": 4.00, "whip": 1.30}
    try:
        search_url = f"https://statsapi.mlb.com/api/v1/people/search?names={requests.utils.quote(nombre_pitcher)}"
        res = requests.get(search_url).json()
        people = res.get('people', [])
        if not people:
            return {"name": nombre_pitcher, "era": 4.00, "whip": 1.30}
        
        pid = people[0]['id']
        stats_url = f"https://statsapi.mlb.com/api/v1/people/{pid}/stats?stats=season&group=pitching"
        stats_res = requests.get(stats_url).json()
        
        splits = stats_res.get('stats', [{}])[0].get('splits', [])
        if splits:
            st_vals = splits[0].get('stat', {})
            return {
                "name": nombre_pitcher,
                "era": float(st_vals.get('era', 4.00)),
                "whip": float(st_vals.get('whip', 1.30))
            }
    except Exception:
        pass
    return {"name": nombre_pitcher, "era": 4.00, "whip": 1.30}