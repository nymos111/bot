import random

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


def generate_replies(stage, context):
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

    return base
