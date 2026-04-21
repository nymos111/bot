import aiohttp
import os

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

URL = "https://openrouter.ai/api/v1/chat/completions"

async def humanize_with_ai(text: str):
    prompt = f"Сделай это сообщение естественным для дейтинга:\n{text}"

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": "mistralai/mistral-7b-instruct",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 60
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(URL, json=payload, headers=headers) as resp:
                data = await resp.json()
                return data["choices"][0]["message"]["content"].strip()
    except:
        return text
