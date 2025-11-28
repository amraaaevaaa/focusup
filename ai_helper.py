import os
import aiohttp
import json
import asyncio
import re
from config import OPENAI_API_KEY, OPENAI_MODEL

class AIAssistant:
    def __init__(self, api_key=None):
        self.openai_key = OPENAI_API_KEY
        self.model = OPENAI_MODEL
        self.provider = "openai" if self.openai_key else None
        self.is_available = bool(self.provider)
    
    async def generate_response(self, user_message, user_context=None):
        if not self.is_available:
            return "❌ OpenAI API key не настроен. Установите OPENAI_API_KEY в .env"

        return await self._openai_api_call(user_message, user_context)
    



    async def _openai_api_call(self, user_message, user_context):
        if not self.openai_key:
            return "❌ OpenAI ключ не настроен"

        try:
            system_prompt = self._build_system_prompt(user_context)
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ]

            url = "https://api.openai.com/v1/chat/completions"
            headers = {
                "Authorization": f"Bearer {self.openai_key}",
                "Content-Type": "application/json"
            }
            payload = {
                "model": self.model,
                "messages": messages,
                "max_completion_tokens": 1000
            }

            attempts = 2
            for attempt in range(1, attempts + 1):
                async with aiohttp.ClientSession() as session:
                    async with session.post(url, headers=headers, json=payload, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                        text = await resp.text()
                        if resp.status != 200:
                            if resp.status == 401:
                                return "❌ Неверный OpenAI API ключ. Проверьте OPENAI_API_KEY в .env"
                            elif resp.status == 403:
                                return "❌ Доступ запрещен. Проверьте права доступа к OpenAI API"
                            elif resp.status == 404:
                                return f"❌ Модель {self.model} не найдена. Возможно, у вас нет доступа к GPT-5"
                            elif resp.status == 429:
                                if attempt < attempts:
                                    await asyncio.sleep(1.0 * attempt)  
                                    continue
                                return "❌ Превышен лимит запросов OpenAI API. Попробуйте позже"
                            elif resp.status >= 500:
                                if attempt < attempts:
                                    await asyncio.sleep(0.5 * attempt)
                                    continue
                                return f"❌ Серверная ошибка OpenAI: {resp.status}"
                            else:
                                return f"❌ Ошибка OpenAI API: {resp.status} - {text}"
                        try:
                            result = json.loads(text)
                        except Exception:
                            if attempt < attempts:
                                await asyncio.sleep(0.5 * attempt)
                                continue
                            return "❌ Неверный ответ от OpenAI (не JSON)"

                        if 'choices' in result and isinstance(result['choices'], list) and result['choices']:
                            choice = result['choices'][0]

                            if 'message' in choice and isinstance(choice['message'], dict) and 'content' in choice['message']:
                                return choice['message']['content']

                            if 'text' in choice and isinstance(choice['text'], str):
                                return choice['text']

                        if 'output' in result and isinstance(result['output'], str):
                            return result['output']
                        if 'text' in result and isinstance(result['text'], str):
                            return result['text']

                        try:
                            with open('openai_raw_responses.log', 'a', encoding='utf-8') as f:
                                f.write(f"--- UNEXPECTED RESPONSE FORMAT ---\n")
                                f.write(f"Model: {self.model}\n")
                                f.write(f"Response: {text}\n\n")
                        except Exception:
                            pass
                        return "❌ Неожиданный формат ответа от OpenAI. Проверьте логи."

        except Exception as e:
            return f"⚠️ OpenAI временно недоступен: {str(e)}"
    
    def _build_system_prompt(self, user_context):
        
        base_prompt = """Ты - AI-ассистент для тайм-менеджмента FocusUp. Ты помогаешь пользователям с планированием, продуктивностью и организацией задач.

Контекст пользователя:
{context}

ВАЖНЫЕ ПРАВИЛА ОТВЕТОВ:
• Отвечай КРАТКО и СТРУКТУРИРОВАННО
• Максимум 3-5 основных пунктов
• Используй только эмодзи и простые списки
• НЕ используй markdown символы: #, *, **, __, ~, `, ```
• НЕ используй заголовки с # и жирный текст с *
• Используй только простой текст и эмодзи
• Избегай длинных абзацев
• Давай конкретные, применимые советы
• Ответ должен быть не длиннее 500-800 символов

Твоя роль:
1. Давать практические советы по тайм-менеджменту
2. Помогать планировать задачи и расставлять приоритеты
3. Предлагать методы продуктивности (Pomodoro, GTD, Eisenhower Matrix)
4. Анализировать рабочие привычки и давать рекомендации
5. Создавать КРАТКИЕ планы выполнения задач
6. Помогать бороться с прокрастинацией

Отвечай на русском языке. Будь конкретным и полезным.
"""
        context_text = user_context if user_context else "Пользователь только начал использовать бот"
        return base_prompt.format(context=context_text)
    
    def _get_fallback_response(self, user_message):
        fallback_responses = {
            "задач": "📋 Я могу помочь вам с задачами! Используйте кнопку '➕ Задача' чтобы создать новую задачу, или '📋 Мои задачи' чтобы посмотреть существующие.",
            "помидор": "🍅 Pomodoro таймер поможет сфокусироваться! 25 минут работы + 5 минут отдыха. Используйте кнопку '🍅 Pomodoro' чтобы начать.",
            "план": "🎯 Для планирования используйте календарь и задачи. AI-функции для продвинутого планирования скоро будут доступны!",
            "статистик": "📊 Статистика показывает ваш прогресс! Проверьте сколько задач выполнено и как распределяются по категориям.",
            "совет": "💡 Вот несколько советов по продуктивности:\n\n• Разбейте большие задачи на маленькие шаги\n• Используйте технику Pomodoro\n• Расставляйте приоритеты по матрице Эйзенхауэра\n• Планируйте следующий день вечером",
            "default": "🤖 AI-ассистент скоро будет доступен! А пока используйте основные функции бота:\n\n• 📝 Задачи - создание и управление задачами\n• 🍅 Pomodoro - техника концентрации\n• 📅 Календарь - планирование времени\n• 📊 Статистика - анализ продуктивности"
        }
        
        message_lower = user_message.lower()
        for key, response in fallback_responses.items():
            if key in message_lower and key != "default":
                return response
        
        return fallback_responses["default"]
    
    async def create_task_plan(self, goal, timeframe):
        prompt = f"""
Цель: {goal}
Временные рамки: {timeframe}

Создай КРАТКИЙ план из 5-7 основных шагов. Каждый шаг должен быть:
• Конкретным и выполнимым
• С указанием времени
• Без лишних деталей

НЕ используй markdown символы (#, *, **, __, ~)!
Используй только простой текст и эмодзи.

Формат ответа:
🎯 План достижения цели:

1. [Шаг 1] - [время]
2. [Шаг 2] - [время]
...

✅ Совет: [краткий практический совет]

Максимум 500-700 символов!
"""
        return await self.generate_response(prompt)
    
    async def analyze_productivity(self, tasks_data):
        prompt = f"""
Данные о задачах: {tasks_data}

Проанализируй КРАТКО и дай 3-4 практических совета:

НЕ используй markdown символы (#, *, **, __, ~)!
Используй только простой текст и эмодзи.

📊 Анализ продуктивности:

• [Главная проблема]
• [Что хорошо]
• [Совет 1]
• [Совет 2]
• [Совет 3]

Максимум 400-500 символов. Без длинных объяснений!
"""
        return await self.generate_response(prompt)
    
    async def generate_task_title(self, voice_text):
        prompt = f"""
Голосовой текст: "{voice_text}"

Создай КРАТКОЕ название задачи (максимум 25 символов).

ПРАВИЛА:
• Убери все временные указания (сегодня, завтра, в 15:00, вечера, утра и т.д.)
• Оставь только СУТЬ задачи
• Используй глаголы в инфинитиве или существительные
• НЕ используй markdown символы
• Максимум 2-3 слова

ПРИМЕРЫ:
"Завтра в 5 часов вечера уроки" → "Уроки"
"Сегодня встреча с другом в 21:00" → "Встреча с другом"
"Позвонить маме утром" → "Позвонить маме"
"Купить продукты в магазине" → "Купить продукты"

Верни ТОЛЬКО название задачи, без дополнительного текста!
"""
        try:
            result = await self.generate_response(prompt)
            title = result.strip().strip('"').strip("'")
            if len(title) > 30:
                title = title[:27] + "..."
            return title
        except Exception as e:
            return None

ai_assistant = AIAssistant()