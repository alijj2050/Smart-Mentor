# از image پایه Python 3.9 نسخه slim استفاده می‌کنیم
FROM python:3.9-slim

# دایرکتوری کاری را به /app تنظیم می‌کنیم
WORKDIR /app

# فایل requirements.txt را از مسیر محلی به داخل image کپی می‌کنیم
COPY requirements.txt .

# وابستگی‌ها را با استفاده از pip نصب می‌کنیم
RUN pip install --no-cache-dir -r requirements.txt

# تمام فایل‌ها و دایرکتوری‌های محلی را به داخل image کپی می‌کنیم
COPY . .

# دستور اجرای برنامه را تعیین می‌کنیم
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "80"]