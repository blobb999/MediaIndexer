import os
import sys
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
import concurrent.futures
import sqlite3

# Extern
from PIL import Image, ImageTk
from mutagen.mp3 import MP3
from mutagen.id3 import ID3, APIC
from screeninfo import get_monitors
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

class Tooltip(tk.Toplevel):
    def __init__(self, widget, metadata, image=None, image_size=(300, 450), font_size=12):
        super().__init__(widget)
        # Direkt anzeigen vermeiden – wir zerstören dieses Fenster beim Verlassen
        self.overrideredirect(True)
        self.configure(background='lightyellow')
        self.widget = widget
        self.metadata = metadata
        self.image = image
        self.image_size = image_size

        # Schriftarten festlegen
        default_font = tkFont.Font(size=font_size)
        bold_font = tkFont.Font(size=font_size, weight="bold")

        # Container-Frame erstellen
        container = tk.Frame(self, bg='lightyellow', padx=10, pady=10, relief='solid', bd=1)
        container.pack()

        # Maximale Breite des Tooltips
        self.max_tooltip_width = 400

        # Bild anzeigen, falls verfügbar
        if self.image:
            try:
                image = self.image.resize(self.image_size, Image.LANCZOS)
                photo = ImageTk.PhotoImage(image)
                image_label = tk.Label(container, image=photo, bg='lightyellow')
                image_label.image = photo  # Referenz behalten
                image_label.pack(pady=(0, 10))
            except Exception as e:
                print(f"Fehler beim Laden des Bildes: {e}")

        # Metadaten parsen und anzeigen
        metadata_dict = self.parse_metadata(self.metadata)

        # Schauspielerliste bereinigen
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

        # Tooltip anpassen, wenn er über die Bildschirmränder hinausgeht
        if preferred_x + tooltip_width > screen_width:
            preferred_x = x - tooltip_width - 20
        if preferred_y + tooltip_height > screen_height:
            preferred_y = y - tooltip_height - 20

        # Sicherstellen, dass der Tooltip nicht außerhalb des Bildschirms erscheint
        preferred_x = max(0, min(preferred_x, screen_width - tooltip_width))
        preferred_y = max(0, min(preferred_y, screen_height - tooltip_height))

        self.geometry(f"+{preferred_x}+{preferred_y}")
        self.deiconify()
        self.lift()

    def hide(self):
        # Anstatt nur zu verstecken, zerstören wir den Tooltip, um Ressourcen freizugeben.
        self.destroy()

# Hauptfenster und Konfiguration
root = tk.Tk()
root.title("Media Indexer and Player")

style = ThemedStyle(root)
style.set_theme('arc')

folder_path = ''
config = configparser.ConfigParser()
previous_window_size = None

bin_dir = os.path.join(os.getcwd(), 'bin')
ffmpeg_path = os.path.join(bin_dir, 'ffmpeg.exe')
ffprobe_path = os.path.join(bin_dir, 'ffprobe.exe')

search_active = False
current_search_results = []

# Initialisieren der Variablen (neu)
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
                # Download ffmpeg
                urllib.request.urlretrieve(url, download_path)

                # Extract the zip file
                with zipfile.ZipFile(download_path, 'r') as zip_ref:
                    zip_ref.extractall(install_path)

                # Locate the ffmpeg and ffprobe binaries
                ffmpeg_bin_path = None
                for root_dir, dirs, files in os.walk(install_path):
                    if 'ffmpeg.exe' in files and 'ffprobe.exe' in files:
                        ffmpeg_bin_path = root_dir
                        break

                if ffmpeg_bin_path:
                    # Move the binaries to the bin directory
                    shutil.move(os.path.join(ffmpeg_bin_path, 'ffmpeg.exe'), os.path.join(bin_dir, 'ffmpeg.exe'))
                    shutil.move(os.path.join(ffmpeg_bin_path, 'ffprobe.exe'), os.path.join(bin_dir, 'ffprobe.exe'))

                # Clean up
                os.remove(download_path)
                shutil.rmtree(install_path)

                # Restart the program
                python_exe = sys.executable
                os.execl(python_exe, python_exe, *sys.argv)

            except Exception as e:
                messagebox.showerror("Error Downloading FFmpeg", f"An error occurred while downloading and installing FFmpeg:\n{e}")

        error_window = tk.Toplevel(root)
        error_window.title("FFmpeg Not Found")
        error_window.geometry("400x150")
        error_window.transient(root)
        error_window.grab_set()

        message = tk.Label(error_window, text="FFmpeg and FFprobe are not found or failed to initialize.")
        message.pack(pady=10)

        link = tk.Label(error_window, text="https://ffmpeg.org/download.html", fg="blue", cursor="hand2")
        link.pack()
        link.bind("<Button-1>", open_ffmpeg_download)

        install_button = tk.Button(error_window, text="Download and Install", command=download_and_install_ffmpeg)
        install_button.pack(pady=10)

        error_window.protocol("WM_DELETE_WINDOW", root.destroy)

        error_window.attributes('-topmost', True)
        error_window.update()
        error_window.attributes('-topmost', False)

    try:
        ffmpeg_path_local = os.path.join(bin_dir, "ffmpeg.exe")
        ffprobe_path_local = os.path.join(bin_dir, "ffprobe.exe")

        if not os.path.exists(ffmpeg_path_local) or not os.path.exists(ffprobe_path_local):
            show_ffmpeg_error()
            return False

        ffmpeg_result = subprocess.run([ffmpeg_path_local, "-version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        ffprobe_result = subprocess.run([ffprobe_path_local, "-version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

        if ffmpeg_result.returncode != 0 or ffprobe_result.returncode != 0:
            show_ffmpeg_error()
            return False

    except FileNotFoundError:
        show_ffmpeg_error()
        return False

    return True

def extract_cover_art(file_path, max_size=(300, 450)):
    """Cover-Art Extraktion mit Pfad-Normalisierung"""
    # Pfad normalisieren
    normalized_path = os.path.normpath(file_path)
    
    # Externe Bilddatei prüfen
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
            # ffprobe mit normalisiertem Pfad
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

def on_enter(event, path, widget):
    x_root, y_root = event.x_root, event.y_root
    global scroll_active
    if scroll_active:
        return
    def show_tooltip_after_delay():
        try:
            # Weniger restriktive Überprüfung - nur prüfen ob Widget noch existiert
            if widget.winfo_exists():
                widget_at_pos = widget.winfo_containing(x_root, y_root)
                # Tooltip zeigen wenn Mouse noch über dem ursprünglichen Widget oder einem Child ist
                if widget_at_pos == widget or (widget_at_pos and str(widget_at_pos).startswith(str(widget))):
                    show_tooltip(x_root, y_root, path, widget)
        except tk.TclError:
            # Widget wurde bereits zerstört
            pass
    
    # Cancel existing tooltip timer
    if hasattr(widget, "tooltip_after_id"):
        widget.after_cancel(widget.tooltip_after_id)
    
    widget.tooltip_after_id = widget.after(500, show_tooltip_after_delay)

def on_leave(event, widget):
    if hasattr(widget, "tooltip_after_id"):
        widget.after_cancel(widget.tooltip_after_id)
        del widget.tooltip_after_id

    if hasattr(widget, "tooltip"):
        # Statt den Tooltip nur zu verstecken, wird er zerstört, um Ressourcen freizugeben.
        widget.tooltip.destroy()
        del widget.tooltip

def on_motion(event, path, widget):
    if hasattr(widget, "tooltip"):
        x_root, y_root = event.x_root, event.y_root
        widget.tooltip.show(x_root, y_root)

def show_tooltip(x_root, y_root, path, widget):
    if hasattr(widget, "tooltip"):
        try:
            if widget.tooltip.winfo_exists():
                widget.tooltip.destroy()
        except:
            pass
    
    image = extract_cover_art(path)
    metadata = get_metadata_info(path)
    tooltip = Tooltip(widget, metadata, image=image)
    widget.tooltip = tooltip
    tooltip.show(x_root, y_root)

def bind_tooltip(widget, path):
    widget.bind("<Enter>", lambda event: on_enter(event, path, widget))
    widget.bind("<Leave>", lambda event: on_leave(event, widget))
    widget.bind("<Motion>", lambda event: on_motion(event, path, widget))

def ffprobe_file(file_path):
    """ffprobe mit besserer Pfad-Behandlung"""
    try:
        # Pfad normalisieren
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
    def fetch_metadata():
        try:
            audio = MP3(file_path, ID3=ID3)
            tags = audio.tags

            if tags is None:
                print(f"No ID3 tags found in {file_path}")
                return '', '', '', '', '', ''

            album = tags.get("TALB").text[0] if tags.get("TALB") else ''
            track_number = tags.get("TRCK").text[0] if tags.get("TRCK") else ''
            year = str(tags.get("TDRC").text[0]) if tags.get("TDRC") else ''
            genre = tags.get("TCON").text[0] if tags.get("TCON") else ''
            contributors = tags.get("TPE1").text[0] if tags.get("TPE1") else ''
            length = f"{round(audio.info.length / 60, 2)} min"
            return album, track_number, year, genre, contributors, length
        except Exception as e:
            print(f"Error extracting MP3 metadata from {file_path}: {e}")
            return '', '', '', '', '', ''

    with concurrent.futures.ThreadPoolExecutor() as executor:
        future = executor.submit(fetch_metadata)
        try:
            return future.result(timeout=timeout)
        except concurrent.futures.TimeoutError:
            print(f"Datei '{file_path}' überschritt den Zeitrahmen und wird übersprungen.")
            return '', '', '', '', '', ''

def update_display():
    # Hier wird nur die Anzeige aktualisiert, wenn bereits ein Verzeichnis vorhanden ist.
    if folder_path:  # Überprüfen, ob ein Verzeichnis geladen ist
        display_folders(folder_path)  # Zeige Ordner an
        display_files(folder_path)    # Zeige Dateien im Ordner an

def create_default_config(config_file_path):
    default_config = configparser.ConfigParser()
    default_config['LastDirectory'] = {'path': ''}
    default_config['WindowSize'] = {'size': '800x600'}
    default_config['PanedWindow'] = {'position': '0'}

    with open(config_file_path, 'w') as configfile:
        default_config.write(configfile)

def save_panedwindow_position():
    try:
        position = paned_window.sashpos(0)
    except Exception as e:
        print(f"Error getting sash position: {e}")
        position = 0

    config['PanedWindow'] = {'position': position}
    with open('MediaIndexer.cfg', 'w') as configfile:
        config.write(configfile)

def load_panedwindow_position():
    try:
        position_str = config['PanedWindow']['position']
        position = int(re.sub('[^0-9]', '', position_str))  # extract only numeric characters
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
        search_active = False  # Suche ist nicht mehr aktiv
        save_last_directory(folder_path)
        update_display()

def natural_sort_key(s):
    return [int(text) if text.isdigit() else text.lower()
            for text in re.split('(\d+)', s)]

def search_files_recursive(path, media_extensions, playlist_extensions, search_results):
    # Using an iterative approach to avoid stack overflow
    stack = [path]
    while stack:
        current_path = stack.pop()
        try:
            entries = os.listdir(current_path)
        except PermissionError:
            continue  # Handle directories where access is denied
        
        for entry in entries:
            entry_path = os.path.join(current_path, entry)
            if os.path.isdir(entry_path):
                stack.append(entry_path)
            elif entry.lower().endswith(media_extensions) or entry.lower().endswith(playlist_extensions):
                search_results.append(entry_path)

def perform_search():
    search_term = search_entry.get()

    if folder_path and search_term:
        media_extensions = ('.mp3', '.mp4', '.mkv', '.avi', '.flv', '.mov', '.wmv')
        search_results = []

        if use_db_var.get():
            conn = sqlite3.connect('media_index.db')
            cursor = conn.cursor()

            # Die SQL-Abfrage beginnt mit einer Bedingung, die den Dateipfad einschränkt.
            # Anschließend werden – je nach aktivierten Checkboxen – die entsprechenden Felder durchsucht.
            query = "SELECT filepath FROM media_files WHERE filepath LIKE ? AND (1=0"
            params = [f"{folder_path}%"]

            if title_search_var.get():
                query += " OR filename LIKE ? OR container LIKE ?"
                params.append(f"%{search_term}%")
                params.append(f"%{search_term}%")

            if genre_var.get():
                query += " OR genre LIKE ?"
                params.append(f"%{search_term}%")

            if actors_var.get():
                query += " OR actors LIKE ?"
                params.append(f"%{search_term}%")

            if comment_var.get():
                query += " OR comment LIKE ?"
                params.append(f"%{search_term}%")

            if album_search_var.get():
                query += " OR album LIKE ?"
                params.append(f"%{search_term}%")

            if interpret_search_var.get():
                query += " OR contributors LIKE ?"
                params.append(f"%{search_term}%")

            query += ")"
            cursor.execute(query, params)
            search_results = [row[0] for row in cursor.fetchall()]
            conn.close()
        else:
            search_files_recursive(folder_path, media_extensions, (), search_results)
            search_results = [result for result in search_results if search_term.lower() in os.path.basename(result).lower()]

        display_folders(folder_path, search_results)
        display_files(search_results)

        global search_active, current_search_results
        search_active = True
        current_search_results = search_results.copy()

        
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

    # Canvas-Breite verwenden statt root-Breite
    canvas_width = folder_canvas.winfo_width()
    if canvas_width <= 1:  # Fallback wenn Canvas noch nicht initialisiert
        canvas_width = root.winfo_width()
    
    button_width = 170
    num_columns = calculate_columns(canvas_width, button_width)

    # Grid-Konfiguration zurücksetzen und neu konfigurieren
    for i in range(20):  # Entferne alte Spalten-Konfigurationen
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
    # Canvas Scroll-Region aktualisieren
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

    # Canvas-Breite verwenden
    canvas_width = media_canvas.winfo_width()
    if canvas_width <= 1:  # Fallback
        canvas_width = root.winfo_width()
    
    button_width = 170
    num_columns = calculate_columns(canvas_width - media_scrollbar.winfo_width(), button_width)

    # Grid-Konfiguration zurücksetzen
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

    # Canvas Scroll-Region aktualisieren
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
    """Extrahiert Videolänge mit besserer Fehlerbehandlung"""
    try:
        # Pfad normalisieren
        normalized_path = os.path.normpath(file_path)
        
        result = subprocess.run(
            [ffprobe_path, '-v', 'error', '-show_entries', 'format=duration', 
             '-of', 'default=noprint_wrappers=1:nokey=1', normalized_path],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            creationflags=subprocess.CREATE_NO_WINDOW
        )
        
        duration_output = result.stdout.strip()
        
        # Prüfe ob Output leer oder ungültig ist
        if not duration_output or duration_output == 'N/A':
            print(f"Keine Dauer verfügbar für: {file_path}")
            return "Unbekannt"
            
        try:
            duration = float(duration_output)
            return f"{int(duration // 60)} min"
        except ValueError:
            print(f"Ungültige Dauer '{duration_output}' für: {file_path}")
            return "Unbekannt"
            
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        print(f"Fehler beim Extrahieren der Videolänge von {file_path}: {e}")
        return "Unbekannt"

def safe_startfile(file_path):
    """Sichere Datei-Öffnung mit Pfad-Normalisierung"""
    try:
        # Pfad normalisieren und Existenz prüfen
        normalized_path = os.path.normpath(file_path)
        
        if not os.path.exists(normalized_path):
            messagebox.showerror("Datei nicht gefunden", 
                               f"Die Datei konnte nicht gefunden werden:\n{normalized_path}")
            return
            
        os.startfile(normalized_path)
    except Exception as e:
        messagebox.showerror("Fehler beim Öffnen", 
                           f"Fehler beim Öffnen der Datei:\n{file_path}\n\nFehler: {e}")

           
def get_metadata_info(file_path):
    try:
        if file_path.lower().endswith('.mp3'):
            album, track_number, year, genre, contributors, length = get_mp3_metadata_with_timeout(file_path)
            metadata = f"Titel: {track_number}\nInterpret: {contributors}\nAlbum: {album}\nJahr: {year}"
        else:
            genre, actors, comment, year = get_media_metadata_hidden(file_path)
            file_name = os.path.basename(file_path)
            length = get_media_duration(file_path) or "Unbekannt"

            indent = ' ' * 13
            comment_wrapped = textwrap.fill(comment, width=100, subsequent_indent=indent)
            actors_wrapped = textwrap.fill(actors, width=100, subsequent_indent=indent)
            metadata = f"Filmtitel: {file_name}\nJahr: {year}\nSchauspieler: {actors_wrapped}\nFilmlänge: {length}\n\nInhalt: {comment_wrapped}"
        return metadata
    except Exception as e:
        print(f"Fehler beim Abrufen der Metadaten für {file_path}: {e}")
        return "Keine Metadaten verfügbar"

def on_root_configure(event):
    global resize_after_id, previous_window_size
    
    # Nur auf root-Widget Events reagieren, nicht auf Child-Widgets
    if event.widget != root:
        return
    
    if resize_after_id:
        root.after_cancel(resize_after_id)
    
    current_size = (root.winfo_width(), root.winfo_height())
    if previous_window_size != current_size:
        previous_window_size = current_size
        # Längere Verzögerung für stabilere Updates
        resize_after_id = root.after(200, refresh_ui)

def bind_scroll_to_canvas(canvas):
    global current_scroll_handler, scroll_active, last_scroll_time
    if current_scroll_handler:
        root.unbind_all("<MouseWheel>")
    
    def scroll_handler(event):
        global scroll_active, last_scroll_time
        import time
        
        scroll_active = True
        last_scroll_time = time.time()
        canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        
        # Reset scroll_active nach 500ms
        def reset_scroll():
            global scroll_active
            scroll_active = False
        root.after(500, reset_scroll)
    
    current_scroll_handler = root.bind_all("<MouseWheel>", scroll_handler)

def on_canvas_configure_debounced(event, canvas_type):
    """Debounced Canvas-Configure Handler"""
    if not hasattr(root, 'canvas_resize_after_id'):
        root.canvas_resize_after_id = {}
    
    # Cancel previous resize for this canvas
    if canvas_type in root.canvas_resize_after_id:
        root.after_cancel(root.canvas_resize_after_id[canvas_type])
    
    # Only refresh after 300ms of no canvas changes
    def delayed_refresh():
        if folder_path:
            refresh_ui()
        if canvas_type in root.canvas_resize_after_id:
            del root.canvas_resize_after_id[canvas_type]
    
    root.canvas_resize_after_id[canvas_type] = root.after(300, delayed_refresh)

def refresh_ui():
    """UI mit korrekter Größenberechnung aktualisieren"""
    if folder_path:
        # Canvas-Größen explizit aktualisieren
        folder_canvas.update_idletasks()
        media_canvas.update_idletasks()
        
        if search_active:
            display_folders(folder_path, current_search_results)
            display_files(current_search_results)
        else:
            display_folders(folder_path)
            display_files(folder_path)

def create_or_reset_db():
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
            filepath TEXT,
            container TEXT,
            album TEXT,
            track_number TEXT,
            year TEXT,
            genre TEXT,
            length TEXT,
            contributors TEXT,
            actors TEXT,
            comment TEXT
        )
    ''')
    conn.commit()
    conn.close()
    print("Datenbank neu erstellt.")

def train_db_with_progress():
    progress_window = tk.Toplevel(root)
    progress_window.title("Suche mit ffprobe")
    progress_window.geometry("400x150")

    progress_label = tk.Label(progress_window, text="Suche läuft...")
    progress_label.pack(pady=10)

    progress_bar = ttk.Progressbar(progress_window, orient='horizontal', mode='determinate', length=350)
    progress_bar.pack(pady=10)

    file_progress_label = tk.Label(progress_window, text="")
    file_progress_label.pack(pady=5)

    total_scanned = 0
    new_files_count = 0
    updated_files_count = 0

    def update_progress(current, total, filename):
        progress_bar['value'] = (current / total) * 100
        file_progress_label.config(text=f"({current}/{total}) - {filename}")
        root.update_idletasks()

    def run_ffprobe():
        nonlocal total_scanned, new_files_count, updated_files_count

        media_extensions = ('.mp3', '.mp4', '.mkv', '.avi', '.mov')
        media_files = []
        batch_size = 100

        total_files = sum([len(files) for r, d, files in os.walk(folder_path) if any(f.lower().endswith(media_extensions) for f in files)])
        current_file_count = 0

        conn = sqlite3.connect('media_index.db', timeout=30.0)
        cursor = conn.cursor()

        for root_dir, _, files in os.walk(folder_path):
            for file in files:
                if file.lower().endswith(media_extensions):
                    file_path = os.path.join(root_dir, file)
                    parent_folder = os.path.basename(os.path.dirname(file_path))
                    
                    cursor.execute("SELECT COUNT(*) FROM media_files WHERE filepath = ?", (file_path,))
                    if cursor.fetchone()[0] > 0:
                        updated_files_count += 1
                        continue

                    try:
                        if file.lower().endswith('.mp3'):
                            album, track_number, year, genre, contributors, length = get_mp3_metadata_with_timeout(file_path)
                            media_files.append((file, file_path, parent_folder, album, track_number, year, genre, length, contributors, '', ''))
                        else:
                            genre, actors, comment, year = get_media_metadata_hidden(file_path)
                            media_files.append((file, file_path, parent_folder, '', '', year or '', genre or '', '', '', actors or '', comment or ''))

                        current_file_count += 1
                        total_scanned += 1
                        new_files_count += 1
                        update_progress(current_file_count, total_files, file)

                        if len(media_files) >= batch_size:
                            cursor.executemany('''
                                INSERT INTO media_files (filename, filepath, container, album, track_number, year, genre, length, contributors, actors, comment)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            ''', media_files)
                            conn.commit()
                            media_files = []

                    except Exception as e:
                        print(f"Error processing file {file_path}: {e}")
                        continue

        if media_files:
            try:
                cursor.executemany('''
                    INSERT INTO media_files (filename, filepath, container, album, track_number, year, genre, length, contributors, actors, comment)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', media_files)
                conn.commit()
            except sqlite3.ProgrammingError as e:
                print(f"Error inserting data into database: {e}")

        conn.close()
        root.after(0, progress_window.destroy)

        winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
        play_tts_message()

        root.lift()
        root.focus_force()

        summary_message = (
            f"Scan abgeschlossen!\n\n"
            f"Gesamte Dateien gescannt: {total_scanned}\n"
            f"Neue Dateien hinzugefügt: {new_files_count}\n"
            f"Dateien mit geänderten Metadaten: {updated_files_count}"
        )
        messagebox.showinfo("Scan-Zusammenfassung", summary_message)

    threading.Thread(target=run_ffprobe, daemon=True).start()


def play_tts_message():
    try:
        engine = pyttsx3.init()
        engine.say("Database training is complete!")
        engine.runAndWait()
    except Exception as e:
        print(f"Text-to-Speech error: {e}")

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
    state = tk.NORMAL if use_db_var.get() else tk.DISABLED
    title_checkbox.config(state=state)
    genre_checkbox.config(state=state)
    actors_checkbox.config(state=state)
    comment_checkbox.config(state=state)
    album_checkbox.config(state=state)
    interpret_checkbox.config(state=state)

def open_settings():
    global settings_window, title_checkbox, genre_checkbox, actors_checkbox, comment_checkbox, album_checkbox, interpret_checkbox

    if settings_window and settings_window.winfo_exists():
        settings_window.lift()
        settings_window.focus_force()
        return

    settings_window = tk.Toplevel(root)
    settings_window.title("Benutzer Einstellungen")
    settings_window.geometry("400x500")

    tk.Button(settings_window, text="Erstelle / Reset SQL-Lite Datenbank", command=create_or_reset_db).pack(pady=10)
    tk.Button(settings_window, text="Trainiere Datenbank", command=train_db_with_progress).pack(pady=10)

    use_db_checkbox = tk.Checkbutton(settings_window, text="Benutze SQL-Datenbank bei der Suche", variable=use_db_var, command=toggle_search_options)
    use_db_checkbox.pack(pady=10)

    title_checkbox = tk.Checkbutton(settings_window, text="Titelsuche (Dateiname/Ordnername)", variable=title_search_var, state=tk.DISABLED)
    title_checkbox.pack(pady=5)

    genre_checkbox = tk.Checkbutton(settings_window, text="Metatag Genre der Datei", variable=genre_var, state=tk.DISABLED)
    genre_checkbox.pack(pady=5)

    actors_checkbox = tk.Checkbutton(settings_window, text="Metatag Schauspieler der Datei", variable=actors_var, state=tk.DISABLED)
    actors_checkbox.pack(pady=5)

    comment_checkbox = tk.Checkbutton(settings_window, text="Metatag 'comment' der Datei", variable=comment_var, state=tk.DISABLED)
    comment_checkbox.pack(pady=5)

    album_checkbox = tk.Checkbutton(settings_window, text="Metatag Album der Datei", variable=album_search_var, state=tk.DISABLED)
    album_checkbox.pack(pady=5)

    interpret_checkbox = tk.Checkbutton(settings_window, text="Metatag Interpret der Datei", variable=interpret_search_var, state=tk.DISABLED)
    interpret_checkbox.pack(pady=5)

    toggle_search_options()

    save_button = tk.Button(settings_window, text="Speichern", command=save_settings)
    save_button.pack(pady=10)

    close_button = tk.Button(settings_window, text="Schließen", command=lambda: on_close_settings(settings_window))
    close_button.pack(pady=10)

    load_settings()


def cleanup_widget_tooltips(widget):
    """Recursively clean up tooltips for widget and all children"""
    if hasattr(widget, "tooltip"):
        try:
            widget.tooltip.destroy()
        except:
            pass
        del widget.tooltip
    
    if hasattr(widget, "tooltip_after_id"):
        try:
            widget.after_cancel(widget.tooltip_after_id)
        except:
            pass
        del widget.tooltip_after_id
    
    # Recursively clean children
    try:
        for child in widget.winfo_children():
            cleanup_widget_tooltips(child)
    except:
        pass

def on_close_settings(window):
    global settings_window
    settings_window = None
    window.destroy()
    
def on_keypress(event):
    if event.keysym == 'Return':
        perform_search()

def on_closing():
    # Alle Tooltips zerstören
    for widget in root.winfo_children():
        cleanup_widget_tooltips(widget)
    
    # Event-Bindings entfernen
    root.unbind_all("<MouseWheel>")
    
    save_last_directory()
    root.destroy()

def save_settings():
    config['Settings'] = {
        'use_database': str(use_db_var.get()),
        'use_title_search': str(title_search_var.get()),
        'use_genre': str(genre_var.get()),
        'use_actors': str(actors_var.get()),
        'use_comment': str(comment_var.get()),
        'use_album_search': str(album_search_var.get()),
        'use_interpret_search': str(interpret_search_var.get())
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

folder_canvas.bind("<Enter>", lambda _: bind_scroll_to_canvas(folder_canvas))
folder_canvas.bind("<Leave>", lambda _: root.unbind_all("<MouseWheel>"))
folder_canvas.bind('<Configure>', lambda event: on_canvas_configure_debounced(event, 'folder'))

media_canvas.bind("<Enter>", lambda _: bind_scroll_to_canvas(media_canvas))
media_canvas.bind("<Leave>", lambda _: root.unbind_all("<MouseWheel>"))
media_canvas.bind('<Configure>', lambda event: on_canvas_configure_debounced(event, 'media'))

load_last_directory()
load_settings()

if __name__ == '__main__':
    if not check_ffmpeg_and_ffprobe():
        sys.exit("FFmpeg and FFprobe are required for the application to run.")

    style.configure("TSizegrip", relief='flat')

    root.sizegrip = ttk.Sizegrip(root, style="TSizegrip")
    root.sizegrip.pack(side='right', anchor='se')

    root.after(100, update_display)

    root.protocol("WM_DELETE_WINDOW", on_closing)
    root.mainloop()
