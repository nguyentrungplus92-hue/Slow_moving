import requests
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime

# =========================
# LOGGING SETUP
# =========================
logger = logging.getLogger("api_client")
logger.setLevel(logging.INFO)

if not logger.handlers:
    file_handler = RotatingFileHandler(
        "client.log",
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8"
    )
    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    file_handler.setFormatter(formatter)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)


# =========================
# CORE FUNCTION
# =========================
def post_and_handle(url: str, data):
    logger.info("=== Bắt đầu gọi API ===")
    logger.info("URL: %s", url)
    logger.info("Payload: %s", data)
    logger.info("Date: %s", datetime.today())
    try:
        response = requests.post(
            url,
            data=data,
            timeout=150 * 60  # 150 phút
        )
        status = response.status_code

        print(f"Status: {status}")
        logger.info("Status code: %s", status)

        # 1) SUCCESS
        if 200 <= status < 300:
            logger.info("✅ Thành công")

            content_type = response.headers.get("Content-Type", "")
            if "application/vnd.openxmlformats" in content_type:
                logger.info("Excel được trả về (server tự xử lý)")
            else:
                try:
                    logger.info("JSON Response: %s", response.json())
                except Exception:
                    logger.info("Text Response: %s", response.text[:300])

        # 2) CLIENT ERROR
        elif 400 <= status < 500:
            logger.warning("❌ Client error: %s", status)
            try:
                logger.warning("Chi tiết: %s", response.json())
            except Exception:
                logger.warning("Raw: %s", response.text[:300])

        # 3) SERVER ERROR
        elif 500 <= status < 600:
            logger.error("💥 Server error: %s", status)
            try:
                logger.error("Chi tiết: %s", response.json())
            except Exception:
                logger.error("Raw: %s", response.text[:300])

        # 4) OTHER
        else:
            logger.warning("⚠️ Unknown status code: %s", status)

        return response

    except Exception:
        logger.exception("❌ Exception xảy ra khi gọi API")
        return None

    finally:
        logger.info("=== Kết thúc gọi API ===\n")


# =========================
# RUN JOBS
# =========================
def run_jobs():
    today_str = datetime.today().strftime("%Y-%m-%d")
    
    jobs = [
        {
            "url": "http://10.92.184.241:8008/FG/submit/",
            "data": [
                ("date", today_str),
                ("down_Radio", "downServer"),
                ("serverPath", "C:/Users/SAP1/Desktop/Slow_moving/store/"),
            ],
        },
        {
            "url": "http://10.92.184.241:8008/submit/",
            "data": [
                ("date", today_str),
                ("report_detail", "1"),
                ("report_summary", "1"),
                ("down_Radio", "downServer"),
                ("serverPath", "C:/Users/SAP1/Desktop/Slow_moving/store/"),
            ],
        },
    ]

    for job in jobs:
        post_and_handle(job["url"], job["data"])


if __name__ == "__main__":
    run_jobs()
