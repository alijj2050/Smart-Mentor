from fastapi import FastAPI, HTTPException, Request, BackgroundTasks, Depends
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
import os
import sqlite3
import logging
from hazm import word_tokenize, Normalizer, stopwords_list
from datetime import datetime
from typing import Optional, List, Dict, Tuple
from dotenv import load_dotenv
import redis
import aiosqlite
from openai import OpenAI
import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    DATABASE_PATH = os.getenv("DATABASE_PATH", "mentor.db")
    REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
    api_key = os.getenv("OPENAI_API_KEY", "missing-key")

# بارگذاری متغیرهای محیطی
env_path = os.path.join(os.path.dirname(__file__), '.env')
load_dotenv(env_path)

# پیکربندی برنامه
class Config:
    DATABASE_PATH = "mentor.db"
    REDIS_HOST = "localhost"
    REDIS_PORT = 6379
    api_key = os.getenv("OPENAI_API_KEY", "missing-key")
    if api_key == "missing-key":
        logging.warning("کلید API یافت نشد. برنامه بدون استفاده از API ادامه می‌یابد.")
        api_key = None

# تنظیمات لاگینگ
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# تنظیمات FastAPI
app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# تنظیمات OpenAI
client = OpenAI(
    api_key=Config.api_key,
)

# ابزارهای کمکی پایگاه داده
async def get_db():
    async with aiosqlite.connect(Config.DATABASE_PATH) as db:
        yield db

async def create_tables():
    async with aiosqlite.connect(Config.DATABASE_PATH) as db:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                phone_number TEXT NOT NULL UNIQUE
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS user_qa_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                question TEXT NOT NULL,
                answer TEXT NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS qa (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                question TEXT UNIQUE NOT NULL,
                answer TEXT NOT NULL
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS menu (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                price INTEGER NOT NULL,
                description TEXT NOT NULL
            )
            """
        )
        await db.commit()

# ابزارهای کمکی Redis
class Cache:
    _client = None

    @staticmethod
    def connect():
        try:
            Cache._client = redis.Redis(host=Config.REDIS_HOST, port=Config.REDIS_PORT, db=0)
            Cache._client.ping()
            logging.info("Connected to Redis successfully.")
        except redis.exceptions.ConnectionError:
            logging.warning("Redis connection failed. Using in-memory cache.")
            Cache._client = None

    @staticmethod
    def get(key: str) -> Optional[str]:
        if Cache._client:
            try:
                value = Cache._client.get(key)
                return value.decode() if value else None
            except redis.exceptions.ConnectionError:
                logging.warning("Redis connection error during GET.")
        return None

    @staticmethod
    def set(key: str, value: str):
        if Cache._client:
            try:
                Cache._client.set(key, value)
            except redis.exceptions.ConnectionError:
                logging.warning("Redis connection error during SET.")

Cache.connect()

# ابزارهای پردازش متن
normalizer = Normalizer()
stop_words = set(stopwords_list())

def preprocess_text(text: str) -> str:
    if not text:
        return ""
    normalized_text = normalizer.normalize(text)
    tokens = word_tokenize(normalized_text)
    return ' '.join(word for word in tokens if word not in stop_words)

# مدیریت پاسخ‌ها
class ResponseHandler:
    @staticmethod
    async def get_cached_answer(question: str) -> Optional[str]:
        answer = Cache.get(question)
        if answer:
            return answer

        async with aiosqlite.connect(Config.DATABASE_PATH) as db:
            cursor = await db.execute("SELECT answer FROM qa WHERE question = ?", (question,))
            result = await cursor.fetchone()
            return result[0] if result else None

    @staticmethod
    async def save_answer(question: str, answer: str):
        async with aiosqlite.connect(Config.DATABASE_PATH) as db:
            await db.execute("INSERT OR IGNORE INTO qa (question, answer) VALUES (?, ?)", (question, answer))
            await db.commit()
        Cache.set(question, answer)

# مدل‌های Pydantic
class User(BaseModel):
    name: str
    phone_number: str

class Question(BaseModel):
    text: str

class Answer(BaseModel):
    answer: str

class MenuItem(BaseModel):
    name: str
    price: int
    description: str

# تابع برای دریافت آیتم‌های منو
async def get_menu_items(db: aiosqlite.Connection) -> List[Tuple[str, int, str]]:
    """
    دریافت لیست آیتم‌های منو از پایگاه داده.
    """
    try:
        cursor = await db.execute("SELECT name, price, description FROM menu")
        menu_items = await cursor.fetchall()
        return menu_items
    except Exception as e:
        logging.error(f"Error fetching menu items: {e}")
        return []

# تابع برای دریافت پاسخ از GPT
async def get_gpt_response(question: str, conversation_history: List[Dict[str, str]], db: aiosqlite.Connection) -> str:
    menu_items = await get_menu_items(db)
    menu_info = "\n".join([f"{item[0]}: {item[1]} تومان - {item[2]}" for item in menu_items])

    system_message = (
        "تو یک دستیار هوش مصنوعی هستی، اسم تو ژاویر هست، ژاویر یک کافه رستوران باحاله. "
        "کافه رستوران ژاویر آدرس تهران مرزداران. کیفیت غذاهای ما عالیه! جواب ها کوتاه باشن با استیکر بسیارجذاب و دوستانه و با صحبت عامیانه صحبت کن. "
        "فقط به سوالات مربوط به کافه و رستوران و اطلاعات داده شد را پاسخ بده. قیمت و لیست غذاهای ما به شرح زیر می باشد:\n\nمنو:\n" + menu_info
    )

    messages = [
        {"role": "system", "content": system_message},
        *conversation_history,
        {"role": "user", "content": question},
    ]

    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=messages,
            max_tokens=250,
            temperature=0.7,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logging.error(f"Error getting GPT response: {e}")
        return "متأسفم، مشکلی در پردازش سوال شما پیش آمد. لطفاً دوباره امتحان کنید."

# API‌ها
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/register")
async def register_user(user: User, db: aiosqlite.Connection = Depends(get_db)):
    try:
        await db.execute(
            "INSERT OR IGNORE INTO users (name, phone_number) VALUES (?, ?)",
            (user.name, user.phone_number)
        )
        await db.commit()
        return {"message": "کاربر با موفقیت ثبت شد."}
    except Exception as e:
        logging.error(f"Error registering user: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="خطای سرور")

@app.post("/ask")
async def ask_question(question: Question, request: Request, background_tasks: BackgroundTasks, db: aiosqlite.Connection = Depends(get_db)):
    try:
        phone_number = request.headers.get("phone-number")
        if not phone_number:
            raise HTTPException(status_code=401, detail="لطفاً ابتدا وارد شوید.")

        cursor = await db.execute("SELECT id FROM users WHERE phone_number = ?", (phone_number,))
        user = await cursor.fetchone()
        if not user:
            raise HTTPException(status_code=404, detail="کاربر یافت نشد.")
        user_id = user[0]

        question_text = preprocess_text(question.text)
        cached_answer = await ResponseHandler.get_cached_answer(question_text)
        if cached_answer:
            return {"answer": cached_answer}

        cursor = await db.execute("SELECT question, answer FROM user_qa_history WHERE user_id = ? ORDER BY timestamp DESC LIMIT 5", (user_id,))
        rows = await cursor.fetchall()
        conversation_history = []
        for row in rows:
            conversation_history.append({"role": "user", "content": row[0]})
            conversation_history.append({"role": "assistant", "content": row[1]})

        gpt_answer = await get_gpt_response(question.text, conversation_history, db)

        await ResponseHandler.save_answer(question.text, gpt_answer)

        await db.execute(
            "INSERT INTO user_qa_history (user_id, question, answer) VALUES (?, ?, ?)",
            (user_id, question.text, gpt_answer)
        )
        await db.commit()

        return {"answer": gpt_answer}
    except Exception as e:
        logging.error(f"Error processing question: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="خطای سرور")

@app.post("/add_menu_item")
async def add_menu_item(item: MenuItem, db: aiosqlite.Connection = Depends(get_db)):
    try:
        await db.execute(
            "INSERT OR IGNORE INTO menu (name, price, description) VALUES (?, ?, ?)",
            (item.name, item.price, item.description)
        )
        await db.commit()
        return {"message": "آیتم منو با موفقیت اضافه شد."}
    except Exception as e:
        logging.error(f"Error adding menu item: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="خطای سرور")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8080)
