import tkinter as tk
from tkinter import messagebox
from ui import DatamoshApp
from engine import check_tools

if __name__ == "__main__":
    root = tk.Tk()
    
    if not check_tools():
        root.withdraw()
        messagebox.showerror("Erreur Fatale", "FFmpeg introuvable. Installe-le ou place ffmpeg.exe / ffprobe.exe dans le dossier.")
        exit(1)
        
    app = DatamoshApp(root)
    root.mainloop()