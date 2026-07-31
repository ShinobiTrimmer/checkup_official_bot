"""
Бот «Чек-ап пары» — v2, поддержка нескольких чек-апов и трёх языков.

Ссылки из описаний видео:
  Видео 1 RU: ?start=q1_ru   EN: ?start=q1_en   ES: ?start=q1_es
  Видео 2 RU: ?start=q2_ru   EN: ?start=q2_en   ES: ?start=q2_es
  Видео 7 RU: ?start=q4_ru   EN: ?start=q4_en   ES: ?start=q4_es
  Видео 8 RU: ?start=q5_ru   EN: ?start=q5_en   ES: ?start=q5_es
  Видео 9 RU: ?start=q6_ru   EN: ?start=q6_en   ES: ?start=q6_es
  Видео 10 RU: ?start=q7_ru   EN: ?start=q7_en   ES: ?start=q7_es
  Языки любви RU: ?start=q8_ru   EN: ?start=q8_en   ES: ?start=q8_es
  Привязанность RU: ?start=q9_ru   EN: ?start=q9_en   ES: ?start=q9_es
  Презрение RU: ?start=q10_ru   EN: ?start=q10_en   ES: ?start=q10_es

Партнёр переходит по ссылке: ?start=q1_ru-КОД
Бот сам определяет чек-ап и язык из параметра.
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
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("checkup_bot")

BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN не найден.")

DB_PATH = os.environ.get("DB_PATH", "checkup.db")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))

# ---------------------------------------------------------------------------
# ТЕКСТЫ ИНТЕРФЕЙСА
# ---------------------------------------------------------------------------
UI = {
    "ru": {
        "consent": (
            "Прежде чем начать — коротко.\n\n"
            "Это не терапия и не диагностика. Это короткий чек-ап для разговора с партнёром.\n"
            "Ваши ответы видит только бот, пока партнёр не завершит свою часть.\n\n"
            "Остановиться можно в любой момент командой /stop — партнёр не получит уведомления.\n"
            "Удалить данные: /delete.\n\n"
            "Продолжая, вы соглашаетесь на хранение ваших ответов для этого чек-апа."
        ),
        "consent_yes": "Согласен(на), начать",
        "consent_no": "Не сейчас",
        "consent_no_reply": "Хорошо, возвращайтесь когда будете готовы — просто напишите /start.",
        "start_msg": "Отлично. Отвечайте честно — здесь нет правильных ответов.",
        "question_prefix": "Вопрос",
        "text_hint": "(ответьте текстом — одним сообщением)",
        "choose_option": "Пожалуйста, выберите один из вариантов выше ⬆️",
        "your_answer": "Ваш ответ",
        "finished_wait": "Готово! Как только партнёр закончит свою часть — пришлю результат вам обоим.",
        "invite_msg": (
            "Готово! Вы прошли все вопросы.\n\n"
            "Код вашей пары: {code}\n\n"
            "Отправьте партнёру это сообщение:\n\n—\n"
            "Не отправляю это как претензию 🙂 Я прошёл(шла) короткий чек-ап для пар, "
            "пройди свою часть — займёт 5 минут, ответы видны только после того, "
            "как оба закончат: {link}\n—\n\n"
            "Как только партнёр завершит — пришлю карточку результата."
        ),
        "result_header": "📋 Результат чек-апа (код {code})\n\n",
        "matched": "Совпало {n} из {total} закрытых вопросов.\n\n",
        "diff_header": "Точки, где взгляды разошлись:\n",
        "all_match": "По всем закрытым вопросам взгляды совпали 🙂\n\n",
        "open_header": "Темы для разговора (открытые ответы, без оценки):\n",
        "partner1": "Партнёр 1",
        "partner2": "Партнёр 2",
        "result_footer": (
            "\n\nЭто не вердикт — просто повод обсудить то, что обычно остаётся непроговорённым. "
            "Через 7 дней предложу пройти снова."
        ),
        "reminder": "Прошла неделя с вашего последнего чек-апа 🙂 Хотите свериться снова? Напишите /start.",
        "deleted": "Все ваши данные удалены.",
        "stopped": "Остановлено. Партнёр не получит уведомления. Для удаления данных — /delete.",
        "help": "/start — начать чек-ап\n/stop — остановиться\n/delete — удалить мои данные",
        "not_found": "Такой код не найден. Проверьте ссылку или попросите партнёра отправить её заново.",
        "choose_lang": "Выберите язык / Choose language / Elige idioma:",
    },
    "en": {
        "consent": (
            "Before we start — a quick note.\n\n"
            "This is not therapy and not a clinical assessment. "
            "It's a short check-up to start a conversation with your partner.\n"
            "Your answers are only visible to the bot until your partner finishes.\n\n"
            "Stop anytime with /stop — your partner won't be notified.\n"
            "Delete your data anytime with /delete.\n\n"
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
        "finished_wait": "Done! As soon as your partner finishes, I'll send you both the result.",
        "invite_msg": (
            "Done! You've answered all the questions.\n\n"
            "Your pair code: {code}\n\n"
            "Send your partner this message:\n\n—\n"
            "Not sending this as a complaint 🙂 I did a short couples check-up — "
            "go through your part, it takes 5 minutes, answers are only visible once "
            "we've both finished: {link}\n—\n\n"
            "Once your partner finishes, I'll send you both the result card."
        ),
        "result_header": "📋 Check-up result (code {code})\n\n",
        "matched": "Matched {n} out of {total} multiple-choice questions.\n\n",
        "diff_header": "Where your perspectives differed:\n",
        "all_match": "All multiple-choice answers matched 🙂\n\n",
        "open_header": "Topics for conversation (open answers, no judgment):\n",
        "partner1": "Partner 1",
        "partner2": "Partner 2",
        "result_footer": (
            "\n\nThis isn't a verdict — just a starting point for a conversation "
            "that might otherwise not happen. In 7 days I'll suggest doing this again."
        ),
        "reminder": "It's been a week since your last check-up 🙂 Want to compare notes again? Just send /start.",
        "deleted": "All your data has been deleted.",
        "stopped": "Stopped. Your partner won't receive any notification. To delete data, use /delete.",
        "help": "/start — begin a check-up\n/stop — stop anytime\n/delete — delete my data",
        "not_found": "That code wasn't found. Check the link or ask your partner to resend it.",
        "choose_lang": "Выберите язык / Choose language / Elige idioma:",
    },
    "es": {
        "consent": (
            "Antes de empezar — una nota rápida.\n\n"
            "Esto no es terapia ni un diagnóstico. Es un breve check-up "
            "para generar una conversación con tu pareja.\n"
            "Tus respuestas solo las ve el bot hasta que tu pareja termine su parte.\n\n"
            "Puedes detenerte en cualquier momento con /stop — tu pareja no recibirá aviso.\n"
            "Eliminar tus datos: /delete.\n\n"
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
        "finished_wait": "¡Listo! En cuanto tu pareja termine, les envío el resultado a los dos.",
        "invite_msg": (
            "¡Listo! Has respondido todas las preguntas.\n\n"
            "El código de tu pareja: {code}\n\n"
            "Envíale a tu pareja este mensaje:\n\n—\n"
            "No te lo mando como una queja 🙂 Hice un breve check-up de pareja — "
            "haz tu parte, son 5 minutos, las respuestas solo se ven cuando "
            "los dos hayamos terminado: {link}\n—\n\n"
            "En cuanto tu pareja termine, les envío la tarjeta de resultado."
        ),
        "result_header": "📋 Resultado del check-up (código {code})\n\n",
        "matched": "Coincidieron {n} de {total} preguntas de opción múltiple.\n\n",
        "diff_header": "Puntos donde las perspectivas difirieron:\n",
        "all_match": "Todas las respuestas de opción múltiple coincidieron 🙂\n\n",
        "open_header": "Temas para conversar (respuestas abiertas, sin juicio):\n",
        "partner1": "Pareja 1",
        "partner2": "Pareja 2",
        "result_footer": (
            "\n\nEsto no es un veredicto — es simplemente un punto de partida. "
            "En 7 días te propongo hacerlo de nuevo."
        ),
        "reminder": "Ha pasado una semana 🙂 ¿Quieres comparar de nuevo? Solo escribe /start.",
        "deleted": "Todos tus datos han sido eliminados.",
        "stopped": "Detenido. Tu pareja no recibirá ningún aviso. Para eliminar datos, usa /delete.",
        "help": "/start — iniciar un check-up\n/stop — detener\n/delete — eliminar mis datos",
        "not_found": "Ese código no fue encontrado. Verifica el enlace o pide a tu pareja que lo reenvíe.",
        "choose_lang": "Выберите язык / Choose language / Elige idioma:",
    },
}

# ---------------------------------------------------------------------------
# ВСЕ ВОПРОСЫ: ТРИ ЧЕК-АПА × ТРИ ЯЗЫКА
# ---------------------------------------------------------------------------
ALL_QUESTIONS = {

    # ── ЧЕК-АП 1: «10 вопросов, на которые пары отвечают по-разному» ────────
    "q1": {
        "ru": [
            {"id":1,"type":"choice","text":"Когда вы в последний раз чувствовали себя по-настоящему услышанными партнёром?","options":["Сегодня / на этой неделе","В этом месяце","Не помню, когда в последний раз"]},
            {"id":2,"type":"text","text":"Одним предложением: в чём, по-вашему, самый большой вклад партнёра в отношения?"},
            {"id":3,"type":"choice","text":"Кто чаще замечает и решает бытовые мелочи (купить, починить, оплатить)?","options":["Я","Партнёр","Примерно поровну"]},
            {"id":4,"type":"text","text":"Одной фразой: из-за чего вы спорите чаще всего?"},
            {"id":5,"type":"choice","text":"Как обычно заканчивается ваша последняя ссора?","options":["Кто-то извиняется первым","Просто затихает само","Обсуждаем до конца"]},
            {"id":6,"type":"choice","text":"Сколько времени вам нужно, чтобы «остыть» после конфликта?","options":["Меньше часа","До конца дня","Больше суток"]},
            {"id":7,"type":"text","text":"Что партнёр делает, что вы считаете заботой — а он(а), возможно, об этом не задумывается?"},
            {"id":8,"type":"choice","text":"Вы чаще говорите о чувствах прямо или ждёте, что партнёр догадается сам?","options":["Говорю прямо","Жду, что догадается"]},
            {"id":9,"type":"choice","text":"Замечает ли партнёр, когда вам нужна поддержка, без слов?","options":["Да, почти всегда","Иногда","Редко"]},
            {"id":10,"type":"text","text":"Если бы можно было изменить одну привычку в том, как вы вдвоём общаетесь — какую?"},
        ],
        "en": [
            {"id":1,"type":"choice","text":"When did you last feel truly heard by your partner?","options":["Today or this week","This month","I can't remember the last time"]},
            {"id":2,"type":"text","text":"In one sentence: what do you think is your partner's greatest contribution to this relationship?"},
            {"id":3,"type":"choice","text":"Who more often notices and handles the small household tasks?","options":["Me","My partner","Roughly equal"]},
            {"id":4,"type":"text","text":"In one phrase: what do you argue about most often?"},
            {"id":5,"type":"choice","text":"How does your last argument usually end?","options":["Someone apologizes first","It just fades out","We talk it through completely"]},
            {"id":6,"type":"choice","text":"How long do you usually need to cool down after a conflict?","options":["Less than an hour","By the end of the day","More than a day"]},
            {"id":7,"type":"text","text":"What does your partner do that you see as care — that they might not even think of as care?"},
            {"id":8,"type":"choice","text":"Do you more often express your feelings directly, or wait for your partner to figure it out?","options":["I say it directly","I wait for them to figure it out"]},
            {"id":9,"type":"choice","text":"Does your partner notice when you need support — without you having to say it?","options":["Yes, almost always","Sometimes","Rarely"]},
            {"id":10,"type":"text","text":"If you could change one communication habit between you — what would it be?"},
        ],
        "es": [
            {"id":1,"type":"choice","text":"¿Cuándo fue la última vez que te sentiste verdaderamente escuchado/a por tu pareja?","options":["Hoy o esta semana","Este mes","No recuerdo la última vez"]},
            {"id":2,"type":"text","text":"En una frase: ¿cuál crees que es la mayor aportación de tu pareja a la relación?"},
            {"id":3,"type":"choice","text":"¿Quién se ocupa más de las pequeñas tareas del hogar?","options":["Yo","Mi pareja","Más o menos igual"]},
            {"id":4,"type":"text","text":"En una frase: ¿de qué discuten más a menudo?"},
            {"id":5,"type":"choice","text":"¿Cómo suele terminar su última discusión?","options":["Alguien se disculpa primero","Se va apagando sola","Lo hablamos hasta el final"]},
            {"id":6,"type":"choice","text":"¿Cuánto tiempo necesitas para calmarte después de un conflicto?","options":["Menos de una hora","Para el final del día","Más de un día"]},
            {"id":7,"type":"text","text":"¿Qué hace tu pareja que consideras un gesto de cuidado — aunque quizás ella/él ni lo piense así?"},
            {"id":8,"type":"choice","text":"¿Sueles expresar tus sentimientos directamente o esperas que tu pareja lo intuya?","options":["Lo digo directamente","Espero que lo intuya"]},
            {"id":9,"type":"choice","text":"¿Tu pareja nota cuando necesitas apoyo — sin que tengas que decirlo?","options":["Sí, casi siempre","A veces","Rara vez"]},
            {"id":10,"type":"text","text":"Si pudieras cambiar un hábito de comunicación entre ustedes — ¿cuál sería?"},
        ],
    },

    # ── ЧЕК-АП 2: «Кто тянет больше по дому» ────────────────────────────────
    "q2": {
        "ru": [
            {"id":1,"type":"choice","text":"Как вы сами оцениваете свой вклад в домашние дела?","options":["Я делаю больше 60%","Примерно 50%","Меньше 40%"]},
            {"id":2,"type":"choice","text":"Кто в вашей паре чаще первым замечает, что что-то нужно сделать — до того как стало срочно?","options":["Я","Партнёр","Примерно поровну"]},
            {"id":3,"type":"choice","text":"Когда дома заканчиваются нужные вещи — кто первым это замечает?","options":["Обычно я","Обычно партнёр","Замечаем одновременно"]},
            {"id":4,"type":"choice","text":"Кто чаще планирует и координирует совместные дела — поездки, встречи, праздники?","options":["Я","Партнёр","Примерно поровну"]},
            {"id":5,"type":"choice","text":"Когда партнёр берётся за домашнее дело — как это обычно происходит?","options":["Замечает сам и делает без слов","Делает, если я прошу","Делает, если я прошу и напоминаю"]},
            {"id":6,"type":"choice","text":"Кто из вас первым почувствует дискомфорт, если несколько дней не заниматься домом?","options":["Я","Партнёр","Примерно одновременно"]},
            {"id":7,"type":"text","text":"Назовите три дела, которые вы делаете регулярно и которые партнёр, скорее всего, просто не замечает."},
            {"id":8,"type":"text","text":"Какое домашнее дело выматывает вас морально — не физически, а потому что оно всегда на вас?"},
            {"id":9,"type":"text","text":"Одним предложением: было ли у вас ощущение, что вы «ведёте» дом в одиночку, даже когда партнёр рядом и физически помогает?"},
            {"id":10,"type":"text","text":"Назовите одно дело, которое делает партнёр тихо и регулярно — и за которое вы ни разу не сказали ему спасибо вслух."},
        ],
        "en": [
            {"id":1,"type":"choice","text":"How would you estimate your own contribution to household responsibilities?","options":["I do more than 60%","About 50%","Less than 40%"]},
            {"id":2,"type":"choice","text":"Who in your relationship usually notices first that something needs to be done — before it becomes urgent?","options":["Me","My partner","Roughly equal"]},
            {"id":3,"type":"choice","text":"When household supplies run out, who usually notices first?","options":["Usually me","Usually my partner","We notice at the same time"]},
            {"id":4,"type":"choice","text":"Who more often plans and coordinates shared things — trips, events, celebrations?","options":["Me","My partner","Roughly equal"]},
            {"id":5,"type":"choice","text":"When your partner takes on a household task, how does it usually happen?","options":["They notice and do it without being asked","They do it when I ask","They do it when I ask and remind them"]},
            {"id":6,"type":"choice","text":"Who would feel discomfort first if the house went untended for a few days?","options":["Me","My partner","About the same time"]},
            {"id":7,"type":"text","text":"Name three things you do regularly at home that your partner probably doesn't notice."},
            {"id":8,"type":"text","text":"What household responsibility drains you mentally — not physically, but because it's always on you?"},
            {"id":9,"type":"text","text":"In one sentence: have you ever felt like you were managing the home alone, even when your partner was around and physically helping?"},
            {"id":10,"type":"text","text":"Name one thing your partner does quietly and regularly — that you've never actually said thank you for out loud."},
        ],
        "es": [
            {"id":1,"type":"choice","text":"¿Cómo estimas tu propia contribución a las tareas del hogar?","options":["Hago más del 60%","Aproximadamente el 50%","Menos del 40%"]},
            {"id":2,"type":"choice","text":"¿Quién en vuestra relación suele notar primero que algo hay que hacer — antes de que se vuelva urgente?","options":["Yo","Mi pareja","Más o menos igual"]},
            {"id":3,"type":"choice","text":"Cuando se acaban cosas en casa, ¿quién lo nota primero?","options":["Generalmente yo","Generalmente mi pareja","Lo notamos al mismo tiempo"]},
            {"id":4,"type":"choice","text":"¿Quién planifica y coordina más las cosas compartidas — viajes, eventos, celebraciones?","options":["Yo","Mi pareja","Más o menos igual"]},
            {"id":5,"type":"choice","text":"Cuando tu pareja hace una tarea del hogar, ¿cómo suele ocurrir?","options":["Lo nota y lo hace sin que se lo pidan","Lo hace cuando se lo pido","Lo hace cuando se lo pido y se lo recuerdo"]},
            {"id":6,"type":"choice","text":"¿Quién sentiría antes el malestar si la casa estuviera descuidada varios días?","options":["Yo","Mi pareja","Aproximadamente al mismo tiempo"]},
            {"id":7,"type":"text","text":"Nombra tres cosas que haces regularmente en casa y que tu pareja probablemente no nota."},
            {"id":8,"type":"text","text":"¿Qué responsabilidad del hogar te agota mentalmente — no físicamente, sino porque siempre recae en ti?"},
            {"id":9,"type":"text","text":"En una frase: ¿has sentido alguna vez que gestionas el hogar en solitario, aunque tu pareja esté presente y ayude físicamente?"},
            {"id":10,"type":"text","text":"Nombra una cosa que tu pareja hace de forma silenciosa y regular — y por la que nunca le has dado las gracias en voz alta."},
        ],
    },

    # ── ЧЕК-АП 4 (видео 7): «Молчание после ссоры» ──────────────────────────
    "q4": {
        "ru": [
            {"id":1,"type":"choice","text":"Когда ты молчишь после конфликта — тебе физически труднее говорить, или ты осознанно выбираешь не разговаривать?","options":["Физически тяжело говорить","Осознанно выбираю молчать","По-разному, зависит от ситуации"]},
            {"id":2,"type":"choice","text":"Через сколько времени после ссоры ты обычно готов(а) вернуться к разговору?","options":["До 10 минут","10–30 минут","Больше часа","До следующего дня"]},
            {"id":3,"type":"choice","text":"Что тебе больше всего нужно от партнёра, пока ты молчишь?","options":["Пространство и тишина в ответ","Короткое «я рядом», без вопросов","Чтобы спросили прямо, нужно ли время"]},
            {"id":4,"type":"choice","text":"Что тяжелее всего терпеть, когда молчит партнёр?","options":["Неизвестно, сколько это продлится","Ощущение, что я в чём-то виноват(а)","Само по себе ничего, если знаю причину"]},
            {"id":5,"type":"choice","text":"Какая фраза от партнёра в момент твоего молчания реально помогла бы?","options":["«Я рядом, не тороплю»","«Скажи, когда сможешь говорить»","Лучше вообще ничего не говорить"]},
        ],
        "en": [
            {"id":1,"type":"choice","text":"When you go quiet after a conflict — is it physically harder to speak, or a conscious choice not to talk?","options":["Physically hard to speak","A conscious choice to stay quiet","Depends on the situation"]},
            {"id":2,"type":"choice","text":"How long after an argument are you usually ready to talk again?","options":["Under 10 minutes","10–30 minutes","More than an hour","Not until the next day"]},
            {"id":3,"type":"choice","text":"What do you need most from your partner while you're silent?","options":["Space and silence in return","A short 'I'm here', no questions","A direct ask whether I need time"]},
            {"id":4,"type":"choice","text":"What's hardest to sit with when your partner goes silent?","options":["Not knowing how long it will last","Feeling like I did something wrong","Nothing, as long as I understand why"]},
            {"id":5,"type":"choice","text":"What would your partner saying actually help while you're silent?","options":["'I'm here, no rush'","'Tell me when you're ready to talk'","Better to say nothing at all"]},
        ],
        "es": [
            {"id":1,"type":"choice","text":"Cuando te quedas en silencio tras un conflicto — ¿te resulta físicamente difícil hablar, o eliges conscientemente no hacerlo?","options":["Físicamente difícil hablar","Elijo conscientemente callar","Depende de la situación"]},
            {"id":2,"type":"choice","text":"¿Cuánto tiempo después de una discusión sueles estar listo/a para retomar la conversación?","options":["Menos de 10 minutos","10–30 minutos","Más de una hora","Hasta el día siguiente"]},
            {"id":3,"type":"choice","text":"¿Qué necesitas más de tu pareja mientras guardas silencio?","options":["Espacio y silencio de vuelta","Un breve 'estoy aquí', sin preguntas","Que pregunten directamente si necesito tiempo"]},
            {"id":4,"type":"choice","text":"¿Qué es lo más difícil de soportar cuando tu pareja guarda silencio?","options":["No saber cuánto va a durar","Sentir que hice algo mal","Nada, si entiendo la razón"]},
            {"id":5,"type":"choice","text":"¿Qué frase de tu pareja realmente ayudaría mientras estás en silencio?","options":["«Estoy aquí, no hay prisa»","«Dime cuándo puedas hablar»","Mejor no decir nada"]},
        ],
    },

    # ── ЧЕК-АП 5 (видео 8): «Разная скорость примирения» ─────────────────────
    "q5": {
        "ru": [
            {"id":1,"type":"choice","text":"Через сколько времени после серьёзной ссоры ты обычно готов(а) вести спокойный разговор?","options":["До 10 минут","10–30 минут","Больше часа","До следующего дня"]},
            {"id":2,"type":"choice","text":"Что ты делаешь, пока ждёшь, когда партнёр будет готов?","options":["Тревожусь и додумываю","Спокойно занимаюсь своими делами","По-разному, зависит от дня"]},
            {"id":3,"type":"choice","text":"Когда ты идёшь мириться первым(ой), а партнёр ещё не готов — что ты обычно делаешь?","options":["Обижаюсь и отступаю","Спокойно жду рядом","Пытаюсь снова через пару минут"]},
            {"id":4,"type":"choice","text":"Что помогло бы тебе больше всего, пока ты ждёшь партнёра?","options":["Конкретный ориентир по времени","Просто знать, что меня не игнорируют","Чтобы меня не торопили с ответом"]},
            {"id":5,"type":"choice","text":"Если партнёр подходит мириться раньше, чем ты готов(а) — что ты чувствуешь?","options":["Мягко прошу ещё немного времени","Чувствую вину и заставляю себя ответить","Раздражаюсь, что меня торопят"]},
        ],
        "en": [
            {"id":1,"type":"choice","text":"How long after a serious argument are you usually ready for a calm conversation?","options":["Under 10 minutes","10–30 minutes","More than an hour","Not until the next day"]},
            {"id":2,"type":"choice","text":"What do you do while waiting for your partner to be ready?","options":["I worry and overthink","I calmly go about my own things","Depends on the day"]},
            {"id":3,"type":"choice","text":"When you go to make up first and your partner isn't ready yet, what do you usually do?","options":["I get hurt and back off","I wait calmly nearby","I try again a few minutes later"]},
            {"id":4,"type":"choice","text":"What would help you most while waiting for your partner?","options":["A concrete time estimate","Just knowing I'm not being ignored","Not being rushed for a response"]},
            {"id":5,"type":"choice","text":"If your partner comes to make up before you're ready, what do you feel?","options":["I gently ask for a bit more time","I feel guilty and force myself to respond","I get irritated at being rushed"]},
        ],
        "es": [
            {"id":1,"type":"choice","text":"¿Cuánto tiempo después de una discusión seria sueles estar listo/a para una conversación tranquila?","options":["Menos de 10 minutos","10–30 minutos","Más de una hora","Hasta el día siguiente"]},
            {"id":2,"type":"choice","text":"¿Qué haces mientras esperas a que tu pareja esté lista?","options":["Me preocupo y le doy vueltas","Me ocupo tranquilamente de mis cosas","Depende del día"]},
            {"id":3,"type":"choice","text":"Cuando vas a reconciliarte primero y tu pareja aún no está lista, ¿qué sueles hacer?","options":["Me duele y me retiro","Espero tranquilo/a cerca","Lo intento de nuevo a los pocos minutos"]},
            {"id":4,"type":"choice","text":"¿Qué te ayudaría más mientras esperas a tu pareja?","options":["Una referencia concreta de tiempo","Simplemente saber que no me ignoran","Que no me apuren para responder"]},
            {"id":5,"type":"choice","text":"Si tu pareja viene a reconciliarse antes de que estés listo/a, ¿qué sientes?","options":["Pido con calma un poco más de tiempo","Me siento culpable y me obligo a responder","Me irrito porque me apuran"]},
        ],
    },

    # ── ЧЕК-АП 6 (видео 9): «Деньги — язык безопасности или свободы» ────────
    "q6": {
        "ru": [
            {"id":1,"type":"choice","text":"Когда я думаю о деньгах, я в первую очередь думаю о защите от рисков, или о возможностях, которые они открывают?","options":["Защита от рисков","Возможности и свобода","По-разному, зависит от ситуации"]},
            {"id":2,"type":"choice","text":"Что для меня важнее в трате партнёра — сама сумма, или то, обсудили ли её со мной заранее?","options":["Сама сумма","То, что не обсудили заранее","И то и другое одинаково важно"]},
            {"id":3,"type":"choice","text":"Как в моей семье в детстве в целом относились к деньгам?","options":["Тревожно, с разговорами о нехватке","Спокойно, как к обычному ресурсу","По-разному в разные периоды"]},
            {"id":4,"type":"choice","text":"Какая сумма для меня комфортна для траты партнёром без предварительного обсуждения?","options":["До 2000 рублей","До 5000–10000 рублей","Любая, если это разумно и по плану"]},
            {"id":5,"type":"choice","text":"Что я чувствую, когда партнёр критикует мою трату?","options":["Обвинение, хочется защищаться","Тревогу партнёра за общий бюджет, хочу объяснить","По-разному, зависит от тона"]},
        ],
        "en": [
            {"id":1,"type":"choice","text":"When I think about money, do I first think about protection from risk, or about the possibilities it opens up?","options":["Protection from risk","Possibilities and freedom","Depends on the situation"]},
            {"id":2,"type":"choice","text":"What matters more to me about a partner's purchase — the amount itself, or whether it was discussed with me beforehand?","options":["The amount itself","That it wasn't discussed beforehand","Both matter equally"]},
            {"id":3,"type":"choice","text":"How did my family generally treat money when I was growing up?","options":["Anxiously, with talk about not having enough","Calmly, as an ordinary resource","Differently at different times"]},
            {"id":4,"type":"choice","text":"What amount am I comfortable with my partner spending without discussing it with me first?","options":["Up to roughly $20","Up to roughly $100","Any amount, if it's reasonable and planned"]},
            {"id":5,"type":"choice","text":"What do I feel when my partner criticizes my spending?","options":["Accusation, I want to defend myself","Their anxiety about the shared budget, I want to explain","Depends on the tone"]},
        ],
        "es": [
            {"id":1,"type":"choice","text":"Cuando pienso en el dinero, ¿pienso primero en la protección frente a riesgos, o en las posibilidades que abre?","options":["Protección frente a riesgos","Posibilidades y libertad","Depende de la situación"]},
            {"id":2,"type":"choice","text":"¿Qué me importa más de un gasto de mi pareja — la cantidad en sí, o que no lo haya hablado conmigo antes?","options":["La cantidad en sí","Que no lo habló antes","Ambas cosas por igual"]},
            {"id":3,"type":"choice","text":"¿Cómo se trataba el dinero en mi familia cuando era niño/a?","options":["Con ansiedad, hablando de que faltaba","Con calma, como un recurso normal","De forma distinta en distintas épocas"]},
            {"id":4,"type":"choice","text":"¿Qué cantidad me resulta cómoda que mi pareja gaste sin hablarlo antes conmigo?","options":["Hasta unos 20 dólares","Hasta unos 100 dólares","Cualquier cantidad, si es razonable y planificada"]},
            {"id":5,"type":"choice","text":"¿Qué siento cuando mi pareja critica mi gasto?","options":["Acusación, quiero defenderme","Su ansiedad por el presupuesto común, quiero explicar","Depende del tono"]},
        ],
    },

    # ── ЧЕК-АП 7 (видео 10): «Близость — разный ритм желания» ───────────────
    "q7": {
        "ru": [
            {"id":1,"type":"choice","text":"Что обычно помогает мне почувствовать настрой на близость?","options":["Сначала контакт — разговор, прикосновение","Желание приходит само по себе","По-разному, зависит от периода"]},
            {"id":2,"type":"choice","text":"Когда партнёр проявляет инициативу, что я чувствую в первую очередь?","options":["Приглашение, без давления","Ожидание, которое нужно оправдать","Зависит от настроения и дня"]},
            {"id":3,"type":"choice","text":"Как часто мы говорим об этой теме вслух, в спокойном состоянии, а не в момент напряжения?","options":["Часто и спокойно","Редко, только когда уже накопилось","Почти никогда"]},
            {"id":4,"type":"choice","text":"Что я чувствую, когда партнёр говорит «не сегодня»?","options":["Спокойно принимаю, знаю, что это не про меня","Тревогу и сомнение в себе","Раздражение или обиду"]},
            {"id":5,"type":"choice","text":"Что помогло бы мне больше всего в этой теме?","options":["Больше тёплого контакта без ожиданий","Чтобы меня не торопили и не давили","Просто говорить об этом спокойно вслух"]},
        ],
        "en": [
            {"id":1,"type":"choice","text":"What usually helps me feel in the mood for intimacy?","options":["Connection first — talking, touch","Desire just shows up on its own","Depends on the period"]},
            {"id":2,"type":"choice","text":"When my partner takes the initiative, what do I feel first?","options":["An invitation, no pressure","An expectation I need to live up to","Depends on my mood that day"]},
            {"id":3,"type":"choice","text":"How often do we talk about this out loud, calmly, not in a moment of tension?","options":["Often, calmly","Rarely, only once it's built up","Almost never"]},
            {"id":4,"type":"choice","text":"What do I feel when my partner says 'not tonight'?","options":["Calm, I know it's not about me","Anxiety and self-doubt","Irritation or hurt"]},
            {"id":5,"type":"choice","text":"What would help me most with this topic?","options":["More warm contact without expectations","Not being rushed or pressured","Just being able to talk about it calmly"]},
        ],
        "es": [
            {"id":1,"type":"choice","text":"¿Qué me ayuda normalmente a sentirme con ganas de intimidad?","options":["Primero el contacto — hablar, tocarnos","El deseo aparece por sí solo","Depende de la etapa"]},
            {"id":2,"type":"choice","text":"Cuando mi pareja toma la iniciativa, ¿qué siento primero?","options":["Una invitación, sin presión","Una expectativa que debo cumplir","Depende de mi ánimo ese día"]},
            {"id":3,"type":"choice","text":"¿Con qué frecuencia hablamos de esto en voz alta, con calma, y no en un momento de tensión?","options":["A menudo, con calma","Rara vez, solo cuando ya se acumuló","Casi nunca"]},
            {"id":4,"type":"choice","text":"¿Qué siento cuando mi pareja dice «hoy no»?","options":["Calma, sé que no es por mí","Ansiedad y dudas sobre mí mismo/a","Irritación o dolor"]},
            {"id":5,"type":"choice","text":"¿Qué me ayudaría más con este tema?","options":["Más contacto cálido sin expectativas","Que no me apuren ni me presionen","Poder hablarlo con calma en voz alta"]},
        ],
    },

    # ── ЧЕК-АП 8: «Языки любви — что вы отдаёте и что реально считывает партнёр» ──
    "q8": {
        "ru": [
            {"id":1,"type":"choice","text":"Что из этого списка выбило бы вас сильнее всего, если бы партнёр перестал это делать?","options":["Слова — услышать вслух, что ценят","Время — полное внимание без телефона","Помощь — партнёр берёт на себя то, что тяжело","Прикосновение — объятие без повода","Знаки внимания — небольшой жест, что о вас думали"]},
            {"id":2,"type":"choice","text":"Что вы сами делали для партнёра чаще всего за последнюю неделю?","options":["Говорил(а) слова поддержки и признательности","Уделял(а) полное внимание, без телефона","Брал(а) на себя дела и заботы партнёра","Обнимал(а), прикасался(лась) просто так","Делал(а) небольшие знаки внимания"]},
            {"id":3,"type":"choice","text":"Изменился ли ваш приоритет за последние пару лет — ребёнок, переезд, новая работа, усталость?","options":["Да, заметно изменился","Немного сдвинулся","Нет, всё так же, как раньше"]},
            {"id":4,"type":"choice","text":"Как вы обычно выражаете любовь партнёру, даже не задумываясь, естественно?","options":["Словами и комплиментами","Временем и вниманием","Практической помощью и делами","Прикосновениями и объятиями","Подарками и небольшими знаками внимания"]},
            {"id":5,"type":"choice","text":"Если бы партнёр сегодня сделал ровно то, что в вашем первом пункте — вы бы заметили сразу?","options":["Да, сразу и очень заметно","Через какое-то время","Не уверен(а), сложно сказать"]},
        ],
        "en": [
            {"id":1,"type":"choice","text":"Which of these would hit you hardest if your partner stopped doing it?","options":["Words — hearing out loud that you're valued","Time — full attention, no phone","Help — partner taking on what's hard for you","Touch — a hug for no reason","Small gestures — something that shows they were thinking of you"]},
            {"id":2,"type":"choice","text":"What did you do for your partner most often over the last week?","options":["Said supportive, appreciative words","Gave full attention, no phone","Took on chores or tasks for them","Hugged or touched them just because","Did small thoughtful gestures"]},
            {"id":3,"type":"choice","text":"Has your priority shifted over the past couple of years — a child, a move, a new job, fatigue?","options":["Yes, noticeably","A bit","No, still the same"]},
            {"id":4,"type":"choice","text":"How do you naturally express love to your partner, without even thinking about it?","options":["Words and compliments","Time and attention","Practical help and chores","Touch and hugs","Gifts and small gestures"]},
            {"id":5,"type":"choice","text":"If your partner did exactly what's in your first answer today, would you notice right away?","options":["Yes, immediately and clearly","After a while","Not sure, hard to say"]},
        ],
        "es": [
            {"id":1,"type":"choice","text":"¿Qué de esta lista te afectaría más si tu pareja dejara de hacerlo?","options":["Palabras — escuchar en voz alta que te valoran","Tiempo — atención plena, sin teléfono","Ayuda — que tu pareja se encargue de lo que te pesa","Contacto físico — un abrazo sin motivo","Detalles — un pequeño gesto que muestre que pensaron en ti"]},
            {"id":2,"type":"choice","text":"¿Qué hiciste tú más a menudo por tu pareja la última semana?","options":["Dije palabras de apoyo y reconocimiento","Di atención plena, sin teléfono","Me encargué de tareas o cosas suyas","Abracé o toqué sin motivo especial","Hice pequeños gestos de detalle"]},
            {"id":3,"type":"choice","text":"¿Ha cambiado tu prioridad en los últimos años — un hijo, una mudanza, un nuevo trabajo, cansancio?","options":["Sí, notablemente","Un poco","No, sigue igual"]},
            {"id":4,"type":"choice","text":"¿Cómo expresas el amor a tu pareja de forma natural, sin pensarlo?","options":["Con palabras y cumplidos","Con tiempo y atención","Con ayuda práctica y tareas","Con contacto físico y abrazos","Con regalos y pequeños detalles"]},
            {"id":5,"type":"choice","text":"Si hoy tu pareja hiciera exactamente lo que pusiste en tu primera respuesta, ¿lo notarías de inmediato?","options":["Sí, de inmediato y claramente","Después de un tiempo","No estoy seguro/a"]},
        ],
    },

    # ── ЧЕК-АП 9: «Тревожный / избегающий тип привязанности» ─────────────────
    "q9": {
        "ru": [
            {"id":1,"type":"choice","text":"Когда партнёр дольше обычного не отвечает, я начинаю прокручивать в голове, что могло пойти не так.","options":["Да","Нет","Скорее да"]},
            {"id":2,"type":"choice","text":"Мне нужно довольно много подтверждений, что меня любят — одного «конечно люблю» надолго не хватает.","options":["Да","Нет","Скорее да"]},
            {"id":3,"type":"choice","text":"Мне комфортнее решать сложные вещи в одиночку, даже если партнёр честно предлагает помощь.","options":["Да","Нет","Скорее да"]},
            {"id":4,"type":"choice","text":"Когда партнёр расстроен и хочет поговорить, моя первая реакция — на секунду отойти, а не остаться полностью рядом.","options":["Да","Нет","Скорее да"]},
            {"id":5,"type":"choice","text":"Когда отношения становятся слишком близкими слишком быстро, внутри срабатывает что-то вроде тормоза.","options":["Да","Нет","Скорее да"]},
        ],
        "en": [
            {"id":1,"type":"choice","text":"When my partner takes longer than usual to respond, I start running through everything that could have gone wrong.","options":["Yes","No","Somewhat yes"]},
            {"id":2,"type":"choice","text":"I need quite a lot of reassurance that I'm loved — one \"of course I love you\" doesn't hold me for very long.","options":["Yes","No","Somewhat yes"]},
            {"id":3,"type":"choice","text":"I'm more comfortable working through hard things on my own, even when my partner sincerely offers to help.","options":["Yes","No","Somewhat yes"]},
            {"id":4,"type":"choice","text":"When my partner is upset and wants to talk, my very first instinct is to step back for a second, rather than stay fully present.","options":["Yes","No","Somewhat yes"]},
            {"id":5,"type":"choice","text":"When a relationship gets close too fast, something like a brake kicks in inside me.","options":["Yes","No","Somewhat yes"]},
        ],
        "es": [
            {"id":1,"type":"choice","text":"Cuando mi pareja tarda más de lo normal en responder, empiezo a repasar mentalmente qué pudo haber salido mal.","options":["Sí","No","Más bien sí"]},
            {"id":2,"type":"choice","text":"Necesito bastantes confirmaciones de que me quieren — un solo «claro que te quiero» no me alcanza por mucho tiempo.","options":["Sí","No","Más bien sí"]},
            {"id":3,"type":"choice","text":"Me resulta más cómodo resolver cosas difíciles yo solo, incluso cuando mi pareja se ofrece a ayudar con sinceridad.","options":["Sí","No","Más bien sí"]},
            {"id":4,"type":"choice","text":"Cuando mi pareja está molesta y quiere hablar, mi primer instinto es alejarme un segundo, en vez de quedarme completamente presente.","options":["Sí","No","Más bien sí"]},
            {"id":5,"type":"choice","text":"Cuando una relación se pone demasiado cercana demasiado rápido, algo así como un freno se activa dentro de mí.","options":["Sí","No","Más bien sí"]},
        ],
    },

    # ── ЧЕК-АП 10: «Презрение — четвёртый всадник» ───────────────────────────
    "q10": {
        "ru": [
            {"id":1,"type":"choice","text":"Закатывали ли вы глаза или тяжело вздыхали, когда партнёр говорил о чём-то, что вам казалось неважным?","options":["Да","Нет","Скорее да"]},
            {"id":2,"type":"choice","text":"Ловили ли вы себя на мысли «я бы никогда не сделал такую глупость», глядя на действия партнёра?","options":["Да","Нет","Скорее да"]},
            {"id":3,"type":"choice","text":"После некоторых разговоров с партнёром у меня остаётся ощущение, что надо мной посмеялись, а не что меня выслушали.","options":["Да","Нет","Скорее да"]},
            {"id":4,"type":"choice","text":"Партнёр иногда реагирует на мои слова закатыванием глаз или тяжёлым вздохом раньше, чем успевает ответить по существу.","options":["Да","Нет","Скорее да"]},
            {"id":5,"type":"choice","text":"После некоторых разговоров мне физически хочется извиниться за то, что я вообще это поднял(а), хотя объективно я не сделал(а) ничего плохого.","options":["Да","Нет","Скорее да"]},
        ],
        "en": [
            {"id":1,"type":"choice","text":"Have you rolled your eyes or sighed heavily while your partner talked about something that felt unimportant to you?","options":["Yes","No","Somewhat yes"]},
            {"id":2,"type":"choice","text":"Have you caught yourself thinking 'I would never do something that dumb,' watching your partner's actions?","options":["Yes","No","Somewhat yes"]},
            {"id":3,"type":"choice","text":"After some conversations with my partner, I'm left with the feeling that I was laughed at rather than listened to.","options":["Yes","No","Somewhat yes"]},
            {"id":4,"type":"choice","text":"My partner sometimes reacts to what I'm saying with an eye-roll or a heavy sigh before responding to the actual point.","options":["Yes","No","Somewhat yes"]},
            {"id":5,"type":"choice","text":"After some conversations, I physically want to apologize for bringing it up at all, even though I didn't do anything wrong.","options":["Yes","No","Somewhat yes"]},
        ],
        "es": [
            {"id":1,"type":"choice","text":"¿Has puesto los ojos en blanco o suspirado pesadamente mientras tu pareja hablaba de algo que te parecía poco importante?","options":["Sí","No","Más bien sí"]},
            {"id":2,"type":"choice","text":"¿Te has sorprendido pensando 'yo nunca haría algo tan tonto', al ver las acciones de tu pareja?","options":["Sí","No","Más bien sí"]},
            {"id":3,"type":"choice","text":"Después de algunas conversaciones con mi pareja, me queda la sensación de que se rieron de mí en vez de escucharme.","options":["Sí","No","Más bien sí"]},
            {"id":4,"type":"choice","text":"Mi pareja a veces reacciona a lo que digo con los ojos en blanco o un suspiro pesado antes de responder al punto en sí.","options":["Sí","No","Más bien sí"]},
            {"id":5,"type":"choice","text":"Después de algunas conversaciones, físicamente quiero disculparme por haberlo mencionado, aunque objetivamente no hice nada malo.","options":["Sí","No","Más bien sí"]},
        ],
    },
}

# ---------------------------------------------------------------------------
# БАЗА ДАННЫХ
# ---------------------------------------------------------------------------
def db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""CREATE TABLE IF NOT EXISTS pairs (
        code TEXT PRIMARY KEY,
        user1_id INTEGER,
        user2_id INTEGER,
        lang TEXT DEFAULT 'ru',
        checkup_id TEXT DEFAULT 'q1',
        created_at TEXT)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS answers (
        code TEXT, user_id INTEGER, question_id INTEGER, answer TEXT,
        PRIMARY KEY (code, user_id, question_id))""")
    conn.execute("""CREATE TABLE IF NOT EXISTS consent (
        user_id INTEGER PRIMARY KEY, lang TEXT, agreed_at TEXT)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS user_lang (
        user_id INTEGER PRIMARY KEY, lang TEXT)""")
    return conn

def gen_code():
    abc = string.ascii_uppercase.replace("O","").replace("I","") + "23456789"
    return "".join(random.choice(abc) for _ in range(6))

def get_user_lang(uid):
    conn=db(); r=conn.execute("SELECT lang FROM user_lang WHERE user_id=?",(uid,)).fetchone(); conn.close()
    return r[0] if r else None

def set_user_lang(uid,lang):
    conn=db(); conn.execute("INSERT OR REPLACE INTO user_lang(user_id,lang) VALUES(?,?)",(uid,lang)); conn.commit(); conn.close()

def create_pair(code, uid, lang, checkup_id):
    conn=db()
    conn.execute("INSERT INTO pairs(code,user1_id,user2_id,lang,checkup_id,created_at) VALUES(?,?,NULL,?,?,?)",
                 (code,uid,lang,checkup_id,datetime.utcnow().isoformat()))
    conn.commit(); conn.close()

def join_pair(code, uid):
    conn=db()
    r=conn.execute("SELECT user1_id,user2_id,lang,checkup_id FROM pairs WHERE code=?",(code,)).fetchone()
    if not r: conn.close(); return None
    u1,u2,lang,cid=r
    if u2 is None and u1!=uid:
        conn.execute("UPDATE pairs SET user2_id=? WHERE code=?",(uid,code)); conn.commit()
    conn.close()
    return {"lang":lang,"checkup_id":cid}

def save_answer(code,uid,qid,answer):
    conn=db(); conn.execute("INSERT OR REPLACE INTO answers(code,user_id,question_id,answer) VALUES(?,?,?,?)",(code,uid,qid,answer)); conn.commit(); conn.close()

def user_finished(code,uid,lang,checkup_id):
    qs=ALL_QUESTIONS[checkup_id][lang]
    conn=db(); n=conn.execute("SELECT COUNT(*) FROM answers WHERE code=? AND user_id=?",(code,uid)).fetchone()[0]; conn.close()
    return n>=len(qs)

def pair_status(code):
    conn=db(); r=conn.execute("SELECT user1_id,user2_id,lang,checkup_id FROM pairs WHERE code=?",(code,)).fetchone(); conn.close()
    return {"user1_id":r[0],"user2_id":r[1],"lang":r[2],"checkup_id":r[3]} if r else None

def get_all_answers(code,uid):
    conn=db(); rows=conn.execute("SELECT question_id,answer FROM answers WHERE code=? AND user_id=? ORDER BY question_id",(code,uid)).fetchall(); conn.close()
    return {qid:ans for qid,ans in rows}

def set_consent(uid,lang):
    conn=db(); conn.execute("INSERT OR REPLACE INTO consent(user_id,lang,agreed_at) VALUES(?,?,?)",(uid,lang,datetime.utcnow().isoformat())); conn.commit(); conn.close()

def delete_user_data(uid):
    conn=db()
    for tbl in ["answers","consent","user_lang"]:
        conn.execute(f"DELETE FROM {tbl} WHERE user_id=?",(uid,))
    conn.execute("UPDATE pairs SET user1_id=NULL WHERE user1_id=?",(uid,))
    conn.execute("UPDATE pairs SET user2_id=NULL WHERE user2_id=?",(uid,))
    conn.commit(); conn.close()

def get_stats():
    conn=db()
    total=conn.execute("SELECT COUNT(*) FROM consent").fetchone()[0]
    full=conn.execute("SELECT COUNT(*) FROM pairs WHERE user2_id IS NOT NULL").fetchone()[0]
    waiting=conn.execute("SELECT COUNT(*) FROM pairs WHERE user2_id IS NULL AND user1_id IS NOT NULL").fetchone()[0]
    by_lang=conn.execute("SELECT lang,COUNT(*) FROM pairs GROUP BY lang").fetchall()
    by_checkup=conn.execute("SELECT checkup_id,COUNT(*) FROM pairs GROUP BY checkup_id").fetchall()
    conn.close()
    return total,full,waiting,by_lang,by_checkup

# ---------------------------------------------------------------------------
# FSM
# ---------------------------------------------------------------------------
class Checkup(StatesGroup):
    choosing_lang = State()
    waiting_consent = State()
    asking = State()

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

def lang_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🇷🇺 Русский",callback_data="lang:ru"),
        InlineKeyboardButton(text="🇬🇧 English",callback_data="lang:en"),
        InlineKeyboardButton(text="🇪🇸 Español",callback_data="lang:es"),
    ]])

def consent_kb(lang):
    t=UI[lang]
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t["consent_yes"],callback_data="consent_yes")],
        [InlineKeyboardButton(text=t["consent_no"],callback_data="consent_no")],
    ])

def choice_kb(options,qid):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=o,callback_data=f"ans:{qid}:{i}")]
        for i,o in enumerate(options)
    ])

async def ask_next(message,state):
    data=await state.get_data()
    idx=data.get("q_index",0)
    lang=data.get("lang","ru")
    cid=data.get("checkup_id","q1")
    qs=ALL_QUESTIONS[cid][lang]
    if idx>=len(qs):
        await finish(message,state); return
    q=qs[idx]
    t=UI[lang]
    prefix=f"{t['question_prefix']} {idx+1}/{len(qs)}\n\n{q['text']}"
    await state.set_state(Checkup.asking)
    if q["type"]=="choice":
        await message.answer(prefix,reply_markup=choice_kb(q["options"],q["id"]))
    else:
        await message.answer(f"{prefix}\n\n{t['text_hint']}")

@dp.message(CommandStart())
async def cmd_start(message:Message,state:FSMContext):
    await state.clear()
    args=message.text.split(maxsplit=1)
    payload=args[1].strip() if len(args)>1 else None
    lang=None; code=None; checkup_id="q1"

    if payload:
        # Форматы: q2_ru (партнёр 1) или q2_ru-КОД (партнёр 2)
        if "-" in payload:
            lpart,code=payload.rsplit("-",1)
            parts=lpart.split("_")
            checkup_id=parts[0] if len(parts)>=1 else "q1"
            lang=parts[1] if len(parts)>=2 else None
        elif "_" in payload:
            parts=payload.split("_")
            checkup_id=parts[0]
            lang=parts[1] if len(parts)>=2 else None

        if lang not in ("ru","en","es"):
            lang=get_user_lang(message.from_user.id) or "ru"
        if checkup_id not in ALL_QUESTIONS:
            checkup_id="q1"

        if code:
            info=join_pair(code,message.from_user.id)
            if not info:
                await message.answer(UI[lang]["not_found"]); return
            lang=info["lang"]; checkup_id=info["checkup_id"]
            await state.update_data(code=code,lang=lang,checkup_id=checkup_id)
            set_user_lang(message.from_user.id,lang)
            await message.answer(UI[lang]["consent"],reply_markup=consent_kb(lang))
            await state.set_state(Checkup.waiting_consent); return

        set_user_lang(message.from_user.id,lang)
        new_code=gen_code()
        create_pair(new_code,message.from_user.id,lang,checkup_id)
        await state.update_data(code=new_code,lang=lang,checkup_id=checkup_id)
        await message.answer(UI[lang]["consent"],reply_markup=consent_kb(lang))
        await state.set_state(Checkup.waiting_consent); return

    lang=get_user_lang(message.from_user.id)
    if lang:
        new_code=gen_code()
        create_pair(new_code,message.from_user.id,lang,checkup_id)
        await state.update_data(code=new_code,lang=lang,checkup_id=checkup_id)
        await message.answer(UI[lang]["consent"],reply_markup=consent_kb(lang))
        await state.set_state(Checkup.waiting_consent)
    else:
        await message.answer(UI["ru"]["choose_lang"],reply_markup=lang_keyboard())
        await state.set_state(Checkup.choosing_lang)

@dp.callback_query(F.data.startswith("lang:"))
async def choose_lang(callback:CallbackQuery,state:FSMContext):
    lang=callback.data.split(":")[1]
    set_user_lang(callback.from_user.id,lang)
    data=await state.get_data()
    cid=data.get("checkup_id","q1")
    new_code=gen_code()
    create_pair(new_code,callback.from_user.id,lang,cid)
    await state.update_data(code=new_code,lang=lang,checkup_id=cid)
    await callback.message.answer(UI[lang]["consent"],reply_markup=consent_kb(lang))
    await state.set_state(Checkup.waiting_consent)
    await callback.answer()

@dp.callback_query(F.data=="consent_no")
async def consent_no(callback:CallbackQuery,state:FSMContext):
    data=await state.get_data(); lang=data.get("lang","ru")
    await callback.message.answer(UI[lang]["consent_no_reply"])
    await state.clear(); await callback.answer()

@dp.callback_query(F.data=="consent_yes")
async def consent_yes(callback:CallbackQuery,state:FSMContext):
    data=await state.get_data(); lang=data.get("lang","ru")
    set_consent(callback.from_user.id,lang)
    await state.update_data(q_index=0)
    await callback.message.answer(UI[lang]["start_msg"])
    await ask_next(callback.message,state)
    await callback.answer()

@dp.callback_query(F.data.startswith("ans:"))
async def handle_choice(callback:CallbackQuery,state:FSMContext):
    _,qid,oi=callback.data.split(":"); qid,oi=int(qid),int(oi)
    data=await state.get_data(); lang=data.get("lang","ru"); cid=data.get("checkup_id","q1")
    qs=ALL_QUESTIONS[cid][lang]
    q=next(x for x in qs if x["id"]==qid)
    ans=q["options"][oi]
    save_answer(data["code"],callback.from_user.id,qid,ans)
    await callback.message.edit_text(f"{q['text']}\n\n{UI[lang]['your_answer']}: {ans} ✅")
    await state.update_data(q_index=data.get("q_index",0)+1)
    await ask_next(callback.message,state)
    await callback.answer()

@dp.message(Checkup.asking)
async def handle_text(message:Message,state:FSMContext):
    data=await state.get_data(); idx=data.get("q_index",0)
    lang=data.get("lang","ru"); cid=data.get("checkup_id","q1")
    qs=ALL_QUESTIONS[cid][lang]
    if idx>=len(qs): return
    q=qs[idx]
    if q["type"]!="text":
        await message.answer(UI[lang]["choose_option"]); return
    save_answer(data["code"],message.from_user.id,q["id"],message.text.strip())
    await state.update_data(q_index=idx+1)
    await ask_next(message,state)

async def finish(message,state):
    data=await state.get_data()
    code=data["code"]; lang=data.get("lang","ru"); cid=data.get("checkup_id","q1")
    uid=message.chat.id
    status=pair_status(code)
    other=None
    if status:
        if status["user1_id"]==message.from_user.id: other=status["user2_id"]
        elif status["user2_id"]==message.from_user.id: other=status["user1_id"]

    if other is None:
        username=(await bot.get_me()).username
        link=f"https://t.me/{username}?start={cid}_{lang}-{code}"
        await message.answer(UI[lang]["invite_msg"].format(code=code,link=link))
    else:
        if user_finished(code,other,lang,cid):
            await send_results(code)
        else:
            await message.answer(UI[lang]["finished_wait"])
    await state.clear()

async def send_results(code):
    st=pair_status(code)
    u1,u2,lang,cid=st["user1_id"],st["user2_id"],st["lang"],st["checkup_id"]
    t=UI[lang]; qs=ALL_QUESTIONS[cid][lang]
    choice_qs=[q for q in qs if q["type"]=="choice"]
    text_qs=[q for q in qs if q["type"]=="text"]
    ans1=get_all_answers(code,u1); ans2=get_all_answers(code,u2)
    matches=0; diff=[]
    for q in choice_qs:
        a1,a2=ans1.get(q["id"],"—"),ans2.get(q["id"],"—")
        if a1==a2: matches+=1
        else: diff.append(f"• {q['text']}\n   {t['partner1']}: {a1}\n   {t['partner2']}: {a2}")
    result=t["result_header"].format(code=code)
    result+=t["matched"].format(n=matches,total=len(choice_qs))
    if diff: result+=t["diff_header"]+"\n\n".join(diff)+"\n\n"
    else: result+=t["all_match"]
    opens=[f"• {q['text']}\n   {t['partner1']}: «{ans1.get(q['id'],'—')}»\n   {t['partner2']}: «{ans2.get(q['id'],'—')}»"
           for q in text_qs]
    if opens:
        result+=t["open_header"]+"\n\n".join(opens)
    result+=t["result_footer"]
    for uid in (u1,u2):
        try: await bot.send_message(uid,result)
        except Exception as e: log.warning(f"Не удалось отправить {uid}: {e}")

@dp.message(Command("stats"))
async def cmd_stats(message:Message):
    if message.from_user.id!=ADMIN_ID: return
    total,full,waiting,by_lang,by_checkup=get_stats()
    lang_lines="\n".join(f"  {l}: {n}" for l,n in by_lang)
    checkup_lines="\n".join(f"  {c}: {n} пар" for c,n in by_checkup)
    await message.answer(
        f"📊 Статистика\n\n"
        f"Всего пользователей: {total}\n"
        f"Пар завершили оба: {full}\n"
        f"Ждут партнёра: {waiting}\n\n"
        f"По языкам:\n{lang_lines}\n\n"
        f"По чек-апам:\n{checkup_lines}"
    )

@dp.message(Command("delete"))
async def cmd_delete(message:Message,state:FSMContext):
    lang=get_user_lang(message.from_user.id) or "ru"
    delete_user_data(message.from_user.id)
    await state.clear()
    await message.answer(UI[lang]["deleted"])

@dp.message(Command("stop"))
async def cmd_stop(message:Message,state:FSMContext):
    lang=get_user_lang(message.from_user.id) or "ru"
    await state.clear()
    await message.answer(UI[lang]["stopped"])

@dp.message(Command("help"))
async def cmd_help(message:Message):
    lang=get_user_lang(message.from_user.id) or "ru"
    await message.answer(UI[lang]["help"])

async def reminder_loop():
    while True:
        await asyncio.sleep(60*60*6)
        conn=db()
        week_ago=(datetime.utcnow()-timedelta(days=7)).isoformat()
        rows=conn.execute(
            "SELECT code,user1_id,user2_id,lang FROM pairs "
            "WHERE user1_id IS NOT NULL AND user2_id IS NOT NULL AND created_at<=?",
            (week_ago,)
        ).fetchall(); conn.close()
        for code,u1,u2,lang in rows:
            msg=UI.get(lang,UI["ru"])["reminder"]
            for uid in (u1,u2):
                try: await bot.send_message(uid,msg)
                except Exception as e: log.warning(f"Напоминание не доставлено {uid}: {e}")

async def main():
    asyncio.create_task(reminder_loop())
    await dp.start_polling(bot)

if __name__=="__main__":
    asyncio.run(main())
