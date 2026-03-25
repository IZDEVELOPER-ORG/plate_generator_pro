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
FONT_SIZE = 150  # Начальный размер для скалирования (максимальный)
OUTPUT_DIR = Path("output")
OUTPUT_DIR.mkdir(exist_ok=True)
ANGLE_RANGE = (-5, 5)
NOISE_LEVEL = 5


# =========================
# HELPERS
# =========================
def add_simple_noise(img):
    img_np = np.array(img)
    noise = np.random.randint(0, NOISE_LEVEL, img_np.shape, dtype='uint8')
    img_np = np.clip(img_np + noise, 0, 255)
    return Image.fromarray(img_np.astype('uint8'))


def add_noise(img):
    # --- 1. Аффинные преобразования (небольшие искажения) ---
    width, height = img.size

    # Коэффициенты для аффинной матрицы (a, b, c, d, e, f)
    # x' = ax + by + c
    # y' = dx + ey + f

    # Небольшой сдвиг (shear) по горизонтали и вертикали
    shear_x = random.uniform(-0.05, 0.05)
    shear_y = random.uniform(-0.05, 0.05)

    # Небольшое изменение масштаба (zoom)
    zoom = random.uniform(0.98, 1.02)

    matrix = (
        zoom, shear_x, 0,
        shear_y, zoom, 0
    )

    # Применяем трансформацию (используем BICUBIC для качества)
    img = img.transform((width, height), Image.AFFINE, matrix, resample=Image.BICUBIC)

    # --- 2. Добавление шума ---
    img_np = np.array(img)
    noise = np.random.randint(0, NOISE_LEVEL, img_np.shape, dtype='uint8')
    img_np = np.clip(img_np + noise, 0, 255)

    return Image.fromarray(img_np.astype('uint8'))


def rotate_image(img, angle):
    # Используем expand=False, чтобы размер картинки не менялся
    return img.rotate(angle, resample=Image.BICUBIC, expand=False, fillcolor=(128, 128, 128))


def draw_text_center(img, text, box, font_path, max_font_size, color, stretch=True):
    """
    Рисует текст в центре бокса с растяжением.
    Текст не обрезается и фон сохраняется.
    """
    x1, y1, x2, y2 = box
    w = x2 - x1
    h = y2 - y1
    if w <= 0 or h <= 0:
        return

    try:
        font = ImageFont.truetype(font_path, max_font_size)
    except:
        font = ImageFont.load_default()

    # Сначала измеряем текст
    bbox = ImageDraw.Draw(img).textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]

    if stretch:
        padding = int(th * 0.55)
        # текст на прозрачном фоне
        text_img = Image.new("RGBA", (tw, th + padding), (0, 0, 0, 0))
        text_draw = ImageDraw.Draw(text_img)
        text_draw.text((0, padding // 2), text, font=font, fill=color)

        # Масштабируем под размер бокса
        text_img = text_img.resize((w, h), resample=Image.BICUBIC)

        # Вставляем на изображение с сохранением фона
        img.paste(text_img, (x1, y1), text_img)
    else:
        # Пропорциональное масштабирование как раньше
        font_size = max_font_size
        draw = ImageDraw.Draw(img)
        while font_size > 5:
            font = ImageFont.truetype(font_path, font_size)
            bbox = draw.textbbox((0, 0), text, font=font)
            tw = bbox[2] - bbox[0]
            th = bbox[3] - bbox[1]
            if tw <= w and th <= h:
                break
            font_size -= 2
        # Центрирование
        tx = x1 + (w - tw) // 2 - bbox[0]
        ty = y1 + (h - th) // 2 - bbox[1]
        draw.text((tx, ty), text, font=font, fill=color)


# =========================
# GUI
# =========================
class App:
    def __init__(self, root):
        self.root = root
        self.root.title("Plate Generator Pro")

        self.canvas = tk.Canvas(root, bg="gray")
        self.canvas.pack(fill="both", expand=True)

        btn_frame = tk.Frame(root)
        btn_frame.pack(pady=5)

        self.field_names = ["Field 1", "Field 2", "Field 3"]
        self.fields = []
        self.active_field = 0

        for i, name in enumerate(self.field_names):
            tk.Button(btn_frame, text=name, command=lambda idx=i: self.set_active(idx)).pack(side="left", padx=2)

        ctrl_frame = tk.Frame(root)
        ctrl_frame.pack(pady=5)

        tk.Button(ctrl_frame, text="Font Color", command=self.change_color).pack(side="left")
        tk.Button(ctrl_frame, text="Pipette", command=self.change_color_pipette).pack(side="left")
        tk.Button(ctrl_frame, text="Load BG", command=self.load_bg).pack(side="left")
        tk.Button(ctrl_frame, text="Load Font", command=self.load_font).pack(side="left")
        tk.Button(ctrl_frame, text="Save JSON", command=self.save_json).pack(side="left")
        tk.Button(ctrl_frame, text="Load JSON", command=self.load_json).pack(side="left")
        tk.Button(ctrl_frame, text="Load TXT", command=self.load_txt).pack(side="left")
        tk.Button(ctrl_frame, text="Load CSV", command=self.load_csv).pack(side="left")
        tk.Button(ctrl_frame, text="GENERATE", command=self.generate, bg="green", fg="white").pack(side="left", padx=10)

        for name in self.field_names:
            self.fields.append({
                "name": name,
                "box": [50, 50, 150, 150],
                "font_color": "#000000"
            })

        self.start_x = None
        self.start_y = None
        self.bg_image = None
        self.tk_img = None
        self.font_path = DEFAULT_FONT_PATH

        # Default данные для генерации
        self.sample_data = [
            {"Field 1": "A", "Field 2": "B", "Field 3": "777"},
            {"Field 1": "AB", "Field 2": "ZY", "Field 3": "123"},
            {"Field 1": "0", "Field 2": "001", "Field 3": "0000RU"}
        ]

        self.canvas.bind("<Button-1>", self.on_click)
        self.canvas.bind("<B1-Motion>", self.on_drag)

    def set_active(self, idx):
        self.active_field = idx
        self.show_image()

    def load_bg(self):
        path = filedialog.askopenfilename()
        if path:
            self.bg_image = Image.open(path).convert("RGB")
            w, h = self.bg_image.size
            self.canvas.config(width=w, height=h)
            self.show_image()

    def load_font(self):
        path = filedialog.askopenfilename(filetypes=[("TTF files", "*.ttf")])
        if path:
            self.font_path = path
            print(f"Font loaded: {path}")

    def show_image(self):
        if self.bg_image is None:
            return

        # Создаем временную копию для отображения интерфейса
        display_img = self.bg_image.copy()
        draw = ImageDraw.Draw(display_img)

        for i, f in enumerate(self.fields):
            is_active = (i == self.active_field)
            color = "red" if is_active else "blue"

            # Рисуем рамку
            box = f["box"]
            draw.rectangle(box, outline=color, width=2)

            # Подпись поля
            draw.text((box[0], box[1] - 15), f"{f['name']}", fill=color)

        self.tk_img = ImageTk.PhotoImage(display_img)
        self.canvas.create_image(0, 0, anchor="nw", image=self.tk_img)

    def change_color(self):
        color_code = colorchooser.askcolor(title="Choose font color")
        if color_code[1]:
            self.fields[self.active_field]["font_color"] = color_code[1]
            self.show_image()

    def change_color_pipette(self):
        """
        Реализация пипетки: наведите курсор на цвет и кликните ЛКМ.
        Цвет будет выбран без блокировки интерфейса.
        """
        messagebox.showinfo("Пипетка", "Наведи мышь на нужный цвет и кликни ЛКМ для выбора")

        # self.root.withdraw()  # Скрываем окно, чтобы не мешалось

        color_selected = []

        def on_click(x, y, button, pressed):
            if pressed and button == mouse.Button.left:
                rgb = pyautogui.screenshot().getpixel((x, y))
                hex_color = '#{:02x}{:02x}{:02x}'.format(*rgb)
                self.fields[self.active_field]["font_color"] = hex_color
                color_selected.append(hex_color)
                return False  # Останавливаем слушатель

        # Запускаем слушатель мыши
        with mouse.Listener(on_click=on_click) as listener:
            listener.join()  # ждем клика

        # self.root.deiconify()  # Показываем окно обратно
        self.show_image()
        return color_selected[0] if color_selected else None

    def on_click(self, event):
        self.start_x = event.x
        self.start_y = event.y

    def on_drag(self, event):
        if self.bg_image is None: return
        # Сразу нормализуем координаты при сохранении
        x1, y1 = self.start_x, self.start_y
        x2, y2 = event.x, event.y
        self.fields[self.active_field]["box"] = [min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)]
        self.show_image()

    def save_json(self):
        path = filedialog.asksaveasfilename(defaultextension=".json")
        if path:
            data = {"fields": self.fields, "font_path": self.font_path}
            with open(path, "w") as f:
                json.dump(data, f, indent=4)

    def load_json(self):
        path = filedialog.askopenfilename()
        if path:
            with open(path, "r") as f:
                data = json.load(f)
            self.fields = data["fields"]
            self.font_path = data.get("font_path", DEFAULT_FONT_PATH)
            self.show_image()

    def load_csv(self):
        path = filedialog.askopenfilename(filetypes=[("CSV files", "*.csv")])
        if not path:
            return
        try:
            df = pd.read_csv(path, encoding='utf-8')
            df = df[[col for col in self.field_names if col in df.columns]]
            if df.empty:
                messagebox.showwarning("Empty CSV", "CSV file is empty or missing required columns")
                return
            self.sample_data = df.to_dict(orient="records")
            messagebox.showinfo("CSV Loaded", f"Loaded {len(self.sample_data)} entries from CSV")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load CSV:\n{e}")

    def load_txt(self):
        path = filedialog.askopenfilename(filetypes=[("Text files", "*.txt")])
        if not path:
            return
        try:
            data = []
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    parts = line.split(",")
                    if len(parts) != len(self.field_names):
                        continue  # Пропускаем строки с неправильным количеством колонок
                    entry = {self.field_names[i]: parts[i] for i in range(len(self.field_names))}
                    data.append(entry)
            if data:
                self.sample_data = data
                messagebox.showinfo("TXT Loaded", f"Loaded {len(data)} entries from TXT")
            else:
                messagebox.showwarning("Empty TXT", "TXT file is empty or invalid")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load TXT:\n{e}")

    def generate(self):
        if self.bg_image is None:
            messagebox.showwarning("Warning", "Load background image first!")
            return

        # Создаем новую папку с меткой времени
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        new_output_dir = OUTPUT_DIR / f"run_{timestamp}"
        new_output_dir.mkdir(parents=True, exist_ok=True)

        # Список для хранения строк будущего текстового файла
        report_lines = []

        for i, sample in enumerate(self.sample_data):
            # 1. Формируем "чистое" значение из всех полей для имени файла
            # Собираем все значения полей в одну строку
            combined_value = "".join(str(sample.get(name, "")) for name in self.field_names)
            # Удаляем запятые, если они были в исходных данных
            clean_name = combined_value.replace(",", "")

            # Имя изображения согласно вашему требованию: image_{номер}.jpg
            image_filename = f"synth_image_{clean_name}_{uuid.uuid4()}.jpg"

            img = self.bg_image.copy()

            for field in self.fields:
                name = field["name"]
                if name in sample:
                    color = field.get("font_color", "#000000")
                    # Рисуем текст
                    draw_text_center(img, str(sample[name]), field["box"], self.font_path, 300, color)

            # Эффекты
            angle = random.uniform(*ANGLE_RANGE)
            img = rotate_image(img, angle)
            # Можно раскоментировать, если нужен простой noise и закоментировать add_noise
            # img = add_simple_noise(img)
            # Noise c Аффинными преобразованиями
            img = add_noise(img)

            # ==========================================
            # ДОБАВЛЕНО: DOWNSCALE ДО 100px ПО ВЫСОТЕ
            # ==========================================
            target_h = 100
            w, h = img.size
            aspect_ratio = w / h
            target_w = int(target_h * aspect_ratio)

            # Используем Resampling.LANCZOS для наилучшего качества при уменьшении
            img = img.resize((target_w, target_h), resample=Image.Resampling.LANCZOS)
            # ==========================================

            # Сохраняем изображение с новым именем
            out_path = new_output_dir / image_filename
            img.save(out_path, quality=95)

            # 2. Формируем строку для TXT файла: имя_файла,значение,99
            report_lines.append(f"{image_filename},{clean_name},99")

        # 3. Сохраняем итоговый TXT файл в ту же папку
        txt_report_path = new_output_dir / "labels_report.txt"
        with open(txt_report_path, "w", encoding="utf-8") as f:
            f.write("\n".join(report_lines))

        messagebox.showinfo("Success", f"Generated {len(self.sample_data)} images and report in {new_output_dir}")


if __name__ == "__main__":
    root = tk.Tk()
    app = App(root)
    root.mainloop()
