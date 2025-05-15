from fastapi import FastAPI, File, UploadFile, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from typing import List, Optional
from PIL import Image
import pytesseract
import io
import uvicorn
import os
import json
from datetime import datetime
from langchain.chat_models import ChatOpenAI
from langchain.schema import SystemMessage, HumanMessage
from dotenv import load_dotenv
import re

load_dotenv()

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

class PostContent(BaseModel):
    chapter: str
    title: str
    intro: str
    quote: str
    highlights: List[str]
    hashtags: List[str]
    schedule: str

llm = ChatOpenAI(model_name="gpt-4o", temperature=0.3)

@app.post("/upload")
async def upload_images(
    files: List[UploadFile] = File(...),
    schedule: Optional[str] = Form(None),
    instruction: Optional[str] = Form("")
):
    now_time = datetime.now().strftime("%Y-%m-%dT%H:%M:%S+08:00")
    schedule = schedule or now_time

    all_text = ""
    filenames = []
    for file in files:
        contents = await file.read()
        image = Image.open(io.BytesIO(contents))
        text = pytesseract.image_to_string(image, lang='chi_tra')
        all_text += f"\n{text}\n"
        filenames.append(file.filename)

    output_dir = "output"
    os.makedirs(output_dir, exist_ok=True)
    existing = [f for f in os.listdir(output_dir) if f.startswith("post_") and f.endswith(".json")]
    latest_num = 0
    for name in existing:
        match = re.search(r'post_(\d+)', name)
        if match:
            latest_num = max(latest_num, int(match.group(1)))
    next_post_num = latest_num + 1
    chapter_tag = f"#{str(next_post_num).zfill(2)}"

    base_prompt = f"""
你是一位社群小編，幫我將以下多章節內容整合為一篇 IG/Threads 書摘格式貼文，請回傳純 JSON（不要有```json）：

📘【{chapter_tag}｜自動產生標題】
請統整所有段落內容，融合每章精華為連貫貼文。

請補一句開頭「引導語」作為貼文開場，幫助讀者快速進入主題。

請分段書寫，正文中可使用 ✅、📌、🎯 開頭的重點句段（建議 5 條以內）
最後加上一段 🔖 hashtag（6~9 個）

JSON 欄位需包含：
- chapter（例如：第24～28章）
- title（貼文標題）
- intro（開場引導語）
- quote（金句一句）
- highlights（整理後的 3~6 句重點句，帶 emoji）
- hashtags（6~9 個話題標籤）
- schedule（{schedule}）
"""
    final_prompt = instruction if instruction else base_prompt

    messages = [SystemMessage(content=final_prompt), HumanMessage(content=all_text.strip())]
    response = llm(messages)
    result_json = response.content.strip()

    try:
        parsed_json = json.loads(result_json)
        raw_chapter = parsed_json.get("chapter", f"post_{next_post_num}")
        safe_chapter = re.sub(r"[^\w\d一-龥]", "_", str(raw_chapter))[:20]
    except Exception:
        safe_chapter = f"post_{next_post_num}"

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filepath = os.path.join(output_dir, f"post_{next_post_num}_{timestamp}.json")
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(result_json)

    return {
        "status": "success",
        "results": [{
            "file": " + ".join(filenames),
            "path": filepath,
            "schedule": schedule
        }],
        "preview": parsed_json.get("intro", "") + "\n\n" + parsed_json.get("chapter", "") + "\n" + parsed_json.get("quote", "") + "\n\n" + "\n".join(parsed_json.get("highlights", [])) + "\n\n" + " ".join(parsed_json.get("hashtags", []))
    }

@app.get("/web", response_class=HTMLResponse)
async def get_upload_form(request: Request):
    return templates.TemplateResponse("upload.html", {"request": request})

# 啟動用指令：uvicorn main:app --reload
