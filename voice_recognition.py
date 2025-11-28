import aiohttp
import asyncio
import tempfile
import os
from config import OPENAI_API_KEY

class VoiceRecognizer:
    def __init__(self, api_key=None):
        self.api_key = api_key or OPENAI_API_KEY
        self.is_available = bool(self.api_key)
    
    async def recognize_voice(self, voice_file_data, file_format="ogg"):
        if not self.is_available:
            return "❌ Голосовое распознавание недоступно. Не настроен OpenAI API ключ."
        
        try:
            return await self.recognize_with_whisper_api(voice_file_data, file_format)
        except Exception as e:
            print(f"Ошибка распознавания голоса: {e}")
            return "❌ Ошибка при распознавании голоса. Попробуйте ещё раз."
    
    async def recognize_with_whisper_api(self, voice_file_data, file_format="ogg"):
        if not self.api_key:
            return "❌ OpenAI API ключ не настроен"
        
        with tempfile.NamedTemporaryFile(suffix=f".{file_format}", delete=False) as temp_file:
            temp_file.write(voice_file_data)
            temp_file_path = temp_file.name
        
        try:
            async with aiohttp.ClientSession() as session:
                data = aiohttp.FormData()
                data.add_field('file', 
                              open(temp_file_path, 'rb'), 
                              filename=f"audio.{file_format}",
                              content_type=f"audio/{file_format}")
                data.add_field('model', 'whisper-1')
                data.add_field('language', 'ru') 
                
                headers = {
                    'Authorization': f'Bearer {self.api_key}'
                }
                
                async with session.post(
                    'https://api.openai.com/v1/audio/transcriptions',
                    data=data,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    
                    if response.status != 200:
                        error_text = await response.text()
                        print(f"Ошибка Whisper API: {response.status} - {error_text}")
                        return f"❌ Ошибка распознавания: {response.status}"
                    
                    result = await response.json()
                    recognized_text = result.get('text', '').strip()
                    
                    if recognized_text:
                        return f"🎤 Распознанный текст:\n\n{recognized_text}"
                    else:
                        return "❌ Не удалось распознать речь. Попробуйте говорить чётче."
        
        except asyncio.TimeoutError:
            return "❌ Превышено время ожидания. Попробуйте ещё раз."
        except Exception as e:
            print(f"Ошибка Whisper API: {e}")
            return "❌ Ошибка при обращении к сервису распознавания."
        
        finally:
            try:
                os.unlink(temp_file_path)
            except Exception:
                pass

voice_recognizer = VoiceRecognizer()