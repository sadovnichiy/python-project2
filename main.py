import logging
import time
from aiogram import Bot, Dispatcher, executor, types
from aiogram.utils.exceptions import BotBlocked
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.contrib.fsm_storage.redis import RedisStorage2
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters import Text
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.types import ParseMode
from aiogram.utils import executor
from app.email_bot import send_code
import sys
import signal
import random
import emoji


logger = logging.getLogger(__name__)

logging.basicConfig(level=logging.INFO)

email_login = "phystech.tinder.bot@gmail.com"
email_password = open("config/email_password.txt").read()
API_TOKEN = open("config/token.txt").read()

storage = RedisStorage2()

bot = Bot(API_TOKEN)
dp = Dispatcher(bot, storage=storage)


@dp.errors_handler(exception=BotBlocked)
async def error_bot_blocked(update: types.Update, exception: BotBlocked):
    print(f"Меня заблокировал пользователь!\nСообщение: {update}\nОшибка: {exception}")


class User(StatesGroup):
    name = State()
    email = State()
    code = State()
    age = State()
    gender = State()
    spec = State()
    bio = State()
    photo = State()
    uni_pref = State()
    age_pref = State()
    gender_pref = State()
    logged = State()


@dp.message_handler(commands='start')
async def cmd_start(message: types.message):
    await message.answer("""Привет!
Я бот Физтех.Знакомства: помогу найти тебе пару!
На данный момент доступен для студентов из МФТИ и ВШЭ.
Чтобы начать регистрацию, напиши /register или 'Зарегистрироваться'
Чтобы посмотреть, какие данные уже записаны, напиши /info
Чтобы найти пару, напиши /match""", reply_markup=types.ReplyKeyboardRemove())


@dp.message_handler(commands='cancel', state='*')
@dp.message_handler(Text(equals="отмена", ignore_case=True), state='*')
async def cancel_handler(message: types.message, state: FSMContext):
    current_state = await state.get_state()
    if current_state is None:
        return

    await state.update_data(full=False)
    logging.info("Cancelling state %r", current_state)
    await state.finish()
    await message.answer("Отмена", reply_markup=types.ReplyKeyboardRemove())


@dp.message_handler(commands='register', state='*')
@dp.message_handler(Text(equals='Зарегистрироваться', ignore_case=True), state='*')
async def register(message: types.message, state: FSMContext):
    await state.update_data(full=False)
    await User.name.set()
    await message.answer("Для того, чтобы начать регистрацию, введи своё имя", reply_markup=types.ReplyKeyboardRemove())


async def get_profile(data, with_private=True):
    text=""
    if 'name' in data:
        text += f"Имя: {data['name']}\n"
    if 'university' in data:
        text += f"ВУЗ: {data['university']}\n"
    if 'age' in data:
        text += f"Возраст: {data['age']}\n"
    if 'gender' in data:
        text += f"Пол: {data['gender']}\n"
    if 'spec' in data:
        text += f"Специальность: {data['spec']}\n"
    if 'bio' in data:
        text += f"О себе: {data['bio']}\n"
    if with_private:
        text2 = ""
        if 'email' in data:
            text2 += f"email: {data['email']}\n"
        if 'uni_pref' in data:
            text2 += f"Предпочтения по вузу: {', '.join(data['uni_pref'])}\n"
        if 'age_pref' in data:
            text2 += f"Предпочтения по возрасту: {data['age_pref'][0]}-{data['age_pref'][1]}\n"
        if 'gender_pref' in data:
            text2 += f"Предпочтения по полу: {', '.join(data['gender_pref'])}\n"
        if text2 != "":
            text += "---Ниже не публичная информация---\n" + text2
    return "Анкета:\n" + text if text != "" else "Анкета пустая"


@dp.message_handler(commands='info', state='*')
async def info(message: types.message, state: FSMContext):
    
    async with state.proxy() as data:
        await message.answer(await get_profile(data), reply_markup=types.ReplyKeyboardRemove())

        if data.get('photo_id') is not None:
            await message.answer_photo(data['photo_id'])


@dp.message_handler(state=User.name)
async def process_name(message: types.message, state: FSMContext):
    name = message.text
    if (len(name) > 100):
        await message.answer("Имя слишком длинное. Попробуй ещё раз")
        return

    await state.update_data(name=name)
    await User.next()

    await message.answer("Теперь введи email, предоставленный университетом")

@dp.message_handler(state=User.email)
async def process_email(message: types.message, state: FSMContext):
    email = message.text
    if email.count('@') != 1:
        await message.answer("Некорректный email. Попробуй ещё раз")
        return

    if email.endswith("@phystech.edu") or email.endswith("@mipt.ru"):
        await state.update_data(university='МФТИ')
    elif email.endswith("@edu.hse.ru") or email.endswith("@hse.ru"):
        await state.update_data(university='ВШЭ')
    else:
        return await message.answer("Неправильный email. Попробуй ещё раз")

    await state.update_data(email=email)
    await User.next()

    async with state.proxy() as data:
        data['code'] = await send_code(email, data['name'], email_login, email_password)
        data['last_code'] = time.time()

    await message.answer("""Для проверки на почту должен прийти 6-значный код, напиши его ответным сообщением.
Если код не придёт, через минуту можно потребовать новый, написав 'Заново'
Не забудь проверить спам :)""")


@dp.message_handler(Text(equals='заново', ignore_case=True), state=User.code)
async def new_code(message: types.message, state: FSMContext):
    async with state.proxy() as data:
        if (time.time() - data['last_code'] < 60):
            return await message.answer("Подожди еще {} секунд".format(max(1, int(60 - (time.time() - data['last_code'])))))

        data['code'] = await send_code(data['email'], data['name'], email_login, email_password)
        data['last_code'] = time.time()

    await message.answer("Отправлен новый код")


@dp.message_handler(state=User.code)
async def process_code(message: types.message, state: FSMContext):
    code = message.text
    async with state.proxy() as data:
        if not code.isdigit() or data['code'] != int(code):
            if 'wrong_attempts' not in data:
                data['wrong_attempts'] = 1
            else:
                data['wrong_attempts'] += 1
            if data['wrong_attempts'] >= 5:
                await message.answer("Слишком много неправильных попыток.\nНапиши 'Заново', чтобы отправить новый код")
                return
            
            await message.answer("Неправильный код. Попробуй ещё раз")
            return
        
        if 'wrong_attempts' in data and data['wrong_attempts'] >= 5:
            await message.answer("Слишком много неправильных попыток.\nНапиши 'Заново', чтобы отправить новый код")
            return

        data.pop('wrong_attempts')
        data.pop('last_code')
        data.pop('code')

    await User.next()
    await message.answer("Отлично, код правильный!\nТеперь введи, пожалуйста, свой возраст")


@dp.message_handler(lambda message: not message.text.isdigit(), state=User.age)
async def process_age_invalid(message: types.Message):
    return await message.answer("Возраст должен быть числом. Попробуй ещё раз")


@dp.message_handler(lambda message: message.text.isdigit(), state=User.age)
async def process_age(message: types.Message, state: FSMContext):
    age = int(message.text)
    if age < 18:
        await message.answer("К сожалению, бот доступен только для совершеннолетних пользователей")
        await cancel_handler(message, state)
        return
    
    await User.next()
    await state.update_data(age=age)

    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, selective=True)
    markup.add('Мужской', 'Женский')
    markup.add('Другой')

    await message.answer('Введи свой пол:', reply_markup=markup)


@dp.message_handler(lambda message: message.text not in ['Мужской', 'Женский', 'Другой'], state=User.gender)
async def process_gender_invalid(message: types.Message, state: FSMContext):
    return await message.answer("Такого варианта нет. Пожалуйста, выбери вариант из предложенных")


@dp.message_handler(state=User.gender)
async def process_gender(message: types.Message, state: FSMContext):
    await state.update_data(gender=message.text)
    await User.next()

    await message.answer("Напиши, пожалуйста, направление обучения (профильные предметы)", \
                        reply_markup=types.ReplyKeyboardRemove())


@dp.message_handler(lambda message: len(message.text) > 100, state=User.spec)
async def process_spec_invalid(message: types.Message, state: FSMContext):
    return await message.answer("Слишком длинная строка. Попробуй ещё раз")


@dp.message_handler(state=User.spec)
async def process_spec(message: types.Message, state: FSMContext):
    await state.update_data(spec=message.text)
    await User.next()
    await message.answer("Осталось совсем чуть-чуть! Напиши немного о себе")


@dp.message_handler(lambda message: len(message.text) > 1000, state=User.bio)
async def process_bio_invalid(message: types.Message, state: FSMContext):
    return await message.answer("Слишком много для 'немного о себе'! Попробуй покороче")


@dp.message_handler(state=User.bio)
async def process_bio(message: types.Message, state: FSMContext):
    await state.update_data(bio=message.text)
    await User.next()
    await message.answer("""Теперь пришли свою фотографию, рекомендуется в анфас.
Это необязательно, но помни, что анкеты с фотографиями нравятся намного чаще :)
Чтобы не отправлять фотографию, можешь написать любой текст""")


@dp.message_handler(content_types=['photo'], state=User.photo)
async def process_photo(message: types.Message, state: FSMContext):
    await state.update_data(photo_id=message.photo[0].file_id)
    
    await User.next()

    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, selective=True)
    markup.add('МФТИ', 'ВШЭ')
    markup.add('МФТИ и ВШЭ')
    await message.answer("""Переходим к последней части анкеты.
Напиши свои предпочтения по вузу:""", reply_markup=markup)


@dp.message_handler(state=User.photo)
async def process_photo(message: types.Message, state: FSMContext):
    await state.update_data(photo_id=None)
    await User.next()

    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, selective=True)
    markup.add('МФТИ', 'ВШЭ')
    markup.add('МФТИ и ВШЭ')
    await message.answer("""Переходим к последней части анкеты.
Напиши свои предпочтения по вузу:""", reply_markup=markup)


@dp.message_handler(lambda message: message.text not in ['МФТИ', 'ВШЭ', 'МФТИ и ВШЭ'], state=User.uni_pref)
async def process_uni_pref_invalid(message: types.Message, state: FSMContext):
    return await message.answer("Такого варианта нет. Пожалуйста, выбери вариант из предложенных")


@dp.message_handler(state=User.uni_pref)
async def process_uni_pref(message: types.Message, state: FSMContext):
    if message.text == 'МФТИ':
        await state.update_data(uni_pref=['МФТИ'])
    elif message.text == 'ВШЭ':
        await state.update_data(uni_pref=['ВШЭ'])
    else:
        await state.update_data(uni_pref=['МФТИ', 'ВШЭ'])

    await User.next()

    await message.answer("Напиши свои предпочтения по возрасту в формате 'мин.возраст-макс.возраст', например:'19-20'",
                         reply_markup=types.ReplyKeyboardRemove())


@dp.message_handler(state=User.age_pref)
async def process_age_pref(message: types.Message, state: FSMContext):
    ages = message.text.split('-')
    if len(ages) != 2 or not ages[0].isdigit() or not ages[1].isdigit():
        return await message.answer("Неправильный формат. Попробуй ещё раз")
    
    ages[0] = int(ages[0])
    ages[1] = int(ages[1])
    if ages[0] > ages[1]:
        return await message.answer("Минимальный возраст не может быть больше максимального. Попробуй ещё раз")
    
    if ages[0] < 18:
        return await message.answer("Бот доступен только для пользователей старше 18 лет. Попробуй ещё раз")

    if ages[0] > 122:
        return await message.answer("Согласно книге рекордов Гиннеса самый старый человек умер в возрасте 122 лет. Попробуй ещё раз")

    await state.update_data(age_pref=(ages[0], ages[1]))
    await User.next()

    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, selective=True)
    markup.add('Мужской', 'Женский')
    markup.add('Мужской и женский', 'Другой')
    await message.answer("Выбери свои предпочтения по полу партнера", reply_markup=markup)


@dp.message_handler(lambda message: message.text not in ['Мужской', 'Женский', 'Мужской и женский', 'Другой'], state=User.gender_pref)
async def process_gender_pref_invalid(message: types.Message, state: FSMContext):
    return await message.answer("Такого варианта нет. Пожалуйста, выбери вариант из предложенных")


@dp.message_handler(state=User.gender_pref)
async def process_gender_pref(message: types.Message, state: FSMContext):
    if message.text == 'Мужской':
        await state.update_data(gender_pref=['Мужской'])
    elif message.text == 'Женский':
        await state.update_data(gender_pref=['Женский'])
    elif message.text == 'Мужской и женский':
        await state.update_data(gender_pref=['Мужской', 'Женский'])
    elif message.text == 'Другой':
        await state.update_data(gender_pref=['Другой'])
    
    await state.update_data(full=True)
    await User.next()

    async with state.proxy() as data:
        await message.answer("Ура, анкета заполнена! Проверь полученные данные:")
        await info(message, state)
        await message.answer("""Если что-то не так, начни регистрацию сначала, написав /register
Чтобы найти мэтч, напиши /match""")


@dp.message_handler(commands='match', state=User.logged)
async def process_match(message: types.Message, state: FSMContext):
    async with state.proxy() as data:
        data['username'] = message.from_user.username
        if 'liked' not in data:
            data['liked'] = []
        if 'disliked' not in data:
            data['disliked'] = []

        list_users = await dp.storage.get_states_list()
        random.shuffle(list_users)
        match = None
        for chat, user in list_users:
            if chat == message.chat.id and user == message.from_user.id:
                continue
            if str(chat) + '_' + str(user) in data['liked'] or str(chat) + '_' + str(user) in data['disliked']:
                continue
            user_data = await dp.storage.get_data(chat=chat, user=user)
            if not user_data.get('full'):
                continue
            if 'uni_pref' not in data or 'uni_pref' not in user_data:
                continue
            if user_data['university'] not in data['uni_pref'] or data['university'] not in user_data['uni_pref']:
                continue
            if user_data['age'] < data['age_pref'][0] or user_data['age'] > data['age_pref'][1]:
                continue
            if data['age'] < user_data['age_pref'][0] or data['age'] > user_data['age_pref'][1]:
                continue
            if user_data['gender'] not in data['gender_pref'] or data['gender'] not in user_data['gender_pref']:
                continue
            match = (chat, user)
            break
        if match is None:
            return await message.answer("К сожалению, никаких мэтчей нет :(\nПопробуй позже!")
        buttons = [
            types.InlineKeyboardButton(text=emoji.emojize(":red_heart:"), callback_data="like_" + str(chat) + '_' + str(user)),
            types.InlineKeyboardButton(text=emoji.emojize(":broken_heart:"), callback_data="dislike_" + str(chat) + '_' + str(user))
        ]
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(*buttons)
        await message.answer("Ура! Найден мэтч:", reply_markup=types.ReplyKeyboardRemove())
        if user_data['photo_id'] is not None:
            await message.answer_photo(user_data['photo_id'])
        await message.answer(await get_profile(user_data, with_private=False), reply_markup=markup)


@dp.message_handler(commands='match', state='*')
async def process_match_invalid(message: types.Message, state: FSMContext):
    return await message.answer("Твоя анкета не заполнена до конца. Пожалуйста, сначала заполни её")


@dp.callback_query_handler(Text(startswith="like_"), state='*')
async def callbacks_like(call: types.CallbackQuery):
    chat, user = call.message.chat.id, call.from_user.id
    partner_chat, partner_user = call.data.split("_")[1:3]
    user_data = await dp.storage.get_data(chat=chat, user=user)
    await dp.storage.update_data(chat=chat, user=user, data={'liked': [str(partner_chat) + '_' + str(partner_user)] + user_data['liked']})
    partner_data = await dp.storage.get_data(chat=partner_chat, user=partner_user)
    if str(chat) + '_' + str(user) in partner_data['liked']:
        await bot.send_message(chat, f"Поздравляю, нашлась пара: {partner_data['name']} @{partner_data['username']}")
        await bot.send_message(partner_chat, f"Поздравляю, нашлась пара: {user_data['name']} @{user_data['username']}")
    await call.answer()
    
    
@dp.callback_query_handler(Text(startswith="dislike_"), state='*')
async def callbacks_dislike(call: types.CallbackQuery):
    chat, user = call.message.chat.id, call.from_user.id
    partner_chat, partner_user = call.data.split("_")[1:3]
    user_data = await dp.storage.get_data(chat=chat, user=user)
    await dp.storage.update_data(chat=chat, user=user, data={'disliked': [str(partner_chat) + '_' + str(partner_user)] + user_data['disliked']})
    await call.answer()


async def on_exit(signum, frame):
    await dp.storage.close()
    await dp.storage.wait_closed()
    sys.exit(0)


signal.signal(signal.SIGTERM, on_exit)

if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True)
