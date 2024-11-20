import blynklib as BlynkLib
import time
from EmulatorGUI import GPIO
from DHT22 import readSensor
from pnhLCD1602 import LCD1602
from SoilMoistureSensor import readSensorSoil
import configparser
from datetime import datetime
import logging

BLYNK_TEMPLATE_NAME = "AppPI"
BLYNK_AUTH_TOKEN = "dwbrmY-tAp0WBFAFZiIPpM6fuP-aCL9i"

blynk = BlynkLib.Blynk(BLYNK_AUTH_TOKEN)

# Cấu hình logging
logging.basicConfig(filename='system.log', level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')

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

# Hiển thị chế độ ban đầu
lcd.write_string('Manual mode...')
print('Manual mode...\n')
logging.info("Mode set to Manual")
time.sleep(1)
lcd.clear()

def update_lcd(temperature, humidity, soil_moisture, fan_status, pump_status, led_status, alert_message=""):
    lcd.clear()
    lcd.set_cursor(0, 0)
    lcd.write_string(f"T:{temperature:.0f}C H:{humidity:.0f}% S:{soil_moisture:.0f}%")
    print(f"Temperature:{temperature:.0f}C Humidity:{humidity:.0f}% Soil_moisture:{soil_moisture:.0f}%")
    
    lcd.set_cursor(1, 0)
    if alert_message:
        lcd.write_string(alert_message)
    else:
        lcd.write_string(f"F:{'T' if fan_status else 'F'} P:{'T' if pump_status else 'F'} L:{'T' if led_status else 'F'}")
    if alert_message:
        print(f"{alert_message}\n")
    else:
        print(f"Fan:{'ON' if fan_status else 'OFF'} Pump:{'ON' if pump_status else 'OFF'} Led:{'ON' if led_status else 'OFF'}\n")
    # Không cần sleep ở đây để tránh làm chậm vòng lặp chính
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

while True:
    try:
        current_time = time.time()
        
        # Kiểm tra nút chuyển chế độ
        button_mode = GPIO.input(BUTTON_MODE)
        if button_mode == GPIO.LOW and prev_button_mode == GPIO.HIGH:
            if current_time - last_toggle_mode >= debounce_time:
                mode_auto = not mode_auto
                lcd.clear()
                lcd.write_string(f"{'Automatic' if mode_auto else 'Manual'} mode")
                print("Mode changed!\n")
                logging.info(f"Mode changed to {'Automatic' if mode_auto else 'Manual'}")
                last_toggle_mode = current_time
        prev_button_mode = button_mode
        
        # Kiểm tra nút điều khiển quạt
        button_fan = GPIO.input(BUTTON_FAN)
        if button_fan == GPIO.LOW and prev_button_fan == GPIO.HIGH:
            if current_time - last_toggle_fan >= debounce_time:
                fan_status = not fan_status
                GPIO.output(FAN_PIN, fan_status)
                print(f"Fan {'ON' if fan_status else 'OFF'} manually.")
                logging.info(f"Fan {'ON' if fan_status else 'OFF'} manually.")
                last_toggle_fan = current_time
        prev_button_fan = button_fan
        
        # Kiểm tra nút điều khiển bơm
        button_pump = GPIO.input(BUTTON_PUMP)
        if button_pump == GPIO.LOW and prev_button_pump == GPIO.HIGH:
            if current_time - last_toggle_pump >= debounce_time:
                pump_status = not pump_status
                GPIO.output(PUMP_PIN, pump_status)
                print(f"Pump {'ON' if pump_status else 'OFF'} manually.")
                logging.info(f"Pump {'ON' if pump_status else 'OFF'} manually.")
                last_toggle_pump = current_time
        prev_button_pump = button_pump
        
        # Kiểm tra nút điều khiển đèn LED
        button_led = GPIO.input(BUTTON_LED)
        if button_led == GPIO.LOW and prev_button_led == GPIO.HIGH:
            if current_time - last_toggle_led >= debounce_time:
                led_status = not led_status
                GPIO.output(LED_PIN, led_status)
                print(f"LED {'ON' if led_status else 'OFF'} manually.")
                logging.info(f"LED {'ON' if led_status else 'OFF'} manually.")
                last_toggle_led = current_time
        prev_button_led = button_led
        
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
            
            alert_message = ""  # Thông điệp cảnh báo để hiển thị trên LCD
            
            if mode_auto:
                # Chế độ tự động
                # Điều khiển bơm
                if soil_moisture < lower_threshold:
                    if not pump_status:
                        pump_status = True
                        GPIO.output(PUMP_PIN, GPIO.HIGH)
                        print("Pump turned ON automatically.")
                        logging.info("Pump turned ON automatically.")
                else:
                    if pump_status:
                        pump_status = False
                        GPIO.output(PUMP_PIN, GPIO.LOW)
                        print("Pump turned OFF automatically.")
                        logging.info("Pump turned OFF automatically.")
                
                # Điều khiển quạt
                if temperature > temperature_threshold:
                    if not fan_status:
                        fan_status = True
                        GPIO.output(FAN_PIN, GPIO.HIGH)
                        print("Fan turned ON automatically.")
                        logging.info("Fan turned ON automatically.")
                else:
                    if fan_status:
                        fan_status = False
                        GPIO.output(FAN_PIN, GPIO.LOW)
                        print("Fan turned OFF automatically.")
                        logging.info("Fan turned OFF automatically.")
                
                # Điều khiển đèn LED theo giờ
                current_hour = datetime.now().hour
                if (led_start_hour <= current_hour < 24) or (0 <= current_hour < led_end_hour):
                    if not led_status:
                        led_status = True
                        GPIO.output(LED_PIN, GPIO.HIGH)
                        print("LED turned ON automatically.")
                        logging.info("LED turned ON automatically.")
                else:
                    if led_status:
                        led_status = False
                        GPIO.output(LED_PIN, GPIO.LOW)
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
            
            # Cập nhật trạng thái trên LCD
            update_lcd(temperature, humidity, soil_moisture, fan_status, pump_status, led_status, alert_message)
            
            # Cập nhật thời gian tiếp theo để cập nhật
            next_update_time = current_time + desired_interval
        
        # Thời gian ngắn để tránh vòng lặp nhanh quá
        time.sleep(0.05)  # Giảm thời gian sleep để tăng độ phản hồi
        
    except KeyboardInterrupt:
        lcd.clear()
        lcd.write_string("System Stop...")
        print("System Stop...")
        logging.info("System Stop")
        time.sleep(1)
        break
    finally:
        GPIO.cleanup()
        logging.info("GPIO cleanup and system stopped.")
