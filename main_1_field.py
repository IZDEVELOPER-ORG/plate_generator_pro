import tkinter as tk
from tkinter import filedialog, colorchooser, messagebox
from PIL import Image, ImageDraw, ImageFont, ImageTk
import numpy as np
import pandas as pd
from pathlib import Path
import random
import json
import pyautogui
from datetime import datetime
from pynput import mouse
import uuid

# =========================
# CONFIG
# =========================
DEFAULT_FONT_PATH = "arial.ttf"
OUTPUT_DIR = Path("output")
OUTPUT_DIR.mkdir(exist_ok=True)
ANGLE_RANGE = (-5, 5)


# =========================
# HELPERS
# =========================
def rotate_image(img, angle):
    return img.rotate(angle, resample=Image.BICUBIC, expand=False, fillcolor=(128, 128, 128))


def draw_text_center(img, text, box, font_path, max_font_size, color, stretch=True):
    x1, y1, x2, y2 = box
    w = x2 - x1
    h = y2 - y1
    if w <= 0 or h <= 0: return

    try:
        font = ImageFont.truetype(font_path, max_font_size)
    except:
        font = ImageFont.load_default()

    draw = ImageDraw.Draw(img)
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]

    if stretch:
        padding = int(th * 0.55)
        text_img = Image.new("RGBA", (tw, th + padding), (0, 0, 0, 0))
        text_draw = ImageDraw.Draw(text_img)
        text_draw.text((0, padding // 2), text, font=font, fill=color)
        text_img = text_img.resize((w, h), resample=Image.BICUBIC)
        img.paste(text_img, (x1, y1), text_img)
    else:
        font_size = max_font_size
        while font_size > 5:
            try:
                font = ImageFont.truetype(font_path, font_size)
            except:
                font = ImageFont.load_default()
            bbox = draw.textbbox((0, 0), text, font=font)
            if (bbox[2] - bbox[0]) <= w and (bbox[3] - bbox[1]) <= h: break
            font_size -= 2
        draw.text((x1, y1), text, font=font, fill=color)


# =========================
# GUI
# =========================
class App:
    def __init__(self, root):
        self.root = root
        self.root.title("Plate Generator - With Jitter Control")

        # Основной контейнер для холста
        self.canvas = tk.Canvas(root, bg="gray")
        self.canvas.pack(fill="both", expand=True)

        # Панель управления
        ctrl_frame = tk.Frame(root)
        ctrl_frame.pack(pady=5, fill="x")

        # Кнопки
        tk.Button(ctrl_frame, text="Font Color", command=self.change_color).pack(side="left", padx=2)
        tk.Button(ctrl_frame, text="Pipette", command=self.change_color_pipette).pack(side="left", padx=2)
        tk.Button(ctrl_frame, text="Load BG", command=self.load_bg).pack(side="left", padx=2)
        tk.Button(ctrl_frame, text="Load Font", command=self.load_font).pack(side="left", padx=2)

        # --- НОВАЯ ФИЧА: Ползунок смещения ---
        self.jitter_var = tk.IntVar(value=5)  # Дефолтное смещение 5 пикселей
        tk.Label(ctrl_frame, text="Jitter:").pack(side="left", padx=(10, 2))
        self.jitter_scale = tk.Scale(ctrl_frame, from_=0, to=50, orient="horizontal", variable=self.jitter_var)
        self.jitter_scale.pack(side="left", padx=5)
        # -------------------------------------

        tk.Button(ctrl_frame, text="Save JSON", command=self.save_json).pack(side="left", padx=2)
        tk.Button(ctrl_frame, text="Load JSON", command=self.load_json).pack(side="left", padx=2)
        tk.Button(ctrl_frame, text="Load Data", command=self.load_data).pack(side="left", padx=2)
        tk.Button(ctrl_frame, text="GENERATE", command=self.generate, bg="green", fg="white").pack(side="right",
                                                                                                   padx=10)

        self.field = {
            "name": "Field 1",
            "box": [50, 50, 250, 150],
            "font_color": "#000000"
        }

        self.bg_image = None
        self.tk_img = None
        self.font_path = DEFAULT_FONT_PATH
        self.sample_data = [{"Field 1": "A123BC"}]

        self.canvas.bind("<Button-1>", self.on_click)
        self.canvas.bind("<B1-Motion>", self.on_drag)

    def load_bg(self):
        path = filedialog.askopenfilename()
        if path:
            self.bg_image = Image.open(path).convert("RGB")
            self.canvas.config(width=self.bg_image.width, height=self.bg_image.height)
            self.show_image()

    def show_image(self):
        if self.bg_image is None: return
        display_img = self.bg_image.copy()
        draw = ImageDraw.Draw(display_img)
        box = self.field["box"]
        draw.rectangle(box, outline="red", width=2)
        draw.text((box[0], box[1] - 15), "Field 1", fill="red")
        self.tk_img = ImageTk.PhotoImage(display_img)
        self.canvas.create_image(0, 0, anchor="nw", image=self.tk_img)

    def load_font(self):
        path = filedialog.askopenfilename(filetypes=[("TTF files", "*.ttf")])
        if path: self.font_path = path

    def change_color(self):
        color_code = colorchooser.askcolor(title="Choose font color")
        if color_code[1]:
            self.field["font_color"] = color_code[1]
            self.show_image()

    def change_color_pipette(self):
        messagebox.showinfo("Pipette", "Click anywhere on screen to pick color")

        def on_click_pipette(x, y, button, pressed):
            if pressed and button == mouse.Button.left:
                rgb = pyautogui.screenshot().getpixel((x, y))
                self.field["font_color"] = '#{:02x}{:02x}{:02x}'.format(*rgb)
                return False

        with mouse.Listener(on_click=on_click_pipette) as listener:
            listener.join()
        self.show_image()

    def on_click(self, event):
        self.start_x = event.x
        self.start_y = event.y

    def on_drag(self, event):
        if self.bg_image is None: return
        x1, y1, x2, y2 = self.start_x, self.start_y, event.x, event.y
        self.field["box"] = [min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)]
        self.show_image()

    def save_json(self):
        path = filedialog.asksaveasfilename(defaultextension=".json")
        if path:
            data = {"field": self.field, "font_path": self.font_path, "jitter": self.jitter_var.get()}
            with open(path, "w") as f:
                json.dump(data, f, indent=4)

    def load_json(self):
        path = filedialog.askopenfilename()
        if path:
            with open(path, "r") as f:
                data = json.load(f)
            self.field = data["field"]
            self.font_path = data.get("font_path", DEFAULT_FONT_PATH)
            self.jitter_var.set(data.get("jitter", 5))
            self.show_image()

    def load_data(self):
        path = filedialog.askopenfilename(filetypes=[("Data files", "*.csv *.txt")])
        if not path: return
        try:
            if path.endswith('.csv'):
                df = pd.read_csv(path)
                self.sample_data = [{"Field 1": str(val)} for val in df.iloc[:, 0].tolist()]
            else:
                with open(path, "r", encoding="utf-8") as f:
                    self.sample_data = [{"Field 1": line.strip()} for line in f if line.strip()]
            messagebox.showinfo("Loaded", f"Loaded {len(self.sample_data)} rows")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load: {e}")

    def generate(self):
        if self.bg_image is None:
            messagebox.showwarning("Warning", "Load background first!")
            return

        prefix1, prefix2 = "W", "A"
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        run_dir = OUTPUT_DIR / f"run_{timestamp}"
        run_dir.mkdir(parents=True)

        jitter_val = self.jitter_var.get()  # Получаем значение с ползунка
        report_lines = []

        for sample in self.sample_data:
            val = str(sample.get("Field 1", ""))
            img = self.bg_image.copy()

            # Вычисляем рандомный офсет для текущей итерации
            off_x = random.randint(-jitter_val, jitter_val)
            off_y = random.randint(-jitter_val, jitter_val)

            b = self.field["box"]
            # Применяем смещение к координатам
            j_box = [b[0] + off_x, b[1] + off_y, b[2] + off_x, b[3] + off_y]

            draw_text_center(img, val, j_box, self.font_path, 300, self.field["font_color"])

            img = rotate_image(img, random.uniform(*ANGLE_RANGE))

            # Ресайз до 100px по высоте
            target_h = 100
            target_w = int(target_h * (img.width / img.height))
            img = img.resize((target_w, target_h), resample=Image.Resampling.LANCZOS)

            image_filename = f"img_{prefix1}{prefix2}{val}_{uuid.uuid4()}.jpg"
            img.save(run_dir / image_filename, quality=95)
            report_lines.append(f"{image_filename},{prefix1}/{prefix2}{val},99")

        with open(run_dir / "labels.txt", "w", encoding="utf-8") as f:
            f.write("\n".join(report_lines))

        messagebox.showinfo("Done", f"Generated {len(self.sample_data)} images in {run_dir}")


if __name__ == "__main__":
    root = tk.Tk()
    app = App(root)
    root.mainloop()
