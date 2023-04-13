import os
import tkinter as tk
from tkinter import filedialog
import tkinter.font as tkFont
import configparser

folder_path = ''
config = configparser.ConfigParser()

def on_mousewheel(event):
    media_canvas.yview_scroll(int((event.delta / 120)), "units")

def on_root_configure(event):
    if hasattr(root, 'folder_path'):
        update_display()

def update_display():
    if folder_path:
        root.after(100, lambda: display_folders(folder_path))
        root.after(100, lambda: display_files(folder_path))

def update_window_size():
    root.update()
    window_width = root.winfo_width()
    window_height = root.winfo_height()
    return f"{window_width}x{window_height}"

def save_last_directory(path=None):
    if path:
        config['LastDirectory'] = {'path': path}
    window_size = f"{root.winfo_width()}x{root.winfo_height()}"
    config['WindowSize'] = {'size': window_size}
    with open('MediaIndexer.cfg', 'w') as configfile:
        config.write(configfile)

def load_last_directory():
    global folder_path
    config.read('MediaIndexer.cfg')
    if 'LastDirectory' in config and 'path' in config['LastDirectory']:
        folder_path = config['LastDirectory']['path']
        if os.path.isdir(folder_path):
            update_display()
    if 'WindowSize' in config and 'size' in config['WindowSize']:
        window_size = config['WindowSize']['size']
        root.geometry(window_size)
        update_display()

def open_folder():
    global folder_path
    folder_path = filedialog.askdirectory()
    if folder_path:
        save_last_directory(folder_path)
        update_display()

def calculate_columns(window_width, button_width):
    padding = 10
    return max(1, (window_width - padding) // (button_width + padding))

def search_files_recursive(path, media_extensions, playlist_extensions, search_results):
    for entry in os.listdir(path):
        entry_path = os.path.join(path, entry)
        if os.path.isdir(entry_path):
            search_files_recursive(entry_path, media_extensions, playlist_extensions, search_results)
        elif entry.lower().endswith(media_extensions) or entry.lower().endswith(playlist_extensions):
            search_results.append(entry_path)

def perform_search():
    search_term = search_entry.get()
    if folder_path and search_term:
        media_extensions = ('.mp3', '.mp4', '.mkv', '.avi', '.flv', '.mov', '.wmv')
        playlist_extensions = ('.xspf',)
        search_results = []
        search_files_recursive(folder_path, media_extensions, playlist_extensions, search_results)
        search_results = [result for result in search_results if search_term.lower() in os.path.basename(result).lower()]
        display_folders(folder_path, search_results)  # Hinzufügen von search_results als Argument
        display_files(search_results)

def display_folders(folder_path, search_results=None):
    for widget in folder_frame.winfo_children():
        widget.destroy()

    window_width = root.winfo_width()

    button_width = 160

    num_columns = calculate_columns(window_width, button_width)

    row, column = 0, 0

    if search_results is None:
        folders = [entry for entry in os.listdir(folder_path) if os.path.isdir(os.path.join(folder_path, entry))]
    else:
        folders = sorted({os.path.dirname(result) for result in search_results})

    # Folder Up Button
    parent_folder = os.path.dirname(folder_path)
    if parent_folder and search_results is None:
        folder_up_button = tk.Button(folder_frame, text="Folder Up", bg='green', fg='white', command=lambda: (display_folders(parent_folder), display_files(parent_folder)))
        folder_up_button.grid(row=row, column=column, padx=5, pady=5)

        default_font = folder_up_button.cget("font")
        new_font = tkFont.Font(font=default_font)
        new_font.config(size=int(new_font['size'] * 1.3), weight='bold')
        folder_up_button.config(font=new_font)

        column += 1
        if column >= num_columns:
            row += 1
            column = 0

    for folder in folders:
        folder_button = tk.Button(folder_frame, text=folder, command=lambda path=os.path.join(folder_path, folder): (display_folders(path), display_files(path)))
        folder_button.grid(row=row, column=column, padx=5, pady=5)

        default_font = folder_button.cget("font")
        new_font = tkFont.Font(font=default_font)
        new_font.config(size=int(new_font['size'] * 1.3), weight='bold')
        folder_button.config(font=new_font)

        column += 1
        if column >= num_columns:
            row += 1
            column = 0
            if row >= 3:
                break


def display_files(files_or_folder_path):
    media_extensions = ('.mp3', '.mp4', '.mkv', '.avi', '.flv', '.mov', '.wmv')
    playlist_extensions = ('.xspf',)

    for widget in media_frame.winfo_children():
        widget.destroy()

    window_width = root.winfo_width()

    button_width = 160

    num_columns = calculate_columns(window_width, button_width)

    row, column = 0, 0
    
    if isinstance(files_or_folder_path, str): 
        folder_path = files_or_folder_path
        files = os.listdir(folder_path)
    else:  
        files = files_or_folder_path

    for file in files:
        if file.lower().endswith(media_extensions) or file.lower().endswith(playlist_extensions):
            if isinstance(files_or_folder_path, str):
                file_path = os.path.join(folder_path, file)
            else:
                file_path = file
                file = os.path.basename(file)
            file_name, file_ext = os.path.splitext(file)

            media_box = tk.Button(media_frame, text=file_name, width=20, height=2, wraplength=150, command=lambda path=file_path: os.startfile(path))
            media_box.grid(row=row, column=column, padx=10, pady=5)

            default_font = media_box.cget("font")
            new_font = tkFont.Font(font=default_font)
            new_font.config(size=int(new_font['size'] * 1.2), weight='bold')
            media_box.config(font=new_font)

            if file_ext.lower() in playlist_extensions:
                media_box.config(bg='yellow')

            column += 1
            if column >= num_columns:
                row += 1
                column = 0
                if row >= 100:
                    break

    media_frame.config(height=(row + 1) * (media_box.winfo_reqheight() + 10))
    media_canvas.config(scrollregion=media_canvas.bbox('all'))

def on_resize(event):
    if not root:  
        return

    media_canvas.configure(scrollregion=media_canvas.bbox('all'))
    if hasattr(root, 'folder_path'):
        update_display()
        save_last_directory()

root = tk.Tk()
root.title("Media Indexer and Player")
root.bind('<Configure>', on_root_configure)

frame = tk.Frame(root, pady=10)
frame.pack(fill='x')

open_button = tk.Button(frame, text="Open folder", command=open_folder)
open_button.grid(row=0, column=0, padx=5, pady=5)

search_entry = tk.Entry(frame)
search_entry.grid(row=0, column=1, padx=5, pady=5)

search_button = tk.Button(frame, text="Search", command=perform_search)
search_button.grid(row=0, column=2, padx=5, pady=5)

separator = tk.Frame(root, height=2, bg="grey")
separator.pack(fill="x", pady=10)

folder_frame = tk.Frame(root)
folder_frame.pack(pady=5)

separator2 = tk.Frame(root, height=2, bg="grey")
separator2.pack(fill="x", pady=10)

media_canvas = tk.Canvas(root)
media_canvas.pack(side='left', expand=True, fill='both')

media_scrollbar = tk.Scrollbar(root, orient='vertical', command=media_canvas.yview)
media_scrollbar.pack(side='right', fill='y')
media_canvas.configure(yscrollcommand=media_scrollbar.set)

media_frame = tk.Frame(media_canvas)
media_canvas.create_window((0, 0), window=media_frame, anchor='nw')
media_canvas.configure(scrollregion=media_canvas.bbox('all'))

media_canvas.bind_all("<MouseWheel>", on_mousewheel)

load_last_directory()

root.after(100, load_last_directory)

root.mainloop()
