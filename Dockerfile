FROM python:3.10

# تثبيت المتطلبات الأساسية لتشغيل pyodbc
RUN apt-get update && \
    apt-get install -y gnupg curl unixodbc-dev gcc g++ && \
    curl https://packages.microsoft.com/keys/microsoft.asc | apt-key add - && \
    curl https://packages.microsoft.com/config/debian/10/prod.list > /etc/apt/sources.list.d/mssql-release.list && \
    apt-get update && ACCEPT_EULA=Y apt-get install -y msodbcsql17

# إنشاء مجلد العمل
WORKDIR /app

# نسخ ملفات المشروع
COPY . /app

# تثبيت الحزم من requirements.txt
RUN pip install --upgrade pip
RUN pip install -r requirements.txt

# بدء التطبيق
CMD ["python", "main.py"]
