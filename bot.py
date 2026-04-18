await asyncio.sleep(15)

        session.votes = {}

        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=p.name, callback_data=f"vote_{p.id}")]
            for p in alive(session)
        ])

        for p in alive(session):
            try:
                await bot.send_message(p.id, "Голосуй:", reply_markup=kb)
            except:
                pass

        for _ in range(20):
            if len(session.votes) >= len(alive(session)):
                break
            await asyncio.sleep(1)

        vote_count = {}
        for v in session.votes.values():
            vote_count[v] = vote_count.get(v, 0) + 1

        text = "Голосование:\n"
        for pid, count in vote_count.items():
            text += session.players[pid].name + ": " + str(count) + "\n"

        if vote_count:
            killed = max(vote_count, key=vote_count.get)
            session.players[killed].dead = True
            text += "Казнён: " + session.players[killed].name

        await bot.send_message(session.chat_id, text)

        session.kill_target = None
        session.heal_target = None
        session.check_target = None

        for p in alive(session):
            if p.role == "Предатель":
                targets = [pl for pl in alive(session) if pl.id != p.id]
                kb = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text=t.name, callback_data=f"kill_{t.id}")]
                    for t in targets
                ])
                try:
                    await bot.send_message(p.id, "Кого убить:", reply_markup=kb)
                except:
                    pass

            if p.role == "Врач":
                kb = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text=t.name, callback_data=f"heal_{t.id}")]
                    for t in alive(session)
                ])
                try:
                    await bot.send_message(p.id, "Кого лечить:", reply_markup=kb)
                except:
                    pass

            if p.role == "Детектив":
                targets = [pl for pl in alive(session) if pl.id != p.id]
                kb = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text=t.name, callback_data=f"check_{t.id}")]
                    for t in targets
                ])
                try:
                    await bot.send_message(p.id, "Кого проверить:", reply_markup=kb)
                except:
                    pass

        await asyncio.sleep(20)

        if session.check_target:
            role = session.players[session.check_target].role
            detective = next((p for p in session.players.values() if p.role == "Детектив"), None)
            if detective:
                try:
                    await bot.send_message(detective.id, f"Роль: {role}")
                except:
                    pass

        if session.kill_target and session.kill_target != session.heal_target:
            session.players[session.kill_target].dead = True
            await bot.send_message(session.chat_id, f"Ночью убит {session.players[session.kill_target].name}")
        else:
            await bot.send_message(session.chat_id, "Ночью никто не умер")

        win = win_check(session)
        if win:
            await bot.send_message(session.chat_id, win)
            session.started = False
            break

@dp.message(Command("story"))
async def story(message: types.Message):
    sessions[message.chat.id] = Session(message.chat.id)
    await message.answer("Игра создана /join")

@dp.message(Command("join"))
async def join(message: types.Message):
    session = sessions.get(message.chat.id)
    if not session:
        return
    session.players[message.from_user.id] = Player(message.from_user)
    await message.answer(message.from_user.first_name + " в игре")

@dp.message(Command("go"))
async def go(message: types.Message):
    session = sessions.get(message.chat.id)
    if not session:
        return
    session.started = True
    assign_roles(session)

    for p in session.players.values():
        try:
            await bot.send_message(p.id, "Роль: " + p.role)
        except:
            pass

    asyncio.create_task(game_loop(session))

@dp.callback_query()
async def callbacks(callback: CallbackQuery):
    if not callback.from_user:
        return

    user_id = callback.from_user.id

    session = None
    for s in sessions.values():
        if user_id in s.players:
            session = s
            break

    if not session:
        return

    data = callback.data

    if data.startswith("choice_"):
        if user_id in session.choices:
            return await callback.answer("Уже выбрал")
        session.choices[user_id] = int(data.split("_")[1])
        await callback.answer("OK")

    elif data.startswith("vote_"):
        if user_id in session.votes:
            return await callback.answer("Уже голосовал")
        session.votes[user_id] = int(data.split("_")[1])
        await callback.answer("Голос принят")

    elif data.startswith("kill_"):
        if user_id != session.traitor_id:
            return
        session.kill_target = int(data.split("_")[1])
        await callback.answer("Цель выбрана")

    elif data.startswith("heal_"):
        player = session.players.get(user_id)
        if not player or player.role != "Врач":
            return
        session.heal_target = int(data.split("_")[1])
        await callback.answer("Лечение выбрано")

    elif data.startswith("check_"):
        player = session.players.get(user_id)
        if not player or player.role != "Детектив":
            return
        session.check_target = int(data.split("_")[1])
        await callback.answer("Проверка выбрана")

async def main():
    logging.basicConfig(level=logging.INFO)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
