import blynklib as BlynkLib
import tkinter as tk
from tkinter import scrolledtext
from tkinter import ttk
from tkinter import messagebox
from ttkthemes import ThemedTk
import openai
import threading
import time
from EmulatorGUI import GPIO
from DHT22 import readSensor
from pnhLCD1602 import LCD1602
from SoilMoistureSensor import readSensorSoil
import configparser
from datetime import datetime
import logging
from PIL import Image, ImageTk

BLYNK_TEMPLATE_NAME = "AppPI"
BLYNK_AUTH_TOKEN = ""

blynk = BlynkLib.Blynk(BLYNK_AUTH_TOKEN)

# Cấu hình OpenAI API Key
openai.api_key = ""  # Thay bằng API Key của bạn

# Cấu hình logging
logging.basicConfig(filename='system.log', level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Khai báo các chân GPIO
PUMP_PIN = 17
FAN_PIN = 25
LED_PIN = 18
ALERT_PIN = 12  # Cảnh báo (buzzer hoặc đèn LED)
SOIL_SENSOR_PIN = 27  # Cảm biến độ ẩm đất
BUTTON_MODE = 5  # Nút chuyển chế độ
BUTTON_FAN = 6  # Nút điều khiển quạt
BUTTON_PUMP = 13  # Nút điều khiển bơm
BUTTON_LED = 26  # Nút điều khiển đèn LED
DHT_PIN = 4  # Cảm biến DHT22

# Thiết lập GPIO
GPIO.setmode(GPIO.BCM)

def setup_gpio():
    GPIO.setup(PUMP_PIN, GPIO.OUT)
    GPIO.setup(FAN_PIN, GPIO.OUT)
    GPIO.setup(LED_PIN, GPIO.OUT)
    GPIO.setup(ALERT_PIN, GPIO.OUT)
    GPIO.setup(SOIL_SENSOR_PIN, GPIO.IN)
    GPIO.setup(BUTTON_MODE, GPIO.IN, pull_up_down=GPIO.PUD_UP)
    GPIO.setup(BUTTON_FAN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
    GPIO.setup(BUTTON_PUMP, GPIO.IN, pull_up_down=GPIO.PUD_UP)
    GPIO.setup(BUTTON_LED, GPIO.IN, pull_up_down=GPIO.PUD_UP)

setup_gpio()

# Khởi tạo LCD I2C
lcd = LCD1602(width=500, height=100)

# Hiển thị thông báo chào mừng
lcd.clear()
lcd.write_string('System Start...')
print('System Start...')
logging.info("System Start")
time.sleep(1)
lcd.clear()

# Đọc file cấu hình
config = configparser.ConfigParser()
config.read('config.ini')

lower_threshold = int(config['Thresholds']['lower_threshold'])
temperature_threshold = int(config['Thresholds']['temperature_threshold'])
led_start_hour = int(config['LED']['start_hour'])
led_end_hour = int(config['LED']['end_hour'])

# Khởi tạo trạng thái
mode_auto = False
pump_status = False
fan_status = False
led_status = False
alert_active = False
alert_state = False
last_alert_toggle = time.time()

# Liên kết các Virtual Pin của Blynk để điều chỉnh từ app
@blynk.handle_event('write V3')  # Ngưỡng nhiệt độ
def v3_write_handler(pin, value):
    global temperature_threshold
    temperature_threshold = int(value[0])
    print(f"Ngưỡng nhiệt độ mới: {temperature_threshold}C")

@blynk.handle_event('write V2')  # Ngưỡng độ ẩm đất
def v2_write_handler(pin, value):
    global lower_threshold
    lower_threshold = int(value[0])
    print(f"Ngưỡng độ ẩm đất mới: {lower_threshold}%")

@blynk.handle_event('write V1')  # Chế độ Thủ công/Tự động
def v1_write_handler(pin, value):
    global mode_auto
    mode_auto = int(value[0]) == 1
    print(f"Chế độ {'Tự động' if mode_auto else 'Thủ công'}")

@blynk.handle_event('write V0')  # Tắt/Bật quạt thủ công
def v0_write_handler(pin, value):
    global fan_status
    fan_status = int(value[0]) == 1
    GPIO.output(FAN_PIN, fan_status)
    print(f"Quạt {'bật' if fan_status else 'tắt'} (thủ công)")

@blynk.handle_event('write V4')  # Tắt/Bật đèn thủ công
def v4_write_handler(pin, value):
    global led_status
    led_status = int(value[0]) == 1
    GPIO.output(LED_PIN, led_status)
    print(f"Đèn {'bật' if led_status else 'tắt'} (thủ công)")

# Khởi tạo thời gian cập nhật sensor và LCD
next_update_time = time.time()
update_interval = 5  # Mặc định 5 giây

# Sử dụng ThemedTk để áp dụng theme
root = ThemedTk(theme="breeze")
root.title("Hệ thống chăm sóc cây trồng")

# Điều chỉnh kích thước cửa sổ và cho phép thay đổi kích thước
root.geometry("850x600")
root.resizable(True, True)

# Tạo Canvas và Scrollbar để hỗ trợ cuộn nội dung
main_canvas = tk.Canvas(root)
main_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

scrollbar = ttk.Scrollbar(root, orient=tk.VERTICAL, command=main_canvas.yview)
scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

main_canvas.configure(yscrollcommand=scrollbar.set)

# Tạo một Frame chứa toàn bộ nội dung
content_frame = ttk.Frame(main_canvas)
main_canvas.create_window((0, 0), window=content_frame, anchor="nw")

# Hàm để cập nhật kích thước Canvas khi nội dung thay đổi
def on_frame_configure(event):
    main_canvas.configure(scrollregion=main_canvas.bbox("all"))

content_frame.bind("<Configure>", on_frame_configure)

# Tạo style cho các widget
style = ttk.Style(root)
style.configure('TLabel', font=("Helvetica", 12, 'bold'))
style.configure('Header.TLabel', font=("Helvetica", 16, 'bold'))
style.configure('TButton', font=("Helvetica", 12, 'bold'))
style.configure('On.TButton', background='green', foreground='green')
style.configure('Off.TButton', background='red', foreground='red')
style.configure('TEntry', font=("Helvetica", 12))
style.configure('TText', font=("Helvetica", 12))

# Tạo tiêu đề cho ứng dụng
title_label = tk.Label(content_frame, text="Hệ thống chăm sóc cây trồng thông minh", font=("Helvetica", 16, 'bold'))
title_label.pack(pady=10)


# Tạo các biến tkinter
temperature_var = tk.StringVar()
humidity_var = tk.StringVar()
soil_moisture_var = tk.StringVar()
fan_status_var = tk.StringVar()
pump_status_var = tk.StringVar()
led_status_var = tk.StringVar()
mode_var = tk.StringVar()

# Thêm các biến StringVar để hiển thị giá trị ngưỡng
temperature_threshold_display = tk.StringVar(value=str(temperature_threshold))
lower_threshold_display = tk.StringVar(value=str(lower_threshold))

# Khởi tạo biến cảm biến toàn cục
temperature = 0.0
humidity = 0.0
soil_moisture = 0.0

# Hàm cập nhật giao diện
def update_gui():
    temperature_var.set(f"Nhiệt độ: {temperature:.1f}°C")
    humidity_var.set(f"Độ ẩm không khí: {humidity:.1f}%")
    soil_moisture_var.set(f"Độ ẩm đất: {soil_moisture:.1f}%")
    fan_status_var.set(f"Quạt: {'Bật' if fan_status else 'Tắt'}")
    pump_status_var.set(f"Bơm: {'Bật' if pump_status else 'Tắt'}")
    led_status_var.set(f"Đèn LED: {'Bật' if led_status else 'Tắt'}")
    mode_var.set(f"Chế độ: {'Tự động' if mode_auto else 'Thủ công'}")
    
    # Cập nhật trạng thái nút
    update_button_states()

# Hàm cập nhật trạng thái nút
def update_button_states():
    if fan_status:
        fan_button.config(text="Tắt Quạt", style='On.TButton')
    else:
        fan_button.config(text="Bật Quạt", style='Off.TButton')
    
    if pump_status:
        pump_button.config(text="Tắt Bơm", style='On.TButton')
    else:
        pump_button.config(text="Bật Bơm", style='Off.TButton')
    
    if led_status:
        led_button.config(text="Tắt Đèn", style='On.TButton')
    else:
        led_button.config(text="Bật Đèn", style='Off.TButton')
    
    if mode_auto:
        mode_button.config(text="Chuyển sang Thủ công", style='On.TButton')
    else:
        mode_button.config(text="Chuyển sang Tự động", style='Off.TButton')

# Hàm cập nhật LCD và in ra terminal
def update_lcd_and_terminal(alert_message=""):
    lcd.clear()
    lcd.set_cursor(0, 0)
    lcd.write_string(f"T:{temperature:.0f}C H:{humidity:.0f}% S:{soil_moisture:.0f}%")
    lcd.set_cursor(1, 0)
    lcd.write_string(f"F:{'T' if fan_status else 'F'} P:{'T' if pump_status else 'F'} L:{'T' if led_status else 'F'}")

    print(f"Temperature:{temperature:.0f}C Humidity:{humidity:.0f}% Soil_moisture:{soil_moisture:.0f}%")
    print(f"Fan: {'ON' if fan_status else 'OFF'} Pump: {'ON' if pump_status else 'OFF'} Led: {'ON' if led_status else 'OFF'}")
    if alert_message:
        print(alert_message)
    print("------------------------------")

# Hàm gọi API OpenAI
def call_openai_api(question):
    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": question}]
        )
        answer = response['choices'][0]['message']['content']
        return answer
    except Exception as e:
        return f"Đã xảy ra lỗi: {e}"

# Hàm xử lý khi nhấn nút Gửi
def send_question():
    question = question_entry.get("1.0", tk.END).strip()
    if question:
        # Hiển thị trạng thái "Đang trả lời..."
        answer_display.delete("1.0", tk.END)
        answer_display.insert(tk.END, "Đang trả lời...\n")
        answer_display.update_idletasks()

        # Gọi API trong một thread riêng
        def process_api_call():
            answer = call_openai_api(question)
            answer_display.delete("1.0", tk.END)
            answer_display.insert(tk.END, answer)

        thread = threading.Thread(target=process_api_call)
        thread.start()
    else:
        messagebox.showwarning("Cảnh báo", "Vui lòng nhập câu hỏi!")

# Tạo frame cho các nút điều khiển
control_frame = ttk.LabelFrame(content_frame, text="Điều khiển")
control_frame.pack(pady=10, fill='x', padx=10)

def toggle_mode():
    global mode_auto
    mode_auto = not mode_auto
    update_gui()
    print(f"Mode changed to {'Automatic' if mode_auto else 'Manual'}")
    logging.info(f"Mode changed to {'Automatic' if mode_auto else 'Manual'}")

def toggle_fan():
    global fan_status
    fan_status = not fan_status
    GPIO.output(FAN_PIN, fan_status)
    update_gui()
    print(f"Fan {'ON' if fan_status else 'OFF'} manually.")
    logging.info(f"Fan {'ON' if fan_status else 'OFF'} manually.")

def toggle_pump():
    global pump_status
    pump_status = not pump_status
    GPIO.output(PUMP_PIN, pump_status)
    update_gui()
    print(f"Pump {'ON' if pump_status else 'OFF'} manually.")
    logging.info(f"Pump {'ON' if pump_status else 'OFF'} manually.")

def toggle_led():
    global led_status
    led_status = not led_status
    GPIO.output(LED_PIN, led_status)
    update_gui()
    print(f"LED {'ON' if led_status else 'OFF'} manually.")
    logging.info(f"LED {'ON' if led_status else 'OFF'} manually.")

# Tạo các nút điều khiển với hiệu ứng
mode_button = ttk.Button(control_frame, text="", command=toggle_mode)
mode_button.grid(row=0, column=0, padx=10, pady=5)

fan_button = ttk.Button(control_frame, text="", command=toggle_fan)
fan_button.grid(row=0, column=1, padx=10, pady=5)

pump_button = ttk.Button(control_frame, text="", command=toggle_pump)
pump_button.grid(row=0, column=2, padx=10, pady=5)

led_button = ttk.Button(control_frame, text="", command=toggle_led)
led_button.grid(row=0, column=3, padx=10, pady=5)

# Cập nhật trạng thái nút ban đầu
update_button_states()

# Thêm thanh trượt cho ngưỡng nhiệt độ và độ ẩm đất
slider_frame = tk.LabelFrame(content_frame, text="Thiết lập ngưỡng")
slider_frame.pack(pady=10, fill='x', padx=10)

# Hàm cập nhật giá trị ngưỡng khi thanh trượt thay đổi
def on_temperature_scale_change(value):
    global temperature_threshold
    temperature_threshold = int(float(value))
    temperature_threshold_display.set(str(temperature_threshold))
    print(f"Temperature threshold updated to {temperature_threshold}")

def on_moisture_scale_change(value):
    global lower_threshold
    lower_threshold = int(float(value))
    lower_threshold_display.set(str(lower_threshold))
    print(f"Moisture threshold updated to {lower_threshold}")

# Thanh trượt ngưỡng nhiệt độ với ticks
tk.Label(slider_frame, text="Ngưỡng nhiệt độ (°C):").grid(row=0, column=0, padx=10, pady=5)
temperature_scale = tk.Scale(slider_frame, from_=0, to=50, orient='horizontal', command=on_temperature_scale_change, tickinterval=5, length=300)
temperature_scale.set(temperature_threshold)
temperature_scale.grid(row=0, column=1, padx=10, pady=5)
tk.Label(slider_frame, textvariable=temperature_threshold_display).grid(row=0, column=2, padx=10, pady=5)

# Thanh trượt ngưỡng độ ẩm đất với ticks
tk.Label(slider_frame, text="Ngưỡng độ ẩm đất (%):").grid(row=1, column=0, padx=10, pady=5)
moisture_scale = tk.Scale(slider_frame, from_=0, to=100, orient='horizontal', command=on_moisture_scale_change, tickinterval=10, length=300)
moisture_scale.set(lower_threshold)
moisture_scale.grid(row=1, column=1, padx=10, pady=5)
tk.Label(slider_frame, textvariable=lower_threshold_display).grid(row=1, column=2, padx=10, pady=5)

# Tạo frame cho phần hỏi đáp
qa_frame = ttk.LabelFrame(content_frame, text="Trợ lý ảo")
qa_frame.pack(pady=10, fill='both', expand=True, padx=10)

# Thêm tiêu đề và mô tả cho phần hỏi đáp

qa_description = ttk.Label(qa_frame, text="Nhập câu hỏi của bạn vào bên dưới và nhận câu trả lời từ trợ lý ảo.")
qa_description.pack(pady=5)

# Tạo frame chứa ô nhập câu hỏi và nút gửi
question_frame = ttk.Frame(qa_frame)
question_frame.pack(pady=5, fill='x')

# Tạo ô nhập câu hỏi với thanh cuộn
question_entry = scrolledtext.ScrolledText(question_frame, height=5, font=("Helvetica", 12))
question_entry.pack(side=tk.LEFT, fill='both', expand=True)

# Tạo nút gửi với biểu tượng
send_image = Image.open("send_icon.png")
send_icon = ImageTk.PhotoImage(send_image)
send_button = tk.Button(question_frame, text="Gửi", image=None, command=send_question)
send_button.image = send_icon  # Giữ tham chiếu tới hình ảnh
send_button.pack(side=tk.RIGHT, padx=5, pady=5)


# Tạo khu vực hiển thị câu trả lời với thanh cuộn
answer_display = scrolledtext.ScrolledText(qa_frame, height=10, font=("Helvetica", 12))
answer_display.pack(pady=10, fill='both', expand=True)

# Hàm chạy vòng lặp chính
def main_loop():
    global temperature, humidity, soil_moisture, fan_status, pump_status, led_status
    global alert_active, alert_state, last_alert_toggle, next_update_time
    global temperature_threshold, lower_threshold

    current_time = time.time()

    # Kiểm tra trạng thái fan và pump để xác định khoảng thời gian cập nhật
    if fan_status or pump_status:
        desired_interval = 1  # 1 giây khi fan hoặc pump đang hoạt động
    else:
        desired_interval = 5  # 5 giây khi cả fan và pump đều tắt

    # Nếu đã đến thời điểm cập nhật
    if current_time >= next_update_time:
        # Đọc cảm biến
        temperature, humidity = readSensor(DHT_PIN)
        soil_moisture = readSensorSoil(SOIL_SENSOR_PIN)

        alert_message = ""  # Thông điệp cảnh báo để hiển thị trên LCD và terminal

        # Chế độ tự động
        if mode_auto:
            # Điều khiển bơm
            if soil_moisture < lower_threshold:
                if not pump_status:
                    pump_status = True
                    GPIO.output(PUMP_PIN, GPIO.HIGH)
                    update_gui()
                    print("Pump turned ON automatically.")
                    logging.info("Pump turned ON automatically.")
            else:
                if pump_status:
                    pump_status = False
                    GPIO.output(PUMP_PIN, GPIO.LOW)
                    update_gui()
                    print("Pump turned OFF automatically.")
                    logging.info("Pump turned OFF automatically.")

            # Điều khiển quạt
            if temperature > temperature_threshold:
                if not fan_status:
                    fan_status = True
                    GPIO.output(FAN_PIN, GPIO.HIGH)
                    update_gui()
                    print("Fan turned ON automatically.")
                    logging.info("Fan turned ON automatically.")
            else:
                if fan_status:
                    fan_status = False
                    GPIO.output(FAN_PIN, GPIO.LOW)
                    update_gui()
                    print("Fan turned OFF automatically.")
                    logging.info("Fan turned OFF automatically.")

            # Điều khiển đèn LED theo giờ
            current_hour = datetime.now().hour
            if (led_start_hour <= current_hour < 24) or (0 <= current_hour < led_end_hour):
                if not led_status:
                    led_status = True
                    GPIO.output(LED_PIN, GPIO.HIGH)
                    update_gui()
                    print("LED turned ON automatically.")
                    logging.info("LED turned ON automatically.")
            else:
                if led_status:
                    led_status = False
                    GPIO.output(LED_PIN, GPIO.LOW)
                    update_gui()
                    print("LED turned OFF automatically.")
                    logging.info("LED turned OFF automatically.")

        # Cập nhật giao diện với dữ liệu cảm biến
        update_gui()

        # Kiểm tra cảnh báo
        if (fan_status and temperature < temperature_threshold):
            alert_active = True
            alert_message = f"Warn: OFF Fan! Temp:{temperature:.0f}C"
            logging.warning(f"Warning: Fan OFF while Temperature is {temperature:.0f}C")
        elif (pump_status and soil_moisture > lower_threshold):
            alert_active = True
            alert_message = f"Warn: OFF Pump! Soil:{soil_moisture:.0f}%"
            logging.warning(f"Warning: Pump OFF while Soil Moisture is {soil_moisture:.0f}%")
        else:
            alert_active = False

        # Xử lý nháy cảnh báo
        if alert_active:
            if current_time - last_alert_toggle >= 0.5:
                alert_state = not alert_state
                GPIO.output(ALERT_PIN, alert_state)
                last_alert_toggle = current_time
        else:
            GPIO.output(ALERT_PIN, GPIO.LOW)

        # Cập nhật LCD và in ra terminal
        update_lcd_and_terminal(alert_message)

        # In ra giá trị ngưỡng hiện tại để kiểm tra
        print(f"Current thresholds: Temperature {temperature_threshold}, Moisture {lower_threshold}")

        # Cập nhật thời gian tiếp theo để cập nhật
        next_update_time = current_time + desired_interval

    # Lên lịch gọi lại main_loop sau 100ms
    root.after(100, main_loop)

# Gọi hàm main_loop lần đầu tiên
main_loop()

# Chạy vòng lặp GUI
root.mainloop()
