# Telegram Bot on Render (Python)

## خطوات النشر السريع

1. ارفع هذا المستودع إلى GitHub.
2. ادخل إلى https://render.com وأنشئ **Web Service** جديدًا من المستودع.
3. أضف متغيري البيئة:
   - `BOT_TOKEN`   : التوكن الخاص بالبوت
   - `DB_CONN_STR` : جملة الاتصال بـ SQL Server
4. اترك إعدادات البناء الافتراضية (`pip install -r requirements.txt`).
5. بعد نجاح النشر احصل على الرابط مثل:
   ```
   https://your-bot.onrender.com
   ```
6. نفّذ:
   ```
   https://api.telegram.org/bot<توكنك>/setWebhook?url=https://your-bot.onrender.com/<توكنك>
   ```

💡 الآن البوت يعمل 24/7.
