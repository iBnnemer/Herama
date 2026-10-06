# Herama

Local LLM backend — FastAPI + llama-cpp-python with an Ollama-compatible API.

## متطلبات التشغيل

```
pip install -r requirements.txt
```

ضع ملفات `.gguf` في مجلد `models/`.

## التشغيل

```bash
python -m app.main
# أو
uvicorn app.main:app --host 127.0.0.1 --port 11434
```

## المتغيرات البيئية

| المتغير | الافتراضي | الوصف |
|---|---|---|
| `HERAMA_ROOT` | مجلد المشروع | جذر المشروع |
| `HERAMA_MODELS` | `models/` | مجلد ملفات GGUF |
| `HERAMA_HOST` | `127.0.0.1` | عنوان الاستماع |
| `HERAMA_PORT` | `11434` | المنفذ (مثل Ollama) |
| `HERAMA_SKILL_EXEC` | `0` | `1` لتفعيل تشغيل المهارات |
| `HERAMA_SKILL_TIMEOUT` | `10` | مهلة تشغيل المهارة (ثواني) |

## مسارات Ollama المتوافقة

| المسار | الطريقة | الوصف |
|---|---|---|
| `/api/tags` | GET | قائمة النماذج |
| `/api/show` | POST | بيانات النموذج (GGUF meta) |
| `/api/ps` | GET | النموذج المحمّل حالياً |
| `/api/generate` | POST | توليد نص |
| `/api/chat` | POST | محادثة (message history) |
| `/api/embeddings` | POST | تضمينات نصية |
| `/api/delete` | DELETE | حذف نموذج |
| `/api/copy` | POST | نسخ نموذج |
| `/api/pull` | POST | stub — لا يُنزّل (ضع GGUF يدوياً) |
| `/api/version` | GET | إصدار Herama |

## امتدادات Herama

أضف هذه الحقول لأي طلب `/api/generate` أو `/api/chat`:

```json
{
  "memory": true,
  "auto_extract": true
}
```

- `memory: true` — يحقن حقائق ذات صلة من الذاكرة في الـ system prompt.
- `auto_extract: true` — يستخرج الجمل الإخبارية من الرد ويخزّنها تلقائياً.

## مسارات الذاكرة

```
POST   /api/memory          إضافة حقيقة
GET    /api/memory?k=20     آخر k حقائق
GET    /api/memory/search?q=... بحث FTS
DELETE /api/memory/{id}     حذف حقيقة
```

## مسارات المهارات

```
GET    /api/skills                    قائمة المهارات
POST   /api/skills/generate           توليد مهارة بالنموذج
POST   /api/skills                    حفظ مهارة يدوياً
POST   /api/skills/{name}/run         تشغيل مهارة (يتطلب HERAMA_SKILL_EXEC=1)
```

## الاختبارات

```bash
pytest tests/ -v
```

## الهيكل

```
app/
  main.py          FastAPI + الراوترات
  config.py        الإعدادات
  engine.py        تحميل النموذج + keep_alive
  resources.py     قراءة RAM/VRAM + رأس GGUF
  api/
    ollama.py      مسارات Ollama
    memory.py      مسارات الذاكرة
    skills.py      مسارات المهارات
  memory/store.py  SQLite + FTS5
  skills/registry.py  AST validator + sandbox
models/   ← ضع ملفات .gguf هنا
.memory/  ← قاعدة بيانات SQLite (تُنشأ تلقائياً)
skills/   ← مهارات مُوَلَّدة (تُنشأ تلقائياً)
```
