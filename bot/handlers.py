"""Telegram handlers for the UIABot."""

from __future__ import annotations

import logging
from datetime import datetime, time, timedelta
from dataclasses import dataclass
from enum import Enum, auto
from typing import Dict, List

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    Update,
)
from telegram.ext import (
    Application,
    CallbackContext,
    CallbackQueryHandler,
    CommandHandler,
    ConversationHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from .ai import AIAssistant
from .config import BotConfig, Engineer
from .database import Database


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class IssueCategory:
    key: str
    title: str
    basic_guidance: str


ISSUE_CATEGORIES: List[IssueCategory] = [
    IssueCategory(
        key="able_erp",
        title="Able ERP систем",
        basic_guidance=(
            "Able ERP-т холбогдохгүй байвал эхлээд VPN идэвхтэй эсэх, интернэт ажиллаж "
            "байгааг шалгана уу. Браузерийн кэш цэвэрлээд дахин нэвтэрч үзнэ үү."
        ),
    ),
    IssueCategory(
        key="network",
        title="Интернэт сүлжээ",
        basic_guidance=(
            "Интернэтийн кабель, Wi-Fi төхөөрөмжөө дахин асааж, өөр төхөөрөмж дээр "
            "сүлжээ орж байгаа эсэхийг шалгана уу."
        ),
    ),
    IssueCategory(
        key="software",
        title="Программ хангамж",
        basic_guidance=(
            "Програмын лиценз хүчинтэй эсэх, хамгийн сүүлийн шинэчлэл суусан эсэхийг шалгаад "
            "дахин ажиллуулна уу."
        ),
    ),
    IssueCategory(
        key="hardware",
        title="Тоног төхөөрөмж",
        basic_guidance=(
            "Компьютерийн тэжээл, кабель, холболтуудыг шалгана уу. Өөр төхөөрөмж дээр туршиж үзнэ үү."
        ),
    ),
    IssueCategory(
        key="printer",
        title="Принтер",
        basic_guidance=(
            "Принтер асаалттай, цаас болон хор байгаа эсэхийг шалгаад драйверыг дахин ачааллана уу."
        ),
    ),
    IssueCategory(
        key="email",
        title="И-мэйл үйлчилгээ",
        basic_guidance=(
            "И-мэйл хаягийн тохиргоо, интернет сүлжээ хэвийн эсэхийг шалгаад веб мэйлээр нэвтэрч үзнэ үү."
        ),
    ),
]

ISSUE_BY_TITLE: Dict[str, IssueCategory] = {item.title: item for item in ISSUE_CATEGORIES}


class ConversationState(Enum):
    ASK_EMPLOYEE_CODE = auto()
    ASK_NAME = auto()
    ASK_DEPARTMENT = auto()
    CHOOSE_ISSUE = auto()
    BASIC_FOLLOWUP = auto()
    REQUEST_DETAILS = auto()
    AI_FOLLOWUP = auto()


YES_NO_KEYBOARD = ReplyKeyboardMarkup(
    [["Тийм", "Үгүй"]], resize_keyboard=True, one_time_keyboard=True
)

ISSUE_KEYBOARD = ReplyKeyboardMarkup(
    [
        [item.title for item in ISSUE_CATEGORIES[i : i + 2]]
        for i in range(0, len(ISSUE_CATEGORIES), 2)
    ],
    resize_keyboard=True,
)

YES_RESPONSES = {"тийм", "tiim", "yes", "y"}
NO_RESPONSES = {"үгүй", "ugui", "no", "n"}


class BotHandler:
    def __init__(self, config: BotConfig, database: Database, ai: AIAssistant) -> None:
        self._config = config
        self._database = database
        self._ai = ai
        self._report_keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("Өнөөдөр", callback_data="report:today"),
                    InlineKeyboardButton("Сүүлийн 7 хоног", callback_data="report:7d"),
                ],
                [
                    InlineKeyboardButton("Энэ сар", callback_data="report:month"),
                    InlineKeyboardButton("Өнгөрсөн сар", callback_data="report:prev_month"),
                ],
                [InlineKeyboardButton("Хугацаа сонгох", callback_data="report:custom")],
            ]
        )

    def _within_working_hours(self) -> bool:
        now = datetime.now().time()
        start = time(9, 0)
        end = time(18, 0)
        return start <= now < end

    # Conversation flow --------------------------------------------------
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> ConversationState:
        context.user_data.clear()
        if not self._within_working_hours():
            await update.message.reply_text(
                "Уучлаарай, ажлын цаг дууссан байна. Бид 09:00-18:00 цагийн хооронд дуудлага хүлээн авна.",
                reply_markup=ReplyKeyboardRemove(),
            )
            return ConversationHandler.END
        if self._config.employee_codes or self._database.has_employee_codes():
            await update.message.reply_text(
                "Сайн байна уу. Та өөрийн ажилтны кодоо оруулна уу.",
                reply_markup=ReplyKeyboardRemove(),
            )
            context.user_data["employee_code_attempts"] = 0
            return ConversationState.ASK_EMPLOYEE_CODE

        await update.message.reply_text(
            "Сайн байна уу. Та өөрийн овог, нэрээ оруулна уу.",
            reply_markup=ReplyKeyboardRemove(),
        )
        return ConversationState.ASK_NAME

    async def receive_employee_code(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> ConversationState:
        code = update.message.text.strip()
        attempts = int(context.user_data.get("employee_code_attempts", 0)) + 1
        context.user_data["employee_code_attempts"] = attempts

        if code in self._config.employee_codes or self._database.is_employee_code_allowed(code):
            context.user_data["employee_code"] = code
            context.user_data.pop("employee_code_attempts", None)
            employee = self._database.get_employee(code)
            if employee and employee.get("full_name"):
                context.user_data["full_name"] = employee["full_name"]
                if employee.get("department"):
                    context.user_data["department"] = employee["department"]
                    await update.message.reply_text(
                        (
                            "Бүртгэлтэй мэдээлэлтэй тохирлоо.\n"
                            f"- Овог, нэр: {employee['full_name']}\n"
                            f"- Бүтцийн нэгж: {employee['department']}\n"
                            "Асуудлын төрлөө сонгоно уу."
                        ),
                        reply_markup=ISSUE_KEYBOARD,
                    )
                    return ConversationState.CHOOSE_ISSUE

                await update.message.reply_text(
                    (
                        f"{employee['full_name']} нэртэй ажилтан байна.\n"
                        "Бүтцийн нэгжийг оруулна уу."
                    )
                )
                return ConversationState.ASK_DEPARTMENT

            await update.message.reply_text("Таны овог, нэрээ оруулна уу.")
            return ConversationState.ASK_NAME

        if attempts >= 3:
            await update.message.reply_text(
                "Алдаатай код 3 удаа орууллаа. Дахин оролдохын тулд /start командыг ашиглана уу.",
                reply_markup=ReplyKeyboardRemove(),
            )
            return ConversationHandler.END

        await update.message.reply_text(
            "Ажилтны код буруу байна. Дахин оруулна уу.",
            reply_markup=ReplyKeyboardRemove(),
        )
        return ConversationState.ASK_EMPLOYEE_CODE

    async def receive_name(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> ConversationState:
        full_name = update.message.text.strip()
        context.user_data["full_name"] = full_name
        await update.message.reply_text(
            "Таны ажиллаж буй бүтцийн нэгжийг бичнэ үү (жишээ нь: Мэдээлэл технологийн тѳв)."
        )
        return ConversationState.ASK_DEPARTMENT

    async def receive_department(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> ConversationState:
        department = update.message.text.strip()
        context.user_data["department"] = department
        await update.message.reply_text(
            "Тулгарсан асуудлын төрлөө сонгоно уу.", reply_markup=ISSUE_KEYBOARD
        )
        return ConversationState.CHOOSE_ISSUE

    async def choose_issue(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> ConversationState:
        text = update.message.text.strip()
        category = ISSUE_BY_TITLE.get(text)
        if not category:
            await update.message.reply_text(
                "Жагсаалтаас сонголтоо хийнэ үү.", reply_markup=ISSUE_KEYBOARD
            )
            return ConversationState.CHOOSE_ISSUE

        context.user_data["issue_category"] = category
        user = update.effective_user
        call_id = self._database.create_call(
            telegram_user_id=user.id,
            full_name=context.user_data["full_name"],
            department=context.user_data["department"],
            issue_type=category.title,
            employee_code=context.user_data.get("employee_code"),
            basic_guidance=category.basic_guidance,
        )
        context.user_data["call_id"] = call_id

        await update.message.reply_text(category.basic_guidance, reply_markup=YES_NO_KEYBOARD)
        await update.message.reply_text(
            "Дээрх алхмууд таны асуудлыг шийдсэн үү?", reply_markup=YES_NO_KEYBOARD
        )
        return ConversationState.BASIC_FOLLOWUP

    async def handle_basic_followup(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> ConversationState | int:
        response = update.message.text.strip().lower()
        if response in YES_RESPONSES:
            self._database.mark_status(
                context.user_data["call_id"], "resolved_with_basic"
            )
            await update.message.reply_text(
                "Баярлалаа. Дуудлага амжилттай хаагдлаа.",
                reply_markup=ReplyKeyboardRemove(),
            )
            return ConversationHandler.END

        if response not in NO_RESPONSES:
            await update.message.reply_text(
                "Хариултаа 'Тийм' эсвэл 'Үгүй' гэж оруулна уу.",
                reply_markup=YES_NO_KEYBOARD,
            )
            return ConversationState.BASIC_FOLLOWUP

        await update.message.reply_text(
            "Тулгарсан асуудлаа дэлгэрэнгүй тайлбарлана уу.",
            reply_markup=ReplyKeyboardRemove(),
        )
        return ConversationState.REQUEST_DETAILS

    async def request_details(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> ConversationState:
        description = update.message.text.strip()
        call_id = context.user_data["call_id"]
        context.user_data["issue_description"] = description
        self._database.update_issue_description(call_id, description)
        self._database.mark_status(call_id, "awaiting_ai_guidance")
        await update.message.reply_text("Хиймэл оюун ухаанаас зөвлөгөө авч байна...")

        category: IssueCategory = context.user_data["issue_category"]
        try:
            guidance = await context.application.run_in_executor(
                None,
                self._ai.generate_guidance,
                category.title,
                description,
            )
        except Exception as exc:  # pragma: no cover - runtime safeguard
            logger.exception("AI guidance generation failed")
            self._database.mark_status(call_id, "ai_guidance_failed")
            await update.message.reply_text(
                "Хиймэл оюуны зөвлөгөө авахад алдаа гарлаа. Менежерт мэдэгдлээ.",
                reply_markup=ReplyKeyboardRemove(),
            )
            await self._notify_manager_ai_failure(context, call_id, exc)
            await self._escalate(update, context, call_id)
            return ConversationHandler.END
        self._database.update_ai_guidance(call_id, guidance)
        context.user_data["ai_guidance"] = guidance

        await update.message.reply_text(guidance, reply_markup=YES_NO_KEYBOARD)
        await update.message.reply_text(
            "Эдгээр алхам тань тус болсон уу?", reply_markup=YES_NO_KEYBOARD
        )
        return ConversationState.AI_FOLLOWUP

    async def handle_ai_followup(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> ConversationState | int:
        response = update.message.text.strip().lower()
        call_id = context.user_data["call_id"]
        if response in YES_RESPONSES:
            self._database.mark_status(call_id, "resolved_with_ai")
            await update.message.reply_text(
                "Сайн байна. Дуудлага хиймэл оюуны зөвлөгөөгөөр хаагдлаа.",
                reply_markup=ReplyKeyboardRemove(),
            )
            return ConversationHandler.END

        if response not in NO_RESPONSES:
            await update.message.reply_text(
                "Хариултаа 'Тийм' эсвэл 'Үгүй' гэж оруулна уу.",
                reply_markup=YES_NO_KEYBOARD,
            )
            return ConversationState.AI_FOLLOWUP

        await self._escalate(update, context, call_id)
        return ConversationHandler.END

    async def _escalate(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE, call_id: int
    ) -> None:
        engineers = self._config.engineers
        if not engineers:
            await update.message.reply_text(
                "Одоогоор инженерийн мэдээлэл бүртгэгдээгүй байна. Менежерт мэдэгдэнэ.",
                reply_markup=ReplyKeyboardRemove(),
            )
            self._database.mark_status(call_id, "awaiting_manager")
            category: IssueCategory = context.user_data["issue_category"]
            await context.bot.send_message(
                chat_id=self._config.manager_chat_id,
                text=(
                    "Инженерийн жагсаалт тохируулагдаагүй тул дуудлага автоматаар оноогдсонгүй.\n"
                    f"- Дуудлагын ID: {call_id}\n"
                    f"- Ажилтан: {context.user_data['full_name']}\n"
                    f"- Бүтцийн нэгж: {context.user_data['department']}\n"
                    f"- Ажилтны код: {context.user_data.get('employee_code', 'бүртгэгдээгүй')}\n"
                    f"- Асуудлын төрөл: {category.title}\n"
                    f"- Дэлгэрэнгүй: {context.user_data.get('issue_description', 'бүртгэгдээгүй')}"
                ),
            )
            return
        loads = self._database.engineer_loads([engineer.name for engineer in engineers])
        self._database.mark_status(call_id, "awaiting_manager")

        category: IssueCategory = context.user_data["issue_category"]
        summary_lines = [
            "Дуудлагыг инженерт оноох шаардлагатай байна.\n",
            f"- Дуудлагын ID: {call_id}\n",
            f"- Ажилтан: {context.user_data['full_name']}\n",
            f"- Бүтцийн нэгж: {context.user_data['department']}\n",
            f"- Ажилтны код: {context.user_data.get('employee_code', 'бүртгэгдээгүй')}\n",
            f"- Асуудлын төрөл: {category.title}\n",
            f"- Дэлгэрэнгүй: {context.user_data.get('issue_description', 'бүртгэгдээгүй')}\n",
        ]
        ai_guidance = context.user_data.get("ai_guidance")
        if ai_guidance:
            summary_lines.append("\n- AI зөвлөгөө:\n" + ai_guidance + "\n")

        summary_lines.append("\nБоломжит инженерүүд:\n")
        for engineer in engineers:
            summary_lines.append(
                f"- {engineer.name}: {loads.get(engineer.name, 0)} дуудлага өнөөдөр\n"
            )

        summary_lines.append(
            "\n10 минутын дотор /assign_call ДУУДЛАГЫН_ID ИНЖЕНЕР_НЭР командыг ашиглан инженер онооно уу."
            " Хэрэв оноохгүй бол систем хамгийн бага ачаалалтай инженерт автоматаар онооно."
        )

        await context.bot.send_message(
            chat_id=self._config.manager_chat_id,
            text="".join(summary_lines),
        )

        job_queue = context.application.job_queue if context.application else None
        if job_queue:
            job_queue.run_once(
                self._auto_assign_job,
                when=600,
                name=self._auto_assign_job_name(call_id),
                data={"call_id": call_id},
            )

        await update.message.reply_text(
            "Манай менежер дуудлагыг шалгаж, инженерт оноож байна. Удахгүй холбогдоно.",
            reply_markup=ReplyKeyboardRemove(),
        )

    async def _notify_manager_ai_failure(
        self,
        context: ContextTypes.DEFAULT_TYPE,
        call_id: int,
        exc: Exception,
    ) -> None:
        message_lines = [
            "AI зөвлөгөө авах үеэр алдаа гарлаа.\n",
            f"- Дуудлагын ID: {call_id}\n",
            f"- Ажилтны код: {context.user_data.get('employee_code', 'бүртгэгдээгүй')}\n",
            f"- Ажилтан: {context.user_data.get('full_name', 'тодорхойгүй')}\n",
            f"- Бүтцийн нэгж: {context.user_data.get('department', 'тодорхойгүй')}\n",
        ]
        details = str(exc)
        if details:
            message_lines.append(f"- Алдааны мэдээлэл: {details}\n")

        await context.bot.send_message(
            chat_id=self._config.manager_chat_id,
            text="".join(message_lines),
        )

    def _auto_assign_job_name(self, call_id: int) -> str:
        return f"auto_assign_{call_id}"

    def _find_engineer(self, name: str) -> Engineer | None:
        lookup = name.strip().lower()
        for engineer in self._config.engineers:
            if engineer.name.lower() == lookup:
                return engineer
        return None

    def _compose_assignment_summary(
        self,
        details: Dict[str, object],
        engineer: Engineer,
        loads: Dict[str, int],
    ) -> str:
        summary_lines = [
            "Шинэ дуудлага:\n",
            f"- Дуудлагын ID: {details['id']}\n",
            f"- Ажилтан: {details['user_full_name']}\n",
            f"- Бүтцийн нэгж: {details['department']}\n",
            f"- Ажилтны код: {details.get('employee_code') or 'бүртгэгдээгүй'}\n",
            f"- Асуудлын төрөл: {details['issue_type']}\n",
            f"- Дэлгэрэнгүй: {details.get('issue_description') or 'бүртгэгдээгүй'}\n",
            f"- Оноосон инженер: {engineer.name}\n",
            f"- Өнөөдрийн ачаалал: {loads.get(engineer.name, 0) + 1} дуудлага",
        ]
        ai_guidance = details.get("ai_guidance")
        if ai_guidance:
            summary_lines.append("\n- AI зөвлөгөө:\n" + str(ai_guidance))
        return "".join(summary_lines)

    async def _notify_engineer(
        self, context: CallbackContext, engineer: Engineer, summary: str
    ) -> None:
        try:
            await context.bot.send_message(
                chat_id=engineer.chat_id,
                text=(
                    f"Танд шинэ дуудлага оноолоо.\n{summary}\n"
                    "Дэлгэрэнгүйг системээс шалгана уу."
                ),
            )
        except Exception:  # pragma: no cover - engineer chat might be invalid
            pass

    async def _auto_assign_job(self, context: CallbackContext) -> None:
        job = context.job
        call_id = job.data.get("call_id") if job and job.data else None
        if call_id is None:
            return

        engineers = self._config.engineers
        if not engineers:
            return

        if self._database.is_call_assigned(call_id):
            return

        loads = self._database.engineer_loads([engineer.name for engineer in engineers])
        selected = min(engineers, key=lambda eng: loads.get(eng.name, 0))
        assigned = self._database.assign_engineer_if_unassigned(call_id, selected.name)
        if not assigned:
            return

        details = self._database.get_call_details(call_id)
        if not details:
            return

        summary = self._compose_assignment_summary(details, selected, loads)
        await context.bot.send_message(
            chat_id=self._config.manager_chat_id,
            text="10 минут өнгөрсөн тул дуудлагыг автоматаар оноолоо.\n\n" + summary,
        )
        await self._notify_engineer(context, selected, summary)

    # Reporting ----------------------------------------------------------
    async def report(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user_id = update.effective_user.id
        if user_id != self._config.manager_chat_id:
            await update.message.reply_text("Энэ коммандыг ашиглах эрхгүй байна.")
            return

        await update.message.reply_text(
            "Тайлан авах хугацаагаа сонгоно уу.", reply_markup=self._report_keyboard
        )

    async def handle_report_callback(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        query = update.callback_query
        await query.answer()

        if query.from_user.id != self._config.manager_chat_id:
            await query.edit_message_text("Энэ үйлдлийг зөвхөн менежер ашиглана.")
            return

        option = query.data.split(":", maxsplit=1)[-1]
        now = datetime.now()

        if option == "today":
            start = end = now
        elif option == "7d":
            start = now - timedelta(days=6)
            end = now
        elif option == "month":
            start = now.replace(day=1)
            end = now
        elif option == "prev_month":
            first_this_month = now.replace(day=1)
            end = first_this_month - timedelta(days=1)
            start = end.replace(day=1)
        elif option == "custom":
            context.user_data["awaiting_report_range"] = True
            await query.edit_message_text(
                (
                    "Хугацаагаа YYYY-MM-DD - YYYY-MM-DD форматтайгаар оруулна уу.\n"
                    "Жишээ: 2024-05-01 - 2024-05-31"
                ),
                reply_markup=ReplyKeyboardRemove(),
            )
            return
        else:
            await query.edit_message_text("Тодорхойгүй сонголт байна.")
            return

        await self._send_summary(query.message.chat_id, context, start, end)

    async def receive_report_range(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        if not context.user_data.get("awaiting_report_range"):
            return

        if update.effective_user.id != self._config.manager_chat_id:
            return

        text = update.message.text
        try:
            start, end = self._parse_date_range(text)
        except ValueError:
            await update.message.reply_text(
                "Огнооны форматыг YYYY-MM-DD - YYYY-MM-DD байдлаар оруулна уу.",
                reply_markup=ReplyKeyboardRemove(),
            )
            return

        context.user_data.pop("awaiting_report_range", None)
        await self._send_summary(update.effective_chat.id, context, start, end)

    def _parse_date_range(self, text: str) -> tuple[datetime, datetime]:
        cleaned = text.replace("–", "-")
        parts = [segment.strip() for segment in cleaned.split(" - ")]
        if len(parts) != 2:
            raise ValueError("invalid format")

        start = datetime.strptime(parts[0], "%Y-%m-%d")
        end = datetime.strptime(parts[1], "%Y-%m-%d")
        if start > end:
            raise ValueError("start after end")
        return start, end

    def _format_summary(
        self, summary: Dict[str, object], start: datetime, end: datetime
    ) -> str:
        lines = [
            f"Тайлангийн хугацаа: {start.date()} - {end.date()}",
            f"Нийт хүлээн авсан дуудлага: {summary['total']}",
        ]

        if summary["by_department"]:
            lines.append("\nБүтцийн нэгжээр:")
            for department, count in summary["by_department"]:
                lines.append(f"- {department}: {count}")

        if summary["by_issue"]:
            lines.append("\nАсуудлын төрлөөр:")
            for issue, count in summary["by_issue"]:
                lines.append(f"- {issue}: {count}")

        if summary["statuses"]:
            lines.append("\nСтатус:")
            for status, count in summary["statuses"]:
                lines.append(f"- {status}: {count}")

        return "\n".join(lines)

    async def _send_summary(
        self,
        chat_id: int,
        context: ContextTypes.DEFAULT_TYPE,
        start: datetime,
        end: datetime,
    ) -> None:
        summary = self._database.summary_between(start, end)
        await context.bot.send_message(
            chat_id=chat_id,
            text=self._format_summary(summary, start, end),
            reply_markup=self._report_keyboard,
        )

    async def add_employee(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        user_id = update.effective_user.id
        if user_id != self._config.manager_chat_id:
            await update.message.reply_text("Энэ коммандыг ашиглах эрхгүй байна.")
            return

        if not context.args or len(context.args) < 2:
            await update.message.reply_text(
                "Хэрэглээ: /add_employee АЖИЛТНЫ_КОД ОВОГ_НЭР; БҮТЦИЙН_НЭГЖ"
            )
            return

        code = context.args[0].strip()
        raw_details = " ".join(context.args[1:]).strip()
        if ";" in raw_details:
            full_name, _, department = raw_details.partition(";")
        else:
            full_name, department = raw_details, ""

        full_name = full_name.strip()
        department = department.strip()

        if not code or not full_name:
            await update.message.reply_text(
                "Код болон овог нэрийг зөв оруулна уу. Бүтцийн нэгжийг ';' тэмдэгтээр салгаж бичиж болно."
            )
            return

        created = self._database.add_employee(code, full_name, department)
        if created:
            await update.message.reply_text(
                f"{code} код бүхий {full_name} амжилттай нэмэгдлээ."
            )
        else:
            await update.message.reply_text(
                f"{code} кодын мэдээллийг {full_name} нэрээр шинэчиллээ."
            )

    async def assign_call(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user_id = update.effective_user.id
        if user_id != self._config.manager_chat_id:
            await update.message.reply_text("Энэ коммандыг ашиглах эрхгүй байна.")
            return

        if not context.args or len(context.args) < 2:
            await update.message.reply_text(
                "Хэрэглээ: /assign_call ДУУДЛАГЫН_ID ИНЖЕНЕР_НЭР"
            )
            return

        try:
            call_id = int(context.args[0])
        except ValueError:
            await update.message.reply_text("Дуудлагын ID бүхэл тоо байх ёстой.")
            return

        engineer_name = " ".join(context.args[1:]).strip()
        if not engineer_name:
            await update.message.reply_text("Инженерийн нэрийг зөв оруулна уу.")
            return

        engineer = self._find_engineer(engineer_name)
        if not engineer:
            available = ", ".join(eng.name for eng in self._config.engineers) or "тодорхойгүй"
            await update.message.reply_text(
                f"{engineer_name} нэртэй инженер тохируулагдаагүй байна. Боломжит нэрс: {available}"
            )
            return

        details = self._database.get_call_details(call_id)
        if not details:
            await update.message.reply_text(
                f"{call_id} дуудлага олдсонгүй."
            )
            return

        if details["status"] in {"resolved_with_basic", "resolved_with_ai"}:
            await update.message.reply_text(
                "Энэ дуудлага аль хэдийн хаагдсан байна."
            )
            return

        job_queue = context.application.job_queue if context.application else None
        if job_queue:
            for job in job_queue.get_jobs_by_name(self._auto_assign_job_name(call_id)):
                job.schedule_removal()

        loads = self._database.engineer_loads([eng.name for eng in self._config.engineers])
        self._database.assign_engineer(call_id, engineer.name)

        summary = self._compose_assignment_summary(details, engineer, loads)
        await update.message.reply_text(
            f"{call_id} дуудлагыг {engineer.name} инженерт оноолоо.\n\n" + summary
        )

        await self._notify_engineer(context, engineer, summary)

    async def cancel(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> ConversationState | int:
        await update.message.reply_text(
            "Яриа цуцлагдлаа. /start командыг ашиглан дахин эхлүүлж болно.",
            reply_markup=ReplyKeyboardRemove(),
        )
        return ConversationHandler.END


def build_application(config: BotConfig, database: Database, ai: AIAssistant) -> Application:
    handler = BotHandler(config, database, ai)

    conversation = ConversationHandler(
        entry_points=[CommandHandler("start", handler.start)],
        states={
            ConversationState.ASK_EMPLOYEE_CODE: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND, handler.receive_employee_code
                )
            ],
            ConversationState.ASK_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handler.receive_name)
            ],
            ConversationState.ASK_DEPARTMENT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handler.receive_department)
            ],
            ConversationState.CHOOSE_ISSUE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handler.choose_issue)
            ],
            ConversationState.BASIC_FOLLOWUP: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handler.handle_basic_followup)
            ],
            ConversationState.REQUEST_DETAILS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handler.request_details)
            ],
            ConversationState.AI_FOLLOWUP: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handler.handle_ai_followup)
            ],
        },
        fallbacks=[CommandHandler("cancel", handler.cancel)],
        allow_reentry=True,
    )

    application = Application.builder().token(config.telegram_token).build()
    application.add_handler(CallbackQueryHandler(handler.handle_report_callback, pattern=r"^report:"))
    application.add_handler(
        MessageHandler(
            filters.TEXT & filters.User(config.manager_chat_id),
            handler.receive_report_range,
        )
    )
    application.add_handler(conversation)
    application.add_handler(CommandHandler("report", handler.report))
    application.add_handler(CommandHandler("add_employee", handler.add_employee))
    application.add_handler(CommandHandler("assign_call", handler.assign_call))

    return application


