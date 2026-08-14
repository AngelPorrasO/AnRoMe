def obtener_stats_pitcher_api(pitcher_input):
    try:
        if isinstance(pitcher_input, int) or (isinstance(pitcher_input, str) and pitcher_input.isdigit()):
            pid = int(pitcher_input)
            if pid == 0: return None
            stats = statsapi.player_stat_data(pid, group="pitching", type="season")
        else:
            players = statsapi.lookup_player(pitcher_input)
            if not players: return None
            pid = players[0]['id']
            stats = statsapi.player_stat_data(pid, group="pitching", type="season")
        
        era, k9 = None, None
        for s in stats.get('stats', []):
            st = s.get('stats', {})
            if 'earnedRunAverage' in st: era = float(st['earnedRunAverage'])
            if 'strikeOutsPer9Inn' in st: k9 = float(st['strikeOutsPer9Inn'])
        
        if era is None: return None
        return {"k9": k9 or 8.0, "era": era, "fip": era}
    except:
        return None

def ejecutar_prediccion_ml(stats_local, stats_visit, pitcher_local_info, pitcher_visit_info, factor_estadio, nombre_local, nombre_visitante):
    # Valores de referencia realistas (promedio liga) solo si el pitcher no tiene datos
    era_l = pitcher_local_info['era'] if pitcher_local_info else 4.20
    fip_l = pitcher_local_info['fip'] if pitcher_local_info else 4.20
    era_v = pitcher_visit_info['era'] if pitcher_visit_info else 4.20
    fip_v = pitcher_visit_info['fip'] if pitcher_visit_info else 4.20
    
    efectividad_local = (era_l * 0.7) + (fip_l * 0.3)
    efectividad_visit = (era_v * 0.7) + (fip_v * 0.3)
    
    # Cálculos de ataque
    carreras_local = float(stats_local['R']) / float(stats_local['G'])
    carreras_visit = float(stats_visit['R']) / float(stats_visit['G'])
    
    fuerza_local = carreras_local * (4.00 / max(efectividad_visit, 1.5)) * factor_estadio
    fuerza_visit = carreras_visit * (4.00 / max(efectividad_local, 1.5))
    
    # Lógica de probabilidad
    diferencia = fuerza_local - fuerza_visit
    prob_local = 1.0 / (1.0 + np.exp(-diferencia * 0.8))
    
    return float(prob_local)