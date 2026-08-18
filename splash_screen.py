import tkinter as tk
import time

class SplashScreen:
    def __init__(self):
        self.root = tk.Tk()
        self.root.overrideredirect(True)
        self.root.geometry("400x250")
        self.root.configure(bg='#2c3e50')
        
        # Center on screen
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        x = (screen_width - 400) // 2
        y = (screen_height - 250) // 2
        self.root.geometry(f"400x250+{x}+{y}")
        
        # Title
        title = tk.Label(
            self.root,
            text="KinderSort Lite",
            font=('Arial', 24, 'bold'),
            fg='white',
            bg='#2c3e50'
        )
        title.pack(pady=(40, 10))
        
        # Subtitle
        subtitle = tk.Label(
            self.root,
            text="AI-Powered Photo Sorting for Teachers",
            font=('Arial', 12),
            fg='#ecf0f1',
            bg='#2c3e50'
        )
        subtitle.pack(pady=10)
        
        # Loading text
        self.status = tk.Label(
            self.root,
            text="Loading...",
            font=('Arial', 10),
            fg='#bdc3c7',
            bg='#2c3e50'
        )
        self.status.pack(pady=20)
        
        # Version
        tk.Label(
            self.root,
            text="v1.0.0",
            font=('Arial', 9),
            fg='#95a5a6',
            bg='#2c3e50'
        ).pack(side='bottom', pady=10)
        
        self.root.update()
    
    def update_status(self, text):
        self.status.config(text=text)
        self.root.update()
    
    def close(self):
        self.root.destroy()