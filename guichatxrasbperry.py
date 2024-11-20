import tkinter as tk
from tkinter import scrolledtext
from tkinter import ttk
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
import queue

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

# Khởi tạo thời gian cập nhật sensor và LCD
next_update_time = time.time()
update_interval = 5  # Mặc định 5 giây

# Khởi tạo trạng thái trước đó của các nút nhấn
prev_button_mode = GPIO.input(BUTTON_MODE)
prev_button_fan = GPIO.input(BUTTON_FAN)
prev_button_pump = GPIO.input(BUTTON_PUMP)
prev_button_led = GPIO.input(BUTTON_LED)

# Thời gian debounce cho từng nút
debounce_time = 0.3  # 300 ms
last_toggle_mode = time.time()
last_toggle_fan = time.time()
last_toggle_pump = time.time()
last_toggle_led = time.time()

# Sử dụng ThemedTk để áp dụng theme
root = ThemedTk(theme="breeze")
root.title("Hệ thống chăm sóc cây trồng")
root.geometry("800x600")

# Tạo style cho các widget
style = ttk.Style(root)
style.configure('TLabel', font=("Helvetica", 12))
style.configure('TButton', font=("Helvetica", 12, 'bold'))
style.configure('TEntry', font=("Helvetica", 12))
style.configure('TText', font=("Helvetica", 12))

# Tạo các biến tkinter
temperature_var = tk.StringVar()
humidity_var = tk.StringVar()
soil_moisture_var = tk.StringVar()
fan_status_var = tk.StringVar()
pump_status_var = tk.StringVar()
led_status_var = tk.StringVar()
mode_var = tk.StringVar()

# Thêm các biến IntVar cho ngưỡng
temperature_threshold_var = tk.IntVar(value=temperature_threshold)
lower_threshold_var = tk.IntVar(value=lower_threshold)

# Khởi tạo biến cảm biến toàn cục
temperature = 0.0
humidity = 0.0
soil_moisture = 0.0

# Hàm cập nhật giao diện
def update_gui():
    temperature_var.set(f"Nhiệt độ: {temperature:.1f}°C")
    humidity_var.set(f"Độ ẩm: {humidity:.1f}%")
    soil_moisture_var.set(f"Độ ẩm đất: {soil_moisture:.1f}%")
    fan_status_var.set(f"Quạt: {'Bật' if fan_status else 'Tắt'}")
    pump_status_var.set(f"Bơm: {'Bật' if pump_status else 'Tắt'}")
    led_status_var.set(f"Đèn LED: {'Bật' if led_status else 'Tắt'}")
    mode_var.set(f"Chế độ: {'Tự động' if mode_auto else 'Thủ công'}")
    

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
        answer_display.delete("1.0", tk.END)
        answer_display.insert(tk.END, "Vui lòng nhập câu hỏi!")

# Tạo các widget giao diện
sensor_frame = ttk.Frame(root)
sensor_frame.pack(pady=10)

ttk.Label(sensor_frame, textvariable=temperature_var).grid(row=0, column=0, padx=10)
ttk.Label(sensor_frame, textvariable=humidity_var).grid(row=0, column=1, padx=10)
ttk.Label(sensor_frame, textvariable=soil_moisture_var).grid(row=0, column=2, padx=10)

status_frame = ttk.Frame(root)
status_frame.pack(pady=10)

ttk.Label(status_frame, textvariable=fan_status_var).grid(row=0, column=0, padx=10)
ttk.Label(status_frame, textvariable=pump_status_var).grid(row=0, column=1, padx=10)
ttk.Label(status_frame, textvariable=led_status_var).grid(row=0, column=2, padx=10)
ttk.Label(status_frame, textvariable=mode_var).grid(row=0, column=3, padx=10)

control_frame = ttk.Frame(root)
control_frame.pack(pady=10)

def toggle_mode():
    global mode_auto
    mode_auto = not mode_auto
    mode_var.set(f"Chế độ: {'Tự động' if mode_auto else 'Thủ công'}")
    print(f"Mode changed to {'Automatic' if mode_auto else 'Manual'}")
    logging.info(f"Mode changed to {'Automatic' if mode_auto else 'Manual'}")

def toggle_fan():
    global fan_status
    fan_status = not fan_status
    GPIO.output(FAN_PIN, fan_status)
    fan_status_var.set(f"Quạt: {'Bật' if fan_status else 'Tắt'}")
    print(f"Fan {'ON' if fan_status else 'OFF'} manually.")
    logging.info(f"Fan {'ON' if fan_status else 'OFF'} manually.")

def toggle_pump():
    global pump_status
    pump_status = not pump_status
    GPIO.output(PUMP_PIN, pump_status)
    pump_status_var.set(f"Bơm: {'Bật' if pump_status else 'Tắt'}")
    print(f"Pump {'ON' if pump_status else 'OFF'} manually.")
    logging.info(f"Pump {'ON' if pump_status else 'OFF'} manually.")

def toggle_led():
    global led_status
    led_status = not led_status
    GPIO.output(LED_PIN, led_status)
    led_status_var.set(f"Đèn LED: {'Bật' if led_status else 'Tắt'}")
    print(f"LED {'ON' if led_status else 'OFF'} manually.")
    logging.info(f"LED {'ON' if led_status else 'OFF'} manually.")

ttk.Button(control_frame, text="Chuyển chế độ", command=toggle_mode).grid(row=0, column=0, padx=10)
ttk.Button(control_frame, text="Bật/Tắt Quạt", command=toggle_fan).grid(row=0, column=1, padx=10)
ttk.Button(control_frame, text="Bật/Tắt Bơm", command=toggle_pump).grid(row=0, column=2, padx=10)
ttk.Button(control_frame, text="Bật/Tắt Đèn", command=toggle_led).grid(row=0, column=3, padx=10)

# Thêm thanh trượt cho ngưỡng nhiệt độ và độ ẩm đất
slider_frame = ttk.Frame(root)
slider_frame.pack(pady=10)

# Thanh trượt ngưỡng nhiệt độ
ttk.Label(slider_frame, text="Ngưỡng nhiệt độ (°C):").grid(row=0, column=0, padx=10)
temperature_scale = ttk.Scale(slider_frame, from_=0, to=100, orient='horizontal', variable=temperature_threshold_var)
temperature_scale.grid(row=0, column=1, padx=10)
ttk.Label(slider_frame, textvariable=temperature_threshold_var).grid(row=0, column=2, padx=10)

# Thanh trượt ngưỡng độ ẩm đất
ttk.Label(slider_frame, text="Ngưỡng độ ẩm đất (%):").grid(row=1, column=0, padx=10)
moisture_scale = ttk.Scale(slider_frame, from_=0, to=100, orient='horizontal', variable=lower_threshold_var)
moisture_scale.grid(row=1, column=1, padx=10)
ttk.Label(slider_frame, textvariable=lower_threshold_var).grid(row=1, column=2, padx=10)

# Tạo hàng đợi để truyền giá trị ngưỡng
thresholds_queue = queue.Queue()

def update_thresholds():
    temperature_value = temperature_threshold_var.get()
    lower_value = lower_threshold_var.get()
    thresholds_queue.put((temperature_value, lower_value))
    root.after(100, update_thresholds)  # Lặp lại sau mỗi 100ms

# Bắt đầu cập nhật giá trị ngưỡng
update_thresholds()

# Tạo ô nhập câu hỏi
question_label = ttk.Label(root, text="Nhập câu hỏi của bạn:")
question_label.pack(pady=5)

question_entry = tk.Text(root, height=5, width=70, font=("Helvetica", 12))
question_entry.pack(pady=5)

# Tạo nút Gửi
send_button = ttk.Button(root, text="Gửi", command=send_question)
send_button.pack(pady=5)

# Tạo khu vực hiển thị câu trả lời với thanh cuộn
answer_display = scrolledtext.ScrolledText(root, height=10, width=80, font=("Helvetica", 12))
answer_display.pack(pady=10)

# Hàm chạy vòng lặp chính trong thread riêng
def main_loop():
    global temperature, humidity, soil_moisture, fan_status, pump_status, led_status
    global alert_active, alert_state, last_alert_toggle, next_update_time
    global temperature_threshold, lower_threshold

    while True:
        try:
            current_time = time.time()

            # Lấy giá trị ngưỡng từ hàng đợi nếu có
            try:
                while not thresholds_queue.empty():
                    temperature_threshold, lower_threshold = thresholds_queue.get_nowait()
            except queue.Empty:
                pass


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
                            pump_status_var.set(f"Bơm: {'Bật' if pump_status else 'Tắt'}")
                            print("Pump turned ON automatically.")
                            logging.info("Pump turned ON automatically.")
                    else:
                        if pump_status:
                            pump_status = False
                            GPIO.output(PUMP_PIN, GPIO.LOW)
                            pump_status_var.set(f"Bơm: {'Bật' if pump_status else 'Tắt'}")
                            print("Pump turned OFF automatically.")
                            logging.info("Pump turned OFF automatically.")

                    # Điều khiển quạt
                    if temperature > temperature_threshold:
                        if not fan_status:
                            fan_status = True
                            GPIO.output(FAN_PIN, GPIO.HIGH)
                            fan_status_var.set(f"Quạt: {'Bật' if fan_status else 'Tắt'}")
                            print("Fan turned ON automatically.")
                            logging.info("Fan turned ON automatically.")
                    else:
                        if fan_status:
                            fan_status = False
                            GPIO.output(FAN_PIN, GPIO.LOW)
                            fan_status_var.set(f"Quạt: {'Bật' if fan_status else 'Tắt'}")
                            print("Fan turned OFF automatically.")
                            logging.info("Fan turned OFF automatically.")

                    # Điều khiển đèn LED theo giờ
                    current_hour = datetime.now().hour
                    if (led_start_hour <= current_hour < 24) or (0 <= current_hour < led_end_hour):
                        if not led_status:
                            led_status = True
                            GPIO.output(LED_PIN, GPIO.HIGH)
                            led_status_var.set(f"Đèn LED: {'Bật' if led_status else 'Tắt'}")
                            print("LED turned ON automatically.")
                            logging.info("LED turned ON automatically.")
                    else:
                        if led_status:
                            led_status = False
                            GPIO.output(LED_PIN, GPIO.LOW)
                            led_status_var.set(f"Đèn LED: {'Bật' if led_status else 'Tắt'}")
                            print("LED turned OFF automatically.")
                            logging.info("LED turned OFF automatically.")

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

                # Cập nhật giao diện
                update_gui()

                # Cập nhật LCD và in ra terminal
                update_lcd_and_terminal(alert_message)

                # Cập nhật thời gian tiếp theo để cập nhật
                next_update_time = current_time + desired_interval

            # Thời gian ngắn để tránh vòng lặp nhanh quá
            time.sleep(0.1)

        except KeyboardInterrupt:
            print("System Stop...")
            logging.info("System Stop")
            break
        except Exception as e:
            logging.error(f"Error: {e}")

    GPIO.cleanup()
    logging.info("GPIO cleanup and system stopped.")

# Chạy vòng lặp chính trong thread riêng
threading.Thread(target=main_loop, daemon=True).start()

# Chạy vòng lặp GUI
root.mainloop()
