from shapely.geometry import LineString, box, Polygon
from core.config import ATTENUATION_REGIONS as ATTENUATION_ZONES


def segment_intersects_zone(A, B, zone_polygon: Polygon):
    """Retourne True si le segment [A,B] intersecte une zone d'atténuation."""
    A_2D = A[:2] if len(A) == 3 else A
    B_2D = B[:2] if len(B) == 3 else B
    line = LineString([A_2D, B_2D])
    return line.intersects(zone_polygon)


def apply_path_based_attenuation(beacon_pos, filtered_rssi, gateway_positions):
    """Applique une atténuation du RSSI si le trajet passe dans une ou plusieurs zones définies."""
    adjusted_rssi = filtered_rssi.copy()
    for gw_name, gw_pos in gateway_positions.items():
        total_attenuation = 0
        for zone in ATTENUATION_ZONES:
            polygon = zone.get("polygon")
            if isinstance(polygon, Polygon) and segment_intersects_zone(beacon_pos, gw_pos, polygon):
                total_attenuation += zone["attenuation_db"]
        if gw_name in adjusted_rssi:
            adjusted_rssi[gw_name] += total_attenuation
        else:
            adjusted_rssi[gw_name] = total_attenuation

    return adjusted_rssi
