from PIL import Image, ImageDraw, ImageFont
import os
import tempfile

class PomodoroGIFCreator:
    def __init__(self):
        self.width = 300
        self.height = 120
        self.duration = 100
        
    def create_timer_gif(self, total_seconds, session_type, output_path):
    
        frames = []
        
        colors = {
            'work': (220, 20, 60),
            'break': (65, 105, 225),
            'long_break': (34, 139, 34)
        }
        
        preview_seconds = min(30, total_seconds)
        
        for seconds_passed in range(0, preview_seconds + 1):
            seconds_left = preview_seconds - seconds_passed
            frame = self._create_frame(seconds_left, total_seconds, colors[session_type], session_type)
            frames.append(frame)
        
        if frames:
            frames[0].save(
                output_path,
                save_all=True,
                append_images=frames[1:],
                duration=self.duration,
                loop=0,
                optimize=True
            )
        
        return output_path
    
    def _create_frame(self, seconds_left, total_seconds, color, session_type):
    
        img = Image.new('RGB', (self.width, self.height), color=(30, 30, 30))
        draw = ImageDraw.Draw(img)
        
        font_large = None
        font_small = None
        
        font_paths = [
            "arial.ttf",
            "Arial.ttf",
            "/usr/share/fonts/truetype/freefont/FreeMono.ttf",
            "/System/Library/Fonts/Arial.ttf"
        ]
        
        for font_path in font_paths:
            try:
                if font_large is None:
                    font_large = ImageFont.truetype(font_path, 32)
                if font_small is None:
                    font_small = ImageFont.truetype(font_path, 14)
            except:
                continue
        
        if font_large is None:
            try:
                font_large = ImageFont.load_default()
                font_small = ImageFont.load_default()
            except:
                font_large = ImageFont.load_default()
                font_small = ImageFont.load_default()
        
        minutes = seconds_left // 60
        seconds = seconds_left % 60
        time_text = f"{minutes:02d}:{seconds:02d}"
        
        session_names = {
            'work': 'РАБОТА',
            'break': 'ОТДЫХ',
            'long_break': 'ДЛИННЫЙ ОТДЫХ'
        }
        
        bbox = draw.textbbox((0, 0), time_text, font=font_large)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        
        time_x = self.width // 2
        time_y = 40
        
        draw.text((time_x + 2, time_y + 2), time_text, fill=(0, 0, 0), font=font_large, anchor="mm")
        draw.text((time_x, time_y), time_text, fill=color, font=font_large, anchor="mm")
        
        session_text = session_names[session_type]
        session_x = self.width // 2
        session_y = 75
        
        draw.text((session_x + 1, session_y + 1), session_text, fill=(0, 0, 0), font=font_small, anchor="mm")
        draw.text((session_x, session_y), session_text, fill=(255, 255, 255), font=font_small, anchor="mm")
        
        progress = 1 - (seconds_left / total_seconds)
        bar_width = 250
        bar_height = 10
        bar_x = (self.width - bar_width) // 2
        bar_y = 100
        
        radius = 5
        
        draw.rectangle([bar_x, bar_y, bar_x + bar_width, bar_y + bar_height], fill=(80, 80, 80))
        
        fill_width = max(radius, int(bar_width * progress))
        if fill_width > radius:
            draw.rectangle([bar_x, bar_y, bar_x + fill_width, bar_y + bar_height], fill=color)
        
        percent_text = f"{int(progress * 100)}%"
        percent_x = bar_x + bar_width + 5
        percent_y = bar_y + bar_height // 2
        
        draw.text((percent_x, percent_y), percent_text, fill=(200, 200, 200), font=font_small, anchor="lm")
        
        return img

gif_creator = PomodoroGIFCreator()