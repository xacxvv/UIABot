"""Telegram handlers for the UIABot."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum, auto
from typing import Dict, List

from telegram import ReplyKeyboardMarkup, ReplyKeyboardRemove, Update
from telegram.ext import (
    Application,
    CommandHandler,
    ConversationHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from .ai import AIAssistant
from .config import BotConfig
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

    # Conversation flow --------------------------------------------------
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> ConversationState:
        context.user_data.clear()
        if self._config.employee_codes:
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

        if code in self._config.employee_codes:
            context.user_data["employee_code"] = code
            context.user_data.pop("employee_code_attempts", None)
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
        selected = min(engineers, key=lambda eng: loads.get(eng.name, 0))
        self._database.assign_engineer(call_id, selected.name)

        category: IssueCategory = context.user_data["issue_category"]
        summary_lines = [
            "Шинэ дуудлага:\n",
            f"- Дуудлагын ID: {call_id}\n",
            f"- Ажилтан: {context.user_data['full_name']}\n",
            f"- Бүтцийн нэгж: {context.user_data['department']}\n",
            f"- Ажилтны код: {context.user_data.get('employee_code', 'бүртгэгдээгүй')}\n",
            f"- Асуудлын төрөл: {category.title}\n",
            f"- Дэлгэрэнгүй: {context.user_data.get('issue_description', 'бүртгэгдээгүй')}\n",
            f"- Оноосон инженер: {selected.name}\n",
            f"- Өнөөдрийн ачаалал: {loads.get(selected.name, 0) + 1} дуудлага",
        ]
        ai_guidance = context.user_data.get("ai_guidance")
        if ai_guidance:
            summary_lines.append("\n- AI зөвлөгөө:\n" + ai_guidance)
        summary = "".join(summary_lines)

        await context.bot.send_message(
            chat_id=self._config.manager_chat_id,
            text=summary,
        )
        try:
            await context.bot.send_message(
                chat_id=selected.chat_id,
                text=(
                    f"Танд шинэ дуудлага оноолоо.\n{summary}\n"
                    "Дэлгэрэнгүйг системээс шалгана уу."
                ),
            )
        except Exception:  # pragma: no cover - engineer chat might be invalid
            pass

        await update.message.reply_text(
            "Манай инженерүүд таныг удахгүй холбогдоно.",
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

    # Reporting ----------------------------------------------------------
    async def report(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user_id = update.effective_user.id
        if user_id != self._config.manager_chat_id:
            await update.message.reply_text("Энэ коммандыг ашиглах эрхгүй байна.")
            return

        summary = self._database.summary()
        lines = [f"Нийт хүлээн авсан дуудлага: {summary['total']}"]

        if summary["by_department"]:
            lines.append("\nБүтцийн нэгжээр:")
            for department, count in summary["by_department"]:
                lines.append(f"- {department}: {count}")

        if summary["by_issue"]:
            lines.append("\nАсуудлын төрлөөр:")
            for issue, count in summary["by_issue"]:
                lines.append(f"- {issue}: {count}")

        if summary["statuses"]:
            lines.append("\nТөлөв:")
            for status, count in summary["statuses"]:
                lines.append(f"- {status}: {count}")

        await update.message.reply_text("\n".join(lines))

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
    application.add_handler(conversation)
    application.add_handler(CommandHandler("report", handler.report))

    return application

