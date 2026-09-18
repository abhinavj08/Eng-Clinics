"""
Solar geometry calculator (NOAA ephemeris equations).
Computes sun elevation & azimuth for a given lat/lon/time.
Used for theoretical max irradiance baseline in anomaly detection.
"""

import math
import datetime
from typing import Dict

class SolarGeometry:
    def __init__(self, lat=30.7046, lon=76.7179, tz_offset=5.5):
        self.lat = lat
        self.lon = lon
        self.tz = tz_offset

    def sun_position(self, dt=None) -> Dict[str, float]:
        if dt is None:
            dt = datetime.datetime.now()

        doy = dt.timetuple().tm_yday
        hour = dt.hour + dt.minute / 60.0 + dt.second / 3600.0
        gamma = (2 * math.pi / 365.0) * (doy - 1 + (hour - 12) / 24.0)

        # Equation of Time (minutes)
        eot = 229.18 * (
            0.000075 + 0.001868 * math.cos(gamma)
            - 0.032077 * math.sin(gamma)
            - 0.014615 * math.cos(2 * gamma)
            - 0.040849 * math.sin(2 * gamma)
        )

        # Solar declination (radians)
        decl = (
            0.006918 - 0.399912 * math.cos(gamma)
            + 0.070257 * math.sin(gamma)
            - 0.006758 * math.cos(2 * gamma)
            + 0.000907 * math.sin(2 * gamma)
            - 0.002697 * math.cos(3 * gamma)
            + 0.001480 * math.sin(3 * gamma)
        )

        time_offset = eot + 4.0 * self.lon - 60.0 * self.tz
        tst = hour * 60.0 + time_offset
        ha = math.radians((tst / 4.0) - 180.0)
        lat_r = math.radians(self.lat)

        cos_z = (math.sin(lat_r) * math.sin(decl)
                 + math.cos(lat_r) * math.cos(decl) * math.cos(ha))
        cos_z = max(-1.0, min(1.0, cos_z))
        zenith = math.acos(cos_z)

        elevation = 90.0 - math.degrees(zenith)

        sin_z = math.sin(zenith)
        if sin_z != 0:
            cos_az = ((math.sin(lat_r) * math.cos(zenith) - math.sin(decl))
                      / (math.cos(lat_r) * sin_z))
            cos_az = max(-1.0, min(1.0, cos_az))
            azimuth = 180.0 - math.degrees(math.acos(cos_az))
            if ha > 0:
                azimuth = 360.0 - azimuth
        else:
            azimuth = 180.0

        # Clear-sky irradiance model (simplified Hottel, W/m2)
        # At sea level, extraterrestrial ~1361 W/m2
        if elevation > 0:
            air_mass = 1.0 / (math.sin(math.radians(elevation)) + 0.50572 * (6.07995 + elevation) ** -1.6364)
            # Atmospheric transmittance ~0.7 at AM1
            irradiance = 1361.0 * (0.7 ** (air_mass ** 0.678))
            irradiance *= math.sin(math.radians(elevation))  # Horizontal surface
        else:
            irradiance = 0.0

        return {
            "elevation": round(elevation, 2),
            "azimuth": round(azimuth, 2),
            "is_day": elevation > 0,
            "irradiance_wm2": round(max(0, irradiance), 1),
            "declination_deg": round(math.degrees(decl), 2)
        }

    def day_profile(self, date=None):
        if date is None:
            date = datetime.date.today()
        pts = []
        for m in range(0, 1440, 10):
            h, mi = divmod(m, 60)
            dt = datetime.datetime.combine(date, datetime.time(h, mi))
            p = self.sun_position(dt)
            p["hour"] = h + mi / 60.0
            p["time_str"] = f"{h:02d}:{mi:02d}"
            pts.append(p)
        return pts
