import customtkinter as ctk
import tkinter as tk
from tkinter import ttk
import threading
import json
import os
# Importamos apenas o essencial que sabemos que existe no main.py
from main import download_and_extract_map, analyze_map_structure, resolve_beatsaver_id
from trainer import predict_stars, train_model

# --- Configuration ---
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

HISTORY_FILE = "analyzed_history.json"

class App(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("BS Star Analyzer v2")
        self.geometry("1000x700")

        # Data
        self.current_analysis = None
        self.current_map_hash = None
        self.history = self.load_history()

        # Layout
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.tab_view = ctk.CTkTabview(self)
        self.tab_view.grid(row=0, column=0, padx=20, pady=20, sticky="nsew")
        
        self.tab_analyze = self.tab_view.add("Analyze")
        self.tab_history = self.tab_view.add("History")
        self.tab_train = self.tab_view.add("Train/Settings")

        self.setup_analyze_tab()
        self.setup_history_tab()
        self.setup_train_tab()

    def load_history(self):
        if os.path.exists(HISTORY_FILE):
            with open(HISTORY_FILE, 'r') as f:
                return json.load(f)
        return []

    def save_history(self):
        with open(HISTORY_FILE, 'w') as f:
            json.dump(self.history, f, indent=2)
        self.update_history_view()

    def setup_analyze_tab(self):
        # Input Frame
        input_frame = ctk.CTkFrame(self.tab_analyze)
        input_frame.pack(fill="x", padx=10, pady=10)

        self.entry_id = ctk.CTkEntry(input_frame, placeholder_text="Enter Map ID (e.g., 42a2e) or Hash")
        self.entry_id.pack(side="left", fill="x", expand=True, padx=10, pady=10)

        btn_analyze = ctk.CTkButton(input_frame, text="Analyze", command=self.start_analysis)
        btn_analyze.pack(side="right", padx=10, pady=10)

        # Info Frame
        self.info_frame = ctk.CTkFrame(self.tab_analyze)
        self.info_frame.pack(fill="x", padx=10, pady=5)
        
        self.lbl_song_name = ctk.CTkLabel(self.info_frame, text="Song: -", font=("Arial", 16, "bold"))
        self.lbl_song_name.pack(anchor="w", padx=10, pady=2)
        
        self.lbl_bpm = ctk.CTkLabel(self.info_frame, text="BPM: -")
        self.lbl_bpm.pack(anchor="w", padx=10, pady=2)

        # Results Scrollable Frame
        self.results_frame = ctk.CTkScrollableFrame(self.tab_analyze, label_text="Difficulties")
        self.results_frame.pack(fill="both", expand=True, padx=10, pady=10)

        # Action Buttons
        action_frame = ctk.CTkFrame(self.tab_analyze)
        action_frame.pack(fill="x", padx=10, pady=10)
        
        btn_save = ctk.CTkButton(action_frame, text="Save to History", command=self.add_to_history, fg_color="green")
        btn_save.pack(fill="x", padx=10, pady=10)

        self.status_label = ctk.CTkLabel(self.tab_analyze, text="Ready", text_color="gray")
        self.status_label.pack(side="bottom", pady=5)

    def setup_history_tab(self):
        # Using Treeview for history list
        self.history_frame = ctk.CTkFrame(self.tab_history)
        self.history_frame.pack(fill="both", expand=True, padx=10, pady=10)

        # Since CustomTkinter doesn't have a native Treeview, we wrap Tkinter's
        style = ttk.Style()
        style.theme_use("default")
        style.configure("Treeview", 
                        background="#2b2b2b", 
                        foreground="white", 
                        fieldbackground="#2b2b2b",
                        rowheight=25)
        style.map('Treeview', background=[('selected', '#1f538d')])

        columns = ("song", "diff", "stars", "hash")
        self.tree = ttk.Treeview(self.history_frame, columns=columns, show="headings")
        self.tree.heading("song", text="Song")
        self.tree.heading("diff", text="Difficulty")
        self.tree.heading("stars", text="Stars")
        self.tree.heading("hash", text="Hash")
        
        self.tree.column("song", width=300)
        self.tree.column("diff", width=100)
        self.tree.column("stars", width=100)
        self.tree.column("hash", width=300)

        self.tree.pack(fill="both", expand=True)
        
        btn_refresh = ctk.CTkButton(self.tab_history, text="Refresh", command=self.update_history_view)
        btn_refresh.pack(pady=10)
        
        self.update_history_view()

    def update_history_view(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        
        for entry in self.history:
            song = entry.get('songName', 'Unknown')
            _hash = entry.get('hash', '')
            for diff in entry.get('difficulties', []):
                self.tree.insert("", "end", values=(song, diff['name'], f"{diff['stars']}*", _hash))

    def setup_train_tab(self):
        btn_train = ctk.CTkButton(self.tab_train, text="Retrain Model", command=self.run_training)
        btn_train.pack(pady=20)
        
        self.train_status = ctk.CTkTextbox(self.tab_train, height=200)
        self.train_status.pack(fill="x", padx=20, pady=10)

    def run_training(self):
        self.train_status.insert("end", "Training started...\n")
        def _train():
            try:
                train_model()
                self.train_status.insert("end", "Training complete!\n")
            except Exception as e:
                self.train_status.insert("end", f"Error: {e}\n")
        
        threading.Thread(target=_train, daemon=True).start()

    def start_analysis(self):
        target = self.entry_id.get().strip()
        if not target:
            self.status_label.configure(text="Please enter an ID or Hash", text_color="red")
            return

        self.status_label.configure(text="Resolving ID...", text_color="yellow")
        self.clear_results()
        
        threading.Thread(target=self.process_analysis, args=(target,), daemon=True).start()

    def clear_results(self):
        self.lbl_song_name.configure(text="Song: -")
        self.lbl_bpm.configure(text="BPM: -")
        for widget in self.results_frame.winfo_children():
            widget.destroy()

    def process_analysis(self, target):
        try:
            if len(target) < 10:
                map_hash = resolve_beatsaver_id(target)
                if not map_hash:
                    self.status_label.configure(text="Could not resolve BeatSaver Key", text_color="red")
                    return
            else:
                map_hash = target

            self.current_map_hash = map_hash
            self.status_label.configure(text="Downloading map...", text_color="yellow")
            
            map_path = download_and_extract_map(map_hash)
            if not map_path:
                self.status_label.configure(text="Download failed", text_color="red")
                return

            self.status_label.configure(text="Analyzing structure...", text_color="yellow")
            analysis = analyze_map_structure(map_path)
            if not analysis:
                self.status_label.configure(text="Analysis failed", text_color="red")
                return

            self.current_analysis = analysis
            
            # Update UI on main thread
            self.after(0, self.display_results, analysis, map_hash)

        except Exception as e:
            self.status_label.configure(text=f"Error: {str(e)}", text_color="red")
            print(e)

    def display_results(self, analysis, map_hash):
        self.lbl_song_name.configure(text=f"Song: {analysis['song_name']}")
        self.lbl_bpm.configure(text=f"BPM: {analysis['bpm']}")
        self.status_label.configure(text="Analysis Complete", text_color="green")

        self.diff_widgets = [] # To store references to entry widgets

        for diff in analysis['difficulties']:
            # Predict
            features = {**diff, 'bpm': analysis['bpm']}
            
            # Use default performance values instead of fetching from ScoreSaber to keep it simple and safe for now
            # This avoids dependency on functions that might not exist in main.py
            features.update({
                'acc_top10': 0.96, 
                'acc_q1': 0.94, 
                'acc_median': 0.90, 
                'acc_q3': 0.85,
                'elite_decay': 0.02, 
                'general_decay': 0.04, 
                'acc_std': 0.05,
                'fc_rate': 0.1, 
                'plays': 0
            })
            
            pred = predict_stars(features)
            pred_val = f"{pred:.2f}" if pred else "0.00"

            # UI Row
            row = ctk.CTkFrame(self.results_frame)
            row.pack(fill="x", pady=5)

            lbl_name = ctk.CTkLabel(row, text=diff['difficulty'], width=100, anchor="w", font=("Arial", 12, "bold"))
            lbl_name.pack(side="left", padx=10)

            lbl_info = ctk.CTkLabel(row, text=f"NPS: {diff['nps']} | Peak: {diff['peak_nps']}", width=150)
            lbl_info.pack(side="left", padx=5)

            # Star Value Entry (Editable)
            entry_stars = ctk.CTkEntry(row, width=60)
            entry_stars.insert(0, pred_val)
            entry_stars.pack(side="left", padx=5)

            # Buff/Nerf Buttons
            def adjust(e=entry_stars, val=0.1):
                try:
                    curr = float(e.get())
                    new_val = max(0, curr + val)
                    e.delete(0, "end")
                    e.insert(0, f"{new_val:.2f}")
                except: pass

            btn_minus = ctk.CTkButton(row, text="-", width=30, command=lambda: adjust(val=-0.1))
            btn_minus.pack(side="left", padx=2)
            
            btn_plus = ctk.CTkButton(row, text="+", width=30, command=lambda: adjust(val=0.1))
            btn_plus.pack(side="left", padx=2)

            self.diff_widgets.append({
                "name": diff['difficulty'],
                "entry": entry_stars
            })

    def add_to_history(self):
        if not self.current_analysis:
            return

        final_diffs = []
        for widget in self.diff_widgets:
            try:
                stars = float(widget["entry"].get())
                final_diffs.append({
                    "name": widget["name"],
                    "stars": stars
                })
            except: pass

        entry = {
            "songName": self.current_analysis["song_name"],
            "hash": self.current_map_hash,
            "difficulties": final_diffs
        }

        # Check if already exists, replace if so
        existing_idx = next((i for i, item in enumerate(self.history) if item["hash"] == self.current_map_hash), -1)
        if existing_idx != -1:
            self.history[existing_idx] = entry
        else:
            self.history.append(entry)

        self.save_history()
        self.status_label.configure(text="Saved to History!", text_color="cyan")

if __name__ == "__main__":
    app = App()
    app.mainloop()
