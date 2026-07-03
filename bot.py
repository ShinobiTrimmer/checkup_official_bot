"""
Бот «Чек-ап пары» — мультиязычная версия (RU / EN / ES)

Логика:
- Ссылки из разных каналов: ?start=q1_ru / ?start=q1_en / ?start=q1_es
  Бот сразу определяет язык из параметра и не задаёт лишних вопросов.
- Если пользователь пришёл без параметра — предлагает выбрать язык кнопками.
- Второй партнёр получает ссылку вида ?start=q1_ru-КОД — язык и код зашиты вместе.
- /stats — статистика только для владельца (задаётся через ADMIN_ID).
- /delete и /stop — работают на всех языках.
"""

import asyncio
import logging
import os
import random
import sqlite3
import string
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, Command
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("checkup_bot")

BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN не найден. Задайте переменную окружения BOT_TOKEN.")

DB_PATH = os.environ.get("DB_PATH", "checkup.db")

# Вставьте сюда ваш Telegram user ID (узнать через @userinfobot)
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))

# ---------------------------------------------------------------------------
# ТЕКСТЫ ИНТЕРФЕЙСА ПО ЯЗЫКАМ
# ---------------------------------------------------------------------------
UI = {
    "ru": {
        "consent": (
            "Прежде чем начать — коротко.\n\n"
            "Это не терапия и не диагностика. Это короткий чек-ап для разговора с партнёром.\n"
            "Ваши ответы видит только бот, пока партнёр не завершит свою часть — после этого "
            "вы оба увидите общую карточку результата.\n\n"
            "Если в какой-то момент вам небезопасно показывать ответы партнёру — вы можете "
            "остановиться в любой момент командой /stop, партнёр не получит уведомления.\n\n"
            "Данные можно удалить в любой момент командой /delete.\n\n"
            "Продолжая, вы соглашаетесь на хранение ваших ответов для этого чек-апа."
        ),
        "consent_yes": "Согласен(на), начать",
        "consent_no": "Не сейчас",
        "consent_no_reply": "Хорошо, возвращайтесь когда будете готовы — просто напишите /start.",
        "start_msg": "Отлично. Отвечайте честно — здесь нет «правильных» ответов.",
        "question_prefix": "Вопрос",
        "text_hint": "(ответьте текстом одним сообщением)",
        "choose_option": "Пожалуйста, выберите один из вариантов выше ⬆️",
        "your_answer": "Ваш ответ",
        "finished_wait": (
            "Готово! Ваши ответы сохранены. "
            "Как только партнёр закончит свою часть — пришлю результат вам обоим."
        ),
        "invite_msg": (
            "Готово! Вы прошли все вопросы.\n\n"
            "Код вашей пары: {code}\n\n"
            "Отправьте партнёру это сообщение:\n\n"
            "—\n"
            "Не отправляю это как претензию 🙂 Я прошёл(шла) короткий чек-ап для пар, "
            "пройди свою часть — займёт 5 минут, ответы видны только после того, "
            "как оба закончат: {link}\n"
            "—\n\n"
            "Как только партнёр завершит свою часть — пришлю вам обоим карточку результата."
        ),
        "result_header": "📋 Результат чек-апа (код {code})\n\n",
        "matched": "Совпало {n} из {total} вопросов с вариантами ответа.\n\n",
        "diff_header": "Точки, где взгляды разошлись:\n",
        "all_match": "По всем закрытым вопросам взгляды совпали 🙂\n\n",
        "open_header": "Темы для разговора (открытые ответы):\n",
        "partner1": "Партнёр 1",
        "partner2": "Партнёр 2",
        "result_footer": (
            "\n\nЭто не вердикт — просто повод обсудить то, что обычно остаётся непроговорённым. "
            "Через 7 дней я предложу пройти это снова."
        ),
        "reminder": (
            "Прошла неделя с вашего последнего чек-апа 🙂 "
            "Хотите быстро свериться снова? Напишите /start."
        ),
        "deleted": "Все ваши данные удалены.",
        "stopped": (
            "Остановлено. Партнёр не получит никакого уведомления. "
            "Если хотите удалить уже сохранённые ответы — используйте /delete."
        ),
        "help": "/start — начать новый чек-ап\n/stop — остановиться\n/delete — удалить мои данные",
        "not_found": "Такой код не найден. Проверьте ссылку или попросите партнёра отправить её заново.",
        "choose_lang": "Выберите язык / Choose language / Elige idioma:",
    },
    "en": {
        "consent": (
            "Before we start — a quick note.\n\n"
            "This is not therapy and not a clinical assessment. It's a short check-up "
            "to create a conversation with your partner.\n"
            "Your answers are only visible to the bot until your partner finishes their part — "
            "after that, you'll both see a shared result card.\n\n"
            "If at any point it feels unsafe to share your answers with your partner — you can "
            "stop at any time with /stop. Your partner won't be notified.\n\n"
            "You can delete your data at any time with /delete.\n\n"
            "By continuing, you agree to your answers being stored for this check-up."
        ),
        "consent_yes": "I agree, let's start",
        "consent_no": "Not right now",
        "consent_no_reply": "No problem — come back whenever you're ready. Just send /start.",
        "start_msg": "Great. Answer honestly — there are no right answers here.",
        "question_prefix": "Question",
        "text_hint": "(reply with a text message)",
        "choose_option": "Please choose one of the options above ⬆️",
        "your_answer": "Your answer",
        "finished_wait": (
            "Done! Your answers are saved. "
            "As soon as your partner finishes their part, I'll send you both the result."
        ),
        "invite_msg": (
            "Done! You've answered all the questions.\n\n"
            "Your pair code: {code}\n\n"
            "Send your partner this message:\n\n"
            "—\n"
            "Not sending this as a complaint 🙂 I did a short couples check-up — "
            "go through your part, it takes 5 minutes, answers are only visible once "
            "we've both finished: {link}\n"
            "—\n\n"
            "Once your partner finishes, I'll send you both the result card."
        ),
        "result_header": "📋 Check-up result (code {code})\n\n",
        "matched": "Matched {n} out of {total} multiple-choice questions.\n\n",
        "diff_header": "Where your perspectives differed:\n",
        "all_match": "All multiple-choice answers matched 🙂\n\n",
        "open_header": "Topics for conversation (open answers):\n",
        "partner1": "Partner 1",
        "partner2": "Partner 2",
        "result_footer": (
            "\n\nThis isn't a verdict — just a starting point for a conversation "
            "that might otherwise never happen. In 7 days I'll suggest doing this again."
        ),
        "reminder": (
            "It's been a week since your last check-up 🙂 "
            "Want to compare notes again? Just send /start."
        ),
        "deleted": "All your data has been deleted.",
        "stopped": (
            "Stopped. Your partner won't receive any notification. "
            "To delete your saved answers, use /delete."
        ),
        "help": "/start — begin a new check-up\n/stop — stop anytime\n/delete — delete my data",
        "not_found": "That code wasn't found. Check the link or ask your partner to resend it.",
        "choose_lang": "Выберите язык / Choose language / Elige idioma:",
    },
    "es": {
        "consent": (
            "Antes de empezar — una nota rápida.\n\n"
            "Esto no es terapia ni un diagnóstico clínico. Es un breve check-up "
            "para generar una conversación con tu pareja.\n"
            "Tus respuestas solo las ve el bot hasta que tu pareja termine su parte — "
            "después, los dos verán una tarjeta de resultado compartida.\n\n"
            "Si en algún momento no te sientes seguro de compartir tus respuestas con tu pareja — "
            "puedes detenerte en cualquier momento con /stop. Tu pareja no recibirá ningún aviso.\n\n"
            "Puedes eliminar tus datos en cualquier momento con /delete.\n\n"
            "Al continuar, aceptas que tus respuestas se almacenen para este check-up."
        ),
        "consent_yes": "De acuerdo, empecemos",
        "consent_no": "Ahora no",
        "consent_no_reply": "Sin problema — vuelve cuando quieras. Solo escribe /start.",
        "start_msg": "Perfecto. Responde honestamente — aquí no hay respuestas correctas.",
        "question_prefix": "Pregunta",
        "text_hint": "(responde con un mensaje de texto)",
        "choose_option": "Por favor elige una de las opciones de arriba ⬆️",
        "your_answer": "Tu respuesta",
        "finished_wait": (
            "¡Listo! Tus respuestas están guardadas. "
            "En cuanto tu pareja termine su parte, les envío el resultado a los dos."
        ),
        "invite_msg": (
            "¡Listo! Has respondido todas las preguntas.\n\n"
            "El código de tu pareja: {code}\n\n"
            "Envíale a tu pareja este mensaje:\n\n"
            "—\n"
            "No te lo mando como una queja 🙂 Hice un breve check-up de pareja — "
            "haz tu parte, son 5 minutos, las respuestas solo se ven cuando "
            "los dos hayamos terminado: {link}\n"
            "—\n\n"
            "En cuanto tu pareja termine, les envío la tarjeta de resultado a los dos."
        ),
        "result_header": "📋 Resultado del check-up (código {code})\n\n",
        "matched": "Coincidieron {n} de {total} preguntas de opción múltiple.\n\n",
        "diff_header": "Puntos donde las perspectivas difirieron:\n",
        "all_match": "Todas las respuestas de opción múltiple coincidieron 🙂\n\n",
        "open_header": "Temas para conversar (respuestas abiertas):\n",
        "partner1": "Pareja 1",
        "partner2": "Pareja 2",
        "result_footer": (
            "\n\nEsto no es un veredicto — es simplemente un punto de partida para una conversación "
            "que quizás nunca habría ocurrido. En 7 días te propongo hacerlo de nuevo."
        ),
        "reminder": (
            "Ha pasado una semana desde tu último check-up 🙂 "
            "¿Quieres comparar de nuevo? Solo escribe /start."
        ),
        "deleted": "Todos tus datos han sido eliminados.",
        "stopped": (
            "Detenido. Tu pareja no recibirá ningún aviso. "
            "Para eliminar tus respuestas guardadas, usa /delete."
        ),
        "help": "/start — iniciar un nuevo check-up\n/stop — detener\n/delete — eliminar mis datos",
        "not_found": "Ese código no fue encontrado. Verifica el enlace o pide a tu pareja que lo reenvíe.",
        "choose_lang": "Выберите язык / Choose language / Elige idioma:",
    },
}

# ---------------------------------------------------------------------------
# ВОПРОСЫ ПО ЯЗЫКАМ
# ---------------------------------------------------------------------------
QUESTIONS = {
    "ru": [
        {"id":1,"type":"choice","text":"Когда вы в последний раз чувствовали себя по-настоящему услышанными партнёром?","options":["Сегодня / на этой неделе","В этом месяце","Не помню, когда в последний раз"]},
        {"id":2,"type":"text","text":"Одним предложением: в чём, по-вашему, самый большой вклад партнёра в отношения?"},
        {"id":3,"type":"choice","text":"Кто чаще замечает и решает бытовые мелочи (купить, починить, оплатить)?","options":["Я","Партнёр","Примерно поровну"]},
        {"id":4,"type":"text","text":"Одной фразой: из-за чего вы спорите чаще всего?"},
        {"id":5,"type":"choice","text":"Как обычно заканчивается ваша последняя ссора?","options":["Кто-то извиняется первым","Просто затихает само","Обсуждаем до конца"]},
        {"id":6,"type":"choice","text":"Сколько времени вам обычно нужно, чтобы «остыть» после конфликта?","options":["Меньше часа","До конца дня","Больше суток"]},
        {"id":7,"type":"text","text":"Что партнёр делает, что вы считаете проявлением заботы — а он(а), возможно, об этом даже не задумывается?"},
        {"id":8,"type":"choice","text":"Вы чаще говорите о чувствах прямо или ждёте, что партнёр догадается сам?","options":["Говорю прямо","Жду, что догадается"]},
        {"id":9,"type":"choice","text":"Замечает ли партнёр, когда вам нужна поддержка, без слов?","options":["Да, почти всегда","Иногда","Редко"]},
        {"id":10,"type":"text","text":"Если бы можно было изменить одну привычку в том, как вы вдвоём общаетесь — какую?"},
    ],
    "en": [
        {"id":1,"type":"choice","text":"When did you last feel truly heard by your partner?","options":["Today / this week","This month","I can't remember the last time"]},
        {"id":2,"type":"text","text":"In one sentence: what do you think is your partner's greatest contribution to this relationship?"},
        {"id":3,"type":"choice","text":"Who more often notices and handles the small household tasks (buying things, fixing things, paying bills)?","options":["Me","My partner","Roughly equal"]},
        {"id":4,"type":"text","text":"In one phrase: what do you argue about most often?"},
        {"id":5,"type":"choice","text":"How does your last argument usually end?","options":["Someone apologizes first","It just fades out","We talk it through completely"]},
        {"id":6,"type":"choice","text":"How long do you usually need to cool down after a conflict?","options":["Less than an hour","By the end of the day","More than a day"]},
        {"id":7,"type":"text","text":"What does your partner do that you see as care — that they might not even think of as care?"},
        {"id":8,"type":"choice","text":"Do you more often express your feelings directly, or wait for your partner to figure it out?","options":["I say it directly","I wait for them to figure it out"]},
        {"id":9,"type":"choice","text":"Does your partner notice when you need support — without you having to say it?","options":["Yes, almost always","Sometimes","Rarely"]},
        {"id":10,"type":"text","text":"If you could change one habit in the way you two communicate — what would it be?"},
    ],
    "es": [
        {"id":1,"type":"choice","text":"¿Cuándo fue la última vez que te sentiste verdaderamente escuchado/a por tu pareja?","options":["Hoy / esta semana","Este mes","No recuerdo la última vez"]},
        {"id":2,"type":"text","text":"En una frase: ¿cuál crees que es la mayor aportación de tu pareja a la relación?"},
        {"id":3,"type":"choice","text":"¿Quién se ocupa más a menudo de las pequeñas tareas del hogar (compras, reparaciones, pagos)?","options":["Yo","Mi pareja","Más o menos igual"]},
        {"id":4,"type":"text","text":"En una frase: ¿de qué discuten más a menudo?"},
        {"id":5,"type":"choice","text":"¿Cómo suele terminar su última discusión?","options":["Alguien se disculpa primero","Se va apagando sola","Lo hablamos hasta el final"]},
        {"id":6,"type":"choice","text":"¿Cuánto tiempo necesitas normalmente para calmarte después de un conflicto?","options":["Menos de una hora","Para el final del día","Más de un día"]},
        {"id":7,"type":"text","text":"¿Qué hace tu pareja que tú consideras un gesto de cuidado — aunque quizás ella/él ni lo piense así?"},
        {"id":8,"type":"choice","text":"¿Sueles expresar tus sentimientos directamente o esperas a que tu pareja lo intuya?","options":["Lo digo directamente","Espero que lo intuya"]},
        {"id":9,"type":"choice","text":"¿Tu pareja nota cuando necesitas apoyo — sin que tengas que decirlo?","options":["Sí, casi siempre","A veces","Rara vez"]},
        {"id":10,"type":"text","text":"Si pudieras cambiar un hábito en la forma en que se comunican — ¿cuál sería?"},
    ],
}

def get_choice_questions(lang):
    return [q for q in QUESTIONS[lang] if q["type"] == "choice"]

def get_text_questions(lang):
    return [q for q in QUESTIONS[lang] if q["type"] == "text"]

# ---------------------------------------------------------------------------
# БАЗА ДАННЫХ
# ---------------------------------------------------------------------------
def db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""CREATE TABLE IF NOT EXISTS pairs (
        code TEXT PRIMARY KEY, user1_id INTEGER, user2_id INTEGER,
        lang TEXT DEFAULT 'ru', created_at TEXT)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS answers (
        code TEXT, user_id INTEGER, question_id INTEGER, answer TEXT,
        PRIMARY KEY (code, user_id, question_id))""")
    conn.execute("""CREATE TABLE IF NOT EXISTS consent (
        user_id INTEGER PRIMARY KEY, lang TEXT, agreed_at TEXT)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS user_lang (
        user_id INTEGER PRIMARY KEY, lang TEXT)""")
    return conn

def gen_code():
    alphabet = string.ascii_uppercase.replace("O","").replace("I","") + "23456789"
    return "".join(random.choice(alphabet) for _ in range(6))

def get_user_lang(user_id):
    conn = db(); row = conn.execute("SELECT lang FROM user_lang WHERE user_id=?", (user_id,)).fetchone(); conn.close()
    return row[0] if row else None

def set_user_lang(user_id, lang):
    conn = db(); conn.execute("INSERT OR REPLACE INTO user_lang (user_id, lang) VALUES (?,?)", (user_id, lang)); conn.commit(); conn.close()

def create_pair(code, user_id, lang):
    conn = db(); conn.execute("INSERT INTO pairs (code, user1_id, user2_id, lang, created_at) VALUES (?,?,NULL,?,?)", (code, user_id, lang, datetime.utcnow().isoformat())); conn.commit(); conn.close()

def join_pair(code, user_id):
    conn = db()
    row = conn.execute("SELECT user1_id, user2_id, lang FROM pairs WHERE code=?", (code,)).fetchone()
    if not row: conn.close(); return None
    u1, u2, lang = row
    if u2 is None and u1 != user_id:
        conn.execute("UPDATE pairs SET user2_id=? WHERE code=?", (user_id, code)); conn.commit()
    conn.close(); return lang

def save_answer(code, user_id, question_id, answer):
    conn = db(); conn.execute("INSERT OR REPLACE INTO answers (code, user_id, question_id, answer) VALUES (?,?,?,?)", (code, user_id, question_id, answer)); conn.commit(); conn.close()

def user_finished(code, user_id, lang):
    conn = db(); n = conn.execute("SELECT COUNT(*) FROM answers WHERE code=? AND user_id=?", (code, user_id)).fetchone()[0]; conn.close()
    return n >= len(QUESTIONS[lang])

def pair_status(code):
    conn = db(); row = conn.execute("SELECT user1_id, user2_id, lang FROM pairs WHERE code=?", (code,)).fetchone(); conn.close()
    return {"user1_id": row[0], "user2_id": row[1], "lang": row[2]} if row else None

def get_all_answers(code, user_id):
    conn = db(); rows = conn.execute("SELECT question_id, answer FROM answers WHERE code=? AND user_id=? ORDER BY question_id", (code, user_id)).fetchall(); conn.close()
    return {qid: ans for qid, ans in rows}

def set_consent(user_id, lang):
    conn = db(); conn.execute("INSERT OR REPLACE INTO consent (user_id, lang, agreed_at) VALUES (?,?,?)", (user_id, lang, datetime.utcnow().isoformat())); conn.commit(); conn.close()

def delete_user_data(user_id):
    conn = db()
    for tbl in ["answers", "consent", "user_lang"]:
        conn.execute(f"DELETE FROM {tbl} WHERE user_id=?", (user_id,))
    conn.execute("UPDATE pairs SET user1_id=NULL WHERE user1_id=?", (user_id,))
    conn.execute("UPDATE pairs SET user2_id=NULL WHERE user2_id=?", (user_id,))
    conn.commit(); conn.close()

def get_stats():
    conn = db()
    total_users = conn.execute("SELECT COUNT(*) FROM consent").fetchone()[0]
    total_pairs = conn.execute("SELECT COUNT(*) FROM pairs WHERE user2_id IS NOT NULL").fetchone()[0]
    started_only = conn.execute("SELECT COUNT(*) FROM pairs WHERE user2_id IS NULL AND user1_id IS NOT NULL").fetchone()[0]
    by_lang = conn.execute("SELECT lang, COUNT(*) FROM pairs GROUP BY lang").fetchall()
    conn.close()
    return total_users, total_pairs, started_only, by_lang

# ---------------------------------------------------------------------------
# FSM
# ---------------------------------------------------------------------------
class Checkup(StatesGroup):
    choosing_lang = State()
    waiting_consent = State()
    asking = State()

# ---------------------------------------------------------------------------
# БОТ
# ---------------------------------------------------------------------------
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

def lang_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🇷🇺 Русский", callback_data="lang:ru"),
        InlineKeyboardButton(text="🇬🇧 English", callback_data="lang:en"),
        InlineKeyboardButton(text="🇪🇸 Español", callback_data="lang:es"),
    ]])

def consent_keyboard(lang):
    t = UI[lang]
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t["consent_yes"], callback_data="consent_yes")],
        [InlineKeyboardButton(text=t["consent_no"], callback_data="consent_no")],
    ])

def choice_keyboard(options, question_id):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=opt, callback_data=f"ans:{question_id}:{i}")]
        for i, opt in enumerate(options)
    ])

async def ask_next_question(message, state):
    data = await state.get_data()
    idx = data.get("q_index", 0)
    lang = data.get("lang", "ru")
    questions = QUESTIONS[lang]
    if idx >= len(questions):
        await finish_questions(message, state); return
    q = questions[idx]
    await state.set_state(Checkup.asking)
    t = UI[lang]
    prefix = f"{t['question_prefix']} {idx+1}/{len(questions)}\n\n{q['text']}"
    if q["type"] == "choice":
        await message.answer(prefix, reply_markup=choice_keyboard(q["options"], q["id"]))
    else:
        await message.answer(f"{prefix}\n\n{t['text_hint']}")

@dp.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    args = message.text.split(maxsplit=1)
    payload = args[1].strip() if len(args) > 1 else None

    lang = None
    code = None

    if payload:
        # Форматы: q1_ru-КОД (партнёр 2) или q1_ru (партнёр 1 с языком)
        if "-" in payload:
            lang_part, code = payload.rsplit("-", 1)
            lang = lang_part.split("_")[-1] if "_" in lang_part else None
        elif "_" in payload:
            lang = payload.split("_")[-1]

        if lang not in ("ru", "en", "es"):
            lang = get_user_lang(message.from_user.id) or "ru"

        if code:
            detected_lang = join_pair(code, message.from_user.id)
            if detected_lang is None:
                await message.answer(UI[lang]["not_found"]); return
            lang = detected_lang
            await state.update_data(code=code, lang=lang)
            set_user_lang(message.from_user.id, lang)
            await message.answer(UI[lang]["consent"], reply_markup=consent_keyboard(lang))
            await state.set_state(Checkup.waiting_consent); return

        # Партнёр 1, язык из ссылки
        set_user_lang(message.from_user.id, lang)
        new_code = gen_code()
        create_pair(new_code, message.from_user.id, lang)
        await state.update_data(code=new_code, lang=lang)
        await message.answer(UI[lang]["consent"], reply_markup=consent_keyboard(lang))
        await state.set_state(Checkup.waiting_consent)
        return

    # Нет параметра — спрашиваем язык
    lang = get_user_lang(message.from_user.id)
    if lang:
        new_code = gen_code()
        create_pair(new_code, message.from_user.id, lang)
        await state.update_data(code=new_code, lang=lang)
        await message.answer(UI[lang]["consent"], reply_markup=consent_keyboard(lang))
        await state.set_state(Checkup.waiting_consent)
    else:
        await message.answer(UI["ru"]["choose_lang"], reply_markup=lang_keyboard())
        await state.set_state(Checkup.choosing_lang)

@dp.callback_query(F.data.startswith("lang:"))
async def choose_lang(callback: CallbackQuery, state: FSMContext):
    lang = callback.data.split(":")[1]
    set_user_lang(callback.from_user.id, lang)
    new_code = gen_code()
    create_pair(new_code, callback.from_user.id, lang)
    await state.update_data(code=new_code, lang=lang)
    await callback.message.answer(UI[lang]["consent"], reply_markup=consent_keyboard(lang))
    await state.set_state(Checkup.waiting_consent)
    await callback.answer()

@dp.callback_query(F.data == "consent_no")
async def consent_no(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data(); lang = data.get("lang", "ru")
    await callback.message.answer(UI[lang]["consent_no_reply"])
    await state.clear(); await callback.answer()

@dp.callback_query(F.data == "consent_yes")
async def consent_yes(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data(); lang = data.get("lang", "ru")
    set_consent(callback.from_user.id, lang)
    await state.update_data(q_index=0)
    await callback.message.answer(UI[lang]["start_msg"])
    await ask_next_question(callback.message, state)
    await callback.answer()

@dp.callback_query(F.data.startswith("ans:"))
async def handle_choice(callback: CallbackQuery, state: FSMContext):
    _, qid, opt_idx = callback.data.split(":"); qid, opt_idx = int(qid), int(opt_idx)
    data = await state.get_data(); lang = data.get("lang", "ru")
    q = next(x for x in QUESTIONS[lang] if x["id"] == qid)
    answer_text = q["options"][opt_idx]
    save_answer(data["code"], callback.from_user.id, qid, answer_text)
    t = UI[lang]
    await callback.message.edit_text(f"{q['text']}\n\n{t['your_answer']}: {answer_text} ✅")
    await state.update_data(q_index=data.get("q_index", 0) + 1)
    await ask_next_question(callback.message, state)
    await callback.answer()

@dp.message(Checkup.asking)
async def handle_text_answer(message: Message, state: FSMContext):
    data = await state.get_data(); idx = data.get("q_index", 0); lang = data.get("lang", "ru")
    questions = QUESTIONS[lang]
    if idx >= len(questions): return
    q = questions[idx]
    if q["type"] != "text":
        await message.answer(UI[lang]["choose_option"]); return
    save_answer(data["code"], message.from_user.id, q["id"], message.text.strip())
    await state.update_data(q_index=idx + 1)
    await ask_next_question(message, state)

async def finish_questions(message, state):
    data = await state.get_data()
    code = data["code"]; lang = data.get("lang", "ru")
    user_id = message.chat.id
    status = pair_status(code)
    other_id = None
    if status:
        if status["user1_id"] == message.from_user.id: other_id = status["user2_id"]
        elif status["user2_id"] == message.from_user.id: other_id = status["user1_id"]

    if other_id is None:
        bot_username = (await bot.get_me()).username
        # Ссылка с языком зашита: q1_LANG-КОД
        link = f"https://t.me/{bot_username}?start=q1_{lang}-{code}"
        await message.answer(UI[lang]["invite_msg"].format(code=code, link=link))
    else:
        if user_finished(code, other_id, lang):
            await send_results(code)
        else:
            await message.answer(UI[lang]["finished_wait"])
    await state.clear()

async def send_results(code):
    status = pair_status(code)
    u1, u2, lang = status["user1_id"], status["user2_id"], status["lang"]
    t = UI[lang]
    ans1 = get_all_answers(code, u1); ans2 = get_all_answers(code, u2)
    cq = get_choice_questions(lang); tq = get_text_questions(lang)
    matches = 0; diff_lines = []
    for q in cq:
        a1, a2 = ans1.get(q["id"], "—"), ans2.get(q["id"], "—")
        if a1 == a2: matches += 1
        else: diff_lines.append(f"• {q['text']}\n   {t['partner1']}: {a1}\n   {t['partner2']}: {a2}")
    result = t["result_header"].format(code=code)
    result += t["matched"].format(n=matches, total=len(cq))
    if diff_lines: result += t["diff_header"] + "\n\n".join(diff_lines) + "\n\n"
    else: result += t["all_match"]
    open_lines = []
    for q in tq:
        a1, a2 = ans1.get(q["id"], "—"), ans2.get(q["id"], "—")
        open_lines.append(f"• {q['text']}\n   {t['partner1']}: «{a1}»\n   {t['partner2']}: «{a2}»")
    result += t["open_header"] + "\n\n".join(open_lines) + t["result_footer"]
    for uid in (u1, u2):
        try: await bot.send_message(uid, result)
        except Exception as e: log.warning(f"Не удалось отправить результат {uid}: {e}")

@dp.message(Command("stats"))
async def cmd_stats(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    total_users, total_pairs, started_only, by_lang = get_stats()
    lang_lines = "\n".join(f"  {l}: {n} пар" for l, n in by_lang)
    await message.answer(
        f"📊 Статистика бота\n\n"
        f"Всего пользователей (дали согласие): {total_users}\n"
        f"Пар завершили оба партнёра: {total_pairs}\n"
        f"Начали, партнёр ещё не присоединился: {started_only}\n\n"
        f"По языкам:\n{lang_lines}"
    )

@dp.message(Command("delete"))
async def cmd_delete(message: Message, state: FSMContext):
    lang = get_user_lang(message.from_user.id) or "ru"
    delete_user_data(message.from_user.id)
    await state.clear()
    await message.answer(UI[lang]["deleted"])

@dp.message(Command("stop"))
async def cmd_stop(message: Message, state: FSMContext):
    lang = get_user_lang(message.from_user.id) or "ru"
    await state.clear()
    await message.answer(UI[lang]["stopped"])

@dp.message(Command("help"))
async def cmd_help(message: Message):
    lang = get_user_lang(message.from_user.id) or "ru"
    await message.answer(UI[lang]["help"])

async def reminder_loop():
    while True:
        await asyncio.sleep(60 * 60 * 6)
        conn = db()
        week_ago = (datetime.utcnow() - timedelta(days=7)).isoformat()
        rows = conn.execute(
            "SELECT code, user1_id, user2_id, lang FROM pairs "
            "WHERE user1_id IS NOT NULL AND user2_id IS NOT NULL AND created_at <= ?",
            (week_ago,)
        ).fetchall(); conn.close()
        for code, u1, u2, lang in rows:
            msg = UI.get(lang, UI["ru"])["reminder"]
            for uid in (u1, u2):
                try: await bot.send_message(uid, msg)
                except Exception as e: log.warning(f"Напоминание не доставлено {uid}: {e}")

async def main():
    asyncio.create_task(reminder_loop())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
