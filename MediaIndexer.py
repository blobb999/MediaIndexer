import os
import tkinter as tk
from tkinter import filedialog
import tkinter.font as tkFont
import configparser
import re
import tkinter.ttk as ttk
from ttkthemes import ThemedStyle

root = tk.Tk()
root.title("Media Indexer and Player")

style = ThemedStyle(root)
style.set_theme('arc')


folder_path = ''
config = configparser.ConfigParser()
previous_window_size = None
initial_load = True

def on_mousewheel(event):
    media_canvas.yview_scroll(int((event.delta / 120)), "units")

def update_display():
    if folder_path:
        root.after(100, lambda: display_folders(folder_path))
        root.after(100, lambda: display_files(folder_path))


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

def on_sash_move(*args):
    position = paned_window.sashpos(0)
    save_panedwindow_position(position)

def print_config_file_contents():
    with open('MediaIndexer.cfg', 'r') as configfile:
        print(configfile.read())

def set_paned_position():
    paned_position = load_panedwindow_position()
    paned_window.sashpos(0, paned_position)

def save_last_directory(path=None):
    if path:
        config['LastDirectory'] = {'path': path}
    window_size = f"{root.winfo_width()}x{root.winfo_height()}"
    config['WindowSize'] = {'size': window_size}
    save_panedwindow_position()
    with open('MediaIndexer.cfg', 'w') as configfile:
        config.write(configfile)

def load_last_directory():
    initial_load = False
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

            # Load paned window position only if window size is larger than 1x1
            window_width, window_height = [int(x) for x in window_size.split('x')]
            if window_width > 1 and window_height > 1:
                if 'PanedWindow' in config and 'position' in config['PanedWindow']:
                    paned_position = load_panedwindow_position()
                    root.after(1000, lambda: paned_window.sashpos(0, paned_position))
                else:
                    print("PanedWindow section not found in config")
    except Exception as e:
        print(f"Error loading last directory: {e}")

def open_folder():
    global folder_path
    folder_path = filedialog.askdirectory()
    if folder_path:
        save_last_directory(folder_path)
        update_display()

def calculate_columns(window_width, button_width):
    padding = 10
    scrollbar_width = 20  # Add an approximate scrollbar width
    return max(1, (window_width - padding - scrollbar_width) // (button_width + padding))

def natural_sort_key(s):
    return [int(text) if text.isdigit() else text.lower()
            for text in re.split('(\d+)', s)]

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
        display_folders(folder_path, search_results)
        display_files(search_results)

def display_folders(folder_path, search_results=None):
    for widget in folder_frame.winfo_children():
        widget.destroy()

    window_width = root.winfo_width()

    button_width = 170

    num_columns = calculate_columns(window_width, button_width)

    row, column = 0, 0

    if search_results is None:
        folders = [entry for entry in os.listdir(folder_path) if os.path.isdir(os.path.join(folder_path, entry))]
    else:
        folders = sorted({os.path.dirname(result) for result in search_results})

    # Folder Up Button
    parent_folder = os.path.dirname(folder_path)
    if parent_folder and search_results is None:
        folder_up_button = tk.Button(folder_frame, text="Folder Up", bg='green', fg='white', width=20, height=2, wraplength=150, command=lambda: (display_folders(parent_folder), display_files(parent_folder)))
        folder_up_button.grid(row=row, column=column, padx=10, pady=5)

        default_font = folder_up_button.cget("font")
        new_font = tkFont.Font(font=default_font)
        new_font.config(size=int(new_font['size'] * 1.2), weight='bold')
        folder_up_button.config(font=new_font)

        column += 1
        if column >= num_columns:
            row += 1
            column = 0

    for folder in folders:
        folder_button = tk.Button(folder_frame, text=folder, width=20, height=2, wraplength=150, command=lambda path=os.path.join(folder_path, folder): (display_folders(path), display_files(path)))
        folder_button.grid(row=row, column=column, padx=10, pady=5)

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

def natural_sort_key(s):
    return [int(text) if text.isdigit() else text.lower()
            for text in re.split('(\d+)', s)]

def display_files(files_or_folder_path):
    media_extensions = ('.mp3', '.mp4', '.mkv', '.avi', '.flv', '.mov', '.wmv')
    playlist_extensions = ('.xspf',)

    padding_x = 10

    for widget in media_frame.winfo_children():
        widget.destroy()

    window_width = root.winfo_width()

    button_width = 170

    num_columns = calculate_columns(window_width - media_scrollbar.winfo_width(), button_width)

    row, column = 0, 0
    
    if isinstance(files_or_folder_path, str): 
        folder_path = files_or_folder_path
        files = os.listdir(folder_path)
        files.sort(key=natural_sort_key)
    else:  
        files = files_or_folder_path
        files.sort(key=lambda x: natural_sort_key(os.path.basename(x)))

    media_box = None

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
    if media_box:
        media_frame_width = (button_width + padding_x) * num_columns
        media_frame.config(width=media_frame_width, height=(row + 1) * (media_box.winfo_reqheight() + 10))
        media_canvas.config(width=media_frame_width + padding_x + media_scrollbar.winfo_width(), scrollregion=media_canvas.bbox('all'))

def on_root_configure(event):
    global previous_window_size, initial_load
    current_window_size = (root.winfo_width(), root.winfo_height())
    
    if folder_path and (previous_window_size is None or previous_window_size != current_window_size):
        root.after(2000, update_display)
        previous_window_size = current_window_size
        save_last_directory()
        
        if not initial_load:
            # Save paned window position only if window size is larger than 1x1
            if current_window_size[0] > 1 and current_window_size[1] > 1:
                save_panedwindow_position()

def on_keypress(event):
    if event.keysym == 'Return':
        perform_search()

def on_closing():
    save_last_directory()
    root.destroy()


root.title("Media Indexer and Player")

root.bind('<Configure>', on_root_configure)

frame = tk.Frame(root, pady=10)
frame.pack(fill='x')

frame.columnconfigure(0, weight=1)
frame.columnconfigure(1, weight=1)
frame.columnconfigure(2, weight=1)

open_button = tk.Button(frame, text="Open folder", command=open_folder)
open_button.grid(row=0, column=0, padx=5, pady=5)

search_entry = tk.Entry(frame)
search_entry.grid(row=0, column=1, padx=5, pady=5, sticky='ew')
search_entry.bind('<Key>', on_keypress)

search_button = tk.Button(frame, text="Search", command=perform_search)
search_button.grid(row=0, column=2, padx=5, pady=5)

paned_window = ttk.Panedwindow(root, orient=tk.VERTICAL)
paned_window.pack(expand=True, fill='both')

s = ttk.Style()
s.configure("TPanedwindow", background='grey', sashthickness=5)

folder_frame = tk.Frame(paned_window)
paned_window.add(folder_frame, weight=1)

media_outer_frame = tk.Frame(paned_window)
paned_window.add(media_outer_frame, weight=1)

media_canvas = tk.Canvas(media_outer_frame)
media_canvas.pack(side='left', expand=True, fill='both')

media_scrollbar = tk.Scrollbar(media_outer_frame, orient='vertical', command=media_canvas.yview)
media_scrollbar.pack(side='right', fill='y')
media_canvas.configure(yscrollcommand=media_scrollbar.set)

media_frame = tk.Frame(media_canvas)
media_canvas.create_window((0, 0), window=media_frame, anchor='nw')
media_canvas.configure(scrollregion=media_canvas.bbox('all'))

media_canvas.bind_all("<MouseWheel>", on_mousewheel)

load_last_directory()

if __name__ == '__main__':
    style = ttk.Style()
    style.configure("TSizegrip", relief='flat')

    bottom_frame = tk.Frame(root)
    bottom_frame.pack(side='bottom', fill='x')

    root.sizegrip = ttk.Sizegrip(bottom_frame, style="TSizegrip")
    root.sizegrip.grid(row=0, column=0, sticky='se')

    root.after(100, update_display)
    root.after(100, lambda: display_folders(folder_path))
    root.after(100, lambda: display_files(folder_path))

    root.protocol("WM_DELETE_WINDOW", on_closing)
    root.mainloop()
