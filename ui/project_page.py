from pathlib import Path

import streamlit as st

from database import (
    delete_project,
    get_chat_recent_messages,
    get_project,
    get_project_artifacts,
    get_project_chats,
    get_project_documents,
    update_project,
)
from gemini_client import safe_generate_content


def generate_project_summary_context(project_id):
    project = get_project(project_id)

    if not project:
        return "Project not found."

    (
        project_id,
        title,
        description,
        deadline,
        status,
        created_at,
        updated_at,
    ) = project
    chats = get_project_chats(project_id)
    documents = get_project_documents(project_id)
    artifacts = get_project_artifacts(project_id)
    context_parts = [
        f"Project: {title}",
        f"Description: {description or 'No description'}",
        f"Deadline: {deadline or 'No deadline'}",
        f"Status: {status}",
        "",
        "Chats:",
    ]

    if chats:
        for chat_id, chat_title, _last_message_id in chats:
            context_parts.append(f"- Chat {chat_id}: {chat_title}")
            recent_messages = get_chat_recent_messages(chat_id, 4)

            for role, message in recent_messages:
                clean_message = " ".join((message or "").split())
                context_parts.append(f"  {role}: {clean_message[:500]}")
    else:
        context_parts.append("- No chats")

    context_parts.append("")
    context_parts.append("Documents:")

    if documents:
        for document_id, chat_id, file_name, created_at, versions_count in documents:
            context_parts.append(
                f"- {file_name} ({versions_count} version(s), chat {chat_id})"
            )
    else:
        context_parts.append("- No documents")

    context_parts.append("")
    context_parts.append("Artifacts:")

    if artifacts:
        for (
            artifact_id,
            chat_id,
            file_name,
            file_path,
            artifact_type,
            file_size,
            created_at,
        ) in artifacts:
            context_parts.append(
                f"- {file_name} ({artifact_type or Path(file_name).suffix}, chat {chat_id})"
            )
    else:
        context_parts.append("- No artifacts")

    return "\n".join(context_parts)


def render_project_page(project_id):
    if not project_id:
        st.info("Select or create a project in the sidebar.")
        return

    project = get_project(project_id)

    if not project:
        st.warning("Project not found.")
        st.session_state["active_project_id"] = None
        return

    (
        project_id,
        title,
        description,
        deadline,
        status,
        created_at,
        updated_at,
    ) = project

    st.markdown(f"## 📁 {title}")
    st.caption(
        f"Status: {status} · Deadline: {deadline or 'No deadline'} · Updated: {updated_at}"
    )

    if description:
        st.write(description)
    else:
        st.caption("No description yet.")

    edit_col, delete_col, summary_col = st.columns([1, 1, 1.2])

    with edit_col:
        with st.expander("Edit Project", expanded=False):
            new_title = st.text_input(
                "Title",
                value=title,
                key=f"project_title_{project_id}",
            )
            new_description = st.text_area(
                "Description",
                value=description or "",
                key=f"project_description_{project_id}",
            )
            new_deadline = st.text_input(
                "Deadline",
                value=deadline or "",
                key=f"project_deadline_{project_id}",
            )
            new_status = st.selectbox(
                "Status",
                ["active", "paused", "done", "archived"],
                index=["active", "paused", "done", "archived"].index(status)
                if status in ["active", "paused", "done", "archived"]
                else 0,
                key=f"project_status_{project_id}",
            )

            if st.button("Save Project", key=f"save_project_{project_id}"):
                update_project(
                    project_id,
                    new_title.strip() or title,
                    new_description.strip(),
                    new_deadline.strip() or None,
                    new_status,
                )
                st.rerun()

    with delete_col:
        if st.button("Delete Project", key=f"delete_project_{project_id}"):
            delete_project(project_id)
            st.session_state["active_project_id"] = None
            st.rerun()

    with summary_col:
        if st.button("Summarize Project", key=f"summarize_project_{project_id}"):
            context = generate_project_summary_context(project_id)
            prompt = f"""
Create a concise project summary from this workspace context.

Use exactly this structure:

Project Summary:
1. What this project is about
2. What has already been done
3. Existing files and artifacts
4. Possible missing parts
5. Recommended next steps

Context:
{context}
"""
            summary = safe_generate_content(prompt)
            st.session_state[f"project_summary_{project_id}"] = summary

    if st.session_state.get(f"project_summary_{project_id}"):
        st.markdown(st.session_state[f"project_summary_{project_id}"])

    chats = get_project_chats(project_id)
    documents = get_project_documents(project_id)
    artifacts = get_project_artifacts(project_id)

    with st.expander(f"Chats ({len(chats)})", expanded=False):
        if not chats:
            st.caption("No chats linked to this project.")
        else:
            for chat_id, chat_title, _last_message_id in chats:
                st.markdown(f"- Chat {chat_id}: {chat_title}")

    with st.expander(f"Documents ({len(documents)})", expanded=False):
        if not documents:
            st.caption("No documents linked to this project.")
        else:
            for document_id, chat_id, file_name, created_at, versions_count in documents:
                st.markdown(
                    f"- {file_name} · {versions_count} version(s) · Chat {chat_id}"
                )

    with st.expander(f"Artifacts ({len(artifacts)})", expanded=False):
        if not artifacts:
            st.caption("No artifacts linked to this project.")
        else:
            for (
                artifact_id,
                chat_id,
                file_name,
                file_path,
                artifact_type,
                file_size,
                created_at,
            ) in artifacts:
                st.markdown(
                    f"- {file_name} · {artifact_type or Path(file_name).suffix.upper()} · Chat {chat_id}"
                )
