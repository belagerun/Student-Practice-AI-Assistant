import streamlit as st

from database import create_project, get_projects


def render_project_panel():
    if "active_project_id" not in st.session_state:
        st.session_state["active_project_id"] = None

    with st.sidebar.expander("Projects", expanded=False):
        projects = get_projects()

        if not projects:
            st.caption("No projects yet")
        else:
            project_ids = [None] + [
                project[0]
                for project in projects
            ]
            project_by_id = {
                project[0]: project
                for project in projects
            }

            current_project_id = st.session_state.get("active_project_id")

            if current_project_id in project_ids:
                current_index = project_ids.index(current_project_id)
            else:
                current_index = 0

            selected_project_id = st.selectbox(
                "Active project",
                project_ids,
                index=current_index,
                key="project_panel_selectbox",
                format_func=lambda project_id: (
                    "No active project"
                    if project_id is None
                    else (
                        f"{project_by_id[project_id][1]} · "
                        f"{project_by_id[project_id][4]}"
                    )
                ),
            )
            st.session_state["active_project_id"] = selected_project_id

            if selected_project_id:
                selected_project = next(
                    (
                        project
                        for project in projects
                        if project[0] == selected_project_id
                    ),
                    None,
                )

                if selected_project:
                    st.caption(f"Status: {selected_project[4]}")

        st.markdown("**New project**")

        with st.form("create_project_form"):
            title = st.text_input("Title")
            description = st.text_area("Description", height=80)
            deadline = st.text_input("Deadline")
            submitted = st.form_submit_button("Create Project")

            if submitted:
                if not title.strip():
                    st.warning("Project title is required.")
                else:
                    project_id = create_project(
                        title.strip(),
                        description.strip(),
                        deadline.strip() or None,
                    )
                    st.session_state["active_project_id"] = project_id
                    st.rerun()

    return st.session_state.get("active_project_id")
