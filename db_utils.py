import asyncio
import asyncpg

import json

from config import DB_NAME, DB_HOST, DB_USERNAME, DB_PASSWORD


class Database:
    def __init__(self, loop: asyncio.AbstractEventLoop):
        self.pool = loop.run_until_complete(
            asyncpg.create_pool(
                database=DB_NAME,
                user=DB_USERNAME,
                password=DB_PASSWORD,
                host=DB_HOST,
                port='5432'
            )
        )

    async def add_user(self, id: int):
        await self.pool.execute(
            'INSERT INTO users (telegram_id) VALUES ($1)',
            id
        )

    async def current_user(self, id: int):
        return await self.pool.fetchval(
            'SELECT * FROM users WHERE telegram_id = $1',
            id
        )

    async def select_all_users(self):
        return await self.pool.fetch("SELECT * FROM users")

    async def get_user_location(self, id: int):
        return await self.pool.fetchval(
            'SELECT location FROM users WHERE telegram_id = $1',
            id
        )

    async def set_user_location(self, id: int, location: dict):
        await self.pool.execute(
            'UPDATE users SET location = $1 WHERE telegram_id = $2',
            json.dumps(location),
            id
        )

    async def get_user_metric(self, id: int):
        return await self.pool.fetchval(
            'SELECT weather_metric FROM users WHERE telegram_id = $1',
            id
        )

    async def change_user_metric(self, id: int):
        current_metric = await self.pool.fetchval(
            'SELECT weather_metric FROM users WHERE telegram_id = $1',
            id
        )
        if current_metric == 'celsius':
            return await self.pool.execute(
                "UPDATE users SET weather_metric = 'fahrenheit' WHERE telegram_id = $1",
                id
            )
        elif current_metric == 'fahrenheit':
            return await self.pool.execute(
                "UPDATE users SET weather_metric = 'celsius' WHERE telegram_id = $1",
                id
            )
