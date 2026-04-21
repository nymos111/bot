import random

STAGES = ["start", "rapport", "flirt", "comfort", "meet"]

REACTIONS = ["Хаха", "Мм", "Слушай", "Интересно", "Ого"]
HOOKS = [
    "расскажи подробнее",
    "что ты обычно делаешь?",
    "это часто у тебя?",
    "как ты к этому пришла?"
]
SOFTENERS = ["", "честно", "кстати", "если честно"]

RARE_LINES = [
    "мне кажется ты специально так отвечаешь 😄",
    "ты всегда такая или это я везучий?"
]


def extract_signals(text: str):
    t = text.lower()
    return {
        "has_question": "?" in text,
        "long": len(text) > 25,
        "short": len(text) < 6,
        "emoji": any(e in text for e in ["😊","😉","😂","😍"]),
        "dry": any(w in t for w in ["понятно", "ясно", "ок"]),
        "initiative": "а ты" in t,
    }


def update_interest(current, signals):
    delta = 0

    if signals["has_question"]:
        delta += 8
    if signals["long"]:
        delta += 8
    if signals["emoji"]:
        delta += 6
    if signals["initiative"]:
        delta += 10

    if signals["short"]:
        delta -= 10
    if signals["dry"]:
        delta -= 8

    return max(0, min(100, current + delta)), delta


def update_stage(interest):
    if interest < 30:
        return "start"
    elif interest < 50:
        return "rapport"
    elif interest < 70:
        return "flirt"
    elif interest < 85:
        return "comfort"
    else:
        return "meet"


def analyze_context(messages):
    if len(messages) < 3:
        return {"momentum": "neutral"}

    avg = sum(len(m) for m in messages) / len(messages)

    if avg > 25:
        return {"momentum": "growing"}
    elif avg < 10:
        return {"momentum": "falling"}
    return {"momentum": "neutral"}


def detect_style(messages):
    if not messages:
        return "neutral"

    avg = sum(len(m) for m in messages) / len(messages)

    if avg < 15:
        return "short"
    elif avg > 40:
        return "long"
    return "neutral"


def humanize(text):
    parts = [
        random.choice(REACTIONS),
        text,
        random.choice(SOFTENERS),
        random.choice(HOOKS)
    ]
    return " ".join([p for p in parts if p])


def add_human_imperfection(text):
    if random.random() < 0.3:
        text = text.replace(",", "")
    if random.random() < 0.2:
        text += "..."
    return text


def adjust_for_momentum(text, context):
    if context["momentum"] == "falling":
        return text + " 😄"
    if context["momentum"] == "growing":
        return text.replace("?", "")
    return text


def generate_replies(stage, context, history):
    style = detect_style(history)

    if stage == "rapport":
        base = ["с тобой легко общаться", "ты интересный человек", "не скучно с тобой"]
    elif stage == "flirt":
        base = ["ты начинаешь цеплять", "с тобой можно залипнуть", "ты умеешь держать внимание"]
    elif stage == "comfort":
        base = ["с тобой спокойно", "приятно с тобой", "ты мне нравишься"]
    elif stage == "meet":
        base = ["давай увидимся", "надо встретиться", "переписка уже не тянет"]
    else:
        base = ["давай познакомимся", "расскажи о себе", "чем занимаешься"]

    replies = []

    for b in random.sample(base, 3):
        text = humanize(b)
        text = adjust_for_momentum(text, context)
        text = add_human_imperfection(text)
        replies.append(text)

    if random.random() < 0.1:
        replies[0] = random.choice(RARE_LINES)

    return {
        "light": replies[0],
        "confident": replies[1],
        "flirt": replies[2]
    }
