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


def add_noise(img):
    arr = np.array(img).astype(np.float32)
    noise = np.random.normal(0, 10, arr.shape)
    arr = np.clip(arr + noise, 0, 255).astype(np.uint8)
    return Image.fromarray(arr)


def draw_text_center(img, text, box, font_path, max_font_size, color, stretch=True):
    x1, y1, x2, y2 = box
    w = x2 - x1
    h = y2 - y1
    if w <= 0 or h <= 0:
        return

    try:
        font = ImageFont.truetype(font_path, max_font_size)
    except:
        font = ImageFont.load_default()

    draw = ImageDraw.Draw(img)
    if stretch:
        bbox = draw.textbbox((0, 0), text, font=font, anchor="lt")
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]

        text_img = Image.new("RGBA", (tw, th), (0, 0, 0, 0))
        text_draw = ImageDraw.Draw(text_img)

        text_draw.text((-bbox[0], -bbox[1]), text, font=font, fill=color, anchor="lt")
        text_img = text_img.resize((w, h), resample=Image.BICUBIC)
        img.paste(text_img, (x1, y1), text_img)
    else:
        draw.text((x1, y1), text, font=font, fill=color)


# =========================
# GUI
# =========================
class App:
    def __init__(self, root):
        self.root = root
        self.root.title("Plate Generator Pro")

        # Настройка 4-х полей
        self.fields = []
        for i in range(4):
            self.fields.append({
                "name": f"Field {i + 1}",
                "box": [50 + (i * 20), 50 + (i * 20), 250 + (i * 20), 150 + (i * 20)],
                "font_color": "#000000"
            })
        self.current_field_idx = tk.IntVar(value=0)

        # Панель режимов
        mode_frame = tk.LabelFrame(root, text=" Control Panel ")
        mode_frame.pack(side="top", fill="x", padx=5, pady=5)

        # Переключатель редактируемого поля
        field_select_frame = tk.LabelFrame(mode_frame, text=" Select Field to Edit ")
        field_select_frame.pack(side="left", padx=5, pady=5)
        for i in range(4):
            tk.Radiobutton(field_select_frame, text=f"F{i + 1}", variable=self.current_field_idx,
                           value=i, command=self.show_image).pack(side="left")

        # Чекбоксы эффектов
        effects_frame = tk.LabelFrame(mode_frame, text=" Effects ")
        effects_frame.pack(side="left", padx=5, pady=5)
        self.use_rotation = tk.BooleanVar(value=True)
        self.use_noise = tk.BooleanVar(value=False)
        tk.Checkbutton(effects_frame, text="Rotation", variable=self.use_rotation).pack(side="left")
        tk.Checkbutton(effects_frame, text="Noise", variable=self.use_noise).pack(side="left")

        # Универсальное поле префикса
        prefix_frame = tk.LabelFrame(mode_frame, text=" Prefix ")
        prefix_frame.pack(side="left", padx=5, fill="y", expand=False)
        self.prefix_var = tk.StringVar(value="")
        self.prefix_entry = tk.Entry(prefix_frame, textvariable=self.prefix_var, width=10)
        self.prefix_entry.pack(side="left", padx=5, pady=2)

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

        # Ползунок смещения
        self.jitter_var = tk.IntVar(value=0)  # Дефолтное смещение 0 пикселей
        tk.Label(ctrl_frame, text="Jitter:").pack(side="left", padx=(10, 2))
        self.jitter_scale = tk.Scale(ctrl_frame, from_=0, to=50, orient="horizontal", variable=self.jitter_var)
        self.jitter_scale.pack(side="left", padx=5)

        tk.Button(ctrl_frame, text="Save JSON", command=self.save_json).pack(side="left", padx=2)
        tk.Button(ctrl_frame, text="Load JSON", command=self.load_json).pack(side="left", padx=2)
        tk.Button(ctrl_frame, text="Load Data", command=self.load_data).pack(side="left", padx=2)
        tk.Button(ctrl_frame, text="GENERATE", command=self.generate, bg="green", fg="white").pack(side="right",
                                                                                                   padx=10)

        # self.field = {
        #     "name": "Field 1",
        #     "box": [50, 50, 250, 150],
        #     "font_color": "#000000"
        # }

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

    # def show_image(self):
    #     if self.bg_image is None:
    #         return
    #     display_img = self.bg_image.copy()
    #     draw = ImageDraw.Draw(display_img)
    #
    #     box = self.field["box"]
    #     draw.rectangle(box, outline="red", width=2)
    #     draw.text((box[0], box[1] - 15), "Field 1", fill="red")
    #
    #     self.tk_img = ImageTk.PhotoImage(display_img)
    #     self.canvas.create_image(0, 0, anchor="nw", image=self.tk_img)

    def show_image(self):
        if self.bg_image is None:
            return
        display_img = self.bg_image.copy()
        draw = ImageDraw.Draw(display_img)

        curr_idx = self.current_field_idx.get()
        for i, field in enumerate(self.fields):
            box = field["box"]
            is_active = (i == curr_idx)
            color = "red" if is_active else "blue"
            width = 3 if is_active else 1
            draw.rectangle(box, outline=color, width=width)
            draw.text((box[0], box[1] - 15), field["name"], fill=color)

        self.tk_img = ImageTk.PhotoImage(display_img)
        self.canvas.create_image(0, 0, anchor="nw", image=self.tk_img)

    def load_font(self):
        path = filedialog.askopenfilename(filetypes=[("TTF files", "*.ttf")])
        if path:
            self.font_path = path

    # def change_color(self):
    #     color_code = colorchooser.askcolor(title="Choose font color")
    #     if color_code[1]:
    #         self.field["font_color"] = color_code[1]
    #         self.show_image()

    def change_color(self):
        color_code = colorchooser.askcolor(title="Choose font color")
        if color_code[1]:
            idx = self.current_field_idx.get()
            self.fields[idx]["font_color"] = color_code[1]
            self.show_image()

    def change_color_pipette(self):
        messagebox.showinfo("Pipette", "Click anywhere on screen to pick color")

        # Функция, которая сработает ПРИ КЛИКЕ
        def on_click_logic(x, y, button, pressed):
            if pressed and button == mouse.Button.left:
                # 1. Берем цвет пикселя
                rgb = pyautogui.screenshot().getpixel((x, y))
                hex_color = '#{:02x}{:02x}{:02x}'.format(*rgb)

                # 2. Передаем обновление цвета в основной поток Tkinter
                # Используем .after(0, ...), чтобы избежать конфликтов потоков
                self.root.after(0, lambda: self.apply_pipette_result(hex_color))

                return False  # Останавливаем слушатель мыши

        # Запускаем слушатель в фоновом режиме
        self.pipette_listener = mouse.Listener(on_click=on_click_logic)
        self.pipette_listener.start()

    def apply_pipette_result(self, hex_color):
        """
            Вспомогательная функция для обновления интерфейса
        """
        # Получаем индекс выбранного сейчас поля (0-3)
        idx = self.current_field_idx.get()
        self.fields[idx]["font_color"] = hex_color

        # Обновляем картинку на холсте
        self.show_image()
        print(f"Цвет для Field {idx + 1} изменен на: {hex_color}")

    def on_click(self, event):
        self.start_x = event.x
        self.start_y = event.y

    # def on_drag(self, event):
    #     if self.bg_image is None: return
    #     x1, y1, x2, y2 = self.start_x, self.start_y, event.x, event.y
    #     self.field["box"] = [min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)]
    #     self.show_image()

    def on_drag(self, event):
        if self.bg_image is None: return
        idx = self.current_field_idx.get()
        x1, y1, x2, y2 = self.start_x, self.start_y, event.x, event.y
        self.fields[idx]["box"] = [min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)]
        self.show_image()

    def save_json(self):
        path = filedialog.asksaveasfilename(defaultextension=".json")
        if path:
            data = {
                "fields": self.fields,
                "font_path": self.font_path,
                "jitter": self.jitter_var.get(),
                "use_rotation": self.use_rotation.get(),
                "use_noise": self.use_noise.get()
            }
            with open(path, "w") as f:
                json.dump(data, f, indent=4)

    def load_json(self):
        path = filedialog.askopenfilename()
        if path:
            with open(path, "r") as f:
                data = json.load(f)
            self.fields = data.get("fields", [self.fields[0]])
            self.font_path = data.get("font_path", DEFAULT_FONT_PATH)
            self.jitter_var.set(data.get("jitter", 0))
            self.use_rotation.set(data.get("use_rotation", False))
            self.use_noise.set(data.get("use_noise", False))
            self.show_image()

    # def save_json(self):
    #     path = filedialog.asksaveasfilename(defaultextension=".json")
    #     if path:
    #         data = {"field": self.field, "font_path": self.font_path, "jitter": self.jitter_var.get()}
    #         with open(path, "w") as f:
    #             json.dump(data, f, indent=4)

    # def load_json(self):
    #     path = filedialog.askopenfilename()
    #     if path:
    #         with open(path, "r") as f:
    #             data = json.load(f)
    #         self.field = data["field"]
    #         self.font_path = data.get("font_path", DEFAULT_FONT_PATH)
    #         self.jitter_var.set(data.get("jitter", 5))
    #         self.show_image()

    # def load_data(self):
    #     path = filedialog.askopenfilename(filetypes=[("Data files", "*.csv *.txt")])
    #     if not path:
    #         return
    #     try:
    #         if path.endswith('.csv'):
    #             df = pd.read_csv(path)
    #             # self.sample_data = [{"Field 1": str(val)} for val in df.iloc[:, 0].tolist()]
    #             self.sample_data = df.to_dict('records')
    #         else:
    #             with open(path, "r", encoding="utf-8") as f:
    #                 self.sample_data = [{"Field 1": line.strip()} for line in f if line.strip()]
    #         messagebox.showinfo("Loaded", f"Loaded {len(self.sample_data)} rows")
    #     except Exception as e:
    #         messagebox.showerror("Error", f"Failed to load: {e}")

    def load_data(self):
        path = filedialog.askopenfilename(filetypes=[("Data files", "*.csv *.txt")])
        if not path:
            return

        field_names = ["Field 1", "Field 2", "Field 3", "Field 4"]
        new_data = []

        try:
            if path.endswith('.csv'):
                df = pd.read_csv(path, sep=',', encoding='utf-8')
                for _, row in df.iterrows():
                    entry = {}
                    for i, name in enumerate(field_names):
                        entry[name] = str(row[i]) if i < len(row) else ""
                    new_data.append(entry)

            else:
                with open(path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue

                        parts = [p.strip() for p in line.split(",")]

                        # Создаем словарь для 4-х полей
                        entry = {}
                        for i in range(4):
                            entry[field_names[i]] = parts[i] if i < len(parts) else ""

                        new_data.append(entry)

            if new_data:
                self.sample_data = new_data
                messagebox.showinfo("Loaded", f"Loaded {len(new_data)} rows.\n"f"Example: {new_data[0]}")
            else:
                messagebox.showwarning("Warning", "Empty file or wrong data format!")

        except Exception as e:
            messagebox.showerror("Error", f"Failed to load: {e}")

    # def generate(self):
    #     if self.bg_image is None:
    #         messagebox.showwarning("Warning", "Load background first!")
    #         return
    #
    #     prefix = self.prefix_var.get()
    #     timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    #     run_dir = OUTPUT_DIR / f"run_{timestamp}"
    #     run_dir.mkdir(parents=True)
    #
    #     jitter_val = self.jitter_var.get()  # Получаем значение с ползунка
    #     report_lines = []
    #
    #     for sample in self.sample_data:
    #         val = str(sample.get("Field 1", ""))
    #         img = self.bg_image.copy()
    #
    #         # Вычисляем рандомный офсет для текущей итерации
    #         off_x = random.randint(-jitter_val, jitter_val)
    #         off_y = random.randint(-jitter_val, jitter_val)
    #
    #         b = self.field["box"]
    #         # Применяем смещение к координатам
    #         j_box = [b[0] + off_x, b[1] + off_y, b[2] + off_x, b[3] + off_y]
    #         draw_text_center(img, val, j_box, self.font_path, 300, self.field["font_color"])
    #         img = rotate_image(img, random.uniform(*ANGLE_RANGE))
    #
    #         # Ресайз до 100px по высоте
    #         target_h = 100
    #         target_w = int(target_h * (img.width / img.height))
    #         img = img.resize((target_w, target_h), resample=Image.Resampling.LANCZOS)
    #
    #         image_filename = f"img_{val}_{uuid.uuid4()}.jpg"
    #         img.save(run_dir / image_filename, quality=95)
    #         report_lines.append(f"{image_filename},{prefix}{val},99")
    #
    #     with open(run_dir / "labels.txt", "w", encoding="utf-8") as f:
    #         f.write("\n".join(report_lines))
    #
    #     messagebox.showinfo("Done", f"Generated {len(self.sample_data)} images in {run_dir}")

    def generate(self):
        if self.bg_image is None:
            messagebox.showwarning("Warning", "Load background first!")
            return

        prefix = self.prefix_var.get()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        run_dir = OUTPUT_DIR / f"run_{timestamp}"
        run_dir.mkdir(parents=True)

        jitter_val = self.jitter_var.get()
        report_lines = []

        for sample in self.sample_data:
            img = self.bg_image.copy()
            full_label_parts = []

            # Отрисовываем каждое из 4-х полей, если для него есть данные
            for i in range(4):
                key = f"Field {i + 1}"
                val = str(sample.get(key, ""))
                if not val or val == "nan":
                    continue

                f_cfg = self.fields[i]
                off_x = random.randint(-jitter_val, jitter_val)
                off_y = random.randint(-jitter_val, jitter_val)

                b = f_cfg["box"]
                j_box = [b[0] + off_x, b[1] + off_y, b[2] + off_x, b[3] + off_y]

                draw_text_center(img, val, j_box, self.font_path, 300, f_cfg["font_color"])
                full_label_parts.append(val)

            # Эффект поворота
            if self.use_rotation.get():
                img = rotate_image(img, random.uniform(*ANGLE_RANGE))

            # Эффект шума
            if self.use_noise.get():
                img = add_noise(img)

            # Resize 100px height
            target_h = 100
            target_w = int(target_h * (img.width / img.height))
            img = img.resize((target_w, target_h), resample=Image.Resampling.LANCZOS)

            combined_val = "_".join(full_label_parts)
            image_filename = f"img_{uuid.uuid4()}.jpg"
            img.save(run_dir / image_filename, quality=95)
            report_lines.append(f"{image_filename},{prefix}{combined_val},99")

        with open(run_dir / "labels.txt", "w", encoding="utf-8") as f:
            f.write("\n".join(report_lines))

        messagebox.showinfo("Done", f"Generated {len(self.sample_data)} images in {run_dir}")


if __name__ == "__main__":
    root = tk.Tk()
    app = App(root)
    root.mainloop()
