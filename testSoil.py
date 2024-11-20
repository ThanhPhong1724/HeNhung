import time
from SoilMoistureSensor import readSensor

# Ví dụ sử dụng
if __name__ == "__main__":
    pin = 27  # Chân nối cảm biến (giả lập)
    while True:
        soil_moisture = readSensor(pin)
        print(f"Độ ẩm đất: {soil_moisture:.2f}%")
        time.sleep(1)  # Giả lập đọc mỗi giây
