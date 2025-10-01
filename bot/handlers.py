"""Telegram handlers for the UIABot."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum, auto
from typing import Dict, List

from openai import OpenAIError
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
        await update.message.reply_text(
            "Сайн байна уу. Та өөрийн ажилтны кодоо оруулна уу.",
            reply_markup=ReplyKeyboardRemove(),
        )
        return ConversationState.ASK_EMPLOYEE_CODE

    async def receive_employee_code(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> ConversationState:
        code = update.message.text.strip().upper()
        employee = self._database.get_employee_by_code(code)
        if not employee:
            await update.message.reply_text(
                "Таны оруулсан ажилтны код бүртгэлгүй байна. Кодоо шалгаад дахин оруулна уу.",
                reply_markup=ReplyKeyboardRemove(),
            )
            return ConversationState.ASK_EMPLOYEE_CODE

        context.user_data["employee"] = employee
        context.user_data["employee_code"] = employee["code"]
        context.user_data["full_name"] = employee["full_name"]
        context.user_data["department"] = employee["department"]

        await update.message.reply_text(
            (
                f"Сайн байна уу, {employee['full_name']}!\n"
                f"Таны мэдээлэл: {employee['department']} - {employee['position']}\n"
                "Тулгарсан асуудлын төрлөө сонгоно уу."
            ),
            reply_markup=ISSUE_KEYBOARD,
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
            employee_code=context.user_data["employee_code"],
            telegram_user_id=user.id,
            full_name=context.user_data["full_name"],
            department=context.user_data["department"],
            issue_type=category.title,
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
        except OpenAIError:  # pragma: no cover - network failure
            logging.exception("Failed to obtain AI guidance from OpenAI")
            self._database.mark_status(call_id, "awaiting_manager")
            await update.message.reply_text(
                "Одоогоор хиймэл оюун ухааны зөвлөгөө өгөх боломжгүй байна. "
                "Манай менежерт мэдэгдэж, инженерүүдэд шууд шилжүүлж байна.",
                reply_markup=ReplyKeyboardRemove(),
            )
            await self._escalate(update, context, call_id)
            return ConversationHandler.END
        except Exception:  # pragma: no cover - defensive
            logging.exception("Unexpected error while obtaining AI guidance")
            self._database.mark_status(call_id, "awaiting_manager")
            await update.message.reply_text(
                "Одоогоор хиймэл оюун ухааны зөвлөгөө өгөх боломжгүй байна. "
                "Манай менежерт мэдэгдэж, инженерүүдэд шууд шилжүүлж байна.",
                reply_markup=ReplyKeyboardRemove(),
            )
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
        self._database.mark_status(call_id, "awaiting_manager")

        category: IssueCategory = context.user_data["issue_category"]
        employee = context.user_data["employee"]
        summary_lines = [
            "Шинэ дуудлага:\n",
            f"- Дуудлагын ID: {call_id}\n",
            f"- Ажилтан: {context.user_data['full_name']}\n",
            f"- Ажилтны код: {employee['code']}\n",
            f"- Бүтцийн нэгж: {context.user_data['department']}\n",
            f"- Албан тушаал: {employee['position']}\n",
            f"- Утас: {employee['phone']}\n",
            f"- Асудлын төрөл: {category.title}\n",
            f"- Дэлгэрэнгүй: {context.user_data.get('issue_description', 'бүртгэгдээгүй')}\n",
        ]
        ai_guidance = context.user_data.get("ai_guidance")
        if ai_guidance:
            summary_lines.append("\n- AI зөвлөгөө:\n" + ai_guidance)

        summary = "".join(summary_lines)
        engineers = self._config.engineers

        if engineers:
            loads = self._database.engineer_loads([engineer.name for engineer in engineers])
            load_lines = ["\nОдоогийн ачаалал:"]
            for engineer in engineers:
                load_lines.append(
                    f"- {engineer.name}: өнөөдөр {loads.get(engineer.name, 0)} дуудлага"
                )
            summary += "\n".join(load_lines)
            engineer_names = ", ".join(engineer.name for engineer in engineers)
            summary += (
                "\n\nИнженер оноохын тулд дараах командыг ашиглана уу:\n"
                f"/assign {call_id} <инженерийн нэр>\n"
                f"Боломжит инженерүүд: {engineer_names}"
            )
        else:
            summary += (
                "\n\nИнженерийн жагсаалт тохируулагдаагүй байна."
            )

        await context.bot.send_message(
            chat_id=self._config.manager_chat_id,
            text=summary,
        )

        await update.message.reply_text(
            "Таны мэдээллийг МТ-ийн төвийн даргад шилжүүллээ. Тэд удахгүй холбогдоно.",
            reply_markup=ReplyKeyboardRemove(),
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

        engineer_rows = {name: (total, resolved) for name, total, resolved in summary["by_engineer"]}
        if self._config.engineers:
            lines.append("\nИнженерүүдээр:")
            for engineer in self._config.engineers:
                total, resolved = engineer_rows.get(engineer.name, (0, 0))
                lines.append(
                    f"- {engineer.name}: нийт {total} дуудлага, шийдвэрлэсэн {resolved}"
                )

            extra_engineers = [
                name for name in engineer_rows.keys()
                if name not in {engineer.name for engineer in self._config.engineers}
            ]
            for name in extra_engineers:
                total, resolved = engineer_rows[name]
                lines.append(
                    f"- {name}: нийт {total} дуудлага, шийдвэрлэсэн {resolved}"
                )

        await update.message.reply_text("\n".join(lines))

    async def assign_call(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.effective_user.id != self._config.manager_chat_id:
            await update.message.reply_text("Энэ коммандыг ашиглах эрхгүй байна.")
            return

        if len(context.args) < 2:
            await update.message.reply_text(
                "Хэрэглээ: /assign <дуудлагын ID> <инженерийн нэр>")
            return

        try:
            call_id = int(context.args[0])
        except ValueError:
            await update.message.reply_text("Дуудлагын ID бүхэл тоо байх ёстой.")
            return

        engineer_name = " ".join(context.args[1:]).strip()
        if not engineer_name:
            await update.message.reply_text("Инженерийн нэрийг бүрэн оруулна уу.")
            return

        engineer = next(
            (eng for eng in self._config.engineers if eng.name.lower() == engineer_name.lower()),
            None,
        )
        if not engineer:
            available = ", ".join(eng.name for eng in self._config.engineers)
            if available:
                message = (
                    "Ийм нэртэй инженер байхгүй байна. Боломжит инженерүүд: "
                    + available
                )
            else:
                message = (
                    "Инженерийн жагсаалт тохируулагдаагүй байна. ENGINEERS тохиргоог шалгана уу."
                )
            await update.message.reply_text(message)
            return

        call = self._database.get_call(call_id)
        if not call:
            await update.message.reply_text("Ийм дуудлага олдсонгүй.")
            return

        previous_engineer = call.get("assigned_engineer")

        self._database.assign_engineer(call_id, engineer.name)
        loads = self._database.engineer_loads([engineer.name])
        current_load = loads.get(engineer.name, 0)

        employee_details = None
        employee_code = call.get("employee_code")
        if employee_code:
            employee_details = self._database.get_employee_by_code(employee_code)

        summary_lines = [
            f"Дуудлага #{call_id} - {call['user_full_name']} инженер {engineer.name}-д оноолоо.",
            f"Өнөөдрийн ачаалал: {current_load} дуудлага.",
        ]
        if previous_engineer and previous_engineer != engineer.name:
            summary_lines.append(f"Өмнөх оноолт: {previous_engineer}")
        await update.message.reply_text("\n".join(summary_lines))

        message_lines = [
            "Танд шинэ дуудлага оноолоо.\n",
            f"- Дуудлагын ID: {call_id}\n",
            f"- Ажилтан: {call['user_full_name']}\n",
            f"- Ажилтны код: {employee_code or 'тодорхойгүй'}\n",
            f"- Бүтцийн нэгж: {call['department']}\n",
            f"- Асуудлын төрөл: {call['issue_type']}\n",
        ]
        if employee_details:
            message_lines.append(f"- Албан тушаал: {employee_details['position']}\n")
            message_lines.append(f"- Утас: {employee_details['phone']}\n")
        description = call.get("issue_description") or "Дэлгэрэнгүй мэдээлэл ирээгүй"
        message_lines.append(f"- Дэлгэрэнгүй: {description}\n")
        if call.get("ai_guidance"):
            message_lines.append("\n- AI зөвлөгөө:\n" + call["ai_guidance"])

        engineer_message = "".join(message_lines)
        try:
            await context.bot.send_message(
                chat_id=engineer.chat_id,
                text=engineer_message,
            )
        except Exception:  # pragma: no cover - defensive guard
            pass

        try:
            await context.bot.send_message(
                chat_id=call["telegram_user_id"],
                text=(
                    "Таны дуудлагад {name} инженер ажиллахаар боллоо."
                ).format(name=engineer.name),
            )
        except Exception:  # pragma: no cover - defensive guard
            pass

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
    application.add_handler(CommandHandler("assign", handler.assign_call))

    return application

