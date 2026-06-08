import hashlib
import re

import streamlit as st

from file_reader import read_file
from gemini_client import (
    extract_user_memories,
    generate_chat_title,
    router_agent,
)
from database import (
    delete_chat,
    delete_document,
    delete_document_version,
    delete_document_with_versions,
    get_document_versions,
    get_chat_context,
    get_chat_list,
    get_chat_title,
    load_chat,
    load_chat_documents,
    load_latest_document_version,
    load_specific_document_version,
    load_memories,
    save_document_version,
    save_memory,
    save_message,
    search_relevant_chunks,
    search_relevant_memories,
    update_memory,
    delete_memory,
)


st.set_page_config(
    page_title="Student Practice AI Assistant",
    page_icon="🤖",
    layout="wide",
)

st.markdown(
    """
    <style>
    .block-container {
        max-width: 920px;
        padding-top: 4.2rem;
        padding-bottom: 9.5rem;
    }

    [data-testid="stAppViewContainer"] {
        padding-top: 0;
    }

    [data-testid="stAppViewContainer"] .main {
        padding-top: 0;
    }

    [data-testid="stSidebar"] {
        min-width: 280px;
    }

    [data-testid="stSidebar"] h1 {
        font-size: 1.15rem;
    }

    div[data-testid="stChatMessage"] {
        padding: 0.8rem 0;
    }

    div[data-testid="stFileUploader"] section {
        padding: 0.45rem;
    }

    div[data-testid="stFileUploader"] small {
        display: none;
    }

    div[data-testid="stTextInput"] input {
        min-height: 46px;
        border-radius: 18px;
        padding-left: 1rem;
        padding-right: 1rem;
    }

    div.stButton > button {
        width: 100%;
        border-radius: 999px;
        height: 42px;
    }

    .chat-header {
        text-align: center;
        padding: 0.25rem 0 1rem;
        margin-top: 0;
    }

    .chat-title {
        font-size: 1.45rem;
        font-weight: 650;
    }

    .chat-subtitle {
        color: #666;
        font-size: 0.92rem;
        margin-top: 0.2rem;
    }

    .composer-status {
        color: #666;
        font-size: 0.9rem;
        margin: 0.35rem 0 0.2rem;
    }

    .st-key-bottom_composer {
        position: fixed;
        width: min(920px, calc(100vw - 340px));
        left: calc(300px + (100vw - 300px - min(920px, calc(100vw - 340px))) / 2);
        right: auto;
        bottom: 0;
        z-index: 1000;
        background: var(--background-color);
        backdrop-filter: blur(12px);
        border-top: 1px solid rgba(128, 128, 128, 0.22);
        padding: 0.35rem 0 0.55rem;
    }

    .st-key-bottom_composer hr {
        margin: 0 0 0.45rem;
    }

    .st-key-bottom_composer [data-testid="stVerticalBlock"] {
        gap: 0.25rem;
    }

    .st-key-bottom_composer [data-testid="column"] {
        display: flex;
        align-items: flex-end;
    }

    .st-key-bottom_composer div.stButton > button {
        height: 46px;
        min-width: 46px;
        padding: 0;
        font-size: 1.1rem;
    }

    @media (max-width: 900px) {
        .block-container {
            padding-top: 3.5rem;
            padding-bottom: 11rem;
        }

        .st-key-bottom_composer {
            left: 0.75rem;
            right: 0.75rem;
            width: auto;
        }
    }
    </style>
    """,
    unsafe_allow_html=True,
)


AI_MODES = [
    "General Assistant",
    "Programming Tutor",
    "Report Writer",
    "Document Analyst",
    "Internship Assistant",
]

MODE_SELECTION_TYPES = [
    "Auto",
    "Manual",
]

TASK_MODES = [
    "Обычный чат",
    "Анализ PDF",
    "Создание отчёта",
    "Генерация резюме",
    "План проекта",
    "📚 Analyze All Documents",
]

MODE_HINTS = {
    "Обычный чат": "Напишите сообщение...",
    "Анализ PDF": "Задайте вопрос по документу...",
    "Создание отчёта": "Опишите тему отчёта...",
    "Генерация резюме": "Опишите опыт, навыки и должность...",
    "План проекта": "Опишите цель проекта...",
    "📚 Analyze All Documents": "Задайте вопрос по всем документам...",
}


def build_all_documents_text(documents):

    combined_text = ""

    for document_id, file_name, file_content, uploaded_at, version_number in documents:

        combined_text += (
            f"\n\n--- DOCUMENT: {file_name} v{version_number} ---\n"
            f"{file_content}"
        )

    return combined_text


def select_document_for_prompt(prompt, documents):

    if not documents:

        return "", ""

    lowered_prompt = prompt.lower()

    for document_id, file_name, file_content, uploaded_at, version_number in documents:

        if file_name.lower() in lowered_prompt:

            return file_name, file_content

    prompt_words = set(lowered_prompt.split())
    best_document = documents[0]
    best_score = -1

    for document in documents:

        document_id, file_name, file_content, uploaded_at, version_number = document
        document_words = set(
            (file_name + " " + file_content[:3000]).lower().split()
        )
        score = len(prompt_words.intersection(document_words))

        if score > best_score:

            best_document = document
            best_score = score

    return best_document[1], best_document[2]


def build_document_text_for_prompt(prompt, documents, chat_id):

    if not documents:

        return "", ""

    lowered_prompt = prompt.lower()
    version_matches = re.findall(r"\bv(\d+)\b", lowered_prompt)

    for document_id, file_name, file_content, uploaded_at, version_number in documents:

        if file_name.lower() not in lowered_prompt:

            continue

        if len(version_matches) >= 2:

            first_version = int(version_matches[0])
            second_version = int(version_matches[1])
            first = load_specific_document_version(
                chat_id,
                file_name,
                first_version
            )
            second = load_specific_document_version(
                chat_id,
                file_name,
                second_version
            )

            if first and second:

                return (
                    f"{file_name} v{first_version} vs v{second_version}",
                    (
                        f"OLD VERSION ({file_name} v{first_version}):\n"
                        f"{first[1]}\n\n"
                        f"NEW VERSION ({file_name} v{second_version}):\n"
                        f"{second[1]}\n\n"
                        "Compare these versions. Explain what was added, "
                        "removed, changed, and give a short conclusion."
                    )
                )

        if len(version_matches) == 1:

            requested_version = int(version_matches[0])
            selected_version = load_specific_document_version(
                chat_id,
                file_name,
                requested_version
            )

            if selected_version:

                return (
                    f"{file_name} v{requested_version}",
                    selected_version[1]
                )

        latest_version = load_latest_document_version(
            chat_id,
            file_name
        )

        if latest_version:

            return (
                f"{file_name} v{latest_version[0]}",
                latest_version[1]
            )

    return select_document_for_prompt(
        prompt,
        documents
    )


def find_document_scope(prompt, documents, chat_id, analyze_all=False):

    if analyze_all or not documents:

        return None, None

    lowered_prompt = prompt.lower()
    version_matches = re.findall(r"\bv(\d+)\b", lowered_prompt)

    for document_id, file_name, file_content, uploaded_at, version_number in documents:

        if file_name.lower() not in lowered_prompt:

            continue

        if version_matches:

            selected_version = load_specific_document_version(
                chat_id,
                file_name,
                int(version_matches[0])
            )

            if selected_version:

                versions = get_document_versions(
                    chat_id,
                    file_name
                )

                for version_id, current_version, current_content, current_uploaded_at in versions:

                    if current_version == int(version_matches[0]):

                        return document_id, version_id

        versions = get_document_versions(
            chat_id,
            file_name
        )

        if versions:

            latest_version = versions[-1]
            return document_id, latest_version[0]

        return document_id, None

    selected_name, selected_text = select_document_for_prompt(
        prompt,
        documents
    )

    for document_id, file_name, file_content, uploaded_at, version_number in documents:

        if file_name == selected_name:

            versions = get_document_versions(
                chat_id,
                file_name
            )

            if versions:

                latest_version = versions[-1]
                return document_id, latest_version[0]

            return document_id, None

    return None, None


def find_compare_version_scope(prompt, documents, chat_id):

    lowered_prompt = prompt.lower()
    version_matches = re.findall(r"\bv(\d+)\b", lowered_prompt)

    if len(version_matches) < 2:

        return None, []

    for document_id, file_name, file_content, uploaded_at, version_number in documents:

        if file_name.lower() not in lowered_prompt:

            continue

        version_ids = []
        versions = get_document_versions(
            chat_id,
            file_name
        )

        requested_versions = [
            int(version_matches[0]),
            int(version_matches[1])
        ]

        for version_id, current_version, current_content, current_uploaded_at in versions:

            if current_version in requested_versions:

                version_ids.append(version_id)

        return document_id, version_ids

    return None, []


def build_rag_context(chunks):

    document_text = ""
    sources = []

    for source_index, chunk in enumerate(chunks, start=1):

        (
            chunk_id,
            document_id,
            version_id,
            chunk_index,
            chunk_text,
            file_name,
            version_number
        ) = chunk

        document_text += (
            f"\n\nSOURCE {source_index}:\n"
            f"Document: {file_name}\n"
            f"Version: v{version_number}\n"
            f"Chunk: {chunk_index}\n"
            f"Text:\n{chunk_text}\n"
        )

        sources.append(
            f"{file_name} v{version_number}, chunk {chunk_index}"
        )

    return document_text, sources


if "current_chat" not in st.session_state:

    chats = get_chat_list()

    if chats:
        st.session_state.current_chat = chats[0]
    else:
        st.session_state.current_chat = 1

if "ai_mode" not in st.session_state:

    st.session_state.ai_mode = "General Assistant"

if "mode_selection_type" not in st.session_state:

    st.session_state.mode_selection_type = "Auto"

if "task_mode" not in st.session_state:

    st.session_state.task_mode = "Обычный чат"

if "message_nonce" not in st.session_state:

    st.session_state.message_nonce = 0

if "chat_settings_open" not in st.session_state:

    st.session_state.chat_settings_open = {}


# ---------------------
# Sidebar: chats only
# ---------------------

st.sidebar.title("Chats")

page = st.sidebar.radio(
    "Navigation",
    [
        "💬 Chats",
        "🧠 Memory",
    ],
    label_visibility="collapsed",
)

search_text = st.sidebar.text_input(
    "🔍 Search chats"
)

if st.sidebar.button(
    "➕ New Chat"
):

    chats = get_chat_list()

    if chats:
        st.session_state.current_chat = max(chats) + 1
    else:
        st.session_state.current_chat = 1

    st.rerun()

if st.sidebar.button(
    "🗑 Delete Current Chat"
):

    delete_chat(
        st.session_state.current_chat
    )

    delete_document(
        st.session_state.current_chat
    )

    chats = get_chat_list()

    if chats:
        st.session_state.current_chat = chats[0]
    else:
        st.session_state.current_chat = 1

    st.rerun()

st.sidebar.markdown("---")

chat_list = get_chat_list()

if st.session_state.current_chat not in chat_list:

    chat_list.insert(0, st.session_state.current_chat)

for chat_id in chat_list:

    title = get_chat_title(chat_id)
    chat_documents = load_chat_documents(chat_id)
    chat_document_name = "Документы не загружены"

    if chat_documents:

        chat_document_name = f"{len(chat_documents)} document(s)"

    if (
        search_text
        and search_text.lower()
        not in title.lower()
    ):
        continue

    if st.sidebar.button(
        f"💬 {title}",
        key=f"chat_{chat_id}"
    ):

        st.session_state.current_chat = chat_id

        st.rerun()

    st.sidebar.caption(f"📄 {chat_document_name}")


# ---------------------
# Current document
# ---------------------

chat_documents = load_chat_documents(
    st.session_state.current_chat
)

document_file_name = ""
document_text = ""

if chat_documents:

    document_file_name = chat_documents[0][1]
    document_text = chat_documents[0][2]

if page == "🧠 Memory":

    st.markdown(
        """
        <div class="chat-header">
            <div class="chat-title">🧠 Memory</div>
            <div class="chat-subtitle">Long-term user memory</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    memories = load_memories()

    if not memories:

        st.info("Память пока пуста.")

    for memory_id, memory_text, importance, created_at, updated_at in memories:

        with st.expander(
            f"Memory #{memory_id} · importance {importance}",
            expanded=False
        ):

            new_memory_text = st.text_area(
                "Memory text",
                value=memory_text,
                key=f"memory_text_{memory_id}",
            )

            new_importance = st.slider(
                "Importance",
                min_value=1,
                max_value=5,
                value=importance,
                key=f"memory_importance_{memory_id}",
            )

            st.caption(
                f"Created: {created_at} · Updated: {updated_at}"
            )

            edit_col, delete_col = st.columns(
                [1, 1]
            )

            with edit_col:

                if st.button(
                    "Save",
                    key=f"save_memory_{memory_id}"
                ):

                    update_memory(
                        memory_id,
                        new_memory_text,
                        new_importance
                    )

                    st.rerun()

            with delete_col:

                if st.button(
                    "Delete",
                    key=f"delete_memory_{memory_id}"
                ):

                    delete_memory(memory_id)
                    st.rerun()

    st.stop()


# ---------------------
# Main chat area
# ---------------------

current_title = get_chat_title(
    st.session_state.current_chat
)

st.markdown(
    f"""
    <div class="chat-header">
        <div class="chat-title">{current_title}</div>
        <div class="chat-subtitle">
            {st.session_state.mode_selection_type} mode · Current agent: {st.session_state.ai_mode}
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

messages = load_chat(
    st.session_state.current_chat
)

st.markdown("### 📁 Documents")

if not chat_documents:

    st.caption("Документы не загружены")

for document_id, file_name, file_content, uploaded_at, version_number in chat_documents:

    with st.expander(
        f"📄 {file_name}",
        expanded=False
    ):

        versions = get_document_versions(
            st.session_state.current_chat,
            file_name
        )

        st.caption(f"{len(versions)} version(s)")

        for version_id, current_version, current_content, current_uploaded_at in versions:

            st.markdown(f"**v{current_version}** — {current_uploaded_at}")

            st.text_area(
                "Document content",
                value=current_content[:10000],
                height=180,
                key=f"document_preview_{document_id}_{current_version}",
                disabled=True,
            )

            if st.button(
                "Delete version",
                key=f"delete_document_version_{document_id}_{current_version}"
            ):

                delete_document_version(
                    st.session_state.current_chat,
                    file_name,
                    current_version
                )

                st.rerun()

            st.markdown("---")

        if st.button(
            "Delete document with all versions",
            key=f"delete_document_{document_id}"
        ):

            delete_document_with_versions(
                st.session_state.current_chat,
                file_name
            )

            st.rerun()

for role, message in messages:

    with st.chat_message(role):

        st.markdown(message)


# ---------------------
# Bottom composer
# ---------------------

with st.container(key="bottom_composer"):

    st.markdown("---")

    settings_key = str(st.session_state.current_chat)

    if settings_key not in st.session_state.chat_settings_open:

        st.session_state.chat_settings_open[settings_key] = len(messages) == 0

    settings_button_label = "⚙ Настройки чата"

    if not st.session_state.chat_settings_open[settings_key]:

        settings_button_label = "⚙ Настройки чата"

    if st.button(
        settings_button_label,
        key=f"settings_toggle_{st.session_state.current_chat}"
    ):

        st.session_state.chat_settings_open[settings_key] = (
            not st.session_state.chat_settings_open[settings_key]
        )

        st.rerun()

    uploaded_file = None

    if st.session_state.chat_settings_open[settings_key]:

        with st.container():

            control_col_1, control_col_2, control_col_3, control_col_4 = st.columns(
                [1.25, 0.9, 1.15, 1.15]
            )

            with control_col_1:

                uploaded_file = st.file_uploader(
                    "📎 Загрузить файл",
                    type=["pdf", "docx", "txt"],
                    key=f"document_upload_{st.session_state.current_chat}",
                )

            with control_col_2:

                st.session_state.mode_selection_type = st.selectbox(
                    "Выбор режима",
                    MODE_SELECTION_TYPES,
                    index=MODE_SELECTION_TYPES.index(
                        st.session_state.mode_selection_type
                    ),
                )

            with control_col_3:

                st.session_state.ai_mode = st.selectbox(
                    "⚙ Режим агента",
                    AI_MODES,
                    index=AI_MODES.index(st.session_state.ai_mode),
                    disabled=(
                        st.session_state.mode_selection_type == "Auto"
                    ),
                )

            with control_col_4:

                st.session_state.task_mode = st.selectbox(
                    "Тип задачи",
                    TASK_MODES,
                    index=TASK_MODES.index(st.session_state.task_mode),
                )

            if uploaded_file:

                document_text = read_file(
                    uploaded_file
                )

                document_hash = hashlib.sha256(
                    document_text.encode("utf-8")
                ).hexdigest()

                upload_key = (
                    st.session_state.current_chat,
                    uploaded_file.name,
                    uploaded_file.size,
                    document_hash,
                )

                if st.session_state.get("last_uploaded_document") != upload_key:

                    document_file_name = uploaded_file.name

                    version_number = save_document_version(
                        st.session_state.current_chat,
                        document_file_name,
                        document_text
                    )

                    st.session_state.last_uploaded_document = upload_key
                    chat_documents = load_chat_documents(
                        st.session_state.current_chat
                    )

                    st.rerun()

    if chat_documents:

        document_label = f"{len(chat_documents)} document(s)"

    else:

        document_label = "Документ не выбран"

    st.markdown(
        f"""
        <div class="composer-status">
            📄 {document_label} &nbsp;&nbsp; ⚙ {st.session_state.mode_selection_type}: {st.session_state.ai_mode}
        </div>
        """,
        unsafe_allow_html=True,
    )

    input_col, send_col = st.columns(
        [7, 1.25]
    )

    with input_col:

        prompt = st.text_input(
            "Сообщение",
            placeholder=MODE_HINTS[st.session_state.task_mode],
            label_visibility="collapsed",
            key=(
                f"message_input_"
                f"{st.session_state.current_chat}_"
                f"{st.session_state.message_nonce}"
            ),
        )

    with send_col:

        send_message = st.button(
            "➤",
            type="primary",
            use_container_width=True,
        )

if send_message and prompt.strip():

    prompt = prompt.strip()

    history = load_chat(
        st.session_state.current_chat
    )

    if len(history) == 0:

        try:

            title = generate_chat_title(prompt)

            if not title:

                title = prompt[:30]

        except Exception:

            title = prompt[:30]

        save_message(
            st.session_state.current_chat,
            "user",
            prompt,
            title
        )

    else:

        save_message(
            st.session_state.current_chat,
            "user",
            prompt
        )

    with st.chat_message("user"):

        st.markdown(prompt)

    extracted_memories = extract_user_memories(prompt)
    existing_memories = load_memories()

    for memory_text, importance in extracted_memories:

        normalized_memory = memory_text.lower()
        matching_memory = None

        for existing_memory in existing_memories:

            (
                existing_id,
                existing_text,
                existing_importance,
                existing_created_at,
                existing_updated_at
            ) = existing_memory

            if (
                normalized_memory in existing_text.lower()
                or existing_text.lower() in normalized_memory
            ):

                matching_memory = existing_memory
                break

        if matching_memory:

            update_memory(
                matching_memory[0],
                memory_text,
                max(importance, matching_memory[2])
            )

        else:

            save_memory(
                memory_text,
                importance
            )

    context_messages = get_chat_context(
        st.session_state.current_chat,
        10
    )

    context_text = (
        f"Current task type: {st.session_state.task_mode}\n"
    )

    relevant_memories = search_relevant_memories(
        prompt,
        5
    )

    if relevant_memories:

        context_text += "\nLong-term memory:\n"

        for memory in relevant_memories:

            memory_id, memory_text, importance, created_at, updated_at = memory

            context_text += (
                f"- {memory_text} "
                f"(importance: {importance})\n"
            )

    for role, message in context_messages:

        context_text += (
            f"{role}: {message}\n"
        )

    if (
        st.session_state.task_mode == "Анализ PDF"
        and not chat_documents
    ):

        selected_agent = "Document Agent"
        sources_used = []
        answer = (
            "Загрузите PDF-файл рядом с полем ввода, "
            "а затем повторите запрос для анализа."
        )

    else:

        selected_document_name = ""
        sources_used = []

        if chat_documents:

            compare_document_id, compare_version_ids = find_compare_version_scope(
                prompt,
                chat_documents,
                st.session_state.current_chat
            )

            if st.session_state.task_mode == "📚 Analyze All Documents":

                relevant_chunks = []

                for document_id, file_name, file_content, uploaded_at, version_number in chat_documents:

                    versions = get_document_versions(
                        st.session_state.current_chat,
                        file_name
                    )

                    if not versions:

                        continue

                    latest_version_id = versions[-1][0]

                    relevant_chunks.extend(
                        search_relevant_chunks(
                            st.session_state.current_chat,
                            prompt,
                            2,
                            document_id,
                            latest_version_id
                        )
                    )

                relevant_chunks = relevant_chunks[:5]

            elif compare_version_ids:

                relevant_chunks = []

                for compare_version_id in compare_version_ids:

                    relevant_chunks.extend(
                        search_relevant_chunks(
                            st.session_state.current_chat,
                            prompt,
                            3,
                            compare_document_id,
                            compare_version_id
                        )
                    )

            else:

                document_id_filter, version_id_filter = find_document_scope(
                    prompt,
                    chat_documents,
                    st.session_state.current_chat,
                    False
                )

                relevant_chunks = search_relevant_chunks(
                    st.session_state.current_chat,
                    prompt,
                    5,
                    document_id_filter,
                    version_id_filter
                )

            if relevant_chunks:

                document_text, sources_used = build_rag_context(
                    relevant_chunks
                )

                first_source = sources_used[0]
                selected_document_name = first_source

            elif st.session_state.task_mode in [
                "Анализ PDF",
                "📚 Analyze All Documents",
            ]:

                selected_agent = "Document Agent"
                answer = (
                    "В документах этого чата не найдено подходящей информации "
                    "по вашему запросу. Можно уточнить вопрос, указать имя файла "
                    "или задать вопрос в общем режиме."
                )
                selected_agent_message = (
                    f"🧠 Selected agent: {selected_agent}"
                )

                save_message(
                    st.session_state.current_chat,
                    "assistant",
                    f"{selected_agent_message}\n\n{answer}"
                )

                with st.chat_message("assistant"):

                    st.markdown(selected_agent_message)
                    st.markdown(answer)

                st.session_state.message_nonce += 1
                st.rerun()

            else:

                document_text = ""

        if selected_document_name:

            context_text += (
                f"\nSelected document: {selected_document_name}\n"
            )

        selected_agent, selected_mode, answer = router_agent(
            prompt,
            bool(chat_documents),
            st.session_state.mode_selection_type == "Auto",
            context_text,
            document_text[:30000],
            st.session_state.ai_mode
        )

        st.session_state.ai_mode = selected_mode

    selected_agent_message = (
        f"🧠 Selected agent: {selected_agent}"
    )

    save_message(
        st.session_state.current_chat,
        "assistant",
        (
            f"{selected_agent_message}\n\n"
            f"🔍 Sources used:\n"
            + "\n".join(f"* {source}" for source in sources_used)
            + f"\n\n{answer}"
            if sources_used
            else f"{selected_agent_message}\n\n{answer}"
        )
    )

    if len(history) == 0:

        st.session_state.chat_settings_open[settings_key] = False

    with st.chat_message(
        "assistant"
    ):

        st.markdown(selected_agent_message)

        if sources_used:

            st.markdown("🔍 Sources used:")

            for source in sources_used:

                st.markdown(f"* {source}")

        st.markdown(answer)

    st.session_state.message_nonce += 1

    st.rerun()
