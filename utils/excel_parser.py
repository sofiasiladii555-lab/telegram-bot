import pandas as pd
from datetime import datetime, time
from database import Session, Task, Duty, User
from loguru import logger


async def parse_and_save_excel_from_bytes(file_path: str, task_type: str, bot, admin_id: int):
    """Парсер для файла на диске (принимает путь к файлу).
    Столбцы Excel: Дата, Время (необязательно), Задание, Telegram_Username / Full_Name / Telegram_ID, Неделя
    """
    try:
        df = pd.read_excel(file_path)
        df.columns = [str(col).strip() for col in df.columns]

        if "Дата" not in df.columns:
            raise Exception("В Excel нет обязательной колонки 'Дата'.\nПроверь заголовки!")
        if "Задание" not in df.columns:
            raise Exception("В Excel нет обязательной колонки 'Задание'.\nПроверь заголовки!")
        if "Telegram_Username" not in df.columns and "Full_Name" not in df.columns:
            raise Exception(
                "В Excel должна быть хотя бы одна колонка: 'Telegram_Username' или 'Full_Name'.\n"
                "Проверь заголовки!"
            )

        session = Session()
        added = 0
        not_found = []

        for _, row in df.iterrows():
            try:
                due_date = pd.to_datetime(row["Дата"]).to_pydatetime()

                # Если есть столбец Время — объединяем с датой
                raw_time = str(row.get("Время", "")).strip()
                if raw_time and raw_time not in ("nan", "none", ""):
                    try:
                        parsed_time = pd.to_datetime(raw_time).time()
                        due_date = due_date.replace(
                            hour=parsed_time.hour,
                            minute=parsed_time.minute,
                            second=0
                        )
                    except Exception:
                        pass

                description = str(row["Задание"]).strip()
                week = str(row.get("Неделя", "")).strip()

                raw_tg_id    = str(row.get("Telegram_ID", "")).strip()
                raw_username = str(row.get("Telegram_Username", "")).strip().lower().replace("@", "")
                raw_fullname = str(row.get("Full_Name", "")).strip()

                tg_id    = int(raw_tg_id) if raw_tg_id not in ("", "nan", "none") and raw_tg_id.isdigit() else None
                username = raw_username if raw_username not in ("", "nan", "none") else None
                fullname = raw_fullname if raw_fullname not in ("", "nan", "none") else None

                user = None
                if tg_id:
                    user = session.query(User).filter(User.tg_id == tg_id).first()
                if not user and username:
                    user = session.query(User).filter(User.username.ilike(username)).first()
                if not user and fullname:
                    user = session.query(User).filter(User.full_name.ilike(fullname)).first()

                if not user:
                    label = str(tg_id) if tg_id else (f"@{username}" if username else fullname or "???")
                    not_found.append(label)
                    continue

                task = Task(
                    due_date=due_date,
                    user_tg_id=user.tg_id,
                    task_type=task_type,
                    description=description,
                    week=week
                )
                session.add(task)
                added += 1

            except Exception as row_e:
                logger.error(f"Ошибка обработки строки: {row_e}")

        session.commit()
        session.close()

        msg = f"✅ Успешно добавлено *{added}* заданий типа '{task_type}'."
        if not_found:
            msg += (
                f"\n\n⚠️ Не найдены пользователи ({len(not_found)} чел.):\n"
                f"{', '.join(not_found)}\n\n"
                f"Эти люди ещё не писали боту /start или имя указано неверно."
            )

        await bot.send_message(admin_id, msg, parse_mode="Markdown")

    except Exception as e:
        await bot.send_message(admin_id, f"❌ Ошибка при чтении Excel:\n{str(e)}")
        logger.error(f"Парсер ошибка: {e}")


async def parse_and_save_duty_excel(file_path: str, bot, admin_id: int):
    """Парсер графика дежурств группы.
    Столбцы Excel: Дата, Время
    """
    try:
        df = pd.read_excel(file_path)
        df.columns = [str(col).strip() for col in df.columns]

        if "Дата" not in df.columns:
            raise Exception("В Excel нет обязательной колонки 'Дата'.\nПроверь заголовки!")
        if "Время" not in df.columns:
            raise Exception("В Excel нет обязательной колонки 'Время'.\nПроверь заголовки!")

        session = Session()
        added = 0

        for _, row in df.iterrows():
            try:
                duty_date = pd.to_datetime(row["Дата"]).to_pydatetime()

                raw_time = str(row.get("Время", "")).strip()
                if raw_time and raw_time not in ("nan", "none", ""):
                    try:
                        parsed_time = pd.to_datetime(raw_time).time()
                        duty_date = duty_date.replace(
                            hour=parsed_time.hour,
                            minute=parsed_time.minute,
                            second=0
                        )
                    except Exception:
                        pass

                duty = Duty(duty_date=duty_date)
                session.add(duty)
                added += 1

            except Exception as row_e:
                logger.error(f"Ошибка обработки строки дежурства: {row_e}")

        session.commit()
        session.close()

        await bot.send_message(
            admin_id,
            f"✅ Успешно добавлено *{added}* дат дежурств группы.",
            parse_mode="Markdown"
        )

    except Exception as e:
        await bot.send_message(admin_id, f"❌ Ошибка при чтении Excel дежурств:\n{str(e)}")
        logger.error(f"Парсер дежурств ошибка: {e}")
