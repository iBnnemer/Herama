# herama

Local LLM desktop app — Electron + React UI, FastAPI + llama-cpp-python backend (Ollama-compatible API).

## التشغيل السريع

### Windows
```
انقر نقراً مزدوجاً على: START.bat
```

### macOS / Linux
```
./START.sh
```

يقوم السكريبت تلقائياً بـ:
1. تثبيت مكتبات Python (`requirements.txt`)
2. تثبيت مكتبات Node عند أول تشغيل (`frontend/node_modules`)
3. تشغيل التطبيق — Electron يشغّل الـ backend تلقائياً عند الفتح

## المتطلبات الأساسية (مرة واحدة فقط)

| أداة | رابط التحميل |
|------|-------------|
| Python 3.10+ | https://www.python.org/downloads/ (✓ Add to PATH) |
| Node.js 20+ | https://nodejs.org/ |

لا يلزم تثبيت أي شيء آخر — كل شيء يثبّت تلقائياً.

## النماذج

ضع ملفات `.gguf` في مجلد `models/` — يجدها التطبيق تلقائياً.

## بناء نسخة قابلة للتوزيع (.exe)

```bash
cd frontend
npm install
npm run dist
# → release/herama Setup x.x.x.exe
```

## API

يعمل على `http://127.0.0.1:11434` — متوافق مع Ollama:

| Endpoint | Description |
|----------|-------------|
| `GET /health` | health check |
| `GET /api/tags` | list models |
| `POST /api/generate` | generate (streaming) |
| `POST /api/chat` | chat (streaming) |
| `GET /api/agents` | list agents |
| `POST /api/agents` | create agent |
