# Personal Data Analytics Platform

> **پروتوتایپ اولیه:** این پروژه در مرحله‌ی اولیه است، خیلی حرفه‌ای و کامل نیست، و ممکن است امکانات و ساختار آن تغییر کند.
>
> **Early prototype:** this project is in an early stage, not a very professional or complete product, and features and structure may change.

---

<div dir="rtl">

## فارسی

پلتفرم تحلیل داده‌های شخصی با پایتون: فایل‌های CSV ،XLSX ،XLS ،JSON و Parquet را آپلود کنید، داده را با پیش‌نمایش قبل از اعمال تمیز کنید (فایل اصلی دست نمی‌خورد)، آمار و تحلیل اکتشافی بگیرید، نمودار بسازید، ناهنجاری پیدا کنید و گزارش PDF ،Excel ،CSV و HTML خروجی بگیرید.

- داشبورد تعاملی Streamlit با ۹ صفحه
- بک‌اند FastAPI و دیتابیس SQLite با SQLAlchemy
- یادگیری ماشین: Isolation Forest ،K-Means و طبقه‌بندی (بدون آموزش خودکار، فقط با تأیید صریح کاربر)

### برای چه کسانی؟

برای کسانی که داده توی اکسل یا CSV دارند ولی برنامه‌نویسی بلد نیستند: دانشجوها (تحلیل پرسشنامه و پایان‌نامه)، کاسب‌ها و مغازه‌دارها (مشتری‌ها، دخل و خرج، انبار)، معلم‌ها و محقق‌ها (نمره‌ها و نظرسنجی‌ها).

برای دیتاساینتیست‌های حرفه‌ای یا شرکت‌های بزرگ نیست؛ آن‌ها مستقیم با پایتون، Power BI یا Tableau کار می‌کنند.

### اجرا

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/streamlit run app.py
```

بک‌اند API:

```bash
.venv/bin/uvicorn api.main:app
```

نیازمند پایتون 3.11+.

</div>

---

## English

A personal data analytics platform in Python: upload CSV, XLSX, XLS, JSON, and Parquet files, clean data with preview-before-apply (the original is never modified), run statistical analysis and EDA, build visualizations, detect anomalies, and export PDF, Excel, CSV, and HTML reports.

- Interactive Streamlit dashboard with 9 pages
- FastAPI backend and SQLite database with SQLAlchemy
- Machine learning: Isolation Forest, K-Means, and classification (no automatic training — only with explicit user confirmation)

### Who is it for?

For people who have data in Excel or CSV but don't code: students (survey and thesis analysis), small shop and business owners (customers, income and expenses, inventory), teachers and researchers (grades and surveys).

Not for professional data scientists or large companies — they work directly with Python, Power BI, or Tableau.

### Run

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/streamlit run app.py
```

API backend:

```bash
.venv/bin/uvicorn api.main:app
```

Requires Python 3.11+.
