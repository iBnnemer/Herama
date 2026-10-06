# Herama — خطة الـ Backend

## الهيكل
```
app/
  main.py            FastAPI + الراوترات
  config.py          المسارات والمتغيرات (HERAMA_*)
  resources.py       قراءة RAM/VRAM + رأس GGUF → n_ctx, n_gpu_layers
  engine.py          تحميل llama-cpp وتبديل النموذج
  api/ollama.py      /api/tags  /api/generate  /api/version
  api/memory.py      /api/memory (إضافة/بحث/حذف)
  api/skills.py      /api/skills (توليد/حفظ/تشغيل)
  memory/store.py    SQLite + FTS5 في .memory/memory.db
  skills/registry.py تحقق AST + حفظ في skills/ + index.json
skills/  models/  .memory/
```

## التشغيل
```
pip install -r requirements.txt
python -m app.main        # المنفذ 11434 مثل Ollama
```
ضع ملفات .gguf في models/. تشغيل المهارات معطّل افتراضياً: `HERAMA_SKILL_EXEC=1`.

## الخطوات التالية
1. /api/chat و /api/show و /api/ps (بقية مسارات Ollama).
2. keep_alive وتفريغ النموذج تلقائياً.
3. استخراج حقائق تلقائياً من المحادثات إلى الذاكرة.
4. تشغيل المهارات في عملية منفصلة بمهلة زمنية (sandbox).
5. اختبارات pytest + git init وربط مستودع iBnnemer/Herama.
