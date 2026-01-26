import os
from dotenv import load_dotenv
from waitress import serve

load_dotenv()  # đọc .env

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "mysite.settings")

from mysite.wsgi import application  # noqa: E402

serve(application, host="0.0.0.0", port=8008, threads=8)
