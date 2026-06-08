import os
import re
import time

import google.generativeai as genai
from google.api_core.exceptions import ResourceExhausted

try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv():
        return None


load_dotenv()

MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

API_KEY = (
    os.getenv("GEMINI_API_KEY")
    or os.getenv("GOOGLE_API_KEY")
    or ""
)

genai.configure(api_key=API_KEY)

model = genai.GenerativeModel(
    MODEL_NAME
)

GEMINI_QUOTA_MESSAGE = (
    "Лимит Gemini API временно исчерпан. "
    "Попробуйте позже или подключите другой API-ключ."
)

_quota_blocked_until = 0


def configure_gemini_api_key(api_key):
    global API_KEY
    global model
    global _quota_blocked_until

    cleaned_key = api_key.strip()

    if not cleaned_key:

        return

    API_KEY = cleaned_key
    _quota_blocked_until = 0
    genai.configure(api_key=API_KEY)
    model = genai.GenerativeModel(MODEL_NAME)


def _extract_retry_delay(error):

    retry_delay = getattr(error, "retry_delay", None)

    if retry_delay:

        seconds = getattr(retry_delay, "seconds", None)

        if seconds:

            return seconds

    details = getattr(error, "details", None)

    if details:

        for detail in details:

            retry_delay = getattr(detail, "retry_delay", None)

            if retry_delay:

                seconds = getattr(retry_delay, "seconds", None)

                if seconds:

                    return seconds

    return None


def safe_generate_content(prompt):
    global _quota_blocked_until

    if not API_KEY:

        return (
            "Gemini API-ключ не настроен. Добавьте ключ в переменную "
            "окружения GEMINI_API_KEY или GOOGLE_API_KEY."
        )

    now = time.time()

    if now < _quota_blocked_until:

        seconds_left = int(_quota_blocked_until - now)

        return (
            f"{GEMINI_QUOTA_MESSAGE} "
            f"Попробуйте снова примерно через {seconds_left} секунд."
        )

    try:

        response = model.generate_content(prompt)

        return response.text

    except ResourceExhausted as error:

        retry_delay = _extract_retry_delay(error)
        _quota_blocked_until = time.time() + (retry_delay or 60)
        message = GEMINI_QUOTA_MESSAGE

        if retry_delay:

            message += f" Попробуйте снова примерно через {retry_delay} секунд."

        return message

    except Exception as error:

        return (
            "Произошла ошибка при обращении к Gemini API. "
            f"Попробуйте повторить запрос позже. Детали: {error}"
        )


def is_quota_message(text):

    return text.startswith(GEMINI_QUOTA_MESSAGE)

SYSTEM_PROMPTS = {
    "General Assistant": """
You are a helpful AI assistant for students.
Answer clearly, practically, and step by step.
Help with learning, planning, writing, and everyday study tasks.
""",
    "Programming Tutor": """
You are a programming tutor.
Explain code in simple language, show examples, and help the student understand the logic.
When useful, provide corrected code and explain why it works.
""",
    "Report Writer": """
You are a report writing assistant.
Help create structured academic and internship reports with introduction, main sections, analysis, conclusion, and recommendations.
Use clear formal language.
""",
    "Document Analyst": """
You are a document analyst.
Extract key ideas, facts, risks, conclusions, and action items from provided documents.
Base answers on the document when document text is available.
""",
    "Internship Assistant": """
You are an internship assistant for students.
Help with internship tasks, daily reports, project explanations, workplace communication, and practical learning goals.
Give concrete next steps.
""",
}

DEFAULT_AI_MODE = "General Assistant"
VALID_AI_MODES = set(SYSTEM_PROMPTS.keys())

AGENT_TO_MODE = {
    "Programming Agent": "Programming Tutor",
    "Report Agent": "Report Writer",
    "Document Agent": "Document Analyst",
    "Internship Agent": "Internship Assistant",
    "General Agent": "General Assistant",
}

MODE_TO_AGENT = {
    mode: agent
    for agent, mode in AGENT_TO_MODE.items()
}


def get_system_prompt(ai_mode=DEFAULT_AI_MODE):

    return SYSTEM_PROMPTS.get(
        ai_mode,
        SYSTEM_PROMPTS[DEFAULT_AI_MODE]
    )


def ask_gemini(question, context="", ai_mode=DEFAULT_AI_MODE):

    prompt = f"""
{get_system_prompt(ai_mode)}

Conversation history:
{context}

Current user question:
{question}
"""

    return safe_generate_content(prompt)

def ask_document(question, document_text, ai_mode=DEFAULT_AI_MODE):

    prompt = f"""
{get_system_prompt(ai_mode)}

Use ONLY the document below.

DOCUMENT:
{document_text}

QUESTION:
{question}
"""

    return safe_generate_content(prompt)


def generate_chat_title(first_message):
    cleaned = " ".join(first_message.strip().split())
    cleaned = cleaned.strip("\"'«»“”")
    cleaned = cleaned.rstrip(".")

    if not cleaned:

        return "New chat"

    words = cleaned.split()
    title = " ".join(words[:4])

    return title[:30]


def extract_user_memories(message):
    memories = []
    normalized_message = " ".join(message.strip().split())

    patterns = [
        (
            5,
            r"(?:меня зовут|мо[её] имя|я\s+)([А-ЯA-ZЁ][а-яa-zё-]{1,30})\b",
            "Имя пользователя: {value}",
        ),
        (
            4,
            r"(?:я учусь в|учусь в|обучаюсь в)\s+([^,.!?]{3,80})",
            "Учебное заведение пользователя: {value}",
        ),
        (
            4,
            r"(?:мой проект|делаю проект|работаю над проектом)\s+([^,.!?]{3,100})",
            "Проект пользователя: {value}",
        ),
        (
            3,
            r"(?:использую|работаю с|пишу на|технологии:?)\s+([^,.!?]{3,100})",
            "Технологии пользователя: {value}",
        ),
        (
            3,
            r"(?:мне нравится|я предпочитаю|предпочитаю)\s+([^,.!?]{3,100})",
            "Предпочтение пользователя: {value}",
        ),
    ]

    for importance, pattern, template in patterns:

        match = re.search(
            pattern,
            normalized_message,
            flags=re.IGNORECASE,
        )

        if not match:

            continue

        value = match.group(1).strip(" .,!?:;")

        if value:

            memories.append(
                (
                    template.format(value=value),
                    importance
                )
            )

    return memories



def detect_task_type(message, document_attached):

    rule_based_agent = _rule_based_agent(
        message,
        document_attached
    )

    if rule_based_agent:

        return AGENT_TO_MODE[rule_based_agent]

    prompt = f"""
Classify the user's message into exactly one AI assistant mode.

Available modes:
- Programming Tutor
- Report Writer
- Document Analyst
- Internship Assistant
- General Assistant

Rules:
- Programming Tutor: code, debugging, programming concepts, algorithms, errors.
- Report Writer: reports, essays, structured writing, conclusions, recommendations.
- Document Analyst: requests to analyze, summarize, extract facts, compare document content.
- Internship Assistant: internship tasks, practice reports, workplace tasks, student practice.
- General Assistant: anything else.
- If a document is attached and the user asks about file content, prefer Document Analyst.

Return only the mode name.

Document attached:
{document_attached}

User message:
{message}
"""

    try:

        detected_mode = safe_generate_content(prompt).strip()

        if is_quota_message(detected_mode):

            return DEFAULT_AI_MODE
        detected_mode = detected_mode.strip("\"'«»“”")
        detected_mode = detected_mode.rstrip(".")

        for mode in VALID_AI_MODES:

            if mode.lower() == detected_mode.lower():

                return mode

    except Exception:

        pass

    lowered_message = message.lower()

    programming_words = [
        "python",
        "код",
        "ошибка",
        "debug",
        "function",
        "class",
        "api",
        "sql",
        "streamlit",
        "sqlite",
        "c++",
        "traceback",
    ]

    report_words = [
        "отчёт",
        "отчет",
        "report",
        "эссе",
        "заключение",
        "рекомендации",
        "введение",
        "формулиров",
    ]

    document_words = [
        "документ",
        "файл",
        "pdf",
        "анализ",
        "проанализируй",
        "из документа",
        "в документе",
        "summary",
        "резюме документа",
    ]

    internship_words = [
        "практика",
        "стажировка",
        "internship",
        "дневник",
        "производственная",
        "flowise",
        "langflow",
        "n8n",
        "zapier",
        "make.com",
        "gemini",
        "rag",
    ]

    if (
        document_attached
        and any(word in lowered_message for word in document_words)
    ):
        return "Document Analyst"

    if any(word in lowered_message for word in programming_words):
        return "Programming Tutor"

    if any(word in lowered_message for word in report_words):
        return "Report Writer"

    if any(word in lowered_message for word in document_words):
        return "Document Analyst"

    if any(word in lowered_message for word in internship_words):
        return "Internship Assistant"

    return DEFAULT_AI_MODE


def _generate_agent_response(system_prompt, prompt, context="", document_text=""):

    full_prompt = f"""
{system_prompt}

Conversation context:
{context}

Document text, if provided:
{document_text}

User request:
{prompt}

Answer in Russian. Be clear, structured, and practical.
"""

    return safe_generate_content(full_prompt)


def programming_agent(prompt, context):

    system_prompt = """
You are Programming Agent.
Specialize in code, debugging, Python, SQL, C++, Streamlit, SQLite, APIs, and software architecture.
Explain the cause of problems, provide corrected code when useful, and give step-by-step reasoning.
"""

    return _generate_agent_response(
        system_prompt,
        prompt,
        context
    )


def report_agent(prompt, context):

    system_prompt = """
You are Report Agent.
Specialize in reports, introductions, conclusions, academic wording, structure, summaries, and recommendations.
Write in a clear formal style and produce well-organized sections.
"""

    return _generate_agent_response(
        system_prompt,
        prompt,
        context
    )


def document_agent(prompt, document_text, context):

    system_prompt = """
You are Document Agent.
Specialize in analyzing uploaded documents, extracting facts, summarizing content, identifying risks, and answering from document context.
If the document does not contain enough information, say what is missing.
"""

    return _generate_agent_response(
        system_prompt,
        prompt,
        context,
        document_text
    )


def internship_agent(prompt, context):

    system_prompt = """
You are Internship Agent.
Specialize in internship work, student practice, Flowise, Langflow, n8n, Zapier, Make.com, Gemini, RAG, AI workflows, and practical project tasks.
Give concrete steps, examples, and implementation guidance.
"""

    return _generate_agent_response(
        system_prompt,
        prompt,
        context
    )


def general_agent(prompt, context):

    system_prompt = """
You are General Agent.
Handle general student questions, planning, explanations, and everyday assistant tasks.
Keep answers helpful, concise, and easy to follow.
"""

    return _generate_agent_response(
        system_prompt,
        prompt,
        context
    )


def _agent_from_keywords(prompt, document_attached):

    lowered_prompt = prompt.lower()

    document_words = [
        "документ",
        "файл",
        "pdf",
        "docx",
        "проанализируй",
        "анализ документа",
        "из документа",
        "в документе",
        "summarize",
        "summary",
    ]

    programming_words = [
        "код",
        "ошибка",
        "python",
        "code",
        "error",
        "bug",
        "sql",
        "c++",
        "streamlit",
        "sqlite",
        "debug",
        "api",
        "function",
        "class",
        "traceback",
    ]

    report_words = [
        "отчёт",
        "отчет",
        "введение",
        "заключение",
        "practice",
        "introduction",
        "conclusion",
        "формулиров",
        "эссе",
        "структура отчета",
        "структура отчёта",
        "report",
        "recommendations",
    ]

    internship_words = [
        "flowise",
        "langflow",
        "n8n",
        "zapier",
        "make.com",
        "gemini",
        "rag",
        "практика",
        "стажировка",
        "internship",
        "автоматизация",
    ]

    if document_attached:
        return "Document Agent"

    if any(word in lowered_prompt for word in programming_words):
        return "Programming Agent"

    if any(word in lowered_prompt for word in report_words):
        return "Report Agent"

    if any(word in lowered_prompt for word in internship_words):
        return "Internship Agent"

    return "General Agent"


def _rule_based_agent(prompt, document_attached):

    selected_agent = _agent_from_keywords(
        prompt,
        document_attached
    )

    if selected_agent != "General Agent":

        return selected_agent

    return None


def router_agent(
    prompt,
    document_attached,
    auto_mode=True,
    context="",
    document_text="",
    manual_mode=DEFAULT_AI_MODE
):

    if auto_mode:

        selected_agent = _agent_from_keywords(
            prompt,
            document_attached
        )

    else:

        selected_agent = MODE_TO_AGENT.get(
            manual_mode,
            "General Agent"
        )

    if selected_agent == "Programming Agent":

        answer = programming_agent(
            prompt,
            context
        )

    elif selected_agent == "Report Agent":

        answer = report_agent(
            prompt,
            context
        )

    elif selected_agent == "Document Agent":

        answer = document_agent(
            prompt,
            document_text,
            context
        )

    elif selected_agent == "Internship Agent":

        answer = internship_agent(
            prompt,
            context
        )

    else:

        selected_agent = "General Agent"
        answer = general_agent(
            prompt,
            context
        )

    return selected_agent, AGENT_TO_MODE[selected_agent], answer


def run_task(
    task_name,
    user_request,
    document_text="",
    ai_mode=DEFAULT_AI_MODE
):

    task_instructions = {
        "PDF analysis": """
Analyze the PDF content. Include:
- short summary
- main ideas
- important facts, dates, names, numbers
- problems or risks
- conclusions
- suggested questions for deeper analysis
""",
        "Report creation": """
Create a report. Include:
- title
- introduction
- main sections
- analysis
- conclusion
- recommendations
- list of sources or data used, if available
""",
        "Resume generation": """
Create a professional resume/CV. Include:
- full name placeholder if missing
- target position
- profile summary
- skills
- work or internship experience
- education
- projects
- languages
- recommendations for improving the resume
""",
        "Project plan creation": """
Create a project plan. Include:
- project goal
- scope
- deliverables
- stages and timeline
- roles and responsibilities
- tools and resources
- risks
- success criteria
- next steps
""",
    }

    prompt = f"""
{get_system_prompt(ai_mode)}

Task type:
{task_name}

Task instructions:
{task_instructions.get(task_name, "Answer the request clearly.")}

User request:
{user_request}

Document text, if provided:
{document_text}

Return a clear, structured answer in Russian.
Use headings, bullet points, and practical next steps.
If information is missing, mention what should be added.
"""

    return safe_generate_content(prompt)
