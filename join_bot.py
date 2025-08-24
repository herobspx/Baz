    import asyncio
    import logging
    import os

    from aiogram import Bot, Dispatcher, executor, types
    from aiogram.client.default import DefaultBotProperties

    # Read token from environment variable
    JOIN_TOKEN = os.getenv("JOIN_TOKEN")

    if not JOIN_TOKEN:
        raise RuntimeError("Environment variable JOIN_TOKEN is missing!")

    # Configure logging
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger("join-bot")

    # Create bot with default parse_mode to avoid aiogram 3.x signature issues
    bot = Bot(token=JOIN_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
    dp = Dispatcher(bot)

    # --- Handlers ---

    @dp.message_handler(commands=["start", "help"])
    async def handle_start(message: types.Message):
        await message.answer("✅ البوت شغّال.
أرسل أي رسالة للتجربة أو اكتب /ping")

    @dp.message_handler(commands=["ping"])
    async def handle_ping(message: types.Message):
        await message.reply("pong 🟢")

    @dp.message_handler()
    async def echo(message: types.Message):
        # Simple echo for smoke test
        await message.answer(f"سمعتك: <b>{types.utils.markdown.quote_html(message.text)}</b>")

    # --- Keepalive (optional) ---
    async def keepalive():
        while True:
            # Just sleep; Render keeps the worker running while the process is alive
            await asyncio.sleep(60)

    if __name__ == "__main__":
        # Start polling
        loop = asyncio.get_event_loop()
        loop.create_task(keepalive())
        executor.start_polling(dp, skip_updates=True)
