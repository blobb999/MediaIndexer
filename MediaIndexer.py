# -*- coding: utf-8 -*-
import os
import re
import json
import shutil
import threading
import subprocess
import configparser
import textwrap
import urllib.request
import zipfile
from io import BytesIO
from pathlib import Path
import concurrent.futures
import sqlite3
from collections import Counter, defaultdict
from functools import lru_cache
import weakref
import hashlib
from datetime import datetime

# Encoding-Fix für Umlaute
import sys

# Matplotlib nur importieren wenn verfügbar
try:
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    matplotlib_available = True
except ImportError:
    matplotlib_available = False
    print("Matplotlib nicht verfügbar - Diagramm-Features deaktiviert")

# Extern
from PIL import Image, ImageTk
from mutagen.mp3 import MP3
from mutagen.id3 import ID3, APIC
import winsound
import pyttsx3
from ttkthemes import ThemedStyle

# Tkinter
import tkinter as tk
from tkinter import filedialog, messagebox
import tkinter.font as tkFont
import tkinter.ttk as ttk

# Bin-Verzeichnis erstellen, falls nicht vorhanden
bin_dir = os.path.join(os.getcwd(), "bin")
if not os.path.exists(bin_dir):
    os.makedirs(bin_dir)

# Globale Tooltip-Registry für Cleanup
_active_tooltips = weakref.WeakSet()

class Tooltip(tk.Toplevel):
    def __init__(self, widget, metadata, image=None, image_size=(300, 450), font_size=12):
        super().__init__(widget)
        self.overrideredirect(True)
        self.configure(background='lightyellow')
        self.widget = widget
        self.metadata = metadata
        self.image = image
        self.image_size = image_size
        
        # Registriere im globalen Set
        _active_tooltips.add(self)

        default_font = tkFont.Font(size=font_size)
        bold_font = tkFont.Font(size=font_size, weight="bold")

        container = tk.Frame(self, bg='lightyellow', padx=10, pady=10, relief='solid', bd=1)
        container.pack()

        self.max_tooltip_width = 400

        if self.image:
            try:
                image = self.image.resize(self.image_size, Image.LANCZOS)
                photo = ImageTk.PhotoImage(image)
                image_label = tk.Label(container, image=photo, bg='lightyellow')
                image_label.image = photo
                image_label.pack(pady=(0, 10))
            except Exception as e:
                print(f"Fehler beim Laden des Bildes: {e}")

        metadata_dict = self.parse_metadata(self.metadata)

        if "Schauspieler" in metadata_dict:
            actors = metadata_dict["Schauspieler"].split(", ")
            unique_actors = ", ".join(sorted(set(actors), key=actors.index))
            metadata_dict["Schauspieler"] = unique_actors

        allowed_titles = {"Filmtitel", "Titel", "Jahr", "Kommentar", "Album", "Interpret", "Filmlänge", "Genre", "Schauspieler", "Inhalt"}

        for label, value in metadata_dict.items():
            if not value:
                continue

            row_frame = tk.Frame(container, bg='lightyellow')
            row_frame.pack(anchor='w', fill='x', padx=5, pady=2)

            font = bold_font if label in allowed_titles else default_font
            label_widget = tk.Label(row_frame, text=label + ":", font=font, bg='lightyellow', anchor='nw')
            label_widget.pack(side='left', anchor='nw')

            wrap_length = self.max_tooltip_width - 20 if label == "Inhalt" else self.max_tooltip_width - 50
            value_widget = tk.Label(
                row_frame,
                text=value,
                font=default_font,
                bg='lightyellow',
                anchor='nw',
                wraplength=wrap_length,
                justify='left'
            )
            value_widget.pack(side='left', anchor='nw')

    def parse_metadata(self, metadata_text):
        metadata_dict = {}
        for line in metadata_text.splitlines():
            if ":" in line:
                label, value = line.split(":", 1)
                metadata_dict[label.strip()] = value.strip()
        return metadata_dict

    def show(self, x, y):
        self.update_idletasks()

        tooltip_width = self.winfo_width()
        tooltip_height = self.winfo_height()

        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()

        preferred_x = x + 20
        preferred_y = y + 20

        if preferred_x + tooltip_width > screen_width:
            preferred_x = x - tooltip_width - 20
        if preferred_y + tooltip_height > screen_height:
            preferred_y = y - tooltip_height - 20

        preferred_x = max(0, min(preferred_x, screen_width - tooltip_width))
        preferred_y = max(0, min(preferred_y, screen_height - tooltip_height))

        self.geometry(f"+{preferred_x}+{preferred_y}")
        self.deiconify()
        self.lift()

    def hide(self):
        self.destroy()

# Hauptfenster und Konfiguration
root = tk.Tk()
root.title("Media Indexer and Player")
root._shutting_down = False

style = ThemedStyle(root)
style.set_theme('arc')

folder_path = ''
config = configparser.ConfigParser()

bin_dir = os.path.join(os.getcwd(), 'bin')
ffmpeg_path = os.path.join(bin_dir, 'ffmpeg.exe')
ffprobe_path = os.path.join(bin_dir, 'ffprobe.exe')

search_active = False
current_search_results = []

# Initialisieren der Variablen
use_db_var = tk.BooleanVar()
title_search_var = tk.BooleanVar()
genre_var = tk.BooleanVar()
actors_var = tk.BooleanVar()
comment_var = tk.BooleanVar()
album_search_var = tk.BooleanVar()
interpret_search_var = tk.BooleanVar()

# Checkbox-Referenzen initialisieren
title_checkbox = None
genre_checkbox = None
actors_checkbox = None
comment_checkbox = None
album_checkbox = None
interpret_checkbox = None

settings_window = None
resize_after_id = None
current_scroll_handler = None
scroll_active = False
analytics_window = None
last_scroll_time = 0

def normalize_file_path(file_path):
    """
    ÜBERPRÜFT: Zentrale Pfad-Normalisierung konsistent verwenden
    """
    # os.path.normpath konvertiert bereits / zu \ auf Windows
    normalized = os.path.normpath(file_path)
    print(f"Normalisiere: {file_path} → {normalized}")  # Debug
    return normalized

def check_ffmpeg_and_ffprobe():
    def show_ffmpeg_error():
        def open_ffmpeg_download(event):
            import webbrowser
            webbrowser.open_new("https://ffmpeg.org/download.html")

        def download_and_install_ffmpeg():
            url = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
            download_path = os.path.join(os.getcwd(), "ffmpeg-release-essentials.zip")
            install_path = os.path.join(os.getcwd(), "ffmpeg")

            try:
                print("Lade FFmpeg herunter...")
                urllib.request.urlretrieve(url, download_path)

                print("Entpacke FFmpeg...")
                with zipfile.ZipFile(download_path, 'r') as zip_ref:
                    zip_ref.extractall(install_path)

                ffmpeg_bin_path = None
                for root_dir, dirs, files in os.walk(install_path):
                    if 'ffmpeg.exe' in files and 'ffprobe.exe' in files:
                        ffmpeg_bin_path = root_dir
                        break

                if ffmpeg_bin_path:
                    print("Installiere FFmpeg...")
                    shutil.move(os.path.join(ffmpeg_bin_path, 'ffmpeg.exe'), os.path.join(bin_dir, 'ffmpeg.exe'))
                    shutil.move(os.path.join(ffmpeg_bin_path, 'ffprobe.exe'), os.path.join(bin_dir, 'ffprobe.exe'))

                print("Bereinige temporäre Dateien...")
                os.remove(download_path)
                shutil.rmtree(install_path)

                messagebox.showinfo("FFmpeg Installation", "FFmpeg wurde erfolgreich installiert.\nDie Anwendung wird neu gestartet.")
                
                python_exe = sys.executable
                os.execl(python_exe, python_exe, *sys.argv)

            except Exception as e:
                messagebox.showerror("FFmpeg Download Fehler", f"Fehler beim Herunterladen von FFmpeg:\n{e}")

        error_window = tk.Toplevel(root)
        error_window.title("FFmpeg Nicht Gefunden")
        error_window.geometry("450x180")
        error_window.transient(root)
        error_window.grab_set()
        
        # Zentrieren
        error_window.geometry("+%d+%d" % (root.winfo_rootx() + 50, root.winfo_rooty() + 50))

        message = tk.Label(error_window, text="FFmpeg und FFprobe wurden nicht gefunden.\nDiese werden für Video-Metadaten benötigt.")
        message.pack(pady=10)

        link = tk.Label(error_window, text="https://ffmpeg.org/download.html", fg="blue", cursor="hand2")
        link.pack(pady=5)
        link.bind("<Button-1>", open_ffmpeg_download)

        button_frame = tk.Frame(error_window)
        button_frame.pack(pady=10)

        install_button = tk.Button(button_frame, text="Automatisch Installieren", command=download_and_install_ffmpeg, bg='lightgreen')
        install_button.pack(side='left', padx=5)
        
        skip_button = tk.Button(button_frame, text="Trotzdem Fortfahren", command=error_window.destroy, bg='lightcoral')
        skip_button.pack(side='left', padx=5)

        error_window.protocol("WM_DELETE_WINDOW", error_window.destroy)
        
        # Fenster sichtbar machen
        error_window.lift()
        error_window.attributes('-topmost', True)
        error_window.focus_force()
    try:
        ffmpeg_path_local = os.path.join(bin_dir, "ffmpeg.exe")
        ffprobe_path_local = os.path.join(bin_dir, "ffprobe.exe")

        if not os.path.exists(ffmpeg_path_local) or not os.path.exists(ffprobe_path_local):
            show_ffmpeg_error()
            return False  # Jetzt wird dieser Code erreicht

        # Test ob FFmpeg funktioniert
        ffmpeg_result = subprocess.run([ffmpeg_path_local, "-version"], 
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=10)
        ffprobe_result = subprocess.run([ffprobe_path_local, "-version"], 
                                      stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=10)

        if ffmpeg_result.returncode != 0 or ffprobe_result.returncode != 0:
            show_ffmpeg_error()
            return False

        print("FFmpeg und FFprobe erfolgreich initialisiert.")
        return True

    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        print(f"FFmpeg-Test fehlgeschlagen: {e}")
        show_ffmpeg_error()
        return False
    except Exception as e:
        print(f"Unerwarteter FFmpeg-Fehler: {e}")
        show_ffmpeg_error()
        return False

# Genre-Normalisierungs-Dictionary (ERWEITERT mit mehr Varianten)
GENRE_NORMALIZATION_MAP = {
    # Groß-/Kleinschreibung
    'TECHNO': 'Techno', 'techno': 'Techno',
    'TRANCE': 'Trance', 'trance': 'Trance',
    'HOUSE': 'House', 'house': 'House',
    'POP': 'Pop', 'pop': 'Pop',
    'ROCK': 'Rock', 'rock': 'Rock',
    'OLDIES': 'Oldies', 'oldies': 'Oldies',
    'LATIN': 'Latin', 'latin': 'Latin',
    'GOA': 'Goa', 'goa': 'Goa',
    'JAZZ': 'Jazz', 'jazz': 'Jazz',
    'BLUES': 'Blues', 'blues': 'Blues',
    'CLASSICAL': 'Classical', 'classical': 'Classical',
    'SOUNDTRACK': 'Soundtrack', 'soundtrack': 'Soundtrack',
    'RAP': 'Rap', 'rap': 'Rap',
    'NEWAGE': 'New Age', 'newage': 'New Age',
    'METAL': 'Metal', 'metal': 'Metal',
    'PUNK': 'Punk', 'punk': 'Punk',
    
    # Varianten zusammenführen
    'Hip Hop': 'Hip-Hop', 'HipHop': 'Hip-Hop', 'hip hop': 'Hip-Hop',
    'Drum & Bass': 'Drum & Bass', 'Drum and Bass': 'Drum & Bass',
    'DnB': 'Drum & Bass', 'D&B': 'Drum & Bass',
    'Sound Track': 'Soundtrack', 'Film Score': 'Soundtrack',
    'Films/Games; Film Scores': 'Soundtrack',
    'Rock & Roll': 'Rock & Roll', 'Rock and Roll': 'Rock & Roll',
    'Classic Rock': 'Rock', 'Progressive Rock': 'Rock',
    'General Rock': 'Rock', 'Hard Rock': 'Rock',
    'Synthpop': 'Synth Pop', 'Synth-Pop': 'Synth Pop',
    'Trip-Hop': 'Trip Hop', 'Trip Hop': 'Trip Hop',
    'Gangsta Rap': 'Rap', 'Gangsta': 'Rap',
    'General New Age': 'New Age',
    'Pop-Folk': 'Folk', 'Folk-Pop': 'Folk',
    'Electro': 'Electronic', 'Electronica': 'Electronic',
    'Dance': 'Dance', 'EDM': 'Electronic',
    
    # Mehrdeutige/Unspezifische entfernen
    'genre': 'Unknown', 'Genre': 'Unknown',
    'misc': 'Other', 'Misc': 'Other', 'Miscellaneous': 'Other',
    'default': 'Unknown', 'Default': 'Unknown',
    'Unbekannt': 'Unknown', 'unbekannt': 'Unknown',
    'various': 'Other', 'Various': 'Other',
    'andere': 'Other', 'Andere': 'Other',
    
    # Tippfehler/Schreibvarianten
    'Psychadelic': 'Psychedelic', 'psychadelic': 'Psychedelic',
    'Humour': 'Comedy', 'humour': 'Comedy',
    'Terror': 'Horror', 'terror': 'Horror',
    "60's": 'Oldies', "70's": 'Oldies', "80's": '80s', "90's": '90s',
    'Patty': 'Party', 'patty': 'Party',
}

# Genres die entfernt werden sollen (zu unspezifisch)
GENRES_TO_REMOVE = {
    'Other', 'Unknown', 'Unbekannt', 'misc', 'default', 
    'genre', 'Genre', 'various', 'andere', 'Andere',
    '', ' ', 'N/A', 'n/a', 'null', 'NULL'
}

def normalize_genre(genre):
    """
    Normalisiert ein Genre nach Regeln
    
    KORRIGIERT: Bessere Leerstring-Behandlung
    
    Returns: Normalisiertes Genre oder None wenn entfernt werden soll
    """
    if not genre or not isinstance(genre, str):
        return None
    
    # Trim Whitespace
    genre = genre.strip()
    
    # Leere/ungültige Genres
    if not genre or genre in GENRES_TO_REMOVE:
        return None
    
    # Prüfe Mapping
    if genre in GENRE_NORMALIZATION_MAP:
        normalized = GENRE_NORMALIZATION_MAP[genre]
        
        # Entfernen wenn in Blacklist
        if normalized in GENRES_TO_REMOVE:
            return None
        
        return normalized
    
    # Komma-separierte Genres: Nimm ersten Eintrag
    if ',' in genre:
        genre = genre.split(',')[0].strip()
        if not genre or genre in GENRES_TO_REMOVE:
            return None
    
    # Semicolon-separierte Genres
    if ';' in genre:
        genre = genre.split(';')[0].strip()
        if not genre or genre in GENRES_TO_REMOVE:
            return None
    
    # Standard: Behalte original Schreibweise (aber trimmed)
    return genre

# Bekannte Genre-Liste (erweiterbar)
KNOWN_GENRES = {
    "action", "action epic", "adult animation", "adventure", "adventure epic", "alien invasion",
    "alien-invasion", "animal adventure", "anime", "artificial intelligence", "aktion episch",
    "aktion im auto", "basketball", "b-action", "b-horror", "biography", "body horror", "bollywood",
    "boxing", "buddy comedy", "buddy cop", "bumbling detective", "caper", "car action",
    "classical western", "classic musical", "comedy", "comedy family", "comedy musical",
    "coming-of-age", "computer animation", "conspiracy thriller", "contemporary western",
    "cop drama", "costume drama", "crime", "crime documentary", "crime drama", "crime thriller",
    "cyber thriller", "cyberpunk", "dark comedy", "dark fantasy", "dark romance",
    "desert adventure", "disaster", "docudrama", "documentary", "dokumentation", "doku", "drama",
    "drama family", "drama fantasy", "drama horror", "drama music", "drama mystery",
    "drama romance", "drama sci-fi", "drama thriller", "drama war", "drug crime",
    "dystopian sci-fi", "epic", "epical", "erotik", "erotic thriller", "extreme sport",
    "fairy tale", "family", "fantasy", "fantasy epic", "farce", "feel-good romance",
    "film-noir", "filme", "folk horror", "found footage horror", "game show",
    "globetrotting adventure", "gun fu", "hand-drawn animation", "heist", "high-concept comedy",
    "historical epic", "history", "holiday", "holiday comedy", "holiday family",
    "holiday romance", "horror", "horror sci-fi", "iyashikei", "kaiju", "kinderfilme",
    "klassischer western", "komödie", "krimi", "kriminalität", "kung fu", "legal drama",
    "martial arts", "medical drama", "monster horror", "mountain adventure", "motorsport",
    "music", "musical", "mystery", "neu", "news", "one-person army action", "parody",
    "period drama", "police procedural", "pop musical", "prison drama", "psychological drama",
    "psychological horror", "psychological thriller", "quest", "quirky comedy",
    "raunchy comedy", "reality tv", "reality-tv", "road trip", "romance", "romantic comedy",
    "samurai", "satire", "sci-fi", "sci-fi epic", "science-fiction", "screwball comedy",
    "sea adventure", "serial killer", "serien", "showbiz drama", "short", "sketch comedy",
    "slasher horror", "slapstick", "space sci-fi", "splatter horror", "sport", "spy",
    "steampunk", "steamy romance", "stoner comedy", "superhero", "supernatural fantasy",
    "supernatural horror", "survival", "suspense mystery", "swashbuckler", "sword & sandal",
    "sword & sorcery", "talk show", "talk-show", "teen adventure", "teen comedy",
    "teen drama", "teen fantasy", "teen horror", "teen romance", "tierfilme", "time travel",
    "tragedy", "tragic romance", "true crime", "urban adventure", "vampire horror", "war",
    "war epic", "western", "western epic", "whodunnit", "witch horror", "workplace drama",
    "wuxia", "zeichentrick", "zombie horror", "zombie-horror", "übernatürlicher horror", "acid"
}


def normalize_all_genres_in_database():
    """
    Normalisiert alle Genres in der Datenbank - THREAD-SAFE VERSION
    
    Zeigt Vorschau und fragt nach Bestätigung
    """
    try:
        # KRITISCH: Verbindung im Haupt-Thread erstellen
        conn = sqlite3.connect('media_index.db')
        cursor = conn.cursor()
        
        # Sammle alle Genres und ihre Häufigkeit
        cursor.execute("""
            SELECT genre, COUNT(*) as count
            FROM media_files
            WHERE genre != '' AND genre IS NOT NULL
            GROUP BY genre
            ORDER BY count DESC
        """)
        
        all_genres = cursor.fetchall()
        
        if not all_genres:
            messagebox.showinfo("Keine Genres", "Keine Genres in der Datenbank gefunden.")
            conn.close()
            return
        
        # Analysiere was geändert werden würde
        changes = {}
        removed_count = 0
        unchanged_count = 0
        
        for genre, count in all_genres:
            normalized = normalize_genre(genre)
            
            if normalized is None:
                removed_count += count
            elif normalized != genre:
                if normalized not in changes:
                    changes[normalized] = []
                changes[normalized].append((genre, count))
            else:
                unchanged_count += count
        
        # WICHTIG: Schließe Connection vor GUI-Operationen
        conn.close()
        
        # Erstelle Vorschau (identisch wie vorher)
        preview_text = "GENRE-NORMALISIERUNG VORSCHAU\n"
        preview_text += "="*60 + "\n\n"
        
        if changes:
            preview_text += "ÄNDERUNGEN:\n"
            preview_text += "-"*60 + "\n"
            
            for normalized, variants in sorted(changes.items()):
                total_count = sum(count for _, count in variants)
                preview_text += f"\n'{normalized}' ({total_count} Dateien):\n"
                for old_genre, count in variants:
                    preview_text += f"  ← '{old_genre}' ({count} Dateien)\n"
        
        if removed_count > 0:
            preview_text += f"\n\nENTFERNT WERDEN:\n"
            preview_text += "-"*60 + "\n"
            preview_text += f"Unspezifische Genres: {removed_count} Dateien\n"
            preview_text += "(werden auf leeren String gesetzt)\n"
        
        preview_text += f"\n\nUNVERÄNDERT:\n"
        preview_text += "-"*60 + "\n"
        preview_text += f"{unchanged_count} Dateien behalten ihre Genres\n"
        
        preview_text += f"\n\n{'='*60}\n"
        preview_text += f"GESAMT:\n"
        preview_text += f"  Zu ändernde Dateien: {sum(sum(c for _, c in v) for v in changes.values())}\n"
        preview_text += f"  Zu entfernende: {removed_count}\n"
        preview_text += f"  Unverändert: {unchanged_count}\n"
        
        # Zeige Vorschau
        preview_window = tk.Toplevel(root)
        preview_window.title("Genre-Normalisierung Vorschau")
        preview_window.geometry("700x600")
        
        tk.Label(preview_window, text="Vorschau der Änderungen", 
                font=('Arial', 14, 'bold')).pack(pady=10)
        
        text_frame = tk.Frame(preview_window)
        text_frame.pack(fill='both', expand=True, padx=10, pady=10)
        
        text_widget = tk.Text(text_frame, wrap=tk.WORD, font=('Courier', 9))
        scrollbar = tk.Scrollbar(text_frame, command=text_widget.yview)
        text_widget.configure(yscrollcommand=scrollbar.set)
        
        text_widget.pack(side='left', fill='both', expand=True)
        scrollbar.pack(side='right', fill='y')
        
        text_widget.insert('1.0', preview_text)
        text_widget.config(state=tk.DISABLED)
        
        # Buttons
        button_frame = tk.Frame(preview_window)
        button_frame.pack(pady=10)
        
        def apply_normalization():
            """KORRIGIERT: Thread-safe Normalisierung"""
            try:
                preview_window.destroy()
                
                # Progress-Window
                progress = tk.Toplevel(root)
                progress.title("Normalisiere Genres...")
                progress.geometry("400x150")
                
                tk.Label(progress, text="Normalisiere Genres...", 
                        font=('Arial', 12, 'bold')).pack(pady=20)
                
                progress_bar = ttk.Progressbar(progress, mode='indeterminate', length=300)
                progress_bar.pack(pady=10)
                progress_bar.start(10)
                
                status_label = tk.Label(progress, text="Bitte warten...")
                status_label.pack(pady=10)
                
                def do_normalization():
                    """KRITISCH: Neue Connection im Worker-Thread erstellen!"""
                    updated_count = 0
                    
                    try:
                        # NEU: Connection im WORKER-Thread erstellen
                        thread_conn = sqlite3.connect('media_index.db', timeout=30.0)
                        thread_cursor = thread_conn.cursor()
                        
                        # Durchlaufe alle Änderungen
                        for normalized, variants in changes.items():
                            old_genres = [v[0] for v in variants]
                            placeholders = ','.join('?' * len(old_genres))
                            
                            thread_cursor.execute(
                                f"UPDATE media_files SET genre = ? WHERE genre IN ({placeholders})",
                                [normalized] + old_genres
                            )
                            updated_count += thread_cursor.rowcount
                        
                        # Entferne unspezifische Genres
                        if removed_count > 0:
                            # Sammle zu entfernende Genres (aus Haupt-Thread-Daten)
                            remove_genres = [g for g, _ in all_genres if normalize_genre(g) is None]
                            if remove_genres:
                                placeholders = ','.join('?' * len(remove_genres))
                                thread_cursor.execute(
                                    f"UPDATE media_files SET genre = '' WHERE genre IN ({placeholders})",
                                    remove_genres
                                )
                        
                        thread_conn.commit()
                        thread_conn.close()
                        
                        # Zeige Ergebnis (im Haupt-Thread via after)
                        root.after(0, lambda: show_result(updated_count, progress))
                        
                    except Exception as e:
                        print(f"Normalisierungs-Fehler: {e}")
                        import traceback
                        traceback.print_exc()
                        root.after(0, lambda: show_error(e, progress))
                
                def show_result(count, progress_win):
                    try:
                        progress_win.destroy()
                    except:
                        pass
                    
                    messagebox.showinfo(
                        "Normalisierung abgeschlossen",
                        f"Genres erfolgreich normalisiert!\n\n"
                        f"Aktualisierte Einträge: {count}\n"
                        f"Entfernte unspezifische Genres: {removed_count}\n\n"
                        f"Bitte öffnen Sie die Statistiken neu,\n"
                        f"um die Änderungen zu sehen."
                    )
                
                def show_error(error, progress_win):
                    try:
                        progress_win.destroy()
                    except:
                        pass
                    messagebox.showerror("Fehler", f"Fehler bei der Normalisierung:\n{error}")
                
                # Starte in Thread
                thread = threading.Thread(target=do_normalization, daemon=True)
                thread.start()
                
            except Exception as e:
                messagebox.showerror("Fehler", f"Fehler bei der Normalisierung:\n{e}")
        
        tk.Button(button_frame, text="✓ Anwenden", command=apply_normalization,
                 bg='lightgreen', font=('Arial', 10, 'bold'), width=15).pack(side='left', padx=5)
        
        tk.Button(button_frame, text="✗ Abbrechen", command=preview_window.destroy,
                 bg='lightcoral', font=('Arial', 10, 'bold'), width=15).pack(side='left', padx=5)
        
    except Exception as e:
        messagebox.showerror("Fehler", f"Fehler beim Laden der Genres:\n{e}")
        import traceback
        traceback.print_exc()

def add_genre_normalization_to_settings():
    """
    Fügt Genre-Normalisierungs-Button zu Settings hinzu
    
    Diese Funktion in open_settings() einbauen:
    """
    settings_code = """
    # In open_settings() nach "Synchronize Drive & Database" Button:
    
    tk.Button(settings_window, text="🔄 Synchronize Drive & Database", 
              command=train_db_with_progress, bg='lightgreen').pack(pady=5)
    
    # NEU: Genre-Normalisierung
    tk.Button(settings_window, text="🏷️ Genre-Normalisierung", 
              command=normalize_all_genres_in_database, bg='lightyellow').pack(pady=5)
    """
    return settings_code

# Hilfe: Jahr erkennen
YEAR_PATTERN = re.compile(r'\b(19|20)\d{2}\b')

@lru_cache(maxsize=10000)
def classify_path_dynamic(file_path):
    """
    Vollständig dynamische Pfad-Klassifizierung mit Caching
    
    Struktur:
    - Stammverzeichnis (Position 0-1) = Hauptkategorie
    - Erstes Unterverzeichnis = Haupt-Genre
    - Weitere Unterverzeichnisse = Unter-Genres/Albums/Serien
    
    Returns: tuple (für Hashbarkeit im Cache)
    """
    parts = os.path.normpath(file_path).split(os.sep)
    filename = parts[-1]
    folders = parts[:-1]

    # Basis-Struktur als tuple (immutable für Cache)
    result_data = {
        'media_type': None,
        'genre': None,
        'sub_genre': None,
        'series': None,
        'album': None,
        'title': None,
        'year': None,
        'main_category': None,
        'hierarchy_depth': 0
    }

    clean_folders = []
    for part in folders:
        if part and not part.endswith(':') and part != '':
            clean_folders.append(part)
    
    if not clean_folders:
        result_data['title'] = os.path.splitext(filename)[0]
        return result_data
    
    result_data['hierarchy_depth'] = len(clean_folders)

    if len(clean_folders) >= 1:
        result_data['main_category'] = clean_folders[0]
        result_data['media_type'] = clean_folders[0]

    if len(clean_folders) >= 2:
        result_data['genre'] = clean_folders[1]

    if len(clean_folders) >= 3:
        result_data['sub_genre'] = clean_folders[2]
        result_data['series'] = clean_folders[2]
        result_data['album'] = clean_folders[2]
    
    if len(clean_folders) >= 4:
        result_data['sub_genre'] = os.sep.join(clean_folders[2:])

    result_data['title'] = os.path.splitext(filename)[0]

    for part in clean_folders + [filename]:
        match = YEAR_PATTERN.search(part)
        if match:
            result_data['year'] = match.group()
            break

    return result_data


def clear_path_classification_cache():
    """Leert den Cache wenn Pfade sich ändern"""
    classify_path_dynamic.cache_clear()
    print("Pfad-Klassifizierungs-Cache geleert")

def extract_cover_art(file_path, max_size=(300, 450)):
    """Cover-Art Extraktion mit Pfad-Normalisierung"""
    normalized_path = normalize_file_path(file_path)
    
    image_path = get_image_path(normalized_path)
    if image_path:
        try:
            with Image.open(image_path) as img:
                img.thumbnail(max_size, Image.LANCZOS)
                return img.copy()
        except Exception as e:
            print(f"Fehler beim Laden des Bildes: {e}")

    try:
        if normalized_path.lower().endswith('.mp3'):
            audio = MP3(normalized_path, ID3=ID3)
            if audio.tags:
                for tag in audio.tags.values():
                    if isinstance(tag, APIC):
                        image_data = tag.data
                        image = Image.open(BytesIO(image_data))
                        image.thumbnail(max_size, Image.LANCZOS)
                        return image
            print(f"Kein Cover gefunden in {normalized_path}")
            return None
        else:
            probe = ffprobe_file(normalized_path)
            streams = probe.get('streams', [])
            cover_stream_index = None
            
            for stream in streams:
                if (stream.get('codec_type') == 'video' and 
                    stream.get('disposition', {}).get('attached_pic') == 1):
                    cover_stream_index = stream['index']
                    break

            if cover_stream_index is not None:
                cmd = [
                    ffmpeg_path, '-i', normalized_path, 
                    '-map', f'0:{cover_stream_index}', 
                    '-f', 'image2pipe', '-vcodec', 'mjpeg', '-'
                ]
                result = subprocess.run(
                    cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    creationflags=subprocess.CREATE_NO_WINDOW
                )
                
                if result.stdout:
                    image = Image.open(BytesIO(result.stdout))
                    image.thumbnail(max_size, Image.LANCZOS)
                    return image
                else:
                    print(f"Fehler beim Extrahieren des Covers aus {normalized_path}")
                    return None
            else:
                print(f"Kein angehängtes Bild gefunden in {normalized_path}")
                return None
                
    except Exception as e:
        print(f"Ausnahme beim Extrahieren der Cover-Art: {e}")
        return None

def cleanup_all_tooltips():
    """KORRIGIERT: Aggressiveres Tooltip-Cleanup"""
    global _active_tooltips
    
    try:
        # Cleanup registered tooltips
        for tooltip in list(_active_tooltips):
            try:
                if tooltip and hasattr(tooltip, 'winfo_exists') and tooltip.winfo_exists():
                    tooltip.destroy()
            except:
                pass
        _active_tooltips.clear()
        
        # ZUSÄTZLICH: Cleanup Widget-attached tooltips
        try:
            if 'folder_frame' in globals() and folder_frame and folder_frame.winfo_exists():
                for widget in folder_frame.winfo_children():
                    cleanup_widget_tooltip(widget)
        except:
            pass
            
        try:
            if 'media_frame' in globals() and media_frame and media_frame.winfo_exists():
                for widget in media_frame.winfo_children():
                    cleanup_widget_tooltip(widget)
        except:
            pass
            
    except Exception as e:
        print(f"Tooltip-Cleanup Fehler: {e}")

def cleanup_widget_tooltip(widget):
    """Hilfsfunktion: Einzelnes Widget Tooltip cleanup"""
    try:
        if hasattr(widget, "tooltip"):
            try:
                if widget.tooltip and widget.tooltip.winfo_exists():
                    widget.tooltip.destroy()
            except:
                pass
            try:
                del widget.tooltip
            except:
                pass
        
        if hasattr(widget, "tooltip_after_id"):
            try:
                widget.after_cancel(widget.tooltip_after_id)
            except:
                pass
            try:
                del widget.tooltip_after_id
            except:
                pass
    except:
        pass

def on_enter(event, path, widget):
    """KORRIGIERT: Robusterer Enter-Handler mit Scroll-Check"""
    global scroll_active, last_scroll_time
    import time
    
    # KRITISCH: Ignoriere Enter während aktivem Scroll
    current_time = time.time()
    if scroll_active or (current_time - last_scroll_time) < 0.5:
        return
    
    x_root, y_root = event.x_root, event.y_root
    
    # Entferne altes Tooltip
    if hasattr(widget, "tooltip"):
        try:
            if widget.tooltip and widget.tooltip.winfo_exists():
                widget.tooltip.destroy()
        except:
            pass
        widget.tooltip = None

    def show_tooltip_after_delay():
        try:
            # Doppel-Check: Scroll aktiv?
            if scroll_active:
                return
                
            if widget.winfo_exists():
                widget_at_pos = widget.winfo_containing(x_root, y_root)
                if widget_at_pos == widget or (widget_at_pos and str(widget_at_pos).startswith(str(widget))):
                    show_tooltip(x_root, y_root, path, widget)
        except tk.TclError:
            pass
    
    # Cancel existing timer
    if hasattr(widget, "tooltip_after_id"):
        widget.after_cancel(widget.tooltip_after_id)
    
    # Längerer Delay (750ms statt 500ms) für stabileres Verhalten
    widget.tooltip_after_id = widget.after(750, show_tooltip_after_delay)

def on_leave(event, widget):
    """KORRIGIERT: Sofortiges Tooltip-Cleanup"""
    global scroll_active
    
    # Cancel Timer
    if hasattr(widget, "tooltip_after_id"):
        try:
            widget.after_cancel(widget.tooltip_after_id)
        except:
            pass
        try:
            del widget.tooltip_after_id
        except:
            pass

    # Destroy Tooltip
    if hasattr(widget, "tooltip"):
        try:
            if widget.tooltip and widget.tooltip.winfo_exists():
                widget.tooltip.destroy()
        except:
            pass
        try:
            del widget.tooltip
        except:
            pass
    
    # WICHTIG: Reset scroll_active wenn Maus Widget verlässt
    scroll_active = False

def on_motion(event, path, widget):
    """KORRIGIERT: Motion nur wenn kein Scroll aktiv"""
    global scroll_active
    
    if scroll_active:
        return
    
    if hasattr(widget, "tooltip"):
        try:
            if widget.tooltip and widget.tooltip.winfo_exists():
                x_root, y_root = event.x_root, event.y_root
                widget.tooltip.show(x_root, y_root)
        except:
            pass

def show_tooltip(x_root, y_root, path, widget):
    """KORRIGIERT: Tooltip nur erstellen wenn kein Scroll aktiv"""
    global scroll_active
    
    # Double-check: Kein Tooltip während Scroll
    if scroll_active:
        return
    
    # Cleanup old tooltip
    if hasattr(widget, "tooltip"):
        try:
            if widget.tooltip and widget.tooltip.winfo_exists():
                widget.tooltip.destroy()
        except:
            pass
    
    try:
        image = extract_cover_art(path)
        metadata = get_metadata_info(path)
        tooltip = Tooltip(widget, metadata, image=image)
        widget.tooltip = tooltip
        tooltip.show(x_root, y_root)
    except Exception as e:
        print(f"Tooltip-Fehler: {e}")

def bind_tooltip(widget, path):
    widget.bind("<Enter>", lambda event: on_enter(event, path, widget))
    widget.bind("<Leave>", lambda event: on_leave(event, widget))
    widget.bind("<Motion>", lambda event: on_motion(event, path, widget))

def ffprobe_file(file_path):
    """ffprobe mit besserer Pfad-Behandlung"""
    try:
        normalized_path = os.path.normpath(file_path)
        
        result = subprocess.run(
            [ffprobe_path, '-v', 'quiet', '-print_format', 'json', 
             '-show_format', '-show_streams', normalized_path],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding='utf-8', errors='replace',
            creationflags=subprocess.CREATE_NO_WINDOW
        )
        
        if result.returncode != 0:
            print(f"ffprobe Fehler für {normalized_path}: {result.stderr}")
            return {}
            
        if not result.stdout.strip():
            print(f"Leere ffprobe Ausgabe für {normalized_path}")
            return {}
            
        metadata = json.loads(result.stdout)
        return metadata
    except json.JSONDecodeError as e:
        print(f"JSON Parsing Fehler für {file_path}: {e}")
        return {}
    except Exception as e:
        print(f"ffprobe Fehler: {e}")
        return {}

def get_mp3_metadata_with_timeout(file_path, timeout=5):
    """
    Extrahiert MP3 Metadaten mit Timeout
    
    Returns: (album, track_number, year, genre, contributors, length)
    Immer 6 Werte - garantiert
    """
    def fetch_metadata():
        try:
            audio = MP3(file_path, ID3=ID3)
            tags = audio.tags

            length = "0 min"
            if hasattr(audio, 'info') and audio.info and hasattr(audio.info, 'length'):
                try:
                    length = f"{round(audio.info.length / 60, 2)} min"
                except:
                    pass

            if tags is None:
                return '', '', '', '', '', length

            album = tags.get("TALB").text[0] if tags.get("TALB") else ''
            track_number = tags.get("TRCK").text[0] if tags.get("TRCK") else ''
            year = str(tags.get("TDRC").text[0]) if tags.get("TDRC") else ''
            genre = tags.get("TCON").text[0] if tags.get("TCON") else ''
            contributors = tags.get("TPE1").text[0] if tags.get("TPE1") else ''
            
            return album, track_number, year, genre, contributors, length
            
        except Exception as e:
            print(f"Error extracting MP3 metadata from {file_path}: {e}")
            try:
                audio = MP3(file_path)
                if hasattr(audio, 'info') and audio.info and hasattr(audio.info, 'length'):
                    length = f"{round(audio.info.length / 60, 2)} min"
                else:
                    length = "0 min"
            except:
                length = "0 min"
            
            return '', '', '', '', '', length

    with concurrent.futures.ThreadPoolExecutor() as executor:
        future = executor.submit(fetch_metadata)
        try:
            return future.result(timeout=timeout)
        except concurrent.futures.TimeoutError:
            print(f"Datei '{file_path}' überschritt den Zeitrahmen und wird übersprungen.")
            return '', '', '', '', '', "0 min"

def get_enhanced_metadata(file_path):
    """
    Einheitliche Metadaten-Extraktion für alle Dateitypen
    
    Returns: (primary, secondary, tertiary, year, length, path_meta, media_type)
    - MP3: (album, contributors, track_number, year, length, path_meta, media_type)
    - Video: (genre, actors, comment, year, length, path_meta, media_type)
    """
    path_meta = classify_path_dynamic(file_path)
    
    if file_path.lower().endswith('.mp3'):
        album, track_number, year, genre, contributors, length = get_mp3_metadata_with_timeout(file_path)
        
        if not album:
            album = path_meta.get('sub_genre') or path_meta.get('album') or path_meta.get('genre') or ''
        
        if not year and path_meta.get('year'):
            year = path_meta['year']
        
        if not genre:
            genre = path_meta.get('genre') or path_meta.get('main_category') or ''
        
        if genre and ',' in genre:
            genre = genre.split(',')[0].strip()
        
        if not length or length == "Unbekannt" or length.strip() == "":
            length = "0 min"
        
        media_type = path_meta.get('main_category', 'Musik')
        return album, contributors, track_number, year, length, path_meta, media_type

    else:
        genre, actors, comment, year = get_media_metadata_hidden(file_path)
        
        if not genre:
            genre = path_meta.get('genre') or path_meta.get('sub_genre') or path_meta.get('main_category') or ''
        
        if not year and path_meta.get('year'):
            year = path_meta['year']
        
        if not actors:
            actors = path_meta.get('sub_genre') or path_meta.get('series') or ''
        
        if genre and ',' in genre:
            genre = genre.split(',')[0].strip()
        
        length = get_media_duration(file_path)
        if not length or length == "Unbekannt" or length.strip() == "":
            length = "0 min"
        
        media_type = path_meta.get('main_category', 'Video')
        return genre, actors, comment, year, length, path_meta, media_type


def update_display():
    if folder_path:
        display_folders(folder_path)
        display_files(folder_path)

def create_default_config(config_file_path):
    default_config = configparser.ConfigParser()
    default_config['LastDirectory'] = {'path': ''}
    default_config['WindowSize'] = {'size': '800x600'}
    default_config['PanedWindow'] = {'position': '0'}

    with open(config_file_path, 'w') as configfile:
        default_config.write(configfile)

def save_panedwindow_position():
    """Sichere Speicherung der PanedWindow-Position mit Existenzprüfung"""
    try:
        # Prüfe ob PanedWindow noch existiert
        if 'paned_window' in globals() and paned_window and paned_window.winfo_exists():
            position = paned_window.sashpos(0)
        else:
            position = 0
    except (tk.TclError, AttributeError, Exception) as e:
        print(f"Warning: Could not get sash position: {e}")
        position = 0

    # Speichere Position in Config
    try:
        config['PanedWindow'] = {'position': str(position)}
        with open('MediaIndexer.cfg', 'w') as configfile:
            config.write(configfile)
    except Exception as e:
        print(f"Warning: Could not save config: {e}")

def load_panedwindow_position():
    try:
        position_str = config['PanedWindow']['position']
        position = int(re.sub('[^0-9]', '', position_str))
        return position
    except Exception as e:
        print(f"Error loading sash position: {e}")
        return 0

def save_last_directory(path=None):
    if path:
        config['LastDirectory'] = {'path': path}
    window_size = f"{root.winfo_width()}x{root.winfo_height()}"
    config['WindowSize'] = {'size': window_size}
    save_panedwindow_position()
    with open('MediaIndexer.cfg', 'w') as configfile:
        config.write(configfile)

def load_last_directory():
    global folder_path
    config_file_path = 'MediaIndexer.cfg'

    if not os.path.exists(config_file_path):
        create_default_config(config_file_path)
        
    config.read(config_file_path)

    try:
        if 'LastDirectory' in config and 'path' in config['LastDirectory']:
            folder_path = config['LastDirectory']['path']
            if os.path.isdir(folder_path):
                update_display()
        if 'WindowSize' in config and 'size' in config['WindowSize']:
            window_size = config['WindowSize']['size']
            root.geometry(window_size)
            update_display()

            if 'PanedWindow' in config and 'position' in config['PanedWindow']:
                paned_position = load_panedwindow_position()
                root.after(1000, lambda: paned_window.sashpos(0, paned_position))
            else:
                print("PanedWindow section not found in config")
    except Exception as e:
        print(f"Error loading last directory: {e}")

def open_folder():
    global folder_path, search_active
    folder_path = filedialog.askdirectory()
    if folder_path:
        search_active = False
        save_last_directory(folder_path)
        update_display()

def natural_sort_key(s):
    return [int(text) if text.isdigit() else text.lower()
            for text in re.split('(\d+)', s)]

def search_files_recursive(path, media_extensions, playlist_extensions, search_results):
    stack = [path]
    while stack:
        current_path = stack.pop()
        try:
            entries = os.listdir(current_path)
        except PermissionError:
            continue
        
        for entry in entries:
            entry_path = os.path.join(current_path, entry)
            if os.path.isdir(entry_path):
                stack.append(entry_path)
            elif entry.lower().endswith(media_extensions) or entry.lower().endswith(playlist_extensions):
                search_results.append(entry_path)

def perform_search():
    """
    BEREINIGT: Ohne Diagnose-Button und überflüssige Meldungen
    """
    search_term = search_entry.get()

    if folder_path and search_term:
        media_extensions = ('.mp3', '.mp4', '.mkv', '.avi', '.flv', '.mov', '.wmv')
        search_results = []

        if use_db_var.get():
            try:
                conn = sqlite3.connect('media_index.db')
                cursor = conn.cursor()

                # Normalisiere Pfad für Windows (Backslashes)
                normalized_search_path = os.path.normpath(folder_path)
                sql_search_path = normalized_search_path.replace('\\', '\\\\')
                
                # Debug-Output
                print(f"\n=== SUCHE GESTARTET ===")
                print(f"Suchbegriff: '{search_term}'")
                print(f"Ordner (Normalisiert): {normalized_search_path}")

                # Basis-Query mit ESCAPE für Backslashes
                query = "SELECT filepath FROM media_files WHERE filepath LIKE ? ESCAPE '\\' AND (1=0"
                params = [f"{sql_search_path}%"]

                search_conditions = []
                
                if title_search_var.get():
                    query += " OR filename LIKE ? OR container LIKE ?"
                    params.append(f"%{search_term}%")
                    params.append(f"%{search_term}%")
                    search_conditions.append("Titel/Dateiname")

                if genre_var.get():
                    query += " OR genre LIKE ?"
                    params.append(f"%{search_term}%")
                    search_conditions.append("Genre")

                if actors_var.get():
                    query += " OR actors LIKE ?"
                    params.append(f"%{search_term}%")
                    search_conditions.append("Actors")

                if comment_var.get():
                    query += " OR comment LIKE ?"
                    params.append(f"%{search_term}%")
                    search_conditions.append("Comment")

                if album_search_var.get():
                    query += " OR album LIKE ?"
                    params.append(f"%{search_term}%")
                    search_conditions.append("Album")

                if interpret_search_var.get():
                    query += " OR contributors LIKE ?"
                    params.append(f"%{search_term}%")
                    search_conditions.append("Interpret")

                query += ")"

                print(f"Suchfelder: {', '.join(search_conditions) if search_conditions else 'KEINE'}")
                
                if not search_conditions:
                    messagebox.showwarning(
                        "Keine Suchfelder", 
                        "Bitte wählen Sie mindestens ein Suchfeld in den Einstellungen aus."
                    )
                    conn.close()
                    return
                
                cursor.execute(query, params)
                search_results = [row[0] for row in cursor.fetchall()]
                
                print(f"Treffer gefunden: {len(search_results)}")
                
                if search_results:
                    print("Erste 3 Treffer:")
                    for result in search_results[:3]:
                        print(f"  - {os.path.basename(result)}")
                
                conn.close()
                
            except sqlite3.Error as e:
                print(f"Datenbank-Fehler: {e}")
                messagebox.showerror("Datenbank-Fehler", f"Fehler bei der Suche:\n{e}")
                return
                
        else:
            # Dateisystem-Suche
            print("Verwende Dateisystem-Suche (kein DB-Modus)")
            search_files_recursive(folder_path, media_extensions, (), search_results)
            search_results = [result for result in search_results 
                            if search_term.lower() in os.path.basename(result).lower()]
            print(f"Treffer gefunden (Dateisystem): {len(search_results)}")

        # Zeige Ergebnisse (ohne Dialog bei 0 Treffern)
        if search_results:
            display_folders(folder_path, search_results)
            display_files(search_results)

            global search_active, current_search_results
            search_active = True
            current_search_results = search_results.copy()
            
            print(f"=== SUCHE ABGESCHLOSSEN: {len(search_results)} Treffer ===\n")
        else:
            # ENTFERNT: Keine MessageBox mehr bei 0 Treffern
            print("=== KEINE TREFFER ===\n")
            display_folders(folder_path, [])
            display_files([])
    
    elif not folder_path:
        messagebox.showwarning("Kein Ordner", "Bitte wählen Sie zuerst einen Ordner aus.")
    elif not search_term:
        messagebox.showwarning("Kein Suchbegriff", "Bitte geben Sie einen Suchbegriff ein.")

def display_folders(folder_path, search_results=None):
    for widget in folder_frame.winfo_children():
        if hasattr(widget, "tooltip_after_id"):
            widget.after_cancel(widget.tooltip_after_id)
            del widget.tooltip_after_id
        if hasattr(widget, "tooltip"):
            try:
                widget.tooltip.destroy()
            except:
                pass
            del widget.tooltip
        widget.destroy()
    folder_frame.update_idletasks()

    canvas_width = folder_canvas.winfo_width()
    if canvas_width <= 1:
        canvas_width = root.winfo_width()
    
    button_width = 170
    num_columns = calculate_columns(canvas_width, button_width)

    for i in range(20):
        folder_frame.grid_columnconfigure(i, weight=0)
    
    folder_frame.columnconfigure(tuple(range(num_columns)), weight=1)

    row, column = 0, 0

    try:
        if search_results is None:
            folders = [entry for entry in os.listdir(folder_path) if os.path.isdir(os.path.join(folder_path, entry))]
        else:
            folders = sorted({os.path.dirname(result) for result in search_results})
    except PermissionError:
        print(f"Permission denied: {folder_path}")
        folders = []

    parent_folder = os.path.dirname(folder_path)
    if parent_folder and search_results is None:
        folder_up_button = tk.Button(folder_frame, text="Folder Up", bg='green', fg='white', width=20, height=2, wraplength=150, command=lambda: navigate_to_folder(parent_folder))
        folder_up_button.grid(row=row, column=column, padx=10, pady=5, sticky='nsew')

        default_font = folder_up_button.cget("font")
        new_font = tkFont.Font(font=default_font)
        new_font.config(size=int(new_font['size'] * 1.2), weight='bold')
        folder_up_button.config(font=new_font)

        column += 1
        if column >= num_columns:
            row += 1
            column = 0

    for folder in folders:
        folder_button = tk.Button(folder_frame, text=folder, width=20, height=2, wraplength=150, command=lambda path=os.path.join(folder_path, folder): navigate_to_folder(path))
        folder_button.grid(row=row, column=column, padx=10, pady=5, sticky='nsew')

        default_font = folder_button.cget("font")
        new_font = tkFont.Font(font=default_font)
        new_font.config(size=int(new_font['size'] * 1.2), weight='bold')
        folder_button.config(font=new_font)

        column += 1
        if column >= num_columns:
            row += 1
            column = 0
            if row >= 100:
                break
    
    folder_frame.update_idletasks()
    folder_canvas.configure(scrollregion=folder_canvas.bbox('all'))

def navigate_to_folder(path):
    global folder_path, search_active, current_search_results
    folder_path = path
    search_active = False
    current_search_results = []
    display_folders(path)
    display_files(path)

def calculate_columns(window_width, button_width):
    padding = 20
    scrollbar_width = 20
    return max(1, (window_width - padding - scrollbar_width) // (button_width + padding))

def display_files(files_or_folder_path):
    media_extensions = ('.mp3', '.mp4', '.mkv', '.avi', '.flv', '.mov', '.wmv')
    playlist_extensions = ('.xspf',)

    for widget in media_frame.winfo_children():
        if hasattr(widget, "tooltip_after_id"):
            widget.after_cancel(widget.tooltip_after_id)
            del widget.tooltip_after_id
        if hasattr(widget, "tooltip"):
            try:
                widget.tooltip.destroy()
            except:
                pass
            del widget.tooltip
        widget.destroy()
    media_frame.update_idletasks()

    canvas_width = media_canvas.winfo_width()
    if canvas_width <= 1:
        canvas_width = root.winfo_width()
    
    button_width = 170
    num_columns = calculate_columns(canvas_width - media_scrollbar.winfo_width(), button_width)

    for i in range(20):
        media_frame.grid_columnconfigure(i, weight=0)
    
    media_frame.columnconfigure(tuple(range(num_columns)), weight=1)

    row, column = 0, 0
    
    if isinstance(files_or_folder_path, str): 
        folder_path_local = files_or_folder_path
        try:
            files = os.listdir(folder_path_local)
            files.sort(key=natural_sort_key)
        except PermissionError:
            print(f"Permission denied: {folder_path_local}")
            files = []
    else:  
        files = files_or_folder_path
        files.sort(key=lambda x: natural_sort_key(os.path.basename(x)))

    media_box = None

    for file in files:
        if file.lower().endswith(media_extensions) or file.lower().endswith(playlist_extensions):
            if isinstance(files_or_folder_path, str):
                file_path = os.path.join(folder_path_local, file)
            else:
                file_path = file
                file = os.path.basename(file)
            file_name, file_ext = os.path.splitext(file)

            media_box = tk.Button(media_frame, text=file_name, width=20, height=2, wraplength=150, command=lambda path=file_path: safe_startfile(path))
            media_box.grid(row=row, column=column, padx=5, pady=5, sticky='nsew')

            default_font = media_box.cget("font")
            new_font = tkFont.Font(font=default_font)
            new_font.config(size=int(new_font['size'] * 1.3), weight='bold')
            media_box.config(font=new_font)

            if file_ext.lower() in playlist_extensions:
                media_box.config(bg='yellow')

            bind_tooltip(media_box, file_path)

            column += 1
            if column >= num_columns:
                row += 1
                column = 0
                if row >= 100:
                    break

    if media_box:
        media_frame.update_idletasks()
        media_canvas.configure(scrollregion=media_canvas.bbox('all'))

def get_image_path(file_path):
    base_name = os.path.splitext(file_path)[0]
    image_extensions = ['.png', '.jpg', '.jpeg']
    for ext in image_extensions:
        image_path = base_name + ext
        if os.path.exists(image_path):
            return image_path
    return None

def get_media_duration(file_path):
    """
    Extrahiert Videolänge mit verbesserter Fehlerbehandlung
    
    Fallback-Reihenfolge:
    1. ffprobe format duration
    2. ffprobe stream duration  
    3. ffprobe JSON parsing
    4. Nur bei explizitem Fehler: "0 min"
    """
    normalized_path = normalize_file_path(file_path)
    
    duration_value = None
    last_error = None
    
    # Methode 1: ffprobe format duration
    try:
        result = subprocess.run(
            [ffprobe_path, '-v', 'error', '-show_entries', 'format=duration', 
             '-of', 'default=noprint_wrappers=1:nokey=1', normalized_path],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            creationflags=subprocess.CREATE_NO_WINDOW, timeout=30
        )
        
        duration_output = result.stdout.strip()
        
        if duration_output and duration_output != 'N/A':
            try:
                duration_value = float(duration_output)
                if duration_value > 0:
                    return f"{round(duration_value / 60, 2)} min"
            except ValueError:
                pass
    except Exception as e:
        last_error = f"Format duration: {e}"
    
    # Methode 2: ffprobe stream duration
    try:
        result = subprocess.run(
            [ffprobe_path, '-v', 'error', '-select_streams', 'v:0', 
             '-show_entries', 'stream=duration', '-of', 'default=noprint_wrappers=1:nokey=1', normalized_path],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            creationflags=subprocess.CREATE_NO_WINDOW, timeout=30
        )
        
        duration_output = result.stdout.strip()
        
        if duration_output and duration_output != 'N/A':
            try:
                duration_value = float(duration_output)
                if duration_value > 0:
                    return f"{round(duration_value / 60, 2)} min"
            except ValueError:
                pass
    except Exception as e:
        last_error = f"Stream duration: {e}"
    
    # Methode 3: ffprobe JSON parsing
    try:
        metadata = ffprobe_file(normalized_path)
        
        # Format duration
        format_duration = metadata.get('format', {}).get('duration')
        if format_duration:
            try:
                duration_value = float(format_duration)
                if duration_value > 0:
                    return f"{round(duration_value / 60, 2)} min"
            except (ValueError, TypeError):
                pass
        
        # Stream duration
        streams = metadata.get('streams', [])
        for stream in streams:
            if stream.get('codec_type') == 'video':
                stream_duration = stream.get('duration')
                if stream_duration:
                    try:
                        duration_value = float(stream_duration)
                        if duration_value > 0:
                            return f"{round(duration_value / 60, 2)} min"
                    except (ValueError, TypeError):
                        pass
                        
    except Exception as e:
        last_error = f"JSON parsing: {e}"
    
    # Fehlerfall: Explizit loggen aber 0 min zurückgeben
    if last_error:
        print(f"WARNUNG: Keine Laufzeit ermittelbar für {file_path}")
        print(f"Letzter Fehler: {last_error}")
    else:
        print(f"INFO: Keine Laufzeit-Metadaten in {file_path}")
    
    return "0 min"

def safe_startfile(file_path):
    """Sichere Datei-Öffnung mit Pfad-Normalisierung"""
    try:
        normalized_path = normalize_file_path(file_path)
        
        if not os.path.exists(normalized_path):
            messagebox.showerror("Datei nicht gefunden", 
                               f"Die Datei konnte nicht gefunden werden:\n{normalized_path}")
            return
            
        os.startfile(normalized_path)
    except Exception as e:
        messagebox.showerror("Fehler beim Öffnen", 
                           f"Fehler beim Öffnen der Datei:\n{file_path}\n\nFehler: {e}")

def get_metadata_info(file_path):
    """
    KORRIGIERT: Korrekte Reihenfolge der 7 Rückgabewerte
    """
    try:
        if file_path.lower().endswith('.mp3'):
            # Rückgabe: album, contributors, track_number, year, length, path_meta, media_type
            album, contributors, track_number, year, length, path_meta, media_type = get_enhanced_metadata(file_path)
            
            metadata_lines = []
            metadata_lines.append(f"Titel: {track_number}")
            metadata_lines.append(f"Interpret: {contributors}")
            metadata_lines.append(f"Album: {album}")
            metadata_lines.append(f"Jahr: {year}")
            metadata_lines.append(f"Laufzeit: {length}")
            
            if media_type:
                metadata_lines.append(f"Medientyp: {media_type}")
            
            if path_meta.get('genre'):
                metadata_lines.append(f"Genre: {path_meta['genre']}")
            
            metadata = "\n".join(metadata_lines)
        else:
            # Rückgabe: genre, actors, comment, year, length, path_meta, media_type
            genre, actors, comment, year, length, path_meta, media_type = get_enhanced_metadata(file_path)
            file_name = os.path.basename(file_path)

            indent = ' ' * 13
            comment_wrapped = textwrap.fill(comment, width=100, subsequent_indent=indent)
            actors_wrapped = textwrap.fill(actors, width=100, subsequent_indent=indent)
            
            metadata_lines = []
            metadata_lines.append(f"Filmtitel: {path_meta.get('title', file_name)}")
            metadata_lines.append(f"Jahr: {year}")
            metadata_lines.append(f"Genre: {genre}")
            metadata_lines.append(f"Schauspieler: {actors_wrapped}")
            metadata_lines.append(f"Filmlänge: {length}")
            
            if media_type:
                metadata_lines.append(f"Medientyp: {media_type}")
            if path_meta.get('series') and media_type == 'Serien':
                metadata_lines.append(f"Serien: {path_meta['series']}")
            
            metadata_lines.append(f"\nInhalt: {comment_wrapped}")
            metadata = "\n".join(metadata_lines)
            
        return metadata
    except Exception as e:
        print(f"Fehler beim Abrufen der Metadaten für {file_path}: {e}")
        return "Keine Metadaten verfügbar"

def on_root_configure(event):
    """Verbesserte Root-Configure Handler"""
    try:
        global resize_after_id
        
        if event.widget != root or not root.winfo_exists():
            return
        
        if resize_after_id:
            try:
                root.after_cancel(resize_after_id)
            except (tk.TclError, AttributeError):
                pass
        
        try:
            if root.winfo_exists():
                resize_after_id = root.after(200, refresh_ui)
        except (tk.TclError, AttributeError):
            pass
            
    except Exception as e:
        print(f"Root-Configure Fehler (ignoriert): {e}")

def bind_scroll_to_canvas(canvas):
    """Verbesserter Scroll-Handler mit Performance-Optimierung"""
    global current_scroll_handler, scroll_active, last_scroll_time
    import time
    
    # Remove old handler
    if current_scroll_handler:
        try:
            root.unbind_all("<MouseWheel>")
        except:
            pass
    
    def scroll_handler(event):
        global scroll_active, last_scroll_time
        
        # Setze Scroll-Flag
        scroll_active = True
        last_scroll_time = time.time()
        
        try:
            # Effizienteres Scrollen mit delta
            delta = int(-1 * (event.delta / 120))
            canvas.yview_scroll(delta, "units")
            
            # Sofortiges Cleanup während Scroll
            cleanup_all_tooltips()
            
            # Verzögertes Reset
            def delayed_reset():
                global scroll_active
                scroll_active = False
                # Optional: Aktualisiere UI nach Scroll-Ende
                root.after(100, refresh_ui)
            
            # Cancel existing timer
            if hasattr(scroll_handler, 'reset_timer'):
                try:
                    root.after_cancel(scroll_handler.reset_timer)
                except:
                    pass
            
            # Setze neuen Timer (kürzer für schnellere Reaktion)
            scroll_handler.reset_timer = root.after(200, delayed_reset)
            
        except Exception as e:
            print(f"Scroll error: {e}")
    
    current_scroll_handler = root.bind_all("<MouseWheel>", scroll_handler)

def on_canvas_enter(event, canvas):
    """NEU: Canvas Enter Handler - aktiviert Scroll"""
    global scroll_active
    scroll_active = False  # Reset beim Betreten
    bind_scroll_to_canvas(canvas)

def on_canvas_leave(event):
    """NEU: Canvas Leave Handler - deaktiviert Scroll"""
    global scroll_active, current_scroll_handler
    
    # Deaktiviere Scroll
    scroll_active = False
    
    # Remove Scroll Handler
    if current_scroll_handler:
        try:
            root.unbind_all("<MouseWheel>")
        except:
            pass
        current_scroll_handler = None
    
    # Cleanup Tooltips
    cleanup_all_tooltips()

def on_canvas_configure_debounced(event, canvas_type):
    """Verbesserte Canvas-Configure Handler mit Existenzprüfung"""
    try:
        # Prüfe ob Root noch existiert
        if not root or not root.winfo_exists():
            return
            
        if not hasattr(root, 'canvas_resize_after_id'):
            root.canvas_resize_after_id = {}
        
        if canvas_type in root.canvas_resize_after_id:
            try:
                root.after_cancel(root.canvas_resize_after_id[canvas_type])
            except (tk.TclError, AttributeError):
                pass
        
        def delayed_refresh():
            try:
                if root and root.winfo_exists() and folder_path:
                    refresh_ui()
                if hasattr(root, 'canvas_resize_after_id') and canvas_type in root.canvas_resize_after_id:
                    del root.canvas_resize_after_id[canvas_type]
            except (tk.TclError, AttributeError):
                pass
        
        try:
            if root and root.winfo_exists():
                root.canvas_resize_after_id[canvas_type] = root.after(300, delayed_refresh)
        except (tk.TclError, AttributeError):
            pass
            
    except Exception as e:
        print(f"Canvas-Configure Fehler (ignoriert): {e}")

def refresh_ui():
    """Sichere UI-Aktualisierung mit Existenzprüfungen"""
    try:
        if not root or not root.winfo_exists() or not folder_path:
            return
            
        try:
            if 'folder_canvas' in globals() and folder_canvas and folder_canvas.winfo_exists():
                folder_canvas.update_idletasks()
        except (tk.TclError, AttributeError):
            pass
            
        try:
            if 'media_canvas' in globals() and media_canvas and media_canvas.winfo_exists():
                media_canvas.update_idletasks()
        except (tk.TclError, AttributeError):
            pass
        
        # Display-Updates nur wenn Widgets existieren
        try:
            if search_active:
                display_folders(folder_path, current_search_results)
                display_files(current_search_results)
            else:
                display_folders(folder_path)
                display_files(folder_path)
        except Exception as e:
            print(f"Display-Update Fehler (ignoriert): {e}")
            
    except Exception as e:
        print(f"Refresh-UI Fehler (ignoriert): {e}")

def get_file_hash(file_path):
    """Erstellt Hash für Datei-Änderungserkennung"""
    try:
        stat = os.stat(file_path)
        hash_string = f"{file_path}_{stat.st_size}_{stat.st_mtime}"
        return hashlib.md5(hash_string.encode()).hexdigest()
    except:
        return None

def create_or_reset_db():
    """Erweiterte Datenbank mit Tracking-Feldern"""
    db_path = 'media_index.db'
    if os.path.exists(db_path):
        os.remove(db_path)
        print("Datenbank gelöscht.")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS media_files (
            id INTEGER PRIMARY KEY,
            filename TEXT,
            filepath TEXT UNIQUE,
            container TEXT,
            album TEXT,
            track_number TEXT,
            year TEXT,
            genre TEXT,
            length TEXT,
            contributors TEXT,
            actors TEXT,
            comment TEXT,
            category TEXT,
            file_size INTEGER,
            bitrate INTEGER,
            video_codec TEXT,
            audio_codec TEXT,
            resolution TEXT,
            fps REAL,
            audio_channels INTEGER,
            sample_rate INTEGER,
            has_metadata INTEGER DEFAULT 0,
            file_hash TEXT,
            scan_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_modified TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_filepath ON media_files(filepath)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_category ON media_files(category)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_genre ON media_files(genre)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_file_hash ON media_files(file_hash)')
    
    conn.commit()
    conn.close()
    print("Erweiterte Datenbank mit Tracking erstellt.")

def train_db_with_progress():
    """
    KORRIGIERT: Verwendet korrektes Genre-Mapping mit Thread-Safety
    """
    if not folder_path:
        messagebox.showwarning("Warnung", "Bitte wählen Sie zuerst einen Ordner aus")
        return
    
    # Prüfe ob bereits ein Scan läuft
    if hasattr(root, '_scan_in_progress') and root._scan_in_progress:
        if messagebox.askyesno("Scan läuft", "Ein Scan läuft bereits. Möchten Sie diesen abbrechen?"):
            # Stoppe aktuellen Scan
            root._scan_in_progress = False
            root.after(1000, train_db_with_progress)  # Neustart nach 1s
        return
    
    root._scan_in_progress = True
    
    progress_window = tk.Toplevel(root)
    progress_window.title("Medien-Scan läuft...")
    progress_window.geometry("700x400")
    progress_window.protocol("WM_DELETE_WINDOW", lambda: cleanup_progress_window(progress_window))

    progress_label = tk.Label(progress_window, text="Initialisiere Scan...", font=('Arial', 11, 'bold'))
    progress_label.pack(pady=10)

    progress_bar = ttk.Progressbar(progress_window, orient='horizontal', mode='determinate', length=650)
    progress_bar.pack(pady=10)

    file_progress_label = tk.Label(progress_window, text="Starte...", font=('Arial', 10))
    file_progress_label.pack(pady=5)

    detail_label = tk.Label(progress_window, text="", font=('Arial', 9))
    detail_label.pack(pady=5)

    duration_label = tk.Label(progress_window, text="", font=('Arial', 9), fg='blue')
    duration_label.pack(pady=2)

    stats_label = tk.Label(progress_window, text="", font=('Arial', 9), fg='green')
    stats_label.pack(pady=2)
    
    status_frame = tk.LabelFrame(progress_window, text="Live-Status", font=('Arial', 9))
    status_frame.pack(fill='x', padx=10, pady=5)
    
    status_text = tk.Label(status_frame, text="Warte auf Start...", font=('Arial', 8), anchor='w')
    status_text.pack(padx=5, pady=2)
    
    main_dir_label = tk.Label(progress_window, text="", font=('Arial', 10, 'bold'), fg='purple')
    main_dir_label.pack(pady=2)
    
    cleanup_label = tk.Label(progress_window, text="", font=('Arial', 9), fg='red')
    cleanup_label.pack(pady=2)

    stop_scanning = threading.Event()

    scan_status = {
        'total_scanned': 0,
        'new_files_count': 0,
        'updated_files_count': 0,
        'path_metadata_used': 0,
        'total_duration_found': 0,
        'duration_errors': 0,
        'medientyp_erkannt': 0,
        'current_file': '',
        'current_file_count': 0,
        'total_files': 0,
        'current_detail': '',
        'current_duration': '',
        'is_running': True,
        'last_update': 0,
        'deleted_files_count': 0,
        'db_entries_checked': 0,
        'cleanup_phase': False,
        'quality_analyzed': 0,
        'current_main_category': '',
        'main_dirs_total': 0,
        'main_dirs_completed': 0
    }

    def update_gui_from_main_thread():
        if not progress_window.winfo_exists():
            return
            
        try:
            if scan_status['total_files'] > 0:
                if scan_status['cleanup_phase']:
                    progress = 100
                    progress_label.config(text=f"Bereinige Datenbank... {scan_status['db_entries_checked']} geprüft")
                else:
                    progress = (scan_status['current_file_count'] / scan_status['total_files']) * 100
                    cat_text = f" [{scan_status['current_main_category']}]" if scan_status['current_main_category'] else ""
                    progress_label.config(text=f"Scan läuft{cat_text}... {progress:.1f}%")
                
                progress_bar['value'] = progress
            
            if scan_status['main_dirs_total'] > 0:
                main_dir_label.config(
                    text=f"Hauptverzeichnis: {scan_status['main_dirs_completed']}/{scan_status['main_dirs_total']} - "
                         f"{scan_status['current_main_category']}"
                )
            
            filename = scan_status['current_file']
            if filename:
                display_name = filename[:60] + "..." if len(filename) > 60 else filename
                file_progress_label.config(
                    text=f"({scan_status['current_file_count']}/{scan_status['total_files']}) - {display_name}"
                )
            
            detail_label.config(text=scan_status['current_detail'])
            
            if scan_status['current_duration']:
                duration_label.config(text=f"Laufzeit: {scan_status['current_duration']}")
            
            hours = int(scan_status['total_duration_found'] / 60)
            minutes = int(scan_status['total_duration_found'] % 60)
            stats_label.config(
                text=f"Gesamt: {hours}h {minutes}m | "
                     f"Neue: {scan_status['new_files_count']} | "
                     f"Übersprungen: {scan_status['updated_files_count']} | "
                     f"Qualität: {scan_status['quality_analyzed']}"
            )
            
            status_text.config(
                text=f"Gescannt: {scan_status['total_scanned']} | "
                     f"Medientypen: {scan_status['medientyp_erkannt']} | "
                     f"Pfad-Meta: {scan_status['path_metadata_used']}"
            )
            
            if scan_status['deleted_files_count'] > 0:
                cleanup_label.config(text=f"Gelöscht: {scan_status['deleted_files_count']} veraltete Einträge")
            
            progress_window.update_idletasks()
            
            if scan_status['is_running'] and progress_window.winfo_exists():
                progress_window.after(100, update_gui_from_main_thread)
                
        except Exception as e:
            print(f"GUI Update Fehler: {e}")

    def cleanup_progress_window(progress_window):
        stop_scanning.set()
        scan_status['is_running'] = False
        root._scan_in_progress = False
        try:
            progress_window.destroy()
        except:
            pass

    def run_ffprobe():
        """
        VOLLSTÄNDIG KORRIGIERT: 
        - Thread-safe DB-Verbindung
        - MP3-Genre wird normalisiert
        - UTF-8 sichere Genre-Behandlung
        """
        try:
            media_extensions = ('.mp3', '.mp4', '.mkv', '.avi', '.mov', '.wmv', '.flv')
            batch_size = 50
            
            # KRITISCH: Connection im Worker-Thread erstellen!
            conn = sqlite3.connect('media_index.db', timeout=30.0)
            cursor = conn.cursor()

            print(f"\n=== STARTE SCAN FÜR: {folder_path} ===")

            current_scan_path = os.path.normpath(folder_path)
            
            # Existing files check
            cursor.execute("SELECT filepath FROM media_files WHERE filepath LIKE ? ESCAPE '\\'", 
                         (f"{current_scan_path.replace(chr(92), chr(92)*2)}%",))
            db_files_in_scope = set(row[0] for row in cursor.fetchall())
            print(f"Gefunden: {len(db_files_in_scope)} DB-Einträge im Scan-Bereich")
            
            # Directory structure analysis
            print("Analysiere Verzeichnisstruktur...")
            main_directories = {}
            
            try:
                for entry in os.listdir(current_scan_path):
                    entry_path = os.path.join(current_scan_path, entry)
                    if os.path.isdir(entry_path):
                        main_directories[entry] = []
            except Exception as e:
                print(f"Fehler beim Lesen von {current_scan_path}: {e}")
            
            if not main_directories:
                main_directories['[Aktueller Ordner]'] = []
            
            scan_status['main_dirs_total'] = len(main_directories)
            
            # File collection
            all_current_files = set()
            for main_dir_name in main_directories.keys():
                if stop_scanning.is_set():
                    break
                    
                if main_dir_name == '[Aktueller Ordner]':
                    scan_root = current_scan_path
                else:
                    scan_root = os.path.join(current_scan_path, main_dir_name)
                
                for root_dir, _, files in os.walk(scan_root):
                    if stop_scanning.is_set():
                        break
                    for file in files:
                        if file.lower().endswith(media_extensions):
                            file_path = os.path.join(root_dir, file)
                            main_directories[main_dir_name].append(file_path)
                            all_current_files.add(file_path)
            
            scan_status['total_files'] = len(all_current_files)
            print(f"Gefunden: {scan_status['total_files']} Mediendateien")
            
            new_files = all_current_files - db_files_in_scope
            existing_files = all_current_files.intersection(db_files_in_scope)
            
            print(f"Neue Dateien: {len(new_files)}")
            print(f"Bereits bekannt (übersprungen): {len(existing_files)}")
            
            scan_status['updated_files_count'] = len(existing_files)
            
            media_files = []
            
            for main_dir_idx, (main_dir_name, file_list) in enumerate(sorted(main_directories.items()), 1):
                if stop_scanning.is_set():
                    break
                
                scan_status['current_main_category'] = main_dir_name
                scan_status['main_dirs_completed'] = main_dir_idx - 1
                
                print(f"\n=== SCANNE HAUPTVERZEICHNIS {main_dir_idx}/{len(main_directories)}: {main_dir_name} ({len(file_list)} Dateien) ===")
                
                for file_path in file_list:
                    if stop_scanning.is_set():
                        break
                    
                    if file_path in existing_files:
                        scan_status['current_file_count'] += 1
                        continue
                    
                    scan_status['current_file_count'] += 1
                    scan_status['current_file'] = os.path.basename(file_path)
                    
                    try:
                        file_size = os.path.getsize(file_path)
                        parent_folder = os.path.basename(os.path.dirname(file_path))

                        if file_path.lower().endswith('.mp3'):
                            # === MP3-VERARBEITUNG (KORRIGIERT) ===
                            album, track_number, year, id3_genre, contributors, length = get_mp3_metadata_with_timeout(file_path)
                            audio_quality = get_audio_quality_info(file_path)
                            
                            path_meta = classify_path_dynamic(file_path)
                            
                            # KRITISCH: Genre-Normalisierung
                            final_genre = ''
                            
                            # 1. Priorität: ID3-Genre normalisieren
                            if id3_genre:
                                normalized_id3 = normalize_genre(id3_genre)
                                if normalized_id3:
                                    final_genre = normalized_id3
                            
                            # 2. Fallback: Pfad-Genre normalisieren
                            if not final_genre:
                                path_genre = path_meta.get('genre', '')
                                if path_genre:
                                    normalized_path = normalize_genre(path_genre)
                                    if normalized_path:
                                        final_genre = normalized_path
                                        scan_status['path_metadata_used'] += 1
                            
                            # Debug-Ausgabe
                            if id3_genre and id3_genre != final_genre:
                                print(f"Genre normalisiert: '{id3_genre}' → '{final_genre}'")
                            
                            # Fallbacks für andere Felder
                            if not year and path_meta.get('year'):
                                year = path_meta['year']
                            if not album and path_meta.get('album'):
                                album = path_meta['album']
                            
                            # Medientyp (NICHT Genre!)
                            category = path_meta.get('main_category', 'Musik')
                            if category:
                                scan_status['medientyp_erkannt'] += 1
                            
                            # Laufzeit
                            duration_minutes = 0
                            try:
                                duration_minutes = float(length.replace(' min', '').replace('min', '').strip())
                                scan_status['total_duration_found'] += duration_minutes
                            except:
                                scan_status['duration_errors'] += 1
                                length = "0 min"
                            
                            has_metadata = 1 if (album and category and contributors) else 0
                            
                            # === SPEICHERN MIT NORMALISIERTEM GENRE ===
                            media_files.append((
                                os.path.basename(file_path), file_path, parent_folder, 
                                album, track_number, year, 
                                final_genre,  # ← NORMALISIERTES Genre!
                                length, contributors, '', '',
                                category, file_size, audio_quality['bitrate'], 
                                '', audio_quality['audio_codec'], '', 0.0,
                                audio_quality['audio_channels'], audio_quality['sample_rate'],
                                has_metadata
                            ))
                            
                            scan_status['current_detail'] = f"MP3: {final_genre or category} | {audio_quality['bitrate']//1000}kbps"
                            scan_status['current_duration'] = f"{length} ({duration_minutes:.1f} min)"
                        
                        else:
                            # === VIDEO-VERARBEITUNG (mit Normalisierung) ===
                            path_meta = classify_path_dynamic(file_path)
                            genre, actors, comment, year = get_media_metadata_hidden(file_path)
                            video_quality = get_video_quality_info(file_path)
                            
                            # Genre normalisieren
                            final_genre = ''
                            if genre:
                                normalized = normalize_genre(genre)
                                if normalized:
                                    final_genre = normalized
                            
                            if not final_genre and path_meta.get('genre'):
                                path_genre = path_meta['genre']
                                normalized = normalize_genre(path_genre)
                                if normalized:
                                    final_genre = normalized
                                    scan_status['path_metadata_used'] += 1
                            
                            if not year and path_meta.get('year'):
                                year = path_meta['year']
                            if not actors:
                                actors = path_meta.get('sub_genre') or path_meta.get('series') or ''
                            
                            category = path_meta.get('main_category', 'Video')
                            if category:
                                scan_status['medientyp_erkannt'] += 1
                            
                            length = get_media_duration(file_path)
                            duration_minutes = 0
                            try:
                                duration_minutes = float(length.replace(' min', '').replace('min', '').strip())
                                scan_status['total_duration_found'] += duration_minutes
                            except:
                                scan_status['duration_errors'] += 1
                                length = "0 min"
                            
                            has_metadata = 1 if (final_genre and year) else 0
                                
                            media_files.append((
                                os.path.basename(file_path), file_path, parent_folder, 
                                '', '', year or '', 
                                final_genre or '',  # ← NORMALISIERTES Genre!
                                length, '', actors or '', comment or '',
                                category, file_size, video_quality['bitrate'],
                                video_quality['video_codec'], video_quality['audio_codec'],
                                video_quality['resolution'], video_quality['fps'],
                                video_quality['audio_channels'], video_quality['sample_rate'],
                                has_metadata
                            ))
                            
                            resolution_text = video_quality['resolution'] or 'N/A'
                            codec_text = video_quality['video_codec'] or 'N/A'
                            scan_status['current_detail'] = f"VIDEO: {category} | {resolution_text} | {codec_text}"
                            scan_status['current_duration'] = f"{length} ({duration_minutes:.1f} min)"

                        scan_status['total_scanned'] += 1
                        scan_status['new_files_count'] += 1
                        scan_status['quality_analyzed'] += 1

                        # Batch-Insert
                        if len(media_files) >= batch_size:
                            cursor.executemany('''
                                INSERT INTO media_files (
                                    filename, filepath, container, album, track_number, 
                                    year, genre, length, contributors, actors, comment,
                                    category, file_size, bitrate, video_codec, audio_codec,
                                    resolution, fps, audio_channels, sample_rate, has_metadata
                                )
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            ''', media_files)
                            conn.commit()
                            media_files = []
                            print(f"Batch gespeichert: {main_dir_name} - {scan_status['current_file_count']}/{scan_status['total_files']}")

                    except Exception as e:
                        print(f"Fehler bei {file_path}: {e}")
                        scan_status['duration_errors'] += 1
                        continue
                
                scan_status['main_dirs_completed'] = main_dir_idx

            # Letzter Batch
            if media_files and not stop_scanning.is_set():
                try:
                    cursor.executemany('''
                        INSERT INTO media_files (
                            filename, filepath, container, album, track_number, 
                            year, genre, length, contributors, actors, comment,
                            category, file_size, bitrate, video_codec, audio_codec,
                            resolution, fps, audio_channels, sample_rate, has_metadata
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', media_files)
                    conn.commit()
                except Exception as e:
                    print(f"Fehler beim Einfügen der letzten Batch: {e}")

            # Cleanup
            if not stop_scanning.is_set():
                print(f"\n=== STARTE CLEANUP FÜR: {current_scan_path} ===")
                scan_status['cleanup_phase'] = True
                
                deleted_files = db_files_in_scope - all_current_files
                
                if deleted_files:
                    delete_batch_size = 100
                    deleted_list = list(deleted_files)
                    
                    for i in range(0, len(deleted_list), delete_batch_size):
                        if stop_scanning.is_set():
                            break
                        
                        batch = deleted_list[i:i + delete_batch_size]
                        placeholders = ','.join('?' * len(batch))
                        
                        cursor.execute(f"DELETE FROM media_files WHERE filepath IN ({placeholders})", batch)
                        conn.commit()
                        
                        scan_status['deleted_files_count'] += len(batch)

            conn.close()
            scan_status['is_running'] = False
            root._scan_in_progress = False
            
            if not stop_scanning.is_set():
                root.after(0, lambda: show_scan_complete_dialog())

        except Exception as e:
            print(f"Scanning-Thread Fehler: {e}")
            import traceback
            traceback.print_exc()
            scan_status['is_running'] = False
            root._scan_in_progress = False

    def show_scan_complete_dialog():
        if progress_window.winfo_exists():
            cleanup_progress_window(progress_window)
        
        winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
        play_tts_message()
        
        total_hours = int(scan_status['total_duration_found'] / 60)
        total_minutes = int(scan_status['total_duration_found'] % 60)
        
        summary_message = (
            f"Scan abgeschlossen!\n\n"
            f"SCAN ERGEBNISSE:\n"
            f"Hauptverzeichnisse: {scan_status['main_dirs_total']}\n"
            f"Dateien gescannt: {scan_status['total_scanned']}\n"
            f"Neue Dateien: {scan_status['new_files_count']}\n"
            f"Übersprungen: {scan_status['updated_files_count']}\n"
            f"Qualität analysiert: {scan_status['quality_analyzed']}\n"
            f"Pfad-Metadaten genutzt: {scan_status['path_metadata_used']}\n"
            f"Medientypen erkannt: {scan_status['medientyp_erkannt']}\n\n"
            f"BEREINIGUNG:\n"
            f"Gelöschte Einträge: {scan_status['deleted_files_count']}\n"
            f"(Nur im Scan-Pfad: {folder_path})\n\n"
            f"LAUFZEIT:\n"
            f"Gesamtlaufzeit: {total_hours}h {total_minutes}m\n"
            f"Fehler: {scan_status['duration_errors']}"
        )
        messagebox.showinfo("Scan Abgeschlossen", summary_message)

    progress_window.after(100, update_gui_from_main_thread)
    
    scan_thread = threading.Thread(target=run_ffprobe, daemon=True)
    scan_thread.start()
    
def get_enhanced_collection_statistics():
    """
    KORRIGIERT: Verwendet tatsächliche Metadaten aus Datenbank
    """
    try:
        conn = sqlite3.connect('media_index.db')
        cursor = conn.cursor()
        
        # === KATEGORIE-EBENE (Hauptebene) ===
        cursor.execute("""
            SELECT 
                category,
                COUNT(*) as file_count,
                SUM(CAST(REPLACE(REPLACE(length, ' min', ''), 'min', '') AS REAL)) as total_duration,
                SUM(file_size) as total_size,
                AVG(bitrate) as avg_bitrate,
                COUNT(CASE WHEN has_metadata = 1 THEN 1 END) as files_with_metadata
            FROM media_files
            WHERE category != '' AND category IS NOT NULL
            GROUP BY category
            ORDER BY file_count DESC
        """)
        
        category_stats = {}
        for row in cursor.fetchall():
            category, count, duration, size, bitrate, metadata_count = row
            category_stats[category] = {
                'count': count,
                'duration': duration or 0,
                'size': size or 0,
                'avg_bitrate': bitrate or 0,
                'metadata_completeness': (metadata_count / count * 100) if count > 0 else 0
            }
        
        # === KORRIGIERT: GENRE DIREKT AUS DATENBANK ===
        cursor.execute("""
            SELECT 
                category,
                genre,
                COUNT(*) as file_count,
                SUM(CAST(REPLACE(REPLACE(length, ' min', ''), 'min', '') AS REAL)) as total_duration,
                SUM(file_size) as total_size,
                AVG(bitrate) as avg_bitrate
            FROM media_files
            WHERE category != '' AND category IS NOT NULL
              AND genre != '' AND genre IS NOT NULL
            GROUP BY category, genre
            ORDER BY category, file_count DESC
        """)
        
        genre_by_category = defaultdict(list)
        for row in cursor.fetchall():
            category, genre, count, duration, size, bitrate = row
            genre_by_category[category].append({
                'genre': genre,
                'count': count,
                'duration': duration or 0,
                'size': size or 0,
                'avg_bitrate': bitrate or 0
            })
        
        # === QUALITÃƒâ€žTS-STATISTIKEN ===
        # Video-Formate
        cursor.execute("""
            SELECT 
                video_codec,
                resolution,
                COUNT(*) as count,
                AVG(bitrate) as avg_bitrate
            FROM media_files
            WHERE video_codec != '' AND category IN ('Filme', 'Serien', 'Video')
            GROUP BY video_codec, resolution
            ORDER BY count DESC
        """)
        video_quality_stats = cursor.fetchall()
        
        # Audio-Formate
        cursor.execute("""
            SELECT 
                audio_codec,
                sample_rate,
                COUNT(*) as count,
                AVG(bitrate) as avg_bitrate
            FROM media_files
            WHERE audio_codec != '' AND category IN ('Musik', 'Audio')
            GROUP BY audio_codec, sample_rate
            ORDER BY count DESC
        """)
        audio_quality_stats = cursor.fetchall()
        
        # === DATEI-EXTENSIONS ===
        cursor.execute("SELECT filepath FROM media_files")
        filepaths = cursor.fetchall()
        file_extensions = {}
        for (filepath,) in filepaths:
            ext = os.path.splitext(filepath)[1].lower()
            if ext:
                file_extensions[ext] = file_extensions.get(ext, 0) + 1
        
        # === JAHRE-STATISTIKEN ===
        cursor.execute("""
            SELECT year, COUNT(*) 
            FROM media_files 
            WHERE year != '' AND year != '0' 
            GROUP BY year 
            ORDER BY year DESC
        """)
        year_stats = cursor.fetchall()
        
        # === GESAMTSTATISTIKEN ===
        cursor.execute("SELECT COUNT(*) FROM media_files")
        total_files = cursor.fetchone()[0]
        
        cursor.execute("""
            SELECT SUM(CAST(REPLACE(REPLACE(length, ' min', ''), 'min', '') AS REAL))
            FROM media_files
        """)
        total_duration = cursor.fetchone()[0] or 0
        
        cursor.execute("SELECT SUM(file_size) FROM media_files")
        total_size = cursor.fetchone()[0] or 0
        
        # === METADATEN-VOLLSTÃƒNDIGKEIT ===
        cursor.execute("""
            SELECT 
                COUNT(CASE WHEN has_metadata = 1 THEN 1 END) * 100.0 / COUNT(*) as completeness
            FROM media_files
        """)
        metadata_completeness = cursor.fetchone()[0] or 0
        
        # === DUPLIKATE ===
        cursor.execute("""
            SELECT file_size, COUNT(*) as duplicate_count
            FROM media_files
            WHERE file_size > 0
            GROUP BY file_size
            HAVING COUNT(*) > 1
            ORDER BY duplicate_count DESC
            LIMIT 20
        """)
        potential_duplicates = cursor.fetchall()
        
        # === GENRE-STATS (für Kompatibilität mit altem Code) ===
        # KORRIGIERT: Direkt aus DB statt Pfad-Analyse
        cursor.execute("""
            SELECT genre, COUNT(*) 
            FROM media_files 
            WHERE genre != '' AND genre IS NOT NULL
            GROUP BY genre 
            ORDER BY COUNT(*) DESC
        """)
        genre_stats = cursor.fetchall()
        
        # === MEDIENTYP-STATS ===
        cursor.execute("""
            SELECT 
                category,
                COUNT(*) as count,
                SUM(CAST(REPLACE(REPLACE(length, ' min', ''), 'min', '') AS REAL)) as total_duration
            FROM media_files
            WHERE category != ''
            GROUP BY category
        """)
        media_type_stats = [(row[0], row[1], row[2] or 0) for row in cursor.fetchall()]
        
        # === HIERARCHIE ===
        cursor.execute("SELECT filepath, filename FROM media_files")
        paths_and_files = cursor.fetchall()
        hierarchy = analyze_enhanced_path_hierarchy(paths_and_files)
        
        conn.close()
        
        return {
            'total_files': total_files,
            'total_duration': total_duration,
            'total_size': total_size,
            'metadata_completeness': metadata_completeness,
            'category_stats': category_stats,
            'genre_by_category': genre_by_category,
            'video_quality_stats': video_quality_stats,
            'audio_quality_stats': audio_quality_stats,
            'file_extensions': file_extensions,
            'year_stats': year_stats,
            'potential_duplicates': potential_duplicates,
            'genre_stats': genre_stats,
            'media_type_stats': media_type_stats,
            'hierarchy': hierarchy,
            'processed_duration_count': total_files,
            'duration_errors': 0
        }
        
    except Exception as e:
        print(f"Fehler beim Laden der erweiterten Statistiken: {e}")
        import traceback
        traceback.print_exc()
        return None

def get_video_quality_info(file_path):
    """
    Extrahiert Video-Qualitätsinformationen
    KORRIGIERT: Ignoriert MJPEG Cover-Art Streams
    """
    try:
        metadata = ffprobe_file(file_path)
        
        video_info = {
            'video_codec': '',
            'resolution': '',
            'fps': 0.0,
            'bitrate': 0,
            'audio_codec': '',
            'audio_channels': 0,
            'sample_rate': 0
        }
        
        # KRITISCH: Finde echten Video-Stream (nicht Cover-Art)
        video_stream = None
        audio_stream = None
        
        for stream in metadata.get('streams', []):
            codec_type = stream.get('codec_type')
            
            if codec_type == 'video':
                codec_name = stream.get('codec_name', '').lower()
                disposition = stream.get('disposition', {})
                
                # FILTER: Überspringe MJPEG Cover-Art
                if codec_name == 'mjpeg' and disposition.get('attached_pic') == 1:
                    continue
                
                # FILTER: Überspringe sehr kleine Auflösungen (wahrscheinlich Thumbnails)
                width = stream.get('width', 0)
                height = stream.get('height', 0)
                if width > 0 and height > 0 and (width < 640 or height < 360):
                    # Behalte als Fallback, falls kein besserer Stream existiert
                    if video_stream is None:
                        video_stream = stream
                    continue
                
                # Primärer Video-Stream gefunden
                video_stream = stream
                break  # Nimm ersten echten Video-Stream
                
            elif codec_type == 'audio' and audio_stream is None:
                audio_stream = stream
        
        # Video-Informationen extrahieren
        if video_stream:
            video_info['video_codec'] = video_stream.get('codec_name', '')
            
            width = video_stream.get('width', 0)
            height = video_stream.get('height', 0)
            if width and height:
                video_info['resolution'] = f"{width}x{height}"
            
            # FPS berechnen
            fps_str = video_stream.get('r_frame_rate', '0/1')
            try:
                num, den = fps_str.split('/')
                if int(den) > 0:
                    video_info['fps'] = round(int(num) / int(den), 2)
            except:
                pass
            
            # Video-Bitrate
            bitrate = video_stream.get('bit_rate')
            if bitrate:
                video_info['bitrate'] = int(bitrate)
        
        # Audio-Informationen
        if audio_stream:
            video_info['audio_codec'] = audio_stream.get('codec_name', '')
            video_info['audio_channels'] = audio_stream.get('channels', 0)
            video_info['sample_rate'] = audio_stream.get('sample_rate', 0)
        
        # Fallback: Format-Bitrate wenn Stream-Bitrate fehlt
        if video_info['bitrate'] == 0:
            format_bitrate = metadata.get('format', {}).get('bit_rate')
            if format_bitrate:
                video_info['bitrate'] = int(format_bitrate)
        
        return video_info
        
    except Exception as e:
        print(f"Fehler bei Video-Qualitätsanalyse für {file_path}: {e}")
        return {
            'video_codec': '',
            'resolution': '',
            'fps': 0.0,
            'bitrate': 0,
            'audio_codec': '',
            'audio_channels': 0,
            'sample_rate': 0
        }

def get_audio_quality_info(file_path):
    """Extrahiert Audio-Qualitätsinformationen"""
    try:
        audio = MP3(file_path)
        
        audio_info = {
            'bitrate': 0,
            'sample_rate': 0,
            'audio_channels': 0,
            'audio_codec': 'mp3'
        }
        
        if hasattr(audio.info, 'bitrate'):
            audio_info['bitrate'] = audio.info.bitrate
        if hasattr(audio.info, 'sample_rate'):
            audio_info['sample_rate'] = audio.info.sample_rate
        if hasattr(audio.info, 'channels'):
            audio_info['audio_channels'] = audio.info.channels
            
        return audio_info
        
    except Exception as e:
        print(f"Fehler bei Audio-Qualitätsanalyse für {file_path}: {e}")
        return {
            'bitrate': 0,
            'sample_rate': 0,
            'audio_channels': 0,
            'audio_codec': 'mp3'
        }

def test_single_file_duration():
    """Test-Funktion für einzelne Datei-Laufzeit"""
    if not folder_path:
        messagebox.showwarning("Warnung", "Bitte wählen Sie zuerst einen Ordner aus")
        return
    
    # Finde erste Video-Datei
    video_extensions = ('.mp4', '.mkv', '.avi', '.mov', '.wmv', '.flv')
    test_file = None
    
    for root_dir, _, files in os.walk(folder_path):
        for file in files:
            if file.lower().endswith(video_extensions):
                test_file = os.path.join(root_dir, file)
                break
        if test_file:
            break
    
    if not test_file:
        messagebox.showinfo("Info", "Keine Video-Datei gefunden")
        return
    
    # Teste verschiedene Methoden
    result_text = f"=== LAUFZEIT-TEST für {os.path.basename(test_file)} ===\n\n"
    
    # Test 1: Direkte get_media_duration
    duration1 = get_media_duration(test_file)
    result_text += f"get_media_duration(): '{duration1}'\n"
    
    # Test 2: Enhanced Metadata
    enhanced_result = get_enhanced_metadata(test_file)
    duration2 = enhanced_result[4] if len(enhanced_result) > 4 else "FEHLT"
    result_text += f"get_enhanced_metadata(): '{duration2}'\n"
    
    # Test 3: ffprobe direkt
    try:
        result = subprocess.run(
            [ffprobe_path, '-v', 'error', '-show_entries', 'format=duration', 
             '-of', 'default=noprint_wrappers=1:nokey=1', test_file],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            creationflags=subprocess.CREATE_NO_WINDOW, timeout=30
        )
        duration3 = result.stdout.strip()
        result_text += f"ffprobe direkt: '{duration3}'\n"
    except Exception as e:
        result_text += f"ffprobe direkt: FEHLER - {e}\n"
    
    # Konvertierung testen
    try:
        clean_duration = duration1.replace(' min', '').replace('min', '').strip()
        converted = float(clean_duration)
        result_text += f"\nKonvertierung erfolgreich: {converted} Minuten\n"
        result_text += f"Das sind {int(converted/60)}h {int(converted%60)}m\n"
    except Exception as e:
        result_text += f"\nKonvertierungs-FEHLER: {e}\n"
    
    # Zeige Ergebnis
    messagebox.showinfo("Laufzeit-Test", result_text)

def play_tts_message():
    """Thread-sichere TTS-Nachricht"""
    def tts_worker():
        try:
            engine = pyttsx3.init()
            engine.say("Database training is complete!")
            engine.runAndWait()
            engine.stop()
            del engine  # Explizit löschen
        except Exception as e:
            print(f"Text-to-Speech error: {e}")
    
    # Als Daemon-Thread starten (wird automatisch beendet)
    tts_thread = threading.Thread(target=tts_worker, daemon=True)
    tts_thread.start()

def get_media_metadata_hidden(file_path):
    metadata = ffprobe_file(file_path)
    format_info = metadata.get('format', {})

    genre = format_info.get('tags', {}).get('genre', '')  
    actors = format_info.get('tags', {}).get('artist', '')  
    comment = format_info.get('tags', {}).get('comment', '')
    year = format_info.get('tags', {}).get('date', '')

    print(f"Extracted metadata for {file_path}: genre={genre}, actors={actors}, comment={comment}, year={year}")

    return genre, actors, comment, year

def toggle_search_options():
    """
    KORRIGIERT: Zeigt Warnung wenn DB-Suche aktiv aber keine Felder gewählt
    """
    state = tk.NORMAL if use_db_var.get() else tk.DISABLED
    
    if title_checkbox:
        title_checkbox.config(state=state)
    if genre_checkbox:
        genre_checkbox.config(state=state)
    if actors_checkbox:
        actors_checkbox.config(state=state)
    if comment_checkbox:
        comment_checkbox.config(state=state)
    if album_checkbox:
        album_checkbox.config(state=state)
    if interpret_checkbox:
        interpret_checkbox.config(state=state)
    
    # Warnung wenn DB-Suche aktiv aber keine Felder
    if use_db_var.get():
        any_selected = (title_search_var.get() or genre_var.get() or 
                       actors_var.get() or comment_var.get() or 
                       album_search_var.get() or interpret_search_var.get())
        
        if not any_selected and settings_window and settings_window.winfo_exists():
            # Zeige Hinweis im Settings-Fenster
            try:
                for widget in settings_window.winfo_children():
                    if isinstance(widget, tk.Label) and "Suchfelder" in widget.cget("text"):
                        widget.destroy()
            except:
                pass
            
            warning_label = tk.Label(
                settings_window, 
                text="⚠️ Bitte wählen Sie mindestens ein Suchfeld aus!",
                font=('Arial', 9, 'bold'),
                fg='red'
            )
            # Finde Position nach den Checkboxen
            try:
                if interpret_checkbox and interpret_checkbox.winfo_exists():
                    warning_label.pack(after=interpret_checkbox, pady=5)
            except:
                pass

def test_database_search():
    """
    Debug-Funktion: Testet Datenbank-Verbindung und Inhalte
    Kann in Debug-Mode zu Settings hinzugefügt werden
    """
    try:
        conn = sqlite3.connect('media_index.db')
        cursor = conn.cursor()
        
        # Basis-Statistiken
        cursor.execute("SELECT COUNT(*) FROM media_files")
        total = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(DISTINCT filepath) FROM media_files")
        unique_paths = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM media_files WHERE filepath LIKE ?", (f"{folder_path}%",))
        in_current_path = cursor.fetchone()[0]
        
        # Beispiel-Einträge
        cursor.execute("SELECT filename, genre, actors, album FROM media_files LIMIT 5")
        samples = cursor.fetchall()
        
        conn.close()
        
        # Zeige Ergebnisse
        debug_info = f"""DATENBANK-TEST
        
Gesamt-Einträge: {total}
Eindeutige Pfade: {unique_paths}
Im aktuellen Pfad: {in_current_path}

Pfad: {folder_path}

Beispiel-Einträge:
"""
        for filename, genre, actors, album in samples:
            debug_info += f"\n• {filename}"
            debug_info += f"\n  Genre: {genre or 'N/A'}"
            debug_info += f"\n  Actors: {actors or 'N/A'}"
            debug_info += f"\n  Album: {album or 'N/A'}\n"
        
        messagebox.showinfo("Datenbank-Test", debug_info)
        print(debug_info)
        
    except Exception as e:
        messagebox.showerror("DB-Test Fehler", f"Fehler:\n{e}")

def debug_video_metadata():
    """Debug-Funktion für Video-Metadaten - korrigiert für neue Pfad-Klassifizierung"""
    debug_file_path = os.path.join(os.getcwd(), "debug_metadata.txt")
    
    if not folder_path:
        with open(debug_file_path, 'w', encoding='utf-8') as f:
            f.write("Kein Ordner ausgewählt\n")
        print("Debug-Datei erstellt: debug_metadata.txt")
        return
        
    video_extensions = ('.mp4', '.mkv', '.avi', '.mov', '.wmv', '.flv')
    audio_extensions = ('.mp3',)
    
    with open(debug_file_path, 'w', encoding='utf-8') as debug_file:
        debug_file.write("=== METADATA DEBUG REPORT MIT NEUER PFAD-KLASSIFIZIERUNG ===\n")
        debug_file.write(f"Ordner: {folder_path}\n")
        debug_file.write(f"Zeit: {threading.current_thread().name}\n\n")
        
        video_count = 0
        audio_count = 0
        total_video_duration = 0
        total_audio_duration = 0
        
        for root_dir, _, files in os.walk(folder_path):
            for file in files:
                if video_count < 10 and file.lower().endswith(video_extensions):
                    file_path = os.path.join(root_dir, file)
                    debug_file.write(f"\n=== VIDEO FILE: {file} ===\n")
                    debug_file.write(f"Pfad: {file_path}\n")
                    
                    # NEU: Erweiterte Pfad-Metadaten mit Medientyp
                    path_meta = classify_path_dynamic(file_path)
                    debug_file.write(f"Pfad-Klassifizierung: {path_meta}\n")
                    debug_file.write(f"Erkannter Medientyp: '{path_meta.get('media_type', 'Unbekannt')}'\n")
                    debug_file.write(f"Pfad-Genre: '{path_meta.get('genre', '')}'\n")
                    debug_file.write(f"Pfad-Serien: '{path_meta.get('series', '')}'\n")
                    debug_file.write(f"Pfad-Jahr: '{path_meta.get('year', '')}'\n")
                    debug_file.write(f"Pfad-Titel: '{path_meta.get('title', '')}'\n")
                    
                    # ffprobe Metadaten
                    genre, actors, comment, year = get_media_metadata_hidden(file_path)
                    debug_file.write(f"ffprobe Genre: '{genre}'\n")
                    debug_file.write(f"ffprobe Actors: '{actors}'\n")
                    debug_file.write(f"ffprobe Comment: '{comment}'\n")
                    debug_file.write(f"ffprobe Year: '{year}'\n")
                    
                    # LAUFZEIT TESTEN
                    debug_file.write(f"\n--- LAUFZEIT TESTS ---\n")
                    duration = get_media_duration(file_path)
                    debug_file.write(f"get_media_duration(): '{duration}'\n")
                    
                    # Enhanced Metadata testen
                    enhanced_result = get_enhanced_metadata(file_path)
                    debug_file.write(f"get_enhanced_metadata(): {len(enhanced_result)} Werte\n")
                    debug_file.write(f"Enhanced Laufzeit: '{enhanced_result[4] if len(enhanced_result) > 4 else 'FEHLT!'}'\n")
                    
                    # NEU: Zeige Fallback-Logik
                    final_genre = enhanced_result[0] if len(enhanced_result) > 0 else ''
                    final_year = enhanced_result[3] if len(enhanced_result) > 3 else ''
                    debug_file.write(f"Finales Genre (nach Fallback): '{final_genre}'\n")
                    debug_file.write(f"Finales Jahr (nach Fallback): '{final_year}'\n")
                    
                    # Zur Gesamtsumme hinzufügen
                    try:
                        duration_value = float(duration.replace(' min', '').replace('min', '').strip())
                        total_video_duration += duration_value
                    except Exception as e:
                        debug_file.write(f"FEHLER: Konnte Laufzeit nicht parsen: '{duration}' - {e}\n")
                    
                    video_count += 1
                    
                elif audio_count < 5 and file.lower().endswith(audio_extensions):
                    file_path = os.path.join(root_dir, file)
                    debug_file.write(f"\n=== AUDIO FILE: {file} ===\n")
                    debug_file.write(f"Pfad: {file_path}\n")
                    
                    # NEU: MP3 Pfad-Klassifizierung
                    path_meta = classify_path_dynamic(file_path)
                    debug_file.write(f"Pfad-Klassifizierung: {path_meta}\n")
                    debug_file.write(f"Erkannter Medientyp: '{path_meta.get('media_type', 'Unbekannt')}'\n")
                    debug_file.write(f"Pfad-Album: '{path_meta.get('album', '')}'\n")
                    debug_file.write(f"Pfad-Genre: '{path_meta.get('genre', '')}'\n")
                    
                    # MP3 Metadaten
                    album, track, year, genre, contributors, length = get_mp3_metadata_with_timeout(file_path)
                    debug_file.write(f"MP3 Album: '{album}'\n")
                    debug_file.write(f"MP3 Track: '{track}'\n")
                    debug_file.write(f"MP3 Year: '{year}'\n")
                    debug_file.write(f"MP3 Genre: '{genre}'\n")
                    debug_file.write(f"MP3 Contributors: '{contributors}'\n")
                    debug_file.write(f"MP3 Laufzeit: '{length}'\n")
                    
                    # Enhanced Metadata testen
                    enhanced_result = get_enhanced_metadata(file_path)
                    debug_file.write(f"Enhanced MP3: {len(enhanced_result)} Werte\n")
                    debug_file.write(f"Enhanced Laufzeit: '{enhanced_result[5] if len(enhanced_result) > 5 else 'FEHLT!'}'\n")
                    
                    # NEU: Zeige Album-Fallback
                    final_album = enhanced_result[0] if len(enhanced_result) > 0 else ''
                    debug_file.write(f"Finales Album (nach Fallback): '{final_album}'\n")
                    
                    # Zur Gesamtsumme hinzufügen
                    try:
                        duration_value = float(length.replace(' min', '').replace('min', '').strip())
                        total_audio_duration += duration_value
                    except Exception as e:
                        debug_file.write(f"FEHLER: Konnte MP3-Laufzeit nicht parsen: '{length}' - {e}\n")
                    
                    audio_count += 1
        
        debug_file.write(f"\n=== ERWEITERTE LAUFZEIT SUMMARY ===\n")
        debug_file.write(f"Video-Dateien analysiert: {video_count}\n")
        debug_file.write(f"Audio-Dateien analysiert: {audio_count}\n")
        debug_file.write(f"Gesamt Video-Laufzeit: {total_video_duration} min ({int(total_video_duration/60)}h {int(total_video_duration%60)}m)\n")
        debug_file.write(f"Gesamt Audio-Laufzeit: {total_audio_duration} min ({int(total_audio_duration/60)}h {int(total_audio_duration%60)}m)\n")
        debug_file.write(f"Gesamtlaufzeit aller Dateien: {total_video_duration + total_audio_duration} min\n")
        
        # NEU: Medientyp-Statistiken
        debug_file.write(f"\n=== MEDIENTYP ERKENNUNG ===\n")
        debug_file.write(f"Neue Pfad-Klassifizierung implementiert\n")
        debug_file.write(f"Unterstützte Medientypen: Filme, Serien, Musik\n")
        debug_file.write(f"Genre-Validierung: {len(KNOWN_GENRES)} bekannte Genres\n")
    
    print(f"Debug-Datei erstellt: {debug_file_path}")
    messagebox.showinfo("Debug Abgeschlossen", f"Erweiterte Debug-Informationen mit neuer Pfad-Klassifizierung in {debug_file_path} gespeichert")

def get_collection_statistics():
    """
    KORRIGIERT: Dynamische Genre-Statistik ohne statische Kategorien
    """
    try:
        conn = sqlite3.connect('media_index.db')
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM media_files")
        total_files = cursor.fetchone()[0]
        
        # Laufzeit-Auswertung (unverändert)
        cursor.execute("SELECT length FROM media_files WHERE length != '' AND length IS NOT NULL")
        all_durations = cursor.fetchall()
        
        total_duration = 0
        processed_count = 0
        error_count = 0
        
        for (length_str,) in all_durations:
            if length_str and length_str != 'Unbekannt':
                try:
                    clean_length = length_str.replace(' min', '').replace('min', '').replace(' ', '').strip()
                    if clean_length and clean_length != '0':
                        duration_value = float(clean_length)
                        total_duration += duration_value
                        processed_count += 1
                except (ValueError, TypeError) as e:
                    error_count += 1
        
        # Dateitypen
        cursor.execute("SELECT filepath FROM media_files")
        filepaths = cursor.fetchall()
        file_extensions = {}
        for (filepath,) in filepaths:
            ext = os.path.splitext(filepath)[1].lower()
            if ext:
                file_extensions[ext] = file_extensions.get(ext, 0) + 1
        
        # KORRIGIERT: Vollständig dynamische Genre-Statistik
        cursor.execute("SELECT filepath, genre FROM media_files")
        all_file_paths = cursor.fetchall()
        
        genre_counter = Counter()
        main_category_counter = Counter()  # NEU: Hauptkategorien separat
        
        for filepath, file_genre in all_file_paths:
            # Pfad-Analyse für jede Datei
            path_meta = classify_path_dynamic(filepath)
            
            # Sammle Hauptkategorie
            if path_meta.get('main_category'):
                main_category_counter[path_meta['main_category']] += 1
            
            # Genre-Zählung (dynamisch aus Pfad)
            genre_found = False
            
            # 1. Priorität: Haupt-Genre aus Pfad
            if path_meta.get('genre'):
                genre_counter[path_meta['genre']] += 1
                genre_found = True
            
            # 2. Falls kein Pfad-Genre: Datei-Genre verwenden
            if not genre_found and file_genre:
                genre_counter[file_genre] += 1
                genre_found = True
            
            # 3. Falls immer noch nichts: Sub-Genre verwenden
            if not genre_found and path_meta.get('sub_genre'):
                genre_counter[path_meta['sub_genre']] += 1
        
        # Konvertiere zu sortierten Listen
        genre_stats = genre_counter.most_common()
        main_category_stats = main_category_counter.most_common()  # NEU
        
        # Jahre, Actors, etc. (unverändert)
        cursor.execute("SELECT year, COUNT(*) FROM media_files WHERE year != '' AND year != '0' GROUP BY year ORDER BY year DESC")
        year_stats = cursor.fetchall()
        
        cursor.execute("SELECT actors, COUNT(*) FROM media_files WHERE actors != '' GROUP BY actors ORDER BY COUNT(*) DESC")
        actors_stats = cursor.fetchall()
        
        cursor.execute("SELECT album, COUNT(*) FROM media_files WHERE album != '' GROUP BY album ORDER BY COUNT(*) DESC")
        album_stats = cursor.fetchall()
        
        cursor.execute("SELECT contributors, COUNT(*) FROM media_files WHERE contributors != '' GROUP BY contributors ORDER BY COUNT(*) DESC")
        contributors_stats = cursor.fetchall()
        
        cursor.execute("SELECT container, COUNT(*) FROM media_files WHERE container != '' GROUP BY container ORDER BY COUNT(*) DESC")
        container_stats = cursor.fetchall()
        
        # Medientyp-Statistiken (unverändert)
        cursor.execute("""
            SELECT 
                CASE 
                    WHEN LOWER(filepath) LIKE '%.mp3' THEN 'Audio'
                    WHEN LOWER(filepath) LIKE '%.mp4' OR LOWER(filepath) LIKE '%.mkv' OR LOWER(filepath) LIKE '%.avi' OR LOWER(filepath) LIKE '%.mov' OR LOWER(filepath) LIKE '%.wmv' OR LOWER(filepath) LIKE '%.flv' THEN 'Video'
                    ELSE 'Andere'
                END as media_type,
                COUNT(*) as count,
                GROUP_CONCAT(length) as all_durations
            FROM media_files 
            GROUP BY media_type
        """)
        
        media_type_results = cursor.fetchall()
        media_type_stats = []
        
        for media_type, count, all_durations_str in media_type_results:
            type_duration = 0
            if all_durations_str:
                durations = all_durations_str.split(',')
                for duration_str in durations:
                    if duration_str and duration_str != 'Unbekannt':
                        try:
                            clean_duration = duration_str.replace(' min', '').replace('min', '').strip()
                            if clean_duration and clean_duration != '0':
                                type_duration += float(clean_duration)
                        except (ValueError, TypeError):
                            pass
            
            media_type_stats.append((media_type, count, type_duration))
        
        # Hierarchie
        cursor.execute("SELECT filepath, filename FROM media_files")
        paths_and_files = cursor.fetchall()
        hierarchy = analyze_enhanced_path_hierarchy(paths_and_files)
        
        conn.close()
        
        return {
            'total_files': total_files,
            'total_duration': total_duration,
            'processed_duration_count': processed_count,
            'duration_errors': error_count,
            'file_extensions': file_extensions,
            'genre_stats': genre_stats,
            'main_category_stats': main_category_stats,  # NEU
            'year_stats': year_stats,
            'actors_stats': actors_stats,
            'album_stats': album_stats,
            'contributors_stats': contributors_stats,
            'container_stats': container_stats,
            'media_type_stats': media_type_stats,
            'hierarchy': hierarchy
        }
    except Exception as e:
        print(f"Fehler beim Laden der Statistiken: {e}")
        import traceback
        traceback.print_exc()
        return None

def analyze_enhanced_path_hierarchy(paths_and_files):
    """
    KORRIGIERT: Robuste dynamische Hierarchie-Analyse mit beliebiger Tiefe
    Verhindert 'children' KeyError bei tiefen Verschachtelungen
    """
    def create_node():
        """Factory-Funktion für konsistente Node-Struktur"""
        return {
            'count': 0,
            'files': [],
            'children': {}
        }
    
    hierarchy = defaultdict(create_node)
    
    for filepath, filename in paths_and_files:
        try:
            path_meta = classify_path_dynamic(filepath)
            
            main_cat = path_meta.get('main_category')
            genre = path_meta.get('genre')
            sub_genre = path_meta.get('sub_genre')
            
            if not main_cat:
                continue
            
            # Initialisiere Hauptkategorie falls nötig
            if main_cat not in hierarchy:
                hierarchy[main_cat] = create_node()
            
            hierarchy[main_cat]['count'] += 1
            
            if genre:
                # Initialisiere Genre falls nötig
                if genre not in hierarchy[main_cat]['children']:
                    hierarchy[main_cat]['children'][genre] = create_node()
                
                hierarchy[main_cat]['children'][genre]['count'] += 1
                
                if sub_genre:
                    # Bei mehreren Ebenen: Splitte und navigiere durch Baum
                    if os.sep in str(sub_genre):
                        sub_parts = str(sub_genre).split(os.sep)
                        current_level = hierarchy[main_cat]['children'][genre]['children']
                        
                        for i, sub_part in enumerate(sub_parts):
                            if not sub_part:  # Überspringe leere Parts
                                continue
                            
                            # Initialisiere Node falls nicht vorhanden
                            if sub_part not in current_level:
                                current_level[sub_part] = create_node()
                            
                            current_level[sub_part]['count'] += 1
                            
                            if i == len(sub_parts) - 1:
                                # Letzte Ebene: Datei hinzufügen
                                current_level[sub_part]['files'].append({
                                    'name': filename,
                                    'path': filepath
                                })
                            else:
                                # Navigiere eine Ebene tiefer
                                if 'children' not in current_level[sub_part]:
                                    current_level[sub_part]['children'] = {}
                                current_level = current_level[sub_part]['children']
                    else:
                        # Einfacher Sub-Genre (eine Ebene)
                        if sub_genre not in hierarchy[main_cat]['children'][genre]['children']:
                            hierarchy[main_cat]['children'][genre]['children'][sub_genre] = create_node()
                        
                        hierarchy[main_cat]['children'][genre]['children'][sub_genre]['count'] += 1
                        hierarchy[main_cat]['children'][genre]['children'][sub_genre]['files'].append({
                            'name': filename,
                            'path': filepath
                        })
                else:
                    # Datei direkt im Genre-Ordner
                    hierarchy[main_cat]['children'][genre]['files'].append({
                        'name': filename,
                        'path': filepath
                    })
            else:
                # Datei direkt in Hauptkategorie
                hierarchy[main_cat]['files'].append({
                    'name': filename,
                    'path': filepath
                })
                        
        except Exception as e:
            print(f"Fehler bei Hierarchie-Analyse für {filepath}: {e}")
            import traceback
            traceback.print_exc()
    
    # Konvertiere zurück zu dict (für Kompatibilität)
    return dict(hierarchy)

def copy_to_clipboard(text):
    """Kopiert Text in die Zwischenablage"""
    root.clipboard_clear()
    root.clipboard_append(text)

def show_in_explorer(file_path):
    """Zeigt Datei im Explorer an"""
    try:
        subprocess.run(['explorer', '/select,', os.path.normpath(file_path)], shell=True)
    except Exception as e:
        print(f"Fehler beim Öffnen des Explorers: {e}")

def create_analytics_window():
    """Erstellt das erweiterte Analytics-Fenster mit hierarchischer Struktur"""
    global analytics_window
    
    if 'analytics_window' in globals() and analytics_window and analytics_window.winfo_exists():
        analytics_window.lift()
        analytics_window.focus_force()
        return
    
    analytics_window = tk.Toplevel(root)
    analytics_window.title("Archiv-Statistiken")
    analytics_window.geometry("1200x800")
    
    try:
        print("Lade erweiterte Statistiken...")
        stats = get_enhanced_collection_statistics()
        if not stats:
            error_label = tk.Label(analytics_window, 
                                 text="Keine Datenbank gefunden.\nBitte erstellen Sie zuerst eine Datenbank und trainieren Sie sie.", 
                                 font=('Arial', 12), fg='red')
            error_label.pack(pady=50)
            return
        
        print(f"Statistiken geladen: {stats['total_files']} Dateien")
        
        notebook = ttk.Notebook(analytics_window)
        notebook.pack(fill='both', expand=True, padx=10, pady=10)
        
        # Tab 1: Dashboard (Kategorien-Übersicht)
        print("Erstelle Dashboard-Tab...")
        dashboard_frame = ttk.Frame(notebook)
        notebook.add(dashboard_frame, text="📊 Dashboard")
        create_dashboard_tab(dashboard_frame, stats)
        
        # Tab 2: Kategorien & Genres (Hierarchisch)
        print("Erstelle Kategorien-Tab...")
        categories_frame = ttk.Frame(notebook)
        notebook.add(categories_frame, text="📁 Kategorien & Genres")
        create_categories_genres_tab(categories_frame, stats)
        
        # Tab 3: Hardware & Speicher
        if matplotlib_available:
            print("Erstelle Hardware-Tab...")
            hardware_frame = ttk.Frame(notebook)
            notebook.add(hardware_frame, text="💾 Hardware & Speicher")
            create_hardware_tab(hardware_frame, stats)
        
        # Tab 4: Qualität & Wartung
        print("Erstelle Qualitäts-Tab...")
        quality_frame = ttk.Frame(notebook)
        notebook.add(quality_frame, text="⚙️ Qualität & Wartung")
        create_quality_maintenance_tab(quality_frame, stats)
        
        # Tab 5: Ordnerstruktur (bestehend)
        print("Erstelle Hierarchie-Tab...")
        hierarchy_frame = ttk.Frame(notebook)
        notebook.add(hierarchy_frame, text="🗂️ Ordnerstruktur")
        
        # Alte Hierarchie-Daten holen
        conn = sqlite3.connect('media_index.db')
        cursor = conn.cursor()
        cursor.execute("SELECT filepath, filename FROM media_files")
        paths_and_files = cursor.fetchall()
        conn.close()
        hierarchy = analyze_enhanced_path_hierarchy(paths_and_files)
        
        old_stats = {'hierarchy': hierarchy, 'total_files': stats['total_files']}
        create_hierarchy_tab(hierarchy_frame, old_stats)
        
        print("Analytics-Fenster erfolgreich erstellt")
        
    except Exception as e:
        print(f"Fehler beim Erstellen des Analytics-Fensters: {e}")
        import traceback
        traceback.print_exc()
        
        error_label = tk.Label(analytics_window, text=f"Fehler beim Laden der Statistiken:\n{str(e)}", 
                             font=('Arial', 10), fg='red')
        error_label.pack(pady=20)

def create_quality_maintenance_tab(parent, stats):
    """Tab fÃ¼r QualitÃ¤t & Wartung"""
    
    paned = ttk.PanedWindow(parent, orient=tk.VERTICAL)
    paned.pack(fill='both', expand=True)
    
    # === QUALITÃ„TS-METRIKEN ===
    quality_frame = tk.LabelFrame(paned, text="QualitÃ¤ts-Ãœbersicht", font=('Arial', 14, 'bold'))
    paned.add(quality_frame, weight=2)
    
    quality_container = tk.Frame(quality_frame)
    quality_container.pack(fill='both', expand=True, padx=10, pady=10)
    
    # Metrics-Grid
    metrics_frame = tk.Frame(quality_container)
    metrics_frame.pack(fill='x', pady=(0, 10))
    
    # Metadaten-Vollständigkeit
    metadata_box = tk.LabelFrame(metrics_frame, text="Metadaten", relief='raised', bd=2)
    metadata_box.grid(row=0, column=0, padx=10, pady=5, sticky='nsew')
    
    metadata_percent = stats['metadata_completeness']
    metadata_color = '#2ecc71' if metadata_percent > 80 else '#f39c12' if metadata_percent > 50 else '#e74c3c'
    
    tk.Label(metadata_box, text=f"{metadata_percent:.1f}%", 
            font=('Arial', 24, 'bold'), fg=metadata_color).pack(pady=10)
    tk.Label(metadata_box, text="Vollständigkeit").pack()
    
    # Video-QualitÃ¤t
    if stats['video_quality_stats']:
        video_box = tk.LabelFrame(metrics_frame, text="Video-QualitÃ¤t", relief='raised', bd=2)
        video_box.grid(row=0, column=1, padx=10, pady=5, sticky='nsew')
        
        # ZÃ¤hle HD+ Dateien
        hd_count = sum(row[2] for row in stats['video_quality_stats'] 
                      if row[1] and 'x' in str(row[1]) and int(str(row[1]).split('x')[1]) >= 720)
        total_video = sum(row[2] for row in stats['video_quality_stats'])
        hd_percent = (hd_count / total_video * 100) if total_video > 0 else 0
        
        tk.Label(video_box, text=f"{hd_percent:.1f}%", 
                font=('Arial', 24, 'bold'), fg='#3498db').pack(pady=10)
        tk.Label(video_box, text="HD+ Content").pack()
    
    # Audio-QualitÃ¤t
    if stats['audio_quality_stats']:
        audio_box = tk.LabelFrame(metrics_frame, text="Audio-QualitÃ¤t", relief='raised', bd=2)
        audio_box.grid(row=0, column=2, padx=10, pady=5, sticky='nsew')
        
        # ZÃ¤hle High-Quality Audio (>= 256kbps)
        hq_count = sum(row[2] for row in stats['audio_quality_stats'] 
                      if row[3] and row[3] >= 256000)
        total_audio = sum(row[2] for row in stats['audio_quality_stats'])
        hq_percent = (hq_count / total_audio * 100) if total_audio > 0 else 0
        
        tk.Label(audio_box, text=f"{hq_percent:.1f}%", 
                font=('Arial', 24, 'bold'), fg='#9b59b6').pack(pady=10)
        tk.Label(audio_box, text="HQ Audio (256kbps+)").pack()
    
    # Duplikate
    dupes_box = tk.LabelFrame(metrics_frame, text="Duplikate", relief='raised', bd=2)
    dupes_box.grid(row=0, column=3, padx=10, pady=5, sticky='nsew')
    
    potential_dupes = len(stats['potential_duplicates'])
    dupe_color = '#e74c3c' if potential_dupes > 10 else '#f39c12' if potential_dupes > 0 else '#2ecc71'
    
    tk.Label(dupes_box, text=str(potential_dupes), 
            font=('Arial', 24, 'bold'), fg=dupe_color).pack(pady=10)
    tk.Label(dupes_box, text="Potenzielle").pack()
    
    for i in range(4):
        metrics_frame.grid_columnconfigure(i, weight=1)
    
    # === DETAILS-TABS ===
    details_notebook = ttk.Notebook(quality_container)
    details_notebook.pack(fill='both', expand=True, pady=(10, 0))
    
    # Tab 1: Format-Verteilung
    formats_frame = ttk.Frame(details_notebook)
    details_notebook.add(formats_frame, text="Formate")
    
    formats_text = tk.Text(formats_frame, height=10, font=('Arial', 9))
    formats_scroll = tk.Scrollbar(formats_frame, orient=tk.VERTICAL, command=formats_text.yview)
    formats_text.configure(yscrollcommand=formats_scroll.set)
    
    formats_text.pack(side='left', fill='both', expand=True, padx=5, pady=5)
    formats_scroll.pack(side='right', fill='y', pady=5)
    
    # Video-Formate
    if stats['video_quality_stats']:
        formats_text.insert(tk.END, "VIDEO-FORMATE:\n" + "="*60 + "\n")
        formats_text.insert(tk.END, f"{'Codec':<15} {'Auflösung':<15} {'Anzahl':<10} {'Ã˜ Bitrate'}\n")
        formats_text.insert(tk.END, "-"*60 + "\n")
        
        for codec, resolution, count, avg_bitrate in stats['video_quality_stats']:
            bitrate_mbps = (avg_bitrate / 1000000) if avg_bitrate else 0
            formats_text.insert(tk.END, 
                f"{codec or 'N/A':<15} {resolution or 'N/A':<15} {count:<10} {bitrate_mbps:.1f} Mbps\n")
    
    # Audio-Formate
    if stats['audio_quality_stats']:
        formats_text.insert(tk.END, "\n\nAUDIO-FORMATE:\n" + "="*60 + "\n")
        formats_text.insert(tk.END, f"{'Codec':<15} {'Sample Rate':<15} {'Anzahl':<10} {'Ã˜ Bitrate'}\n")
        formats_text.insert(tk.END, "-"*60 + "\n")
        
        for codec, sample_rate, count, avg_bitrate in stats['audio_quality_stats']:
            bitrate_kbps = (avg_bitrate / 1000) if avg_bitrate else 0
            sr_khz = (sample_rate / 1000) if sample_rate else 0
            formats_text.insert(tk.END, 
                f"{codec or 'N/A':<15} {sr_khz:.1f} kHz      {count:<10} {bitrate_kbps:.0f} kbps\n")
    
    formats_text.config(state=tk.DISABLED)
    
    # Tab 2: Duplikate
    dupes_frame = ttk.Frame(details_notebook)
    details_notebook.add(dupes_frame, text="Duplikate")
    
    dupes_text = tk.Text(dupes_frame, height=10, font=('Arial', 9))
    dupes_scroll = tk.Scrollbar(dupes_frame, orient=tk.VERTICAL, command=dupes_text.yview)
    dupes_text.configure(yscrollcommand=dupes_scroll.set)
    
    dupes_text.pack(side='left', fill='both', expand=True, padx=5, pady=5)
    dupes_scroll.pack(side='right', fill='y', pady=5)
    
    if stats['potential_duplicates']:
        dupes_text.insert(tk.END, "POTENZIELLE DUPLIKATE (gleiche Dateigrösse):\n" + "="*60 + "\n\n")
        dupes_text.insert(tk.END, f"{'Dateigrössee':<20} {'Anzahl Dateien':<15} {'Gesamt'}\n")
        dupes_text.insert(tk.END, "-"*60 + "\n")
        
        for file_size, count in stats['potential_duplicates']:
            size_mb = file_size / (1024**2)
            total_size_mb = (file_size * count) / (1024**2)
            
            if size_mb >= 1024:
                size_str = f"{size_mb/1024:.2f} GB"
                total_str = f"{total_size_mb/1024:.2f} GB"
            else:
                size_str = f"{size_mb:.1f} MB"
                total_str = f"{total_size_mb:.1f} MB"
            
            dupes_text.insert(tk.END, f"{size_str:<20} {count:<15} {total_str}\n")
        
        dupes_text.insert(tk.END, "\n" + "="*60 + "\n")
        dupes_text.insert(tk.END, "HINWEIS: Diese Dateien haben die gleiche Grössee.\n")
        dupes_text.insert(tk.END, "Prüfen Sie manuell, ob es echte Duplikate sind.\n")
    else:
        dupes_text.insert(tk.END, "Keine potenziellen Duplikate gefunden.\n\nâœ" + "Ihre Sammlung sieht sauber aus!")
    
    dupes_text.config(state=tk.DISABLED)
    
    # Tab 3: Fehlende Metadaten (in create_quality_maintenance_tab)
    missing_frame = ttk.Frame(details_notebook)
    details_notebook.add(missing_frame, text="Fehlende Metadaten")

    missing_text = tk.Text(missing_frame, height=10, font=('Arial', 9))
    missing_scroll = tk.Scrollbar(missing_frame, orient=tk.VERTICAL, command=missing_text.yview)
    missing_text.configure(yscrollcommand=missing_scroll.set)

    missing_text.pack(side='left', fill='both', expand=True, padx=5, pady=5)
    missing_scroll.pack(side='right', fill='y', pady=5)

    # Berechne fehlende Metadaten pro Kategorie
    try:
        conn = sqlite3.connect('media_index.db')
        cursor = conn.cursor()
        
        header_text = "METADATEN-VOLLSTÄNDIGKEIT PRO KATEGORIE:\n" + "="*60 + "\n\n"
        insert_text_utf8(missing_text, header_text)
        
        for category in stats['category_stats'].keys():
            cursor.execute("""
                SELECT 
                    COUNT(*) as total,
                    COUNT(CASE WHEN genre = '' OR genre IS NULL THEN 1 END) as missing_genre,
                    COUNT(CASE WHEN year = '' OR year = '0' OR year IS NULL THEN 1 END) as missing_year,
                    COUNT(CASE WHEN (actors = '' OR actors IS NULL) AND (contributors = '' OR contributors IS NULL) THEN 1 END) as missing_artist
                FROM media_files
                WHERE category = ?
            """, (category,))
            
            total, missing_genre, missing_year, missing_artist = cursor.fetchone()
            
            if total > 0:
                category_info = f"{category}:\n"
                category_info += f"  Gesamt: {total} Dateien\n"
                category_info += f"  Fehlendes Genre: {missing_genre} ({missing_genre/total*100:.1f}%)\n"
                category_info += f"  Fehlendes Jahr: {missing_year} ({missing_year/total*100:.1f}%)\n"
                category_info += f"  Fehlende Künstler/Actors: {missing_artist} ({missing_artist/total*100:.1f}%)\n\n"
                
                insert_text_utf8(missing_text, category_info)
        
        conn.close()
        
        footer_text = "="*60 + "\n"
        footer_text += "EMPFEHLUNG:\n"
        footer_text += "• Dateien mit fehlenden Metadaten sollten nachbearbeitet werden\n"
        footer_text += "• Verwenden Sie Tools wie MP3Tag oder MediaInfo\n"
        
        insert_text_utf8(missing_text, footer_text)
        
    except Exception as e:
        error_text = f"Fehler beim Laden: {e}\n"
        insert_text_utf8(missing_text, error_text)

    missing_text.config(state=tk.DISABLED)
    
    # === WARTUNGS-EMPFEHLUNGEN ===
    maintenance_frame = tk.LabelFrame(paned, text="Wartungs-Empfehlungen", font=('Arial', 12, 'bold'))
    paned.add(maintenance_frame, weight=1)
    
    maintenance_container = tk.Frame(maintenance_frame)
    maintenance_container.pack(fill='both', expand=True, padx=10, pady=10)
    
    # Recommendations basierend auf Statistiken
    recommendations = []
    
    # Metadaten-Check
    if stats['metadata_completeness'] < 80:
        recommendations.append(("⚠ Metadaten-Vollständigkeit niedrig", 
                               f"Nur {stats['metadata_completeness']:.1f}% der Dateien haben vollständige Metadaten",
                               "Hohe Priorität"))
    elif stats['metadata_completeness'] < 95:
        recommendations.append(("⚠ Metadaten-Vollständigkeit verbesserbar", 
                               f"{stats['metadata_completeness']:.1f}% Vollständigkeit",
                               "Mittlere Priorität"))
    else:
        recommendations.append(("✓ Metadaten-Vollständigkeit ausgezeichnet", 
                               f"{stats['metadata_completeness']:.1f}% Vollständigkeit",
                               "Keine Aktion nötig"))
    
    # Duplikate-Check
    if len(stats['potential_duplicates']) > 10:
        total_dupe_size = sum(size * count for size, count in stats['potential_duplicates'])
        recommendations.append(("⚠ Viele potenzielle Duplikate", 
                               f"{len(stats['potential_duplicates'])} Größen-Duplikate ({total_dupe_size/(1024**3):.1f} GB potenzielle Einsparung)",
                               "Hohe Priorität"))
    elif len(stats['potential_duplicates']) > 0:
        recommendations.append(("⚠ Einige potenzielle Duplikate", 
                               f"{len(stats['potential_duplicates'])} Größen-Duplikate gefunden",
                               "Mittlere Priorität"))
    else:
        recommendations.append(("✓ Keine Duplikate", 
                               "Keine potenziellen Duplikate gefunden",
                               "Keine Aktion nötig"))
    
    # Qualitäts-Check (Video)
    if stats['video_quality_stats']:
        hd_count = sum(row[2] for row in stats['video_quality_stats'] 
                      if row[1] and 'x' in str(row[1]) and int(str(row[1]).split('x')[1]) >= 720)
        total_video = sum(row[2] for row in stats['video_quality_stats'])
        hd_percent = (hd_count / total_video * 100) if total_video > 0 else 0
        
        if hd_percent < 50:
            recommendations.append(("⚠ Video-Qualität niedrig", 
                                   f"Nur {hd_percent:.1f}% HD+ Content",
                                   "Niedrige Priorität"))
        else:
            recommendations.append(("✓ Video-Qualität gut", 
                                   f"{hd_percent:.1f}% HD+ Content",
                                   "Keine Aktion nötig"))
    
    # Backup-Empfehlung
    collection_gb = stats['total_size'] / (1024**3)
    recommendations.append(("💾 Backup-Empfehlung", 
                           f"Sichern Sie {collection_gb:,.1f} GB (empfohlen: {collection_gb*1.2:,.1f} GB mit Puffer)",
                           "Hohe Priorität"))
    
    # Darstellung mit UTF-8 Fix
    for i, (title, description, priority) in enumerate(recommendations):
        rec_frame = tk.Frame(maintenance_container, relief='raised', bd=2)
        rec_frame.pack(fill='x', pady=5)
        
        # Prioritäts-Farbe
        if "Hohe" in priority:
            color = '#e74c3c'
        elif "Mittlere" in priority:
            color = '#f39c12'
        else:
            color = '#2ecc71'
        
        # Header
        header_frame = tk.Frame(rec_frame, bg=color)
        header_frame.pack(fill='x')
        
        tk.Label(header_frame, text=title, font=('Arial', 11, 'bold'), 
                bg=color, fg='white').pack(side='left', padx=10, pady=5)
        tk.Label(header_frame, text=priority, font=('Arial', 9), 
                bg=color, fg='white').pack(side='right', padx=10, pady=5)
        
        # Beschreibung
        tk.Label(rec_frame, text=description, font=('Arial', 9), 
                anchor='w').pack(fill='x', padx=10, pady=5)


# === ENCODING FIX FÜR TKINTER TEXT-WIDGETS ===
def normalize_text_for_tkinter(text):
    """
    Korrigiert kaputte UTF-8 Kodierung in Strings
    """
    # Häufige Fehlkodierungen reparieren
    replacements = {
        'â€¢': '•',      # Bullet point
        'Ã¤': 'ä', 'Ã¶': 'ö', 'Ã¼': 'ü',
        'Ã„': 'Ä', 'Ã–': 'Ö', 'Ãœ': 'Ü',
        'ÃŸ': 'ß',
        'Ã©': 'é', 'Ã¨': 'è', 'Ã ': 'à',
        'GrÃ¶ÃŸe': 'Größe',
        'MÃ¶gliche': 'Mögliche',
        'benÃ¶tigt': 'benötigt',
        'VollstÃ¤ndiges': 'Vollständiges',
        'KÃ¼nstler': 'Künstler',
        'â‚¬': '€',
        'âœ"': '✓',
        'â ': '⚠',
        'â€"': '–',
        'â€"': '—',
        'â€˜': ''',
        'â€™': ''',
        'â€œ': '"',
        'â€': '"',
    }
    
    for old, new in replacements.items():
        text = text.replace(old, new)
    
    return text

def insert_text_utf8(text_widget, text, index='end'):
    """
    Fügt Text mit korrekter UTF-8 Kodierung in Tkinter Text-Widget ein
    """
    try:
        # Normalisiere Text
        text = normalize_text_for_tkinter(text)
        
        # Stelle sicher, dass es ein String ist
        if isinstance(text, bytes):
            text = text.decode('utf-8', errors='replace')
        
        text_widget.insert(index, text)
    except Exception as e:
        print(f"Text-Encoding Fehler: {e}")
        # Fallback: ASCII-only
        try:
            clean_text = text.encode('ascii', errors='replace').decode('ascii')
            text_widget.insert(index, clean_text)
        except:
            text_widget.insert(index, "[Encoding Error]")

def create_dashboard_tab(parent, stats):
    """Dashboard mit Kategorie-Kacheln und Gesamt-Übersicht"""
    
    # Scrollbarer Container
    canvas = tk.Canvas(parent)
    scrollbar = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
    scrollable_frame = ttk.Frame(canvas)
    
    scrollable_frame.bind(
        "<Configure>",
        lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
    )
    
    canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
    canvas.configure(yscrollcommand=scrollbar.set)
    
    canvas.pack(side="left", fill="both", expand=True)
    scrollbar.pack(side="right", fill="y")
    
    # Header
    header = tk.Frame(scrollable_frame, bg='#2c3e50', height=80)
    header.pack(fill='x', padx=10, pady=(10, 20))
    
    tk.Label(header, text="📊 ARCHIV DASHBOARD", font=('Arial', 20, 'bold'), 
             bg='#2c3e50', fg='white').pack(pady=20)
    
    # Gesamt-Statistiken
    total_frame = tk.LabelFrame(scrollable_frame, text="Gesamt-Übersicht", 
                                font=('Arial', 14, 'bold'), padx=20, pady=15)
    total_frame.pack(fill='x', padx=20, pady=10)
    
    total_stats_frame = tk.Frame(total_frame)
    total_stats_frame.pack(fill='x')
    
    total_hours = int(stats['total_duration'] / 60)
    total_minutes = int(stats['total_duration'] % 60)
    total_gb = stats['total_size'] / (1024**3)
    
    total_stats = [
        ("📚 Dateien", f"{stats['total_files']:,}", "Gesamt"),
        ("⏱️ Laufzeit", f"{total_hours:,}h {total_minutes}m", "Gesamt"),
        ("💾 Speicher", f"{total_gb:,.1f} GB", "Gesamt"),
        ("✅ Metadaten", f"{stats['metadata_completeness']:.1f}%", "Vollständig")
    ]
    
    for i, (icon_title, value, subtitle) in enumerate(total_stats):
        box = tk.Frame(total_stats_frame, relief='raised', bd=2, bg='#ecf0f1')
        box.grid(row=0, column=i, padx=10, pady=5, sticky='nsew')
        
        tk.Label(box, text=icon_title, font=('Arial', 11, 'bold'), 
                bg='#ecf0f1', fg='#2c3e50').pack(pady=(10, 5))
        tk.Label(box, text=value, font=('Arial', 18, 'bold'), 
                bg='#ecf0f1', fg='#3498db').pack(pady=5)
        tk.Label(box, text=subtitle, font=('Arial', 9), 
                bg='#ecf0f1', fg='#7f8c8d').pack(pady=(5, 10))
        
        total_stats_frame.grid_columnconfigure(i, weight=1)
    
    # Kategorie-Kacheln
    categories_label = tk.Label(scrollable_frame, text="Kategorien", 
                                font=('Arial', 16, 'bold'))
    categories_label.pack(anchor='w', padx=20, pady=(20, 10))
    
    categories_container = tk.Frame(scrollable_frame)
    categories_container.pack(fill='both', expand=True, padx=20, pady=10)
    
    # Farben für Kategorien
    category_colors = {
        'Filme': ('#e74c3c', '#c0392b'),
        'Serien': ('#3498db', '#2980b9'),
        'Musik': ('#2ecc71', '#27ae60'),
        'Video': ('#9b59b6', '#8e44ad'),
        'Audio': ('#f39c12', '#e67e22')
    }
    
    # Sortiere Kategorien nach Dateizahl
    sorted_categories = sorted(stats['category_stats'].items(), 
                              key=lambda x: x[1]['count'], reverse=True)
    
    row = 0
    col = 0
    max_cols = 3
    
    for category, cat_stats in sorted_categories:
        # Farben
        bg_color, hover_color = category_colors.get(category, ('#95a5a6', '#7f8c8d'))
        
        # Kachel
        tile = tk.Frame(categories_container, relief='raised', bd=3, bg=bg_color, cursor='hand2')
        tile.grid(row=row, column=col, padx=15, pady=15, sticky='nsew')
        
        # Header mit Icon
        header_frame = tk.Frame(tile, bg=bg_color)
        header_frame.pack(fill='x', pady=(15, 10))
        
        category_icons = {
            'Filme': '🎬',
            'Serien': '📺',
            'Musik': '🎵',
            'Video': '🎥',
            'Audio': '🎧'
        }
        
        icon = category_icons.get(category, '📁')
        tk.Label(header_frame, text=f"{icon} {category}", 
                font=('Arial', 16, 'bold'), bg=bg_color, fg='white').pack()
        
        # Statistiken
        stats_frame = tk.Frame(tile, bg=bg_color)
        stats_frame.pack(fill='both', expand=True, padx=20, pady=10)
        
        # Dateien
        tk.Label(stats_frame, text="Dateien:", font=('Arial', 10, 'bold'), 
                bg=bg_color, fg='white', anchor='w').grid(row=0, column=0, sticky='w', pady=2)
        tk.Label(stats_frame, text=f"{cat_stats['count']:,}", font=('Arial', 10), 
                bg=bg_color, fg='white', anchor='e').grid(row=0, column=1, sticky='e', pady=2)
        
        # Laufzeit
        hours = int(cat_stats['duration'] / 60)
        minutes = int(cat_stats['duration'] % 60)
        tk.Label(stats_frame, text="Laufzeit:", font=('Arial', 10, 'bold'), 
                bg=bg_color, fg='white', anchor='w').grid(row=1, column=0, sticky='w', pady=2)
        tk.Label(stats_frame, text=f"{hours:,}h {minutes}m", font=('Arial', 10), 
                bg=bg_color, fg='white', anchor='e').grid(row=1, column=1, sticky='e', pady=2)
        
        # Speicher
        gb = cat_stats['size'] / (1024**3)
        tk.Label(stats_frame, text="Speicher:", font=('Arial', 10, 'bold'), 
                bg=bg_color, fg='white', anchor='w').grid(row=2, column=0, sticky='w', pady=2)
        tk.Label(stats_frame, text=f"{gb:,.1f} GB", font=('Arial', 10), 
                bg=bg_color, fg='white', anchor='e').grid(row=2, column=1, sticky='e', pady=2)
        
        # Durchschnitt
        avg_size_mb = (cat_stats['size'] / cat_stats['count']) / (1024**2) if cat_stats['count'] > 0 else 0
        tk.Label(stats_frame, text="Ø Größe:", font=('Arial', 10, 'bold'), 
                bg=bg_color, fg='white', anchor='w').grid(row=3, column=0, sticky='w', pady=2)
        tk.Label(stats_frame, text=f"{avg_size_mb:,.0f} MB", font=('Arial', 10), 
                bg=bg_color, fg='white', anchor='e').grid(row=3, column=1, sticky='e', pady=2)
        
        # Qualität
        if cat_stats['avg_bitrate'] > 0:
            bitrate_display = f"{int(cat_stats['avg_bitrate'] / 1000)} kbps"
        else:
            bitrate_display = "N/A"
        tk.Label(stats_frame, text="Ø Bitrate:", font=('Arial', 10, 'bold'), 
                bg=bg_color, fg='white', anchor='w').grid(row=4, column=0, sticky='w', pady=2)
        tk.Label(stats_frame, text=bitrate_display, font=('Arial', 10), 
                bg=bg_color, fg='white', anchor='e').grid(row=4, column=1, sticky='e', pady=2)
        
        # Metadaten-Vollständigkeit
        tk.Label(stats_frame, text="Metadaten:", font=('Arial', 10, 'bold'), 
                bg=bg_color, fg='white', anchor='w').grid(row=5, column=0, sticky='w', pady=2)
        meta_color = '#2ecc71' if cat_stats['metadata_completeness'] > 80 else '#f39c12' if cat_stats['metadata_completeness'] > 50 else '#e74c3c'
        tk.Label(stats_frame, text=f"{cat_stats['metadata_completeness']:.0f}%", 
                font=('Arial', 10, 'bold'), bg=bg_color, fg=meta_color, anchor='e').grid(row=5, column=1, sticky='e', pady=2)
        
        stats_frame.grid_columnconfigure(1, weight=1)
        
        # Prozent-Anteil am Gesamtbestand
        percent = (cat_stats['count'] / stats['total_files'] * 100) if stats['total_files'] > 0 else 0
        footer = tk.Frame(tile, bg=hover_color, height=30)
        footer.pack(fill='x', side='bottom')
        tk.Label(footer, text=f"{percent:.1f}% des Gesamtbestands", 
                font=('Arial', 9, 'bold'), bg=hover_color, fg='white').pack(pady=5)
        
        # Grid-Position aktualisieren
        col += 1
        if col >= max_cols:
            col = 0
            row += 1
    
    # Grid-Konfiguration
    for i in range(max_cols):
        categories_container.grid_columnconfigure(i, weight=1, minsize=300)

def create_categories_genres_tab(parent, stats):
    """Hierarchische Darstellung: Kategorie → Genres mit Export"""
    
    paned = ttk.PanedWindow(parent, orient=tk.HORIZONTAL)
    paned.pack(fill='both', expand=True, padx=5, pady=5)
    
    left_frame = tk.Frame(paned)
    paned.add(left_frame, weight=1)
    
    tk.Label(left_frame, text="Kategorie wählen:", font=('Arial', 14, 'bold')).pack(pady=10)
    
    selected_category = tk.StringVar()
    
    button_frame = tk.Frame(left_frame)
    button_frame.pack(fill='both', expand=True, padx=10, pady=10)
    
    sorted_categories = sorted(stats['category_stats'].items(), 
                              key=lambda x: x[1]['count'], reverse=True)
    
    for i, (category, cat_stats) in enumerate(sorted_categories):
        btn_text = f"{category}\n{cat_stats['count']:,} Dateien\n{cat_stats['size']/(1024**3):.1f} GB"
        
        btn = tk.Radiobutton(
            button_frame, 
            text=btn_text,
            variable=selected_category,
            value=category,
            indicatoron=False,
            width=20,
            height=5,
            font=('Arial', 10, 'bold'),
            bg='#3498db',
            fg='white',
            selectcolor='#2ecc71',
            relief='raised',
            bd=3,
            command=lambda: update_genre_display()
        )
        btn.pack(pady=5, padx=10, fill='x')
    
    right_frame = tk.Frame(paned)
    paned.add(right_frame, weight=3)
    
    genre_header_frame = tk.Frame(right_frame)
    genre_header_frame.pack(fill='x', pady=10)
    
    genre_header = tk.Label(genre_header_frame, text="Bitte Kategorie wählen", 
                           font=('Arial', 16, 'bold'))
    genre_header.pack(side='left', padx=10)
    
    export_button = tk.Button(genre_header_frame, text="📊 Genre-Liste Exportieren",
                             command=lambda: export_current_genre_list(),
                             state=tk.DISABLED, bg='#3498db', fg='white')
    export_button.pack(side='right', padx=10)
    
    genre_content_frame = tk.Frame(right_frame)
    genre_content_frame.pack(fill='both', expand=True, padx=10, pady=10)
    
    def update_genre_display():
        for widget in genre_content_frame.winfo_children():
            widget.destroy()
        
        category = selected_category.get()
        if not category:
            export_button.config(state=tk.DISABLED)
            return
        
        export_button.config(state=tk.NORMAL)
        genre_header.config(text=f"Genres in: {category}")
        
        genres = stats['genre_by_category'].get(category, [])
        
        if not genres:
            tk.Label(genre_content_frame, text="Keine Genre-Daten verfügbar", 
                    font=('Arial', 12)).pack(pady=50)
            return
        
        cat_stats = stats['category_stats'][category]
        info_frame = tk.LabelFrame(genre_content_frame, text="Kategorie-Übersicht", 
                                   font=('Arial', 12, 'bold'))
        info_frame.pack(fill='x', pady=(0, 10))
        
        info_text = tk.Text(info_frame, height=4, font=('Arial', 10), wrap=tk.WORD)
        info_text.pack(padx=10, pady=10, fill='x')
        
        hours = int(cat_stats['duration'] / 60)
        minutes = int(cat_stats['duration'] % 60)
        gb = cat_stats['size'] / (1024**3)
        
        info_content = (
            f"Dateien: {cat_stats['count']:,}  |  "
            f"Laufzeit: {hours:,}h {minutes}m  |  "
            f"Speicher: {gb:,.1f} GB  |  "
            f"Metadaten: {cat_stats['metadata_completeness']:.0f}%  |  "
            f"Ø Bitrate: {int(cat_stats['avg_bitrate']/1000)} kbps"
        )
        info_text.insert('1.0', info_content)
        info_text.config(state=tk.DISABLED)
        
        table_frame = tk.Frame(genre_content_frame)
        table_frame.pack(fill='both', expand=True)
        
        columns = ('Genre', 'Dateien', 'Laufzeit', 'Speicher', 'Ø Bitrate', 'Anteil')
        tree = ttk.Treeview(table_frame, columns=columns, show='headings', height=20)
        
        for col in columns:
            tree.heading(col, text=col)
        
        tree.column('Genre', width=200, anchor='w')
        tree.column('Dateien', width=100, anchor='e')
        tree.column('Laufzeit', width=120, anchor='e')
        tree.column('Speicher', width=120, anchor='e')
        tree.column('Ø Bitrate', width=120, anchor='e')
        tree.column('Anteil', width=100, anchor='e')
        
        tree_scroll_y = ttk.Scrollbar(table_frame, orient='vertical', command=tree.yview)
        tree_scroll_x = ttk.Scrollbar(table_frame, orient='horizontal', command=tree.xview)
        tree.configure(yscrollcommand=tree_scroll_y.set, xscrollcommand=tree_scroll_x.set)
        
        tree.grid(row=0, column=0, sticky='nsew')
        tree_scroll_y.grid(row=0, column=1, sticky='ns')
        tree_scroll_x.grid(row=1, column=0, sticky='ew')
        
        table_frame.grid_rowconfigure(0, weight=1)
        table_frame.grid_columnconfigure(0, weight=1)
        
        for genre_data in genres:
            hours = int(genre_data['duration'] / 60)
            minutes = int(genre_data['duration'] % 60)
            gb = genre_data['size'] / (1024**3)
            bitrate_kbps = int(genre_data['avg_bitrate'] / 1000) if genre_data['avg_bitrate'] > 0 else 0
            percent = (genre_data['count'] / cat_stats['count'] * 100) if cat_stats['count'] > 0 else 0
            
            tree.insert('', 'end', values=(
                genre_data['genre'],
                f"{genre_data['count']:,}",
                f"{hours}h {minutes}m",
                f"{gb:.1f} GB",
                f"{bitrate_kbps} kbps" if bitrate_kbps > 0 else "N/A",
                f"{percent:.1f}%"
            ))
        
        summary_frame = tk.LabelFrame(genre_content_frame, text="Zusammenfassung", 
                                     font=('Arial', 11, 'bold'))
        summary_frame.pack(fill='x', pady=(10, 0))
        
        summary_text = tk.Text(summary_frame, height=3, font=('Arial', 9))
        summary_text.pack(padx=10, pady=10, fill='x')
        
        summary_content = (
            f"Verschiedene Genres: {len(genres)}\n"
            f"Durchschnitt Dateien/Genre: {cat_stats['count'] / len(genres):.0f}\n"
            f"Beliebtestes Genre: {genres[0]['genre']} ({genres[0]['count']} Dateien)"
        )
        summary_text.insert('1.0', summary_content)
        summary_text.config(state=tk.DISABLED)
    
    def export_current_genre_list():
        category = selected_category.get()
        if not category:
            return
        
        genres = stats['genre_by_category'].get(category, [])
        if not genres:
            return
        
        export_text = f"GENRE-STATISTIK: {category}\n{'='*100}\n\n"
        export_text += f"{'Genre':<30} {'Dateien':<12} {'Laufzeit':<15} {'Speicher':<15} {'Bitrate':<15} {'Anteil'}\n"
        export_text += f"{'-'*100}\n"
        
        cat_stats = stats['category_stats'][category]
        for genre_data in genres:
            hours = int(genre_data['duration'] / 60)
            minutes = int(genre_data['duration'] % 60)
            gb = genre_data['size'] / (1024**3)
            bitrate_kbps = int(genre_data['avg_bitrate'] / 1000) if genre_data['avg_bitrate'] > 0 else 0
            percent = (genre_data['count'] / cat_stats['count'] * 100) if cat_stats['count'] > 0 else 0
            
            export_text += (f"{genre_data['genre']:<30} "
                          f"{genre_data['count']:<12,} "
                          f"{hours:>4}h {minutes:>2}m      "
                          f"{gb:>8.1f} GB    "
                          f"{bitrate_kbps:>8} kbps   "
                          f"{percent:>6.1f}%\n")
        
        export_text += f"\n{'='*100}\n"
        export_text += f"Gesamt: {len(genres)} Genres, {cat_stats['count']:,} Dateien\n"
        
        copy_to_clipboard(export_text)
        messagebox.showinfo("Export", "Genre-Statistik in Zwischenablage kopiert!")
    
    if sorted_categories:
        selected_category.set(sorted_categories[0][0])
        update_genre_display()
    
def create_hardware_tab(parent, stats):
    """Hardware-Auslastung und Speicher-Prognosen - VOLLSTÃNDIG"""
    
    paned = ttk.PanedWindow(parent, orient=tk.VERTICAL)
    paned.pack(fill='both', expand=True)
    
    # Oberer Bereich: Charts
    charts_frame = ttk.Frame(paned)
    paned.add(charts_frame, weight=2)
    
    if matplotlib_available:
        try:
            if folder_path:
                drive = os.path.splitdrive(folder_path)[0] or folder_path.split(os.sep)[0]
                if not drive.endswith(os.sep):
                    drive += os.sep
                
                # Laufwerks-Info
                disk_usage = shutil.disk_usage(drive)
                total_gb = disk_usage.total / (1024**3)
                used_gb = disk_usage.used / (1024**3)
                free_gb = disk_usage.free / (1024**3)
                
                # Sammlung-GrÃ¶ÃŸe
                collection_gb = stats['total_size'] / (1024**3)
                other_used_gb = used_gb - collection_gb
                
                # Charts erstellen
                fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(12, 8))
                
                # 1. Laufwerk Gesamt-Übersicht
                disk_labels = ['Sammlung', 'Andere Daten', 'Frei']
                disk_sizes = [collection_gb, max(0, other_used_gb), free_gb]
                colors1 = ['#3498db', '#95a5a6', '#2ecc71']
                
                wedges1, texts1, autotexts1 = ax1.pie(disk_sizes, labels=disk_labels, 
                                                      autopct='%1.1f%%', colors=colors1, startangle=90)
                ax1.set_title(f'Laufwerk {drive} - Übersicht', fontsize=12, fontweight='bold')
                
                # 2. Kategorie-Speicher
                if stats['category_stats']:
                    cat_names = []
                    cat_sizes_gb = []
                    for cat, cat_stats in sorted(stats['category_stats'].items(), 
                                                 key=lambda x: x[1]['size'], reverse=True):
                        cat_names.append(cat)
                        cat_sizes_gb.append(cat_stats['size'] / (1024**3))
                    
                    colors2 = plt.cm.Set3(range(len(cat_names)))
                    bars = ax2.bar(cat_names, cat_sizes_gb, color=colors2)
                    ax2.set_title('Speicher nach Kategorien', fontsize=12, fontweight='bold')
                    ax2.set_ylabel('GrÃ¶ÃŸe (GB)')
                    ax2.tick_params(axis='x', rotation=45)
                    
                    for bar, value in zip(bars, cat_sizes_gb):
                        height = bar.get_height()
                        ax2.text(bar.get_x() + bar.get_width()/2., height,
                                f'{value:.1f} GB', ha='center', va='bottom', fontsize=9)
                
                # 3. Wachstums-Prognose
                avg_file_size_gb = collection_gb / stats['total_files'] if stats['total_files'] > 0 else 0
                if avg_file_size_gb > 0 and free_gb > 0:
                    potential_files = int(free_gb / avg_file_size_gb)
                    growth_scenarios = ['Aktuell', '+25%', '+50%', '+100%', 'Voll']
                    growth_values = [
                        collection_gb,
                        collection_gb * 1.25,
                        collection_gb * 1.50,
                        collection_gb * 2.00,
                        total_gb
                    ]
                    
                    colors3 = ['#3498db', '#f39c12', '#e67e22', '#e74c3c', '#c0392b']
                    bars3 = ax3.bar(growth_scenarios, growth_values, color=colors3)
                    ax3.set_title('Wachstums-Szenarien', fontsize=12, fontweight='bold')
                    ax3.set_ylabel('Speicherbedarf (GB)')
                    ax3.axhline(y=total_gb, color='r', linestyle='--', label='KapazitÃ¤tsgrenze')
                    ax3.legend()
                    
                    for bar, value in zip(bars3, growth_values):
                        height = bar.get_height()
                        ax3.text(bar.get_x() + bar.get_width()/2., height,
                                f'{value:.0f} GB', ha='center', va='bottom', fontsize=8)
                
                # 4. Effizienz: GB pro Stunde (KORRIGIERT - VOLLSTÃNDIG)
                if stats['total_duration'] > 0:
                    total_hours = stats['total_duration'] / 60
                    efficiency = collection_gb / total_hours
                    
                    # Pro Kategorie
                    cat_efficiency = []
                    cat_labels = []
                    for cat, cat_stats in sorted(stats['category_stats'].items(), 
                                                 key=lambda x: x[1]['count'], reverse=True):
                        if cat_stats['duration'] > 0:
                            cat_hours = cat_stats['duration'] / 60
                            cat_gb = cat_stats['size'] / (1024**3)
                            cat_eff = cat_gb / cat_hours
                            cat_efficiency.append(cat_eff)
                            cat_labels.append(cat)
                    
                    if cat_efficiency:
                        colors4 = plt.cm.Pastel1(range(len(cat_labels)))
                        bars4 = ax4.bar(cat_labels, cat_efficiency, color=colors4)  # ← KORRIGIERT
                        ax4.set_title('Speicher-Effizienz (GB/Stunde)', fontsize=12, fontweight='bold')
                        ax4.set_ylabel('GB pro Stunde Content')
                        ax4.tick_params(axis='x', rotation=45)
                        
                        for bar, value in zip(bars4, cat_efficiency):
                            height = bar.get_height()
                            ax4.text(bar.get_x() + bar.get_width()/2., height,
                                    f'{value:.2f}', ha='center', va='bottom', fontsize=8)
                    else:
                        ax4.text(0.5, 0.5, 'Keine Laufzeit-\nDaten verfÃ¼gbar', 
                                ha='center', va='center', transform=ax4.transAxes)
                else:
                    ax4.text(0.5, 0.5, 'Keine Laufzeit-\nDaten verfÃ¼gbar', 
                            ha='center', va='center', transform=ax4.transAxes)
                
                plt.tight_layout()
                
                canvas = FigureCanvasTkAgg(fig, charts_frame)
                canvas.draw()
                canvas.get_tk_widget().pack(fill='both', expand=True, padx=5, pady=5)
                
        except Exception as e:
            print(f"Fehler bei Hardware-Charts: {e}")
            import traceback
            traceback.print_exc()
    
    # Unterer Bereich: Hardware-Details
    details_frame = tk.LabelFrame(paned, text="Hardware & Prognosen", font=('Arial', 12, 'bold'))
    paned.add(details_frame, weight=1)
    
    details_container = tk.Frame(details_frame)
    details_container.pack(fill='both', expand=True, padx=5, pady=5)
    
    details_text = tk.Text(details_container, height=8, font=('Arial', 10), wrap=tk.WORD)
    details_scrollbar = tk.Scrollbar(details_container, orient=tk.VERTICAL, command=details_text.yview)
    details_text.configure(yscrollcommand=details_scrollbar.set)
    
    details_text.pack(side='left', fill='both', expand=True)
    details_scrollbar.pack(side='right', fill='y')
    
    # Details erstellen mit UTF-8 Fix
    try:
        if folder_path:
            drive = os.path.splitdrive(folder_path)[0] or folder_path.split(os.sep)[0]
            if not drive.endswith(os.sep):
                drive += os.sep
            
            disk_usage = shutil.disk_usage(drive)
            total_gb = disk_usage.total / (1024**3)
            used_gb = disk_usage.used / (1024**3)
            free_gb = disk_usage.free / (1024**3)
            collection_gb = stats['total_size'] / (1024**3)
            
            # KORRIGIERT: F-String korrigiert + UTF-8 sichere Zeichen
            details_info = f"""HARDWARE AUSLASTUNG & PROGNOSEN

LAUFWERK: {drive}
{'='*60}

Gesamtkapazität: {total_gb:,.1f} GB
Belegt: {used_gb:,.1f} GB ({(used_gb/total_gb)*100:.1f}%)
Frei: {free_gb:,.1f} GB ({(free_gb/total_gb)*100:.1f}%)

MEDIEN-SAMMLUNG:
{'='*60}
Größe: {collection_gb:,.1f} GB
Anteil am Laufwerk: {(collection_gb/total_gb)*100:.2f}%
Durchschnitt pro Datei: {(collection_gb/stats['total_files'])*1024:.1f} MB

WACHSTUMSPROGNOSE:
{'='*60}
"""
            
            avg_file_size_gb = collection_gb / stats['total_files'] if stats['total_files'] > 0 else 0
            if avg_file_size_gb > 0 and free_gb > 0:
                potential_files = int(free_gb / avg_file_size_gb)
                details_info += f"Mögliche zusätzliche Dateien: ~{potential_files:,}\n"
                details_info += f"Bei +50% Wachstum: {collection_gb*1.5:.1f} GB benötigt\n"
                details_info += f"Bei +100% Wachstum: {collection_gb*2:.1f} GB benötigt\n"
                
                if collection_gb * 2 > total_gb:
                    details_info += f"\n⚠ WARNUNG: Verdopplung übersteigt Kapazität!\n"
                else:
                    # KORRIGIERT: F-String repariert
                    reserve_gb = total_gb - collection_gb * 2
                    details_info += f"\n✓ OK: Verdopplung möglich ({reserve_gb:.1f} GB Reserve)\n"
            
            # Backup-Bedarf
            details_info += f"\nBACKUP-BEDARF:\n"
            details_info += f"{'='*60}\n"
            details_info += f"Vollständiges Backup: {collection_gb:,.1f} GB\n"
            details_info += f"Empfohlene Backup-Größe: {collection_gb*1.2:.1f} GB (mit 20% Puffer)\n"
            
            # Effizienz
            if stats['total_duration'] > 0:
                total_hours = stats['total_duration'] / 60
                efficiency = collection_gb / total_hours
                details_info += f"\nSPEICHER-EFFIZIENZ:\n"
                details_info += f"{'='*60}\n"
                details_info += f"Durchschnitt: {efficiency:.2f} GB pro Stunde Content\n"
                details_info += f"1 TB speichert ca. {1024/efficiency:.0f} Stunden Content\n"
            
            # UTF-8 sicher einfügen
            insert_text_utf8(details_text, details_info)
        else:
            insert_text_utf8(details_text, "Kein Ordner ausgewählt.")
            
    except Exception as e:
        error_text = f"Fehler beim Laden der Details:\n{str(e)}"
        insert_text_utf8(details_text, error_text)
    
    details_text.config(state=tk.DISABLED)

def create_filetypes_tab(parent, stats):
    """Erweiterte Dateitypen-Tab mit Genres, Kategorien, Zeit und Speicherauslastung"""
    
    # Hauptcontainer mit Notebook für verschiedene Ansichten
    main_frame = ttk.Frame(parent)
    main_frame.pack(fill='both', expand=True, padx=5, pady=5)
    
    # Ansicht-Auswahl Buttons
    button_frame = tk.Frame(main_frame)
    button_frame.pack(fill='x', pady=(0, 10))
    
    tk.Label(button_frame, text="Ansicht:", font=('Arial', 12, 'bold')).pack(side='left', padx=(10, 5))
    
    # Variable für aktuelle Ansicht
    current_view = tk.StringVar(value="overview")
    
    view_buttons = [
        ("Übersicht & Zeit", "overview", "lightblue"),
        ("Genres & Kategorien", "genres", "lightgreen"), 
        ("Dateiformate", "formats", "lightyellow"),
        ("Speicherauslastung", "storage", "yellow")  # NEU
    ]
    
    for text, value, color in view_buttons:
        btn = tk.Radiobutton(
            button_frame, text=text, variable=current_view, value=value,
            bg=color, indicatoron=False, width=15, relief='raised',
            command=lambda: update_view()
        )
        btn.pack(side='left', padx=2)
    
    # Content Frame für wechselnde Inhalte
    content_frame = ttk.Frame(main_frame)
    content_frame.pack(fill='both', expand=True)
    
    def clear_content():
        """Leert den Content-Bereich"""
        for widget in content_frame.winfo_children():
            widget.destroy()
    
    def create_overview_view():
        """Standard-Ansicht: Medientypen mit Zeit und Gesamtübersicht"""
        clear_content()
        
        # PanedWindow für verstellbare Bereiche
        paned = ttk.PanedWindow(content_frame, orient=tk.VERTICAL)
        paned.pack(fill='both', expand=True)
        
        # Oberer Bereich: Charts
        charts_frame = ttk.Frame(paned)
        paned.add(charts_frame, weight=2)
        
        if matplotlib_available and stats['media_type_stats']:
            fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(12, 6))
            
            # 1. Medientypen Verteilung (Anzahl)
            media_types = [item[0] for item in stats['media_type_stats']]
            media_counts = [item[1] for item in stats['media_type_stats']]
            colors1 = plt.cm.Set2(range(len(media_types)))
            
            wedges1, texts1, autotexts1 = ax1.pie(media_counts, labels=media_types, autopct='%1.1f%%', colors=colors1)
            ax1.set_title('Medientypen (Anzahl)', fontsize=11, fontweight='bold')
            
            # 2. Medientypen Zeit-Verteilung
            media_durations = [item[2] for item in stats['media_type_stats']]
            if any(d > 0 for d in media_durations):
                duration_hours = [d/60 for d in media_durations]
                wedges2, texts2, autotexts2 = ax2.pie(duration_hours, labels=media_types, autopct='%1.1f%%', colors=colors1)
                ax2.set_title('Medientypen (Laufzeit)', fontsize=11, fontweight='bold')
            else:
                ax2.text(0.5, 0.5, 'Keine Laufzeit-\nDaten verfügbar', ha='center', va='center', transform=ax2.transAxes)
                ax2.set_title('Medientypen (Laufzeit)', fontsize=11, fontweight='bold')
            
            # 3. Top Genres Bar Chart
            if stats['genre_stats']:
                top_genres = stats['genre_stats'][:8]
                genre_names = [item[0] for item in top_genres]
                genre_counts = [item[1] for item in top_genres]
                
                colors3 = plt.cm.Set3(range(len(genre_names)))
                bars = ax3.bar(range(len(genre_names)), genre_counts, color=colors3)
                ax3.set_title('Top Genres (Anzahl)', fontsize=11, fontweight='bold')
                ax3.set_xticks(range(len(genre_names)))
                ax3.set_xticklabels(genre_names, rotation=45, ha='right', fontsize=9)
                ax3.set_ylabel('Anzahl')
                
                for bar, count in zip(bars, genre_counts):
                    height = bar.get_height()
                    ax3.text(bar.get_x() + bar.get_width()/2., height + 0.5,
                            f'{count}', ha='center', va='bottom', fontsize=8)
            else:
                ax3.text(0.5, 0.5, 'Keine Genre-\nDaten verfügbar', ha='center', va='center', transform=ax3.transAxes)
                ax3.set_title('Top Genres', fontsize=11, fontweight='bold')
            
            # 4. Dateiformate Verteilung
            if stats['file_extensions']:
                ext_items = list(stats['file_extensions'].items())
                ext_names = [item[0].upper() for item in ext_items]
                ext_counts = [item[1] for item in ext_items]
                
                colors4 = plt.cm.Pastel1(range(len(ext_names)))
                wedges4, texts4, autotexts4 = ax4.pie(ext_counts, labels=ext_names, autopct='%1.1f%%', colors=colors4)
                ax4.set_title('Dateiformate', fontsize=11, fontweight='bold')
            else:
                ax4.text(0.5, 0.5, 'Keine Format-\nDaten verfügbar', ha='center', va='center', transform=ax4.transAxes)
                ax4.set_title('Dateiformate', fontsize=11, fontweight='bold')
            
            plt.tight_layout()
            
            canvas = FigureCanvasTkAgg(fig, charts_frame)
            canvas.draw()
            canvas.get_tk_widget().pack(fill='both', expand=True, padx=5, pady=5)
        
        # Unterer Bereich: Zusammenfassung
        summary_frame = tk.LabelFrame(paned, text="Sammlung Zusammenfassung", font=('Arial', 12, 'bold'))
        paned.add(summary_frame, weight=1)
        
        summary_container = tk.Frame(summary_frame)
        summary_container.pack(fill='both', expand=True, padx=5, pady=5)
        
        summary_text = tk.Text(summary_container, height=6, font=('Arial', 10), wrap=tk.WORD)
        summary_scrollbar = tk.Scrollbar(summary_container, orient=tk.VERTICAL, command=summary_text.yview)
        summary_text.configure(yscrollcommand=summary_scrollbar.set)
        
        summary_text.pack(side='left', fill='both', expand=True)
        summary_scrollbar.pack(side='right', fill='y')
        
        # Berechne erweiterte Statistiken
        total_hours = int(stats['total_duration'] / 60) if stats['total_duration'] else 0
        total_minutes = int(stats['total_duration'] % 60) if stats['total_duration'] else 0
        
        avg_duration_per_file = stats['total_duration'] / stats['total_files'] if stats['total_files'] > 0 else 0
        avg_hours = int(avg_duration_per_file / 60)
        avg_minutes = int(avg_duration_per_file % 60)
        
        longest_media_type = ""
        if stats['media_type_stats']:
            longest = max(stats['media_type_stats'], key=lambda x: x[2])
            longest_media_type = f"{longest[0]} ({int(longest[2]/60)}h {int(longest[2]%60)}m)"
        
        top_genre = ""
        if stats['genre_stats']:
            top_genre = f"{stats['genre_stats'][0][0]} ({stats['genre_stats'][0][1]} Dateien)"
        
        summary_info = f"""SAMMLUNG ÜBERSICHT:

Gesamtdateien: {stats['total_files']:,}
Gesamtlaufzeit: {total_hours}h {total_minutes}m
Durchschnitt/Datei: {avg_hours}h {avg_minutes}m
Genres erfasst: {len(stats['genre_stats'])}
Dateiformate: {len(stats['file_extensions'])}

HIGHLIGHTS:
Beliebtestes Genre: {top_genre}
Meiste Laufzeit: {longest_media_type}
Verarbeitete Dateien: {stats['processed_duration_count']}/{stats['total_files']}
Laufzeit-Fehler: {stats['duration_errors']}

MEDIENTYPEN DETAILS:"""
        
        if stats['media_type_stats']:
            for media_type, count, duration in stats['media_type_stats']:
                hours = int(duration / 60) if duration else 0
                minutes = int(duration % 60) if duration else 0
                percentage = (count / stats['total_files']) * 100
                summary_info += f"\n• {media_type}: {count} Dateien ({percentage:.1f}%) - {hours}h {minutes}m"
        
        insert_text_utf8(summary_text, summary_info)
        summary_text.config(state=tk.DISABLED)
        
        # Rechtsklick-Menü für Summary
        def on_right_click_summary(event):
            context_menu = tk.Menu(content_frame, tearoff=0)
            context_menu.add_command(label="Alles auswählen", command=lambda: summary_text.tag_add(tk.SEL, "1.0", tk.END))
            context_menu.add_command(label="Kopieren", command=lambda: copy_selected_text(summary_text))
            context_menu.add_separator()
            context_menu.add_command(label="Alles kopieren", command=lambda: copy_to_clipboard(summary_text.get("1.0", tk.END)))
            
            try:
                context_menu.tk_popup(event.x_root, event.y_root)
            finally:
                context_menu.grab_release()
        
        summary_text.bind("<Button-3>", on_right_click_summary)
    
    def create_genres_view():
        """Genres und Kategorien Detailansicht"""
        clear_content()
        
        paned = ttk.PanedWindow(content_frame, orient=tk.HORIZONTAL)
        paned.pack(fill='both', expand=True)
        
        # Linke Seite: Genre Charts
        if matplotlib_available and stats['genre_stats']:
            charts_frame = ttk.Frame(paned)
            paned.add(charts_frame, weight=2)
            
            fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 4))
            
            # Top 10 Genres Pie Chart
            top_10_genres = stats['genre_stats'][:10]
            genre_names = [item[0] for item in top_10_genres]
            genre_counts = [item[1] for item in top_10_genres]
            
            colors = plt.cm.Set3(range(len(genre_names)))
            wedges, texts, autotexts = ax1.pie(genre_counts, labels=genre_names, autopct='%1.1f%%', colors=colors)
            ax1.set_title('Top 10 Genres', fontsize=12, fontweight='bold')
            
            # Genre Verteilung Bar Chart (Top 15)
            top_15_genres = stats['genre_stats'][:15]
            genre_names_15 = [item[0] for item in top_15_genres]
            genre_counts_15 = [item[1] for item in top_15_genres]
            
            bars = ax2.bar(range(len(genre_names_15)), genre_counts_15, color=colors)
            ax2.set_title('Top 15 Genres (Detail)', fontsize=12, fontweight='bold')
            ax2.set_xticks(range(len(genre_names_15)))
            ax2.set_xticklabels(genre_names_15, rotation=45, ha='right', fontsize=8)
            ax2.set_ylabel('Anzahl Dateien')
            
            for bar, count in zip(bars, genre_counts_15):
                height = bar.get_height()
                ax2.text(bar.get_x() + bar.get_width()/2., height + 0.5,
                        f'{count}', ha='center', va='bottom', fontsize=7)
            
            plt.tight_layout()
            
            canvas = FigureCanvasTkAgg(fig, charts_frame)
            canvas.draw()
            canvas.get_tk_widget().pack(fill='both', expand=True, padx=5, pady=5)
        
        # Rechte Seite: Genre Liste mit Statistiken
        list_frame = tk.LabelFrame(paned, text=f"Alle Genres ({len(stats['genre_stats'])})", font=('Arial', 12, 'bold'))
        paned.add(list_frame, weight=1)
        
        list_container = tk.Frame(list_frame)
        list_container.pack(fill='both', expand=True, padx=5, pady=5)
        
        genres_listbox = tk.Listbox(list_container, font=('Arial', 9), selectmode=tk.EXTENDED)
        list_scrollbar = tk.Scrollbar(list_container, orient=tk.VERTICAL, command=genres_listbox.yview)
        genres_listbox.configure(yscrollcommand=list_scrollbar.set)
        
        genres_listbox.pack(side='left', fill='both', expand=True)
        list_scrollbar.pack(side='right', fill='y')
        
        # Alle Genres mit erweiterten Infos
        for i, (genre, count) in enumerate(stats['genre_stats'], 1):
            if genre:
                percentage = (count / stats['total_files']) * 100
                if count >= 100:
                    category = "*** Hauptgenre"
                elif count >= 50:
                    category = "** Beliebtes Genre"
                elif count >= 10:
                    category = "* Standard Genre"
                else:
                    category = "Seltenes Genre"
                
                genres_listbox.insert(tk.END, f"{i:3}. {genre:<25} | {count:>4} Dateien | {percentage:5.1f}% | {category}")
        
        # Rechtsklick-Menü für Genre-Liste
        def on_right_click_genres(event):
            context_menu = tk.Menu(content_frame, tearoff=0)
            context_menu.add_command(label="Alles auswählen", command=lambda: genres_listbox.select_set(0, tk.END))
            context_menu.add_command(label="Auswahl kopieren", command=lambda: copy_selected_listbox_items(genres_listbox))
            context_menu.add_separator()
            context_menu.add_command(label="Genre-Statistik kopieren", command=lambda: copy_genre_statistics())
            
            try:
                context_menu.tk_popup(event.x_root, event.y_root)
            finally:
                context_menu.grab_release()
        
        def copy_genre_statistics():
            """Kopiert detaillierte Genre-Statistiken"""
            genre_stats_text = "GENRE STATISTIKEN\n" + "="*50 + "\n\n"
            for i, (genre, count) in enumerate(stats['genre_stats'], 1):
                if genre:
                    percentage = (count / stats['total_files']) * 100
                    genre_stats_text += f"{i:3}. {genre:<30} {count:>6} Dateien ({percentage:5.1f}%)\n"
            copy_to_clipboard(genre_stats_text)
        
        genres_listbox.bind("<Button-3>", on_right_click_genres)
    
    def create_formats_view():
        """Original Dateiformate-Ansicht (erweitert)"""
        clear_content()
        
        # PanedWindow für verstellbare Höhe
        paned = ttk.PanedWindow(content_frame, orient=tk.VERTICAL)
        paned.pack(fill='both', expand=True)
        
        # Charts-Frame (oberer Bereich)
        charts_frame = ttk.Frame(paned)
        paned.add(charts_frame, weight=2)
        
        if matplotlib_available:
            fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 3))
            
            extensions = list(stats['file_extensions'].keys())
            counts = list(stats['file_extensions'].values())
            
            colors = plt.cm.Set3(range(len(extensions)))
            
            wedges, texts, autotexts = ax1.pie(counts, labels=extensions, autopct='%1.1f%%', colors=colors)
            ax1.set_title('Dateitypen Verteilung', fontsize=12, fontweight='bold')
            
            ax2.bar(extensions, counts, color=colors)
            ax2.set_title('Anzahl pro Dateityp', fontsize=12, fontweight='bold')
            ax2.set_ylabel('Anzahl Dateien')
            ax2.tick_params(axis='x', rotation=45, labelsize=10)
            
            plt.tight_layout()
            
            canvas = FigureCanvasTkAgg(fig, charts_frame)
            canvas.draw()
            canvas.get_tk_widget().pack(fill='both', expand=True, padx=10, pady=10)
        
        # Details-Frame (unterer Bereich)
        details_frame = tk.LabelFrame(paned, text="Dateiformate Details", font=('Arial', 12, 'bold'))
        paned.add(details_frame, weight=1)
        
        details_container = tk.Frame(details_frame)
        details_container.pack(fill='both', expand=True, padx=5, pady=5)
        
        details_text = tk.Text(details_container, height=8, font=('Arial', 10))
        details_scrollbar = tk.Scrollbar(details_container, orient=tk.VERTICAL, command=details_text.yview)
        details_text.configure(yscrollcommand=details_scrollbar.set)
        
        details_text.pack(side='left', fill='both', expand=True)
        details_scrollbar.pack(side='right', fill='y')
        
        # Erweiterte Format-Analyse
        sorted_extensions = sorted(stats['file_extensions'].items(), key=lambda x: x[1], reverse=True)
        
        details_text.insert(tk.END, "DATEIFORMATE ANALYSE\n")
        details_text.insert(tk.END, "="*60 + "\n\n")
        details_text.insert(tk.END, f"{'Format':<8} {'Anzahl':<8} {'Anteil':<8} {'Kategorie':<15} {'Beschreibung'}\n")
        details_text.insert(tk.END, "-"*60 + "\n")
        
        format_categories = {
            '.mp4': ('Video', 'Standard Video (H.264)'),
            '.mkv': ('Video', 'Matroska Video Container'),
            '.avi': ('Video', 'Audio Video Interleave'),
            '.mov': ('Video', 'QuickTime Movie'),
            '.wmv': ('Video', 'Windows Media Video'),
            '.flv': ('Video', 'Flash Video'),
            '.mp3': ('Audio', 'MPEG Audio Layer 3'),
            '.flac': ('Audio', 'Free Lossless Audio Codec'),
            '.wav': ('Audio', 'Waveform Audio'),
            '.m4a': ('Audio', 'MPEG-4 Audio'),
            '.xspf': ('Playlist', 'XML Shareable Playlist')
        }
        
        for ext, count in sorted_extensions:
            percentage = (count / stats['total_files']) * 100
            category, description = format_categories.get(ext.lower(), ('Andere', 'Unbekanntes Format'))
            
            details_text.insert(tk.END, f"{ext.upper():<8} {count:<8} {percentage:5.1f}%   {category:<15} {description}\n")
        
        details_text.insert(tk.END, "\n" + "="*60 + "\n")
        details_text.insert(tk.END, "ZUSAMMENFASSUNG:\n")
        details_text.insert(tk.END, f"• Verschiedene Formate: {len(stats['file_extensions'])}\n")
        
        video_formats = sum(count for ext, count in stats['file_extensions'].items() 
                           if ext.lower() in ['.mp4', '.mkv', '.avi', '.mov', '.wmv', '.flv'])
        audio_formats = sum(count for ext, count in stats['file_extensions'].items() 
                           if ext.lower() in ['.mp3', '.flac', '.wav', '.m4a'])
        
        details_text.insert(tk.END, f"• Video-Dateien: {video_formats} ({(video_formats/stats['total_files']*100):5.1f}%)\n")
        details_text.insert(tk.END, f"• Audio-Dateien: {audio_formats} ({(audio_formats/stats['total_files']*100):5.1f}%)\n")
        details_text.insert(tk.END, f"• Andere Formate: {stats['total_files'] - video_formats - audio_formats}\n")
        
        details_text.config(state=tk.DISABLED)
        
        # Rechtsklick-Menü für Details
        def on_right_click_details(event):
            context_menu = tk.Menu(content_frame, tearoff=0)
            context_menu.add_command(label="Alles auswählen", command=lambda: details_text.tag_add(tk.SEL, "1.0", tk.END))
            context_menu.add_command(label="Kopieren", command=lambda: copy_selected_text(details_text))
            context_menu.add_separator()
            context_menu.add_command(label="Alles kopieren", command=lambda: copy_to_clipboard(details_text.get("1.0", tk.END)))
            
            try:
                context_menu.tk_popup(event.x_root, event.y_root)
            finally:
                context_menu.grab_release()
        
        details_text.bind("<Button-3>", on_right_click_details)
    
    def create_storage_view():
        """Speicherauslastung mit vollständig dynamischen Kategorien"""
        clear_content()
        
        paned = ttk.PanedWindow(content_frame, orient=tk.VERTICAL)
        paned.pack(fill='both', expand=True)
        
        charts_frame = ttk.Frame(paned)
        paned.add(charts_frame, weight=2)
        
        category_sizes_gb = {}  # WICHTIG: Außerhalb des try-Blocks initialisieren
        
        if matplotlib_available:
            try:
                if folder_path:
                    drive = os.path.splitdrive(folder_path)[0] or folder_path.split(os.sep)[0]
                    if not drive.endswith(os.sep):
                        drive += os.sep
                    
                    disk_usage = shutil.disk_usage(drive)
                    total_gb = disk_usage.total / (1024**3)
                    used_gb = disk_usage.used / (1024**3)
                    free_gb = disk_usage.free / (1024**3)
                    
                    conn = sqlite3.connect('media_index.db')
                    cursor = conn.cursor()
                    
                    cursor.execute("SELECT filepath FROM media_files")
                    all_files = cursor.fetchall()
                    
                    category_sizes = defaultdict(int)
                    
                    for (filepath,) in all_files:
                        try:
                            if os.path.exists(filepath):
                                file_size = os.path.getsize(filepath)
                                
                                path_meta = classify_path_dynamic(filepath)
                                main_category = path_meta.get('main_category')
                                
                                if main_category:
                                    category_sizes[main_category] += file_size
                                else:
                                    category_sizes['Unkategorisiert'] += file_size
                                        
                        except Exception as e:
                            print(f"Fehler bei Dateigröße für {filepath}: {e}")
                    
                    conn.close()
                    
                    category_sizes_gb = {k: v/(1024**3) for k, v in category_sizes.items()}
                    
                    # Rest der Chart-Erstellung...
                    
            except Exception as e:
                print(f"Fehler bei Speicheranalyse: {e}")
                import traceback
                traceback.print_exc()
        
        # Details-Frame verwendet category_sizes_gb
        details_frame = tk.LabelFrame(paned, text="Speicher Details", font=('Arial', 12, 'bold'))
        paned.add(details_frame, weight=1)
        
        details_container = tk.Frame(details_frame)
        details_container.pack(fill='both', expand=True, padx=5, pady=5)
        
        details_text = tk.Text(details_container, height=8, font=('Arial', 10), wrap=tk.WORD)
        details_scrollbar = tk.Scrollbar(details_container, orient=tk.VERTICAL, command=details_text.yview)
        details_text.configure(yscrollcommand=details_scrollbar.set)
        
        details_text.pack(side='left', fill='both', expand=True)
        details_scrollbar.pack(side='right', fill='y')
        
        try:
            if folder_path and category_sizes_gb:  # Prüfung hinzugefügt
                drive = os.path.splitdrive(folder_path)[0] or folder_path.split(os.sep)[0]
                if not drive.endswith(os.sep):
                    drive += os.sep
                
                disk_usage = shutil.disk_usage(drive)
                total_gb = disk_usage.total / (1024**3)
                used_gb = disk_usage.used / (1024**3)
                free_gb = disk_usage.free / (1024**3)
                used_percent = (used_gb / total_gb) * 100
                
                details_info = f"""SPEICHERAUSLASTUNG ANALYSE

    LAUFWERK: {drive}
    {'='*50}

    Gesamtspeicher: {total_gb:,.1f} GB
    Belegt: {used_gb:,.1f} GB ({used_percent:.1f}%)
    Frei: {free_gb:,.1f} GB ({100-used_percent:.1f}%)

    MEDIEN-SAMMLUNG:
    {'='*50}
    """
                
                total_media_size = sum(category_sizes_gb.values())
                details_info += f"\nGesamtgröße Sammlung: {total_media_size:,.1f} GB\n"
                details_info += f"Anteil am Laufwerk: {(total_media_size/total_gb)*100:.2f}%\n\n"
                details_info += "KATEGORIEN:\n"
                
                for category, size_gb in sorted(category_sizes_gb.items(), key=lambda x: x[1], reverse=True):
                    percent_of_media = (size_gb / total_media_size) * 100 if total_media_size > 0 else 0
                    percent_of_disk = (size_gb / total_gb) * 100
                    details_info += f"• {category}: {size_gb:,.1f} GB ({percent_of_media:.1f}% der Sammlung, {percent_of_disk:.2f}% des Laufwerks)\n"
                
                insert_text_utf8(details_text, details_info)
            else:
                details_text.insert(tk.END, "Kein Ordner ausgewählt oder keine Kategorie-Daten verfügbar.")
                
        except Exception as e:
            details_text.insert(tk.END, f"Fehler beim Laden der Details:\n{str(e)}")
        
        details_text.config(state=tk.DISABLED)
        
        # Rechtsklick-Menü
        def on_right_click_storage(event):
            context_menu = tk.Menu(content_frame, tearoff=0)
            context_menu.add_command(label="Alles auswählen", command=lambda: details_text.tag_add(tk.SEL, "1.0", tk.END))
            context_menu.add_command(label="Kopieren", command=lambda: copy_selected_text(details_text))
            context_menu.add_separator()
            context_menu.add_command(label="Alles kopieren", command=lambda: copy_to_clipboard(details_text.get("1.0", tk.END)))
            
            try:
                context_menu.tk_popup(event.x_root, event.y_root)
            finally:
                context_menu.grab_release()
        
        details_text.bind("<Button-3>", on_right_click_storage)
    
    def update_view():
        """Aktualisiert die Ansicht basierend auf der Auswahl"""
        view = current_view.get()
        
        if view == "overview":
            create_overview_view()
        elif view == "genres":
            create_genres_view()
        elif view == "formats":
            create_formats_view()
        elif view == "storage":
            create_storage_view()
    
    # Standard-Ansicht laden (Übersicht)
    update_view()

def create_genres_tab(parent, stats):
    """Erstellt die Genres & Jahre Tab mit mehr Einträgen und Multi-Select"""
    main_paned = ttk.PanedWindow(parent, orient=tk.HORIZONTAL)
    main_paned.pack(fill='both', expand=True, padx=5, pady=5)
    
    # Genres-Frame (linke Seite)
    genres_frame = tk.LabelFrame(main_paned, text=f"Alle Genres ({len(stats['genre_stats'])})", font=('Arial', 12, 'bold'))
    main_paned.add(genres_frame, weight=2)
    
    genres_container = tk.Frame(genres_frame)
    genres_container.pack(fill='both', expand=True, padx=5, pady=5)
    
    genres_list = tk.Listbox(genres_container, font=('Arial', 9), selectmode=tk.EXTENDED)  # Multi-Select aktiviert
    genres_scrollbar = tk.Scrollbar(genres_container, orient=tk.VERTICAL, command=genres_list.yview)
    genres_list.configure(yscrollcommand=genres_scrollbar.set)
    
    genres_list.pack(side='left', fill='both', expand=True)
    genres_scrollbar.pack(side='right', fill='y')
    
    # Alle Genres anzeigen (nicht limitiert)
    for genre, count in stats['genre_stats']:
        if genre:
            percentage = (count / stats['total_files']) * 100
            genres_list.insert(tk.END, f"{genre} ({count}, {percentage:.1f}%)")
    
    # Rechtsklick-Menü für Genres
    def on_right_click_genres(event):
        context_menu = tk.Menu(root, tearoff=0)
        context_menu.add_command(label="Alles auswählen", command=lambda: genres_list.select_set(0, tk.END))
        context_menu.add_command(label="Auswahl kopieren", command=lambda: copy_selected_listbox_items(genres_list))
        context_menu.add_separator()
        context_menu.add_command(label="Alle kopieren", command=lambda: copy_all_listbox_items(genres_list))
        
        try:
            context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            context_menu.grab_release()
    
    genres_list.bind("<Button-3>", on_right_click_genres)
    
    # Rechte Seite - vertikal geteilt
    right_paned = ttk.PanedWindow(main_paned, orient=tk.VERTICAL)
    main_paned.add(right_paned, weight=3)
    
    # Künstler/Schauspieler (obere rechte Seite)
    if stats.get('actors_stats') or stats.get('contributors_stats'):
        artists_frame = tk.LabelFrame(right_paned, text="Künstler/Schauspieler", font=('Arial', 12, 'bold'))
        right_paned.add(artists_frame, weight=1)
        
        artists_container = tk.Frame(artists_frame)
        artists_container.pack(fill='both', expand=True, padx=5, pady=5)
        
        artists_list = tk.Listbox(artists_container, font=('Arial', 9), selectmode=tk.EXTENDED)  # Multi-Select
        artists_scrollbar = tk.Scrollbar(artists_container, orient=tk.VERTICAL, command=artists_list.yview)
        artists_list.configure(yscrollcommand=artists_scrollbar.set)
        
        artists_list.pack(side='left', fill='both', expand=True)
        artists_scrollbar.pack(side='right', fill='y')
        
        if stats.get('actors_stats'):
            artists_list.insert(tk.END, "=== SCHAUSPIELER/FILMREIHEN ===")
            for actor, count in stats['actors_stats'][:100]:  # Mehr Einträge (100 statt 30)
                if actor:
                    artists_list.insert(tk.END, f"{actor} ({count})")
        
        if stats.get('contributors_stats'):
            artists_list.insert(tk.END, "")
            artists_list.insert(tk.END, "=== INTERPRETEN ===")
            for contributor, count in stats['contributors_stats'][:100]:  # Mehr Einträge (100 statt 30)
                if contributor:
                    artists_list.insert(tk.END, f"{contributor} ({count})")
        
        # Rechtsklick-Menü für Künstler
        def on_right_click_artists(event):
            context_menu = tk.Menu(root, tearoff=0)
            context_menu.add_command(label="Alles auswählen", command=lambda: artists_list.select_set(0, tk.END))
            context_menu.add_command(label="Auswahl kopieren", command=lambda: copy_selected_listbox_items(artists_list))
            context_menu.add_separator()
            context_menu.add_command(label="Alle kopieren", command=lambda: copy_all_listbox_items(artists_list))
            
            try:
                context_menu.tk_popup(event.x_root, event.y_root)
            finally:
                context_menu.grab_release()
        
        artists_list.bind("<Button-3>", on_right_click_artists)
    
    # Jahre (untere rechte Seite)
    years_frame = tk.LabelFrame(right_paned, text=f"Jahre ({len(stats['year_stats'])})", font=('Arial', 12, 'bold'))
    right_paned.add(years_frame, weight=1)
    
    years_container = tk.Frame(years_frame)
    years_container.pack(fill='both', expand=True, padx=5, pady=5)
    
    years_list = tk.Listbox(years_container, font=('Arial', 9), selectmode=tk.EXTENDED)  # Multi-Select
    years_scrollbar = tk.Scrollbar(years_container, orient=tk.VERTICAL, command=years_list.yview)
    years_list.configure(yscrollcommand=years_scrollbar.set)
    
    years_list.pack(side='left', fill='both', expand=True)
    years_scrollbar.pack(side='right', fill='y')
    
    # Alle Jahre anzeigen (nicht limitiert)
    for year, count in stats['year_stats']:
        if year and year != '0':
            percentage = (count / stats['total_files']) * 100
            years_list.insert(tk.END, f"{year} ({count}, {percentage:.1f}%)")
    
    # Rechtsklick-Menü für Jahre
    def on_right_click_years(event):
        context_menu = tk.Menu(root, tearoff=0)
        context_menu.add_command(label="Alles auswählen", command=lambda: years_list.select_set(0, tk.END))
        context_menu.add_command(label="Auswahl kopieren", command=lambda: copy_selected_listbox_items(years_list))
        context_menu.add_separator()
        context_menu.add_command(label="Alle kopieren", command=lambda: copy_all_listbox_items(years_list))
        
        try:
            context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            context_menu.grab_release()
    
    years_list.bind("<Button-3>", on_right_click_years)

def copy_selected_text(text_widget):
    """Kopiert markierten Text aus Text-Widget"""
    try:
        selected_text = text_widget.get(tk.SEL_FIRST, tk.SEL_LAST)
        copy_to_clipboard(selected_text)
    except tk.TclError:
        # Keine Auswahl vorhanden
        pass

def copy_selected_listbox_items(listbox):
    """Kopiert ausgewählte Einträge aus Listbox"""
    selected_indices = listbox.curselection()
    if selected_indices:
        selected_items = [listbox.get(i) for i in selected_indices]
        copy_to_clipboard('\n'.join(selected_items))

def copy_all_listbox_items(listbox):
    """Kopiert alle Einträge aus Listbox"""
    all_items = [listbox.get(i) for i in range(listbox.size())]
    copy_to_clipboard('\n'.join(all_items))

def create_hierarchy_tab(parent, stats):
    """
    KORRIGIERT: Hierarchie-Tab mit robuster Baumdarstellung für beliebige Tiefe
    """
    paned = ttk.PanedWindow(parent, orient=tk.VERTICAL)
    paned.pack(fill='both', expand=True, padx=5, pady=5)
    
    tree_frame = ttk.Frame(paned)
    paned.add(tree_frame, weight=3)
    
    header_frame = tk.Frame(tree_frame)
    header_frame.pack(fill='x', padx=10, pady=5)
    tk.Label(header_frame, text="Ordnerstruktur (Dynamisch)", font=('Arial', 14, 'bold')).pack()
    
    tree_container = tk.Frame(tree_frame)
    tree_container.pack(fill='both', expand=True, padx=10, pady=10)
    
    tree = ttk.Treeview(tree_container, columns=('count', 'type'), show='tree headings')
    tree.heading('#0', text='Ordner/Datei')
    tree.heading('count', text='Anzahl')
    tree.heading('type', text='Typ')
    
    tree.column('#0', width=400)
    tree.column('count', width=80)
    tree.column('type', width=100)
    
    tree_scroll_y = ttk.Scrollbar(tree_container, orient=tk.VERTICAL, command=tree.yview)
    tree_scroll_x = ttk.Scrollbar(tree_container, orient=tk.HORIZONTAL, command=tree.xview)
    tree.configure(yscrollcommand=tree_scroll_y.set, xscrollcommand=tree_scroll_x.set)
    
    tree.grid(row=0, column=0, sticky='nsew')
    tree_scroll_y.grid(row=0, column=1, sticky='ns')
    tree_scroll_x.grid(row=1, column=0, sticky='ew')
    
    tree_container.grid_rowconfigure(0, weight=1)
    tree_container.grid_columnconfigure(0, weight=1)
    
    def add_tree_nodes_recursive(parent_id, node_data, level=0):
        """Rekursive Funktion zum Hinzufügen beliebig tiefer Nodes"""
        if not isinstance(node_data, dict):
            return
        
        children = node_data.get('children', {})
        files = node_data.get('files', [])
        
        # Füge Dateien hinzu
        for file_info in files:
            tree.insert(parent_id, 'end', text=file_info['name'],
                       values=('', 'Datei'),
                       tags=('file', file_info['path']))
        
        # Füge Unterordner rekursiv hinzu
        if children:
            sorted_children = sorted(children.items(), key=lambda x: x[1].get('count', 0), reverse=True)
            for child_name, child_data in sorted_children:
                if child_name and child_data.get('count', 0) > 0:
                    child_id = tree.insert(parent_id, 'end', text=child_name,
                                          values=(child_data.get('count', 0), f'Level {level+1}'),
                                          tags=(f'level_{level+1}',))
                    
                    # Rekursiv in die Tiefe gehen
                    add_tree_nodes_recursive(child_id, child_data, level + 1)
    
    if stats['hierarchy']:
        sorted_main = sorted(stats['hierarchy'].items(), key=lambda x: x[1].get('count', 0), reverse=True)
        
        for main_cat, main_data in sorted_main:
            if main_cat and main_data.get('count', 0) > 0:
                main_id = tree.insert('', 'end', text=main_cat, 
                                    values=(main_data.get('count', 0), 'Hauptkategorie'),
                                    tags=('category',))
                
                # Verwende rekursive Funktion
                add_tree_nodes_recursive(main_id, main_data, level=1)
    
    def on_right_click(event):
        item = tree.selection()[0] if tree.selection() else None
        if item:
            tags = tree.item(item, 'tags')
            if 'file' in tags and len(tags) > 1:
                file_path = tags[1]
                
                context_menu = tk.Menu(root, tearoff=0)
                context_menu.add_command(label="Datei öffnen", command=lambda: safe_startfile(file_path))
                context_menu.add_command(label="Pfad kopieren", command=lambda: copy_to_clipboard(file_path))
                context_menu.add_separator()
                context_menu.add_command(label="Im Explorer anzeigen", command=lambda: show_in_explorer(file_path))
                
                try:
                    context_menu.tk_popup(event.x_root, event.y_root)
                finally:
                    context_menu.grab_release()
    
    tree.bind("<Button-3>", on_right_click)
    
    # Zusammenfassung
    summary_frame = ttk.Frame(paned)
    paned.add(summary_frame, weight=1)
    
    if stats['hierarchy']:
        summary_label_frame = tk.LabelFrame(summary_frame, text="Zusammenfassung", font=('Arial', 12, 'bold'))
        summary_label_frame.pack(fill='both', expand=True, padx=10, pady=10)
        
        summary_text = tk.Text(summary_label_frame, height=6, font=('Arial', 10))
        summary_scrollbar = tk.Scrollbar(summary_label_frame, orient=tk.VERTICAL, command=summary_text.yview)
        summary_text.configure(yscrollcommand=summary_scrollbar.set)
        
        summary_text.pack(side='left', fill='both', expand=True, padx=5, pady=5)
        summary_scrollbar.pack(side='right', fill='y', pady=5)
        
        # Berechne Statistiken
        main_categories = len(stats['hierarchy'])
        total_subcategories = 0
        max_depth = 0
        
        def count_depth(node, current_depth=1):
            """Rekursiv maximale Tiefe ermitteln"""
            nonlocal max_depth, total_subcategories
            max_depth = max(max_depth, current_depth)
            
            if isinstance(node, dict) and 'children' in node:
                children = node['children']
                total_subcategories += len(children)
                for child in children.values():
                    count_depth(child, current_depth + 1)
        
        for category_data in stats['hierarchy'].values():
            count_depth(category_data)
        
        total_files_in_tree = sum(len(data.get('files', [])) for data in stats['hierarchy'].values())
        
        summary_text.insert(tk.END, f"Hauptkategorien: {main_categories}\n")
        summary_text.insert(tk.END, f"Unterkategorien (gesamt): {total_subcategories}\n")
        summary_text.insert(tk.END, f"Maximale Hierarchie-Tiefe: {max_depth} Ebenen\n")
        summary_text.insert(tk.END, f"Dateien: {total_files_in_tree}\n")
        
        if main_categories > 0:
            summary_text.insert(tk.END, f"Durchschnitt Dateien/Kategorie: {stats['total_files']/main_categories:.1f}\n")
        
        summary_text.insert(tk.END, f"\nStruktur: Vollständig dynamisch\n")
        summary_text.insert(tk.END, f"Doppelklick zum Erweitern\n")
        summary_text.insert(tk.END, f"Rechtsklick auf Dateien für Optionen")
        
        summary_text.config(state=tk.DISABLED)

def open_settings():
    """Settings mit Genre-Normalisierungs-Button"""
    global settings_window, title_checkbox, genre_checkbox, actors_checkbox
    global comment_checkbox, album_checkbox, interpret_checkbox

    if settings_window and settings_window.winfo_exists():
        settings_window.lift()
        settings_window.focus_force()
        return

    settings_window = tk.Toplevel(root)
    settings_window.title("Benutzer Einstellungen")
    settings_window.geometry("400x650")  # Höhe erhöht

    tk.Label(settings_window, text="Datenbank-Verwaltung", 
             font=('Arial', 12, 'bold')).pack(pady=(10, 5))
    
    tk.Button(settings_window, text="Erstelle / Reset Datenbank", 
              command=create_or_reset_db, bg='lightcoral').pack(pady=5)
    
    tk.Button(settings_window, text="🔄 Synchronize Drive & Database", 
              command=train_db_with_progress, bg='lightgreen').pack(pady=5)
    
    # NEU: Genre-Normalisierung
    tk.Button(settings_window, text="🏷️ Genre-Normalisierung", 
              command=normalize_all_genres_in_database, bg='lightyellow').pack(pady=5)
    
    tk.Label(settings_window, text="Bereinigt Duplikate wie Pop/POP/pop,\n"
                                   "Techno/TECHNO, Rock/rock, etc.", 
             font=('Arial', 8), fg='gray').pack(pady=(0, 5))
    
    tk.Button(settings_window, text="📊 Sammlung Statistiken", 
              command=create_analytics_window).pack(pady=10)
    
    # Debug-Mode
    debug_mode = config.getboolean('Settings', 'debug_mode', fallback=False)
    if debug_mode:
        tk.Label(settings_window, text="Debug-Tools", 
                 font=('Arial', 10, 'bold')).pack(pady=(10, 5))
        tk.Button(settings_window, text="Debug Video Metadaten", 
                  command=debug_video_metadata).pack(pady=5)
        tk.Button(settings_window, text="Test Einzeldatei-Laufzeit", 
                  command=test_single_file_duration).pack(pady=5)

    tk.Label(settings_window, text="Such-Optionen", 
             font=('Arial', 10, 'bold')).pack(pady=(10, 5))
    
    use_db_checkbox = tk.Checkbutton(settings_window, 
                                     text="Benutze SQL-Datenbank bei der Suche", 
                                     variable=use_db_var, 
                                     command=toggle_search_options)
    use_db_checkbox.pack(pady=5)

    title_checkbox = tk.Checkbutton(settings_window, 
                                    text="Titelsuche (Dateiname/Ordnername)", 
                                    variable=title_search_var, state=tk.DISABLED)
    title_checkbox.pack(pady=2)

    genre_checkbox = tk.Checkbutton(settings_window, 
                                    text="Metatag Genre der Datei", 
                                    variable=genre_var, state=tk.DISABLED)
    genre_checkbox.pack(pady=2)

    actors_checkbox = tk.Checkbutton(settings_window, 
                                     text="Metatag Schauspieler der Datei", 
                                     variable=actors_var, state=tk.DISABLED)
    actors_checkbox.pack(pady=2)

    comment_checkbox = tk.Checkbutton(settings_window, 
                                      text="Metatag 'comment' der Datei", 
                                      variable=comment_var, state=tk.DISABLED)
    comment_checkbox.pack(pady=2)

    album_checkbox = tk.Checkbutton(settings_window, 
                                    text="Metatag Album der Datei", 
                                    variable=album_search_var, state=tk.DISABLED)
    album_checkbox.pack(pady=2)

    interpret_checkbox = tk.Checkbutton(settings_window, 
                                        text="Metatag Interpret der Datei", 
                                        variable=interpret_search_var, state=tk.DISABLED)
    interpret_checkbox.pack(pady=2)

    toggle_search_options()

    save_button = tk.Button(settings_window, text="Speichern", command=save_settings)
    save_button.pack(pady=10)

    close_button = tk.Button(settings_window, text="Schließen", 
                             command=lambda: on_close_settings(settings_window))
    close_button.pack(pady=5)

    load_settings()


def test_path_normalization():
    """
    Debug: Testet Pfad-Normalisierung
    """
    test_paths = [
        "F:/Filme",
        "F:\\Filme",
        "F:/Filme/Action",
        "F:\\Filme\\Action"
    ]
    
    results = "PFAD-NORMALISIERUNGS-TEST\n" + "="*60 + "\n\n"
    
    for path in test_paths:
        normalized = os.path.normpath(path)
        sql_escaped = normalized.replace('\\', '\\\\')
        results += f"Original:     {path}\n"
        results += f"Normalisiert: {normalized}\n"
        results += f"SQL-Escaped:  {sql_escaped}\n"
        results += "-"*60 + "\n"
    
    # Teste mit Datenbank
    try:
        conn = sqlite3.connect('media_index.db')
        cursor = conn.cursor()
        
        results += "\nDATENBANK-TEST:\n"
        
        for path in test_paths:
            normalized = os.path.normpath(path)
            sql_escaped = normalized.replace('\\', '\\\\')
            
            cursor.execute(
                "SELECT COUNT(*) FROM media_files WHERE filepath LIKE ? ESCAPE '\\'",
                (f"{sql_escaped}%",)
            )
            count = cursor.fetchone()[0]
            
            results += f"\nPfad: {path}\n"
            results += f"Treffer: {count:,}\n"
        
        conn.close()
        
    except Exception as e:
        results += f"\nDatenbank-Fehler: {e}\n"
    
    messagebox.showinfo("Pfad-Test", results)
    print(results)

def on_close_settings(window):
    global settings_window
    settings_window = None
    window.destroy()
    
def on_keypress(event):
    if event.keysym == 'Return':
        perform_search()

def on_closing():
    """Verbesserte Anwendungsbeendigung mit robustem Cleanup"""
    try:
        print("Starte Anwendungsbeendigung...")
        
        # Signalisiere allen Threads das Ende
        root._shutting_down = True
        
        # 1. UI-Elemente schließen
        try:
            cleanup_all_tooltips()
        except:
            pass
        
        # 2. Alle Fenster schließen
        try:
            for window in root.winfo_children():
                if isinstance(window, tk.Toplevel):
                    try:
                        window.destroy()
                    except:
                        pass
        except:
            pass
        
        # 3. Datenbank-Connections schließen
        try:
            import sqlite3
            import gc
            gc.collect()  # Erzwinge Garbage Collection
        except:
            pass
        
        # 4. Config speichern
        try:
            save_last_directory()
        except:
            pass
        
        # 5. Root-Widget beenden
        try:
            if root and root.winfo_exists():
                root.quit()
        except:
            pass
        
        print("Anwendung erfolgreich beendet.")
        
    except Exception as e:
        print(f"Fehler beim Beenden: {e}")
    finally:
        # Notfall-Beendigung
        try:
            import os
            os._exit(0)
        except:
            pass

def stop_all_threads():
    """Stoppt alle laufenden Threads"""
    try:
        import threading
        
        # Liste aller aktiven Threads
        active_threads = threading.enumerate()
        main_thread = threading.main_thread()
        
        print(f"Aktive Threads: {len(active_threads)}")
        
        for thread in active_threads:
            if thread != main_thread and thread.is_alive():
                print(f"Stoppe Thread: {thread.name}")
                if hasattr(thread, '_stop'):
                    thread._stop()
                    
        # Warte kurz auf Thread-Beendigung
        import time
        time.sleep(0.5)
        
    except Exception as e:
        print(f"Fehler beim Stoppen der Threads: {e}")

def cleanup_tts_engine():
    """Bereinigt TTS-Engine Ressourcen"""
    try:
        # Versuche alle pyttsx3-Engines zu stoppen
        import pyttsx3
        # TTS-Engine kann im Hintergrund laufen - force cleanup
        print("Bereinige TTS-Engine...")
        
    except Exception as e:
        print(f"TTS-Cleanup Fehler: {e}")

def cleanup_all_widgets():
    """Sichere Bereinigung aller Widgets mit umfassender Fehlerbehandlung"""
    try:
        print("Bereinige alle Widgets...")
        
        # Root-Children bereinigen
        try:
            if root and root.winfo_exists():
                children = list(root.winfo_children())
                for widget in children:
                    try:
                        cleanup_widget_tooltips(widget)
                    except (tk.TclError, AttributeError):
                        pass
        except (tk.TclError, AttributeError):
            pass
            
        # Canvas-spezifische Bereinigung
        cleanup_canvas_widgets()
        
    except Exception as e:
        print(f"Widget-Cleanup Fehler (ignoriert): {e}")

def cleanup_canvas_widgets():
    """Sichere Bereinigung für Canvas-Widgets mit Existenzprüfungen"""
    try:
        global folder_canvas, media_canvas, folder_frame, media_frame
        
        # Folder Canvas bereinigen
        if 'folder_canvas' in globals() and folder_canvas:
            try:
                if folder_canvas.winfo_exists():
                    folder_canvas.delete("all")
            except (tk.TclError, AttributeError):
                pass
            
        # Media Canvas bereinigen  
        if 'media_canvas' in globals() and media_canvas:
            try:
                if media_canvas.winfo_exists():
                    media_canvas.delete("all")
            except (tk.TclError, AttributeError):
                pass
            
        # Folder Frame bereinigen
        if 'folder_frame' in globals() and folder_frame:
            try:
                if folder_frame.winfo_exists():
                    for widget in folder_frame.winfo_children():
                        try:
                            if widget.winfo_exists():
                                cleanup_widget_tooltips(widget)
                        except (tk.TclError, AttributeError):
                            pass
            except (tk.TclError, AttributeError):
                pass
                
        # Media Frame bereinigen
        if 'media_frame' in globals() and media_frame:
            try:
                if media_frame.winfo_exists():
                    for widget in media_frame.winfo_children():
                        try:
                            if widget.winfo_exists():
                                cleanup_widget_tooltips(widget)
                        except (tk.TclError, AttributeError):
                            pass
            except (tk.TclError, AttributeError):
                pass
                
    except Exception as e:
        print(f"Canvas-Cleanup Fehler (ignoriert): {e}")

def close_analytics_window():
    """Sichere Schließung des Analytics-Fensters"""
    try:
        global analytics_window
        if 'analytics_window' in globals() and analytics_window:
            try:
                if analytics_window.winfo_exists():
                    print("Schließe Analytics-Fenster...")
                    analytics_window.destroy()
            except (tk.TclError, AttributeError):
                pass
            analytics_window = None
    except Exception as e:
        print(f"Analytics-Cleanup Fehler (ignoriert): {e}")

def close_settings_window():
    """Sichere Schließung des Settings-Fensters"""
    try:
        global settings_window
        if 'settings_window' in globals() and settings_window:
            try:
                if settings_window.winfo_exists():
                    print("Schließe Settings-Fenster...")
                    settings_window.destroy()
            except (tk.TclError, AttributeError):
                pass
            settings_window = None
    except Exception as e:
        print(f"Settings-Cleanup Fehler (ignoriert): {e}")

def cleanup_event_bindings():
    """Sichere Entfernung aller Event-Bindings mit Existenzprüfungen"""
    try:
        print("Entferne Event-Bindings...")
        
        # Root-Bindings entfernen
        try:
            if root and root.winfo_exists():
                root.unbind_all("<MouseWheel>")
                root.unbind('<Configure>')
        except (tk.TclError, AttributeError):
            pass
        
        # Folder Canvas Bindings
        if 'folder_canvas' in globals() and folder_canvas:
            try:
                if folder_canvas.winfo_exists():
                    folder_canvas.unbind("<Enter>")
                    folder_canvas.unbind("<Leave>")
                    folder_canvas.unbind('<Configure>')
            except (tk.TclError, AttributeError):
                pass
            
        # Media Canvas Bindings
        if 'media_canvas' in globals() and media_canvas:
            try:
                if media_canvas.winfo_exists():
                    media_canvas.unbind("<Enter>")
                    media_canvas.unbind("<Leave>")
                    media_canvas.unbind('<Configure>')
            except (tk.TclError, AttributeError):
                pass
            
        # Search Entry Bindings
        if 'search_entry' in globals() and search_entry:
            try:
                if search_entry.winfo_exists():
                    search_entry.unbind('<Key>')
            except (tk.TclError, AttributeError):
                pass
            
    except Exception as e:
        print(f"Event-Binding Cleanup Fehler (ignoriert): {e}")

def cleanup_matplotlib_resources():
    """Bereinigt Matplotlib-Ressourcen"""
    try:
        import matplotlib.pyplot as plt
        
        print("Bereinige Matplotlib...")
        plt.close('all')  # Schließt alle Figures
        
        # Clear backend
        try:
            plt.switch_backend('Agg')  # Wechsle zu non-GUI backend
        except:
            pass
            
    except Exception as e:
        print(f"Matplotlib-Cleanup Fehler: {e}")

def cleanup_database_connections():
    """Schließt alle offenen Datenbankverbindungen"""
    try:
        import sqlite3
        
        print("Schließe Datenbank-Verbindungen...")
        
        # Alle offenen Connections schließen ist schwierig
        # SQLite sollte automatisch schließen, aber sicherheitshalber:
        import gc
        gc.collect()  # Garbage Collection
        
    except Exception as e:
        print(f"Database-Cleanup Fehler: {e}")

def cleanup_widget_tooltips(widget):
    """Rekursive Tooltip-Bereinigung mit verbesserter Fehlerbehandlung"""
    try:
        # Prüfe Widget-Existenz
        if not widget or not hasattr(widget, 'winfo_exists'):
            return
        try:
            if not widget.winfo_exists():
                return
        except tk.TclError:
            return
            
        # Tooltip bereinigen
        if hasattr(widget, "tooltip"):
            try:
                if (widget.tooltip and 
                    hasattr(widget.tooltip, 'winfo_exists') and 
                    widget.tooltip.winfo_exists()):
                    widget.tooltip.destroy()
            except (tk.TclError, AttributeError):
                pass
            try:
                del widget.tooltip
            except (AttributeError, NameError):
                pass
        
        # Tooltip Timer bereinigen
        if hasattr(widget, "tooltip_after_id"):
            try:
                if widget.winfo_exists():
                    widget.after_cancel(widget.tooltip_after_id)
            except (tk.TclError, AttributeError):
                pass
            finally:
                try:
                    del widget.tooltip_after_id
                except (AttributeError, NameError):
                    pass
        
        # Rekursiv Children bereinigen
        try:
            if widget.winfo_exists():
                for child in widget.winfo_children():
                    cleanup_widget_tooltips(child)
        except (tk.TclError, AttributeError):
            pass
            
    except Exception as e:
        # Stille Ignorierung von Cleanup-Fehlern
        pass

def save_settings():
    config['Settings'] = {
        'use_database': str(use_db_var.get()),
        'use_title_search': str(title_search_var.get()),
        'use_genre': str(genre_var.get()),
        'use_actors': str(actors_var.get()),
        'use_comment': str(comment_var.get()),
        'use_album_search': str(album_search_var.get()),
        'use_interpret_search': str(interpret_search_var.get()),
        'debug_mode': 'False'
    }
    with open('MediaIndexer.cfg', 'w') as configfile:
        config.write(configfile)
    print("Einstellungen gespeichert")

def load_settings():
    if 'Settings' in config:
        use_db_var.set(config.getboolean('Settings', 'use_database', fallback=False))
        title_search_var.set(config.getboolean('Settings', 'use_title_search', fallback=False))
        genre_var.set(config.getboolean('Settings', 'use_genre', fallback=False))
        actors_var.set(config.getboolean('Settings', 'use_actors', fallback=False))
        comment_var.set(config.getboolean('Settings', 'use_comment', fallback=False))
        album_search_var.set(config.getboolean('Settings', 'use_album_search', fallback=False))
        interpret_search_var.set(config.getboolean('Settings', 'use_interpret_search', fallback=False))

# GUI Setup
root.title("Media Indexer and Player")
root.bind('<Configure>', on_root_configure)

frame = tk.Frame(root, pady=10)
frame.pack(fill='x')

frame.columnconfigure(0, weight=1)
frame.columnconfigure(1, weight=1)
frame.columnconfigure(2, weight=1)
frame.columnconfigure(3, weight=1)

open_button = tk.Button(frame, text="Open folder", command=open_folder)
open_button.grid(row=0, column=0, padx=5, pady=5)

search_entry = tk.Entry(frame)
search_entry.grid(row=0, column=1, padx=5, pady=5, sticky='ew')
search_entry.bind('<Key>', on_keypress)

search_button = tk.Button(frame, text="Search", command=perform_search)
search_button.grid(row=0, column=2, padx=5, pady=5)

settings_button = tk.Button(frame, text="Benutzer Einstellungen", command=open_settings)
settings_button.grid(row=0, column=3, padx=5, pady=5)

paned_window = ttk.Panedwindow(root, orient=tk.VERTICAL)
paned_window.pack(expand=True, fill='both')

s = ttk.Style()
s.configure("TPanedwindow", background='grey', sashthickness=5)

folder_outer_frame = tk.Frame(paned_window)
paned_window.add(folder_outer_frame, weight=1)

folder_canvas = tk.Canvas(folder_outer_frame)
folder_canvas.pack(side='left', expand=True, fill='both')

folder_scrollbar = tk.Scrollbar(folder_outer_frame, orient='vertical', command=folder_canvas.yview)
folder_scrollbar.pack(side='right', fill='y')
folder_canvas.configure(yscrollcommand=folder_scrollbar.set)

folder_frame = tk.Frame(folder_canvas)
folder_canvas.create_window((0, 0), window=folder_frame, anchor='nw')

def update_folder_scrollregion(event):
    folder_canvas.configure(scrollregion=folder_canvas.bbox('all'))

folder_frame.bind("<Configure>", update_folder_scrollregion)

media_outer_frame = tk.Frame(paned_window)
paned_window.add(media_outer_frame, weight=1)

media_canvas = tk.Canvas(media_outer_frame)
media_canvas.pack(side='left', expand=True, fill='both')

media_scrollbar = tk.Scrollbar(media_outer_frame, orient='vertical', command=media_canvas.yview)
media_scrollbar.pack(side='right', fill='y')
media_canvas.configure(yscrollcommand=media_scrollbar.set)

media_frame = tk.Frame(media_canvas)
media_canvas.create_window((0, 0), window=media_frame, anchor='nw')

def update_media_scrollregion(event):
    media_canvas.configure(scrollregion=media_canvas.bbox('all'))

media_frame.bind("<Configure>", update_media_scrollregion)

# Folder Canvas Bindings (ERSETZE die bestehenden Zeilen ~1730)
folder_canvas.bind("<Enter>", lambda event: on_canvas_enter(event, folder_canvas))
folder_canvas.bind("<Leave>", on_canvas_leave)  # KORRIGIERT: Nutze neuen Handler
folder_canvas.bind('<Configure>', lambda event: on_canvas_configure_debounced(event, 'folder'))

# Media Canvas Bindings (ERSETZE die bestehenden Zeilen ~1735)
media_canvas.bind("<Enter>", lambda event: on_canvas_enter(event, media_canvas))
media_canvas.bind("<Leave>", on_canvas_leave)  # KORRIGIERT: Nutze neuen Handler
media_canvas.bind('<Configure>', lambda event: on_canvas_configure_debounced(event, 'media'))

load_last_directory()
load_settings()

def cleanup_image_references():
    """Bereinigt alle PIL Image Referenzen"""
    try:
        import gc
        # Collect garbage
        gc.collect()
        
        # Manuell PIL Images aufräumen
        for obj in gc.get_objects():
            try:
                if isinstance(obj, Image.Image):
                    obj.close()
            except:
                pass
                
    except Exception as e:
        print(f"Image cleanup error: {e}")

def periodic_cleanup():
    """Regelmäßige Bereinigung alle 5 Minuten"""
    try:
        if root and root.winfo_exists():
            # Cleanup alte Tooltips
            cleanup_all_tooltips()
            
            # Cleanup Image-Referenzen
            cleanup_image_references()
            
            # Clear Pfad-Cache
            clear_path_classification_cache()
            
            # Nächsten Cleanup planen
            root.after(300000, periodic_cleanup)  # 5 Minuten
    except:
        pass

if __name__ == '__main__':
    try:
        # Startup-Optimierungen
        root.withdraw()  # Fenster erst unsichtbar machen
        
        print("Initialisiere Media Indexer...")
        
        # Initialisiere zuerst alle Komponenten
        if not os.path.exists(bin_dir):
            os.makedirs(bin_dir)
        
        # FFmpeg-Check
        ffmpeg_available = check_ffmpeg_and_ffprobe()
        
        # Theme setzen
        try:
            style = ThemedStyle(root)
            style.set_theme('arc')
        except:
            pass
        
        # Window-Protokolle setzen
        root.protocol("WM_DELETE_WINDOW", on_closing)
        
        # Initialisiere Config
        load_last_directory()
        load_settings()
        
        # Fenster sichtbar machen
        root.deiconify()
        
        # UI nach kurzer Verzögerung aktualisieren
        root.after(500, update_display)
        
        # Regelmäßigen Cleanup starten
        root.after(60000, periodic_cleanup)  # Starte nach 1 Minute
        
        print("Starte GUI-Hauptschleife...")
        root.mainloop()
        
    except KeyboardInterrupt:
        print("Strg+C erkannt - beende Anwendung...")
        on_closing()
    except Exception as e:
        print(f"Kritischer Startup-Fehler: {e}")
        import traceback
        traceback.print_exc()
        try:
            messagebox.showerror("Startup Fehler", 
                               f"Kritischer Fehler beim Start:\n{e}\n\nBitte prüfen Sie die Konsole für Details.")
        except:
            pass
        sys.exit(1)

#   Keine Admin-Rechte nötig!
#   Keine UAC-Prompts!
#   Keine Neustarts!
#   ❌ Keine Internet-Verbindungen
#   ❌ Keine Telemetrie
#   ❌ Keine Uploads
#   ❌ Keine Analytics zu Drittanbietern
#   ✅ Alles lokal in einem Ordner
#   ✅ Config ist Klartext
#   ✅ Datenbank ist SQLite
#   ⚡ Performance → Instant-Suche bei 5000+ Medien
#   🎯 Präzise → Exakt für Nutzung, Finden + Abspielen
#   🎒 Portabel → Keine Installation, keine Spuren
#   🛡️ Privat → Alles lokal, keine Cloud
#   🔧 Eigenbau → Perfekt auf grosse Sammlungen zugeschnitten
#   ✅ Keine Over-Engineering → Nur was nötig ist
#   ✅ Performance-first → Instant-Suche ist Priorität
#   ✅ Portabilität → Wichtiger als bunte Features
#   ✅ Praktisch → Finden + Abspielen, nicht nur Spielerei
