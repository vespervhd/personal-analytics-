# Personal Data Analytics Platform

> **پروتوتایپ اولیه:** این پروژه در مرحله‌ی اولیه است و ممکن است امکانات و ساختار آن تغییر کند.
>
> **Early prototype:** this project is in an early stage; features and structure may change.

---

## فارسی

پلتفرم تحلیل داده‌های شخصی با پایتون: فایل‌های CSV ،XLSX ،XLS ،JSON و Parquet را آپلود کنید، داده را با پیش‌نمایش قبل از اعمال تمیز کنید (فایل اصلی دست نمی‌خورد)، آمار و تحلیل اکتشافی بگیرید، نمودار بسازید، ناهنجاری پیدا کنید و گزارش PDF ،Excel ،CSV و HTML خروجی بگیرید.

- داشبورد تعاملی Streamlit با ۹ صفحه
- بک‌اند FastAPI و دیتابیس SQLite با SQLAlchemy
- یادگیری ماشین: Isolation Forest ،K-Means و طبقه‌بندی (بدون آموزش خودکار، فقط با تأیید صریح کاربر)

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

---

## English

A personal data analytics platform in Python: upload CSV, XLSX, XLS, JSON, and Parquet files, clean data with preview-before-apply (the original is never modified), run statistical analysis and EDA, build visualizations, detect anomalies, and export PDF, Excel, CSV, and HTML reports.

- Interactive Streamlit dashboard with 9 pages
- FastAPI backend and SQLite database with SQLAlchemy
- Machine learning: Isolation Forest, K-Means, and classification (no automatic training — only with explicit user confirmation)

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
