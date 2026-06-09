import os
import re
import time

from google import genai
from presentation_generator import generate_presentation
from web_search import search_web

try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv():
        return None


load_dotenv()


def _get_streamlit_secret(name, default=""):
    try:
        import streamlit as st

        return st.secrets.get(name, default)
    except Exception:
        return default

MODEL_NAME = (
    _get_streamlit_secret("GEMINI_MODEL")
    or os.getenv("GEMINI_MODEL")
    or "gemini-2.5-flash"
)

API_KEY = (
    _get_streamlit_secret("GEMINI_API_KEY")
    or os.getenv("GEMINI_API_KEY")
    or ""
)

client = genai.Client(api_key=API_KEY) if API_KEY else None

GEMINI_QUOTA_MESSAGE = (
    "Лимит Gemini API временно исчерпан. "
    "Попробуйте позже или подключите другой API-ключ."
)

_quota_blocked_until = 0


def configure_gemini_api_key(api_key):
    global API_KEY
    global client
    global _quota_blocked_until

    cleaned_key = api_key.strip()

    if not cleaned_key:

        return

    API_KEY = cleaned_key
    _quota_blocked_until = 0
    client = genai.Client(api_key=API_KEY)


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


def _is_quota_error(error):
    error_text = str(error).lower()
    quota_markers = [
        "resource_exhausted",
        "quota",
        "rate limit",
        "429",
        "too many requests",
    ]

    return any(marker in error_text for marker in quota_markers)


def safe_generate_content(prompt):
    global _quota_blocked_until

    if not API_KEY or client is None:

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

        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=prompt
        )

        return response.text

    except Exception as error:

        if not _is_quota_error(error):

            return (
                "Произошла ошибка при обращении к Gemini API. "
                f"Попробуйте повторить запрос позже. Детали: {error}"
            )

        retry_delay = _extract_retry_delay(error)
        _quota_blocked_until = time.time() + (retry_delay or 60)
        message = GEMINI_QUOTA_MESSAGE

        if retry_delay:

            message += f" Попробуйте снова примерно через {retry_delay} секунд."

        return message


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
    "Web Search": """
You are Web Search Agent.
Use web search results to answer questions about current, recent, or time-sensitive information.
Mention uncertainty when sources are incomplete or conflicting.
""",
    "Presentation Generator": """
You are Presentation Generator.
Create clear PowerPoint slide structures with concise titles and 5-7 bullet points per slide.
Use uploaded document context when available.
""",
}

DEFAULT_AI_MODE = "General Assistant"
VALID_AI_MODES = set(SYSTEM_PROMPTS.keys())

AGENT_TO_MODE = {
    "Programming Agent": "Programming Tutor",
    "Report Agent": "Report Writer",
    "Document Agent": "Document Analyst",
    "Internship Agent": "Internship Assistant",
    "Web Search Agent": "Web Search",
    "Presentation Agent": "Presentation Generator",
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
- Web Search
- Presentation Generator
- General Assistant

Rules:
- Programming Tutor: code, debugging, programming concepts, algorithms, errors.
- Report Writer: reports, essays, structured writing, conclusions, recommendations.
- Document Analyst: requests to analyze, summarize, extract facts, compare document content.
- Internship Assistant: internship tasks, practice reports, workplace tasks, student practice.
- Web Search: latest news, recent facts, current versions, winners, prices, schedules, releases.
- Presentation Generator: PowerPoint, PPTX, slides, presentation creation.
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

    presentation_words = [
        "создай презентацию",
        "сделай презентацию",
        "подготовь презентацию",
        "сделай ppt",
        "ppt",
        "pptx",
        "слайды",
        "create presentation",
        "presentation",
        "slides",
    ]

    if needs_web_search(message):
        return "Web Search"

    if any(word in lowered_message for word in presentation_words):
        return "Presentation Generator"

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


def web_search_agent(prompt, context):
    search_result = search_web(
        prompt,
        5
    )

    search_available = (
        search_result.get("ok")
        or search_result.get("success")
    )

    if not search_available:

        return (
            search_result.get(
                "error",
                search_result.get(
                    "message",
                    "Web search is not configured yet."
                )
            ),
            []
        )

    sources = []
    web_context = ""

    for index, result in enumerate(search_result.get("results", []), start=1):
        title = result.get("title", f"Source {index}")
        url = result.get("url", "")
        snippet = result.get("snippet", "")
        content = result.get("content", snippet)

        sources.append(
            f"{title} - {url}"
        )

        web_context += (
            f"\n\nSOURCE {index}:\n"
            f"Title: {title}\n"
            f"URL: {url}\n"
            f"Snippet: {snippet}\n"
            f"Content:\n{content}\n"
        )

    system_prompt = """
You are Web Search Agent.
Answer in Russian using the web sources below.
Focus on current facts, dates, versions, winners, releases, and recent changes.
If sources do not contain enough evidence, say that clearly.
"""

    full_prompt = f"""
{system_prompt}

Conversation context:
{context}

Web sources:
{web_context}

User request:
{prompt}

Give a concise answer first, then key details. Do not invent facts.
"""

    answer = safe_generate_content(full_prompt)

    return answer, sources


def presentation_agent(prompt, context, document_text=""):
    source_text = document_text.strip() or prompt

    if not source_text.strip():

        return (
            "Не удалось создать презентацию: нет текста запроса или документа.",
            ""
        )

    outline_prompt = f"""
Create a PowerPoint presentation outline in Russian.

Rules:
- Return exactly 10 slide blocks.
- Use this format for each block:
SLIDE 1: Title
- bullet
- bullet
- bullet
- bullet
- bullet
- bullet
- bullet
- First slide must be a title slide.
- Last slide must be Thank You / Conclusion.
- Every content slide must have a short title and no more than 5-7 concise bullets.

Conversation context:
{context}

User request:
{prompt}

Source material:
{source_text[:30000]}
"""

    outline = safe_generate_content(outline_prompt)

    if (
        is_quota_message(outline)
        or outline.startswith("Произошла ошибка")
        or outline.startswith("Gemini API-ключ")
        or not outline.strip()
    ):

        return outline, ""

    try:

        file_path = generate_presentation(
            generate_chat_title(prompt),
            outline,
            10
        )

    except Exception as error:

        return (
            f"Не удалось создать презентацию. Детали: {error}",
            ""
        )

    return (
        "📊 Presentation created successfully",
        file_path
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


def needs_web_search(prompt):
    lowered_prompt = prompt.lower()

    current_words = [
        "последние",
        "последняя",
        "последний",
        "последнюю",
        "актуальн",
        "сейчас",
        "сегодня",
        "новости",
        "новые функции",
        "новая версия",
        "последняя версия",
        "кто выиграл",
        "кто победил",
        "результат",
        "цена",
        "курс",
        "расписание",
        "latest",
        "recent",
        "today",
        "news",
        "current",
        "new features",
        "release",
        "version",
        "winner",
        "won",
    ]

    current_topics = [
        "gemini",
        "streamlit",
        "python",
        "лига чемпионов",
        "champions league",
        "openai",
        "google",
        "render",
    ]

    if any(word in lowered_prompt for word in current_words):

        return True

    return (
        any(topic in lowered_prompt for topic in current_topics)
        and any(
            marker in lowered_prompt
            for marker in ["версия", "новост", "latest", "current", "release"]
        )
    )


def _agent_from_keywords(prompt, document_attached, allow_web_search=True):

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

    presentation_words = [
        "создай презентацию",
        "сделай презентацию",
        "подготовь презентацию",
        "презентацию по документу",
        "сделай ppt",
        "ppt",
        "pptx",
        "слайды",
        "сделай слайды",
        "create presentation",
        "presentation",
        "slides",
    ]

    if allow_web_search and needs_web_search(lowered_prompt):
        return "Web Search Agent"

    if any(word in lowered_prompt for word in presentation_words):
        return "Presentation Agent"

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
    manual_mode=DEFAULT_AI_MODE,
    auto_web_search=True,
    force_web_search=False
):

    if force_web_search or manual_mode == "Web Search":

        selected_agent = "Web Search Agent"

    elif manual_mode == "Presentation Generator":

        selected_agent = "Presentation Agent"

    elif auto_mode:

        if auto_web_search and needs_web_search(prompt):

            selected_agent = "Web Search Agent"

        else:

            selected_agent = _agent_from_keywords(
                prompt,
                document_attached,
                False
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

    elif selected_agent == "Web Search Agent":

        answer, web_sources = web_search_agent(
            prompt,
            context
        )

        return selected_agent, AGENT_TO_MODE[selected_agent], answer, web_sources, ""

    elif selected_agent == "Presentation Agent":

        answer, artifact_path = presentation_agent(
            prompt,
            context,
            document_text
        )

        return selected_agent, AGENT_TO_MODE[selected_agent], answer, [], artifact_path

    else:

        selected_agent = "General Agent"
        answer = general_agent(
            prompt,
            context
        )

    return selected_agent, AGENT_TO_MODE[selected_agent], answer, [], ""


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
