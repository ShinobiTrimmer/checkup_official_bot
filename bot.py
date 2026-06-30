"""
Бот «Чек-ап пары» — пилот №1: «10 вопросов, на которые пары отвечают по-разному»

Логика:
1. Первый партнёр пишет /start -> бот создаёт уникальный код пары и проводит его
   через 10 вопросов (раздельно, по одному).
2. Бот выдаёт код и готовое сообщение для пересылки партнёру.
3. Партнёр переходит по ссылке вида https://t.me/ИМЯ_БОТА?start=КОД (или вручную
   вводит код через /join КОД), проходит те же 10 вопросов.
4. Как только ОБА завершили — бот присылает каждому карточку результата:
   - число совпадений по 6 вопросам с вариантами ответа;
   - 4 открытых вопроса показаны рядом для обсуждения (без оценки "правильно/неправильно").
5. Через 7 дней бот сам присылает обоим участникам напоминание пройти чек-ап снова.

Хранилище: локальная SQLite-база (файл checkup.db). Для MVP этого достаточно.
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
    raise RuntimeError("Не найден BOT_TOKEN. Задайте переменную окружения BOT_TOKEN.")

DB_PATH = os.environ.get("DB_PATH", "checkup.db")

# ---------------------------------------------------------------------------
# ВОПРОСЫ ПИЛОТА №1
# type: "choice" -> сравниваем напрямую (совпало / не совпало)
# type: "text"   -> показываем рядом как тему для разговора, без оценки
# ---------------------------------------------------------------------------
QUESTIONS = [
    {
        "id": 1,
        "type": "choice",
        "text": "Когда вы в последний раз чувствовали себя по-настоящему услышанными партнёром?",
        "options": ["Сегодня / на этой неделе", "В этом месяце", "Не помню, когда в последний раз"],
    },
    {
        "id": 2,
        "type": "text",
        "text": "Одним предложением: в чём, по-вашему, самый большой вклад партнёра в отношения?",
    },
    {
        "id": 3,
        "type": "choice",
        "text": "Кто чаще замечает и решает бытовые мелочи (купить, починить, оплатить)?",
        "options": ["Я", "Партнёр", "Примерно поровну"],
    },
    {
        "id": 4,
        "type": "text",
        "text": "Одной фразой: из-за чего вы спорите чаще всего?",
    },
    {
        "id": 5,
        "type": "choice",
        "text": "Как обычно заканчивается ваша последняя ссора?",
        "options": ["Кто-то извиняется первым", "Просто затихает само", "Обсуждаем до конца"],
    },
    {
        "id": 6,
        "type": "choice",
        "text": "Сколько времени вам обычно нужно, чтобы «остыть» после конфликта?",
        "options": ["Меньше часа", "До конца дня", "Больше суток"],
    },
    {
        "id": 7,
        "type": "text",
        "text": "Что партнёр делает, что вы считаете проявлением заботы — а он(а), возможно, об этом даже не задумывается?",
    },
    {
        "id": 8,
        "type": "choice",
        "text": "Вы чаще говорите о чувствах прямо или ждёте, что партнёр догадается сам?",
        "options": ["Говорю прямо", "Жду, что догадается"],
    },
    {
        "id": 9,
        "type": "choice",
        "text": "Замечает ли партнёр, когда вам нужна поддержка, без слов?",
        "options": ["Да, почти всегда", "Иногда", "Редко"],
    },
    {
        "id": 10,
        "type": "text",
        "text": "Если бы можно было изменить одну привычку в том, как вы вдвоём общаетесь — какую?",
    },
]

CHOICE_QUESTIONS = [q for q in QUESTIONS if q["type"] == "choice"]
TEXT_QUESTIONS = [q for q in QUESTIONS if q["type"] == "text"]


# ---------------------------------------------------------------------------
# БАЗА ДАННЫХ
# ---------------------------------------------------------------------------
def db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS pairs (
            code TEXT PRIMARY KEY,
            user1_id INTEGER,
            user2_id INTEGER,
            created_at TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS answers (
            code TEXT,
            user_id INTEGER,
            question_id INTEGER,
            answer TEXT,
            PRIMARY KEY (code, user_id, question_id)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS consent (
            user_id INTEGER PRIMARY KEY,
            agreed_at TEXT
        )
    """)
    return conn


def gen_code() -> str:
    alphabet = string.ascii_uppercase.replace("O", "").replace("I", "") + "23456789"
    return "".join(random.choice(alphabet) for _ in range(6))


def create_pair(code: str, user_id: int):
    conn = db()
    conn.execute(
        "INSERT INTO pairs (code, user1_id, user2_id, created_at) VALUES (?, ?, NULL, ?)",
        (code, user_id, datetime.utcnow().isoformat()),
    )
    conn.commit()
    conn.close()


def join_pair(code: str, user_id: int) -> bool:
    conn = db()
    row = conn.execute("SELECT user1_id, user2_id FROM pairs WHERE code=?", (code,)).fetchone()
    if not row:
        conn.close()
        return False
    user1_id, user2_id = row
    if user1_id == user_id:
        conn.close()
        return True  # это тот же человек, не второй партнёр
    if user2_id is None:
        conn.execute("UPDATE pairs SET user2_id=? WHERE code=?", (user_id, code))
        conn.commit()
    conn.close()
    return True


def save_answer(code: str, user_id: int, question_id: int, answer: str):
    conn = db()
    conn.execute(
        "INSERT OR REPLACE INTO answers (code, user_id, question_id, answer) VALUES (?, ?, ?, ?)",
        (code, user_id, question_id, answer),
    )
    conn.commit()
    conn.close()


def user_finished(code: str, user_id: int) -> bool:
    conn = db()
    n = conn.execute(
        "SELECT COUNT(*) FROM answers WHERE code=? AND user_id=?", (code, user_id)
    ).fetchone()[0]
    conn.close()
    return n >= len(QUESTIONS)


def pair_status(code: str):
    conn = db()
    row = conn.execute("SELECT user1_id, user2_id FROM pairs WHERE code=?", (code,)).fetchone()
    conn.close()
    if not row:
        return None
    return {"user1_id": row[0], "user2_id": row[1]}


def get_all_answers(code: str, user_id: int):
    conn = db()
    rows = conn.execute(
        "SELECT question_id, answer FROM answers WHERE code=? AND user_id=? ORDER BY question_id",
        (code, user_id),
    ).fetchall()
    conn.close()
    return {qid: ans for qid, ans in rows}


def delete_user_data(user_id: int):
    conn = db()
    conn.execute("DELETE FROM answers WHERE user_id=?", (user_id,))
    conn.execute(
        "UPDATE pairs SET user1_id=NULL WHERE user1_id=?", (user_id,)
    )
    conn.execute(
        "UPDATE pairs SET user2_id=NULL WHERE user2_id=?", (user_id,)
    )
    conn.execute("DELETE FROM consent WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()


def set_consent(user_id: int):
    conn = db()
    conn.execute(
        "INSERT OR REPLACE INTO consent (user_id, agreed_at) VALUES (?, ?)",
        (user_id, datetime.utcnow().isoformat()),
    )
    conn.commit()
    conn.close()


def has_consent(user_id: int) -> bool:
    conn = db()
    row = conn.execute("SELECT 1 FROM consent WHERE user_id=?", (user_id,)).fetchone()
    conn.close()
    return row is not None


# ---------------------------------------------------------------------------
# FSM-СОСТОЯНИЯ
# ---------------------------------------------------------------------------
class Checkup(StatesGroup):
    waiting_consent = State()
    asking = State()


# ---------------------------------------------------------------------------
# БОТ
# ---------------------------------------------------------------------------
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())


def consent_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Согласен(на), начать", callback_data="consent_yes")],
            [InlineKeyboardButton(text="Не сейчас", callback_data="consent_no")],
        ]
    )


def choice_keyboard(options, question_id):
    rows = [
        [InlineKeyboardButton(text=opt, callback_data=f"ans:{question_id}:{i}")]
        for i, opt in enumerate(options)
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


CONSENT_TEXT = (
    "Прежде чем начать — коротко.\n\n"
    "Это не терапия и не диагностика. Это короткий чек-ап для разговора с партнёром.\n"
    "Ваши ответы видит только бот, пока партнёр не завершит свою часть — после этого "
    "вы оба увидите общую карточку результата.\n\n"
    "Если в какой-то момент вам небезопасно показывать ответы партнёру — вы можете "
    "остановиться в любой момент командой /stop, партнёр не получит уведомления.\n\n"
    "Данные можно удалить в любой момент командой /delete.\n\n"
    "Продолжая, вы соглашаетесь на хранение ваших ответов для этого чек-апа."
)


@dp.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, command: Command = None):
    args = message.text.split(maxsplit=1)
    payload = args[1].strip().upper() if len(args) > 1 else None

    if payload:
        # переход по ссылке с кодом пары — это второй партнёр (или владелец кода)
        ok = join_pair(payload, message.from_user.id)
        if not ok:
            await message.answer(
                "Такой код не найден. Проверьте ссылку или попросите партнёра отправить её заново."
            )
            return
        await state.update_data(code=payload)
        await message.answer(CONSENT_TEXT, reply_markup=consent_keyboard())
        await state.set_state(Checkup.waiting_consent)
        return

    # первый партнёр, новый чек-ап
    code = gen_code()
    create_pair(code, message.from_user.id)
    await state.update_data(code=code)
    await message.answer(CONSENT_TEXT, reply_markup=consent_keyboard())
    await state.set_state(Checkup.waiting_consent)


@dp.callback_query(F.data == "consent_no")
async def consent_no(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("Хорошо, возвращайтесь, когда будете готовы — просто напишите /start.")
    await state.clear()
    await callback.answer()


@dp.callback_query(F.data == "consent_yes")
async def consent_yes(callback: CallbackQuery, state: FSMContext):
    set_consent(callback.from_user.id)
    await state.update_data(q_index=0)
    await callback.message.answer("Отлично. Отвечайте честно — здесь нет «правильных» ответов.")
    await ask_next_question(callback.message, state)
    await callback.answer()


async def ask_next_question(message: Message, state: FSMContext):
    data = await state.get_data()
    idx = data.get("q_index", 0)

    if idx >= len(QUESTIONS):
        await finish_questions(message, state)
        return

    q = QUESTIONS[idx]
    await state.set_state(Checkup.asking)
    if q["type"] == "choice":
        await message.answer(
            f"Вопрос {idx + 1}/10\n\n{q['text']}", reply_markup=choice_keyboard(q["options"], q["id"])
        )
    else:
        await message.answer(f"Вопрос {idx + 1}/10\n\n{q['text']}\n\n(ответьте текстом одним сообщением)")


@dp.callback_query(F.data.startswith("ans:"))
async def handle_choice_answer(callback: CallbackQuery, state: FSMContext):
    _, qid, opt_idx = callback.data.split(":")
    qid, opt_idx = int(qid), int(opt_idx)
    q = next(x for x in QUESTIONS if x["id"] == qid)
    answer_text = q["options"][opt_idx]

    data = await state.get_data()
    code = data["code"]
    save_answer(code, callback.from_user.id, qid, answer_text)

    await callback.message.edit_text(f"{q['text']}\n\nВаш ответ: {answer_text} ✅")
    await state.update_data(q_index=data.get("q_index", 0) + 1)
    await ask_next_question(callback.message, state)
    await callback.answer()


@dp.message(Checkup.asking)
async def handle_text_answer(message: Message, state: FSMContext):
    data = await state.get_data()
    idx = data.get("q_index", 0)
    if idx >= len(QUESTIONS):
        return
    q = QUESTIONS[idx]
    if q["type"] != "text":
        await message.answer("Пожалуйста, выберите один из вариантов выше ⬆️")
        return

    save_answer(data["code"], message.from_user.id, q["id"], message.text.strip())
    await state.update_data(q_index=idx + 1)
    await ask_next_question(message, state)


async def finish_questions(message: Message, state: FSMContext):
    data = await state.get_data()
    code = data["code"]
    user_id = message.chat.id

    status = pair_status(code)
    other_id = None
    if status:
        if status["user1_id"] == message.from_user.id:
            other_id = status["user2_id"]
        elif status["user2_id"] == message.from_user.id:
            other_id = status["user1_id"]

    if other_id is None:
        bot_username = (await bot.get_me()).username
        link = f"https://t.me/{bot_username}?start={code}"
        await message.answer(
            "Готово! Вы прошли все 10 вопросов.\n\n"
            f"Код вашей пары: {code}\n\n"
            "Отправьте партнёру это сообщение:\n\n"
            "—\n"
            "Не отправляю это как претензию 🙂 Я прошёл(шла) короткий чек-ап для пар, "
            f"пройди свою часть — займёт 5 минут, ответы видны только после того, как оба закончат: {link}\n"
            "—\n\n"
            "Как только партнёр завершит свою часть — пришлю вам обоим карточку результата."
        )
    else:
        if user_finished(code, other_id):
            await send_results(code)
        else:
            await message.answer(
                "Готово! Ваши ответы сохранены. Как только партнёр закончит свою часть — "
                "пришлю результат вам обоим."
            )

    await state.clear()


async def send_results(code: str):
    status = pair_status(code)
    u1, u2 = status["user1_id"], status["user2_id"]
    ans1 = get_all_answers(code, u1)
    ans2 = get_all_answers(code, u2)

    matches = 0
    diff_choice_lines = []
    for q in CHOICE_QUESTIONS:
        a1, a2 = ans1.get(q["id"], "—"), ans2.get(q["id"], "—")
        if a1 == a2:
            matches += 1
        else:
            diff_choice_lines.append(f"• {q['text']}\n   Партнёр 1: {a1}\n   Партнёр 2: {a2}")

    text_lines = []
    for q in TEXT_QUESTIONS:
        a1, a2 = ans1.get(q["id"], "—"), ans2.get(q["id"], "—")
        text_lines.append(f"• {q['text']}\n   Партнёр 1: «{a1}»\n   Партнёр 2: «{a2}»")

    result = (
        f"📋 Результат чек-апа (код {code})\n\n"
        f"Совпало {matches} из {len(CHOICE_QUESTIONS)} вопросов с вариантами ответа.\n\n"
    )
    if diff_choice_lines:
        result += "Точки, где взгляды разошлись:\n" + "\n\n".join(diff_choice_lines) + "\n\n"
    else:
        result += "По всем закрытым вопросам взгляды совпали — это уже отдельный повод поговорить о том, почему 🙂\n\n"

    result += "Темы для разговора (открытые ответы, без оценки «правильно/неправильно»):\n" + "\n\n".join(text_lines)
    result += (
        "\n\nЭто не вердикт — просто повод обсудить то, что обычно остаётся непроговорённым. "
        "Через 7 дней я предложу пройти короткий повтор."
    )

    for uid in (u1, u2):
        try:
            await bot.send_message(uid, result)
        except Exception as e:
            log.warning(f"Не удалось отправить результат {uid}: {e}")


@dp.message(Command("delete"))
async def cmd_delete(message: Message, state: FSMContext):
    delete_user_data(message.from_user.id)
    await state.clear()
    await message.answer("Все ваши данные удалены.")


@dp.message(Command("stop"))
async def cmd_stop(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "Остановлено. Партнёр не получит никакого уведомления об этом. "
        "Если захотите удалить уже сохранённые ответы — используйте /delete."
    )


@dp.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(
        "/start — начать новый чек-ап\n"
        "/stop — остановиться без уведомления партнёра\n"
        "/delete — удалить все свои данные\n"
    )


# ---------------------------------------------------------------------------
# НАПОМИНАНИЕ ЧЕРЕЗ 7 ДНЕЙ (фоновая задача)
# ---------------------------------------------------------------------------
async def reminder_loop():
    while True:
        await asyncio.sleep(60 * 60 * 6)  # проверка каждые 6 часов
        conn = db()
        week_ago = (datetime.utcnow() - timedelta(days=7)).isoformat()
        rows = conn.execute(
            "SELECT code, user1_id, user2_id, created_at FROM pairs "
            "WHERE user1_id IS NOT NULL AND user2_id IS NOT NULL AND created_at <= ?",
            (week_ago,),
        ).fetchall()
        conn.close()
        for code, u1, u2, _ in rows:
            for uid in (u1, u2):
                try:
                    await bot.send_message(
                        uid,
                        "Прошла неделя с вашего последнего чек-апа 🙂 "
                        "Хотите быстро свериться снова? Напишите /start.",
                    )
                except Exception as e:
                    log.warning(f"Напоминание не доставлено {uid}: {e}")


async def main():
    asyncio.create_task(reminder_loop())
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
