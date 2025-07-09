# استخدم نسخة خفيفة من بايثون
FROM python:3.10-slim

# تحديد مجلد العمل داخل الحاوية
WORKDIR /app

# نسخ كل الملفات إلى الحاوية
COPY . .

# تثبيت المتطلبات
RUN pip install --upgrade pip
RUN pip install -r requirements.txt

# تنفيذ ملف البوت
CMD ["python", "main.py"]
