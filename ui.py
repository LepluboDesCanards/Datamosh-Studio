import os
import threading
import tkinter as tk
from tkinter import filedialog, ttk, messagebox
import cv2
from PIL import Image, ImageTk
from engine import process_video

class DatamoshApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Datamosh Studio - Ultimate NLE Edition")
        self.root.geometry("1100x850")
        
        self.input_path = tk.StringVar()
        self.output_path = tk.StringVar()
        
        self.gop_var = tk.StringVar()
        self.gop_presets = {
            "Court (Rétablissement rapide)": "50",
            "Moyen (Standard)": "250",
            "Long (Glitch persistant - Recommandé)": "1000",
            "Infini (Chaos total - 1 seul I-frame)": "9999"
        }
        
        self.timeline_events = [] 
        
        self.cap = None
        self.video_fps = 25.0
        self.total_frames = 0
        self.current_frame = 0
        self.is_seeking = False

        self.effect_descriptions = {
            "🔴 [TRANSITION] Melting": "Détruit la coupure. Fait baver la scène précédente sur la nouvelle.",
            "🔴 [TRANSITION] Flashback": "Insère l'image d'un ancien plan au milieu d'un nouveau (Ghosting).",
            "🔵 [MOUVEMENT] Smear": "Étire les pixels à l'infini dans la direction du mouvement.",
            "🔵 [MOUVEMENT] Stutter": "Bloque l'image et répète le mouvement en boucle (mitraillette).",
            "🔵 [MOUVEMENT] Reverse Stutter": "Fait bégayer le mouvement en marche arrière.",
            "🔵 [MOUVEMENT] Wobble": "Pioche aléatoirement dans les mouvements récents (rendu liquide).",
            "🔵 [MOUVEMENT] Shuffle": "Brouille l'ordre des images (destruction totale)."
        }

        self.setup_ui()

    def setup_ui(self):
        top_frame = ttk.Frame(self.root)
        top_frame.pack(fill="x", padx=10, pady=10)

        player_frame = ttk.LabelFrame(top_frame, text=" Moniteur Vidéo ", padding=5)
        player_frame.pack(side="left", fill="both", expand=True, padx=(0, 5))

        self.canvas = tk.Canvas(player_frame, width=480, height=270, bg="black")
        self.canvas.pack(pady=5)
        
        controls_frame = ttk.Frame(player_frame)
        controls_frame.pack(fill="x", pady=5)
        
        self.slider = ttk.Scale(controls_frame, from_=0, to=100, orient="horizontal", command=self.on_slider_move)
        self.slider.pack(fill="x", padx=10, pady=5)

        btn_box = ttk.Frame(controls_frame)
        btn_box.pack()
        
        ttk.Button(btn_box, text="< Frame", width=8, command=lambda: self.step_frame(-1)).grid(row=0, column=0, padx=2)
        ttk.Button(btn_box, text="Frame >", width=8, command=lambda: self.step_frame(1)).grid(row=0, column=1, padx=2)
        self.lbl_time = ttk.Label(btn_box, text="0.00s", font=("Consolas", 10, "bold"))
        self.lbl_time.grid(row=0, column=2, padx=15)
        
        ttk.Button(btn_box, text="[ Marquer Début", command=self.set_start_time).grid(row=0, column=3, padx=2)
        ttk.Button(btn_box, text="Marquer Fin ]", command=self.set_end_time).grid(row=0, column=4, padx=2)

        right_frame = ttk.Frame(top_frame)
        right_frame.pack(side="right", fill="both", expand=True, padx=(5, 0))

        file_frame = ttk.LabelFrame(right_frame, text=" Fichiers & Stabilité ", padding=10)
        file_frame.pack(fill="x", pady=(0, 5))

        ttk.Button(file_frame, text="Ouvrir Vidéo", command=self.browse_input).pack(fill="x", pady=2)
        ttk.Entry(file_frame, textvariable=self.input_path, state="readonly").pack(fill="x", pady=2)
        ttk.Button(file_frame, text="Dossier Sortie", command=self.browse_output).pack(fill="x", pady=2)
        ttk.Entry(file_frame, textvariable=self.output_path, state="readonly").pack(fill="x", pady=2)

        ttk.Label(file_frame, text="Durée de vie des glitchs (Avant réparation) :").pack(anchor="w", pady=(10, 0))
        self.gop_combo = ttk.Combobox(file_frame, textvariable=self.gop_var, values=list(self.gop_presets.keys()), state="readonly")
        self.gop_combo.current(2)
        self.gop_combo.pack(fill="x", pady=2)

        seq_frame = ttk.LabelFrame(self.root, text=" Séquenceur d'Effets ", padding=10)
        seq_frame.pack(fill="x", padx=10, pady=5)

        form_f = ttk.Frame(seq_frame)
        form_f.pack(fill="x", pady=5)
        
        ttk.Label(form_f, text="Début(s):").grid(row=0, column=0)
        self.ent_start = ttk.Entry(form_f, width=8)
        self.ent_start.grid(row=0, column=1, padx=2)

        ttk.Label(form_f, text="Fin(s):").grid(row=0, column=2)
        self.ent_end = ttk.Entry(form_f, width=8)
        self.ent_end.grid(row=0, column=3, padx=2)

        ttk.Label(form_f, text="Effet:").grid(row=0, column=4)
        self.cb_effect = ttk.Combobox(form_f, values=list(self.effect_descriptions.keys()), width=28, state="readonly")
        self.cb_effect.current(0)
        self.cb_effect.grid(row=0, column=5, padx=2)
        self.cb_effect.bind("<<ComboboxSelected>>", self.update_effect_help)

        ttk.Label(form_f, text="Intensité(2-15):").grid(row=0, column=6)
        self.ent_buffer = ttk.Entry(form_f, width=5)
        self.ent_buffer.grid(row=0, column=7, padx=2)
        self.ent_buffer.insert(0, "5")

        self.chk_audio_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(form_f, text="Corrompre Audio", variable=self.chk_audio_var).grid(row=0, column=8, padx=10)

        ttk.Button(form_f, text="➕ Ajouter à la timeline", command=self.add_event).grid(row=0, column=9)

        self.lbl_help = ttk.Label(seq_frame, text=self.effect_descriptions["🔴 [TRANSITION] Melting"], foreground="#aaaaaa")
        self.lbl_help.pack(fill="x", pady=5)

        list_frame = ttk.Frame(seq_frame)
        list_frame.pack(fill="both", expand=True, pady=5)
        
        self.listbox = tk.Listbox(list_frame, height=6, bg="#1e1e1e", fg="#ffffff", selectbackground="#555555", font=("Consolas", 10))
        self.listbox.pack(side="left", fill="both", expand=True)
        ttk.Button(list_frame, text="Supprimer", command=self.remove_event).pack(side="right", padx=5)

        self.btn_run = ttk.Button(self.root, text="🔥 LANCER L'ENCODAGE DU DATAMOSH 🔥", command=self.start_process)
        self.btn_run.pack(fill="x", padx=10, pady=10, ipady=10)

        self.log_area = tk.Text(self.root, height=10, bg="#1e1e1e", fg="#00ff00", font=("Consolas", 9))
        self.log_area.pack(fill="both", expand=True, padx=10, pady=(0, 10))

    def update_effect_help(self, event=None):
        self.lbl_help.config(text=self.effect_descriptions.get(self.cb_effect.get(), ""))

    def log(self, message):
        self.root.after(0, self._insert_log, message)

    def _insert_log(self, message):
        self.log_area.insert("end", message + "\n")
        self.log_area.see("end")

    def browse_input(self):
        f = filedialog.askopenfilename(filetypes=[("Vidéos", "*.mp4 *.avi *.mov *.mkv")])
        if f:
            self.input_path.set(f)
            if not self.output_path.get():
                base, ext = os.path.splitext(f)
                self.output_path.set(f"{base}_moshed.mp4")
            self.load_video(f)

    def browse_output(self):
        f = filedialog.asksaveasfilename(defaultextension=".mp4", filetypes=[("MP4", "*.mp4")])
        if f:
            self.output_path.set(f)

    def load_video(self, path):
        if self.cap: self.cap.release()
        self.cap = cv2.VideoCapture(path)
        self.video_fps = self.cap.get(cv2.CAP_PROP_FPS) or 25.0
        self.total_frames = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
        self.slider.config(to=max(1, self.total_frames - 1))
        self.show_frame(0)

    def show_frame(self, frame_idx):
        if not self.cap or self.total_frames <= 0: return
        self.current_frame = max(0, min(int(frame_idx), self.total_frames - 1))
        self.cap.set(cv2.CAP_PROP_POS_FRAMES, self.current_frame)
        ret, frame = self.cap.read()
        if ret:
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            frame = cv2.resize(frame, (480, 270))
            self.img = ImageTk.PhotoImage(image=Image.fromarray(frame))
            self.canvas.create_image(0, 0, anchor="nw", image=self.img)
            t_sec = self.current_frame / self.video_fps
            self.lbl_time.config(text=f"{t_sec:.2f}s")
            
            self.is_seeking = True
            self.slider.set(self.current_frame)
            self.is_seeking = False

    def on_slider_move(self, val):
        if self.is_seeking: return
        self.show_frame(float(val))

    def step_frame(self, direction):
        if not self.cap: return
        new_f = max(0, min(self.total_frames - 1, self.current_frame + direction))
        self.show_frame(new_f)

    def set_start_time(self):
        if not self.cap: return
        self.ent_start.delete(0, tk.END)
        self.ent_start.insert(0, f"{(self.current_frame / self.video_fps):.2f}")

    def set_end_time(self):
        if not self.cap: return
        self.ent_end.delete(0, tk.END)
        self.ent_end.insert(0, f"{(self.current_frame / self.video_fps):.2f}")

    def add_event(self):
        try:
            start_sec = float(self.ent_start.get())
            end_sec = float(self.ent_end.get())
            if start_sec >= end_sec: raise ValueError("Fin > Début !")
            
            ev = {
                "start": start_sec, "end": end_sec, 
                "frame": int(start_sec * 25), "dur": int((end_sec - start_sec) * 25), 
                "type": self.cb_effect.get(), 
                "buffer": max(2, min(int(self.ent_buffer.get()), 20)),
                "audio": self.chk_audio_var.get()
            }
            self.timeline_events.append(ev)
            self.timeline_events.sort(key=lambda x: x["frame"])
            self.update_listbox()
        except Exception as e:
            messagebox.showwarning("Erreur", str(e))

    def remove_event(self):
        sel = self.listbox.curselection()
        if sel:
            del self.timeline_events[sel[0]]
            self.update_listbox()

    def update_listbox(self):
        self.listbox.delete(0, tk.END)
        for idx, e in enumerate(self.timeline_events):
            aud = "🔊" if e['audio'] else "🔇"
            txt = f"[{e['start']}s -> {e['end']}s] {e['type']} (Int:{e['buffer']}) {aud}"
            self.listbox.insert(tk.END, txt)
            
            if "[TRANSITION]" in e['type']: self.listbox.itemconfig(idx, {'fg': '#ff6b6b'})
            else: self.listbox.itemconfig(idx, {'fg': '#4dabf7'})

    def start_process(self):
        inp = self.input_path.get()
        out = self.output_path.get()
        
        if not inp or not out:
            self.log("[!] Fichiers source ou destination manquants.")
            return

        self.btn_run.config(state="disabled")
        self.log_area.delete(1.0, tk.END)
        
        if self.cap:
            self.cap.release()
            self.cap = None

        gop_val = self.gop_presets[self.gop_var.get()]
        
        t = threading.Thread(target=process_video, args=(
            inp, out, gop_val, self.timeline_events, self.log, self._on_process_done
        ))
        t.daemon = True
        t.start()

    def _on_process_done(self):
        self.root.after(0, self._restore_ui)

    def _restore_ui(self):
        self.btn_run.config(state="normal")
        self.load_video(self.input_path.get())