from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import hashlib
import hmac
import urllib.parse
import os, re
import json
from dotenv import load_dotenv
from datetime import datetime, timedelta
from ai_helper import ai_assistant
import asyncio
from voice_recognition import voice_recognizer


from database import (
    init_db,
    add_user,
    get_user_stats,
    add_task,
    get_user_tasks,
    update_task_status,
    delete_task,
    add_pomodoro_session,
    get_user_pomodoro_stats,
)

load_dotenv()

app = Flask(__name__)
CORS(app)

BOT_TOKEN = os.getenv("BOT_TOKEN")

# Инициализация базы
init_db()


# --------- Вспомогательное ---------
def normalize_category(cat: str | None) -> str:
    """Переводим старые русские категории в кодовые (work/personal/study/health)"""
    if not cat:
        return "personal"
    c = str(cat).lower()
    if c in {"work", "personal", "study", "health"}:
        return c
    if "работ" in c:
        return "work"
    if "учеб" in c or "учёб" in c:
        return "study"
    if "здоров" in c:
        return "health"
    return "personal"


def normalize_deadline(deadline: str | None) -> str | None:
    """
    Приводим deadline к формату 'dd.mm.yy HH:MM',
    чтобы всё было как у задач из бота.
    """
    if not deadline:
        return None

    try:
        dt = None

        # Если пришёл ISO из мини-аппа: 2025-11-25T03:41:00
        if "T" in deadline:
            try:
                dt = datetime.fromisoformat(deadline)
            except ValueError:
                dt = None

        # Если уже в формате dd.mm.yy HH:MM – просто вернём как есть
        if dt is None:
            for fmt in ("%d.%m.%y %H:%M", "%d.%m.%Y %H:%M", "%Y-%m-%d %H:%M:%S"):
                try:
                    dt = datetime.strptime(deadline, fmt)
                    break
                except ValueError:
                    continue

        if dt is None:
            return deadline

        return dt.strftime("%d.%m.%y %H:%M")
    except Exception:
        return deadline


def priority_from_tags(tags: str | None) -> str:
    """Достаём приоритет из поля tags, если оно используется, иначе medium"""
    if not tags:
        return "medium"
    t = str(tags).lower()
    if "high" in t or "высок" in t or "3" == t.strip():
        return "high"
    if "low" in t or "низк" in t or "1" == t.strip():
        return "low"
    return "medium"


def parse_voice_to_task(text: str) -> dict:
    """
    Очень простой парсер русской фразы в структуру задачи:
    - дата: сегодня / завтра / послезавтра / 12.03 / 12.03.2025
    - время: 10:30 / 9.00 и т.п.
    - категория: по ключевым словам (работа, учеба, здоровье, личное)
    - приоритет: высокий / средний / низкий / важный / срочный
    - title: остаток строки без служебных слов
    """
    original_text = text.strip()
    text_low = original_text.lower()
    now = datetime.now()

    date_str = None
    time_str = None
    category = None
    priority = None

    # ---------- ДАТА ----------
    date = None
    if "сегодня" in text_low:
        date = now.date()
    elif "завтра" in text_low:
        date = (now + timedelta(days=1)).date()
    elif "послезавтра" in text_low:
        date = (now + timedelta(days=2)).date()
    else:
        # ищем формат 12.03, 12/03, 12-03, с годом или без
        m_date = re.search(r"\b(\d{1,2})[.\-/](\d{1,2})(?:[.\-/](\d{2,4}))?\b", text_low)
        if m_date:
            d = int(m_date.group(1))
            mo = int(m_date.group(2))
            y = int(m_date.group(3)) if m_date.group(3) else now.year
            # если год двухзначный — приводим к 20xx
            if y < 100:
                y += 2000
            try:
                date = datetime(y, mo, d).date()
            except ValueError:
                date = None

    if date:
        date_str = date.strftime("%Y-%m-%d")

    # ---------- ВРЕМЯ ----------
    m_time = re.search(r"\b(\d{1,2})[:.](\d{2})\b", text_low)
    if m_time:
        hh = int(m_time.group(1))
        mm = int(m_time.group(2))
        if 0 <= hh <= 23 and 0 <= mm <= 59:
            time_str = f"{hh:02d}:{mm:02d}"

    # ---------- КАТЕГОРИЯ ----------
    if any(w in text_low for w in ["работ", "офис", "созвон", "митинг", "совещан"]):
        category = "work"
    elif any(w in text_low for w in ["учеб", "универ", "школ", "лекци", "семинар", "дз", "домашк"]):
        category = "study"
    elif any(w in text_low for w in ["здоров", "спорт", "трениров", "зал", "врач", "клини", "больниц"]):
        category = "health"
    elif any(w in text_low for w in ["дом", "семь", "личн", "друз", "поездк", "покупк"]):
        category = "personal"

    # ---------- ПРИОРИТЕТ ----------
    if any(w in text_low for w in ["высок", "самое важное", "очень важно", "срочн", "🔥"]):
        priority = "high"
    elif any(w in text_low for w in ["средн", "обычн"]):
        priority = "medium"
    elif any(w in text_low for w in ["низк", "несрочн", "когда-нибудь"]):
        priority = "low"

    # ---------- TITLE (очищаем от "служебного") ----------
    title = original_text

    # убираем слова сегодня/завтра/послезавтра
    for w in ["сегодня", "завтра", "послезавтра"]:
        title = re.sub(rf"\b{w}\b", "", title, flags=re.IGNORECASE)

    # убираем время
    if m_time:
        title = title.replace(m_time.group(0), "")

    # убираем дату (формат dd.mm / dd.mm.yyyy)
    m_date2 = re.search(r"\b(\d{1,2})[.\-/](\d{1,2})(?:[.\-/](\d{2,4}))?\b", title)
    if m_date2:
        title = title.replace(m_date2.group(0), "")

    # убираем слова про приоритет
    for w in [
        "высокий приоритет",
        "низкий приоритет",
        "средний приоритет",
        "высокий",
        "низкий",
        "средний",
        "приоритет",
        "важная задача",
        "важно",
        "срочно",
    ]:
        title = re.sub(rf"\b{w}\b", "", title, flags=re.IGNORECASE)

    # убираем явные слова категорий (чтобы не дублировать)
    for w in [
        "по работе",
        "работа",
        "рабочее",
        "учёба",
        "учеба",
        "по учёбе",
        "по учебе",
        "здоровье",
        "по здоровью",
        "личное",
    ]:
        title = re.sub(rf"\b{w}\b", "", title, flags=re.IGNORECASE)

    # финальная чистка пробелов/знаков
    title = re.sub(r"\s+", " ", title).strip(" ,.-")

    if not title:
        title = original_text

    return {
        "title": title,
        "date": date_str,
        "time": time_str,
        "category": category,
        "priority": priority,
    }


# --------- Проверка данных Telegram WebApp ---------
def verify_telegram_data(init_data: str) -> dict | None:
    try:
        parsed_data = dict(urllib.parse.parse_qsl(init_data))
        print("parsed_data:", parsed_data)

        received_hash = parsed_data.pop("hash", None)
        if not received_hash:
            print("NO HASH IN DATA")
            return None

        data_check_arr = []
        for key in sorted(parsed_data.keys()):
            value = parsed_data[key]
            data_check_arr.append(f"{key}={value}")
        data_check_string = "\n".join(data_check_arr)

        print("data_check_string:", data_check_string)

        # secret_key = HMAC_SHA256("WebAppData", BOT_TOKEN)
        secret_key = hmac.new(
            b"WebAppData",
            BOT_TOKEN.encode(),
            hashlib.sha256,
        ).digest()

        calculated_hash = hmac.new(
            secret_key,
            data_check_string.encode(),
            hashlib.sha256,
        ).hexdigest()

        print("calculated_hash:", calculated_hash)
        print("received_hash:", received_hash)

        if calculated_hash != received_hash:
            print("HASH MISMATCH!")
            return None

        user_json = parsed_data.get("user")
        if user_json:
            return json.loads(user_json)

        return None
    except Exception as e:
        print(f"Error verifying Telegram data: {e}")
        return None


# --------- AUTH ---------
@app.route("/api/auth", methods=["POST"])
def auth():
    data = request.json or {}
    init_data = data.get("initData")

    if not init_data:
        return jsonify({"success": False, "error": "No initData provided"}), 400

    user = verify_telegram_data(init_data)
    if not user:
        return jsonify({"success": False, "error": "Invalid Telegram data"}), 401

    telegram_id = user["id"]
    username = user.get("username")
    first_name = user.get("first_name")
    last_name = user.get("last_name")

    internal_id = add_user(
        telegram_id=telegram_id,
        username=username,
        first_name=first_name,
        last_name=last_name,
    )

    return jsonify(
        {
            "success": True,
            "user": {
                "id": internal_id,
                "telegram_id": telegram_id,
                "username": username,
                "first_name": first_name,
                "last_name": last_name,
            },
        }
    )


# --------- TASKS ---------
@app.route('/api/tasks', methods=['GET'])
def get_tasks():
    user_id = request.args.get('user_id')
    if not user_id:
        return jsonify({'success': False, 'error': 'user_id required'}), 400

    rows = get_user_tasks(int(user_id))
    tasks_clean = []

    for t in rows:
        # Если база возвращает dict (частый вариант)
        if isinstance(t, dict):
            task_id = t.get("id")
            uid = t.get("user_id")
            title = t.get("title") or t.get("task")
            category_raw = t.get("category")
            tags = t.get("tags")
            deadline_raw = t.get("deadline")
            completed = t.get("completed", 0)
            created_at = t.get("created_at")
            updated_at = t.get("updated_at")
            priority_raw = t.get("priority")
        else:
            # Если возвращается tuple / list — аккуратно берём по индексам
            task_id      = t[0] if len(t) > 0 else None
            uid          = t[1] if len(t) > 1 else None
            title        = t[2] if len(t) > 2 else None
            category_raw = t[3] if len(t) > 3 else None
            tags         = t[4] if len(t) > 4 else None
            deadline_raw = t[5] if len(t) > 5 else None
            completed    = t[6] if len(t) > 6 else 0
            created_at   = t[7] if len(t) > 7 else None
            updated_at   = t[8] if len(t) > 8 else None
            priority_raw = t[9] if len(t) > 9 else None

        category = normalize_category(category_raw)
        deadline_norm = normalize_deadline(deadline_raw)

        # приоритет берём из колонки, а если нет — из tags
        pr = priority_raw or priority_from_tags(tags)
        if pr not in ("low", "medium", "high"):
            pr = "medium"

        tasks_clean.append({
            "id": task_id,
            "user_id": uid,
            "title": title,
            "category": category,
            "tags": tags,
            "deadline": deadline_norm,
            "completed": bool(completed),
            "created_at": created_at,
            "updated_at": updated_at,
            "priority": pr,
        })

    return jsonify({"success": True, "tasks": tasks_clean})


@app.route('/api/tasks', methods=['POST'])
def create_task():
    data = request.json or {}
    user_id = data.get('user_id')
    task_text = data.get('task')
    priority = data.get('priority', 'medium')
    deadline = data.get('deadline')
    category = data.get('category', 'personal')

    if not user_id or not task_text:
        return jsonify({'success': False, 'error': 'user_id and task required'}), 400

    try:
        task_id = add_task(
            int(user_id),
            task_text,
            category=category,
            tags=priority,
            deadline=deadline,
        )
    except Exception as e:
        print("ADD_TASK ERROR:", e)
        return jsonify({'success': False, 'error': str(e)}), 500

    return jsonify({
        'success': True,
        'task_id': task_id,
        'message': 'Task created successfully'
    })


@app.route("/api/tasks/<int:task_id>", methods=["PUT"])
def update_task(task_id):
    """Обновить статус задачи (completed / in_progress)"""
    data = request.json or {}
    status = data.get("status")

    if status is None:
        return jsonify({"success": False, "error": "status required"}), 400

    # переводим строковый статус в bool для БД
    if isinstance(status, bool):
        completed = status
    else:
        s = str(status).lower()
        completed = s in {"completed", "done", "true", "1"}

    success = update_task_status(task_id, completed)

    if not success:
        return jsonify({"success": False, "error": "Task not found"}), 404

    return jsonify({"success": True, "message": "Task updated successfully"})


@app.route("/api/tasks/<int:task_id>", methods=["DELETE"])
def remove_task(task_id):
    """Удалить задачу"""
    success = delete_task(task_id)
    if not success:
        return jsonify({"success": False, "error": "Task not found"}), 404
    return jsonify({"success": True, "message": "Task deleted successfully"})


# --------- AI ---------
@app.route('/api/ai', methods=['POST'])
def api_ai():
    """
    AI для мини-аппы — тот же движок, что и в боте
    """
    data = request.json or {}
    user_id = data.get('user_id')
    message = (data.get('message') or "").strip()

    if not message:
        return jsonify({"success": False, "error": "message required"}), 400

    user_context = f"Пользователь ID={user_id}"

    try:
        # AIAssistant — асинхронный → оборачиваем
        reply = asyncio.run(ai_assistant.generate_response(message, user_context))
        return jsonify({"success": True, "reply": reply})
    except Exception as e:
        print("AI ERROR:", e)
        return jsonify({"success": False, "error": str(e)}), 500
    

@app.route("/api/voice", methods=["POST"])
def api_voice():
    """
    Принимает аудио-файл (form-data: file),
    отправляет в Whisper через voice_recognition.py
    и возвращает распознанный текст + разобранные поля задачи.
    """
    if "file" not in request.files:
        return jsonify({"success": False, "error": "Файл не передан"}), 400

    file = request.files["file"]
    voice_bytes = file.read()

    # Определяем формат файла по расширению
    ext = "ogg"
    if file.filename and "." in file.filename:
        ext = file.filename.rsplit(".", 1)[1].lower()

    try:
        # вызываем асинхронный метод через asyncio.run (как в /api/ai)
        raw_result = asyncio.run(
            voice_recognizer.recognize_voice(voice_bytes, file_format=ext)
        )

        # Если пришла ошибка из voice_recognition.py — отдадим её как error
        if isinstance(raw_result, str) and raw_result.startswith("❌"):
            return jsonify({"success": False, "error": raw_result}), 500

        # raw_result сейчас строка вида:
        # "🎤 Распознанный текст:\n\n...."
        text = raw_result

        if text.startswith("🎤"):
            parts = text.split("\n\n", 1)
            if len(parts) == 2:
                text = parts[1].strip()

        # 👉 ПАРСИМ ТЕКСТ В СТРУКТУРУ
        parsed = parse_voice_to_task(text)

        return jsonify({
            "success": True,
            "text": text,
            "parsed": parsed,   # <-- сюда кладём title/date/time/category/priority
        })

    except Exception as e:
        print("VOICE API ERROR:", e)
        return jsonify(
            {"success": False, "error": "Ошибка при распознавании голоса"}
        ), 500


# --------- POMODORO ---------
@app.route("/api/pomodoro", methods=["POST"])
def add_pomodoro():
    """Сохранить Pomodoro-сессию (duration в СЕКУНДАХ)"""
    data = request.json or {}
    user_id = data.get("user_id")
    task_id = data.get("task_id")
    duration = data.get("duration", 25 * 60)

    if not user_id:
        return jsonify({"success": False, "error": "user_id required"}), 400

    try:
        duration = int(duration)
    except Exception:
        duration = 25 * 60

    session_id = add_pomodoro_session(int(user_id), duration, task_id)

    return jsonify(
        {
            "success": True,
            "session_id": session_id,
            "message": "Pomodoro session saved",
        }
    )


@app.route("/api/pomodoro/stats", methods=["GET"])
def get_pomodoro_stats():
    user_id = request.args.get("user_id")
    if not user_id:
        return jsonify({"success": False, "error": "user_id required"}), 400

    stats = get_user_pomodoro_stats(int(user_id))
    return jsonify({"success": True, "stats": stats})


# --------- ОБЩАЯ СТАТИСТИКА ---------
@app.route("/api/stats", methods=["GET"])
def get_stats():
    user_id = request.args.get("user_id")
    if not user_id:
        return jsonify({"success": False, "error": "user_id required"}), 400

    tasks_stats = get_user_stats(int(user_id))
    pomodoro_stats = get_user_pomodoro_stats(int(user_id))

    return jsonify(
        {
            "success": True,
            "tasks_stats": tasks_stats,
            "pomodoro_stats": pomodoro_stats,
        }
    )


# --------- SERVICE ---------
@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "message": "FocusUp API is running"})


@app.route("/")
def index_page():
    return send_from_directory(".", "index.html")


if __name__ == "__main__":
    print("🚀 FocusUp API Server starting...")
    print("📊 Database: focusup.db")
    print("🌐 Mini App can connect on: http://localhost:8888")
    app.run(host="0.0.0.0", port=8888, debug=True)
