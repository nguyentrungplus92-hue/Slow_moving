import requests
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime

# ========== LOGGING SETUP ==========
logger = logging.getLogger("slow_moving_client")
logger.setLevel(logging.INFO)

file_handler = RotatingFileHandler(
    "client.log", maxBytes=5*1024*1024, backupCount=3, encoding="utf-8"
)
file_handler.setFormatter(logging.Formatter(
    "%(asctime)s - %(levelname)s - %(message)s"
))
logger.addHandler(file_handler)
# ===================================


def call_slow_moving():

    today_str = datetime.today().strftime("%Y-%m-%d")
    
    url = "http://10.92.184.241:8008/FG/submit/"

    data = [
        ("date", today_str),
        # ("material", "B0ACEM000012"),
        # ("sloc", ""),
        # ("report_detail", "1"),
        # ("report_summary", "1"),
        ("down_Radio", "downServer"),
        ("serverPath", "C:/Users/SAP1/Desktop/Slow_moving/store/")

    ]

    logger.info("=== Bắt đầu gọi API Slow Moving - FG & HALB ===")
    logger.info("URL: %s", url)
    logger.info(f"Ngày: {today_str}")
    try:
        response = requests.post(url, data=data)
        status = response.status_code

        # In và log status
        print(f"Status: {status}")
        logger.info("Status code: %s", status)

        # =============================
        # 1️⃣ THÀNH CÔNG – Status 200–299
        # =============================
        if 200 <= status < 300:
            print("Kết quả: **Thành công** 🎉")
            logger.info(f"✅ Kết quả: Thành công")

            # Kiểm tra nếu là file Excel
            content_type = response.headers.get("Content-Type", "")
            if "application/vnd.openxmlformats" in content_type:
                filename = "download.xlsx"
                with open(filename, "wb") as f:
                    f.write(response.content)
                print("Đã lưu file Excel:", filename)
                logger.info("Đã lưu file Excel: %s", filename)
            else:
                # JSON (nếu có)
                try:
                    data_json = response.json()
                    print("Response JSON:", data_json)
                    logger.info("JSON Response: %s", data_json)
                except:
                    print("Response Text:", response.text[:300])
                    logger.info("Text Response: %s", response.text[:300])

        # =============================
        # 2️⃣ LỖI CLIENT – Status 400–499
        # =============================
        elif 400 <= status < 500:
            print(f"❌Kết quả: **Lỗi phía Client** ")
            logger.warning("Client error: %s", status)

            try:
                data_json = response.json()
                print("Chi tiết:", data_json)
                logger.warning("Chi tiết lỗi: %s", data_json)
            except:
                print("Response Text:", response.text[:300])
                logger.warning(f"❌ Raw lỗi: %s", response.text[:300])

        # =============================
        # 3️⃣ LỖI SERVER – Status 500–599
        # =============================
        elif 500 <= status < 600:
            print("Kết quả: **Lỗi phía Server** 💥")
            logger.error(f"❌ Server error: %s", status)

            try:
                data_json = response.json()
                print("Chi tiết:", data_json)
                logger.error("Chi tiết lỗi: %s", data_json)
            except:
                print("Response Text:", response.text[:300])
                logger.error(f"❌ Raw lỗi: %s", response.text[:300])

        # =============================
        # 4️⃣ Mọi trường hợp khác
        # =============================
        else:
            print("Kết quả: **Không xác định** ⚠️")
            logger.warning(f" ❌Unknown status code: %s", status)
            print("Response:", response.text[:300])

    except Exception as e:
        print("Lỗi khi gọi API:", e)
        logger.exception(f"❌ Exception xảy ra: %s", e)

    logger.info("=== Kết thúc gọi API ===\n")



if __name__ == "__main__":
    call_slow_moving()
