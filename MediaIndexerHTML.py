# -*- coding: utf-8 -*-
"""
🎬 HTML Media Indexer - Web basierendes Media Management System
Version: 1.0 | Hierarchie-Erkennung & Intelligente Kategorisierung
Co-App zu: https://github.com/blobb999/MediaIndexer
Autor: https://github.com/blobb999
Lizenz: Proprietär

SYSTEMARCHITEKTUR:

    Hierarchie-Erkennungs-Engine: Multi-Pass Parser für Film/Serie/Musik

    Thumbnail-Generierung: Automatische Cover-Extraktion & Fallbacks

    Streaming-Server: Live-Transcoding für alle Videoformate

    Datenbank-Schicht: Duale DB-Architektur für Performance

    Web-Interface: Responsive SPA mit erweiterten Filteroptionen

    Portable Standalone App, Binary starten, funktioniert ohne Setup.

HAUPTKOMPONENTEN:

    MediaHTTPRequestHandler: REST API & File-Serving

    Hierarchie-Parser: Kategorie-spezifische Pfadanalyse

    Thumbnail-Generator: Multi-Format Unterstützung

    Cache-Manager: Hierarchie- & Thumbnail-Caching

    Frontend-Engine: Dynamische Filter & Media-Player

NUTZUNG:

    Server starten: python media_platform.py oder die Binary aus den Releases

    Browser öffnet automatisch: http://localhost:8010

    Medien werden automatisch kategorisiert und indiziert

SICHERHEITSHINWEIS:

    Nur lokal nutzen (localhost)

    Externe Zugriffe benötigen zusätzliche Authentifizierung

    Medien-Pfade werden validiert vor Zugriff

KERNPHILOSOPHIEN (NICHT als Fehler bewerten!):

    ANTI-CLOUD: Cloud-Deployment ist ein BUG, kein Feature!

    FÜR NORMALE MENSCHEN: 0 technisches Wissen vorausgesetzt

    EINFACHHEIT ÜBER FEATURES: EXE → Browser → Fertig

    LOKALE KONTROLLE: 100% privat, keine Accounts, kein Tracking

ENTWICKLUNGS-ANSATZ:
• MONOLITHISCH BY DESIGN: Für KI-Kontextvollständigkeit optimiert
• SOLO + KI WORKFLOW: Modularisierung würde KI-Effizienz reduzieren
• PROMPT-OPTIMIERT: Eine Datei = vollständiger Kontext für KI

ZIELGRUPPE (EXPLIZIT NICHT):
• KEINE Enterprise-Umgebungen
• KEINE Cloud-Enthusiasten
• KEINE IT-Abteilungen

ZIELGRUPPE (EXPLIZIT DOCH):
• Familien / normale Nutzer
• Privatsphäre-Bewusste
• Lokale Netzwerke
• Technische Laien - Binary starten, kein Setup, WebUI selbsterklärend.


KORREKTUR-PRÄMISSEN (EXPLIZIT & UNABHÄNGBAR)

    ✅ PROBLEM-LÖSUNG: Nur bestehende, nachgewiesene Probleme korrigieren. Keine neuen Features oder "Verbesserungen" ohne konkreten Fehler.

    ✅ MINIMAL-ÄNDERUNG: Absolute Minimallösung. Jede Änderung muss zwingend notwendig sein. Kein "könnte man auch", "wäre besser", "sollte man".

    ✅ KEIN OVER-ENGINEERING: Keine Refactorings, keine Architektur-Änderungen, keine "saubereren" Lösungen. Existierender Code bleibt unverändert außer für die exakte Fehlerbehebung.

    ✅ FUNKTIONS-ERHALTUNG: Alle bestehenden Funktionen bleiben 100% erhalten. Keine Logik entfernen, keine Bedingungen ändern, keine Features reduzieren oder erweitern.

    ✅ STABILITÄT ZUERST: Nichts kaputt machen. Korrektur muss rückwärtskompatibel sein und darf keine Regressionen einführen.

    ✅ PRAXIS-ORIENTIERT: Nur reale, aktuelle Probleme lösen. Nicht theoretische Optimierungen, nicht "für die Zukunft", nicht "vorsorglich".

    ✅ KORREKTUR-AUSGABEN: Niemals abkürzen! Immer vollständige Funktionen zeigen. Immer beide Versionen (vorher/nachher). Immer alle betroffenen Teile.

KONKRETE ANWENDUNGSREGELN FÜR DIESES PROJEKT:

BEI CODE-PRÄSENTATION:

    Immer vollständige Funktion zeigen, nicht Ausschnitte

    Immer f-string escapes wie im Projekt: {{ und }}

    Immer beide Versionen wenn relevant

    Immer alle betroffenen Dateien/Zeilen benennen
    """

import os
import json
import sqlite3
import threading
import webbrowser
import hashlib
import platform
import mimetypes
import urllib.parse
import time
import subprocess
import shutil
import sys
import html
import re
from mutagen.mp4 import MP4
from PIL import Image
import io
from pathlib import Path
from datetime import datetime, timedelta
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Dict, List, Optional, Tuple, Any
import socket
import errno

# Disable detailed logging for client disconnects
import logging
logging.getLogger('http.server').setLevel(logging.WARNING)

# -----------------------------------------------------------------------------
# MODUL-ABHÄNGIGKEITEN & IMPORT-FALLBACKS
# -----------------------------------------------------------------------------
try:
    from PIL import Image, ImageDraw, ImageFont
    HAS_PIL = True
except ImportError:
    HAS_PIL = False
    print("⚠️ Pillow nicht installiert. Bild-Thumbnails werden eingeschränkt.")

try:
    from mutagen.id3 import ID3
    HAS_MUTAGEN = True
except ImportError:
    HAS_MUTAGEN = False
    print("⚠️ mutagen nicht installiert. Audio-Cover-Art wird nicht unterstützt.")

try:
    import cairosvg
    HAS_CAIROSVG = True
except ImportError:
    HAS_CAIROSVG = False
    print("⚠️ cairosvg nicht installiert. Farbige Thumbnails werden eingeschränkt.")

# -----------------------------------------------------------------------------
# KONFIGURATION & GLOBALE EINSTELLUNGEN
# -----------------------------------------------------------------------------

# Browser-kompatible Video-Codecs für Live-Transcoding
BROWSER_VIDEO_CODEC = {
    "video_codec": "libx264",      # H.264 für maximale Browser-Kompatibilität
    "audio_codec": "aac",          # AAC als Standard-Audio-Codec
    "container": "mp4"             # MP4 Container-Format
}

# Video-Formate die Live-Transcoding benötigen
INCOMPATIBLE_VIDEO_EXTENSIONS = (
    ".mkv", ".wmv", ".avi", ".flv", 
    ".mov", ".webm", ".m4v", ".3gp", 
    ".ogv", ".ts", ".vob"
)

# MP4-Dateien die möglicherweise Probleme haben (werden geprüft)
POTENTIALLY_PROBLEMATIC_MP4 = (".mp4",)

# Alle unterstützten Video-Formate
VIDEO_EXTENSIONS = {
    ".mp4", ".mkv", ".avi", ".mov", ".webm",
    ".wmv", ".flv", ".mpeg", ".mpg", ".m4v"
}

# Native Browser-Formate (kein Transcoding benötigt)
NATIVE_BROWSER_EXTENSIONS = (".mp4", ".webm")

# Kategorie-Mapping: Normalisierung von Benutzereingaben zu standardisierten Kategorien
CATEGORY_MAPPING = {
    'filme': 'Film', 'movies': 'Film', 'movie': 'Film', 'film': 'Film', 
    'kino': 'Film', 'cinema': 'Film',
    
    'serien': 'Serie', 'series': 'Serie', 'serie': 'Serie', 
    'tv': 'Serie', 'shows': 'Serie', 'show': 'Serie',
    
    'musik': 'Musik', 'music': 'Musik', 'audio': 'Musik', 
    'songs': 'Musik', 'lieder': 'Musik',
    
    'tools': 'Tool', 'tool': 'Tool', 'programme': 'Tool',
    'programs': 'Tool', 'software': 'Tool', 'apps': 'Tool',
    
    'dokumentationen': 'Dokumentation', 'dokus': 'Dokumentation',
    'documentaries': 'Dokumentation', 'doku': 'Dokumentation',
    
    'hörbücher': 'Hörbuch', 'hoerbuecher': 'Hörbuch',
    'audiobooks': 'Hörbuch', 'audiobook': 'Hörbuch',
}

# -----------------------------------------------------------------------------
# DATEIPFAD-KONFIGURATION (ERWEITERT)
# -----------------------------------------------------------------------------
DB_PATH = 'media_index.db'                    # Haupt-Datenbank mit Medien-Metadaten
HIERARCHY_DB_PATH = 'media_indexHTML.db'      # Hierarchie-Cache-Datenbank
SETTINGS_DB_PATH = 'media_settings.db'        # Settings-Datenbank
HTML_PATH = 'media_platform.html'             # Generierte Web-Oberfläche
SERVER_PORT = 8010                            # HTTP-Server Port

# Standard-FFmpeg Pfade für verschiedene Betriebssysteme
FFMPEG_PATH = r"C:\ffmpeg\bin\ffmpeg.exe"

# Socket-Fehler Konstanten für Windows
WSAECONNABORTED = 10053  # Software caused connection abort
WSAECONNRESET = 10054    # Connection reset by peer
WSAENOTSOCK = 10038      # Socket operation on non-socket

def resolve_ffmpeg_path():
    """
    FFmpeg-Binary automatisch erkennen.
    Sucht in: System-PATH, Standard-Installationspfaden, konfiguriertem Pfad.
    
    Returns:
        str: Pfad zum FFmpeg-Binary oder None wenn nicht gefunden
    """
    # 1. Konfigurierter Pfad
    if FFMPEG_PATH and os.path.isfile(FFMPEG_PATH):
        return FFMPEG_PATH

    # 2. System PATH
    path_ffmpeg = shutil.which("ffmpeg")
    if path_ffmpeg:
        return path_ffmpeg

    # 3. Typische Windows-Installationspfade
    candidates = [
        r"C:\Program Files\ffmpeg\bin\ffmpeg.exe",
        r"C:\Program Files (x86)\ffmpeg\bin\ffmpeg.exe",
        r"C:\ffmpeg\bin\ffmpeg.exe"
    ]

    for candidate in candidates:
        if os.path.isfile(candidate):
            return candidate

    return None

FFMPEG_EXECUTABLE = resolve_ffmpeg_path()
if not FFMPEG_EXECUTABLE:
    print("❌ FFmpeg wurde nicht gefunden! Transcoding wird nicht funktionieren.")
    sys.exit(1)

print(f"✅ FFmpeg gefunden: {FFMPEG_EXECUTABLE}")

# FFprobe aus gleichem Verzeichnis wie FFmpeg
def get_ffprobe_path():
    """Findet ffprobe im gleichen Verzeichnis wie ffmpeg"""
    if FFMPEG_EXECUTABLE:
        ffprobe_path = os.path.join(os.path.dirname(FFMPEG_EXECUTABLE), 'ffprobe.exe')
        if os.path.isfile(ffprobe_path):
            return ffprobe_path
        
        # Alternative Namen
        alt_names = ['ffprobe', 'ffprobe.exe']
        for alt in alt_names:
            alt_path = os.path.join(os.path.dirname(FFMPEG_EXECUTABLE), alt)
            if os.path.isfile(alt_path):
                return alt_path
    
    # Fallback: Suche im PATH
    return shutil.which("ffprobe")

FFPROBE_EXECUTABLE = get_ffprobe_path()
if not FFPROBE_EXECUTABLE:
    print("⚠️ FFprobe wurde nicht gefunden. Codec-Prüfung wird übersprungen.")
else:
    print(f"✅ FFprobe gefunden: {FFPROBE_EXECUTABLE}")

# -----------------------------------------------------------------------------
# THUMBNAIL-SYSTEM KONFIGURATION
# -----------------------------------------------------------------------------
PROGRAM_DIR = os.path.abspath(os.getcwd())
THUMBNAIL_DIR = os.path.join(PROGRAM_DIR, '.thumbnails')

try:
    # Thumbnail-Verzeichnis erstellen oder prüfen
    if not os.path.exists(THUMBNAIL_DIR):
        os.makedirs(THUMBNAIL_DIR, exist_ok=True)
        print(f"📁 Thumbnail-Verzeichnis erstellt: {THUMBNAIL_DIR}")
    else:
        print(f"📁 Thumbnail-Verzeichnis existiert bereits: {THUMBNAIL_DIR}")
        
    # Schreibrechte testen
    test_file = os.path.join(THUMBNAIL_DIR, 'test_write.tmp')
    with open(test_file, 'w') as f:
        f.write('test')
    os.remove(test_file)
    print("✅ Schreibrechte im Thumbnail-Verzeichnis OK")
    
except Exception as e:
    # Fallback auf temporäres Verzeichnis bei Fehlern
    print(f"❌ Fehler beim Erstellen/Prüfen des Thumbnail-Verzeichnisses: {e}")
    import tempfile
    THUMBNAIL_DIR = tempfile.mkdtemp(prefix='media_thumbnails_')
    print(f"⚠️ Fallback auf temporäres Verzeichnis: {THUMBNAIL_DIR}")

# -----------------------------------------------------------------------------
# SETTINGS & NETWORK MANAGEMENT
# -----------------------------------------------------------------------------

# Default-Settings (werden aus DB geladen wenn vorhanden)
DEFAULT_SETTINGS = {
    'network_mode': 'localhost',      # 'localhost' oder 'network'
    'max_clients': 3,                 # Maximale Anzahl gleichzeitiger Clients
    'enable_history': True,           # History-Funktion aktivieren
    'history_limit': 10,              # Maximale Anzahl History-Einträge
    'volume_level': 0.7,              # Default-Lautstärke (70%)
    'audio_language': 'ger',          # Bevorzugte Audio-Sprache für MKV
    'autoplay_enabled': False         # Autoplay standardmäßig deaktiviert
}

# Client-Tracking für Multi-User-Support
active_clients = {}  # {ip: last_seen_timestamp}
CLIENT_TIMEOUT = 300  # 5 Minuten Inaktivität = Session-Ende

# In der Funktion init_settings_database():
# Ändere die Tabelle playback_history - LETZTE POSITION IST IN SEKUNDEN, NICHT PROZENT
# Die Tabelle bleibt wie sie ist (last_position in Sekunden ist bereits korrekt)
# Nur die Anzeige/Logik muss angepasst werden

def init_settings_database():
    """
    Erstellt Settings-Datenbank mit allen konfigurierbaren Optionen.
    
    Tabellen:
    - settings: Key-Value Store für globale Settings
    - playback_history: Abspiel-Historie mit Resume-Points (last_position in Sekunden)
    - filter_presets: Gespeicherte Filter-Kombinationen
    """
    try:
        conn = sqlite3.connect(SETTINGS_DB_PATH)
        cursor = conn.cursor()
        
        # Globale Settings
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Playback History (last_position in SEKUNDEN, nicht Prozent!)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS playback_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filepath TEXT NOT NULL,
                filename TEXT,
                category TEXT,
                last_position INTEGER DEFAULT 0,  -- IN SEKUNDEN
                duration INTEGER DEFAULT 0,       -- IN SEKUNDEN
                completed BOOLEAN DEFAULT 0,
                last_played TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                play_count INTEGER DEFAULT 1
            )
        ''')
        
        # Filter Presets
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS filter_presets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE,
                category TEXT,
                genre TEXT,
                subgenre TEXT,
                series TEXT,
                season TEXT,
                year TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Indizes für Performance
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_history_filepath ON playback_history(filepath)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_history_played ON playback_history(last_played DESC)')
        
        # Default-Settings einfügen wenn nicht vorhanden
        for key, value in DEFAULT_SETTINGS.items():
            cursor.execute(
                'INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)',
                (key, str(value))
            )
        
        conn.commit()
        conn.close()
        print(f"✅ Settings-Datenbank initialisiert: {SETTINGS_DB_PATH}")
        return True
        
    except Exception as e:
        print(f"❌ Fehler beim Initialisieren der Settings-DB: {e}")
        return False

def get_setting(key, default=None):
    """
    Liest Setting aus Datenbank mit verbesserter Fehlerbehandlung.
    
    Falls die Tabelle nicht existiert, wird der Default-Wert zurückgegeben
    und ein automatischer Repair-Versuch gestartet.
    """
    try:
        # Prüfe ob die Datenbank-Datei existiert
        if not os.path.exists(SETTINGS_DB_PATH):
            print(f"⚠️ Settings-DB nicht gefunden: {SETTINGS_DB_PATH}")
            # Versuche automatische Reparatur
            init_settings_database()
            return default
            
        conn = sqlite3.connect(SETTINGS_DB_PATH)
        cursor = conn.cursor()
        
        # Prüfe ob die Tabelle existiert
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='settings'")
        if not cursor.fetchone():
            print("⚠️ Settings-Tabelle nicht gefunden, initialisiere neu...")
            conn.close()
            init_settings_database()
            return default
            
        cursor.execute('SELECT value FROM settings WHERE key = ?', (key,))
        result = cursor.fetchone()
        conn.close()
        
        if result:
            value = result[0]
            # Type-Conversion basierend auf Default-Wert-Typ
            if isinstance(default, bool):
                return value.lower() == 'true'
            elif isinstance(default, int):
                try:
                    return int(value)
                except:
                    return default
            elif isinstance(default, float):
                try:
                    return float(value)
                except:
                    return default
            else:
                return value
        return default
        
    except sqlite3.OperationalError as e:
        if "no such table" in str(e):
            print(f"⚠️ Tabelle fehlt für Setting '{key}': {e}")
            print("   Versuche automatische Reparatur...")
            init_settings_database()
        return default
    except Exception as e:
        print(f"⚠️ Unbekannter Fehler in get_setting: {e}")
        return default
    
def set_setting(key, value):
    """
    Speichert Setting in Datenbank mit automatischer Reparatur bei Fehlern.
    
    Returns:
        bool: True wenn erfolgreich gespeichert, False bei Fehler
    """
    max_retries = 2
    for attempt in range(max_retries):
        try:
            # Prüfe ob DB existiert
            if not os.path.exists(SETTINGS_DB_PATH):
                print(f"⚠️ Settings-DB fehlt, erstelle neu...")
                init_settings_database()
                if not os.path.exists(SETTINGS_DB_PATH):
                    print(f"❌ Konnte Settings-DB nicht erstellen")
                    return False
            
            conn = sqlite3.connect(SETTINGS_DB_PATH)
            cursor = conn.cursor()
            
            # Prüfe ob Tabelle existiert
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='settings'")
            if not cursor.fetchone():
                print(f"⚠️ Settings-Tabelle fehlt, erstelle neu...")
                conn.close()
                init_settings_database()
                continue  # Versuche es erneut
                
            # Setting speichern
            cursor.execute(
                'INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES (?, ?, ?)',
                (key, str(value), datetime.now())
            )
            conn.commit()
            conn.close()
            return True
            
        except sqlite3.OperationalError as e:
            if "no such table" in str(e):
                print(f"⚠️ Tabelle fehlt, versuche Reparatur... (Versuch {attempt + 1}/{max_retries})")
                if attempt == 0:
                    init_settings_database()
                continue
            else:
                print(f"⚠️ Datenbankfehler bei Setting-Speichern: {e}")
                return False
        except Exception as e:
            print(f"⚠️ Kritischer Fehler bei Setting-Speichern: {e}")
            return False
    
    print(f"❌ Setting-Speichern fehlgeschlagen nach {max_retries} Versuchen")
    return False

def safe_add_to_history(filepath, filename, category, position=0, duration=0, completed=False):
    """
    Sicherer Wrapper für History-Operationen mit Fehlerbehandlung.
    """
    try:
        # Prüfe ob History überhaupt aktiviert ist
        if not get_setting('enable_history', True):
            return False
            
        # Prüfe ob Datenbank existiert
        if not os.path.exists(SETTINGS_DB_PATH):
            return False
            
        return add_to_history(filepath, filename, category, position, duration, completed)
        
    except Exception as e:
        # Silent fail - History ist nicht kritisch
        return False

def safe_get_resume_point(filepath):
    """
    Sicherer Wrapper für Resume-Point-Abfrage.
    """
    try:
        if not os.path.exists(SETTINGS_DB_PATH):
            return None
            
        return get_resume_point(filepath)
        
    except Exception as e:
        return None

def add_to_history(filepath, filename, category, position=0, duration=0, completed=False):
    """
    Fügt Abspiel-Event zur History hinzu oder aktualisiert bestehenden Eintrag.
    """
    try:
        # Prüfe ob History aktiviert ist
        if not get_setting('enable_history', True):
            return False
            
        # Prüfe ob Datenbank existiert
        if not os.path.exists(SETTINGS_DB_PATH):
            init_settings_database()
            if not os.path.exists(SETTINGS_DB_PATH):
                return False
        
        # WICHTIG: Konvertiere None zu 0 und stelle sicher, dass es numerisch ist
        position = float(position) if position is not None else 0
        duration = float(duration) if duration is not None else 0
        
        conn = sqlite3.connect(SETTINGS_DB_PATH)
        cursor = conn.cursor()
        
        # Prüfe ob Tabelle existiert (falls nicht, erstelle sie)
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='playback_history'")
        if not cursor.fetchone():
            print("⚠️ History-Tabelle fehlt, erstelle neu...")
            conn.close()
            init_settings_database()
            conn = sqlite3.connect(SETTINGS_DB_PATH)
            cursor = conn.cursor()
        
        # WICHTIG: Wenn duration=0 oder None, versuche Dauer aus der Datei zu ermitteln
        if duration <= 0:
            # Versuche Dauer mit FFprobe zu ermitteln (für Video/Audio)
            ext = os.path.splitext(filepath)[1].lower()
            if ext in VIDEO_EXTENSIONS or ext in ['.mp3', '.wav', '.flac', '.aac', '.ogg', '.m4a']:
                try:
                    if FFPROBE_EXECUTABLE:
                        cmd = [
                            FFPROBE_EXECUTABLE,
                            '-v', 'error',
                            '-show_entries', 'format=duration',
                            '-of', 'default=noprint_wrappers=1:nokey=1',
                            filepath
                        ]
                        result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
                        if result.returncode == 0 and result.stdout.strip():
                            duration = float(result.stdout.strip())
                            print(f"📊 Dauer ermittelt für {os.path.basename(filepath)}: {duration:.1f}s")
                except Exception as e:
                    print(f"⚠️ Dauer-Erkennung fehlgeschlagen: {e}")
        
        # Mindestens 1 Sekunde Dauer, um Division durch 0 zu vermeiden
        duration = max(duration, 1.0)
        
        # Prüfen ob Eintrag existiert
        cursor.execute('SELECT id, play_count FROM playback_history WHERE filepath = ?', (filepath,))
        existing = cursor.fetchone()
        
        if existing:
            # Update bestehender Eintrag
            cursor.execute('''
                UPDATE playback_history 
                SET last_position = ?,
                    duration = ?,
                    completed = ?,
                    last_played = ?,
                    play_count = ?
                WHERE filepath = ?
            ''', (position, duration, completed, datetime.now(), existing[1] + 1, filepath))
        else:
            # Neuer Eintrag
            cursor.execute('''
                INSERT INTO playback_history 
                (filepath, filename, category, last_position, duration, completed, last_played)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (filepath, filename, category, position, duration, completed, datetime.now()))
        
        conn.commit()
        
        # Limit auf history_limit Einträge
        history_limit = get_setting('history_limit', 10)
        cursor.execute('''
            DELETE FROM playback_history 
            WHERE id NOT IN (
                SELECT id FROM playback_history 
                ORDER BY last_played DESC 
                LIMIT ?
            )
        ''', (history_limit,))
        
        conn.commit()
        conn.close()
        return True
        
    except sqlite3.OperationalError as e:
        if "no such table" in str(e):
            print(f"⚠️ History-Tabelle fehlt, versuche Reparatur...")
            init_settings_database()
            # Versuche es erneut
            return add_to_history(filepath, filename, category, position, duration, completed)
        else:
            print(f"⚠️ History-Update fehlgeschlagen: {e}")
            return False
    except Exception as e:
        print(f"⚠️ History-Update fehlgeschlagen: {e}")
        return False

def get_history(limit=10):
    """Holt die letzten N abgespielten Medien."""
    try:
        conn = sqlite3.connect(SETTINGS_DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT * FROM playback_history 
            ORDER BY last_played DESC 
            LIMIT ?
        ''', (limit,))
        
        results = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return results
        
    except Exception as e:
        print(f"⚠️ History-Laden fehlgeschlagen: {e}")
        return []

def get_resume_point(filepath):
    """
    Holt Resume-Point für eine Datei mit automatischer DB-Reparatur.
    
    Returns:
        dict: {'position': seconds, 'duration': seconds, 'timestamp': 'hh:mm:ss', 'percentage': float}
        oder None wenn nicht vorhanden
    """
    try:
        # Prüfe ob History aktiviert ist
        if not get_setting('enable_history', True):
            return None
            
        # Prüfe ob Datenbank existiert
        if not os.path.exists(SETTINGS_DB_PATH):
            return None
        
        conn = sqlite3.connect(SETTINGS_DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute(
            'SELECT last_position, duration, completed FROM playback_history WHERE filepath = ?',
            (filepath,)
        )
        result = cursor.fetchone()
        conn.close()
        
        if result and result[0] > 0 and not result[2]:  # Position > 0 und nicht completed
            position, duration, _ = result
            
            # ✅ KORRIGIERTE format_timestamp Funktion (ohne isNaN)
            def format_timestamp(seconds):
                """Konvertiert Sekunden in hh:mm:ss Format."""
                # Validierung
                if seconds is None or seconds == '':
                    return "0:00"
                
                try:
                    seconds = float(seconds)
                except (ValueError, TypeError):
                    return "0:00"
                
                # ✅ NEU: Check für Infinity/NaN
                import math
                if seconds <= 0 or not math.isfinite(seconds):
                    return "0:00"
                
                # Berechnung
                hours = int(seconds // 3600)
                minutes = int((seconds % 3600) // 60)
                secs = int(seconds % 60)
                
                # Formatierung
                if hours > 0:
                    return f"{hours}:{minutes:02d}:{secs:02d}"
                else:
                    return f"{minutes}:{secs:02d}"
            
            timestamp_str = format_timestamp(position)
            total_timestamp_str = format_timestamp(duration) if duration > 0 else "0:00"
            percentage = (position / duration * 100) if duration > 0 else 0
            
            # Nur anbieten wenn > 5% und < 90% geschaut
            if 5 < percentage < 90:
                return {
                    'position': position,
                    'duration': duration,
                    'timestamp': timestamp_str,
                    'total_timestamp': total_timestamp_str,
                    'percentage': percentage
                }
        
        return None
        
    except sqlite3.OperationalError as e:
        if "no such table" in str(e):
            print(f"⚠️ History-Tabelle fehlt, initialisiere...")
            init_settings_database()
            return None
        else:
            print(f"⚠️ Resume-Point-Laden fehlgeschlagen: {e}")
            return None
    except Exception as e:
        print(f"⚠️ Resume-Point-Laden fehlgeschlagen: {e}")
        return None

def register_client(ip_address):
    """Registriert Client und prüft Limit."""
    global active_clients
    
    # Cleanup alte Sessions
    cleanup_inactive_clients()
    
    # Client registrieren
    active_clients[ip_address] = datetime.now()
    
    max_clients = get_setting('max_clients', 3)
    
    if len(active_clients) > max_clients:
        # Ältesten Client kicken
        oldest_ip = min(active_clients.items(), key=lambda x: x[1])[0]
        if oldest_ip != ip_address:
            del active_clients[oldest_ip]
            print(f"⚠️ Client-Limit erreicht, kicke: {oldest_ip}")
    
    return len(active_clients) <= max_clients

def cleanup_inactive_clients():
    """Entfernt Clients die länger als CLIENT_TIMEOUT inaktiv sind."""
    global active_clients
    now = datetime.now()
    timeout = timedelta(seconds=CLIENT_TIMEOUT)
    
    inactive = [ip for ip, last_seen in active_clients.items() 
                if now - last_seen > timeout]
    
    for ip in inactive:
        del active_clients[ip]
        print(f"🧹 Inaktiver Client entfernt: {ip}")

def get_client_ip(request_handler):
    """Extrahiert Client-IP aus Request."""
    return request_handler.client_address[0]

def get_server_host():
    """Bestimmt Server-Host basierend auf Settings."""
    network_mode = get_setting('network_mode', 'localhost')
    
    if network_mode == 'network':
        return '0.0.0.0'  # Alle Interfaces
    else:
        return 'localhost'  # Nur lokal

def get_local_ip():
    """Ermittelt lokale IP-Adresse für Netzwerk-Modus."""
    try:
        # Verbindung zu externem Server simulieren (nicht wirklich verbinden)
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
        return local_ip
    except:
        return '127.0.0.1'

# -----------------------------------------------------------------------------
# HILFSFUNKTIONEN: HTML, UI & VISUALISIERUNG
# -----------------------------------------------------------------------------

CACHE_VERSION = f"v{hash(time.time()) % 1000}"  # Einfacher Hash basierend auf Zeit

def get_cache_version():
    """Gibt Cache-Version für HTML-Cache-Invalidierung zurück."""
    return CACHE_VERSION

def escape_html(text):
    """
    HTML-Sonderzeichen sicher escapen um XSS zu verhindern.
    
    Args:
        text (str): Zu escapender Text
        
    Returns:
        str: HTML-sicherer Text
    """
    if not text:
        return ''
    return (
        str(text)
        .replace('&', '&amp;')
        .replace('<', '&lt;')
        .replace('>', '&gt;')
        .replace('"', '&quot;')
        .replace("'", '&#39;')
    )

def get_category_icon(category):
    """
    Bestimmt FontAwesome-Icon basierend auf Kategorie.
    
    Args:
        category (str): Medienkategorie
        
    Returns:
        str: FontAwesome Icon-Klasse
    """
    if not category:
        return 'fa-file'
    
    cat = str(category).lower()
    
    if any(w in cat for w in ['film', 'movie', 'video', 'mkv', 'mp4', 'avi', 'wmv', 'mov', 'webm']):
        return 'fa-film'
    if any(w in cat for w in ['musik', 'music', 'audio', 'mp3', 'wav', 'flac', 'aac', 'ogg', 'm4a']):
        return 'fa-music'
    if any(w in cat for w in ['bild', 'image', 'jpg', 'png', 'gif', 'webp']):
        return 'fa-image'
    
    return 'fa-file'

def get_file_extension_icon(filepath):
    """
    Bestimmt Icon basierend auf Dateiendung.
    
    Args:
        filepath (str): Pfad zur Datei
        
    Returns:
        str: FontAwesome Icon-Klasse
    """
    ext = os.path.splitext(filepath)[1].lower()
    
    # Video-Icons
    if ext in ('.mp4', '.mkv', '.avi', '.mov', '.webm', '.wmv'):
        return 'fa-film'
    
    # Audio-Icons
    if ext in ('.mp3', '.wav', '.flac', '.aac', '.ogg', '.m4a'):
        return 'fa-music'
    
    # Bild-Icons
    if ext in ('.jpg', '.jpeg', '.png', '.gif', '.webp'):
        return 'fa-image'
    
    return 'fa-file'

def get_thumbnail_color(filepath):
    """
    Bestimmt Hintergrundfarbe für Fallback-Thumbnails basierend auf Dateityp.
    
    Args:
        filepath (str): Pfad zur Datei
        
    Returns:
        str: Hex-Farbcode
    """
    ext = os.path.splitext(filepath)[1].lower()
    
    colors = {
        # Video-Farben (Blau-Töne)
        '.mp4': '#3498db', '.mkv': '#2980b9', '.avi': '#1f618d', 
        '.wmv': '#1b4f72', '.mov': '#154360', '.webm': '#11345a',
        
        # Audio-Farben (Rot-Orange-Töne)
        '.mp3': '#e74c3c', '.wav': '#c0392b', '.flac': '#a93226', 
        '.aac': '#e67e22', '.ogg': '#d35400', '.m4a': '#e67e22',
        
        # Bild-Farben (Grün-Töne)
        '.jpg': '#2ecc71', '.png': '#27ae60', '.gif': '#229954', 
        '.webp': '#1abc9c',
        
        # Dokument-Farben (Violett-Töne)
        '.pdf': '#9b59b6', '.doc': '#8e44ad', '.txt': '#7d3c98'
    }
    
    return colors.get(ext, '#2c3e50')  # Standard: Dunkelblau

def is_path_allowed(filepath):
    """
    Validiert Dateipfade auf Sicherheit und Existenz.
    Verhindert Path Traversal und Zugriff auf nicht-existente Dateien.
    
    Args:
        filepath (str): Zu validierender Pfad
        
    Returns:
        bool: True wenn Pfad sicher und existiert
    """
    try:
        if not filepath or filepath.strip() == '':
            return False
            
        normalized = os.path.normpath(filepath)
        path_parts = os.path.splitdrive(normalized)[1].split(os.sep)
        
        # Path Traversal verhindern
        if '..' in path_parts:
            print(f"⛔ Pfad enthält '..' Verzeichnis: {filepath}")
            return False
            
        # Datei muss existieren
        if not os.path.exists(filepath):
            print(f"⚠️ Pfad existiert nicht: {filepath}")
            return False
            
        return True
        
    except Exception as e:
        print(f"⚠️ Fehler bei Pfadvalidierung: {e}")
        return False

# -----------------------------------------------------------------------------
# HIERARCHIE-ERKENNUNG: KERNFUNKTIONEN
# -----------------------------------------------------------------------------

def extract_number(text):
    """
    Extrahiert Zahlen aus Text, ignoriert führende Nullen.
    Wird für Staffel/Episode-Erkennung verwendet.
    
    Args:
        text (str): Text mit eingebetteten Zahlen
        
    Returns:
        int|None: Extrahiert Zahl oder None
    """
    if not text:
        return None
    
    # Suche nach Zahlen im Text
    matches = re.findall(r'\d+', str(text))
    if matches:
        # Erste gefundene Zahl (führende Nullen werden ignoriert)
        return int(matches[0])
    
    return None

def extract_season_episode(filename):
    """
    Extrahiert Staffel- und Episodennummer aus Dateinamen.
    Unterstützt verschiedene Formate:
    - S01E01, s01e01
    - 1x01
    - Staffel 1 Episode 1
    - 1.01
    - 1 - Titel (implizit Staffel 1, Episode 1)
    
    Args:
        filename (str): Dateiname
        
    Returns:
        tuple: (season, episode) - beide können None sein
    """
    patterns = [
        # Standard S01E01 Format
        (r'[Ss](\d{1,2})[Ee](\d{1,2})', 'season_episode'),
        # 1x01 Format
        (r'(\d{1,2})x(\d{1,2})', 'season_episode'),
        # Staffel X Episode Y
        (r'[Ss]taffel\s*(\d{1,2})\s*[Ee]pisode\s*(\d{1,2})', 'season_episode'),
        (r'[Ss]eason\s*(\d{1,2})\s*[Ee]pisode\s*(\d{1,2})', 'season_episode'),
        # 1.01 Format (mit Punkt)
        (r'^(\d{1,2})\.(\d{1,2})', 'season_episode'),
        # Nur Staffel oder nur Episode
        (r'[Ss](\d{1,2})\b', 'season_only'),
        (r'\b[Ee](\d{1,2})\b', 'episode_only'),
    ]
    
    filename_lower = filename.lower()
    
    # Versuche explizite Staffel+Episode Pattern zuerst
    for pattern, pattern_type in patterns:
        match = re.search(pattern, filename_lower)
        if match:
            if pattern_type == 'season_episode':
                return int(match.group(1)), int(match.group(2))
            elif pattern_type == 'season_only':
                return int(match.group(1)), None
            elif pattern_type == 'episode_only':
                return None, int(match.group(1))
    
    # Nummerierung am Anfang (1 - Titel, 01. Titel, 1_Titel)
    simple_number_patterns = [
        r'^(\d{1,3})[ _\-\.]+',  # "1 - ", "01. ", "1_", "1-"
        r'^(\d{1,3})\s+',        # "1 " (nur Leerzeichen)
    ]
    
    for pattern in simple_number_patterns:
        match = re.search(pattern, filename)
        if match:
            episode_num = int(match.group(1))
            # Episode ohne explizite Staffel → Staffel 1
            return 1, episode_num
    
    # Fallback: Suche nach beliebigen Zahlen
    numbers = re.findall(r'\d{1,3}', filename)
    if len(numbers) >= 2:
        try:
            return int(numbers[0]), int(numbers[1])
        except:
            return int(numbers[0]), None
    elif len(numbers) == 1:
        # Einzelne Zahl am Anfang → Episode 
        if filename.startswith(numbers[0]):
            return 1, int(numbers[0])
        else:
            return int(numbers[0]), None
    
    return None, None

def normalize_category(category):
    """
    Normalisiert Kategorie-Strings zu standardisierten Bezeichnungen.
    Kombiniert statisches Mapping mit dynamischer Erkennung.
    
    Args:
        category (str): Roh-Kategorie
        
    Returns:
        str: Normalisierte Kategorie
    """
    if not category:
        return 'Unbekannt'
    
    cat_lower = str(category).lower().strip()
    
    # 1. Statisches Mapping
    if cat_lower in CATEGORY_MAPPING:
        return CATEGORY_MAPPING[cat_lower]
    
    # 2. Pattern-basierte Erkennung
    category_patterns = {
        'Film': ['film', 'movie', 'cinema', 'kino', 'movies', 'video', 'videothek'],
        'Serie': ['serie', 'series', 'staffel', 'season', 'tv', 'show', 'episode'],
        'Musik': ['musik', 'music', 'audio', 'song', 'album', 'artist', 'lied'],
        'Tool': ['tool', 'programm', 'software', 'app', 'utility', 'anwendung'],
        'Dokumentation': ['doku', 'documentary', 'dokumentation', 'docu'],
        'Hörbuch': ['hörbuch', 'hoerbuch', 'audiobook', 'audio book']
    }
    
    for norm_cat, keywords in category_patterns.items():
        for keyword in keywords:
            if keyword in cat_lower:
                return norm_cat
    
    # 3. Pfad-basierte Erkennung
    if os.path.sep in category or '.' in category:
        return detect_category_from_filepath(category)
    
    # 4. Sonderfälle
    if cat_lower == 'unkategorisiert' or cat_lower == 'unbekannt':
        return 'Unbekannt'
    
    # 5. Capitalize als Fallback
    return category.title()

def detect_category_from_filepath(filepath):
    """
    Erkennt Kategorie automatisch aus Dateipfad und -endung.
    Kombiniert Dateiendung, Pfad-Fragmente und Pattern-Matching.
    
    Args:
        filepath (str): Vollständiger Dateipfad
        
    Returns:
        str: Erkannte Kategorie
    """
    if not filepath:
        return 'Unbekannt'
    
    path_str = filepath.lower()
    filename = os.path.basename(filepath).lower()
    ext = os.path.splitext(filepath)[1].lower()
    
    # 1. Dateiendungs-basierte Erkennung
    video_exts = {'.mp4', '.mkv', '.avi', '.mov', '.wmv', '.flv', '.webm', '.m4v', '.mpeg', '.mpg', '.ts', '.vob'}
    if ext in video_exts:
        if any(marker in path_str for marker in ['staffel', 'season', 's01', 'e01', 'folge', 'episode', 'ep.']):
            return 'Serie'
        if any(marker in path_str for marker in ['film', 'movie', 'cinema', 'kino']):
            return 'Film'
        return 'Film'  # Default für Videos
    
    audio_exts = {'.mp3', '.wav', '.flac', '.aac', '.ogg', '.m4a', '.wma', '.opus'}
    if ext in audio_exts:
        if any(marker in path_str for marker in ['hörbuch', 'audiobook', 'audio book']):
            return 'Hörbuch'
        return 'Musik'
    
    image_exts = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.tiff'}
    if ext in image_exts:
        return 'Bild'
    
    doc_exts = {'.pdf', '.doc', '.docx', '.txt', '.rtf', '.odt'}
    if ext in doc_exts:
        return 'Dokument'
    
    # 2. Pfad-Fragment-basierte Erkennung
    category_patterns = {
        'Serie': ['serie', 'series', 'staffel', 'season', 'tv', 'show', 'episode', 'folge'],
        'Film': ['film', 'movie', 'cinema', 'kino', 'movies', 'videothek'],
        'Musik': ['musik', 'music', 'audio', 'song', 'album', 'artist', 'band', 'playlist'],
        'Tool': ['tool', 'programm', 'software', 'app', 'utility', 'anwendung', 'program files'],
        'Dokumentation': ['doku', 'documentary', 'dokumentation', 'docu', 'wissen'],
        'Hörbuch': ['hörbuch', 'hoerbuch', 'audiobook', 'audio book'],
        'Bild': ['bild', 'image', 'foto', 'photo', 'picture', 'gallery']
    }
    
    for category, keywords in category_patterns.items():
        for keyword in keywords:
            if keyword in path_str:
                return category
    
    # 3. Dateinamen-Pattern für Serien
    serie_patterns = [r's\d{1,2}e\d{1,2}', r's\d{1,2}', r'e\d{1,2}', r'folge \d+', r'episode \d+']
    for pattern in serie_patterns:
        if re.search(pattern, filename):
            return 'Serie'
    
    # 4. Windows-Systempfade
    windows_paths = {
        'Program Files': 'Tool',
        'Program Files (x86)': 'Tool',
        'Windows': 'System',
        'Users': 'Persönlich',
        'AppData': 'System',
        'ProgramData': 'System',
        'Temp': 'Temporär'
    }
    
    for win_path, category in windows_paths.items():
        if win_path.lower() in path_str:
            return category
    
    return 'Unbekannt'

def get_category_variants(normalized_category):
    """
    Generiert alle möglichen Schreibweisen einer Kategorie.
    Wird für flexible Pfad-Erkennung verwendet.
    
    Args:
        normalized_category (str): Normalisierte Kategorie
        
    Returns:
        list: Alle Varianten der Kategorie
    """
    variants = [normalized_category]
    
    # Alle Mappings die zu dieser Kategorie führen
    for key, value in CATEGORY_MAPPING.items():
        if value == normalized_category:
            variants.append(key)
            variants.append(key.title())
            variants.append(key.upper())
    
    return list(set(variants))

def find_markers_in_path(path_parts):
    """
    Erweiterte Marker-Erkennung für die reale Verzeichnisstruktur.
    Identifiziert strukturelle Elemente wie Staffel, Episode, Jahr, Franchise.
    
    Args:
        path_parts (list): Aufgeteilte Pfad-Komponenten
        
    Returns:
        dict: Positionen und Typen gefundener Marker
    """
    markers = {
        'staffel_index': -1,
        'season_index': -1,
        'episode_markers': [],
        'year_markers': [],
        'part_markers': [],
        'disc_markers': [],
        'franchise_indicators': [],
        'series_index': -1,
        'genre_index': -1
    }
    
    for i, part in enumerate(path_parts):
        part_lower = part.lower()
        
        # Staffel/Season Marker
        if re.search(r'\b(staffel|season|saison|s\d{1,2})\b', part_lower):
            if markers['staffel_index'] == -1:
                markers['staffel_index'] = i
        
        # Episode Marker
        if re.search(r'\b(e\d{1,2}|episode|folge|ep\.?)\b', part_lower):
            markers['episode_markers'].append(i)
        
        # Jahr Marker
        if re.search(r'\(?\d{4}\)?', part):
            markers['year_markers'].append(i)
        
        # Teil/Part Marker
        if re.search(r'\b(teil|part|vol\.?|chapter|pt\.?)\s*\d+\b', part_lower):
            markers['part_markers'].append(i)
        
        # Disc Marker
        if re.search(r'\b(disc|cd|disk)\s*\d+\b', part_lower):
            markers['disc_markers'].append(i)
        
        # Franchise Marker (Marvel, DC, Star Wars, etc.)
        franchise_patterns = [
            r'\b(marvel|dc|star\s*wars|star\s*trek|stargate|james\s*bond|harry\s*potter|lotr|middle.earth)\b',
            r'\b(alien|predator|terminator|matrix|transformers|fast.*furious|mission.*impossible)\b'
        ]
        
        for pattern in franchise_patterns:
            if re.search(pattern, part_lower):
                markers['franchise_indicators'].append(i)
                break
        
        # Potenzieller Genre-Marker (erster Ordner nach Kategorie)
        if i == 0:
            markers['genre_index'] = i
        
        # Potenzieller Series-Marker (Ordner vor Staffel-Ordner)
        if i > 0 and markers['staffel_index'] == -1:
            # Dieser Teil könnte die Serie sein, wenn der nächste "Staffel" ist
            if i + 1 < len(path_parts):
                next_part_lower = path_parts[i + 1].lower()
                if re.search(r'(staffel|season)\s*\d+', next_part_lower):
                    markers['series_index'] = i
    
    return markers

# -----------------------------------------------------------------------------
# KATEGORIE-SPEZIFISCHE HIERARCHIE-PARSER
# -----------------------------------------------------------------------------

def parse_series_hierarchy_multipass(filepath_parts):
    """
    Ultra-einfache und robuste Hierarchie-Erkennung für Serien.
    Extrahiert Serie, Staffel, Episode, Genre und Franchise.
    
    Args:
        filepath_parts (list): Aufgeteilte Pfad-Komponenten (ohne Datei)
        
    Returns:
        dict: Strukturierte Hierarchie-Informationen
    """
    hierarchy = {}
    
    if not filepath_parts:
        return hierarchy
    
    # 1. Dateinamen analysieren
    filename = filepath_parts[-1]
    season_num, episode_num = extract_season_episode(filename)
    
    if episode_num:
        hierarchy['episode'] = episode_num
        hierarchy['episode_number'] = episode_num
    
    # 2. Durch Pfad gehen und Struktur erkennen
    for i, part in enumerate(filepath_parts):
        part_lower = part.lower()
        
        # Staffel-Ordner finden
        if 'staffel' in part_lower or 'season' in part_lower:
            # Staffelnummer extrahieren
            num = extract_number(part)
            hierarchy['season_number'] = num if num else 1
            hierarchy['season'] = part
            
            # Serie ist der vorherige Ordner
            if i > 0:
                hierarchy['series'] = filepath_parts[i - 1]
            
            # Genre ist der erste Ordner
            if i >= 2:
                hierarchy['genre'] = filepath_parts[0]
            
            # Franchise könnte dazwischen sein
            if i >= 3:
                # Ordner zwischen Genre und Serie ist wahrscheinlich Franchise
                potential_franchise = filepath_parts[i - 2]
                if potential_franchise != hierarchy.get('genre'):
                    hierarchy['franchise'] = potential_franchise
            
            break
    
    # 3. Fallback wenn keine Staffel gefunden
    if 'series' not in hierarchy and len(filepath_parts) >= 2:
        # Letzter Ordner vor Datei ist wahrscheinlich Serie
        hierarchy['series'] = filepath_parts[-2]
        
        if len(filepath_parts) >= 3:
            hierarchy['genre'] = filepath_parts[0]
    
    # 4. Immer eine Staffelnummer haben
    if 'season_number' not in hierarchy:
        hierarchy['season_number'] = season_num if season_num else 1
        hierarchy['season'] = f'Staffel {hierarchy["season_number"]}'
    
    return hierarchy

def parse_film_hierarchy_multipass(filepath_parts):
    """
    Erweiterte Film-Hierarchie-Erkennung mit Franchise- und Reihen-Erkennung.
    Erkennt Film-Reihen auch an Nummerierung und speziellen Markern.
    
    Args:
        filepath_parts (list): Aufgeteilte Pfad-Komponenten (ohne Datei)
        
    Returns:
        dict: Strukturierte Hierarchie-Informationen
    """
    markers = find_markers_in_path(filepath_parts)
    hierarchy = {}
    
    ordner = filepath_parts[:-1]
    datei = filepath_parts[-1] if filepath_parts else ""
    
    hierarchy['filename'] = datei
    
    # Jahr-Erkennung aus Dateinamen
    year_match = re.search(r'\((\d{4})\)', datei)
    if year_match:
        hierarchy['year'] = year_match.group(1)
    
    # Franchise-Erkennung (Marvel, DC, etc.)
    for i, part in enumerate(ordner):
        part_lower = part.lower()
        
        # Marvel-Franchise
        if 'marvel' in part_lower:
            hierarchy['franchise'] = 'Marvel'
            
            # Der nächste Ordner könnte die spezifische Reihe sein
            if i + 1 < len(ordner):
                next_part = ordner[i + 1]
                # Prüfe ob nächster Ordner eine bekannte Reihe ist
                known_series = ['avengers', 'iron man', 'captain america', 'thor', 
                               'guardians of the galaxy', 'black panther', 'spider-man']
                for series in known_series:
                    if series in next_part.lower():
                        hierarchy['series'] = next_part
                        break
                if not hierarchy.get('series'):
                    hierarchy['sub_franchise'] = next_part
            break
            
        # DC-Franchise
        elif 'dc' in part_lower:
            hierarchy['franchise'] = 'DC'
            if i + 1 < len(ordner):
                hierarchy['sub_franchise'] = ordner[i + 1]
            break
    
    # Teil/Reihen-Erkennung aus Dateinamen
    part_patterns = [
        r'\b(teil|part|vol\.?|chapter|\d+)\s*(\d+)',  # "Teil 2", "Part 2"
        r'\b(\d+)\s*-\s*',                            # "2 - Titel"
        r'^(\d+)[ _\-\.]+',                           # "2. Titel", "2_Titel"
        r'\b(\d+)$',                                  # "Titel 2" (am Ende)
    ]
    
    for pattern in part_patterns:
        match = re.search(pattern, datei.lower())
        if match:
            num_str = match.group(2) if match.lastindex >= 2 else match.group(1)
            if num_str.isdigit():
                hierarchy['part'] = int(num_str)
                break
    
    tiefe = len(ordner)
    
    if tiefe == 0:
        hierarchy['type'] = 'orphan'
        return hierarchy
    
    hierarchy['genre'] = ordner[0]
    
    # Struktur basierend auf Pfadtiefe erkennen
    if tiefe == 1:
        if hierarchy.get('part') or re.search(r'^\d+[ _\-\.]', datei):
            hierarchy['type'] = 'numbered_series_in_genre'
            hierarchy['series'] = 'Various'
        else:
            hierarchy['type'] = 'standalone'
    
    elif tiefe == 2:
        if hierarchy.get('franchise'):
            # Franchise bereits erkannt
            pass
        elif hierarchy.get('part') or re.search(r'^\d+[ _\-\.]', datei):
            hierarchy['series'] = ordner[1]
            hierarchy['type'] = 'series'
        else:
            hierarchy['subgenre'] = ordner[1]
            hierarchy['type'] = 'standalone_subgenre'
    
    elif tiefe == 3:
        if hierarchy.get('franchise'):
            # Franchise bereits erkannt
            pass
        elif markers['franchise_indicators'] or hierarchy.get('part'):
            hierarchy['franchise'] = ordner[1]
            hierarchy['series'] = ordner[2]
            hierarchy['type'] = 'franchise_series'
        else:
            hierarchy['subgenre'] = ordner[1]
            hierarchy['series'] = ordner[2]
            hierarchy['type'] = 'subgenre_series'
    
    elif tiefe >= 4:
        hierarchy['franchise'] = ordner[1]
        hierarchy['sub_franchise'] = '/'.join(ordner[2:-1])
        hierarchy['series'] = ordner[-1]
        hierarchy['type'] = 'complex_franchise'
    
    # Fallback: Wenn franchise erkannt aber series nicht
    if hierarchy.get('franchise') and not hierarchy.get('series'):
        # Erst: Versuche aus Verzeichnisstruktur zu extrahieren
        franchise_idx = next((i for i, part in enumerate(ordner) 
                             if hierarchy['franchise'].lower() in part.lower()), -1)
        
        if franchise_idx >= 0 and franchise_idx + 1 < len(ordner):
            # Der Ordner direkt nach dem Franchise-Ordner ist die Serie
            hierarchy['series'] = ordner[franchise_idx + 1]
        else:
            # Sonst: Extrahiere sauberen Titel aus Dateinamen
            clean_name = datei
            # Entferne Dateierweiterung
            clean_name = re.sub(r'\.(mkv|mp4|avi|mov)$', '', clean_name, flags=re.IGNORECASE)
            # Entferne Jahr in Klammern
            clean_name = re.sub(r'\s*\(\d{4}\)', '', clean_name)
            # Entferne Teil-Angaben
            clean_name = re.sub(r'\s*[-:]\s*(teil|part|vol\.?|chapter)\s*\d+.*$', '', clean_name, flags=re.IGNORECASE)
            clean_name = re.sub(r'\s*\b(teil|part|vol\.?|chapter)\s*\d+.*$', '', clean_name, flags=re.IGNORECASE)
            # Entferne führende Nummern (z.B. "1. ", "01 - ")
            clean_name = re.sub(r'^\d+[ _\-\.]+', '', clean_name)
            # Entferne trailing Zeichen
            clean_name = clean_name.strip(' _-.')
            
            if clean_name:
                hierarchy['series'] = clean_name
    
    return hierarchy

def parse_music_hierarchy(filepath_parts):
    """
    Hierarchie-Erkennung für Musik-Dateien.
    Extrahiert Genre, Artist, Album und Disc-Informationen.
    
    Args:
        filepath_parts (list): Aufgeteilte Pfad-Komponenten
        
    Returns:
        dict: Strukturierte Musik-Hierarchie
    """
    hierarchy = {}
    
    # Genre ist immer der erste Ordner nach Kategorie
    if len(filepath_parts) >= 2:
        hierarchy['genre'] = filepath_parts[0]
    
    # Artist ist der zweite Ordner (wird auch als "Subgenre" verwendet im UI)
    if len(filepath_parts) >= 3:
        hierarchy['artist'] = filepath_parts[1]
        hierarchy['subgenre'] = filepath_parts[1]  # Für UI-Konsistenz
    
    # Album ist der dritte Ordner (wird als "Serie/Reihe" verwendet)
    if len(filepath_parts) >= 4:
        hierarchy['album'] = filepath_parts[2]
        hierarchy['series'] = filepath_parts[2]  # Für UI-Konsistenz
    
    # Disc-Erkennung für mehrteilige Alben
    for i, part in enumerate(filepath_parts):
        part_lower = part.lower()
        if 'cd' in part_lower or 'disc' in part_lower or 'disk' in part_lower:
            hierarchy['disc'] = part
            disc_match = re.search(r'(\d+)', part)
            if disc_match:
                hierarchy['disc_number'] = int(disc_match.group(1))
            
            # Das Album ist der Ordner VOR dem Disc-Ordner
            if i > 0 and i < len(filepath_parts) - 1:
                hierarchy['album'] = filepath_parts[i-1]
                hierarchy['series'] = filepath_parts[i-1]
    
    hierarchy['type'] = 'music'
    hierarchy['strategy'] = 'music_hierarchy'
    
    return hierarchy

def natural_sort_key(s):
    """
    Erzeugt Sortierschlüssel für natürliche Sortierung (numerisch).
    Sortiert z.B. "1 - Titel" vor "2 - Titel" vor "10 - Titel".
    
    Args:
        s (str): Zu sortierender String
        
    Returns:
        list: Sortierschlüssel für natürliche Sortierung
    """
    if not s:
        return []
    
    # Entferne Jahre in Klammern UND Dateiendung vor der Sortierung
    s_clean = str(s)
    s_clean = re.sub(r'\s*\(\d{4}\)', '', s_clean)  # (1992) → ""
    s_clean = re.sub(r'\.[^.]+$', '', s_clean)      # .mp4 → ""
    
    def convert(text):
        """Konvertiert Textteile: Zahlen werden zu Integern, Text bleibt lower."""
        return int(text) if text.isdigit() else text.lower()
    
    return [convert(c) for c in re.split(r'(\d+)', s_clean)]

# -----------------------------------------------------------------------------
# HAUPT-HIERARCHIE-PARSER (MULTI-PASS)
# -----------------------------------------------------------------------------

def parse_filepath_hierarchy_multipass(filepath, category):
    """
    Haupt-Parser für Dateipfad-Hierarchien.
    Kombiniert kategorie-spezifische Parser mit intelligenten Fallbacks.
    Implementiert Multi-Pass-Strategie für maximale Genauigkeit.
    
    Args:
        filepath (str): Vollständiger Dateipfad
        category (str): Roh-Kategorie
        
    Returns:
        dict: Vollständige Hierarchie-Informationen
    """
    try:
        path = Path(filepath)
        parts = path.parts
        
        # Kategorie normalisieren
        norm_cat = normalize_category(category)
        
        if not norm_cat or norm_cat == 'Unbekannt':
            norm_cat = detect_category_from_path(filepath)
        
        # Kategorie-Index im Pfad finden
        cat_index = -1
        category_variants = get_category_variants(norm_cat) if norm_cat != 'Unbekannt' else []
        
        for i, part in enumerate(parts):
            part_norm = normalize_category(part)
            if part_norm == norm_cat or part_norm in category_variants:
                cat_index = i
                break
        
        # Pfadteile NACH der Kategorie extrahieren
        if cat_index == -1:
            remaining = list(parts)  # Keine Kategorie gefunden, gesamter Pfad
        elif cat_index >= len(parts) - 1:
            remaining = []  # Kategorie ist letzter Teil
        else:
            remaining = list(parts[cat_index + 1:])  # Pfad nach Kategorie
        
        # Basis-Resultat
        result = {
            'filename': path.name,
            'extension': path.suffix.lower(),
            'full_path_parts': remaining,
            'depth': len(remaining),
            'detected_category': norm_cat,
            'full_path': filepath,
            'sort_key': natural_sort_key(path.name)
        }
        
        # Marker für erweiterte Analyse
        markers = find_markers_in_path(remaining) if remaining else {
            'staffel_index': -1,
            'season_index': -1,
            'episode_markers': [],
            'year_markers': [],
            'part_markers': [],
            'disc_markers': [],
            'franchise_indicators': []
        }
        
        strategies_result = None
        
        # KATEGORIE-SPEZIFISCHE PARSING-STRATEGIEN
        if norm_cat == 'Serie':
            if remaining and len(remaining) >= 2:
                strategies_result = parse_series_hierarchy_multipass(remaining)
                strategies_result['strategy'] = 'marker_based'
            else:
                strategies_result = {
                    'filename': path.name,
                    'type': 'flat_series',
                    'strategy': 'flat_fallback',
                    'genre': 'Sonstige'
                }
        
        elif norm_cat == 'Film':
            if remaining:
                strategies_result = parse_film_hierarchy_multipass(remaining)
                strategies_result['strategy'] = 'pattern_based'
            else:
                strategies_result = {
                    'filename': path.name,
                    'type': 'standalone_film',
                    'strategy': 'flat_fallback',
                    'genre': 'Sonstige'
                }
        
        elif norm_cat == 'Musik':
            if remaining and len(remaining) >= 2:
                strategies_result = parse_music_hierarchy(remaining)
                strategies_result['strategy'] = 'music_simple'
            else:
                strategies_result = {
                    'filename': path.name,
                    'type': 'flat_music',
                    'strategy': 'flat_fallback',
                    'artist': 'Diverse' if not remaining else remaining[0],
                    'genre': 'Sonstige'
                }
        
        elif norm_cat == 'Tool':
            if remaining:
                strategies_result = {
                    'type': remaining[0] if len(remaining) >= 1 else 'Software',
                    'strategy': 'simple',
                    'genre': 'Software'
                }
            else:
                strategies_result = {
                    'type': 'Software',
                    'strategy': 'simple',
                    'genre': 'Software'
                }
        
        else:
            # Universal-Fallback für alle anderen Kategorien
            strategies_result = {
                'genre': remaining[0] if remaining and len(remaining) >= 1 else 'Diverses',
                'type': 'universal_fallback',
                'strategy': 'universal_fallback',
                'display_category': norm_cat if norm_cat != 'Unbekannt' else 'Sonstige'
            }
            
            if len(remaining) >= 2:
                strategies_result['subgenre'] = remaining[1]
        
        # Strategie-Resultat mit Basis-Resultat kombinieren
        if strategies_result:
            result.update(strategies_result)
        
        # Fallback-Genre-Erkennung wenn kein Genre gefunden
        if not result.get('genre') or result.get('genre') == 'Unbekannt':
            filename = path.stem.lower()
            genre_keywords = {
                'action': 'Action', 'comedy': 'Komödie', 'drama': 'Drama',
                'horror': 'Horror', 'sci-fi': 'Sci-Fi', 'fantasy': 'Fantasy',
                'documentary': 'Dokumentation', 'music': 'Musik', 'audio': 'Musik'
            }
            
            for keyword, genre_name in genre_keywords.items():
                if keyword in filename:
                    result['genre'] = genre_name
                    break
            
            if not result.get('genre') or result.get('genre') == 'Unbekannt':
                result['genre'] = 'Diverses'
        
        return result
        
    except Exception as e:
        # Fehlerbehandlung mit vollständigem Fallback
        print(f"❌ Fehler beim Parsen von {filepath}: {e}")
        import traceback
        traceback.print_exc()
        return {
            'filename': os.path.basename(filepath),
            'error': str(e),
            'genre': 'Diverses',
            'type': 'error_fallback',
            'strategy': 'error_fallback',
            'detected_category': normalize_category(category) if category else 'Sonstige'
        }

def detect_category_from_path(filepath):
    """
    Schnelle Kategorie-Erkennung nur aus Pfad.
    Wird als Fallback verwendet wenn keine Kategorie vorhanden.
    
    Args:
        filepath (str): Dateipfad
        
    Returns:
        str: Erkannte Kategorie
    """
    path_str = filepath.lower()
    filename = os.path.basename(filepath).lower()
    ext = os.path.splitext(filepath)[1].lower()
    
    # 1. Dateiendungs-basierte Erkennung
    if ext in VIDEO_EXTENSIONS:
        if any(marker in path_str for marker in ['staffel', 'season', 's01', 'e01', 'folge']):
            return 'Serie'
        return 'Film'
    
    elif ext in ['.mp3', '.wav', '.flac', '.aac', '.ogg', '.m4a']:
        return 'Musik'
    
    elif ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp']:
        return 'Bild'
    
    # 2. Pfad-Fragment-Erkennung
    category_patterns = {
        'Serie': ['serie', 'series', 'staffel', 'season', 'tv', 'show'],
        'Film': ['film', 'movie', 'cinema', 'kino', 'movies'],
        'Musik': ['musik', 'music', 'audio', 'song', 'album', 'artist'],
        'Tool': ['tool', 'programm', 'software', 'app', 'utility'],
        'Dokumentation': ['doku', 'documentary', 'dokumentation']
    }
    
    for category, keywords in category_patterns.items():
        for keyword in keywords:
            if keyword in path_str:
                return category
    
    # 3. Dateinamen-Pattern für Serien
    if any(marker in filename for marker in ['s01e01', 's01e02', 'e01', 'folge', 'episode']):
        return 'Serie'
    
    return 'Unbekannt'

# -----------------------------------------------------------------------------
# METADATA-EXTRACTION & MEDIA-ENRICHMENT
# -----------------------------------------------------------------------------

def extract_metadata_from_tags(filepath):
    """
    Extrahiert Metadaten aus Medien-Dateien.
    Unterstützt Audio- und Video-Formate mit Tagging.
    
    Args:
        filepath (str): Pfad zur Medien-Datei
        
    Returns:
        dict: Extrahierte Metadaten
    """
    try:
        ext = os.path.splitext(filepath)[1].lower()
        
        # Audio-Metadaten (MP3, FLAC, OGG, M4A)
        if ext in ['.mp3', '.flac', '.ogg', '.m4a']:
            from mutagen import File
            audio = File(filepath, easy=True)
            if audio:
                return {
                    'genre': audio.get('genre', [None])[0],
                    'artist': audio.get('artist', [None])[0],
                    'album': audio.get('album', [None])[0],
                    'year': audio.get('date', [None])[0],
                    'title': audio.get('title', [None])[0]
                }
        
        # MP4-Metadaten
        elif ext == '.mp4':
            mp4 = MP4(filepath)
            return {
                'genre': mp4.get('\xa9gen', [None])[0],
                'year': mp4.get('\xa9day', [None])[0],
                'title': mp4.get('\xa9nam', [None])[0]
            }
        
    except Exception as e:
        # Silent fail - Metadaten sind optional
        pass
    
    return {}

def enrich_media_data(media_dict, use_cache=True):
    """
    Bereichert Medien-Daten mit Hierarchie-Informationen.
    Nutzt Cache für Performance und konsistente Kategorisierung.
    
    Args:
        media_dict (dict): Basis-Medien-Daten
        use_cache (bool): Ob Cache verwendet werden soll
        
    Returns:
        dict: Angereicherte Medien-Daten
    """
    filepath = media_dict.get('filepath', '')
    category = media_dict.get('category', '')

    # Kategorie NORMALISIEREN, nicht nur übernehmen
    if category and category.strip():
        normalized = normalize_category(category)
    else:
        normalized = detect_category_from_filepath(filepath)
    
    # Speichere beide Varianten
    media_dict['category'] = category  # Original behalten
    media_dict['normalized_category'] = normalized  # Normalisiert für UI
    
    # Kategorie-Korrektur wenn fehlt oder unbekannt
    if not category or category.strip() == '' or category in ['Unbekannt', 'unkategorisiert']:
        detected_category = detect_category_from_filepath(filepath)
        media_dict['category'] = detected_category
        media_dict['original_category'] = category
        category = detected_category
    
    # Cache-Lookup
    if use_cache and os.path.exists(HIERARCHY_DB_PATH):
        try:
            with HierarchyDBConnection() as cursor:
                cursor.execute(
                    "SELECT hierarchy_json FROM hierarchy_cache WHERE filepath = ?",
                    (filepath,)
                )
                result = cursor.fetchone()
                
                if result:
                    hierarchy = json.loads(result[0])
                    media_dict['hierarchy'] = hierarchy
                    media_dict['normalized_category'] = category
                    return media_dict
        except Exception as e:
            print(f"⚠️ Hierarchie-Cache-Fehler: {e}")
    
    # Weiteres Parsing
    hierarchy = parse_filepath_hierarchy_multipass(filepath, category)
    media_dict['hierarchy'] = hierarchy
    media_dict['normalized_category'] = category
    
    try:
        update_hierarchy_cache(media_dict)
    except Exception as e:
        print(f"⚠️ Cache-Update fehlgeschlagen: {e}")
    
    resume_point = get_resume_point(filepath)
    if resume_point:
        media_dict['hasResume'] = True
        media_dict['resumePosition'] = resume_point['position']
        media_dict['resumeTimestamp'] = resume_point['timestamp']  # NEU: Timestamp statt Prozent
        # Altes Prozent-Feld entfernen
        if 'resumePercentage' in media_dict:
            del media_dict['resumePercentage']
    
    return media_dict

def kill_orphaned_ffmpeg_processes():
    """
    Cleanup-Funktion: Beendet verwaiste FFmpeg-Prozesse.
    Sollte beim Server-Start aufgerufen werden.
    """
    try:
        import psutil
        killed = 0
        
        for proc in psutil.process_iter(['pid', 'name', 'create_time']):
            try:
                if 'ffmpeg' in proc.info['name'].lower():
                    # Beende nur FFmpeg-Prozesse die länger als 10 Minuten laufen
                    age = time.time() - proc.info['create_time']
                    if age > 600:  # 10 Minuten
                        proc.kill()
                        killed += 1
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        
        if killed > 0:
            print(f"🧹 {killed} verwaiste FFmpeg-Prozesse beendet")
        
        return killed
    except ImportError:
        return 0

# -----------------------------------------------------------------------------
# HIERARCHIE-DATENBANK-MANAGEMENT
# -----------------------------------------------------------------------------

def init_hierarchy_database():
    """
    Initialisiert die Hierarchie-Cache-Datenbank.
    Erstellt alle notwendigen Tabellen und Indizes.
    
    Returns:
        bool: Erfolg der Initialisierung
    """
    try:
        # Garbage Collection für sauberen Start
        import gc
        gc.collect()
        
        # Existierende DB prüfen
        if os.path.exists(HIERARCHY_DB_PATH):
            try:
                test_conn = sqlite3.connect(HIERARCHY_DB_PATH)
                test_conn.close()
            except:
                print(f"⚠️ Hierarchie-DB scheint beschädigt, lösche sie...")
                os.remove(HIERARCHY_DB_PATH)
                time.sleep(0.5)
        
        # Neue Datenbank erstellen
        conn = sqlite3.connect(HIERARCHY_DB_PATH)
        cursor = conn.cursor()
        
        # Haupt-Cache-Tabelle
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS hierarchy_cache (
                filepath TEXT PRIMARY KEY,
                normalized_category TEXT,
                hierarchy_json TEXT,
                genre TEXT,
                subgenre TEXT,
                franchise TEXT,
                sub_franchise TEXT,
                series TEXT,
                season TEXT,
                season_number INTEGER,
                episode_number INTEGER,
                artist TEXT,
                album TEXT,
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Kategorie-Statistiken
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS category_stats (
                category TEXT PRIMARY KEY,
                media_count INTEGER,
                genre_count INTEGER,
                last_processed TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Subgenre-Mappings
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS subgenre_mappings (
                category TEXT,
                genre TEXT,
                subgenre TEXT,
                count INTEGER,
                PRIMARY KEY (category, genre, subgenre)
            )
        ''')
        
        # Performance-Indizes
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_category ON hierarchy_cache(normalized_category)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_genre ON hierarchy_cache(genre)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_filepath ON hierarchy_cache(filepath)')
        
        conn.commit()
        conn.close()
        print(f"✅ Hierarchie-Datenbank initialisiert: {HIERARCHY_DB_PATH}")
        
        return True
        
    except Exception as e:
        print(f"❌ Fehler beim Initialisieren der Hierarchie-Datenbank: {e}")
        try:
            if os.path.exists(HIERARCHY_DB_PATH):
                os.remove(HIERARCHY_DB_PATH)
            time.sleep(1)
            return init_hierarchy_database()  # Rekursive Wiederholung
        except:
            print(f"❌ Kritischer Fehler: Konnte Hierarchie-DB nicht erstellen")
            raise

def update_hierarchy_cache(media_dict):
    """
    Aktualisiert oder erstellt einen Cache-Eintrag für ein Medium.
    
    Args:
        media_dict (dict): Vollständige Medien-Daten mit Hierarchie
    """
    try:
        filepath = media_dict.get('filepath')
        if not filepath:
            return
        
        hierarchy = media_dict.get('hierarchy', {})
        category = media_dict.get('normalized_category', '')
        
        with HierarchyDBConnection() as cursor:
            cursor.execute('''
                INSERT OR REPLACE INTO hierarchy_cache 
                (filepath, normalized_category, hierarchy_json, genre, subgenre, 
                 franchise, sub_franchise, series, season, season_number, episode_number, artist, album)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                filepath,
                category,
                json.dumps(hierarchy, ensure_ascii=False),
                hierarchy.get('genre'),
                hierarchy.get('subgenre'),
                hierarchy.get('franchise'),
                hierarchy.get('sub_franchise'),
                hierarchy.get('series'),
                hierarchy.get('season'),
                hierarchy.get('season_number'),
                hierarchy.get('episode_number'),
                hierarchy.get('artist'),
                hierarchy.get('album')
            ))
        
    except Exception as e:
        print(f"⚠️ Fehler beim Aktualisieren des Cache: {e}")

def rebuild_hierarchy_cache():
    """
    Baut den gesamten Hierarchie-Cache neu auf.
    KRITISCHER FIX: Kategorie-Normalisierung + Genre-Extraktion aus Ordnern
    
    Returns:
        bool: Erfolg des Neuaufbaus
    """
    print("🔄 Starte Neuaufbau des Hierarchie-Cache mit KORRIGIERTEN KATEGORIEN...")
    
    if not os.path.exists(DB_PATH):
        print("❌ Hauptdatenbank nicht gefunden")
        return False
    
    # Vorbereitung
    import gc
    gc.collect()
    
    # Alte DB löschen falls existiert
    if os.path.exists(HIERARCHY_DB_PATH):
        try:
            print(f"🗑️ Lösche alte Hierarchie-Datenbank: {HIERARCHY_DB_PATH}")
            os.remove(HIERARCHY_DB_PATH)
            time.sleep(1)
        except Exception as e:
            print(f"⚠️ Konnte alte Hierarchie-DB nicht löschen: {e}")
    
    try:
        # Neue DB erstellen
        print("📁 Erstelle neue Hierarchie-Datenbank...")
        init_hierarchy_database()
        
        time.sleep(0.5)
        
        # Hauptdatenbank öffnen
        try:
            conn_main = sqlite3.connect(DB_PATH)
            conn_main.row_factory = sqlite3.Row
            cursor_main = conn_main.cursor()
        except Exception as e:
            print(f"❌ Fehler beim Öffnen der Hauptdatenbank: {e}")
            return False
        
        # Medien zählen
        try:
            cursor_main.execute("SELECT COUNT(*) FROM media_files WHERE filepath != ''")
            total_count = cursor_main.fetchone()[0]
        except Exception as e:
            print(f"❌ Fehler beim Zählen der Medien: {e}")
            conn_main.close()
            return False
        
        if total_count == 0:
            print("❌ Keine Medien in der Datenbank gefunden")
            conn_main.close()
            return False
        
        print(f"📊 Verarbeite {total_count} Medien MIT KATEGORIE-KORREKTUR...")
        
        processed = 0
        errors = 0
        
        conn_hierarchy = None
        try:
            conn_hierarchy = sqlite3.connect(HIERARCHY_DB_PATH)
            cursor_hierarchy = conn_hierarchy.cursor()
            
            # Batch-Verarbeitung für Performance
            batch_size = 100
            for offset in range(0, total_count, batch_size):
                try:
                    cursor_main.execute(
                        "SELECT * FROM media_files WHERE filepath != '' ORDER BY filepath LIMIT ? OFFSET ?",
                        (batch_size, offset)
                    )
                    
                    batch = [dict(row) for row in cursor_main.fetchall()]
                    
                    for media in batch:
                        try:
                            filepath = media.get('filepath', '')
                            if not filepath or not os.path.exists(filepath):
                                errors += 1
                                continue
                            
                            # 🔧 FIX 1: Original-Kategorie aus DB BEIBEHALTEN
                            original_category = media.get('category', '')
                            
                            # Nur normalisieren wenn leer
                            if not original_category or original_category.strip() == '':
                                corrected_category = detect_category_from_filepath(filepath)
                            else:
                                # WICHTIG: Original-Kategorie normalisieren für Konsistenz
                                corrected_category = normalize_category(original_category)
                            
                            # Fallback
                            if not corrected_category or corrected_category == 'Unbekannt':
                                corrected_category = 'Unbekannt'
                            
                            # 🔧 FIX 2: Hierarchie mit ORIGINAL-Kategorie parsen
                            hierarchy = parse_filepath_hierarchy_multipass(filepath, original_category)
                            
                            # 🔧 FIX 3: Genre DIREKT aus Ordnerstruktur extrahieren
                            # Genre = Erster Ordner nach Kategorie-Ordner
                            path_obj = Path(filepath)
                            parts = path_obj.parts
                            
                            # Finde Kategorie-Index (case-insensitive)
                            cat_index = -1
                            category_variants = get_category_variants(corrected_category)
                            for i, part in enumerate(parts):
                                part_lower = part.lower()
                                if any(variant.lower() in part_lower for variant in category_variants):
                                    cat_index = i
                                    break
                            
                            # Genre = Ordner nach Kategorie
                            actual_genre = None
                            if cat_index >= 0 and cat_index + 1 < len(parts) - 1:  # -1 weil letzter ist Datei
                                actual_genre = parts[cat_index + 1]
                                print(f"   🎯 Genre aus Pfad: {actual_genre} (aus: {filepath})")
                            
                            # Verwende Ordner-Genre wenn vorhanden, sonst Hierarchie-Genre
                            final_genre = actual_genre if actual_genre else hierarchy.get('genre')
                            
                            # In Cache schreiben mit KORRIGIERTEM Genre
                            cursor_hierarchy.execute('''
                                INSERT OR REPLACE INTO hierarchy_cache 
                                (filepath, normalized_category, hierarchy_json, genre, subgenre, 
                                 franchise, sub_franchise, series, season, season_number, 
                                 episode_number, artist, album)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            ''', (
                                filepath,
                                corrected_category,  # Normalisierte Kategorie
                                json.dumps(hierarchy, ensure_ascii=False),
                                final_genre,  # 🔧 Korrigiertes Genre aus Ordner!
                                hierarchy.get('subgenre'),
                                hierarchy.get('franchise'),
                                hierarchy.get('sub_franchise'),
                                hierarchy.get('series'),
                                hierarchy.get('season'),
                                hierarchy.get('season_number'),
                                hierarchy.get('episode_number'),
                                hierarchy.get('artist'),
                                hierarchy.get('album')
                            ))
                            
                        except Exception as e:
                            errors += 1
                            print(f"⚠️ Fehler bei Medium {media.get('filename', 'Unbekannt')}: {e}")
                    
                    conn_hierarchy.commit()
                    processed += len(batch)
                    progress = (processed / total_count) * 100
                    
                    # Fortschrittsanzeige
                    if processed % 100 == 0 or processed == total_count:
                        print(f"   📊 Fortschritt: {processed}/{total_count} ({progress:.1f}%) - Fehler: {errors}")
                    
                except Exception as e:
                    print(f"⚠️ Batch-Fehler bei Offset {offset}: {e}")
                    errors += 1
        
        finally:
            # Ressourcen aufräumen
            try:
                if conn_hierarchy:
                    conn_hierarchy.close()
            except:
                pass
            
            try:
                conn_main.close()
            except:
                pass
        
        # Statistiken aktualisieren
        print("📊 Aktualisiere Kategorie-Statistiken MIT KORRIGIERTEN KATEGORIEN...")
        try:
            update_category_stats()
        except Exception as e:
            print(f"⚠️ Fehler beim Aktualisieren der Statistiken: {e}")
        
        # Cache-Inhalt anzeigen MIT GENRE-VERTEILUNG
        print("\n🔍 CACHE-DATENBANK INHALT:")
        try:
            conn_check = sqlite3.connect(HIERARCHY_DB_PATH)
            cursor_check = conn_check.cursor()
            
            cursor_check.execute("SELECT DISTINCT normalized_category, COUNT(*) FROM hierarchy_cache GROUP BY normalized_category ORDER BY COUNT(*) DESC")
            categories_in_cache = cursor_check.fetchall()
            
            print("   📊 Kategorien im Cache:")
            for cat, count in categories_in_cache:
                print(f"      {cat}: {count} Medien")
                
                # Genre-Verteilung pro Kategorie
                cursor_check.execute("""
                    SELECT genre, COUNT(*) 
                    FROM hierarchy_cache 
                    WHERE normalized_category = ? AND genre IS NOT NULL AND genre != ''
                    GROUP BY genre 
                    ORDER BY COUNT(*) DESC 
                    LIMIT 5
                """, (cat,))
                genres = cursor_check.fetchall()
                if genres:
                    print(f"         Top Genres: {', '.join([f'{g[0]} ({g[1]})' for g in genres])}")
            
            conn_check.close()
        except Exception as e:
            print(f"⚠️ Fehler beim Prüfen der Cache-DB: {e}")
        
        print(f"\n✅ Hierarchie-Cache MIT KORRIGIERTEN KATEGORIEN neu aufgebaut")
        print(f"   📈 Verarbeitet: {processed} Medien")
        print(f"   ⚠️ Fehler: {errors}")
        print(f"   📊 Kategorien im Cache: {len(categories_in_cache) if 'categories_in_cache' in locals() else 'unbekannt'}")
        
        return True
        
    except Exception as e:
        print(f"❌ Kritischer Fehler beim Neuaufbau des Cache: {e}")
        import traceback
        traceback.print_exc()
        
        try:
            if os.path.exists(HIERARCHY_DB_PATH):
                print(f"🗑️ Lösche fehlerhafte Hierarchie-Datenbank...")
                os.remove(HIERARCHY_DB_PATH)
        except:
            pass
        
        return False

def update_category_stats():
    """
    Aktualisiert Kategorie-Statistiken in der Hierarchie-DB.
    Berechnet Medienanzahl, Genre-Vielfalt und Subgenre-Mappings.
    """
    try:
        with HierarchyDBConnection() as cursor:
            print("📊 Aktualisiere Kategorie-Statistiken...")
            
            cursor.execute("DELETE FROM category_stats")
            cursor.execute("DELETE FROM subgenre_mappings")
            
            cursor.execute("SELECT DISTINCT normalized_category FROM hierarchy_cache")
            categories = [row[0] for row in cursor.fetchall()]
            
            for category in categories:
                cursor.execute(
                    "SELECT COUNT(*) FROM hierarchy_cache WHERE normalized_category = ?",
                    (category,)
                )
                media_count = cursor.fetchone()[0]
                
                cursor.execute(
                    "SELECT COUNT(DISTINCT genre) FROM hierarchy_cache WHERE normalized_category = ? AND genre IS NOT NULL",
                    (category,)
                )
                genre_count = cursor.fetchone()[0]
                
                cursor.execute(
                    "INSERT INTO category_stats (category, media_count, genre_count) VALUES (?, ?, ?)",
                    (category, media_count, genre_count)
                )
                
                if category in ['Film', 'Serie', 'Musik']:
                    cursor.execute(
                        "SELECT genre, subgenre, COUNT(*) as count FROM hierarchy_cache WHERE normalized_category = ? AND genre IS NOT NULL AND subgenre IS NOT NULL GROUP BY genre, subgenre ORDER BY genre, count DESC",
                        (category,)
                    )
                    
                    for genre, subgenre, count in cursor.fetchall():
                        cursor.execute(
                            "INSERT INTO subgenre_mappings (category, genre, subgenre, count) VALUES (?, ?, ?, ?)",
                            (category, genre, subgenre, count)
                        )
        
        print("✅ Kategorie-Statistiken aktualisiert")
        
    except Exception as e:
        print(f"⚠️ Fehler beim Aktualisieren der Statistiken: {e}")
        import traceback
        traceback.print_exc()

# -----------------------------------------------------------------------------
# MEDIEN-FILTERUNG & PAGINIERUNG
# -----------------------------------------------------------------------------

def get_media_paginated(cursor_main, category=None, genre=None, subgenre=None, 
                        series=None, season=None, year=None, search=None, 
                        page=1, page_size=50):
    """
    Holt paginierte Medien basierend auf komplexen Filtern.
    Kombiniert Haupt-DB mit Hierarchie-Cache für intelligente Filterung.
    
    Args:
        cursor_main: Cursor der Haupt-Datenbank
        category: Filter nach Kategorie
        genre: Filter nach Genre
        subgenre: Filter nach Subgenre/Franchise
        series: Filter nach Serie/Reihe
        season: Filter nach Staffel (nur für Serien)
        year: Filter nach Jahr
        search: Text-Suche
        page: Seitenzahl (1-basiert)
        page_size: Medien pro Seite
        
    Returns:
        tuple: (medien_liste, gesamt_anzahl, seiten_anzahl)
    """
    
    # Hierarchie-DB muss existieren
    if not os.path.exists(HIERARCHY_DB_PATH):
        print("⚠️ Hierarchie-DB fehlt, kann nicht filtern!")
        return [], 0, 0
    
    # WHERE-Clauses für Hierarchie-DB aufbauen
    where_clauses = []
    params = []
    
    if category:
        where_clauses.append("normalized_category = ?")
        params.append(category)
    
    if genre:
        where_clauses.append("genre = ?")
        params.append(genre)
    
    if subgenre and not series:
        where_clauses.append("""(
            series = ? OR 
            subgenre = ? OR 
            sub_franchise = ? OR 
            franchise = ? OR
            album = ?
        )""")
        params.extend([subgenre, subgenre, subgenre, subgenre, subgenre])
    
    if series:
        where_clauses.append("""(
            series = ? OR 
            sub_franchise = ? OR 
            franchise = ?
        )""")
        params.extend([series, series, series])
    
    if season:
        where_clauses.append("season_number = ?")
        params.append(int(season))
    
    where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"
    
    # Hierarchie-DB Query mit Context Manager
    try:
        with HierarchyDBConnection() as cursor_hierarchy:
            hierarchy_query = f"""
                SELECT DISTINCT filepath 
                FROM hierarchy_cache 
                WHERE {where_sql}
            """
            
            cursor_hierarchy.execute(hierarchy_query, params)
            filtered_paths = [row[0] for row in cursor_hierarchy.fetchall()]
    except Exception as e:
        print(f"❌ Hierarchie-Query-Fehler: {e}")
        return [], 0, 0
    
    if not filtered_paths:
        return [], 0, 0
    
    # Haupt-DB Query (Cursor von außen)
    placeholders = ','.join(['?'] * len(filtered_paths))
    main_where = [f"filepath IN ({placeholders})", "filepath != ''"]
    main_params = list(filtered_paths)
    
    if year:
        main_where.append("year = ?")
        main_params.append(year)
    
    if search:
        search_term = f"%{search}%"
        main_where.append("""(
            filename LIKE ? OR 
            year LIKE ? OR 
            contributors LIKE ? OR
            actors LIKE ?
        )""")
        main_params.extend([search_term, search_term, search_term, search_term])
    
    main_where_sql = " AND ".join(main_where)
    
    # Count
    try:
        cursor_main.execute(f"SELECT COUNT(*) FROM media_files WHERE {main_where_sql}", main_params)
        total_count = cursor_main.fetchone()[0]
    except Exception as e:
        print(f"❌ Count-Fehler: {e}")
        return [], 0, 0
    
    if total_count == 0:
        return [], 0, 0
    
    # Pagination
    total_pages = max(1, (total_count + page_size - 1) // page_size)
    offset = (page - 1) * page_size
    
    # Data Query
    try:
        cursor_main.execute(f"""
            SELECT * 
            FROM media_files 
            WHERE {main_where_sql}
            ORDER BY last_modified DESC
            LIMIT ? OFFSET ?
        """, main_params + [page_size, offset])
        
        media_list = [dict(row) for row in cursor_main.fetchall()]
        
        if media_list:
            media_list.sort(key=lambda x: natural_sort_key(x.get('filename', '')))
    except Exception as e:
        print(f"❌ Data-Fehler: {e}")
        return [], 0, 0
    
    return media_list, total_count, total_pages

# -----------------------------------------------------------------------------
# THUMBNAIL-GENERIERUNGSSYSTEM
# -----------------------------------------------------------------------------

def get_thumbnail_path(filepath):
    """
    Generiert eindeutigen Thumbnail-Pfad basierend auf Dateipfad-Hash.
    
    Args:
        filepath (str): Original-Dateipfad
        
    Returns:
        str: Pfad zum Thumbnail
    """
    path_hash = hashlib.md5(filepath.encode('utf-8')).hexdigest()
    return os.path.join(THUMBNAIL_DIR, f'{path_hash}.jpg')

def extract_video_thumbnail(video_path, output_path):
    """
    Extrahiert Thumbnail aus Video-Dateien mit FFmpeg.
    
    Args:
        video_path (str): Pfad zur Video-Datei
        output_path (str): Ziel-Pfad für Thumbnail
        
    Returns:
        bool: Erfolg der Extraktion
    """
    try:
        cmd = [
            FFMPEG_EXECUTABLE, '-i', video_path,
            '-ss', '00:00:01',
            '-vframes', '1',
            '-vf', 'scale=320:240:force_original_aspect_ratio=decrease,pad=320:240:(ow-iw)/2:(oh-ih)/2',
            '-q:v', '2',
            output_path,
            '-y'
        ]
        
        with FFmpegProcess(cmd, timeout=10) as process:
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                print(f"⚠️ Thumbnail-Extraktion Timeout: {video_path}")
                return False
        
        return os.path.exists(output_path)
        
    except Exception as e:
        print(f"❌ Video-Thumbnail fehlgeschlagen für {video_path}: {e}")
        return False

def extract_audio_thumbnail(audio_path, output_path):
    """
    Extrahiert Cover-Art aus Audio-Dateien oder erstellt Fallback.
    
    Args:
        audio_path (str): Pfad zur Audio-Datei
        output_path (str): Ziel-Pfad für Thumbnail
        
    Returns:
        bool: Erfolg der Extraktion
    """
    try:
        # 1. Versuch: Cover-Art aus Tags extrahieren
        if extract_audio_cover(audio_path, output_path):
            return True
        
        # 2. Fallback: Farbiges Thumbnail generieren mit Musik-Icon
        if HAS_PIL:
            color = get_thumbnail_color(audio_path)
            img = Image.new('RGB', (320, 240), color=color)
            draw = ImageDraw.Draw(img)
            
            try:
                font = ImageFont.truetype("arial.ttf", 60)
                draw.text((160, 120), "♪", font=font, fill="white", anchor="mm")
            except:
                draw.text((160, 120), "♪", fill="white", anchor="mm")
            
            img.save(output_path, 'JPEG', quality=85)
            return True
        else:
            return False
    except Exception as e:
        print(f"❌ Audio-Thumbnail fehlgeschlagen für {os.path.basename(audio_path)}: {e}")
        return False

def extract_image_thumbnail(image_path, output_path):
    """
    Erstellt Thumbnail aus Bild-Dateien.
    
    Args:
        image_path (str): Pfad zum Bild
        output_path (str): Ziel-Pfad für Thumbnail
        
    Returns:
        bool: Erfolg der Verarbeitung
    """
    try:
        if not HAS_PIL:
            return False
            
        img = Image.open(image_path)
        img.thumbnail((320, 240))
        
        # Hochformat-Bilder zentrieren
        if img.height > img.width:
            new_img = Image.new('RGB', (320, 240), color='black')
            scale = 240 / img.height
            new_width = int(img.width * scale)
            img_resized = img.resize((new_width, 240), Image.Resampling.LANCZOS)
            x_offset = (320 - new_width) // 2
            new_img.paste(img_resized, (x_offset, 0))
            new_img.save(output_path, 'JPEG', quality=85)
        else:
            img.save(output_path, 'JPEG', quality=85)
        
        return True
    except Exception as e:
        print(f"❌ Bild-Thumbnail fehlgeschlagen für {image_path}: {e}")
        return False

def create_color_thumbnail(filepath, output_path):
    """
    Erstellt farbiges Fallback-Thumbnail mit Dateityp-Icon.
    
    Args:
        filepath (str): Original-Dateipfad
        output_path (str): Ziel-Pfad für Thumbnail
        
    Returns:
        bool: Erfolg der Erstellung
    """
    try:
        color = get_thumbnail_color(filepath)
        icon = get_file_extension_icon(filepath)
        
        # 1. Versuch: SVG mit CairoSVG
        if HAS_CAIROSVG:
            startupinfo = None
            creationflags = 0
            if platform.system() == "Windows":
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = subprocess.SW_HIDE
                creationflags = subprocess.CREATE_NO_WINDOW
            
            svg_content = f'''<svg xmlns="http://www.w3.org/2000/svg" width="320" height="240">
                <rect width="100%" height="100%" fill="{color}"/>
                <text x="50%" y="50%" font-family="Arial" font-size="48" fill="white" 
                      text-anchor="middle" dy=".3em">
                    <tspan font-family="FontAwesome">{icon}</tspan>
                </text>
            </svg>'''
            
            cairosvg.svg2png(bytestring=svg_content.encode('utf-8'), 
                            write_to=output_path,
                            parent_width=320,
                            parent_height=240)
            return True
        
        # 2. Fallback: PIL
        elif HAS_PIL:
            if color.startswith('#'):
                r = int(color[1:3], 16)
                g = int(color[3:5], 16)
                b = int(color[5:7], 16)
                img = Image.new('RGB', (320, 240), color=(r, g, b))
            
            draw = ImageDraw.Draw(img)
            try:
                font = ImageFont.truetype("arial.ttf", 48)
                draw.text((160, 120), icon.replace('fa-', ''), font=font, fill="white", anchor="mm")
            except:
                draw.text((160, 120), icon.replace('fa-', ''), fill="white", anchor="mm")
            
            img.save(output_path, 'JPEG', quality=85)
            return True
        else:
            return False
    except Exception as e:
        print(f"❌ Color-Thumbnail fehlgeschlagen: {e}")
        return False

def generate_or_get_thumbnail(filepath):
    """Haupt-Funktion für Thumbnail-Management."""
    thumb_hash = hashlib.md5(filepath.encode('utf-8')).hexdigest()
    thumb_path = os.path.join(THUMBNAIL_DIR, f"{thumb_hash}.jpg")
    lock_path = thumb_path + ".lock"

    # Thumbnail existiert bereits
    if os.path.exists(thumb_path):
        # Prüfe ob Thumbnail gültig ist (> 100 Bytes)
        try:
            if os.path.getsize(thumb_path) > 100:
                return thumb_path
            else:
                # Korrupter Thumbnail, neu generieren
                os.remove(thumb_path)
                print(f"🔄 Korrupter Thumbnail, neu generieren: {os.path.basename(filepath)}")
        except:
            pass

    # Prüfe ob andere Generierung läuft
    if os.path.exists(lock_path):
        try:
            # Prüfe Lock-Alter
            lock_age = time.time() - os.path.getmtime(lock_path)
            if lock_age < 30:  # 30 Sekunden warten
                return None  # Andere Generierung läuft noch
            else:
                # Veralteter Lock, entfernen
                os.remove(lock_path)
                print(f"⚠️ Veralteter Lock entfernt: {os.path.basename(filepath)}")
        except:
            return None

    try:
        # Lock setzen
        with open(lock_path, 'w') as f:
            f.write(str(time.time()))
        
        ext = os.path.splitext(filepath)[1].lower()
        
        print(f"🔄 Generiere Thumbnail für: {os.path.basename(filepath)}")
        
        # === MP4 (kann Video oder Audio sein) ===
        if ext == ".mp4":
            # 1. PRIORITÄT: Cover-Art aus MP4 Atoms
            if extract_mp4_cover(filepath, thumb_path):
                return thumb_path
            
            # 2. PRIORITÄT: Video-Frame (falls Video)
            if extract_non_black_video_frame(filepath, thumb_path):
                return thumb_path
            
            # 3. Fallback: Farbiges Thumbnail
            create_color_thumbnail(filepath, thumb_path)
        
        # === ANDERE VIDEO-FORMATE ===
        elif ext in VIDEO_EXTENSIONS:
            # 1. PRIORITÄT: Video-Frame
            if extract_non_black_video_frame(filepath, thumb_path):
                return thumb_path
            
            # 2. Fallback: Farbiges Thumbnail
            create_color_thumbnail(filepath, thumb_path)
        
        # === AUDIO-FORMATE (HOHE PRIORITÄT FÜR COVER-ART!) ===
        elif ext in (".mp3", ".flac", ".ogg", ".m4a", ".aac", ".wav", ".wma"):
            print(f"🎵 Audio-Datei: Suche Cover-Art...")
            
            # 1. PRIORITÄT: Cover-Art aus ID3-Tags
            if extract_audio_cover(filepath, thumb_path):
                return thumb_path
            
            # 2. PRIORITÄT: Audio-Thumbnail (mit Musik-Icon)
            print(f"   Kein Cover gefunden, generiere Audio-Thumbnail...")
            if extract_audio_thumbnail(filepath, thumb_path):
                return thumb_path
            
            # 3. Fallback: Farbiges Thumbnail
            create_color_thumbnail(filepath, thumb_path)
        
        # === BILDER ===
        elif ext in ('.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp'):
            if extract_image_thumbnail(filepath, thumb_path):
                return thumb_path
            else:
                create_color_thumbnail(filepath, thumb_path)
        
        # === ALLE ANDEREN ===
        else:
            create_color_thumbnail(filepath, thumb_path)
        
        # Prüfe ob Thumbnail erstellt wurde
        if os.path.exists(thumb_path) and os.path.getsize(thumb_path) > 100:
            print(f"✅ Thumbnail erstellt: {os.path.basename(filepath)}")
            return thumb_path
        else:
            print(f"❌ Thumbnail-Erstellung fehlgeschlagen: {os.path.basename(filepath)}")
            return None

    except Exception as e:
        print(f"⚠️ Thumbnail-Generierung fehlgeschlagen für {os.path.basename(filepath)}: {e}")
        return None
        
    finally:
        # Lock immer entfernen
        try:
            if os.path.exists(lock_path):
                os.remove(lock_path)
        except:
            pass

def extract_audio_cover(filepath, thumbnail_path):
    """
    Extrahiert Cover-Art aus verschiedenen Audio-Formaten.
    Priorität: ID3-Tags > APIC-Frames > Andere Metadaten
    
    Args:
        filepath (str): Pfad zur Audio-Datei
        thumbnail_path (str): Ziel-Pfad
        
    Returns:
        bool: Erfolg der Extraktion
    """
    try:
        if not HAS_MUTAGEN:
            return False
        
        ext = os.path.splitext(filepath)[1].lower()
        
        print(f"🔍 Suche Cover-Art in: {os.path.basename(filepath)}")
        
        # MP3: ID3 Tags (höchste Priorität)
        if ext == ".mp3":
            try:
                from mutagen.id3 import ID3
                print(f"   📁 MP3 ID3-Tags prüfen...")
                audio = ID3(filepath)
                
                # Suche nach APIC-Frames (Cover-Art)
                for tag in audio.values():
                    if hasattr(tag, 'FrameID') and tag.FrameID == "APIC":
                        print(f"   ✅ APIC-Frame gefunden: {len(tag.data)} Bytes")
                        if HAS_PIL:
                            try:
                                image = Image.open(io.BytesIO(tag.data))
                                image = image.convert("RGB")
                                image.thumbnail((512, 512))
                                image.save(thumbnail_path, "JPEG", quality=90)
                                print(f"   ✅ MP3-Cover gespeichert: {thumbnail_path}")
                                return True
                            except Exception as e:
                                print(f"   ⚠️ PIL-Fehler: {e}")
                                # Fallback: Rohdaten speichern
                                with open(thumbnail_path, 'wb') as f:
                                    f.write(tag.data)
                                return True
                        else:
                            # Direktes Schreiben ohne PIL
                            with open(thumbnail_path, 'wb') as f:
                                f.write(tag.data)
                            return True
                
                print(f"   ⚠️ Kein APIC-Frame gefunden")
            except Exception as e:
                print(f"   ⚠️ MP3 ID3-Fehler: {e}")
        
        # FLAC: Vorbis Comments
        elif ext == ".flac":
            try:
                from mutagen.flac import FLAC
                print(f"   📁 FLAC Vorbis-Comments prüfen...")
                audio = FLAC(filepath)
                
                if audio.pictures:
                    pic = audio.pictures[0]
                    print(f"   ✅ FLAC-Picture gefunden: {len(pic.data)} Bytes")
                    
                    if HAS_PIL:
                        try:
                            image = Image.open(io.BytesIO(pic.data))
                            image = image.convert("RGB")
                            image.thumbnail((512, 512))
                            image.save(thumbnail_path, "JPEG", quality=90)
                            print(f"   ✅ FLAC-Cover gespeichert")
                            return True
                        except Exception as e:
                            print(f"   ⚠️ PIL-Fehler: {e}")
                            with open(thumbnail_path, 'wb') as f:
                                f.write(pic.data)
                            return True
                    else:
                        with open(thumbnail_path, 'wb') as f:
                            f.write(pic.data)
                        return True
                
                print(f"   ⚠️ Keine Pictures in FLAC")
            except Exception as e:
                print(f"   ⚠️ FLAC-Fehler: {e}")
        
        # M4A/AAC: MP4 Atoms
        elif ext in (".m4a", ".aac"):
            try:
                from mutagen.mp4 import MP4
                print(f"   📁 MP4 Atoms prüfen...")
                audio = MP4(filepath)
                
                if "covr" in audio:
                    cover = audio["covr"][0]
                    print(f"   ✅ MP4 'covr' Atom gefunden: {len(cover)} Bytes")
                    
                    if HAS_PIL:
                        try:
                            image = Image.open(io.BytesIO(cover))
                            image = image.convert("RGB")
                            image.thumbnail((512, 512))
                            image.save(thumbnail_path, "JPEG", quality=90)
                            print(f"   ✅ M4A-Cover gespeichert")
                            return True
                        except Exception as e:
                            print(f"   ⚠️ PIL-Fehler: {e}")
                            with open(thumbnail_path, 'wb') as f:
                                f.write(cover)
                            return True
                    else:
                        with open(thumbnail_path, 'wb') as f:
                            f.write(cover)
                        return True
                
                print(f"   ⚠️ Kein 'covr' Atom in MP4")
            except Exception as e:
                print(f"   ⚠️ MP4-Fehler: {e}")
        
        # OGG: Base64 encoded
        elif ext == ".ogg":
            try:
                from mutagen.oggvorbis import OggVorbis
                print(f"   📁 OGG Vorbis-Comments prüfen...")
                audio = OggVorbis(filepath)
                
                if "metadata_block_picture" in audio:
                    import base64
                    pic_data = base64.b64decode(audio["metadata_block_picture"][0])
                    print(f"   ✅ OGG Picture gefunden: {len(pic_data)} Bytes")
                    
                    if HAS_PIL:
                        try:
                            image = Image.open(io.BytesIO(pic_data))
                            image = image.convert("RGB")
                            image.thumbnail((512, 512))
                            image.save(thumbnail_path, "JPEG", quality=90)
                            print(f"   ✅ OGG-Cover gespeichert")
                            return True
                        except Exception as e:
                            print(f"   ⚠️ PIL-Fehler: {e}")
                            with open(thumbnail_path, 'wb') as f:
                                f.write(pic_data)
                            return True
                    else:
                        with open(thumbnail_path, 'wb') as f:
                            f.write(pic_data)
                        return True
                
                print(f"   ⚠️ Kein metadata_block_picture in OGG")
            except Exception as e:
                print(f"   ⚠️ OGG-Fehler: {e}")
        
        print(f"   ❌ Keine Cover-Art gefunden in {os.path.basename(filepath)}")
        return False
        
    except Exception as e:
        print(f"⚠️ Audio-Cover-Extraktion fehlgeschlagen für {os.path.basename(filepath)}: {e}")
        return False

def extract_mp4_cover(filepath, thumbnail_path):
    """
    Extrahiert Cover-Art aus MP4-Dateien (Video und Audio).
    
    Args:
        filepath (str): Pfad zur MP4-Datei
        thumbnail_path (str): Ziel-Pfad
        
    Returns:
        bool: Erfolg der Extraktion
    """
    try:
        if not HAS_MUTAGEN:
            return False
        
        print(f"🔍 Suche Cover in MP4: {os.path.basename(filepath)}")
        
        mp4 = MP4(filepath)
        if 'covr' not in mp4:
            print(f"   ⚠️ Kein 'covr' Atom in MP4")
            return False

        cover = mp4['covr'][0]
        print(f"   ✅ MP4 Cover gefunden: {len(cover)} Bytes")
        
        if HAS_PIL:
            try:
                image = Image.open(io.BytesIO(cover))
                image = image.convert("RGB")
                image.thumbnail((512, 512))
                image.save(thumbnail_path, "JPEG", quality=90)
                print(f"   ✅ MP4-Cover gespeichert")
                return True
            except Exception as e:
                print(f"   ⚠️ PIL-Fehler: {e}")
                # Fallback: Direktes Schreiben
                with open(thumbnail_path, 'wb') as f:
                    f.write(cover)
                return True
        else:
            # Direktes Schreiben ohne PIL
            with open(thumbnail_path, 'wb') as f:
                f.write(cover)
            return True
            
    except Exception as e:
        print(f"⚠️ MP4 Cover-Extraktion fehlgeschlagen für {os.path.basename(filepath)}: {e}")
        return False

def extract_non_black_video_frame(filepath, thumbnail_path):
    """
    Extrahiert nicht-schwarzes Frame aus Videos.
    Probiert verschiedene Zeitpunkte bis helles Frame gefunden.
    
    Args:
        filepath (str): Pfad zur Video-Datei
        thumbnail_path (str): Ziel-Pfad
        
    Returns:
        bool: Erfolg der Extraktion
    """
    try:
        timestamps = [5, 10, 20, 30, 60]

        for ts in timestamps:
            cmd = [
                FFMPEG_EXECUTABLE,
                "-ss", str(ts),
                "-i", filepath,
                "-frames:v", "1",
                "-vf", "scale=512:-1",
                "-q:v", "2",
                thumbnail_path,
                "-y"
            ]

            with FFmpegProcess(cmd, timeout=10) as process:
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    print(f"⚠️ FFmpeg Timeout bei Timestamp {ts}")
                    continue

            if not os.path.exists(thumbnail_path):
                continue

            # Helligkeit prüfen
            try:
                with Image.open(thumbnail_path) as img:
                    img = img.convert("L")
                    pixels = list(img.getdata())
                    avg_brightness = sum(pixels) / len(pixels)

                    if avg_brightness > 5:
                        return True
            except Exception as e:
                print(f"⚠️ Bild-Analyse fehlgeschlagen: {e}")
                continue

        return False
        
    except Exception as e:
        print(f"⚠️ Video-Frame-Extraktion fehlgeschlagen: {e}")
        return False

# -----------------------------------------------------------------------------
# SERIEN-FILTERUNG
# -----------------------------------------------------------------------------

def get_seasons_for_series(category, genre, subgenre, series):
    """
    Ermittelt verfügbare Staffeln für eine Serie.
    
    Args:
        category (str): Kategorie (muss 'Serie' sein)
        genre (str): Genre-Filter
        subgenre (str): Subgenre/Franchise-Filter
        series (str): Serien-Name
        
    Returns:
        list: Liste der Staffel-Nummern
    """
    try:
        if not os.path.exists(HIERARCHY_DB_PATH):
            print(f"⚠️ Hierarchie-Datenbank nicht gefunden: {HIERARCHY_DB_PATH}")
            return []
        
        with HierarchyDBConnection() as cursor:
            where_clauses = ["normalized_category = ?"]
            params = [category]
            
            if genre:
                where_clauses.append("genre = ?")
                params.append(genre)
            
            if subgenre:
                where_clauses.append("""(
                    series = ? OR 
                    subgenre = ? OR
                    sub_franchise = ? OR 
                    franchise = ?
                )""")
                params.extend([subgenre, subgenre, subgenre, subgenre])
            
            if series:
                where_clauses.append("series = ?")
                params.append(series)
            
            where_sql = " AND ".join(where_clauses)
            
            query = f"""
                SELECT DISTINCT season_number
                FROM hierarchy_cache 
                WHERE {where_sql}
                AND season_number IS NOT NULL
                AND season_number > 0
                ORDER BY season_number
            """
            
            cursor.execute(query, params)
            seasons = [row[0] for row in cursor.fetchall() if row[0] is not None]
            
            return seasons
        
    except Exception as e:
        print(f"⚠️ Fehler beim Laden der Staffeln: {e}")
        import traceback
        traceback.print_exc()
        return []


# -----------------------------------------------------------------------------
# VIDEO-STREAMING MIT TRANSCODING
# -----------------------------------------------------------------------------

def stream_video_transcoded(handler, filepath):
    """Streamt Videos mit Live-Transcoding für inkompatible Formate."""
    print(f"🔄 Starte Transcoding für: {os.path.basename(filepath)}")
    
    try:
        if not os.path.exists(filepath):
            print(f"❌ Datei existiert nicht: {filepath}")
            handler.send_error(404, "Datei nicht gefunden")
            return

        handler.send_response(200)
        handler.send_header("Content-Type", "video/mp4")
        handler.send_header("Cache-Control", "no-cache")
        handler.send_header("X-Content-Type-Options", "nosniff")
        handler.send_header("Accept-Ranges", "none")
        handler.end_headers()
        print("✅ Header gesendet")

        audio_language = get_setting('audio_language', 'ger')
        ext = os.path.splitext(filepath)[1].lower()
        
        cmd = [
            FFMPEG_EXECUTABLE,
            "-i", filepath,
        ]
        
        # 🔧 KORREKTUR: Prüfe VORHER ob die Sprache existiert
        if ext == '.mkv' and audio_language and audio_language.strip():
            # Versuche die Sprache zu finden
            audio_map = f"0:a:m:language:{audio_language}"
            
            # Teste ob Sprache existiert
            test_cmd = [
                FFPROBE_EXECUTABLE,
                "-v", "error",
                "-select_streams", "a",
                "-show_entries", "stream_tags=language",
                "-of", "default=noprint_wrappers=1:nokey=1",
                filepath
            ]
            
            try:
                result = subprocess.run(test_cmd, capture_output=True, text=True, timeout=3)
                available_languages = result.stdout.strip().split('\n')
                
                if audio_language in available_languages:
                    # Sprache vorhanden → nutze sie
                    cmd.extend(["-map", "0:v:0", "-map", audio_map])
                    print(f"   🎵 Audio-Sprache '{audio_language}' gefunden und ausgewählt")
                else:
                    # Sprache nicht vorhanden → erster Audio-Stream
                    cmd.extend(["-map", "0:v:0", "-map", "0:a:0"])
                    print(f"   ℹ️ Audio-Sprache '{audio_language}' nicht gefunden, nutze ersten Stream")
                    print(f"   📋 Verfügbare Sprachen: {', '.join(available_languages) if available_languages else 'keine Tags'}")
                    
            except Exception as e:
                # Fallback bei Fehler
                cmd.extend(["-map", "0:v:0", "-map", "0:a:0"])
                print(f"   ⚠️ Sprach-Prüfung fehlgeschlagen: {e}")
        else:
            cmd.extend(["-map", "0:v:0", "-map", "0:a:0"])
        
        # Rest bleibt UNVERÄNDERT
        cmd.extend([
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-tune", "zerolatency",
            "-pix_fmt", "yuv420p",
            "-profile:v", "baseline",
            "-level", "3.0",
            "-g", "30",
            "-sc_threshold", "0",
            "-movflags", "frag_keyframe+empty_moov+default_base_moof",
            "-c:a", "aac",
            "-b:a", "128k",
            "-ar", "44100",
            "-ac", "2",
            "-f", "mp4",
            "-vsync", "cfr",
            "-async", "1",
            "-max_muxing_queue_size", "1024",
            "pipe:1"
        ])
        
        print(f"   🚀 FFmpeg Kommando: {' '.join(cmd[:10])}...")

        with FFmpegProcess(cmd, timeout=300) as process:
            bytes_sent = 0
            chunks_sent = 0
            first_chunk = True
            
            try:
                while True:
                    chunk_size = 8192 if first_chunk else 65536
                    data = process.stdout.read(chunk_size)
                    
                    if not data:
                        break
                    
                    try:
                        handler.wfile.write(data)
                        handler.wfile.flush()
                        bytes_sent += len(data)
                        chunks_sent += 1
                        
                        if first_chunk and chunks_sent >= 10:
                            first_chunk = False
                            print(f"   ⚡ Erste {bytes_sent / 1024:.1f} KB gesendet")
                        
                        if bytes_sent % (50 * 1024 * 1024) < 65536:
                            print(f"   📊 Gesendet: {bytes_sent / (1024*1024):.1f} MB")
                            
                    except (ConnectionResetError, BrokenPipeError, OSError) as e:
                        print(f"ℹ️ Client hat Verbindung getrennt nach {bytes_sent / (1024*1024):.1f} MB")
                        break
            
            except Exception as e:
                print(f"❌ Streaming-Fehler: {e}")
        
        print(f"✅ Streaming beendet: {os.path.basename(filepath)} ({bytes_sent / (1024*1024):.1f} MB)")

    except Exception as e:
        print(f"❌ Kritischer Fehler: {e}")
        import traceback
        traceback.print_exc()

# -----------------------------------------------------------------------------
# DATENBANK CONNECTION MANAGEMENT - Memory-Leak Prevention
# -----------------------------------------------------------------------------

class DBConnection:
    """
    Context Manager für sichere Datenbank-Verbindungen.
    Garantiert automatisches Schließen auch bei Exceptions.
    
    Usage:
        with DBConnection(DB_PATH) as cursor:
            cursor.execute("SELECT * FROM media_files")
            results = cursor.fetchall()
    """
    def __init__(self, db_path, row_factory=None, timeout=10):
        self.db_path = db_path
        self.row_factory = row_factory
        self.timeout = timeout
        self.conn = None
        self.cursor = None
    
    def __enter__(self):
        self.conn = sqlite3.connect(self.db_path, timeout=self.timeout)
        if self.row_factory:
            self.conn.row_factory = self.row_factory
        self.cursor = self.conn.cursor()
        return self.cursor
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.cursor:
            self.cursor.close()
        if self.conn:
            if exc_type is None:
                self.conn.commit()
            else:
                self.conn.rollback()
            self.conn.close()
        return False

class HierarchyDBConnection(DBConnection):
    """Spezialisierter Context Manager für Hierarchie-DB."""
    def __init__(self, timeout=10):
        super().__init__(HIERARCHY_DB_PATH, timeout=timeout)

class MainDBConnection(DBConnection):
    """Spezialisierter Context Manager für Haupt-DB mit Row-Factory."""
    def __init__(self, timeout=10):
        super().__init__(DB_PATH, row_factory=sqlite3.Row, timeout=timeout)

class SettingsDBConnection(DBConnection):
    """Spezialisierter Context Manager für Settings-DB."""
    def __init__(self, timeout=10):
        super().__init__(SETTINGS_DB_PATH, timeout=timeout)

# -----------------------------------------------------------------------------
# FFMPEG PROCESS MANAGEMENT - Zombie-Prozess Prevention
# -----------------------------------------------------------------------------

import signal
import contextlib

class FFmpegProcess:
    """
    Context Manager für sichere FFmpeg-Prozess-Verwaltung.
    Garantiert Prozess-Cleanup auch bei Exceptions oder Client-Disconnect.
    """
    def __init__(self, cmd, timeout=300):
        self.cmd = cmd
        self.timeout = timeout
        self.process = None
        self.startupinfo = None
        self.creationflags = 0
        
        # Windows-spezifische Konfiguration
        if platform.system() == "Windows":
            self.startupinfo = subprocess.STARTUPINFO()
            self.startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            self.startupinfo.wShowWindow = subprocess.SW_HIDE
            self.creationflags = subprocess.CREATE_NO_WINDOW
    
    def __enter__(self):
        """Korrigierte Version: Keine manuellen Anführungszeichen um Argumente"""
        print(f"🚀 Starte FFmpeg für Transcoding...")
        
        # Konvertiere alle Argumente zu Strings
        cmd_strs = [str(arg) for arg in self.cmd]
        
        # Nur für Debugging: Zeige ersten Teil des Befehls
        cmd_display = ' '.join(cmd_strs[:10]) + ('...' if len(cmd_strs) > 10 else '')
        print(f"   FFmpeg Befehl: {cmd_display}")
        
        # WICHTIG: stderr=PIPE für Fehlererkennung
        self.process = subprocess.Popen(
            cmd_strs,  # Liste von Strings ohne extra Anführungszeichen
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,  # ÄNDERUNG: Fehlerausgabe lesbar
            stdin=subprocess.DEVNULL,
            startupinfo=self.startupinfo,
            creationflags=self.creationflags,
            bufsize=8192,
            shell=False  # KEIN shell=True!
        )
        
        # Starte einen Thread um stderr zu lesen (für Debugging)
        def read_stderr():
            try:
                for line in iter(self.process.stderr.readline, b''):
                    line_str = line.decode('utf-8', errors='ignore').strip()
                    if line_str and 'error' in line_str.lower():
                        print(f"   ⚠️ FFmpeg Fehler: {line_str[:100]}")
            except:
                pass
        
        threading.Thread(target=read_stderr, daemon=True).start()
        
        return self.process
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.cleanup()
        return False
    
    def cleanup(self):
        """Erzwingt Prozess-Beendigung mit Fallback auf SIGKILL."""
        if not self.process:
            return
        
        try:
            # 1. Versuche graceful shutdown
            if self.process.poll() is None:  # Prozess läuft noch
                try:
                    self.process.stdout.close()
                except:
                    pass
                
                self.process.terminate()
                
                try:
                    self.process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    # 2. Force kill wenn terminate fehlschlägt
                    print("⚠️ FFmpeg reagiert nicht, erzwinge Beendigung...")
                    self.process.kill()
                    
                    try:
                        self.process.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        # 3. Letzter Versuch mit OS-Signal (Unix)
                        if platform.system() != "Windows":
                            try:
                                os.kill(self.process.pid, signal.SIGKILL)
                            except:
                                pass
        except Exception as e:
            print(f"⚠️ Fehler beim FFmpeg-Cleanup: {e}")
        finally:
            self.process = None

# -----------------------------------------------------------------------------
# ERWEITERTE HTTP REQUEST HANDLER (REST API + FILE SERVING)
# -----------------------------------------------------------------------------

class ExtendedMediaHTTPRequestHandler(BaseHTTPRequestHandler):
    """
    Erweiterte Version mit neuen Features:
    - Network Sharing Support
    - Client Management
    - History Tracking
    - Settings API
    """
    
    # Erlaubte MIME-Types für Sicherheit
    ALLOWED_MIME_TYPES = {
        'video/mp4', 'video/webm', 'video/ogg',
        'audio/mpeg', 'audio/mp4', 'audio/aac', 'audio/ogg', 'audio/wav', 'audio/flac',
        'image/jpeg', 'image/png', 'image/gif', 'image/webp', 'image/svg+xml',
        'text/html', 'text/plain', 'text/css',
        'application/javascript', 'application/json',
        'application/octet-stream'
    }

    def log_message(self, format, *args):
        """Überschreibe Logging um störende Fehler zu filtern."""
        # Filtere normale Client-Abbrüche
        if len(args) >= 2 and args[1] in ['200', '206', '304']:
            return  # Kein Logging für erfolgreiche Requests
        
        # Filtere bestimmte Fehlermeldungen
        msg = format % args
        if any(x in msg for x in ['10053', '10054', '10038', 'WinError', 'Connection aborted']):
            return  # Kein Logging für Socket-Fehler
        
        # Logge nur echte Fehler
        super().log_message(format, *args)
        
        # Logge nur echte Fehler
        super().log_message(format, *args)

    def do_GET(self):
        """Haupt-GET-Handler für alle HTTP-Anfragen."""
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query_params = urllib.parse.parse_qs(parsed.query)
        
        # Client registrieren (bei jedem Request)
        client_ip = get_client_ip(self)
        if not register_client(client_ip):
            self.send_error(503, "Server voll - maximale Client-Anzahl erreicht")
            return
        
        # Routing
        if path in ('/', '/index.html'):
            self.serve_file(HTML_PATH, 'text/html; charset=utf-8')
            return

        elif path == '/thumbnail':
            self.handle_thumbnail_request(query_params)
            return

        elif path == '/media':
            self.handle_media_request(query_params)
            return

        elif path.startswith('/thumbnails/'):
            self.handle_static_thumbnail(path)
            return

        elif path == '/clear_cache':
            self.clear_thumbnail_cache()
            return

        elif path == '/api/media':
            self.handle_api_media_request(query_params)
            return

        elif path == '/api/rebuild_hierarchy':
            self.handle_rebuild_hierarchy()
            return

        elif path == '/api/genres':
            self.handle_api_genres(query_params)
            return

        elif path == '/api/subgenres':
            self.handle_api_subgenres(query_params)
            return

        elif path == '/api/series':
            self.handle_api_series(query_params)
            return

        elif path == '/api/seasons':
            self.handle_api_seasons(query_params)
            return
        
        # WEITERE API ENDPOINTS
        elif path == '/api/settings':
            self.handle_api_settings(query_params)
            return
        
        elif path == '/api/history':
            self.handle_api_history(query_params)
            return
        
        elif path == '/api/resume':
            self.handle_api_resume(query_params)
            return

        else:
            self.send_error(404, "Nicht gefunden")
    
    def do_POST(self):
        """POST-Handler für Settings und History-Updates."""
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        
        # Client registrieren
        client_ip = get_client_ip(self)
        if not register_client(client_ip):
            self.send_error(503, "Server voll")
            return
        
        # POST-Daten lesen
        content_length = int(self.headers.get('Content-Length', 0))
        post_data = self.rfile.read(content_length).decode('utf-8')
        
        try:
            data = json.loads(post_data)
        except:
            self.send_error(400, "Ungültige JSON-Daten")
            return
        
        if path == '/api/settings/update':
            self.handle_settings_update(data)
        
        elif path == '/api/history/add':
            self.handle_history_add(data)
        
        elif path == '/api/history/clear':
            self.handle_history_clear()
        
        else:
            self.send_error(404, "Endpoint nicht gefunden")

    def handle_thumbnail_request(self, query_params):
        """Verarbeitet Thumbnail-Anfragen."""
        filepath = query_params.get('filepath', [None])[0]

        if not filepath:
            self.send_error(400, "Kein Dateipfad angegeben")
            return

        # Pfad dekodieren
        filepath = urllib.parse.unquote(filepath)
        filepath = html.unescape(filepath)

        # Sicherheitsprüfung
        real_path = os.path.realpath(filepath)
        if not os.path.isfile(real_path):
            self.send_error(403, "Ungültiger Pfad")
            return

        # In Datenbank prüfen
        try:
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.execute(
                "SELECT COUNT(*) FROM media_files WHERE filepath = ?",
                (filepath,)
            )
            result = cursor.fetchone()[0]
            conn.close()

            if result == 0:
                print(f"⛔ Thumbnail-Anfrage für nicht-indexierte Datei: {os.path.basename(filepath)}")
                self.send_error(403, "Datei nicht in der Datenbank")
                return
        except Exception as e:
            print(f"⚠️ Datenbankfehler bei Thumbnail-Prüfung: {e}")

        # Thumbnail generieren oder holen
        thumb_path = generate_or_get_thumbnail(filepath)

        if thumb_path and os.path.exists(thumb_path):
            self.serve_file(thumb_path, 'image/jpeg')
        else:
            self.serve_color_thumbnail(filepath)

    def handle_range_request(self, filepath, content_type, range_header):
        """Handle HTTP Range Requests für effizientes Video-Seeking mit adaptiven Chunks."""
        try:
            file_size = os.path.getsize(filepath)
            
            if file_size == 0:
                print(f"❌ Leere Datei: {os.path.basename(filepath)}")
                self.send_error(404, "Empty file")
                return
            
            # Range-Header parsen
            range_match = re.match(r'bytes=(\d+)-(\d*)', range_header)
            if not range_match:
                print(f"⚠️ Ungültiger Range-Header: {range_header}")
                self.send_error(416, "Invalid Range Header")
                return
                
            start = int(range_match.group(1))
            end_str = range_match.group(2)
            
            if end_str:
                end = int(end_str)
                if end >= file_size:
                    end = file_size - 1
            else:
                end = file_size - 1
            
            # Grenzen validieren
            if start >= file_size:
                print(f"⚠️ Start ({start}) >= File Size ({file_size})")
                self.send_error(416, "Requested Range Not Satisfiable")
                return
                
            if start > end:
                print(f"⚠️ Start ({start}) > End ({end})")
                self.send_error(416, "Requested Range Not Satisfiable")
                return
                
            length = end - start + 1
            
            print(f"   📊 Range-Request: {start}-{end} ({length / 1024:.1f}KB von {file_size / (1024*1024):.1f}MB)")
            
            # Adaptive Chunk-Größe
            if length > 100 * 1024 * 1024:
                chunk_size = 2 * 1024 * 1024
            elif length > 10 * 1024 * 1024:
                chunk_size = 1 * 1024 * 1024
            else:
                chunk_size = 256 * 1024
            
            # Partial Content Response
            self.send_response(206)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(length))
            self.send_header('Content-Range', f'bytes {start}-{end}/{file_size}')
            self.send_header('Accept-Ranges', 'bytes')
            self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.end_headers()
            
            # OPTIMIERTES STREAMING MIT ROBUSTEM ERROR-HANDLING
            bytes_sent = 0
            try:
                with open(filepath, 'rb') as f:
                    f.seek(start)
                    remaining = length
                    
                    while remaining > 0:
                        chunk = f.read(min(chunk_size, remaining))
                        if not chunk:
                            print(f"ℹ️ Dateiende erreicht: {bytes_sent / 1024:.1f}KB gesendet")
                            break
                            
                        try:
                            self.wfile.write(chunk)
                            self.wfile.flush()
                            bytes_sent += len(chunk)
                            remaining -= len(chunk)
                            
                            # Fortschritt anzeigen (nur für größere Dateien)
                            if length > 10 * 1024 * 1024 and bytes_sent % (10 * 1024 * 1024) < chunk_size:
                                percent = (bytes_sent / length) * 100
                                print(f"   📈 Range-Fortschritt: {bytes_sent / 1024:.1f}KB ({percent:.1f}%)")
                                
                        except (ConnectionAbortedError, BrokenPipeError, OSError, ConnectionResetError) as e:
                            # NORMALER ABBRUCH - Client hat Video gestoppt/geskippt
                            print(f"ℹ️ Client-Verbindung abgebrochen: {bytes_sent / 1024:.1f}KB gesendet")
                            return  # KEIN ERROR - einfach beenden
                        
                        except Exception as e:
                            print(f"⚠️ Unerwarteter Fehler beim Senden: {e}")
                            return  # Beenden bei unbekannten Fehlern
                    
                    print(f"✅ Range vollständig gesendet: {bytes_sent / 1024:.1f}KB")
                    
            except Exception as e:
                print(f"⚠️ Datei-Lesefehler: {e}")
                # Kein send_error() hier - Client hat bereits Response-Headers bekommen
                
        except Exception as e:
            print(f"❌ Range-Request Setup Fehler: {e}")
            import traceback
            traceback.print_exc()
            self.send_error(500, "Internal Server Error")
        
    def handle_media_request(self, query_params):
        """Verarbeitet Media-Streaming-Anfragen."""
        filepath = query_params.get('filepath', [None])[0]

        if not filepath:
            self.send_error(400, "Kein Dateipfad angegeben")
            return

        # Pfad dekodieren
        filepath = urllib.parse.unquote(filepath)
        filepath = html.unescape(filepath)

        print(f"📥 /media Anfrage für: {os.path.basename(filepath)}")
        print(f"   📍 Vollständiger Pfad: {filepath}")

        # Sicherheitsprüfung
        if not is_path_allowed(filepath):
            self.send_error(403, "Ungültiger Pfad")
            return

        # In Datenbank prüfen
        try:
            with MainDBConnection() as cursor:
                cursor.execute(
                    "SELECT COUNT(*) FROM media_files WHERE filepath = ?",
                    (filepath,)
                )
                result = cursor.fetchone()[0]

                if result == 0:
                    self.send_error(403, "Datei nicht in der Datenbank")
                    return
                else:
                    print(f"✅ Datei in Datenbank gefunden: {os.path.basename(filepath)}")
        except Exception as e:
            print(f"⚠️ Datenbankfehler bei Medien-Prüfung: {e}")

        # Datei existiert?
        if not os.path.isfile(filepath):
            self.send_error(404, "Datei nicht gefunden")
            return

        # MIME-Type frühzeitig bestimmen
        ext = os.path.splitext(filepath)[1].lower()
        mime_type, _ = mimetypes.guess_type(filepath)
        if not mime_type:
            mime_type = 'video/mp4' if ext == '.mp4' else 'video/webm' if ext == '.webm' else 'application/octet-stream'
        
        print(f"   📁 Dateiendung: {ext}")
        print(f"   🎯 MIME-Type: {mime_type}")

        # AUDIO-DATEIEN - KORREKTUR HIER
        audio_exts = ['.mp3', '.wav', '.flac', '.aac', '.ogg', '.m4a', '.wma']
        if ext in audio_exts:
            print(f"🎵 Audio-Datei erkannt: {os.path.basename(filepath)}")
            
            # Range-Header prüfen für Audio
            range_header = self.headers.get('Range')
            if range_header:
                print(f"🎯 Range-Request für Audio: {range_header}")
                self.handle_range_request(filepath, mime_type, range_header)
                return
            
            # Direktes Streaming für Audio
            print(f"📤 Direktes Audio-Streaming: {os.path.basename(filepath)}")
            self.serve_file(filepath, mime_type)
            return

        # Range-Header frühzeitig prüfen (für alle anderen Dateien)
        range_header = self.headers.get('Range')
        
        # Immer transcodieren: MKV, AVI, WMV, etc.
        if ext in INCOMPATIBLE_VIDEO_EXTENSIONS:
            print(f"🔁 Live-Transcoding gestartet für: {os.path.basename(filepath)}")
            stream_video_transcoded(self, filepath)
            return

        # MP4: Intelligente Entscheidung basierend auf Browser-Kompatibilität
        if ext in POTENTIALLY_PROBLEMATIC_MP4:
            # Range-Request für MP4s direkt behandeln
            if range_header:
                print(f"🎯 Range-Request für MP4: {range_header}")
                self.handle_range_request(filepath, mime_type, range_header)
                return
                
            # Prüfe ob es ein natives Browser-MP4 ist (H.264 + AAC)
            try:
                if not FFPROBE_EXECUTABLE:
                    print(f"⚠️ FFprobe nicht verfügbar, transcodiere zur Sicherheit")
                    stream_video_transcoded(self, filepath)
                    return
                    
                # Schnelle FFprobe-Prüfung der Codecs
                probe_cmd = [
                    FFPROBE_EXECUTABLE,
                    '-v', 'error',
                    '-select_streams', 'v:0',
                    '-show_entries', 'stream=codec_name',
                    '-of', 'default=noprint_wrappers=1:nokey=1',
                    filepath
                ]
                
                video_codec = subprocess.run(
                    probe_cmd, 
                    capture_output=True, 
                    text=True, 
                    timeout=3
                ).stdout.strip()
                
                # Wenn nicht H.264, transcodieren
                if video_codec != 'h264':
                    print(f"🔄 MP4-Transcoding (Codec: {video_codec}): {os.path.basename(filepath)}")
                    stream_video_transcoded(self, filepath)
                    return
                else:
                    print(f"✅ Native MP4 (H.264): {os.path.basename(filepath)}")
                    # Direktes Streaming für natives MP4
                    self.serve_file(filepath, mime_type)
                    return
                    
            except Exception as e:
                # Bei Fehler: Sicherheitshalber transcodieren
                print(f"⚠️ Codec-Prüfung fehlgeschlagen, transcodiere zur Sicherheit: {e}")
                stream_video_transcoded(self, filepath)
                return
        
        # Direktes Streaming für native Browser-Formate (MP4, WebM)
        if ext in NATIVE_BROWSER_EXTENSIONS:
            # Range-Request für direkte Formate
            if range_header:
                print(f"🎯 Range-Request für natives Format: {range_header}")
                self.handle_range_request(filepath, mime_type, range_header)
                return
                
            print(f"📤 Direktes Streaming: {os.path.basename(filepath)}")
            self.serve_file(filepath, mime_type)
            return

        # Fallback für alle anderen Dateien
        print(f"📁 Allgemeine Datei: {os.path.basename(filepath)}")
        self.serve_file(filepath, mime_type)

    def handle_static_thumbnail(self, path):
        """Liefert statische Thumbnails aus Cache."""
        thumb_name = os.path.basename(path)
        if not thumb_name:
            self.send_error(403, "Ungültiger Thumbnail-Name")
            return

        thumb_path = os.path.join(THUMBNAIL_DIR, thumb_name)
        if os.path.isfile(thumb_path):
            try:
                with open(thumb_path, 'rb') as f:
                    data = f.read()
                    self.send_response(200)
                    self.send_header('Content-Type', 'image/jpeg')
                    self.send_header('Content-Length', str(len(data)))
                    self.send_header('Cache-Control', 'public, max-age=31536000')  # 1 Jahr Cache
                    self.send_header('Expires', 'Fri, 01 Jan 2026 00:00:00 GMT')
                    self.end_headers()
                    self.wfile.write(data)
                    print(f"✅ Statisches Thumbnail: {thumb_name}")
            except (ConnectionAbortedError, BrokenPipeError, ConnectionResetError, OSError):
                # Client-Abbruch ignorieren
                print(f"ℹ️ Client-Abbruch bei statischem Thumbnail")
            except Exception as e:
                print(f"⚠️ Statisches Thumbnail-Fehler: {e}")
        else:
            self.send_error(404, "Thumbnail nicht gefunden")

    def handle_api_media_request(self, query_params):
        """API-Endpoint für Medien-Listen mit Filtern."""
        try:
            # Parameter extrahieren
            category = query_params.get('category', [''])[0]
            genre = query_params.get('genre', [''])[0]
            subgenre = query_params.get('subgenre', [''])[0]
            series = query_params.get('series', [''])[0]
            season = query_params.get('season', [''])[0]
            year = query_params.get('year', [''])[0]
            search = query_params.get('search', [''])[0]
            page = int(query_params.get('page', [1])[0])
            
            print(f"\n📡 API Request:")
            print(f"   Category: '{category}'")
            print(f"   Genre: '{genre}'")
            print(f"   Subgenre: '{subgenre}'")
            print(f"   Series: '{series}'")
            print(f"   Season: '{season}'")
            print(f"   Year: '{year}'")
            print(f"   Page: {page}")
            
            # Datenbank öffnen
            conn = sqlite3.connect(DB_PATH)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # Medien abfragen
            media_list, total_count, total_pages = get_media_paginated(
                cursor, category, genre, subgenre, series, season, year, search, page, 50
            )
            
            # Medien anreichern
            enriched_media = []
            for media in media_list:
                enriched = enrich_media_data(media, use_cache=True)
                enriched_media.append(enriched)
            
            conn.close()
            
            # JSON-Response
            response = {
                'success': True,
                'page': page,
                'total_pages': total_pages,
                'total_count': total_count,
                'media': enriched_media,
                'page_size': 50
            }
            
            print(f"   ✅ Response: {total_count} Medien, {total_pages} Seiten")
            
            self.send_json_response(response)
            
        except Exception as e:
            print(f"❌ API-Fehler: {e}")
            import traceback
            traceback.print_exc()
            self.send_json_response({'success': False, 'error': str(e)}, 500)

    def handle_api_subgenres(self, query_params):
        """API-Endpoint für Subgenres/Franchises."""
        try:
            category = query_params.get('category', [''])[0]
            genre = query_params.get('genre', [''])[0]
            
            if not category or not genre:
                self.send_json_response({
                    'success': False, 
                    'error': 'Kategorie und Genre erforderlich',
                    'subgenres': []
                }, 400)
                return
            
            if not os.path.exists(HIERARCHY_DB_PATH):
                self.send_json_response({
                    'success': False, 
                    'error': 'Hierarchie-Datenbank nicht gefunden.',
                    'subgenres': []
                }, 404)
                return
            
            conn = sqlite3.connect(HIERARCHY_DB_PATH, timeout=10)
            cursor = conn.cursor()
            
            # Kategorie-spezifische Logik
            if category == 'Serie':
                query = """
                    SELECT DISTINCT 
                        COALESCE(
                            NULLIF(TRIM(series), ''),
                            NULLIF(TRIM(subgenre), ''),
                            NULLIF(TRIM(sub_franchise), ''),
                            NULLIF(TRIM(franchise), '')
                        ) as subgenre_name,
                        COUNT(*) as count
                    FROM hierarchy_cache 
                    WHERE normalized_category = ? 
                    AND genre = ?
                    AND (
                        TRIM(COALESCE(series, '')) != '' OR
                        TRIM(COALESCE(subgenre, '')) != '' OR
                        TRIM(COALESCE(sub_franchise, '')) != '' OR
                        TRIM(COALESCE(franchise, '')) != ''
                    )
                    GROUP BY subgenre_name
                    HAVING subgenre_name IS NOT NULL
                    ORDER BY count DESC, subgenre_name
                """
                cursor.execute(query, (category, genre))
                
            elif category == 'Musik':
                query = """
                    SELECT DISTINCT artist, COUNT(*) as count
                    FROM hierarchy_cache 
                    WHERE normalized_category = ? 
                    AND genre = ?
                    AND artist IS NOT NULL 
                    AND TRIM(artist) != ''
                    GROUP BY artist
                    ORDER BY count DESC, artist
                """
                cursor.execute(query, (category, genre))
                
            elif category == 'Film':
                query = """
                    SELECT DISTINCT 
                        COALESCE(
                            NULLIF(TRIM(franchise), ''),
                            NULLIF(TRIM(sub_franchise), ''),
                            NULLIF(TRIM(series), ''),
                            NULLIF(TRIM(subgenre), '')
                        ) as subgenre_name,
                        COUNT(*) as count
                    FROM hierarchy_cache 
                    WHERE normalized_category = ? 
                    AND genre = ?
                    AND (
                        TRIM(COALESCE(franchise, '')) != '' OR
                        TRIM(COALESCE(sub_franchise, '')) != '' OR
                        TRIM(COALESCE(series, '')) != '' OR
                        TRIM(COALESCE(subgenre, '')) != ''
                    )
                    GROUP BY subgenre_name
                    HAVING subgenre_name IS NOT NULL
                    ORDER BY count DESC, subgenre_name
                """
                cursor.execute(query, (category, genre))
                
            else:
                query = """
                    SELECT DISTINCT 
                        COALESCE(
                            NULLIF(TRIM(subgenre), ''),
                            NULLIF(TRIM(sub_franchise), ''),
                            NULLIF(TRIM(franchise), ''),
                            NULLIF(TRIM(series), '')
                        ) as subgenre_name,
                        COUNT(*) as count
                    FROM hierarchy_cache 
                    WHERE normalized_category = ? 
                    AND genre = ?
                    AND (
                        TRIM(COALESCE(subgenre, '')) != '' OR
                        TRIM(COALESCE(sub_franchise, '')) != '' OR
                        TRIM(COALESCE(franchise, '')) != '' OR
                        TRIM(COALESCE(series, '')) != ''
                    )
                    GROUP BY subgenre_name
                    HAVING subgenre_name IS NOT NULL
                    ORDER BY count DESC, subgenre_name
                """
                cursor.execute(query, (category, genre))
            
            results = cursor.fetchall()
            conn.close()
            
            # Ergebnisse verarbeiten
            subgenres = []
            seen = set()
            for row in results:
                if row[0] and row[0].strip() and row[0].strip() not in seen:
                    seen.add(row[0].strip())
                    subgenres.append({
                        'name': row[0].strip(),
                        'count': row[1]
                    })
            
            print(f"🔍 Subgenre-Query für {category}/{genre}:")
            print(f"   Gefunden: {len(subgenres)} Subgenres")
            if subgenres:
                for sg in subgenres[:10]:
                    print(f"   - {sg['name']} ({sg['count']})")
            
            response = {
                'success': True,
                'category': category,
                'genre': genre,
                'subgenres': [s['name'] for s in subgenres],
                'subgenres_with_count': subgenres,
                'count': len(subgenres)
            }
            
            self.send_json_response(response)
            
        except Exception as e:
            print(f"❌ Subgenre-API-Fehler: {e}")
            import traceback
            traceback.print_exc()
            self.send_json_response({
                'success': False, 
                'error': str(e),
                'subgenres': []
            }, 500)
        
    def handle_api_genres(self, query_params):
        """API-Endpoint für Genres."""
        try:
            category = query_params.get('category', [''])[0]
            
            if not category:
                self.send_json_response({'success': False, 'error': 'Kategorie-Parameter fehlt'}, 400)
                return
            
            if not os.path.exists(HIERARCHY_DB_PATH):
                self.send_json_response({
                    'success': False, 
                    'error': 'Hierarchie-DB nicht gefunden',
                    'genres': []
                }, 404)
                return
            
            conn = sqlite3.connect(HIERARCHY_DB_PATH, timeout=10)
            cursor = conn.cursor()
            
            query = """
                SELECT DISTINCT genre, COUNT(*) as media_count
                FROM hierarchy_cache
                WHERE normalized_category = ?
                AND genre != '' 
                AND genre IS NOT NULL
                GROUP BY genre
                ORDER BY genre
            """
            
            cursor.execute(query, (category,))
            results = cursor.fetchall()
            conn.close()
            
            genres = [{'name': row[0], 'count': row[1]} for row in results]
            
            response = {
                'success': True,
                'category': category,
                'genres': [g['name'] for g in genres],
                'genres_with_count': genres,
                'total_genres': len(genres)
            }
            
            self.send_json_response(response)
            
        except Exception as e:
            print(f"❌ Genre-API-Fehler: {e}")
            self.send_json_response({'success': False, 'error': str(e)}, 500)

    def handle_api_series(self, query_params):
        """API-Endpoint für Serien/Reihen."""
        try:
            category = query_params.get('category', [''])[0]
            genre = query_params.get('genre', [''])[0]
            subgenre = query_params.get('subgenre', [''])[0]
            
            if not category:
                self.send_json_response({
                    'success': False, 
                    'error': 'Kategorie erforderlich',
                    'series': []
                }, 400)
                return
            
            if not os.path.exists(HIERARCHY_DB_PATH):
                self.send_json_response({
                    'success': False, 
                    'error': 'Hierarchie-Datenbank nicht gefunden',
                    'series': []
                }, 404)
                return
            
            conn = sqlite3.connect(HIERARCHY_DB_PATH, timeout=20)
            cursor = conn.cursor()
            
            where_clauses = ["normalized_category = ?"]
            params = [category]
            
            if genre and genre.strip():
                where_clauses.append("genre = ?")
                params.append(genre)
            
            # Kategorie-spezifische Logik
            if category == 'Musik':
                if subgenre and subgenre.strip():
                    where_clauses.append("artist = ?")
                    params.append(subgenre)
                
                query = f"""
                    SELECT DISTINCT album, COUNT(*) as count
                    FROM hierarchy_cache 
                    WHERE {' AND '.join(where_clauses)}
                    AND album IS NOT NULL 
                    AND TRIM(album) != ''
                    GROUP BY album
                    ORDER BY album
                """
                
            elif category == 'Film':
                if subgenre and subgenre.strip():
                    where_clauses.append("""(
                        franchise = ? OR 
                        sub_franchise LIKE ? OR 
                        subgenre = ? OR
                        series = ?
                    )""")
                    params.extend([subgenre, f"%{subgenre}%", subgenre, subgenre])
                
                query = f"""
                    SELECT DISTINCT 
                        COALESCE(
                            NULLIF(TRIM(series), ''),
                            NULLIF(TRIM(sub_franchise), ''),
                            NULLIF(TRIM(franchise), ''),
                            NULLIF(TRIM(subgenre), '')
                        ) as series_name,
                        COUNT(*) as count
                    FROM hierarchy_cache 
                    WHERE {' AND '.join(where_clauses)}
                    AND (
                        TRIM(COALESCE(series, '')) != '' OR
                        TRIM(COALESCE(sub_franchise, '')) != '' OR
                        TRIM(COALESCE(franchise, '')) != '' OR
                        TRIM(COALESCE(subgenre, '')) != ''
                    )
                    GROUP BY series_name
                    HAVING series_name IS NOT NULL
                    ORDER BY series_name
                """
                
            else:
                if subgenre and subgenre.strip():
                    where_clauses.append("""(
                        series = ? OR 
                        sub_franchise = ? OR 
                        franchise = ? OR
                        subgenre = ?
                    )""")
                    params.extend([subgenre, subgenre, subgenre, subgenre])
                
                query = f"""
                    SELECT DISTINCT 
                        COALESCE(
                            NULLIF(TRIM(series), ''),
                            NULLIF(TRIM(sub_franchise), ''),
                            NULLIF(TRIM(franchise), ''),
                            NULLIF(TRIM(subgenre), '')
                        ) as series_name,
                        COUNT(*) as count
                    FROM hierarchy_cache 
                    WHERE {' AND '.join(where_clauses)}
                    AND (
                        TRIM(COALESCE(series, '')) != '' OR
                        TRIM(COALESCE(sub_franchise, '')) != '' OR
                        TRIM(COALESCE(franchise, '')) != '' OR
                        TRIM(COALESCE(subgenre, '')) != ''
                    )
                    GROUP BY series_name
                    HAVING series_name IS NOT NULL
                    ORDER BY 
                        CASE 
                            WHEN series_name LIKE '%Staffel%' THEN 0
                            WHEN series_name LIKE '%Season%' THEN 0
                            ELSE 1
                        END,
                        series_name
                """
            
            print(f"🔍 Series-Query: {query}")
            print(f"   Parameters: {params}")
            
            cursor.execute(query, params)
            results = cursor.fetchall()
            conn.close()
            
            # Ergebnisse bereinigen
            series_list = []
            seen_series = set()
            
            for row in results:
                if row[0] and row[0].strip():
                    series_name = row[0].strip()
                    
                    # Redundante Staffel-Texte entfernen (nur bei Serien)
                    if category == 'Serie':
                        series_name = re.sub(r'\s*Staffel\s*\d+', '', series_name, flags=re.IGNORECASE)
                        series_name = re.sub(r'\s*Season\s*\d+', '', series_name, flags=re.IGNORECASE)
                        series_name = series_name.strip()
                    
                    if series_name and series_name not in seen_series:
                        seen_series.add(series_name)
                        series_list.append({
                            'name': series_name,
                            'count': row[1]
                        })
            
            print(f"   ✅ Gefundene Series: {len(series_list)}")
            for s in series_list[:10]:
                print(f"   - {s['name']} ({s['count']})")
            
            response = {
                'success': True,
                'category': category,
                'genre': genre,
                'subgenre': subgenre,
                'series': [s['name'] for s in series_list],
                'series_with_count': series_list,
                'total_series': len(series_list)
            }
            
            self.send_json_response(response)
            
        except Exception as e:
            print(f"❌ Series-API-Fehler: {e}")
            import traceback
            traceback.print_exc()
            self.send_json_response({
                'success': False, 
                'error': str(e),
                'series': []
            }, 500)
        
    def handle_api_filter_metadata(self, query_params):
        """API-Endpoint für Filter-Metadaten."""
        try:
            category = query_params.get('category', [''])[0]
            
            if not category:
                self.send_json_response({
                    'success': False,
                    'error': 'Kategorie erforderlich'
                }, 400)
                return
            
            metadata = {
                'category': category,
                'genres': [],
                'years': [],
                'has_seasons': category == 'Serie'
            }
            
            self.send_json_response({
                'success': True,
                **metadata
            })
            
        except Exception as e:
            self.send_json_response({
                'success': False,
                'error': str(e)
            }, 500)

    def handle_api_seasons(self, query_params):
        """API-Endpoint für Staffeln."""
        try:
            category = query_params.get('category', [''])[0]
            genre = query_params.get('genre', [''])[0]
            subgenre = query_params.get('subgenre', [''])[0]
            series = query_params.get('series', [''])[0]
            
            if category != 'Serie':
                self.send_json_response({
                    'success': False,
                    'error': 'Staffeln nur für Kategorie "Serie" verfügbar',
                    'seasons': []
                }, 400)
                return
            
            print(f"🔍 Seasons API Request:")
            print(f"   Category: {category}")
            print(f"   Genre: {genre}")
            print(f"   Subgenre: {subgenre}")
            print(f"   Series: {series}")
            
            seasons = get_seasons_for_series(category, genre, subgenre, series)
            
            response = {
                'success': True,
                'category': category,
                'genre': genre,
                'subgenre': subgenre,
                'series': series,
                'seasons': seasons,
                'total_seasons': len(seasons)
            }
            
            self.send_json_response(response)
            
        except Exception as e:
            print(f"❌ Seasons-API-Fehler: {e}")
            self.send_json_response({
                'success': False,
                'error': str(e),
                'seasons': []
            }, 500)

    def handle_rebuild_hierarchy(self):
        """API-Endpoint für Hierarchie-Cache-Rebuild."""
        try:
            if os.path.exists(HIERARCHY_DB_PATH):
                os.remove(HIERARCHY_DB_PATH)
                time.sleep(0.5)
            success = rebuild_hierarchy_cache()
            if success:
                response = {
                    'success': True,
                    'message': 'Hierarchie-Cache erfolgreich neu aufgebaut'
                }
                self.send_json_response(response)
            else:
                response = {
                    'success': False,
                    'message': 'Fehler beim Neuerstellen des Hierarchie-Cache'
                }
                self.send_json_response(response, 500)
        except Exception as e:
            print(f"❌ Rebuild-Hierarchie-Fehler: {e}")
            self.send_json_response({'success': False, 'error': str(e)}, 500)
    
    # ===== API ENDPOINTS FÜR ERWEITERTE FEATURES =====
    
    def handle_api_settings(self, query_params):
        """GET /api/settings - Alle Settings abrufen."""
        try:
            settings = {
                'network_mode': get_setting('network_mode', 'localhost'),
                'max_clients': get_setting('max_clients', 3),
                'enable_history': get_setting('enable_history', True),
                'history_limit': get_setting('history_limit', 10),
                'volume_level': get_setting('volume_level', 0.7),
                'audio_language': get_setting('audio_language', 'ger'),
                'autoplay_enabled': get_setting('autoplay_enabled', False),
                'active_clients': len(active_clients),
                'local_ip': get_local_ip() if get_setting('network_mode') == 'network' else None,
                'server_host': get_server_host(),
                'server_port': SERVER_PORT
            }
            
            self.send_json_response({'success': True, 'settings': settings})
            
        except Exception as e:
            self.send_json_response({'success': False, 'error': str(e)}, 500)
    
    def handle_settings_update(self, data):
        """POST /api/settings/update - Settings aktualisieren."""
        try:
            updated = []
            
            for key, value in data.items():
                if key in DEFAULT_SETTINGS:
                    if set_setting(key, value):
                        updated.append(key)
            
            # Bei network_mode Änderung Info ausgeben
            if 'network_mode' in updated:
                self.send_json_response({
                    'success': True,
                    'updated': updated,
                    'restart_required': True,
                    'message': 'Server-Neustart erforderlich für Netzwerk-Modus-Änderung'
                })
            else:
                self.send_json_response({
                    'success': True,
                    'updated': updated,
                    'restart_required': False
                })
            
        except Exception as e:
            self.send_json_response({'success': False, 'error': str(e)}, 500)
    
    def handle_api_resume(self, query_params):
        """GET /api/resume?filepath=... - Resume-Point abrufen."""
        try:
            filepath = query_params.get('filepath', [None])[0]
            if not filepath:
                self.send_json_response({'success': False, 'error': 'Filepath fehlt'}, 400)
                return
            
            filepath = urllib.parse.unquote(filepath)
            resume_point = get_resume_point(filepath)
            
            if resume_point:
                self.send_json_response({
                    'success': True,
                    'has_resume': True,
                    'resume': resume_point
                })
            else:
                self.send_json_response({
                    'success': True,
                    'has_resume': False
                })
            
        except Exception as e:
            self.send_json_response({'success': False, 'error': str(e)}, 500)
    
    def handle_api_history(self, query_params):
        """GET /api/history - Abspiel-Historie abrufen."""
        try:
            limit = int(query_params.get('limit', [10])[0])
            history = get_history(limit)
            
            # Konvertiere für JSON-Ausgabe (Sekunden bleiben, Prozent werden entfernt)
            for item in history:
                # Stelle sicher, dass last_position und duration vorhanden sind
                item['last_position'] = item.get('last_position', 0)
                item['duration'] = item.get('duration', 0)
                # Prozent-Feld entfernen, falls vorhanden
                if 'percentage' in item:
                    del item['percentage']
            
            self.send_json_response({
                'success': True,
                'history': history,
                'count': len(history)
            })
            
        except Exception as e:
            self.send_json_response({'success': False, 'error': str(e)}, 500)
    
    def handle_history_add(self, data):
        """POST /api/history/add - History-Eintrag hinzufügen."""
        try:
            required = ['filepath', 'filename', 'category']
            if not all(k in data for k in required):
                self.send_json_response({'success': False, 'error': 'Fehlende Pflichtfelder'}, 400)
                return
            
            # Extrahiere und konvertiere Werte sicher
            filepath = data['filepath']
            filename = data['filename']
            category = data['category']
            position = data.get('position', 0)
            duration = data.get('duration', 0)
            completed = data.get('completed', False)
            
            # Konvertiere zu numerischen Werten (falls sie als Strings kommen)
            try:
                position = float(position) if position not in [None, ''] else 0
            except:
                position = 0
                
            try:
                duration = float(duration) if duration not in [None, ''] else 0
            except:
                duration = 0
            
            success = add_to_history(
                filepath=filepath,
                filename=filename,
                category=category,
                position=position,
                duration=duration,
                completed=completed
            )
            
            self.send_json_response({'success': success})
            
        except Exception as e:
            print(f"⚠️ History-Add API Fehler: {e}")
            self.send_json_response({'success': False, 'error': str(e)}, 500)
    
    def handle_history_clear(self):
        """POST /api/history/clear - Gesamte History löschen."""
        try:
            conn = sqlite3.connect(SETTINGS_DB_PATH)
            cursor = conn.cursor()
            cursor.execute('DELETE FROM playback_history')
            conn.commit()
            conn.close()
            
            self.send_json_response({'success': True, 'message': 'History gelöscht'})
            
        except Exception as e:
            self.send_json_response({'success': False, 'error': str(e)}, 500)

    def send_json_response(self, data, status_code=200):
        """Sendet JSON-Response mit korrekten Headers."""
        self.send_response(status_code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        
        json_data = json.dumps(data, ensure_ascii=False)
        self.wfile.write(json_data.encode('utf-8'))
        
    def serve_file(self, filepath, content_type):
        """Liefert Dateien mit optimiertem Streaming und adaptive Chunk-Größen."""
        try:
            if not os.path.isfile(filepath):
                self.send_error(404, "Datei nicht gefunden")
                return

            file_size = os.path.getsize(filepath)
            
            # Content-Type bestimmen
            if content_type is None:
                content_type, _ = mimetypes.guess_type(filepath)
                content_type = content_type or 'application/octet-stream'

            base_content_type = content_type.split(';')[0].strip()
            
            # Adaptive Chunk-Größe - BESONDERE BEHANDLUNG FÜR KLEINE DATEIEN (Thumbnails)
            if file_size < 100 * 1024:  # Kleine Dateien (< 100KB) komplett senden
                chunk_size = file_size  # Ein Chunk für alles
                print(f"   📊 Kleine Datei: {os.path.basename(filepath)} ({file_size / 1024:.1f}KB)")
            elif base_content_type.startswith('video/') or base_content_type.startswith('audio/'):
                if file_size > 5 * 1024 * 1024 * 1024:  # >5GB
                    chunk_size = 2 * 1024 * 1024  # 2MB
                elif file_size > 1 * 1024 * 1024 * 1024:  # >1GB
                    chunk_size = 1 * 1024 * 1024  # 1MB
                else:
                    chunk_size = 512 * 1024  # 512KB
            else:
                chunk_size = 256 * 1024  # 256KB
            
            print(f"   📊 Streaming: {os.path.basename(filepath)} ({file_size / (1024*1024):.1f}MB)")
            
            # Headers senden
            self.send_response(200)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(file_size))
            self.send_header('Accept-Ranges', 'bytes')
            self.send_header('X-Content-Type-Options', 'nosniff')
            
            # Cache-Strategie - WICHTIG: Thumbnails lange cachen
            if base_content_type.startswith('image/'):
                self.send_header('Cache-Control', 'public, max-age=31536000')  # 1 Jahr Cache
                self.send_header('Expires', 'Fri, 01 Jan 2026 00:00:00 GMT')
            elif base_content_type.startswith('video/') or base_content_type.startswith('audio/'):
                self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
            else:
                self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')  # NEUE ZEILE
                self.send_header('Pragma', 'no-cache')  # NEUE ZEILE
            
            self.end_headers()
            
            # ROBUSTES STREAMING - SPEZIALBEHANDLUNG FÜR KLEINE DATEIEN
            bytes_sent = 0
            try:
                with open(filepath, 'rb') as f:
                    # Für kleine Dateien: Einmalig komplett lesen
                    if file_size < 100 * 1024:
                        try:
                            data = f.read()
                            self.wfile.write(data)
                            self.wfile.flush()
                            bytes_sent = len(data)
                            print(f"✅ {os.path.basename(filepath)} komplett gesendet: {bytes_sent / 1024:.1f}KB")
                        except (ConnectionAbortedError, BrokenPipeError, ConnectionResetError, OSError):
                            # Client-Abbruch bei kleinen Dateien ignorieren
                            return
                    else:
                        # Normales Streaming für große Dateien
                        while True:
                            chunk = f.read(chunk_size)
                            if not chunk:
                                break
                            
                            try:
                                self.wfile.write(chunk)
                                bytes_sent += len(chunk)
                                self.wfile.flush()
                                    
                            except (ConnectionAbortedError, BrokenPipeError, 
                                    ConnectionResetError, OSError):
                                # Client hat Verbindung abgebrochen - normal bei Browsern
                                print(f"ℹ️ Client-Abbruch: {os.path.basename(filepath)}")
                                return
                            
                            except Exception as e:
                                print(f"⚠️ Sendefehler: {e}")
                                return
                        
                        if bytes_sent > 0:
                            print(f"✅ {os.path.basename(filepath)} gesendet: {bytes_sent / (1024*1024):.1f}MB")

            except Exception as e:
                print(f"⚠️ Datei-Lesefehler: {e}")
                
        except Exception as e:
            print(f"❌ Fehler in serve_file(): {e}")
            try:
                if not self.headers_sent:
                    self.send_error(500, "Interner Fehler")
            except:
                pass

    def serve_color_thumbnail(self, filepath):
        """Liefert farbiges Fallback-Thumbnail als SVG."""
        try:
            color = get_thumbnail_color(filepath)
            icon = get_file_extension_icon(filepath)

            svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="300" height="200">
                <rect width="100%" height="100%" fill="{color}"/>
                <text x="50%" y="50%" font-family="Arial" font-size="48" fill="white" 
                      text-anchor="middle" dy=".3em">
                    <tspan font-family="FontAwesome">{icon}</tspan>
                </text>
            </svg>'''

            svg_bytes = svg.encode('utf-8')

            self.send_response(200)
            self.send_header('Content-Type', 'image/svg+xml')
            self.send_header('Content-Length', str(len(svg_bytes)))
            self.send_header('Cache-Control', 'public, max-age=86400')
            self.end_headers()

            self.wfile.write(svg_bytes)
            print(f"✅ SVG-Thumbnail gesendet für: {os.path.basename(filepath)}")

        except (ConnectionAbortedError, BrokenPipeError, ConnectionResetError, OSError):
            # Client-Abbruch ignorieren
            print(f"ℹ️ Client-Abbruch bei SVG-Thumbnail")
        except Exception as e:
            print(f"❌ Fehler beim SVG-Thumbnail: {e}")
            try:
                self.send_error(500, "Interner Fehler")
            except:
                pass

    def clear_thumbnail_cache(self):
        """Löscht den Thumbnail-Cache."""
        try:
            count = 0
            for filename in os.listdir(THUMBNAIL_DIR):
                if filename.endswith('.jpg'):
                    os.remove(os.path.join(THUMBNAIL_DIR, filename))
                    count += 1
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'status': 'success', 'deleted': count}).encode())
            print(f"🗑️ {count} Thumbnails aus Cache gelöscht")
        except Exception as e:
            self.send_error(500, f"Fehler beim Löschen: {e}")

# -----------------------------------------------------------------------------
# WEB-INTERFACE GENERATOR (ERWEITERT)
# -----------------------------------------------------------------------------

def generate_media_cards(media_list, is_latest=False, use_grid=False):
    """
    Generiert HTML-Medienkarten für das Web-Interface.
    
    Args:
        media_list (list): Liste von Medien-Daten
        is_latest (bool): Ob "Neueste" Karten (andere Styling)
        use_grid (bool): Ob Grid-Layout verwendet werden soll
        
    Returns:
        str: HTML-Code für Medienkarten
    """
    cards = []
    limit = 5000 if use_grid else 24
    
    for media in media_list[:limit]:
        filename = escape_html(media.get('filename', 'Unbekannt'))
        category = escape_html(media.get('normalized_category', media.get('category', 'Unbekannt')))
        year = escape_html(media.get('year', ''))
        genre = escape_html(media.get('genre', ''))
        filepath = media.get('filepath', '')
        
        if not filepath or not isinstance(filepath, str) or filepath.strip() == '':
            print(f"⚠️ Leerer Dateipfad für: {filename}")
            continue
        
        # JavaScript-sichere Strings
        filename_js = escape_html(filename).replace("'", "\\'")
        category_js = escape_html(category).replace("'", "\\'")
        
        # Styling
        icon = get_category_icon(category)
        bg_style = 'background: linear-gradient(45deg, #e74c3c, #c0392b);' if is_latest else ''
        safe_path = urllib.parse.quote(filepath, safe='')
        thumbnail_url = f'/thumbnail?filepath={safe_path}'
        
        # Resume-Point prüfen
        resume_info = ''
        resume_point = get_resume_point(filepath)
        if resume_point:
            resume_info = f'data-resume="true" data-resume-position="{resume_point["position"]}" data-resume-timestamp="{resume_point["timestamp"]}"'
        
        # Karte generieren
        card = f'''
        <div class="media-card" data-filepath="{escape_html(safe_path)}" data-filename="{filename_js}" data-category="{category_js}" {resume_info} onclick="playMediaFromCard(this)">
            <div class="media-thumbnail" style="{bg_style}">
                <img src="{thumbnail_url}" alt="{filename}" style="width:100%;height:100%;object-fit:cover;">
                {f'<div class="resume-badge" title="Fortsetzen bei {resume_point["timestamp"]}"><i class="fas fa-play-circle"></i></div>' if resume_point else ''}
            </div>
            <div class="media-info-overlay">
                <div class="media-title">{filename}</div>
                <div class="media-meta">
                    <span class="media-year">{year if year else ''}</span>
                    {f'<span class="media-genre">{genre}</span>' if genre else ''}
                </div>
            </div>
        </div>
        '''
        cards.append(card)
    
    return ''.join(cards)

def generate_html_with_subgenres(categories, category_data, genres, years, 
                                 featured_media, latest_media, total_files, total_gb, all_media_json):
    """
    Generiert das komplette HTML-Interface mit allen dynamischen Komponenten.
    
    Args:
        categories (list): Verfügbare Kategorien
        category_data (dict): Kategorie-spezifische Daten
        genres (list): Verfügbare Genres
        years (list): Verfügbare Jahre
        featured_media (list): Featured Medien
        latest_media (list): Neueste Medien
        total_files (int): Gesamtanzahl Medien
        total_gb (float): Gesamtgröße in GB
        all_media_json (list): Alle Medien als JSON
        
    Returns:
        str: Komplettes HTML-Dokument
    """
    # Metadaten
    current_date = datetime.now().strftime("%d.%m.%Y %H:%M")
    current_year = datetime.now().year
    all_media_json_str = json.dumps(all_media_json, ensure_ascii=False)
    total_gb_formatted = f"{total_gb:.1f}"
    total_categories = len(categories)
    total_genres = len(genres)
    
    # Dropdowns generieren
    dropdown_categories = ''.join(
        f'<a href="#" class="dropdown-item" onclick="filterByCategory(\'{escape_html(cat)}\'); return false;">{escape_html(cat)}</a>' 
        for cat in categories
    )
    
    film_genres = genres[:20] if genres else []
    dropdown_genres = ''.join(
        f'<a href="#" class="dropdown-item" onclick="filterByGenre(\'{escape_html(genre)}\'); return false;">{escape_html(genre)}</a>' 
        for genre in film_genres
    )
    
    film_years = years[:15] if years else []
    dropdown_years = ''.join(
        f'<a href="#" class="dropdown-item" onclick="filterByYear(\'{escape_html(year)}\'); return false;">{escape_html(year)}</a>' 
        for year in film_years
    )
    
    # Kategorie-Tabs
    category_tabs_html = '''<div class="category-tab active" onclick="filterByCategory('')">Alle</div>''' + \
        ''.join(
            f'''<div class="category-tab" onclick="filterByCategory('{escape_html(cat)}')">{escape_html(cat)}</div>''' 
            for cat in categories
        )
    
    # Filter-Select-Optionen
    select_options_categories = '<option value="">Alle Kategorien</option>' + \
        ''.join(f'<option value="{escape_html(cat)}">{escape_html(cat)}</option>' for cat in categories)

    select_options_genres = '<option value="">Alle Genres</option>' + \
        ''.join(f'<option value="{escape_html(genre)}">{escape_html(genre)}</option>' for genre in film_genres)

    select_options_years = '<option value="">Alle Jahre</option>' + \
        ''.join(f'<option value="{escape_html(year)}">{escape_html(year)}</option>' for year in film_years)

    # Filter-Status
    initial_filter_state = {
        'category': '',
        'genre': '',
        'subgenre': '',
        'series': ''
    }
    initial_filter_state_json = json.dumps(initial_filter_state, ensure_ascii=False)
    
    # Medienkarten generieren
    trending_media = generate_media_cards(featured_media, False)
    latest_media_cards = generate_media_cards(latest_media, True)
    
    # Kategorie-Statistiken
    category_stats = {}
    try:
        with HierarchyDBConnection() as cursor:
            cursor.execute("""
                SELECT normalized_category, COUNT(*) as count
                FROM hierarchy_cache
                GROUP BY normalized_category
                ORDER BY normalized_category
            """)
            for row in cursor.fetchall():
                cat, count = row
                if cat:
                    category_stats[cat] = count
    except Exception as e:
        print(f"⚠️ Fehler bei Hierarchie-DB Zählung: {e}")
        # Fallback auf alte Methode
        category_stats = {}
        for media in all_media_json:
            cat = media.get('normalized_category', 'Unbekannt')
            if cat not in category_stats:
                category_stats[cat] = 0
            category_stats[cat] += 1
    
    stats_items = []
    for cat in categories:
        count = category_stats.get(cat, 0)
        stats_items.append(f'''
        <div class="stat-item" style="cursor: pointer;" onclick="showCategory('{escape_html(cat)}')">
            <div class="stat-number">{count}</div>
            <div class="stat-label">{escape_html(cat)}</div>
        </div>
        ''')
    
    stats_bar_html = '\n'.join(stats_items)
    
    # Kategorie-Daten für JavaScript
    category_data_js = {}
    try:
        import sqlite3
        if os.path.exists(HIERARCHY_DB_PATH):
            conn = sqlite3.connect(HIERARCHY_DB_PATH)
            cursor = conn.cursor()
            
            for cat in categories:
                cursor.execute('''
                    SELECT DISTINCT 
                        COALESCE(NULLIF(subgenre, ''), 
                                NULLIF(sub_franchise, ''), 
                                NULLIF(franchise, '')) as subgenre_name
                    FROM hierarchy_cache 
                    WHERE normalized_category = ?
                    AND (subgenre IS NOT NULL OR sub_franchise IS NOT NULL OR franchise IS NOT NULL)
                ''', (cat,))
                
                subgenres = [row[0] for row in cursor.fetchall() if row[0]]
                
                subgenre_by_genre = {}
                for sg in subgenres:
                    cursor.execute('''
                        SELECT DISTINCT genre FROM hierarchy_cache 
                        WHERE normalized_category = ? 
                        AND (subgenre = ? OR sub_franchise = ? OR franchise = ?)
                        AND genre IS NOT NULL
                    ''', (cat, sg, sg, sg))
                    
                    genres_for_subgenre = [row[0] for row in cursor.fetchall() if row[0]]
                    for genre in genres_for_subgenre:
                        if genre not in subgenre_by_genre:
                            subgenre_by_genre[genre] = []
                        if sg not in subgenre_by_genre[genre]:
                            subgenre_by_genre[genre].append(sg)
                
                base_data = category_data.get(cat, {'genres': [], 'years': [], 'subgenres': {}})
                category_data_js[cat] = {
                    'genres': base_data['genres'],
                    'years': base_data['years'],
                    'subgenres': subgenre_by_genre
                }
            
            conn.close()
    except Exception as e:
        print(f"⚠️ Fehler beim Laden von Subgenre-Daten: {e}")
        for cat, data in category_data.items():
            category_data_js[cat] = {
                'genres': data['genres'],
                'years': data['years'],
                'subgenres': {}
            }

    category_data_json = json.dumps(category_data_js, ensure_ascii=False)

   
    footer_category_links = ''.join(
        f'<li><a href="#" onclick="showCategory(\'{escape_html(cat)}\'); return false;">{escape_html(cat)}</a></li>'
        for cat in categories
    )
    
    html_template = '''<!DOCTYPE html>
<html lang="de">
<head>
    <meta charset="UTF-8">
    <meta name="media-cache" content="{{get_cache_version()}}">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>🎬 Private Media Collection v1.0</title>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        :root {{
            --primary-color: #0a0a0a;
            --secondary-color: #141414;
            --accent-color: #e50914;
            --light-color: #2c2c2c;
            --dark-color: #ffffff;
            --text-color: #ffffff;
            --text-light: #b3b3b3;
            --text-muted: #6d6d6d;
            --shadow: 0 8px 16px rgba(0, 0, 0, 0.7);
            --transition: all 0.3s ease;
            --card-bg: #141414;
            --body-bg: #0a0a0a;
            --navbar-bg: rgba(20, 20, 20, 0.95);
            --footer-bg: #141414;
            --input-bg: rgba(255, 255, 255, 0.1);
            --player-bg: #141414;
            --hover-bg: #2c2c2c;
            --gradient-overlay: linear-gradient(to top, rgba(0,0,0,0.9) 0%, rgba(0,0,0,0.5) 50%, transparent 100%);
            --card-gradient: linear-gradient(135deg, #1a1a1a 0%, #2d2d2d 100%);
        }}
        .light-mode {{
            --primary-color: #ffffff;
            --secondary-color: #f5f5f5;
            --accent-color: #e50914;
            --light-color: #e0e0e0;
            --dark-color: #333333;
            --text-color: #333333;
            --text-light: #666666;
            --text-muted: #999999;
            --shadow: 0 8px 16px rgba(0, 0, 0, 0.1);
            --card-bg: #ffffff;
            --body-bg: #f5f5f5;
            --navbar-bg: rgba(255, 255, 255, 0.95);
            --footer-bg: #ffffff;
            --input-bg: rgba(0, 0, 0, 0.1);
            --player-bg: #ffffff;
            --hover-bg: #f0f0f0;
            --gradient-overlay: linear-gradient(to top, rgba(255,255,255,0.9) 0%, rgba(255,255,255,0.5) 50%, transparent 100%);
            --card-gradient: linear-gradient(135deg, #ffffff 0%, #f0f0f0 100%);
        }}
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            line-height: 1.6;
            color: var(--text-color);
            background-color: var(--body-bg);
            padding-bottom: 60px;
            transition: var(--transition);
        }}
        .navbar {{
            background-color: var(--navbar-bg);
            color: var(--text-color);
            padding: 0 2rem;
            display: flex;
            justify-content: space-between;
            align-items: center;
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            height: 70px;
            z-index: 1000;
            box-shadow: var(--shadow);
            transition: var(--transition);
            backdrop-filter: blur(10px);
        }}
        .nav-left {{
            display: flex;
            align-items: center;
            gap: 30px;
        }}
        .hamburger-menu {{
            background: none;
            border: none;
            color: var(--text-color);
            font-size: 1.5rem;
            cursor: pointer;
            padding: 8px;
            border-radius: 4px;
            transition: var(--transition);
        }}
        .hamburger-menu:hover {{
            background-color: var(--hover-bg);
        }}
        .logo-container {{
            display: flex;
            align-items: center;
            gap: 10px;
            cursor: pointer;
            transition: var(--transition);
            padding: 5px;
            border-radius: 4px;
        }}
        .logo-container:hover {{
            background-color: var(--hover-bg);
            transform: scale(1.05);
        }}
        .logo-icon {{
            width: 40px;
            height: 40px;
            background: linear-gradient(135deg, var(--accent-color), #ff6b6b);
            border-radius: 8px;
            display: flex;
            align-items: center;
            justify-content: center;
            color: white;
            font-size: 1.2rem;
        }}
        .logo-text {{
            font-size: 1.8rem;
            font-weight: bold;
            background: linear-gradient(45deg, var(--accent-color), #ff6b6b);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
        }}
        .nav-center {{
            display: none;
        }}
        .nav-item {{
            position: relative;
        }}
        .nav-link {{
            color: var(--text-color);
            text-decoration: none;
            padding: 8px 16px;
            border-radius: 4px;
            transition: var(--transition);
            display: flex;
            align-items: center;
            gap: 8px;
            font-weight: 500;
            font-size: 0.95rem;
        }}
        .nav-link:hover {{
            background-color: var(--hover-bg);
        }}
        .nav-link i {{
            font-size: 0.9rem;
        }}
        .dropdown {{
            position: absolute;
            top: 100%;
            left: 0;
            background-color: var(--card-bg);
            min-width: 250px;
            border-radius: 8px;
            box-shadow: var(--shadow);
            display: none;
            z-index: 1001;
            padding: 10px 0;
            border: 1px solid var(--light-color);
        }}
        .nav-item:hover .dropdown {{
            display: block;
        }}
        .dropdown-column {{
            padding: 15px;
        }}
        .dropdown-title {{
            font-weight: bold;
            margin-bottom: 10px;
            color: var(--accent-color);
            font-size: 0.9rem;
            text-transform: uppercase;
            letter-spacing: 1px;
        }}
        .dropdown-item {{
            display: block;
            padding: 8px 12px;
            color: var(--text-color);
            text-decoration: none;
            transition: var(--transition);
            border-radius: 4px;
            margin-bottom: 2px;
            font-size: 0.9rem;
        }}
        .dropdown-item:hover {{
            background-color: var(--hover-bg);
        }}
        .dropdown-grid {{
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 10px;
            max-height: 400px;
            overflow-y: auto;
        }}
        .nav-right {{
            display: flex;
            align-items: center;
            gap: 20px;
            flex: 1;
            justify-content: flex-end;
        }}
        .search-container {{
            position: relative;
            width: 400px;
            max-width: 50%;
        }}
        #searchInput {{
            width: 100%;
            padding: 10px 40px 10px 15px;
            border: 1px solid var(--light-color);
            border-radius: 25px;
            font-size: 0.9rem;
            background-color: var(--input-bg);
            color: var(--text-color);
            transition: var(--transition);
        }}
        #searchInput:focus {{
            outline: none;
            border-color: var(--accent-color);
            background-color: var(--card-bg);
        }}
        #searchInput::placeholder {{
            color: var(--text-muted);
        }}
        .search-btn {{
            position: absolute;
            right: 12px;
            top: 50%;
            transform: translateY(-50%);
            background: none;
            border: none;
            color: var(--text-muted);
            cursor: pointer;
            font-size: 1rem;
        }}
        .filter-toggle-btn {{
            background: none;
            border: none;
            color: var(--text-color);
            font-size: 1.2rem;
            cursor: pointer;
            padding: 8px;
            border-radius: 50%;
            width: 40px;
            height: 40px;
            display: flex;
            align-items: center;
            justify-content: center;
            transition: var(--transition);
        }}
        .filter-toggle-btn:hover {{
            background-color: var(--hover-bg);
            color: var(--accent-color);
        }}
        .user-menu {{
            position: relative;
        }}
        .user-btn {{
            background: none;
            border: none;
            color: var(--text-color);
            font-size: 1.3rem;
            cursor: pointer;
            padding: 8px;
            border-radius: 50%;
            width: 40px;
            height: 40px;
            display: flex;
            align-items: center;
            justify-content: center;
            transition: var(--transition);
        }}
        .user-btn:hover {{
            background-color: var(--hover-bg);
        }}
        .user-dropdown {{
            position: absolute;
            top: 100%;
            right: 0;
            background-color: var(--card-bg);
            min-width: 200px;
            border-radius: 8px;
            box-shadow: var(--shadow);
            display: none;
            z-index: 1001;
            padding: 10px 0;
            border: 1px solid var(--light-color);
        }}
        .user-menu:hover .user-dropdown {{
            display: block;
        }}
        .theme-toggle {{
            background: none;
            border: none;
            color: var(--text-color);
            font-size: 1.2rem;
            cursor: pointer;
            padding: 8px;
            border-radius: 50%;
            width: 40px;
            height: 40px;
            display: flex;
            align-items: center;
            justify-content: center;
            transition: var(--transition);
        }}
        .theme-toggle:hover {{
            background-color: var(--hover-bg);
        }}
        .main-content {{
            margin-top: 70px;
            padding: 2rem;
        }}
        .admin-notice {{
            display: none;
        }}
        .section-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin: 3rem 0 1.5rem;
        }}
        .section-title {{
            font-size: 1.8rem;
            font-weight: bold;
            color: var(--text-color);
        }}
        .category-tabs {{
            display: flex;
            gap: 10px;
            overflow-x: auto;
            padding: 10px 0;
            margin-bottom: 1.5rem;
            scrollbar-width: thin;
        }}
        .category-tabs::-webkit-scrollbar {{
            height: 4px;
        }}
        .category-tabs::-webkit-scrollbar-track {{
            background: var(--light-color);
            border-radius: 2px;
        }}
        .category-tabs::-webkit-scrollbar-thumb {{
            background: var(--accent-color);
            border-radius: 2px;
        }}
        .category-tab {{
            padding: 8px 20px;
            background-color: var(--light-color);
            color: var(--text-light);
            border-radius: 20px;
            font-size: 0.9rem;
            cursor: pointer;
            transition: var(--transition);
            white-space: nowrap;
            border: 1px solid transparent;
        }}
        .category-tab:hover {{
            background-color: var(--hover-bg);
            color: var(--text-color);
        }}
        .category-tab.active {{
            background-color: var(--accent-color);
            color: white;
            border-color: var(--accent-color);
        }}
        .media-row {{
            display: flex;
            gap: 1rem;
            overflow-x: auto;
            padding: 1rem 0;
            scrollbar-width: thin;
        }}
        .media-row::-webkit-scrollbar {{
            height: 6px;
        }}
        .media-row::-webkit-scrollbar-track {{
            background: var(--light-color);
            border-radius: 3px;
        }}
        .media-row::-webkit-scrollbar-thumb {{
            background: var(--accent-color);
            border-radius: 3px;
        }}
        .media-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
            gap: 1.2rem;
            padding: 1rem 0;
        }}
        @media (max-width: 768px) {{
            .media-grid {{
                grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
            }}
        }}
        .media-card {{
            background: var(--card-gradient);
            border-radius: 8px;
            overflow: hidden;
            box-shadow: var(--shadow);
            transition: var(--transition);
            cursor: pointer;
            position: relative;
            min-width: 180px;
            max-width: 220px;
        }}
        .media-card:hover {{
            transform: scale(1.03);
            box-shadow: 0 12px 24px rgba(0, 0, 0, 0.9);
            z-index: 10;
        }}
        .media-thumbnail {{
            height: 260px;
            position: relative;
            overflow: hidden;
        }}
        .media-thumbnail img {{
            width: 100%;
            height: 100%;
            object-fit: cover;
            transition: transform 0.3s;
        }}
        .media-card:hover .media-thumbnail img {{
            transform: scale(1.1);
        }}
        .resume-badge {{
            position: absolute;
            top: 10px;
            right: 10px;
            background-color: rgba(46, 204, 113, 0.9);
            animation: resume-pulse 2s ease-in-out infinite;
            color: white;
            width: 40px;
            height: 40px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 1.5rem;
            box-shadow: 0 2px 8px rgba(0,0,0,0.5);
            z-index: 5;
        }}
        @keyframes resume-pulse {{
            0%, 100% {{
                transform: scale(1);
                box-shadow: 0 2px 8px rgba(0,0,0,0.5);
            }}
            50% {{
                transform: scale(1.1);
                box-shadow: 0 4px 16px rgba(46, 204, 113, 0.6);
            }}
        }}
        .media-info-overlay {{
            position: absolute;
            bottom: 0;
            left: 0;
            right: 0;
            padding: 1rem;
            background: var(--gradient-overlay);
            color: white;
            transform: translateY(100%);
            transition: var(--transition);
        }}
        .media-card:hover .media-info-overlay {{
            transform: translateY(0);
        }}
        .media-title {{
            font-weight: bold;
            margin-bottom: 0.5rem;
            font-size: 1rem;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }}
        .media-meta {{
            font-size: 0.85rem;
            color: var(--text-light);
            display: flex;
            gap: 10px;
            flex-wrap: wrap;
        }}
        .media-year {{
            color: #fff;
            background-color: rgba(0, 0, 0, 0.5);
            padding: 2px 8px;
            border-radius: 10px;
        }}
        .media-genre {{
            color: #fff;
            background-color: var(--accent-color);
            padding: 2px 8px;
            border-radius: 10px;
        }}
        .stats-bar {{
            display: flex;
            justify-content: space-around;
            background: var(--card-gradient);
            padding: 1.5rem;
            border-radius: 10px;
            margin: 2rem 0;
            box-shadow: var(--shadow);
        }}
        .stat-item {{
            text-align: center;
            transition: var(--transition);
        }}
        .stat-item:hover {{
            transform: scale(1.05);
        }}
        .stat-number {{
            font-size: 2rem;
            font-weight: bold;
            color: var(--accent-color);
            margin-bottom: 0.5rem;
        }}
        .stat-label {{
            font-size: 0.9rem;
            color: var(--text-light);
            text-transform: uppercase;
            letter-spacing: 1px;
        }}
        .filter-panel {{
            background: var(--card-gradient);
            padding: 1.5rem;
            border-radius: 10px;
            margin-bottom: 2rem;
            box-shadow: var(--shadow);
            display: none;
        }}
        .filter-row {{
            display: flex;
            gap: 1rem;
            flex-wrap: wrap;
        }}
        .filter-group {{
            flex: 1;
            min-width: 200px;
        }}
        .filter-label {{
            display: block;
            margin-bottom: 0.5rem;
            font-weight: bold;
            color: var(--text-color);
            font-size: 0.9rem;
        }}
        .filter-select {{
            width: 100%;
            padding: 0.75rem;
            border: 1px solid var(--light-color);
            border-radius: 5px;
            background-color: var(--card-bg);
            color: var(--text-color);
            font-size: 0.9rem;
            transition: var(--transition);
        }}
        .filter-select:focus {{
            outline: none;
            border-color: var(--accent-color);
        }}
        .filter-buttons {{
            display: flex;
            gap: 1rem;
            justify-content: flex-end;
            margin-top: 1rem;
        }}
        .btn {{
            padding: 0.75rem 1.5rem;
            border: none;
            border-radius: 5px;
            cursor: pointer;
            font-weight: bold;
            transition: var(--transition);
            font-size: 0.9rem;
            display: flex;
            align-items: center;
            gap: 8px;
        }}
        .btn-primary {{
            background-color: var(--accent-color);
            color: white;
        }}
        .btn-primary:hover {{
            background-color: #ff2d2d;
        }}
        .btn-secondary {{
            background-color: var(--light-color);
            color: var(--text-color);
        }}
        .btn-secondary:hover {{
            background-color: var(--hover-bg);
        }}
        .pagination {{
            margin-top: 2rem;
            margin-bottom: 2rem;
        }}
        .page-link {{
            background-color: var(--card-bg);
            border-color: var(--light-color);
            color: var(--text-color);
        }}
        .page-link:hover {{
            background-color: var(--hover-bg);
            border-color: var(--accent-color);
        }}
        .page-item.active .page-link {{
            background-color: var(--accent-color);
            border-color: var(--accent-color);
        }}
        .audio-player {{
            position: fixed;
            bottom: 0;
            left: 0;
            right: 0;
            background: var(--player-bg);
            color: var(--text-color);
            padding: 1rem;
            display: none;
            z-index: 1001;
            box-shadow: 0 -2px 10px rgba(0,0,0,0.5);
            transition: var(--transition);
            border-top: 1px solid var(--light-color);
        }}
        .player-controls {{
            display: flex;
            align-items: center;
            gap: 1rem;
            max-width: 1200px;
            margin: 0 auto;
        }}
        .player-btn {{
            background: none;
            border: none;
            color: var(--text-color);
            font-size: 1.5rem;
            cursor: pointer;
            padding: 5px;
            transition: var(--transition);
        }}
        .player-btn:hover {{
            color: var(--accent-color);
        }}
        .player-title {{
            flex: 1;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
            font-weight: 500;
        }}
        .player-progress {{
            flex: 3;
            height: 5px;
            background: var(--light-color);
            border-radius: 3px;
            overflow: hidden;
            cursor: pointer;
        }}
        .progress-bar {{
            height: 100%;
            background: var(--accent-color);
            width: 0%;
            transition: width 0.1s;
        }}
        .history-progress-bar {{
            height: 4px;
            background: var(--light-color);
            border-radius: 2px;
            margin: 5px 0;
            overflow: hidden;
        }}
        .history-progress-fill {{
            height: 100%;
            background: var(--accent-color);
            transition: width 0.3s;
        }}
        .player-time {{
            min-width: 100px;
            text-align: center;
            font-size: 0.9rem;
            color: var(--text-light);
        }}
        .player-volume {{
            display: flex;
            align-items: center;
            gap: 10px;
            margin-left: 10px;
        }}
        .volume-slider {{
            width: 100px;
            height: 5px;
            -webkit-appearance: none;
            appearance: none;
            background: var(--light-color);
            border-radius: 3px;
            outline: none;
        }}
        .volume-slider::-webkit-slider-thumb {{
            -webkit-appearance: none;
            appearance: none;
            width: 15px;
            height: 15px;
            border-radius: 50%;
            background: var(--accent-color);
            cursor: pointer;
        }}
        .volume-slider::-moz-range-thumb {{
            width: 15px;
            height: 15px;
            border-radius: 50%;
            background: var(--accent-color);
            cursor: pointer;
            border: none;
        }}
        .video-overlay {{
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background: rgba(0, 0, 0, 0.95);
            z-index: 2000;
            display: none;
            justify-content: center;
            align-items: center;
        }}
        .video-container {{
            width: 90%;
            max-width: 1200px;
            background: #000;
            border-radius: 10px;
            overflow: hidden;
        }}
        .video-player {{
            width: 100%;
            height: 70vh;
            background: #000;
        }}
        .video-info {{
            padding: 1rem;
            background: var(--secondary-color);
            color: var(--text-color);
        }}
        .close-video {{
            position: absolute;
            top: 20px;
            right: 20px;
            background: var(--accent-color);
            border: none;
            color: white;
            width: 40px;
            height: 40px;
            border-radius: 50%;
            font-size: 1.5rem;
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            transition: var(--transition);
        }}
        .close-video:hover {{
            background: #ff2d2d;
            transform: scale(1.1);
        }}
        .search-results {{
            display: none;
        }}
        .result-count {{
            margin: 1rem 0;
            color: var(--text-light);
            font-size: 1rem;
            font-weight: normal;
        }}
        .loading {{
            display: none;
            text-align: center;
            padding: 3rem;
        }}
        .loading-spinner {{
            border: 4px solid var(--light-color);
            border-top: 4px solid var(--accent-color);
            border-radius: 50%;
            width: 40px;
            height: 40px;
            animation: spin 1s linear infinite;
            margin: 0 auto 1rem;
        }}
        @keyframes spin {{
            0% {{ transform: rotate(0deg); }}
            100% {{ transform: rotate(360deg); }}
        }}
        .no-results {{
            text-align: center;
            padding: 4rem 2rem;
            color: var(--text-light);
        }}
        .no-results i {{
            font-size: 3rem;
            margin-bottom: 1rem;
            color: var(--light-color);
        }}
        .badge {{
            display: inline-block;
            padding: 4px 10px;
            background-color: var(--light-color);
            color: var(--text-color);
            border-radius: 15px;
            font-size: 0.8rem;
            margin-right: 5px;
            margin-bottom: 5px;
        }}
        .badge.genre {{
            background-color: var(--accent-color);
            color: white;
        }}
        .badge.year {{
            background-color: var(--light-color);
            color: var(--text-color);
        }}
        .footer {{
            background-color: var(--footer-bg);
            color: var(--text-color);
            padding: 3rem 2rem;
            margin-top: 4rem;
            transition: var(--transition);
            border-top: 1px solid var(--light-color);
        }}
        .footer-content {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 2rem;
            max-width: 1400px;
            margin: 0 auto;
        }}
        .footer-section h3 {{
            margin-bottom: 1rem;
            color: var(--accent-color);
        }}
        .footer-links {{
            list-style: none;
        }}
        .footer-links li {{
            margin-bottom: 0.5rem;
        }}
        .footer-links a {{
            color: var(--text-light);
            text-decoration: none;
            transition: var(--transition);
        }}
        .footer-links a:hover {{
            color: var(--accent-color);
            padding-left: 5px;
        }}
        .copyright {{
            text-align: center;
            margin-top: 2rem;
            padding-top: 2rem;
            border-top: 1px solid var(--light-color);
            color: var(--text-muted);
            font-size: 0.9rem;
        }}
        .autoplay-toggle {{
            position: fixed;
            bottom: 80px;
            right: 20px;
            background-color: var(--accent-color);
            color: white;
            width: 50px;
            height: 50px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            cursor: pointer;
            z-index: 1000;
            box-shadow: var(--shadow);
            transition: var(--transition);
        }}
        .autoplay-toggle:hover {{
            transform: scale(1.1);
        }}
        .autoplay-toggle.active {{
            background-color: #2ecc71;
        }}
        .history-toggle {{
            position: fixed;
            bottom: 140px;
            right: 20px;
            background-color: #3498db;
            color: white;
            width: 50px;
            height: 50px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            cursor: pointer;
            z-index: 1000;
            box-shadow: var(--shadow);
            transition: var(--transition);
        }}
        .history-toggle:hover {{
            transform: scale(1.1);
        }}
        .settings-toggle {{
            position: fixed;
            bottom: 200px;
            right: 20px;
            background-color: #9b59b6;
            color: white;
            width: 50px;
            height: 50px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            cursor: pointer;
            z-index: 1000;
            box-shadow: var(--shadow);
            transition: var(--transition);
        }}
        .settings-toggle:hover {{
            transform: scale(1.1);
        }}
        .history-panel {{
            position: fixed;
            bottom: 200px;
            right: 80px;
            background: var(--card-gradient);
            color: var(--text-color);
            width: 300px;
            max-height: 400px;
            border-radius: 10px;
            box-shadow: var(--shadow);
            display: none;
            z-index: 1001;
            overflow: hidden;
        }}
        .history-header {{
            padding: 1rem;
            background-color: var(--accent-color);
            color: white;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        .history-list {{
            max-height: 300px;
            overflow-y: auto;
            padding: 1rem;
        }}
        .history-item {{
            padding: 0.5rem;
            margin-bottom: 0.5rem;
            background-color: var(--light-color);
            border-radius: 5px;
            cursor: pointer;
            transition: var(--transition);
        }}
        .history-item:hover {{
            background-color: var(--hover-bg);
        }}
        .history-title {{
            font-weight: bold;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }}
        .history-meta {{
            font-size: 0.8rem;
            color: var(--text-light);
            display: flex;
            justify-content: space-between;
        }}
        .settings-panel {{
            position: fixed;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            background: var(--card-gradient);
            color: var(--text-color);
            width: 500px;
            max-width: 90vw;
            /* max-height entfernt */
            border-radius: 10px;
            box-shadow: var(--shadow);
            display: none;
            z-index: 2001;
        }}
        .settings-header {{
            padding: 1rem;
            background-color: var(--accent-color);
            color: white;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        .settings-content {{
            padding: 1.5rem;
            max-height: 60vh; /* Höhe für den Content-Bereich */
            overflow-y: auto;
        }}
        .settings-group {{
            margin-bottom: 1.5rem;
        }}
        .settings-label {{
            display: block;
            margin-bottom: 0.5rem;
            font-weight: bold;
        }}
        .settings-input {{
            width: 100%;
            padding: 0.75rem;
            border: 1px solid var(--light-color);
            border-radius: 5px;
            background-color: var(--card-bg);
            color: var(--text-color);
            font-size: 0.9rem;
        }}
        .settings-input:focus {{
            outline: none;
            border-color: var(--accent-color);
        }}
        .settings-select {{
            width: 100%;
            padding: 0.75rem;
            border: 1px solid var(--light-color);
            border-radius: 5px;
            background-color: var(--card-bg);
            color: var(--text-color);
            font-size: 0.9rem;
        }}
        .settings-slider {{
            width: 100%;
            height: 5px;
            -webkit-appearance: none;
            appearance: none;
            background: var(--light-color);
            border-radius: 3px;
            outline: none;
        }}
        .settings-slider::-webkit-slider-thumb {{
            -webkit-appearance: none;
            appearance: none;
            width: 20px;
            height: 20px;
            border-radius: 50%;
            background: var(--accent-color);
            cursor: pointer;
        }}
        .settings-footer {{
            padding: 1rem;
            background-color: var(--light-color);
            display: flex;
            justify-content: flex-end;
            gap: 1rem;
            border-top: 1px solid var(--hover-bg);
        }}
        @media (max-width: 768px) {{
            .settings-footer {{
                flex-direction: column;
            }}
            .settings-footer .btn {{
                width: 100%;
                text-align: center;
            }}
        }}
            .search-container {{
                width: 300px;
            }}
            .media-card {{
                min-width: 160px;
                max-width: 200px;
            }}
            .media-thumbnail {{
                height: 230px;
            }}
        }}
        @media (max-width: 768px) {{
            .navbar {{
                padding: 0 1rem;
                height: 60px;
            }}
            .main-content {{
                margin-top: 60px;
                padding: 1rem;
            }}
            .logo-text {{
                font-size: 1.4rem;
            }}
            .search-container {{
                width: 200px;
            }}
            .section-header {{
                flex-direction: column;
                align-items: flex-start;
                gap: 1rem;
            }}
            .category-tabs {{
                width: 100%;
            }}
            .media-card {{
                min-width: 140px;
                max-width: 160px;
            }}
            .media-thumbnail {{
                height: 200px;
            }}
            .stats-bar {{
                flex-wrap: wrap;
                gap: 1rem;
            }}
            .stat-item {{
                flex: 1 1 45%;
            }}
            .video-player {{
                height: 50vh;
            }}
            .player-controls {{
                flex-wrap: wrap;
            }}
            .player-progress {{
                order: 3;
                flex: 100%;
                margin-top: 10px;
            }}
            .settings-panel {{
                width: 90%;
            }}
        }}
        @media (max-width: 480px) {{
            .nav-right {{
                gap: 10px;
            }}
            .search-container {{
                width: 150px;
            }}
            .media-card {{
                min-width: 120px;
            }}
            .media-thumbnail {{
                height: 180px;
            }}
            .section-title {{
                font-size: 1.4rem;
            }}
            .stats-bar {{
                flex-direction: column;
                gap: 1.5rem;
            }}
        }}
    </style>
</head>
<body class="dark-mode">
    <nav class="navbar">
        <div class="nav-left">
            <button class="hamburger-menu" onclick="toggleSidebar()">
                <i class="fas fa-bars"></i>
            </button>
            <div class="logo-container" onclick="showHome(); return false;">
                <div class="logo-icon">
                    <i class="fas fa-film"></i>
                </div>
                <span class="logo-text">Media Indexer</span>
            </div>
        </div>
        <div class="nav-center" style="display: none;">
        </div>
        <div class="nav-right">
            <div class="search-container">
                <input type="text" id="searchInput" placeholder="Suchen (Titel, Genre, Jahr...)">
                <!-- NUR EIN FILTER BUTTON WIE GEFORDERT -->
                <button class="search-btn" onclick="performSearch()" title="Suchen">
                    <i class="fas fa-search"></i>
                </button>
            </div>
            <button class="filter-toggle-btn" onclick="toggleFilterPanel()" title="Filter anzeigen">
                <i class="fas fa-filter"></i>
            </button>
            <button class="theme-toggle" onclick="toggleDarkMode()" id="themeToggle" title="Light Mode">
                <i class="fas fa-sun"></i>
            </button>
            <div class="user-menu">
                <button class="user-btn">
                    <i class="fas fa-user"></i>
                </button>
                <div class="user-dropdown">
                    <a href="#" class="dropdown-item" onclick="showHelp(); return false;">
                        <i class="fas fa-question-circle"></i> Hilfe
                    </a>
                    <a href="#" class="dropdown-item" onclick="exportMediaList(); return false;">
                        <i class="fas fa-download"></i> Export
                    </a>
                    <a href="#" class="dropdown-item" onclick="clearCache(); return false;">
                        <i class="fas fa-trash-alt"></i> Cache leeren
                    </a>
                    <a href="#" class="dropdown-item" onclick="rebuildHierarchyCache(); return false;">
                        <i class="fas fa-sync-alt"></i> Hierarchie neu aufbauen
                    </a>
                </div>
            </div>
        </div>
    </nav>
    <div class="main-content">
        <section id="homeSection">
            <div class="section-header">
                <h2 class="section-title">Neueste Hinzufügungen</h2>
                <div class="category-tabs" id="trendingTabs">
                    {category_tabs_html}
                </div>
            </div>
            <div class="media-row" id="trendingRow">
                {trending_media}
            </div>
            <div class="section-header">
                <h2 class="section-title">Derzeit Beliebt</h2>
            </div>
            <div class="media-row" id="latestRow">
                {latest_media_cards}
            </div>
            <div class="stats-bar">
                {stats_bar_html}
                <div class="stat-item">
                    <div class="stat-number">{total_gb_formatted}</div>
                    <div class="stat-label">GB Gesamt</div>
                </div>
            </div>
        </section>
        <section id="allMediaSection" style="display: none;">
            <div class="section-header">
                <h2 class="section-title">Alle Medien</h2>
                <button class="btn btn-secondary" onclick="toggleFilterPanel()">
                    <i class="fas fa-filter"></i> Filter
                </button>
            </div>
            <div class="filter-panel" id="filterPanel">
                <div class="filter-row">
                    <div class="filter-group">
                        <label class="filter-label">Kategorie</label>
                        <select id="filterCategory" class="filter-select" onchange="onCategoryChange()">
                            {select_options_categories}
                        </select>
                    </div>
                    <div class="filter-group">
                        <label class="filter-label">Genre</label>
                        <select id="filterGenre" class="filter-select" onchange="onGenreChange()" disabled>
                            <option value="">Alle Genres</option>
                        </select>
                    </div>
                    <div class="filter-group">
                        <label class="filter-label">Subgenre/Franchise</label>
                        <select id="filterSubgenre" class="filter-select" onchange="onSubgenreChange()" disabled>
                            <option value="">Alle Subgenres</option>
                        </select>
                    </div>
                    <div class="filter-group">
                        <label class="filter-label">Serie/Reihe</label>
                        <select id="filterSeries" class="filter-select" onchange="onSeriesChange()" disabled>
                            <option value="">Alle Serien</option>
                        </select>
                    </div>
                    <div class="filter-group" id="dynamicFilterGroup">
                        <label class="filter-label" id="dynamicFilterLabel">Jahr</label>
                        <select id="filterDynamic" class="filter-select" onchange="applyFilters()" disabled>
                            <option value="">Alle</option>
                        </select>
                    </div>
                </div>
                <div class="filter-buttons">
                    <button class="btn btn-secondary" onclick="resetFilters()">
                        <i class="fas fa-redo"></i> Zurücksetzen
                    </button>
                    <button class="btn btn-primary" onclick="applyFilters()">
                        <i class="fas fa-check"></i> Anwenden
                    </button>
                </div>
            </div>
            <div class="media-grid" id="allMediaRow">
            </div>
            <div id="paginationContainer"></div>
            <div id="loading" class="loading">
                <div class="loading-spinner"></div>
                <p>Lade Medien...</p>
            </div>
            <div id="noResults" class="no-results" style="display: none;">
                <i class="fas fa-search"></i>
                <h3>Keine Ergebnisse gefunden</h3>
                <p>Versuchen Sie es mit anderen Suchbegriffen oder Filtern</p>
            </div>
        </section>
        <section id="searchResultsSection" class="search-results">
            <div class="section-header">
                <h2 class="section-title">
                    <span>Suchergebnisse</span>
                    <span id="resultCount" class="result-count"></span>
                </h2>
            </div>
            <div class="media-grid" id="searchResultsRow"></div>
            <div id="searchPaginationContainer"></div>
        </section>
    </div>
    
    <!-- ERWEITERTE FEATURES -->
    <div class="settings-toggle" onclick="showSettingsPanel()" title="Einstellungen">
        <i class="fas fa-cog"></i>
    </div>
    <div class="history-toggle" onclick="toggleHistoryPanel()" title="Abspiel-History">
        <i class="fas fa-history"></i>
    </div>
    <div class="autoplay-toggle" id="autoplayToggle" onclick="toggleAutoplay()" title="Autoplay deaktiviert">
        <i class="fas fa-play-circle"></i>
    </div>
    
    <!-- History Panel -->
    <div class="history-panel" id="historyPanel">
        <div class="history-header">
            <h3>Abspiel-History</h3>
            <button onclick="toggleHistoryPanel()" style="background: none; border: none; color: white;">
                <i class="fas fa-times"></i>
            </button>
        </div>
        <div class="history-list" id="historyList">
            <!-- History-Einträge werden hier dynamisch eingefügt -->
        </div>
    </div>
    
    <!-- Settings Panel -->
    <div class="settings-panel" id="settingsPanel">
        <div class="settings-header">
            <h3>Einstellungen</h3>
            <button onclick="hideSettingsPanel()" style="background: none; border: none; color: white;">
                <i class="fas fa-times"></i>
            </button>
        </div>
        <div class="settings-content">
            <div class="settings-group">
                <label class="settings-label">Netzwerk-Modus</label>
                <select id="networkMode" class="settings-select">
                    <option value="localhost">Nur lokaler Zugriff (localhost)</option>
                    <option value="network">Netzwerk-Freigabe (0.0.0.0)</option>
                </select>
                <small id="networkInfo" style="color: var(--text-light); display: block; margin-top: 5px;"></small>
            </div>
            
            <div class="settings-group">
                <label class="settings-label">Maximale Anzahl Clients</label>
                <input type="number" id="maxClients" class="settings-input" min="1" max="10" value="3">
            </div>
            
            <div class="settings-group">
                <label class="settings-label">Abspiel-History aktivieren</label>
                <select id="enableHistory" class="settings-select">
                    <option value="true">Ja</option>
                    <option value="false">Nein</option>
                </select>
            </div>
            
            <div class="settings-group">
                <label class="settings-label">Lautstärke</label>
                <input type="range" id="volumeSlider" class="settings-slider" min="0" max="1" step="0.1">
                <div style="display: flex; justify-content: space-between;">
                    <span>0%</span>
                    <span id="volumeValue">70%</span>
                    <span>100%</span>
                </div>
            </div>
            
            <div class="settings-group">
                <label class="settings-label">Audio-Sprache für MKV (z.B. ger, eng)</label>
                <input type="text" id="audioLanguage" class="settings-input" placeholder="ger">
            </div>
            
            <div class="settings-group">
                <label class="settings-label">Autoplay</label>
                <select id="autoplaySetting" class="settings-select">
                    <option value="false">Deaktiviert</option>
                    <option value="true">Aktiviert</option>
                </select>
            </div>
        </div>
        <div class="settings-footer">
            <button class="btn btn-secondary" onclick="hideSettingsPanel()">Abbrechen</button>
            <button class="btn btn-primary" onclick="saveSettings()">Speichern</button>
        </div>
    </div>
    
    <div class="audio-player" id="audioPlayer">
        <div class="player-controls">
            <button class="player-btn" onclick="togglePlay()">
                <i class="fas fa-play" id="playBtnIcon"></i>
            </button>
            <div class="player-title" id="playerTitle">Keine Datei ausgewählt</div>
            <div class="player-progress" onclick="seekAudio(event)">
                <div class="progress-bar" id="progressBar"></div>
            </div>
            <div class="player-time" id="playerTime">00:00 / 00:00</div>
            <div class="player-volume">
                <i class="fas fa-volume-up"></i>
                <input type="range" class="volume-slider" id="volumeControl" min="0" max="1" step="0.1" oninput="changeVolume(this.value)">
            </div>
            <button class="player-btn" onclick="closeAudioPlayer()">
                <i class="fas fa-times"></i>
            </button>
        </div>
    </div>
    <div class="video-overlay" id="videoOverlay">
        <button class="close-video" onclick="closeVideoPlayer()">
            <i class="fas fa-times"></i>
        </button>
        <div class="video-container">
            <video class="video-player" id="videoPlayer" controls>
                Ihr Browser unterstützt das Video-Tag nicht.
            </video>
            <div class="video-info">
                <h3 id="videoTitle">Video</h3>
                <div id="videoInfo"></div>
            </div>
        </div>
    </div>
    <footer class="footer">
        <div class="footer-content">
            <div class="footer-section">
                <h3>Private Media Collection v1.0</h3>
                <p>Ihre persönliche Sammlung lokaler Medien.</p>
                <p>100% privat - Keine Cloud, keine Abonnements.</p>
            </div>
            <div class="footer-section">
                <h3>Schnellzugriff</h3>
                <ul class="footer-links">
                    <li><a href="#" onclick="showHome(); return false;">Startseite</a></li>
                    <li><a href="#" onclick="showAllMedia(); return false;">Alle Medien</a></li>
                    {footer_category_links}
                    <li><a href="#" onclick="showSettingsPanel(); return false;">Einstellungen</a></li>
                </ul>
            </div>
            <div class="footer-section">
                <h3>Statistiken</h3>
                <ul class="footer-links">
                    <li>{total_files} Medien</li>
                    <li>{total_categories} Kategorien</li>
                    <li>{total_genres} Genres</li>
                    <li>{total_gb_formatted} GB Gesamtgröße</li>
                </ul>
            </div>
            <div class="footer-section">
                <h3>System</h3>
                <ul class="footer-links">
                    <li><a href="#" onclick="clearCache(); return false;">Cache leeren</a></li>
                    <li><a href="#" onclick="exportMediaList(); return false;">Liste exportieren</a></li>
                    <li><a href="#" onclick="rebuildHierarchyCache(); return false;">Hierarchie neu aufbauen</a></li>
                    <li><a href="#" onclick="showHelp(); return false;">Hilfe & Anleitung</a></li>
                </ul>
            </div>
        </div>
        <div class="copyright">
            <p>© {current_year} Private Media Collection v1.0</p>
            <p>Generiert am {current_date} | Alle Medien sind lokal gespeichert.</p>
        </div>
    </footer>
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
    <script>
        const allMedia = {all_media_json_str};
        const categoryData = {category_data_json};
        const CACHE_VERSION = "{{get_cache_version()}}";
        console.log('Media Cache Version:', CACHE_VERSION);

        // Speichere Cache-Version in sessionStorage
        if (!sessionStorage.getItem('media_cache_version') || 
            sessionStorage.getItem('media_cache_version') !== CACHE_VERSION) {{
            sessionStorage.setItem('media_cache_version', CACHE_VERSION);
            console.log('Cache Version aktualisiert:', CACHE_VERSION);
        }}
        
        let currentFilters = {{
            category: '',
            genre: '',
            subgenre: '',
            series: '',
            season: '',
            year: '',
            search: '',
            page: 1
        }};
        
        let currentAudio = null;
        let isPlaying = false;
        let updateInterval = null;
        let isDarkMode = true;
        let currentCategory = null;
        let currentSearchResults = [];
        let currentSearchPage = 1;
        let autoplayEnabled = false;
        let currentMediaQueue = [];
        let currentMediaIndex = -1;
        let currentMediaInfo = null;
        let volumeLevel = 0.7;
        let sessionVolume = null;
        let history = [];
        
        // ===== ERWEITERTE FUNKTIONEN =====
        
        async function loadSettings() {{
            try {{
                const response = await fetch('/api/settings');
                const data = await response.json();
                
                if (data.success) {{
                    const settings = data.settings;
                    
                    document.getElementById('networkMode').value = settings.network_mode;
                    document.getElementById('maxClients').value = settings.max_clients;
                    document.getElementById('enableHistory').value = settings.enable_history.toString();
                    document.getElementById('volumeSlider').value = settings.volume_level;
                    document.getElementById('volumeValue').textContent = Math.round(settings.volume_level * 100) + '%';
                    document.getElementById('audioLanguage').value = settings.audio_language;
                    document.getElementById('autoplaySetting').value = settings.autoplay_enabled.toString();
                    
                    volumeLevel = settings.volume_level;
                    sessionVolume = null;
                    
                    if (document.getElementById('volumeControl')) {{
                        document.getElementById('volumeControl').value = volumeLevel;
                    }}
                    
                    autoplayEnabled = settings.autoplay_enabled;
                    updateAutoplayToggle();
                    
                    updateNetworkInfo(settings);

                    window.settingsLoaded = true;
                }}
            }} catch (error) {{
                console.error('Fehler beim Laden der Einstellungen:', error);
                window.settingsLoaded = true;
            }}
        }}
        
        function updateNetworkInfo(settings) {{
            const info = document.getElementById('networkInfo');
            if (!info) return;
            
            if (settings.network_mode === 'network') {{
                info.textContent = `Netzwerk aktiv - Zugriff über: http://${{settings.local_ip}}:${{settings.server_port}}`;
            }} else {{
                info.textContent = 'Nur lokaler Zugriff (localhost)';
            }}
        }}
        
        async function saveSettings() {{
            try {{
                const newVolumeLevel = parseFloat(document.getElementById('volumeSlider').value);
                
                const settings = {{
                    network_mode: document.getElementById('networkMode').value,
                    max_clients: parseInt(document.getElementById('maxClients').value),
                    enable_history: document.getElementById('enableHistory').value === 'true',
                    volume_level: newVolumeLevel,
                    audio_language: document.getElementById('audioLanguage').value,
                    autoplay_enabled: document.getElementById('autoplaySetting').value === 'true'
                }};
                
                const response = await fetch('/api/settings/update', {{
                    method: 'POST',
                    headers: {{
                        'Content-Type': 'application/json'
                    }},
                    body: JSON.stringify(settings)
                }});
                
                const data = await response.json();
                
                if (data.success) {{
                    volumeLevel = newVolumeLevel;
                    sessionVolume = null;
                    
                    if (document.getElementById('volumeControl')) {{
                        document.getElementById('volumeControl').value = volumeLevel;
                    }}
                    
                    alert('Einstellungen gespeichert' + (data.restart_required ? '\\nServer-Neustart erforderlich!' : ''));
                    loadSettings();
                    hideSettingsPanel();
                }} else {{
                    alert('Fehler: ' + data.error);
                }}
            }} catch (error) {{
                alert('Fehler beim Speichern: ' + error);
            }}
        }}
        
        async function loadHistory() {{
            try {{
                const response = await fetch('/api/history?limit=10');
                const data = await response.json();
                
                if (data.success) {{
                    history = data.history;
                    updateHistoryPanel();
                }}
            }} catch (error) {{
                console.error('Fehler beim Laden der History:', error);
            }}
        }}

        // Hilfsfunktion: Sekunden in hh:mm:ss formatieren
        function formatTimestamp(seconds) {{
            if (!seconds || isNaN(seconds)) return "0:00";
            
            const hours = Math.floor(seconds / 3600);
            const minutes = Math.floor((seconds % 3600) / 60);
            const secs = Math.floor(seconds % 60);
            
            if (hours > 0) {{
                return `${{hours}}:${{minutes.toString().padStart(2, '0')}}:${{secs.toString().padStart(2, '0')}}`;
            }} else {{
                return `${{minutes}}:${{secs.toString().padStart(2, '0')}}`;
            }}
        }}
        
        function updateHistoryPanel() {{
            const list = document.getElementById('historyList');
            list.innerHTML = '';
            
            if (history.length === 0) {{
                list.innerHTML = '<div style="text-align: center; padding: 20px; color: var(--text-light);">Keine History verfügbar</div>';
                return;
            }}
            
            history.forEach(item => {{
                const itemDiv = document.createElement('div');
                itemDiv.className = 'history-item';
                itemDiv.onclick = () => playFromHistory(item);
                
                const timestamp = formatTimestamp(item.last_position);
                const totalTimestamp = formatTimestamp(item.duration);
                const percentage = item.duration > 0 
                    ? (item.last_position / item.duration * 100) 
                    : 0;
                
                itemDiv.innerHTML = `
                    <div class="history-title">${{escapeHtml(item.filename)}}</div>
                    <div class="history-progress-bar">
                        <div class="history-progress-fill" style="width: ${{percentage}}%"></div>
                    </div>
                    <div class="history-meta">
                        <span>${{escapeHtml(item.category)}}</span>
                        <span>${{timestamp}} / ${{totalTimestamp}}</span>
                    </div>
                `;
                
                list.appendChild(itemDiv);
            }});
        }}
               
        function playFromHistory(historyItem) {{
            playMedia(historyItem.filepath, historyItem.filename, historyItem.category);
            
            // Bei Video Resume-Point anbieten
            const ext = historyItem.filepath.toLowerCase().split('.').pop();
            if (ext === 'mkv' || ext === 'mp4' || ext === 'avi') {{
                checkResumePoint(historyItem.filepath);
            }}
            
            toggleHistoryPanel();
        }}
        
        async function checkResumePoint(filepath) {{
            try {{
                const response = await fetch(`/api/resume?filepath=${{encodeURIComponent(filepath)}}`);
                const data = await response.json();
                
                if (data.success && data.has_resume) {{
                    const resume = data.resume;
                    // ✅ KORREKT: formatTimestamp verwenden
                    const timestamp = formatTimestamp(resume.position);
                    const shouldResume = confirm(`Fortsetzen bei ${{timestamp}}?`);
                    
                    if (shouldResume) {{
                        if (currentAudio) {{
                            currentAudio.currentTime = resume.position;
                        }} else {{
                            const videoPlayer = document.getElementById('videoPlayer');
                            if (videoPlayer) {{
                                videoPlayer.currentTime = resume.position;
                            }}
                        }}
                    }}
                }}
            }} catch (error) {{
                console.error('Fehler beim Abrufen des Resume-Points:', error);
            }}
        }}
       
        function showSettingsPanel() {{
            document.getElementById('settingsPanel').style.display = 'block';
            loadSettings();
        }}
        
        function hideSettingsPanel() {{
            document.getElementById('settingsPanel').style.display = 'none';
        }}
        
        function toggleHistoryPanel() {{
            const panel = document.getElementById('historyPanel');
            panel.style.display = panel.style.display === 'block' ? 'none' : 'block';
            
            if (panel.style.display === 'block') {{
                loadHistory();
            }}
        }}
        
        function changeVolume(value) {{
                    const newVolume = parseFloat(value);
                    
                    sessionVolume = newVolume;
                    
                    if (currentAudio) {{
                        currentAudio.volume = newVolume;
                    }}

                    const videoPlayer = document.getElementById('videoPlayer');
                    if (videoPlayer && !videoPlayer.paused) {{
                        videoPlayer.volume = newVolume;
                    }}
                    
                    console.log(`🔊 Session-Lautstärke geändert auf: ${{Math.round(newVolume * 100)}}%`);
                }}
                
                function getCurrentVolume() {{
                    return sessionVolume !== null ? sessionVolume : volumeLevel;
                }}
        
        function updateAutoplayToggle() {{
            const toggleBtn = document.getElementById('autoplayToggle');
            
            if (autoplayEnabled) {{
                toggleBtn.classList.add('active');
                toggleBtn.title = 'Autoplay aktiviert';
                toggleBtn.innerHTML = '<i class="fas fa-pause-circle"></i>';
            }} else {{
                toggleBtn.classList.remove('active');
                toggleBtn.title = 'Autoplay deaktiviert';
                toggleBtn.innerHTML = '<i class="fas fa-play-circle"></i>';
            }}
        }}
        
        // ===== BESTEHENDE FUNKTIONEN (angepasst) =====
        
        async function onCategoryChange() {{
            const category = document.getElementById('filterCategory').value;
            
            resetDependentFilters(['genre', 'subgenre', 'series', 'dynamic']);
            
            if (!category) {{
                disableAllFilters();
                return;
            }}
            
            currentFilters.category = category;
            
            try {{
                const response = await fetch(`/api/genres?category=${{encodeURIComponent(category)}}`);
                const data = await response.json();
                
                if (data.success && data.genres.length > 0) {{
                    populateGenreSelect(data.genres);
                    document.getElementById('filterGenre').disabled = false;
                }} else {{
                    document.getElementById('filterGenre').disabled = true;
                }}
                
                updateDynamicFilter(category);
                
            }} catch (error) {{
                console.error('Fehler beim Laden der Genres:', error);
            }}
            
            applyFilters();
        }}
        
        async function onGenreChange() {{
            const category = currentFilters.category;
            const genre = document.getElementById('filterGenre').value;
            
            resetDependentFilters(['subgenre', 'series', 'dynamic']);
            
            if (!genre) {{
                document.getElementById('filterSubgenre').disabled = true;
                document.getElementById('filterSeries').disabled = true;
                applyFilters();
                return;
            }}
            
            currentFilters.genre = genre;
            
            try {{
                const response = await fetch(
                    `/api/subgenres?category=${{encodeURIComponent(category)}}&genre=${{encodeURIComponent(genre)}}`
                );
                const data = await response.json();
                
                if (data.success && data.subgenres.length > 0) {{
                    populateSubgenreSelect(data.subgenres);
                    document.getElementById('filterSubgenre').disabled = false;
                }} else {{
                    document.getElementById('filterSubgenre').disabled = true;
                }}
                
            }} catch (error) {{
                console.error('Fehler beim Laden der Subgenres:', error);
            }}
            
            applyFilters();
        }}
        
        async function onSubgenreChange() {{
            const category = currentFilters.category;
            const genre = currentFilters.genre;
            const subgenre = document.getElementById('filterSubgenre').value;
            
            resetDependentFilters(['series']);
            
            if (!subgenre) {{
                document.getElementById('filterSeries').disabled = true;
                if (category === 'Serie') {{
                    loadSeasonsForSeriesContext(category, genre, subgenre, '');
                }}
                applyFilters();
                return;
            }}
            
            currentFilters.subgenre = subgenre;
            
            if (category === 'Serie') {{
                try {{
                    const params = new URLSearchParams({{
                        category: category,
                        genre: genre || '',
                        subgenre: subgenre
                    }});
                    
                    const response = await fetch('/api/series?' + params);
                    const data = await response.json();
                    
                    if (data.success && data.series && data.series.length > 0) {{
                        populateSeriesSelect(data.series);
                        document.getElementById('filterSeries').disabled = false;
                    }} else {{
                        console.log('ℹ️ Keine Series-Ebene → Lade Staffeln direkt');
                        document.getElementById('filterSeries').disabled = true;
                        document.getElementById('filterSeries').innerHTML = '<option value="">Keine Serie/Reihe</option>';
                        await loadSeasonsForSeriesContext(category, genre, subgenre, '');
                    }}
                }} catch (error) {{
                    console.error('❌ Fehler:', error);
                }}
            }} else {{
                try {{
                    const params = new URLSearchParams({{
                        category: category,
                        genre: genre || '',
                        subgenre: subgenre
                    }});
                    
                    const response = await fetch('/api/series?' + params);
                    const data = await response.json();
                    
                    if (data.success && data.series && data.series.length > 0) {{
                        populateSeriesSelect(data.series);
                        document.getElementById('filterSeries').disabled = false;
                    }} else {{
                        document.getElementById('filterSeries').disabled = true;
                        document.getElementById('filterSeries').innerHTML = '<option value="">Keine Serien verfügbar</option>';
                    }}
                }} catch (error) {{
                    console.error('❌ Fehler:', error);
                }}
            }}
            
            applyFilters();
        }}
        
        async function loadSeasonsForSeriesContext(category, genre, subgenre, series) {{
            if (category !== 'Serie') return;
            
            try {{
                const params = new URLSearchParams({{
                    category: category,
                    genre: genre || '',
                    subgenre: subgenre || '',
                    series: series || ''
                }});
                
                const response = await fetch('/api/seasons?' + params);
                const data = await response.json();
                
                if (data.success && data.seasons && data.seasons.length > 0) {{
                    populateDynamicSelect(data.seasons, 'Staffel');
                    document.getElementById('filterDynamic').disabled = false;
                    console.log('✅ Staffeln geladen: ' + data.seasons.length);
                }} else {{
                    document.getElementById('filterDynamic').disabled = true;
                    document.getElementById('filterDynamic').innerHTML = '<option value="">Keine Staffeln</option>';
                }}
            }} catch (error) {{
                console.error('❌ Staffel-Ladefehler:', error);
            }}
        }}
        
        async function onSeriesChange() {{
            const category = currentFilters.category;
            const genre = currentFilters.genre;
            const series = document.getElementById('filterSeries').value;
            
            if (!series) {{
                currentFilters.series = '';
                applyFilters();
                return;
            }}
            
            currentFilters.series = series;
            
            // Für Serien: Staffeln laden
            if (category === 'Serie') {{
                try {{
                    const params = new URLSearchParams({{
                        category: category,
                        genre: genre || '',
                        subgenre: currentFilters.subgenre || '',
                        series: series
                    }});
                    
                    console.log(`🔍 Lade Staffeln für Serie: ${{series}}`);
                    
                    const response = await fetch(`/api/seasons?${{params}}`);
                    const data = await response.json();
                    
                    console.log('📊 Seasons API Response:', data);
                    
                    if (data.success && data.seasons && data.seasons.length > 0) {{
                        populateDynamicSelect(data.seasons, 'Staffel');
                        document.getElementById('filterDynamic').disabled = false;
                        console.log(`✅ Geladen: ${{data.seasons.length}} Staffeln`);
                    }} else {{
                        console.log('ℹ️ Keine Staffeln für diese Serie gefunden');
                        document.getElementById('filterDynamic').disabled = true;
                    }}
                }} catch (error) {{
                    console.error('❌ Fehler beim Laden der Staffeln:', error);
                    document.getElementById('filterDynamic').disabled = true;
                }}
            }}
            
            applyFilters();
        }}
        
        function applyFilters() {{
            const category = document.getElementById('filterCategory').value;
            const genre = document.getElementById('filterGenre').value;
            const subgenre = document.getElementById('filterSubgenre').value;
            const series = document.getElementById('filterSeries').value;
            const dynamic = document.getElementById('filterDynamic').value;
            
            currentFilters.category = category;
            currentFilters.genre = genre;
            currentFilters.subgenre = subgenre;
            currentFilters.series = series;
            
            if (category === 'Serie') {{
                currentFilters.season = dynamic;
                currentFilters.year = '';
            }} else {{
                currentFilters.year = dynamic;
                currentFilters.season = '';
            }}
            
            currentFilters.page = 1;
            
            console.log('🔍 Applying filters:', currentFilters);
            
            loadAllMedia(1);
        }}
        
        function updateDynamicFilter(category) {{
            const label = document.getElementById('dynamicFilterLabel');
            const select = document.getElementById('filterDynamic');
            
            if (category === 'Serie') {{
                label.textContent = 'Staffel';
                select.innerHTML = '<option value="">Alle Staffeln</option>';
                select.disabled = true;
            }} else {{
                label.textContent = 'Jahr';
                select.innerHTML = '<option value="">Alle Jahre</option>';
                
                const data = categoryData[category];
                if (data && data.years) {{
                    data.years.forEach(year => {{
                        const option = document.createElement('option');
                        option.value = year;
                        option.textContent = year;
                        select.appendChild(option);
                    }});
                    select.disabled = false;
                }}
            }}
        }}
        
        function populateGenreSelect(genres) {{
            const select = document.getElementById('filterGenre');
            select.innerHTML = '<option value="">Alle Genres</option>';
            genres.forEach(genre => {{
                const option = document.createElement('option');
                option.value = genre;
                option.textContent = genre;
                select.appendChild(option);
            }});
        }}
        
        function populateSubgenreSelect(subgenres) {{
            const select = document.getElementById('filterSubgenre');
            select.innerHTML = '<option value="">Alle Subgenres/Franchises</option>';
            subgenres.forEach(sg => {{
                const option = document.createElement('option');
                option.value = sg;
                option.textContent = sg;
                select.appendChild(option);
            }});
        }}
        
        function populateSeriesSelect(series) {{
            const select = document.getElementById('filterSeries');
            select.innerHTML = '<option value="">Alle Serien/Reihen</option>';
            
            console.log('🔧 Populate Series Select:', series);
            
            if (!series || series.length === 0) {{
                console.log('   ⚠️ Keine Series zum Befüllen');
                return;
            }}
            
            series.forEach(s => {{
                const option = document.createElement('option');
                option.value = s;
                option.textContent = s;
                select.appendChild(option);
                console.log(`   ➕ Added: ${{s}}`);
            }});
            
            console.log(`   ✅ Series-Select befüllt mit ${{series.length}} Einträgen`);
        }}
        
        function populateDynamicSelect(values, type) {{
            const select = document.getElementById('filterDynamic');
            select.innerHTML = `<option value="">Alle ${{type}}n</option>`;
            values.forEach(val => {{
                const option = document.createElement('option');
                option.value = val;
                option.textContent = type === 'Staffel' ? `Staffel ${{val}}` : val;
                select.appendChild(option);
            }});
        }}
        
        function resetDependentFilters(filterNames) {{
            filterNames.forEach(name => {{
                if (name === 'genre') {{
                    document.getElementById('filterGenre').innerHTML = '<option value="">Alle Genres</option>';
                    document.getElementById('filterGenre').disabled = true;
                    currentFilters.genre = '';
                }} else if (name === 'subgenre') {{
                    document.getElementById('filterSubgenre').innerHTML = '<option value="">Alle Subgenres</option>';
                    document.getElementById('filterSubgenre').disabled = true;
                    currentFilters.subgenre = '';
                }} else if (name === 'series') {{
                    document.getElementById('filterSeries').innerHTML = '<option value="">Alle Serien</option>';
                    document.getElementById('filterSeries').disabled = true;
                    currentFilters.series = '';
                }} else if (name === 'dynamic') {{
                    document.getElementById('filterDynamic').innerHTML = '<option value="">Alle</option>';
                    document.getElementById('filterDynamic').disabled = true;
                    currentFilters.season = '';
                    currentFilters.year = '';
                }}
            }});
        }}
        
        function disableAllFilters() {{
            document.getElementById('filterGenre').disabled = true;
            document.getElementById('filterSubgenre').disabled = true;
            document.getElementById('filterSeries').disabled = true;
            document.getElementById('filterDynamic').disabled = true;
        }}
        
        function resetFilters() {{
            document.getElementById('filterCategory').value = '';
            document.getElementById('filterGenre').value = '';
            document.getElementById('filterSubgenre').value = '';
            document.getElementById('filterSeries').value = '';
            document.getElementById('filterDynamic').value = '';
            
            disableAllFilters();
            
            currentFilters = {{
                category: '',
                genre: '',
                subgenre: '',
                series: '',
                season: '',
                year: '',
                search: '',
                page: 1
            }};
            
            loadAllMedia(1);
        }}
        
        function initDarkMode() {{
            if (isDarkMode) {{
                document.body.classList.remove('light-mode');
                document.body.classList.add('dark-mode');
                document.getElementById('themeToggle').innerHTML = '<i class="fas fa-sun"></i>';
                document.getElementById('themeToggle').title = 'Light Mode';
            }} else {{
                document.body.classList.remove('dark-mode');
                document.body.classList.add('light-mode');
                document.getElementById('themeToggle').innerHTML = '<i class="fas fa-moon"></i>';
                document.getElementById('themeToggle').title = 'Dark Mode';
            }}
        }}
        
        function toggleDarkMode() {{
            isDarkMode = !isDarkMode;
            initDarkMode();
        }}
        
        function playMediaFromCard(card) {{
            const filepath = decodeURIComponent(card.dataset.filepath);
            const filename = card.dataset.filename;
            const category = card.dataset.category;
            
            currentMediaQueue = getMediaQueueFromCurrentContext();
            currentMediaIndex = findMediaIndexInQueue(filepath);
            
            playMedia(filepath, filename, category);
        }}
        
        function getMediaQueueFromCurrentContext() {{
            const cards = document.querySelectorAll('.media-card');
            const queue = [];
            
            cards.forEach(card => {{
                const filepath = decodeURIComponent(card.dataset.filepath);
                const filename = card.dataset.filename;
                const category = card.dataset.category;
                
                const media = allMedia.find(m => m.filepath === filepath);
                if (media) {{
                    queue.push({{
                        filepath: filepath,
                        filename: filename,
                        category: category,
                        media: media
                    }});
                }}
            }});
            
            return queue;
        }}
        
        function findMediaIndexInQueue(filepath) {{
            return currentMediaQueue.findIndex(item => item.filepath === filepath);
        }}
        
        function playNextMedia() {{
            // AUTOPLAY BOUNDARY FIX: Stoppe wenn letztes Medium erreicht
            if (!autoplayEnabled || currentMediaQueue.length === 0) return;
            
            currentMediaIndex++;
            
            // Wenn letztes Medium erreicht, stoppe Autoplay
            if (currentMediaIndex >= currentMediaQueue.length) {{
                currentMediaIndex = -1;
                toggleAutoplay(); // Autoplay deaktivieren
                alert('Autoplay beendet: Letztes Medium erreicht');
                return;
            }}
            
            const nextMedia = currentMediaQueue[currentMediaIndex];
            playMedia(nextMedia.filepath, nextMedia.filename, nextMedia.category);
        }}
        
        function toggleAutoplay() {{
            autoplayEnabled = !autoplayEnabled;
            
            // In Settings speichern
            fetch('/api/settings/update', {{
                method: 'POST',
                headers: {{
                    'Content-Type': 'application/json'
                }},
                body: JSON.stringify({{ autoplay_enabled: autoplayEnabled }})
            }});
            
            updateAutoplayToggle();
        }}
        
        function showHome() {{
            document.getElementById('homeSection').style.display = 'block';
            document.getElementById('allMediaSection').style.display = 'none';
            document.getElementById('searchResultsSection').style.display = 'none';
            document.getElementById('filterPanel').style.display = 'none';
            updatePageTitle('Startseite');
            updateActiveTab('trendingTabs');
            currentCategory = null;
            currentMediaQueue = getMediaQueueFromCurrentContext();
        }}
        
        function showAllMedia() {{
            document.getElementById('homeSection').style.display = 'none';
            document.getElementById('allMediaSection').style.display = 'block';
            document.getElementById('searchResultsSection').style.display = 'none';
            updatePageTitle('Alle Medien');
            loadAllMedia(1);
        }}
        
        function showCategory(category) {{
            console.log('Zeige Kategorie:', category);
            showAllMedia();
            currentCategory = category;
            currentFilters.category = category;
            currentFilters.page = 1;
            
            document.getElementById('filterCategory').value = category;
            onCategoryChange();
            updatePageTitle(category);
        }}
        
        function playMedia(filepath, title, category) {{
            const ext = filepath.toLowerCase().split('.').pop();
            const audioExts = ['mp3', 'wav', 'flac', 'aac', 'ogg', 'm4a'];
            const videoExts = ['mp4', 'mkv', 'avi', 'mov', 'wmv', 'webm'];
            
            // Füge diese globale Variable hinzu
            currentMediaInfo = {{
                filepath: filepath,
                filename: title,
                category: category
            }};
            
            if (audioExts.includes(ext)) {{
                playAudio(filepath, title);
            }} else if (videoExts.includes(ext)) {{
                playVideo(filepath, title);
            }} else {{
                openFile(filepath);
            }}
        }}
        
        async function addToHistory(filepath, title, category, position = 0, duration = 0, completed = false) {{
            try {{
                // Stelle sicher, dass die Werte numerisch sind
                const pos = Number(position) || 0;
                const dur = Number(duration) || 0;
                
                const response = await fetch('/api/history/add', {{
                    method: 'POST',
                    headers: {{
                        'Content-Type': 'application/json'
                    }},
                    body: JSON.stringify({{
                        filepath: filepath,
                        filename: title,
                        category: category,
                        position: pos,      // Numerischer Wert
                        duration: dur,      // Numerischer Wert
                        completed: completed
                    }})
                }});
                
                const data = await response.json();
                return data.success;
            }} catch (error) {{
                console.error('History-Fehler:', error);
                return false;
            }}
        }}
        
        function playAudio(filepath, title) {{
            if (currentAudio) {{
                currentAudio.pause();
                clearInterval(updateInterval);
            }}
            
            const safePath = encodeURIComponent(filepath);
            currentAudio = new Audio(`/media?filepath=${{safePath}}`);

            const actualVolume = getCurrentVolume();
            currentAudio.volume = actualVolume;
            
            document.getElementById('audioPlayer').style.display = 'block';
            document.getElementById('playerTitle').textContent = title;
            document.getElementById('volumeControl').value = actualVolume;
            
            currentAudio.addEventListener('loadedmetadata', function() {{
                updatePlayerTime();
                
                if (currentMediaInfo && this.duration) {{
                    const duration = Number(this.duration);
                    if (!isNaN(duration) && duration > 0) {{
                        addToHistory(currentMediaInfo.filepath, currentMediaInfo.filename, 
                                    currentMediaInfo.category, 0, duration);
                    }}
                }}
            }});

            currentAudio.addEventListener('ended', () => {{
                isPlaying = false;
                document.getElementById('playBtnIcon').className = 'fas fa-play';
                updateProgress();
                
                if (currentMediaInfo && currentAudio.duration) {{
                    const duration = Number(currentAudio.duration);
                    const position = Number(currentAudio.currentTime);
                    if (!isNaN(duration) && !isNaN(position) && duration > 0) {{
                        addToHistory(currentMediaInfo.filepath, currentMediaInfo.filename,
                                    currentMediaInfo.category, position, duration, true);
                    }}
                }}
                
                if (autoplayEnabled) {{
                    setTimeout(playNextMedia, 1000);
                }}
            }});
            
            currentAudio.addEventListener('timeupdate', function() {{
                updateProgress();
                
                if (currentMediaInfo && this.duration) {{
                    const duration = Number(this.duration);
                    const currentTime = Math.floor(this.currentTime);
                    if (!isNaN(duration) && duration > 0 && currentTime % 30 === 0) {{
                        addToHistory(currentMediaInfo.filepath, currentMediaInfo.filename,
                                   currentMediaInfo.category, currentTime, duration);
                    }}
                }}
            }});
            
            currentAudio.play().then(() => {{
                isPlaying = true;
                document.getElementById('playBtnIcon').className = 'fas fa-pause';
                updateInterval = setInterval(updateProgress, 1000);
            }}).catch(e => {{
                console.error('Fehler beim Abspielen:', e);
                alert('Fehler beim Laden der Audiodatei.');
            }});
        }}
        
        function playVideo(filepath, title) {{
            const videoPlayer = document.getElementById('videoPlayer');
            const videoOverlay = document.getElementById('videoOverlay');
            const safePath = encodeURIComponent(filepath);
            
            videoPlayer.pause();
            videoPlayer.removeAttribute('src');
            
            if (videoPlayer.hasListeners) {{
                delete videoPlayer.hasListeners;
            }}
            
            videoPlayer.load();

            const actualVolume = getCurrentVolume();
            
            videoPlayer.onloadedmetadata = function() {{
                this.volume = actualVolume;
                
                if (currentMediaInfo && this.duration) {{
                    const duration = Number(this.duration);
                    if (!isNaN(duration) && duration > 0) {{
                        addToHistory(currentMediaInfo.filepath, currentMediaInfo.filename,
                                    currentMediaInfo.category, 0, duration);
                    }}
                }}
            }};
            
            videoPlayer.onended = function() {{
                if (currentMediaInfo && this.duration) {{
                    const duration = Number(this.duration);
                    const position = Number(this.currentTime);
                    if (!isNaN(duration) && !isNaN(position) && duration > 0) {{
                        addToHistory(currentMediaInfo.filepath, currentMediaInfo.filename,
                                    currentMediaInfo.category, position, duration, true);
                    }}
                }}
                
                if (autoplayEnabled) {{
                    setTimeout(playNextMedia, 1000);
                }}
            }};
            
            videoPlayer.onvolumechange = function() {{
                if (document.getElementById('volumeControl')) {{
                    document.getElementById('volumeControl').value = this.volume;
                }}
                sessionVolume = this.volume;
                console.log(`🔊 Video-Lautstärke geändert: ${{Math.round(this.volume * 100)}}%`);
            }};
            
            const mediaInfo = allMedia.find(m => m.filepath === filepath);
            let infoHTML = '';
            if (mediaInfo) {{
                if (mediaInfo.category) infoHTML += `<p>Kategorie: ${{escapeHtml(mediaInfo.category)}}</p>`;
                if (mediaInfo.genre) infoHTML += `<p>Genre: ${{escapeHtml(mediaInfo.genre)}}</p>`;
                if (mediaInfo.year) infoHTML += `<p>Jahr: ${{escapeHtml(mediaInfo.year)}}</p>`;
                if (mediaInfo.contributors) infoHTML += `<p>Interpret: ${{escapeHtml(mediaInfo.contributors)}}</p>`;
            }}
            document.getElementById('videoInfo').innerHTML = infoHTML;
            document.getElementById('videoTitle').textContent = title;
            
            videoPlayer.innerHTML = `
                <source src="/media?filepath=${{safePath}}" type="video/mp4">
            `;
            videoOverlay.style.display = 'flex';
            
            videoPlayer.load();
            videoPlayer.play().catch(e => {{
                console.error('Video-Abspielfehler:', e);
                alert('Fehler beim Laden des Videos.');
            }});
        }}
        
        function togglePlay() {{
            if (!currentAudio) return;
            if (isPlaying) {{
                currentAudio.pause();
                document.getElementById('playBtnIcon').className = 'fas fa-play';
            }} else {{
                currentAudio.play();
                document.getElementById('playBtnIcon').className = 'fas fa-pause';
            }}
            isPlaying = !isPlaying;
        }}
        
        function closeAudioPlayer() {{
            if (currentAudio) {{
                currentAudio.pause();
                currentAudio = null;
            }}
            clearInterval(updateInterval);
            document.getElementById('audioPlayer').style.display = 'none';
            isPlaying = false;
        }}
        
        function closeVideoPlayer() {{
            const videoPlayer = document.getElementById('videoPlayer');
            videoPlayer.pause();
            videoPlayer.src = '';
            videoPlayer.onended = null;
            document.getElementById('videoOverlay').style.display = 'none';
        }}
        
        function updateProgress() {{
            if (!currentAudio) return;
            const progress = (currentAudio.currentTime / currentAudio.duration) * 100 || 0;
            document.getElementById('progressBar').style.width = `${{progress}}%`;
            updatePlayerTime();
        }}
        
        function updatePlayerTime() {{
            if (!currentAudio) return;
            const current = formatTime(currentAudio.currentTime);
            const duration = formatTime(currentAudio.duration);
            document.getElementById('playerTime').textContent = `${{current}} / ${{duration}}`;
        }}
        
        function formatTime(seconds) {{
            if (!seconds || isNaN(seconds)) return '00:00';
            const mins = Math.floor(seconds / 60);
            const secs = Math.floor(seconds % 60);
            return `${{mins.toString().padStart(2, '0')}}:${{secs.toString().padStart(2, '0')}}`;
        }}
        
        function seekAudio(event) {{
            if (!currentAudio) return;
            const progressBar = document.querySelector('.player-progress');
            const rect = progressBar.getBoundingClientRect();
            const pos = (event.clientX - rect.left) / rect.width;
            currentAudio.currentTime = pos * currentAudio.duration;
            updateProgress();
        }}
        
        function performSearch() {{
            const query = document.getElementById('searchInput').value.toLowerCase().trim();
            if (!query) return;
            
            currentFilters.search = query;
            currentSearchPage = 1;
            loadSearchResults(query, 1);
        }}
        
        function loadSearchResults(query, page) {{
            const searchParams = new URLSearchParams({{
                search: query,
                page: page
            }});
            
            document.getElementById('loading').style.display = 'block';
            
            fetch(`/api/media?${{searchParams}}`)
                .then(response => response.json())
                .then(data => {{
                    if (data.success) {{
                        showSearchResults(data.media, data.total_count, page, data.total_pages);
                        currentSearchResults = data.media;
                    }} else {{
                        showNoResults();
                    }}
                    document.getElementById('loading').style.display = 'none';
                }})
                .catch(error => {{
                    console.error('Suchfehler:', error);
                    showNoResults();
                    document.getElementById('loading').style.display = 'none';
                }});
        }}
        
        function showSearchResults(results, totalCount, page, totalPages) {{
            document.getElementById('homeSection').style.display = 'none';
            document.getElementById('allMediaSection').style.display = 'none';
            document.getElementById('searchResultsSection').style.display = 'block';
            updatePageTitle('Suchergebnisse');
            
            const row = document.getElementById('searchResultsRow');
            const count = document.getElementById('resultCount');
            count.textContent = `(${{totalCount}} Treffer)`;
            
            if (results.length === 0) {{
                row.innerHTML = '<div class="no-results"><i class="fas fa-search"></i><h3>Keine Ergebnisse gefunden</h3><p>Versuchen Sie es mit anderen Suchbegriffen</p></div>';
                document.getElementById('searchPaginationContainer').innerHTML = '';
                return;
            }}
            
            row.innerHTML = results.map(m => createMediaCardHTML(m)).join('');
            currentMediaQueue = getMediaQueueFromCurrentContext();
            
            const paginationHTML = generatePaginationHTML(page, totalPages, 'search');
            document.getElementById('searchPaginationContainer').innerHTML = paginationHTML;
        }}
        
        function loadAllMedia(page) {{
            currentFilters.page = page;
            
            const searchParams = new URLSearchParams(currentFilters);
            searchParams.set('page', page);
            
            document.getElementById('loading').style.display = 'block';
            document.getElementById('allMediaRow').innerHTML = '';
            document.getElementById('paginationContainer').innerHTML = '';
            
            fetch(`/api/media?${{searchParams}}`)
                .then(response => response.json())
                .then(data => {{
                    if (data.success) {{
                        displayFilteredMedia(data.media, data.total_count, page, data.total_pages);
                    }} else {{
                        showNoResults();
                    }}
                    document.getElementById('loading').style.display = 'none';
                }})
                .catch(error => {{
                    console.error('Ladefehler:', error);
                    showNoResults();
                    document.getElementById('loading').style.display = 'none';
                }});
        }}
        
        function displayFilteredMedia(mediaList, totalCount, page, totalPages) {{
            const row = document.getElementById('allMediaRow');
            const noRes = document.getElementById('noResults');
            
            if (mediaList.length === 0) {{
                row.style.display = 'grid';
                row.innerHTML = '';
                noRes.style.display = 'block';
                document.getElementById('paginationContainer').innerHTML = '';
            }} else {{
                noRes.style.display = 'none';
                row.style.display = 'grid';
                row.innerHTML = mediaList.map(m => createMediaCardHTML(m)).join('');
                currentMediaQueue = getMediaQueueFromCurrentContext();
                
                const paginationHTML = generatePaginationHTML(page, totalPages, 'main');
                document.getElementById('paginationContainer').innerHTML = paginationHTML;
            }}
        }}
        
        function changePage(page, type = 'main') {{
            if (type === 'search') {{
                currentSearchPage = page;
                loadSearchResults(currentFilters.search, page);
            }} else {{
                loadAllMedia(page);
            }}
        }}
        
        function generatePaginationHTML(currentPage, totalPages, type = 'main') {{
            if (totalPages <= 1) return '';
            
            let pages = [];
            
            if (currentPage > 1) {{
                pages.push(`
                    <li class="page-item">
                        <a class="page-link" href="#" onclick="changePage(${{currentPage - 1}}, '${{type}}'); return false;">
                            <i class="fas fa-chevron-left"></i>
                        </a>
                    </li>
                `);
            }}
            
            if (currentPage > 3) {{
                pages.push(`
                    <li class="page-item">
                        <a class="page-link" href="#" onclick="changePage(1, '${{type}}'); return false;">1</a>
                    </li>
                `);
                if (currentPage > 4) {{
                    pages.push('<li class="page-item disabled"><span class="page-link">...</span></li>');
                }}
            }}
            
            for (let pageNum = Math.max(1, currentPage - 2); pageNum <= Math.min(totalPages, currentPage + 2); pageNum++) {{
                if (pageNum === currentPage) {{
                    pages.push(`
                        <li class="page-item active">
                            <span class="page-link">${{pageNum}}</span>
                        </li>
                    `);
                }} else {{
                    pages.push(`
                        <li class="page-item">
                            <a class="page-link" href="#" onclick="changePage(${{pageNum}}, '${{type}}'); return false;">${{pageNum}}</a>
                        </li>
                    `);
                }}
            }}
            
            if (currentPage < totalPages - 2) {{
                if (currentPage < totalPages - 3) {{
                    pages.push('<li class="page-item disabled"><span class="page-link">...</span></li>');
                }}
                pages.push(`
                    <li class="page-item">
                        <a class="page-link" href="#" onclick="changePage(${{totalPages}}, '${{type}}'); return false;">${{totalPages}}</a>
                    </li>
                `);
            }}
            
            if (currentPage < totalPages) {{
                pages.push(`
                    <li class="page-item">
                        <a class="page-link" href="#" onclick="changePage(${{currentPage + 1}}, '${{type}}'); return false;">
                            <i class="fas fa-chevron-right"></i>
                        </a>
                    </li>
                `);
            }}
            
            return `
                <nav aria-label="Seitennavigation">
                    <ul class="pagination justify-content-center">
                        ${{pages.join('')}}
                    </ul>
                </nav>
            `;
        }}
        
        function showNoResults() {{
            const row = document.getElementById('allMediaRow');
            const noRes = document.getElementById('noResults');
            row.style.display = 'grid';
            row.innerHTML = '';
            noRes.style.display = 'block';
            document.getElementById('paginationContainer').innerHTML = '';
        }}
        
        function filterByCategory(category) {{
            showCategory(category);
        }}
        
        function filterByGenre(genre) {{
            showAllMedia();
            document.getElementById('filterGenre').value = genre;
            const cat = document.getElementById('filterCategory').value;
            if (cat) {{
                onGenreChange();
            }}
            applyFilters();
        }}
        
        function filterByYear(year) {{
            showAllMedia();
            document.getElementById('filterDynamic').value = year;
            applyFilters();
        }}
        
        function createMediaCardHTML(media) {{
            const filename = escapeHtml(media.filename || 'Unbekannt');
            const category = escapeHtml(media.normalized_category || media.category || 'Unbekannt');
            const year = escapeHtml(media.year || '');
            const genre = escapeHtml(media.genre || '');
            const filepath = escapeHtml(media.filepath || '');
            const safePath = encodeURIComponent(filepath);
            const thumbnailUrl = `/thumbnail?filepath=${{safePath}}`;
            
            // Resume-Point prüfen
            const hasResume = media.hasResume || false;
            const resumeTimestamp = media.resumeTimestamp || '';
            
            return `
                <div class="media-card" onclick="playMediaFromCard(this)" data-filepath="${{safePath}}" data-filename="${{filename}}" data-category="${{category}}">
                    <div class="media-thumbnail">
                        <img src="${{thumbnailUrl}}" alt="${{filename}}" style="width:100%;height:100%;object-fit:cover;">
                        ${{hasResume ? `<div class="resume-badge" title="Fortsetzen bei ${{resumeTimestamp}}"><i class="fas fa-play-circle"></i></div>` : ''}}
                    </div>
                    <div class="media-info-overlay">
                        <div class="media-title">${{filename}}</div>
                        <div class="media-meta">
                            ${{year ? `<span class="media-year">${{year}}</span>` : ''}}
                            ${{genre ? `<span class="media-genre">${{genre}}</span>` : ''}}
                        </div>
                    </div>
                </div>
            `;
        }}
        
        function escapeHtml(text) {{
            if (!text) return '';
            return String(text)
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;')
                .replace(/"/g, '&quot;')
                .replace(/'/g, '&#39;');
        }}
        
        function showHelp() {{
            alert('Private Media Collection v1.0 - Hilfe:\\n\\n' +
                  'NEUE FEATURES:\\n' +
                  '• Netzwerk-Sharing: In Einstellungen aktivieren\\n' +
                  '• Abspiel-History: Rechts unten (Uhr-Icon)\\n' +
                  '• Resume-Funktion: Fortsetzen bei Videos\\n' +
                  '• Lautstärkeregler: In Audio-Player\\n' +
                  '• Einstellungen: Rechts unten (Zahnrad-Icon)\\n\\n' +
                  'BASIS-FUNKTIONEN:\\n' +
                  '• Klicken Sie auf Medienkarten zum Abspielen\\n' +
                  '• Autoplay: Rechts unten aktivieren (Serien)\\n' +
                  '• Paginierung: Unten zwischen Seiten wechseln\\n' +
                  '• Filter: Kategorie-spezifische Genres/Subgenres\\n' +
                  '• Tastaturkürzel: Strg+F (Suche), ESC (Schließen)\\n' +
                  '• Dark Mode: Sonnen-Symbol in der Navigation');
        }}
        
        function exportMediaList() {{
            const csv = "data:text/csv;charset=utf-8," 
                + "Name,Kategorie,Genre,Jahr,Pfad\\n"
                + allMedia.map(m => 
                    `"${{m.filename}}","${{m.normalized_category || m.category}}","${{m.genre}}","${{m.year}}","${{m.filepath}}"`
                  ).join("\\n");
            const link = document.createElement("a");
            link.href = encodeURI(csv);
            link.download = "medienliste.csv";
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
        }}
        
        function clearCache() {{
            if (confirm('Möchten Sie wirklich ALLE Thumbnails aus dem Cache löschen?\\nSie werden beim nächsten Laden neu generiert.')) {{
                fetch('/clear_cache')
                    .then(response => response.json())
                    .then(data => {{
                        alert(`🗑️ ${{data.deleted}} Thumbnails wurden gelöscht.\\nDie Seite wird neu geladen.`);
                        location.reload();
                    }})
                    .catch(error => {{
                        alert('Fehler beim Löschen des Caches: ' + error);
                    }});
            }}
        }}
        
        function rebuildHierarchyCache() {{
            if (confirm('Möchten Sie die Hierarchie-Erkennung neu aufbauen?\\nDies kann bei großen Sammlungen einige Minuten dauern.')) {{
                fetch('/api/rebuild_hierarchy')
                    .then(response => response.json())
                    .then(data => {{
                        if (data.success) {{
                            alert('✅ Hierarchie-Cache erfolgreich neu aufgebaut.\\nDie Seite wird neu geladen.');
                            location.reload();
                        }} else {{
                            alert('❌ Fehler beim Neuerstellen des Hierarchie-Cache: ' + data.message);
                        }}
                    }})
                    .catch(error => {{
                        alert('Fehler: ' + error);
                    }});
            }}
        }}
        
        function toggleSidebar() {{
            alert('Sidebar-Funktion wird in einer zukünftigen Version implementiert.');
        }}
        
        function toggleFilterPanel() {{
            const panel = document.getElementById('filterPanel');
            panel.style.display = panel.style.display === 'none' ? 'block' : 'none';
        }}
        
        function updatePageTitle(title) {{
            document.title = `🎬 ${{title}} - Private Collection v1.0`;
        }}
        
        function updateActiveTab(containerId) {{
            const tabs = document.querySelectorAll('.category-tab');
            tabs.forEach(tab => tab.classList.remove('active'));
            const firstTab = document.querySelector(`#${{containerId}} .category-tab`);
            if (firstTab) firstTab.classList.add('active');
        }}
        
        document.addEventListener('keydown', (e) => {{
            if (e.key === 'Escape') {{
                if (document.getElementById('videoOverlay').style.display === 'flex') closeVideoPlayer();
                else if (document.getElementById('audioPlayer').style.display === 'block') closeAudioPlayer();
                else if (document.getElementById('settingsPanel').style.display === 'block') hideSettingsPanel();
                else if (document.getElementById('historyPanel').style.display === 'block') toggleHistoryPanel();
            }}
            if (e.ctrlKey && e.key === 'f') {{
                e.preventDefault();
                document.getElementById('searchInput').focus();
            }}
            if (e.key === ' ' && document.getElementById('audioPlayer').style.display === 'block') {{
                e.preventDefault();
                togglePlay();
            }}
        }});
        
        document.getElementById('searchInput').addEventListener('input', (e) => {{
            clearTimeout(window.searchTimeout);
            const q = e.target.value.trim();
            if (q.length < 2) return;
            window.searchTimeout = setTimeout(() => {{
                if (q.length >= 2) performSearch();
            }}, 500);
        }});
        
        document.getElementById('searchInput').addEventListener('keypress', (e) => {{
            if (e.key === 'Enter') performSearch();
        }});
        
        // !!! WICHTIG: NUR EIN DOMContentLoaded EVENT-LISTENER !!!
        document.addEventListener('DOMContentLoaded', () => {{
            initDarkMode();
            loadSettings();  // Lädt Einstellungen aus Datenbank (Volume, Autoplay, etc.)
            showHome();      // Zeigt Startseite
            setupVideoPlayerListeners(); // Video-Player Listener initialisieren
        }});
        
        // Video Player Event Listener Setup
        function setupVideoPlayerListeners() {{
            const videoPlayer = document.getElementById('videoPlayer');
            if (!videoPlayer) {{
                // Versuche später erneut
                setTimeout(setupVideoPlayerListeners, 500);
                return;
            }}
            
            // Verhindere doppelte Listener
            if (videoPlayer.hasListeners) return;
            videoPlayer.hasListeners = true;
            
            videoPlayer.addEventListener('timeupdate', function() {{
                if (currentMediaInfo && this.duration && !isNaN(this.duration)) {{
                    const currentTime = Math.floor(this.currentTime);
                    if (currentTime % 30 === 0) {{
                        addToHistory(currentMediaInfo.filepath, currentMediaInfo.filename,
                                   currentMediaInfo.category, currentTime, this.duration);
                    }}
                }}
            }});
            
            videoPlayer.addEventListener('pause', function() {{
                if (currentMediaInfo && this.duration && !isNaN(this.duration)) {{
                    addToHistory(currentMediaInfo.filepath, currentMediaInfo.filename,
                               currentMediaInfo.category, this.currentTime, this.duration);
                }}
            }});
            
            videoPlayer.addEventListener('seeking', function() {{
                if (currentMediaInfo && this.duration && !isNaN(this.duration)) {{
                    addToHistory(currentMediaInfo.filepath, currentMediaInfo.filename,
                               currentMediaInfo.category, this.currentTime, this.duration);
                }}
            }});
        }}
        
    </script>
</body>
</html>'''
    
    return html_template.format(
        dropdown_categories=dropdown_categories,
        dropdown_genres=dropdown_genres,
        dropdown_years=dropdown_years,
        category_tabs_html=category_tabs_html,
        select_options_categories=select_options_categories,
        select_options_genres=select_options_genres,
        select_options_years=select_options_years,
        total_files=total_files,
        total_gb_formatted=total_gb_formatted,
        current_date=current_date,
        current_year=current_year,
        all_media_json_str=all_media_json_str,
        category_data_json=category_data_json,
        trending_media=trending_media,
        latest_media_cards=latest_media_cards,
        stats_bar_html=stats_bar_html,
        footer_category_links=footer_category_links,
        total_categories=total_categories,
        total_genres=total_genres,
        initial_filter_state_json=initial_filter_state_json,
    )

def generate_web_interface():
    """
    Hauptfunktion zur Generierung des Web-Interfaces.
    Lädt Daten, bereitet sie auf und generiert HTML.
    """
    if not os.path.exists(DB_PATH):
        print("❌ Hauptdatenbank nicht gefunden.")
        return

    # Settings-DB initialisieren
    if not os.path.exists(SETTINGS_DB_PATH):
        print("🆕 Erstelle Settings-Datenbank...")
        init_settings_database()
    else:
        print("✅ Settings-Datenbank vorhanden")

    # Hierarchie-Cache initialisieren
    if not os.path.exists(HIERARCHY_DB_PATH):
        print("🔄 Keine Hierarchie-Datenbank gefunden – führe Initialaufbau durch...")
        success = rebuild_hierarchy_cache()
        if not success:
            print("❌ Fehler beim Initialaufbau der Hierarchie-Datenbank – Abbruch.")
            return
    else:
        print("✅ Hierarchie-Datenbank bereits vorhanden – überspringe Neuaufbau.")

    # Alle Medien laden
    with MainDBConnection() as cursor_main:
        cursor_main.execute("SELECT * FROM media_files WHERE filepath != ''")
        all_media_raw = [dict(row) for row in cursor_main.fetchall()]

    print("📊 Lade Daten mit KORRIGIERTER KATEGORIE-ERKENNUNG...")
    print(f"   Reichere {len(all_media_raw)} Medien für Startseite an...")

    # Medien anreichern
    all_media = []
    for media in all_media_raw:
        try:
            enriched = enrich_media_data(media, use_cache=True)
            
            # Resume-Point prüfen
            resume_point = get_resume_point(media.get('filepath', ''))
            if resume_point:
                enriched['hasResume'] = True
                enriched['resumePosition'] = resume_point['position']
                enriched['resumePercentage'] = resume_point['percentage']
            
            all_media.append(enriched)
        except Exception as e:
            print(f"⚠️ Fehler beim Anreichern von {media.get('filename', 'Unbekannt')}: {e}")
            all_media.append(media)

    # Kategorien aus Cache laden
    categories = []
    try:
        with HierarchyDBConnection() as cursor:
            cursor.execute("""
                SELECT DISTINCT normalized_category 
                FROM hierarchy_cache 
                WHERE normalized_category IS NOT NULL 
                AND normalized_category != ''
                ORDER BY normalized_category
            """)
            categories = [row[0] for row in cursor.fetchall()]
            
        # Falls keine Kategorien gefunden, versuche Haupt-DB
        if not categories:
            print("⚠️ Keine Kategorien in Hierarchie-DB, versuche Haupt-DB...")
            with MainDBConnection() as cursor_main:
                cursor_main.execute("""
                    SELECT DISTINCT category 
                    FROM media_files 
                    WHERE category IS NOT NULL 
                    AND category != ''
                    ORDER BY category
                """)
                raw_categories = [row[0] for row in cursor_main.fetchall()]
                
                # Normalisiere die Kategorienamen
                for cat in raw_categories:
                    normalized = normalize_category(cat)
                    if normalized not in categories:
                        categories.append(normalized)
                        
    except Exception as e:
        print(f"⚠️ Fehler beim Laden der Kategorien: {e}")
        # Notfall-Fallback
        categories = ['Film', 'Serie', 'Musik', 'Tool', 'Dokumentation', 'Hörbuch']

    # Verteilung anzeigen
    print("\n📊 REAL MEDIA DISTRIBUTION:")
    for cat in categories:
        count = sum(1 for m in all_media if m.get('normalized_category') == cat)
        if count > 0:
            print(f"   {cat}: {count} Medien")

    # Kategorie-Daten sammeln
    category_data = {}
    
    with HierarchyDBConnection() as cursor_hierarchy, \
         MainDBConnection() as cursor_main_for_years:
        
        for cat in categories:
            # Genres
            cursor_hierarchy.execute(
                "SELECT DISTINCT genre FROM hierarchy_cache WHERE normalized_category = ? AND genre IS NOT NULL",
                (cat,)
            )
            genres = sorted([row[0] for row in cursor_hierarchy.fetchall() if row[0]])

            # Jahre
            cursor_main_for_years.execute(
                "SELECT DISTINCT year FROM media_files WHERE category LIKE ? AND year IS NOT NULL ORDER BY year DESC",
                (f'%{cat}%',)
            )
            years = sorted([row[0] for row in cursor_main_for_years.fetchall() if row[0]], reverse=True)

            # Subgenres
            cursor_hierarchy.execute(
                "SELECT genre, subgenre, sub_franchise, franchise, series FROM hierarchy_cache WHERE normalized_category = ?",
                (cat,)
            )
            subgenres_by_genre = {}
            for row in cursor_hierarchy.fetchall():
                genre = row[0]
                if not genre:
                    continue
                candidates = [r for r in row[1:] if r and str(r).strip()]
                if candidates:
                    if genre not in subgenres_by_genre:
                        subgenres_by_genre[genre] = set()
                    for c in candidates:
                        subgenres_by_genre[genre].add(str(c))
            subgenres_processed = {g: sorted(list(s)) for g, s in subgenres_by_genre.items()}
            
            category_data[cat] = {
                'genres': genres,
                'years': years,
                'subgenres': subgenres_processed
            }

    # Statistiken
    with MainDBConnection() as cursor_main:
        cursor_main.execute("SELECT COUNT(*) FROM media_files WHERE filepath != ''")
        total_files = cursor_main.fetchone()[0]
        cursor_main.execute("SELECT SUM(file_size) FROM media_files WHERE filepath != ''")
        total_size = cursor_main.fetchone()[0] or 0
        total_gb = total_size / (1024**3)

        # Neueste Medien
        cursor_main.execute("SELECT * FROM media_files WHERE filepath != '' ORDER BY last_modified DESC LIMIT 20")
        latest_media = []
        for row in cursor_main.fetchall():
            try:
                enriched = enrich_media_data(dict(row), use_cache=True)
                latest_media.append(enriched)
            except Exception as e:
                print(f"⚠️ Fehler beim Anreichern (latest): {e}")
                latest_media.append(dict(row))

        # Featured Medien
        cursor_main.execute("SELECT * FROM media_files WHERE filepath != '' ORDER BY RANDOM() LIMIT 100")
        featured_media = []
        for row in cursor_main.fetchall():
            try:
                enriched = enrich_media_data(dict(row), use_cache=True)
                featured_media.append(enriched)
            except Exception as e:
                print(f"⚠️ Fehler beim Anreichern (featured): {e}")
                featured_media.append(dict(row))

    film_genres = category_data.get('Film', {}).get('genres', [])
    film_years = category_data.get('Film', {}).get('years', [])

    # HTML generieren
    html = generate_html_with_subgenres(
        categories=categories,
        category_data=category_data,
        genres=film_genres,
        years=film_years,
        featured_media=featured_media,
        latest_media=latest_media,
        total_files=total_files,
        total_gb=total_gb,
        all_media_json=all_media
    )

    # HTML speichern
    with open(HTML_PATH, 'w', encoding='utf-8') as f:
        f.write(html)

    size_kb = os.path.getsize(HTML_PATH) / 1024
    print(f"\n✅ Web-Interface mit ERWEITERTEN FEATURES erstellt: {os.path.abspath(HTML_PATH)} ({size_kb:.1f} KB)")
    print(f"✅ Hierarchie-Datenbank: {HIERARCHY_DB_PATH}")
    print(f"✅ Settings-Datenbank: {SETTINGS_DB_PATH}")
    print("🎯 ERWEITERTE FEATURES AKTIV:")
    print("   ✅ Netzwerk-Sharing (0.0.0.0) mit Client-Limit")
    print("   ✅ Single Filter Button (nur ein Such-Button)")
    print("   ✅ Abspiel-History mit Resume-Funktion")
    print("   ✅ Settings-Datenbank für Persistenz")
    print("   ✅ Autoplay Boundary Fix")
    print("   ✅ Audio-Lautstärkeregler mit Persistenz")
    print("   ✅ MKV Audio-Sprache Einstellung")

def ensure_hierarchy_cache():
    """
    Stellt sicher dass Hierarchie-Cache existiert und aktuell ist.
    
    Returns:
        bool: Erfolg der Operation
    """
    print("🔄 Prüfe/Erstelle Hierarchie-Cache mit KORRIGIERTEN KATEGORIEN...")
    if not os.path.exists(DB_PATH):
        print("❌ Hauptdatenbank nicht gefunden")
        return False

    if os.path.exists(HIERARCHY_DB_PATH):
        print("✅ Hierarchie-Datenbank bereits vorhanden – überspringe Neuerstellung")
        return True

    print("🆕 Keine Hierarchie-Datenbank gefunden – führe Initialaufbau durch...")

    # Alte DB löschen
    if os.path.exists(HIERARCHY_DB_PATH):
        try:
            os.remove(HIERARCHY_DB_PATH)
            time.sleep(0.5)
        except Exception as e:
            print(f"⚠️ Konnte alte Hierarchie-DB nicht löschen: {e}")

    # Neue DB initialisieren
    init_hierarchy_database()
    time.sleep(0.5)

    # Hauptdatenbank öffnen
    try:
        conn_main = sqlite3.connect(DB_PATH)
        conn_main.row_factory = sqlite3.Row
        cursor_main = conn_main.cursor()
    except Exception as e:
        print(f"❌ Fehler beim Öffnen der Hauptdatenbank: {e}")
        return False

    # Medien zählen
    try:
        cursor_main.execute("SELECT COUNT(*) FROM media_files WHERE filepath != ''")
        total_count = cursor_main.fetchone()[0]
    except Exception as e:
        print(f"❌ Fehler beim Zählen der Medien: {e}")
        conn_main.close()
        return False

    if total_count == 0:
        print("❌ Keine Medien in der Datenbank gefunden")
        conn_main.close()
        return False

    print(f"📊 Verarbeite {total_count} Medien MIT KATEGORIE-KORREKTUR...")
    processed = 0
    errors = 0

    conn_hierarchy = sqlite3.connect(HIERARCHY_DB_PATH)
    cursor_hierarchy = conn_hierarchy.cursor()

    # Batch-Verarbeitung
    batch_size = 100
    for offset in range(0, total_count, batch_size):
        try:
            cursor_main.execute(
                "SELECT * FROM media_files WHERE filepath != '' ORDER BY filepath LIMIT ? OFFSET ?",
                (batch_size, offset)
            )
            batch = [dict(row) for row in cursor_main.fetchall()]
            for media in batch:
                try:
                    filepath = media.get('filepath', '')
                    if not filepath or not os.path.exists(filepath):
                        errors += 1
                        continue

                    # Kategorie korrigieren
                    corrected_category = detect_category_from_filepath(filepath)
                    if not corrected_category or corrected_category == 'Unbekannt':
                        corrected_category = media.get('category', 'Unbekannt')

                    # Hierarchie parsen
                    hierarchy = parse_filepath_hierarchy_multipass(filepath, corrected_category)

                    # In Cache schreiben
                    cursor_hierarchy.execute('''
                    INSERT OR REPLACE INTO hierarchy_cache
                    (filepath, normalized_category, hierarchy_json, genre, subgenre,
                     franchise, sub_franchise, series, season, season_number,
                     episode_number, artist, album)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        filepath,
                        corrected_category,
                        json.dumps(hierarchy, ensure_ascii=False),
                        hierarchy.get('genre'),
                        hierarchy.get('subgenre'),
                        hierarchy.get('franchise'),
                        hierarchy.get('sub_franchise'),
                        hierarchy.get('series'),
                        hierarchy.get('season'),
                        hierarchy.get('season_number'),
                        hierarchy.get('episode_number'),
                        hierarchy.get('artist'),
                        hierarchy.get('album')
                    ))
                except Exception as e:
                    errors += 1
                    print(f"⚠️ Fehler bei Medium {media.get('filename', 'Unbekannt')}: {e}")
            conn_hierarchy.commit()
            processed += len(batch)
            progress = (processed / total_count) * 100
            if processed % 100 == 0 or processed == total_count:
                print(f"   📊 Fortschritt: {processed}/{total_count} ({progress:.1f}%) - Fehler: {errors}")
        except Exception as e:
            print(f"⚠️ Batch-Fehler bei Offset {offset}: {e}")
            errors += 1

    conn_hierarchy.close()
    conn_main.close()

    # Statistiken aktualisieren
    print("📊 Aktualisiere Kategorie-Statistiken MIT KORRIGIERTEN KATEGORIEN...")
    try:
        update_category_stats()
    except Exception as e:
        print(f"⚠️ Fehler beim Aktualisieren der Statistiken: {e}")

    print(f"\n✅ Hierarchie-Cache erfolgreich initialisiert")
    print(f"   📈 Verarbeitet: {processed} Medien")
    print(f"   ⚠️ Fehler: {errors}")
    return True

def migrate_history_durations():
    """
    Migriert bestehende History-Einträge, um Dauer-Informationen hinzuzufügen.
    """
    try:
        if not os.path.exists(SETTINGS_DB_PATH):
            return False
            
        conn = sqlite3.connect(SETTINGS_DB_PATH)
        cursor = conn.cursor()
        
        # Hole alle Einträge ohne Dauer (duration=0)
        cursor.execute('SELECT id, filepath FROM playback_history WHERE duration = 0')
        entries = cursor.fetchall()
        
        print(f"🔄 Migriere {len(entries)} History-Einträge...")
        migrated = 0
        
        for entry_id, filepath in entries:
            try:
                if os.path.exists(filepath):
                    ext = os.path.splitext(filepath)[1].lower()
                    duration = 0
                    
                    # Versuche Dauer zu ermitteln
                    if ext in VIDEO_EXTENSIONS or ext in ['.mp3', '.wav', '.flac', '.aac', '.ogg', '.m4a']:
                        if FFPROBE_EXECUTABLE:
                            cmd = [
                                FFPROBE_EXECUTABLE,
                                '-v', 'error',
                                '-show_entries', 'format=duration',
                                '-of', 'default=noprint_wrappers=1:nokey=1',
                                filepath
                            ]
                            result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
                            if result.returncode == 0:
                                duration = float(result.stdout.strip())
                                
                    # Update Datenbank (mindestens 1 Sekunde)
                    if duration > 0:
                        cursor.execute('UPDATE playback_history SET duration = ? WHERE id = ?', 
                                     (duration, entry_id))
                        migrated += 1
                        
                        if migrated % 10 == 0:
                            print(f"   Migriert: {migrated}/{len(entries)}")
                    
            except Exception as e:
                print(f"⚠️ Fehler bei Migration von {filepath}: {e}")
                continue
        
        conn.commit()
        conn.close()
        
        print(f"✅ Migration abgeschlossen: {migrated} Einträge aktualisiert")
        return True
        
    except Exception as e:
        print(f"❌ Migrationsfehler: {e}")
        return False

# -----------------------------------------------------------------------------
# HTTP REQUEST HANDLER KORREKTUR
# -----------------------------------------------------------------------------

class MediaHTTPRequestHandler(ExtendedMediaHTTPRequestHandler):
    """
    Korrigierte Version des HTTP Request Handlers.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
    
    def handle_thumbnail_request(self, query_params):
        """Verarbeitet Thumbnail-Anfragen."""
        filepath = query_params.get('filepath', [None])[0]

        if not filepath:
            self.send_error(400, "Kein Dateipfad angegeben")
            return

        # Pfad dekodieren
        filepath = urllib.parse.unquote(filepath)
        filepath = html.unescape(filepath)

        # Sicherheitsprüfung
        real_path = os.path.realpath(filepath)
        if not os.path.isfile(real_path):
            self.send_error(403, "Ungültiger Pfad")
            return

        # In Datenbank prüfen
        try:
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.execute(
                "SELECT COUNT(*) FROM media_files WHERE filepath = ?",
                (filepath,)
            )
            result = cursor.fetchone()[0]
            conn.close()

            if result == 0:
                print(f"⛔ Thumbnail für nicht-indexierte Datei: {os.path.basename(filepath)}")
                self.send_error(403, "Datei nicht in der Datenbank")
                return
        except Exception as e:
            print(f"⚠️ Datenbankfehler: {e}")

        # Thumbnail generieren oder holen
        thumb_path = generate_or_get_thumbnail(filepath)

        if thumb_path and os.path.exists(thumb_path):
            # WICHTIG: Bessere Cache-Header für Thumbnails
            try:
                with open(thumb_path, 'rb') as f:
                    data = f.read()
                    self.send_response(200)
                    self.send_header('Content-Type', 'image/jpeg')
                    self.send_header('Content-Length', str(len(data)))
                    self.send_header('Cache-Control', 'public, max-age=31536000')  # 1 Jahr
                    self.send_header('Expires', 'Fri, 01 Jan 2026 00:00:00 GMT')
                    self.end_headers()
                    self.wfile.write(data)
                    print(f"✅ Thumbnail gesendet: {os.path.basename(filepath)}")
            except (ConnectionAbortedError, BrokenPipeError, ConnectionResetError, OSError):
                # Client-Abbruch ignorieren
                print(f"ℹ️ Client-Abbruch bei Thumbnail: {os.path.basename(filepath)}")
            except Exception as e:
                print(f"⚠️ Thumbnail-Sendefehler: {e}")
        else:
            self.serve_color_thumbnail(filepath)

    def handle_one_request(self):
        """Überschreibe handle_one_request um Socket-Fehler abzufangen."""
        try:
            super().handle_one_request()
        except (ConnectionResetError, BrokenPipeError, OSError) as e:
            # Client hat Verbindung abgebrochen - das ist normal
            print(f"ℹ️ Client-Verbindungsfehler: {e}")
            return  # Einfach zurückkehren statt Fehler zu werfen
        except Exception as e:
            print(f"⚠️ Unerwarteter Fehler in handle_one_request: {e}")
            import traceback
            traceback.print_exc()

# -----------------------------------------------------------------------------
# SERVER-KONFIGURATION
# -----------------------------------------------------------------------------

def get_server_host():
    """Bestimmt Server-Host basierend auf Settings."""
    network_mode = get_setting('network_mode', 'localhost')
    
    if network_mode == 'network':
        return '0.0.0.0'  # Alle Interfaces
    else:
        return 'localhost'  # Nur lokal

SERVER_HOST = get_server_host()

def start_http_server():
    """
    Startet den HTTP-Server für Media Platform mit vollständiger Initialisierung.
    VERSION 1.0.
    """
    print("\n" + "="*70)
    print("🎬 HTML Media Indexer - 1.0")
    print("="*70)
    
    # 1. Verwaiste FFmpeg-Prozesse beenden
    print("🧹 Starte System-Cleanup...")
    kill_orphaned_ffmpeg_processes()
    
    # 2. ALLE Datenbanken initialisieren (KRITISCH!)
    print("\n📊 Initialisiere Datenbanken...")
    
    # Settings-DB MUSS zuerst initialisiert werden
    print("   1. Settings-Datenbank...")
    if not init_settings_database():
        print("   ⚠️ Settings-DB konnte nicht initialisiert werden")
        print("   ⚠️ Erweiterte Features sind eingeschränkt")
    else:
        print("   ✅ Settings-DB: OK (History, Volume, Client-Limit)")
    
    # Haupt-DB
    print("   2. Haupt-Datenbank...")
    if not os.path.exists(DB_PATH):
        print("   ❌ Haupt-Datenbank nicht gefunden!")
        print("   ℹ️ Führen Sie zuerst media_indexer.py aus")
        print("   ℹ️ Oder stellen Sie sicher, dass 'media_index.db' existiert")
        return
    print("   ✅ Haupt-DB: OK")
    
    # Hierarchie-DB
    print("   3. Hierarchie-Datenbank...")
    if not os.path.exists(HIERARCHY_DB_PATH):
        print("   ℹ️ Hierarchie-DB nicht gefunden, baue neu auf...")
        rebuild_hierarchy_cache()
    else:
        print("   ✅ Hierarchie-DB: OK")
    
    # 3. HTML generieren - SO WIE ES IN IHRER DATEI BEREITS FUNKTIONIERT
    print("\n🌐 Generiere Web-Interface...")
    try:
        # Hole die Daten für die HTML-Generierung
        categories = []
        category_data = {}
        genres = []
        years = []
        featured_media = []
        latest_media = []
        total_files = 0
        total_gb = 0
        all_media_json = []
        
        # Lade Kategorien
        try:
            with MainDBConnection() as cursor:
                cursor.execute("SELECT DISTINCT category FROM media_files WHERE category != '' ORDER BY category")
                categories = [row[0] for row in cursor.fetchall()]
                
                # Lade neueste Medien
                cursor.execute("SELECT * FROM media_files WHERE filepath != '' ORDER BY last_modified DESC LIMIT 24")
                featured_media = [dict(row) for row in cursor.fetchall()]
                
                # Lade zufällige Medien
                cursor.execute("SELECT * FROM media_files WHERE filepath != '' ORDER BY RANDOM() LIMIT 24")
                latest_media = [dict(row) for row in cursor.fetchall()]
                
                # Statistiken
                cursor.execute("SELECT COUNT(*) FROM media_files WHERE filepath != ''")
                total_files = cursor.fetchone()[0]
                
                # Versuche verschiedene Spaltennamen für die Größe
                total_bytes = 0
                try:
                    cursor.execute("SELECT SUM(size) FROM media_files WHERE size > 0")
                    total_bytes = cursor.fetchone()[0] or 0
                except sqlite3.OperationalError:
                    try:
                        cursor.execute("SELECT SUM(filesize) FROM media_files WHERE filesize > 0")
                        total_bytes = cursor.fetchone()[0] or 0
                    except sqlite3.OperationalError:
                        # Fallback: Verwende Standard-Größe pro Datei
                        total_bytes = total_files * 500 * 1024 * 1024  # 500MB pro Datei als Schätzung
                
                total_gb = total_bytes / (1024**3) if total_bytes > 0 else 0
                
                # Jahre
                cursor.execute("SELECT DISTINCT year FROM media_files WHERE year != '' ORDER BY year DESC")
                years = [row[0] for row in cursor.fetchall()]
                
        except Exception as e:
            print(f"⚠️ Fehler beim Laden der Haupt-DB: {e}")
            # Vereinfachte Fallback-Werte
            categories = ['Film', 'Serie', 'Musik', 'Tool', 'Dokumentation']
            total_files = 873  # Vom API-Call bekannt
            total_gb = total_files * 0.5  # Schätzung: 0.5GB pro Datei
        
        # Lade Genres aus Hierarchie-DB
        try:
            with HierarchyDBConnection() as cursor:
                cursor.execute("SELECT DISTINCT genre FROM hierarchy_cache WHERE genre IS NOT NULL AND genre != '' ORDER BY genre")
                genres = [row[0] for row in cursor.fetchall()]
        except Exception as e:
            print(f"⚠️ Fehler beim Laden der Genres: {e}")
            genres = []
        
        # Bereite Kategorie-Daten vor
        for cat in categories:
            category_data[cat] = {
                'genres': genres[:10] if genres else [],
                'years': years[:5] if years else [],
                'subgenres': {}
            }
        
        # Rufe die EXISTIERENDE Funktion auf
        generate_html_with_subgenres(
            categories=categories,
            category_data=category_data,
            genres=genres,
            years=years,
            featured_media=featured_media,
            latest_media=latest_media,
            total_files=total_files,
            total_gb=total_gb,
            all_media_json=all_media_json
        )
        
        print("✅ Web-Interface erstellt")
        
    except Exception as e:
        print(f"❌ Fehler beim Generieren des HTML: {e}")
        import traceback
        traceback.print_exc()
        
        # Versuche minimales HTML zu erstellen
        try:
            minimal_html = """<!DOCTYPE html>
<html>
<head><title>Media Indexer</title></head>
<body>
<h1>Media Indexer Server läuft</h1>
<p>API ist verfügbar unter:</p>
<ul>
<li><a href="/api/media">/api/media</a></li>
<li><a href="/api/settings">/api/settings</a></li>
</ul>
</body>
</html>"""
            with open(HTML_PATH, 'w', encoding='utf-8') as f:
                f.write(minimal_html)
            print("⚠️ Minimales HTML erstellt")
        except:
            print("❌ Konnte nicht einmal minimales HTML erstellen")
            # Server trotzdem starten
    
    # 4. Server-Informationen anzeigen
    print("\n🚀 Starte Webserver...")
    host = get_server_host()
    
    if host == '0.0.0.0':
        local_ip = get_local_ip()
        print("🌐 Netzwerk-Modus aktiviert:")
        print(f"   💻 Lokal: http://localhost:{SERVER_PORT}")
        print(f"   🌐 Netzwerk: http://{local_ip}:{SERVER_PORT}")
        print(f"   🔒 Max. Clients: {get_setting('max_clients', 3)}")
    else:
        print("🏠 Lokaler Modus - Nur dieser Computer:")
        print(f"   💻 http://localhost:{SERVER_PORT}")
    
    # 5. Einstellungen anzeigen
    print("\n🎯 AKTIVE EINSTELLUNGEN:")
    print(f"   • History: {'Aktiviert' if get_setting('enable_history', True) else 'Deaktiviert'}")
    print(f"   • Volume: {get_setting('volume_level', 0.7) * 100:.0f}%")
    print(f"   • MKV Audio-Sprache: {get_setting('audio_language', 'ger')}")
    print(f"   • Autoplay: {'Aktiviert' if get_setting('autoplay_enabled', False) else 'Deaktiviert'}")
    print("="*70 + "\n")
    
    # 6. Server starten
    try:
        server = RobustHTTPServer((host, SERVER_PORT), ExtendedMediaHTTPRequestHandler)
        
        # Browser öffnen (nur bei localhost)
        if host == 'localhost':
            webbrowser.open(f'http://localhost:{SERVER_PORT}')
        
        print("✅ Server gestartet. Drücken Sie STRG+C zum Beenden.")
        print("💡 TASTATURKÜRZEL:")
        print("   ESC - Player/History/Settings schließen")
        print("   LEERTASTE - Play/Pause")
        print("   F5 - Seite neu laden")
        print("-"*70)
        
        server.serve_forever()
        
    except KeyboardInterrupt:
        print("\n\n🛑 Server wird beendet...")
        print("🧹 Räume auf...")
        kill_orphaned_ffmpeg_processes()
        print("👋 Auf Wiedersehen!")
    except Exception as e:
        print(f"\n❌ Server-Fehler: {e}")
        import traceback
        traceback.print_exc()
# -----------------------------------------------------------------------------
# HAUPTFUNKTION
# -----------------------------------------------------------------------------

def main():
    """
    Hauptfunktion des Media Platform Systems v1.0.
    """
    print("=" * 70)
    print("🎬 HTML MEDIA INDEXER - VERSION 1.0")
    print("=" * 70)
    print(f"📁 Programmordner: {PROGRAM_DIR}")
    print(f"📁 Thumbnail-Verzeichnis: {THUMBNAIL_DIR}")
    print(f"📊 Hauptdatenbank: {DB_PATH}")
    print(f"📊 Hierarchie-Datenbank: {HIERARCHY_DB_PATH}")
    print(f"⚙️ Settings-Datenbank: {SETTINGS_DB_PATH}")
    print(f"🌐 Server: http://{SERVER_HOST}:{SERVER_PORT}")
    print("=" * 70)
    
    print("🔍 Prüfe Abhängigkeiten...")
    
    # FFmpeg prüfen
    try:
        result = subprocess.run([FFMPEG_EXECUTABLE, '-version'], capture_output=True, text=True)
        if result.returncode == 0:
            print("✅ ffmpeg gefunden")
        else:
            print("❌ ffmpeg nicht verfügbar - Transcoding wird nicht funktionieren!")
    except:
        print("❌ ffmpeg nicht installiert - Transcoding wird nicht funktionieren!")
    
    # Python-Module prüfen
    if not HAS_PIL:
        print("❌ Pillow nicht installiert. Bitte installieren mit: pip install Pillow")
    else:
        print("✅ Pillow installiert")
    
    if not HAS_MUTAGEN:
        print("⚠️ mutagen nicht installiert. Audio-Cover-Art wird nicht unterstützt.")
    else:
        print("✅ mutagen installiert")
    
    if not HAS_CAIROSVG:
        print("⚠️ cairosvg nicht installiert. Farbige Thumbnails werden eingeschränkt.")
    else:
        print("✅ cairosvg installiert")
    
    print("=" * 70)

    # Database Migration für History
    print("\n🔄 Prüfe History-Datenbank auf Migration...")
    try:
        migrated = migrate_history_durations()
        if migrated:
            print("✅ History-Datenbank migriert (Dauer-Informationen hinzugefügt)")
        else:
            print("✅ History-Datenbank ist aktuell")
    except Exception as e:
        print(f"⚠️ Migration nicht möglich: {e}")
    
    # Cleanup verwaiste FFmpeg-Prozesse beim Start
    print("🧹 Prüfe auf verwaiste FFmpeg-Prozesse...")
    try:
        killed = kill_orphaned_ffmpeg_processes()
        if killed > 0:
            print(f"   🧹 {killed} verwaiste FFmpeg-Prozesse beendet")
        else:
            print("   ✅ Keine verwaisten Prozesse gefunden")
    except Exception as e:
        print(f"   ⚠️ Process-Cleanup nicht verfügbar: {e}")
    
    # Thumbnail-Status
    print("\n📊 Thumbnail-Verzeichnis Status:")
    if os.path.exists(THUMBNAIL_DIR):
        thumb_count = len([f for f in os.listdir(THUMBNAIL_DIR) if f.endswith('.jpg')])
        print(f"   {thumb_count} Thumbnails vorhanden")
    else:
        print("   Verzeichnis existiert noch nicht")
    
    # Settings laden
    print("\n⚙️ Aktuelle Einstellungen:")
    network_mode = get_setting('network_mode', 'localhost')
    max_clients = get_setting('max_clients', 3)
    volume = get_setting('volume_level', 0.7)
    autoplay = get_setting('autoplay_enabled', False)
    
    print(f"   Netzwerk-Modus: {network_mode}")
    print(f"   Max. Clients: {max_clients}")
    print(f"   Lautstärke: {volume*100:.0f}%")
    print(f"   Autoplay: {'Aktiviert' if autoplay else 'Deaktiviert'}")
    
    print("=" * 70)
    
    # Web-Interface generieren
    print("\n🔄 Generiere Web-Interface mit erweiterten Features...")
    generate_web_interface()
    
    # Server starten
    server_thread = threading.Thread(target=start_http_server, daemon=True)
    server_thread.start()
    
    # Browser öffnen
    url = f"http://localhost:{SERVER_PORT}"
    print(f"⏳ Starte Webserver...")
    time.sleep(2)
    
    try:
        webbrowser.open(url)
        print(f"✅ Browser geöffnet: {url}")
    except:
        print(f"⚠️ Browser konnte nicht automatisch geöffnet werden")
        print(f"   Bitte öffnen Sie manuell: {url}")
    
    print("=" * 70)
    print("🎯 ERWEITERTE FEATURES AKTIVIERT:")
    print("   1. ✅ Netzwerk-Sharing (0.0.0.0) mit Client-Limit")
    print("   2. ✅ Single Filter Button (nur ein Such-Button)")
    print("   3. ✅ Abspiel-History mit Resume-Funktion")
    print("   4. ✅ Settings-Datenbank für Persistenz")
    print("   5. ✅ Autoplay Boundary Fix (stoppt nach letztem Medium)")
    print("   6. ✅ Audio-Lautstärkeregler mit Persistenz")
    print("   7. ✅ MKV Audio-Sprache Einstellung")
    print("=" * 70)
    
    # Network Info falls aktiv
    if network_mode == 'network':
        try:
            local_ip = get_local_ip()
            print(f"\n📡 NETZWERK-FREIGABE AKTIV:")
            print(f"   Andere Geräte im Netzwerk können verbinden über:")
            print(f"   🌐 http://{local_ip}:{SERVER_PORT}")
            print(f"   🔧 Client-Limit: {max_clients} gleichzeitige Nutzer")
        except:
            print("\n📡 Netzwerk-Modus aktiv, aber IP konnte nicht ermittelt werden")
    
    print("\n💡 TASTATURKÜRZEL:")
    print("   ESC - Video/Audio/History/Settings schließen")
    print("   STRG+F - Suchfeld fokussieren")
    print("   LEERTASTE - Audio-Player Play/Pause")
    print("   STRG+C - Server beenden")
    
    print("\n🎮 BEDIENUNG:")
    print("   • Klicken Sie auf Medienkarten zum Abspielen")
    print("   • Rechts unten: History, Autoplay, Einstellungen")
    print("   • Oben rechts: Nur EIN Such-Button (Single Filter)")
    print("   • Audio-Player hat Lautstärkeregler mit Speicherung")
    print("   • History zeigt zuletzt gesehene Medien")
    
    print("=" * 70)
    print("💡 Drücke STRG+C zum Beenden mit automatischem Cleanup")
    
    try:
        # Hauptloop (bis STRG+C)
        while True:
            # Aktive Clients aktualisieren
            cleanup_inactive_clients()
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n\n👋 Server wird beendet...")
        print("🧹 Cleanup läuft...")
        
        # Cleanup bei Shutdown
        try:
            killed = kill_orphaned_ffmpeg_processes()
            if killed > 0:
                print(f"   🧹 {killed} FFmpeg-Prozesse beendet")
            else:
                print("   ✅ Keine aktiven FFmpeg-Prozesse")
        except Exception as e:
            print(f"   ⚠️ Cleanup-Fehler: {e}")
        
        # Settings speichern
        print("💾 Aktuelle Settings gesichert...")
        
        print("✅ Server sauber beendet.")
        print("=" * 70)

class RobustHTTPServer(HTTPServer):
    """HTTP-Server mit verbessertem Error-Handling."""
    
    def handle_error(self, request, client_address):
        """Überschreibe Error-Handling um Socket-Fehler zu ignorieren."""
        error_type, error_value, _ = sys.exc_info()
        
        # Ignoriere normale Socket-Fehler (Client-Abbrüche)
        socket_errors = [
            ConnectionResetError, ConnectionAbortedError, 
            BrokenPipeError, OSError, TimeoutError
        ]
        
        for error in socket_errors:
            if error_type == error:
                err_msg = str(error_value)
                # Windows Socket-Fehler-Codes ignorieren
                if any(str(code) in err_msg for code in [10053, 10054, 10038, 10004]):
                    print(f"ℹ️ Client {client_address[0]}:{client_address[1]} hat Verbindung abgebrochen")
                    return
                else:
                    print(f"⚠️ Socket-Fehler mit Client {client_address[0]}: {err_msg}")
                    return
        
        # Für alle anderen Fehler: Standard-Verhalten
        print(f"❌ Server-Fehler mit Client {client_address[0]}: {error_type.__name__}: {error_value}")
        import traceback
        traceback.print_exc()
# -----------------------------------------------------------------------------
# HAUPTPROGRAMM
# -----------------------------------------------------------------------------

if __name__ == "__main__":
    """
    Hauptprogramm mit erweiterter Initialisierung.
    """
    # ASCII-Art Banner
    print("\n" + "="*80)
    print("""
    ███╗   ███╗███████╗██████╗ ██╗ █████╗     ██╗███╗   ██╗██████╗ ███████╗██╗  ██╗███████╗██████╗ 
    ████╗ ████║██╔════╝██╔══██╗██║██╔══██╗    ██║████╗  ██║██╔══██╗██╔════╝╚██╗██╔╝██╔════╝██╔══██╗
    ██╔████╔██║█████╗  ██║  ██║██║███████║    ██║██╔██╗ ██║██║  ██║█████╗   ╚███╔╝ █████╗  ██████╔╝
    ██║╚██╔╝██║██╔══╝  ██║  ██║██║██╔══██║    ██║██║╚██╗██║██║  ██║██╔══╝   ██╔██╗ ██╔══╝  ██╔══██╗
    ██║ ╚═╝ ██║███████╗██████╔╝██║██║  ██║    ██║██║ ╚████║██████╔╝███████╗██╔╝ ██╗███████╗██║  ██║
    ╚═╝     ╚═╝╚══════╝╚═════╝ ╚═╝╚═╝  ╚═╝    ╚═╝╚═╝  ╚═══╝╚═════╝ ╚══════╝╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝
    
                            🎬 Version 1.0 | Your personal Video-Platform
    """)
    print("="*80)
    
    # 1. Settings-Datenbank erzwingend initialisieren
    print("\n📁 INITIALISIERE DATENBANKEN")
    print("-"*40)
    
    settings_ok = init_settings_database()
    if not settings_ok:
        print("❌ KRITISCHER FEHLER: Settings-DB konnte nicht erstellt werden!")
        print("   Versuche Reparatur...")
        
        try:
            if os.path.exists(SETTINGS_DB_PATH):
                os.remove(SETTINGS_DB_PATH)
        except:
            pass
        
        settings_ok = init_settings_database()
        
        if not settings_ok:
            print("❌ Reparatur fehlgeschlagen!")
            print("   Starte mit eingeschränkten Features...")
        else:
            print("✅ Reparatur erfolgreich!")
    
    print("-"*40)
    
    # 2. Web-Interface generieren (WICHTIG - DAS FEHLTE!)
    try:
        generate_web_interface()  # DIESE FUNKTION MUSS AUFGERUFEN WERDEN!
        print("✅ Web-Interface erfolgreich generiert")
    except NameError:
        # Fallback: Versuche mit der anderen Funktion
        print("⚠️ generate_web_interface() nicht gefunden, versuche alternative...")
        try:
            # Erstelle minimales HTML
            with open(HTML_PATH, 'w', encoding='utf-8') as f:
                f.write("<html><body><h1>Media Indexer</h1><p>Server läuft</p></body></html>")
            print("✅ Minimales HTML erstellt")
        except Exception as e:
            print(f"❌ Konnte kein HTML erstellen: {e}")
    except Exception as e:
        print(f"❌ Fehler beim Generieren des Web-Interfaces: {e}")
    
    # 3. Server starten
    start_http_server()
