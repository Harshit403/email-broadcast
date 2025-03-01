from fastapi import FastAPI, Form, Request
from fastapi.templating import Jinja2Templates
from fastapi.responses import FileResponse
import redis
import json
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from starlette.responses import RedirectResponse
import mistune  # Markdown parser
import logging
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# FastAPI app & Jinja Templates
app = FastAPI()
templates = Jinja2Templates(directory="templates")

# Configure Logging
logging.basicConfig(filename="logs.txt", level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Upstash Redis Connection
UPSTASH_REDIS_URL = os.getenv("UPSTASH_REDIS_URL")
UPSTASH_REDIS_PASSWORD = os.getenv("UPSTASH_REDIS_PASSWORD")
redis_client = redis.Redis.from_url(UPSTASH_REDIS_URL, password=UPSTASH_REDIS_PASSWORD, decode_responses=True, ssl=True)

# SMTP Configuration
SMTP_SERVER = os.getenv("SMTP_SERVER")
SMTP_PORT = int(os.getenv("SMTP_PORT", 587))
SMTP_USERNAME = os.getenv("SMTP_USERNAME")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")

# Admin Panel - Homepage
@app.get("/")
async def admin_panel(request: Request):
    try:
        groups = {key: json.loads(redis_client.get(key)) for key in redis_client.keys("group:*")}
        return templates.TemplateResponse("index.html", {"request": request, "groups": groups})
    except Exception as e:
        logging.error(f"Error loading admin panel: {e}")
        return {"error": "Something went wrong!"}

# Create Group
@app.post("/create_group/")
async def create_group(name: str = Form(...), emails: str = Form(...)):
    try:
        email_list = [email.strip() for email in emails.split(",") if email.strip()]
        if not (4 <= len(email_list) <= 5):
            logging.warning("Group must have 4-5 members.")
            return RedirectResponse(url="/", status_code=303)

        group_id = f"group:{name}"
        redis_client.set(group_id, json.dumps(email_list))
        logging.info(f"Created group '{name}' with members: {email_list}")

        return RedirectResponse(url="/", status_code=303)
    except Exception as e:
        logging.error(f"Error creating group: {e}")
        return RedirectResponse(url="/", status_code=303)

# Send Broadcast Email
@app.post("/broadcast/")
async def broadcast_email(group_name: str = Form(...), subject: str = Form(...), message: str = Form(...), format_type: str = Form(...)):
    try:
        group_id = f"group:{group_name}"
        recipients = json.loads(redis_client.get(group_id)) if redis_client.exists(group_id) else []

        if not recipients:
            logging.warning(f"Broadcast failed: No recipients found for group {group_name}.")
            return RedirectResponse(url="/", status_code=303)

        message_content = mistune.markdown(message) if format_type == "markdown" else message

        msg = MIMEMultipart()
        msg["Subject"] = subject
        msg["From"] = SMTP_USERNAME
        msg["To"] = ", ".join(recipients)
        msg.attach(MIMEText(message_content, "html"))

        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USERNAME, SMTP_PASSWORD)
            server.sendmail(SMTP_USERNAME, recipients, msg.as_string())

        logging.info(f"Broadcast sent to group '{group_name}' - {len(recipients)} recipients.")
        return RedirectResponse(url="/", status_code=303)

    except Exception as e:
        logging.error(f"Error sending broadcast: {e}")
        return RedirectResponse(url="/", status_code=303)

# Download Logs
@app.get("/logs/")
async def download_logs():
    return FileResponse("logs.txt", media_type="text/plain", filename="logs.txt")
