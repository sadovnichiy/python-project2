import asyncio
import aiosmtplib
import secrets
from email.message import EmailMessage


async def send_code(to, name, login, password) -> int:
    code = secrets.choice(range(100000, 1000000))

    message = EmailMessage()
    message["From"] = login
    message["To"] = to
    message["Subject"] = "Регистрация в Физтех.Знакомства"
    message.set_content("Привет, {}!\nКод регистрации: {}".format(name, code))

    await aiosmtplib.send(message, hostname="smtp.gmail.com", port=465, 
                            use_tls=True, username=login, password=password)
    return code