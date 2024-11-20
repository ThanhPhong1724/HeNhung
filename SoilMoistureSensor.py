import random
import time

class SoilMoistureSensor:
    def __init__(self, pin):
        self.pin = pin

    def read(self):
        # Giả lập giá trị độ ẩm đất trong khoảng từ 0% đến 100%
        soil_moisture = random.uniform(0.0, 100.0)  # Độ ẩm đất từ 0% (khô) đến 100% (ướt)
        
        # Thời gian giả lập để đọc dữ liệu (0.5 giây)
        time.sleep(0.5)
        
        return soil_moisture

# Hàm đọc giá trị độ ẩm đất
def readSensorSoil(pin):
    sensor = SoilMoistureSensor(pin)
    return sensor.read()

