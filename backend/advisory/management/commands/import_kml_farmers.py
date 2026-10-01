"""
Management command: import_kml_farmers

Reads every .kml file in advisory/data/kml_farmers/ (one field boundary per
file, exported from Google Earth Pro — a single Placemark containing a
Polygon per farmer) and creates/updates one FarmProfile row per farmer:

  - farmer_name / farm_name  <- the KML Placemark <name> (falls back to the
    file name if the placemark has no name)
  - latitude / longitude     <- centroid of the boundary polygon
  - area_hectares            <- computed from the polygon itself (shoelace
    formula on a local equirectangular projection), overriding the model's
    generic default
  - boundary_geojson         <- the full boundary ring as [[lon, lat], ...],
    so the frontend map can draw the exact surveyed field outline
  - boundary_source_file     <- original filename, for traceability

Matching for update_or_create is done on boundary_source_file, so re-running
this command is safe and just refreshes the same 25 rows instead of
duplicating them.

Usage:
    python manage.py import_kml_farmers
    python manage.py import_kml_farmers --dir /path/to/other/kml/folder
    python manage.py import_kml_farmers --dry-run
"""

import datetime
import glob
import math
import os
import xml.etree.ElementTree as ET

from django.core.management.base import BaseCommand
from django.db import transaction

from advisory.models import FarmProfile

KML_NS = {"kml": "http://www.opengis.net/kml/2.2"}
DEFAULT_KML_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "kml_farmers")


def _parse_coordinates(text):
    """'<lon>,<lat>,<alt> <lon>,<lat>,<alt> ...' -> [[lon, lat], ...]"""
    points = []
    for chunk in text.split():
        parts = chunk.split(",")
        if len(parts) < 2:
            continue
        lon, lat = float(parts[0]), float(parts[1])
        points.append([lon, lat])
    return points


def _polygon_centroid_and_area_ha(points):
    """
    Shoelace centroid + area on a local equirectangular projection (longitude
    scaled by cos(mean latitude)). Accurate enough for single-field plots
    (a few hundred metres across) without needing a GIS/projection library.
    """
    if len(points) < 3:
        lon, lat = points[0]
        return lat, lon, 0.0

    mean_lat = sum(p[1] for p in points) / len(points)
    scale = math.cos(math.radians(mean_lat))
    m_per_deg_lat = 111_320.0
    m_per_deg_lon = 111_320.0 * scale

    xy = [(p[0] * m_per_deg_lon, p[1] * m_per_deg_lat) for p in points]

    # Ensure closed ring for the shoelace sum
    if xy[0] != xy[-1]:
        xy.append(xy[0])

    a = 0.0
    cx = 0.0
    cy = 0.0
    for i in range(len(xy) - 1):
        x0, y0 = xy[i]
        x1, y1 = xy[i + 1]
        cross = x0 * y1 - x1 * y0
        a += cross
        cx += (x0 + x1) * cross
        cy += (y0 + y1) * cross
    a *= 0.5

    if abs(a) < 1e-9:
        avg_lon = sum(p[0] for p in points) / len(points)
        avg_lat = sum(p[1] for p in points) / len(points)
        return avg_lat, avg_lon, 0.0

    cx /= 6 * a
    cy /= 6 * a
    area_m2 = abs(a)
    area_ha = area_m2 / 10_000.0

    centroid_lon = cx / m_per_deg_lon
    centroid_lat = cy / m_per_deg_lat
    return centroid_lat, centroid_lon, round(area_ha, 3)


def _extract_placemark(kml_path):
    tree = ET.parse(kml_path)
    root = tree.getroot()
    placemark = root.find(".//kml:Placemark", KML_NS)
    if placemark is None:
        return None

    name_el = placemark.find("kml:name", KML_NS)
    name = (name_el.text or "").strip() if name_el is not None else ""
    if not name:
        name = os.path.splitext(os.path.basename(kml_path))[0]
    # Title-case tidy-up for names that came through all lowercase in the KML
    if name == name.lower() or name == name.upper():
        name = name.title()

    coords_el = placemark.find(".//kml:Polygon//kml:coordinates", KML_NS)
    if coords_el is None or not (coords_el.text or "").strip():
        return None
    points = _parse_coordinates(coords_el.text)
    if len(points) < 3:
        return None

    return name, points


class Command(BaseCommand):
    help = "Import farmer field boundaries from KML files into FarmProfile (boundary_geojson, centroid, area)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dir",
            default=DEFAULT_KML_DIR,
            help="Folder containing .kml files (default: advisory/data/kml_farmers/)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Parse and print what would be imported without writing to the database.",
        )

    def handle(self, *args, **options):
        kml_dir = os.path.abspath(options["dir"])
        dry_run = options["dry_run"]

        kml_files = sorted(glob.glob(os.path.join(kml_dir, "*.kml")))
        if not kml_files:
            self.stderr.write(self.style.ERROR(f"No .kml files found in {kml_dir}"))
            return

        self.stdout.write(f"Found {len(kml_files)} KML file(s) in {kml_dir}\n")

        created, updated, skipped = 0, 0, 0

        with transaction.atomic():
            for kml_path in kml_files:
                filename = os.path.basename(kml_path)
                try:
                    parsed = _extract_placemark(kml_path)
                except ET.ParseError as exc:
                    self.stderr.write(self.style.ERROR(f"  ✗ {filename}: could not parse XML ({exc})"))
                    skipped += 1
                    continue

                if parsed is None:
                    self.stderr.write(self.style.ERROR(f"  ✗ {filename}: no usable Polygon/coordinates found"))
                    skipped += 1
                    continue

                name, points = parsed
                lat, lon, area_ha = _polygon_centroid_and_area_ha(points)

                self.stdout.write(
                    f"  • {name:<32} centroid=({lat:.6f}, {lon:.6f})  "
                    f"area≈{area_ha} ha  points={len(points)}  <- {filename}"
                )

                if dry_run:
                    continue

                defaults = {
                    "farm_name": f"{name} Field",
                    "farmer_name": name,
                    "latitude": lat,
                    "longitude": lon,
                    "area_hectares": area_ha if area_ha > 0 else 1.0,
                    "boundary_geojson": points,
                    "crop_name": "Sugarcane",
                    "variety": "Co 86032",
                    "soil_type": "Black Cotton",
                    "irrigation_method": "Drip",
                    # These field boundaries sit well outside Baramati (~19.1-19.2N,
                    # 77.1-77.2E) -- don't inherit the model's "Baramati, Pune"
                    # default, since that would silently mislabel every farm.
                    "village": "",
                }
                # planting_date has no model default and is required at INSERT
                # time, so it must be in `defaults` for the create path. Only
                # set it here for genuinely new rows -- update_or_create passes
                # the whole `defaults` dict on update too, so guard against
                # clobbering a real planting date on farms imported before.
                existing = FarmProfile.objects.filter(boundary_source_file=filename).first()
                if existing is None:
                    defaults["planting_date"] = datetime.date.today()

                farm, was_created = FarmProfile.objects.update_or_create(
                    boundary_source_file=filename,
                    defaults=defaults,
                )

                if was_created:
                    created += 1
                else:
                    updated += 1

        if dry_run:
            self.stdout.write(self.style.WARNING("\nDry run — no changes written."))
            return

        self.stdout.write(
            self.style.SUCCESS(f"\nDone. {created} farm(s) created, {updated} updated, {skipped} skipped.")
        )
        self.stdout.write(
            "Note: village/phone were left blank and planting_date defaulted to today — "
            "these KML files only carry field boundaries, so edit those fields in the "
            "admin or via the farms API once you have the real details."
        )
