import sqlite3
import os
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv():
        return None


load_dotenv()


DB_PATH = Path(
    os.getenv(
        "SQLITE_DB_PATH",
        Path(__file__).resolve().with_name("chat_history.db")
    )
)

DB_PATH.parent.mkdir(
    parents=True,
    exist_ok=True
)

conn = sqlite3.connect(
    DB_PATH,
    check_same_thread=False
)

cursor = conn.cursor()


def _table_columns(table_name):
    cursor.execute(f"PRAGMA table_info({table_name})")

    return [
        row[1]
        for row in cursor.fetchall()
    ]


def _add_column_if_missing(table_name, column_name, column_definition):
    if column_name in _table_columns(table_name):

        return

    cursor.execute(
        f"""
        ALTER TABLE {table_name}
        ADD COLUMN {column_name} {column_definition}
        """
    )

cursor.execute("""
CREATE TABLE IF NOT EXISTS chats(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER,
    chat_title TEXT,
    role TEXT,
    message TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS documents(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER,
    file_name TEXT,
    file_content TEXT,
    uploaded_at TEXT DEFAULT CURRENT_TIMESTAMP
)
""")

cursor.execute("PRAGMA table_info(documents)")
document_columns = [
    row[1]
    for row in cursor.fetchall()
]

if "uploaded_at" not in document_columns:

    cursor.execute(
        """
        ALTER TABLE documents
        ADD COLUMN uploaded_at TEXT
        """
    )

    cursor.execute(
        """
        UPDATE documents
        SET uploaded_at=CURRENT_TIMESTAMP
        WHERE uploaded_at IS NULL
        """
    )

if "created_at" not in document_columns:

    cursor.execute(
        """
        ALTER TABLE documents
        ADD COLUMN created_at TEXT
        """
    )

    cursor.execute(
        """
        UPDATE documents
        SET created_at=COALESCE(uploaded_at, CURRENT_TIMESTAMP)
        WHERE created_at IS NULL
        """
    )

cursor.execute("""
CREATE TABLE IF NOT EXISTS document_versions(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id INTEGER,
    version_number INTEGER,
    file_content TEXT,
    uploaded_at TEXT DEFAULT CURRENT_TIMESTAMP
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS document_chunks(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER,
    document_id INTEGER,
    version_id INTEGER,
    chunk_index INTEGER,
    chunk_text TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS memory(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    memory_text TEXT,
    importance INTEGER,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS projects(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    description TEXT,
    deadline TEXT,
    status TEXT DEFAULT 'active',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS artifacts(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER,
    project_id INTEGER,
    file_name TEXT NOT NULL,
    file_path TEXT,
    artifact_type TEXT,
    file_size INTEGER,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
)
""")

_add_column_if_missing(
    "chats",
    "project_id",
    "INTEGER"
)
_add_column_if_missing(
    "documents",
    "project_id",
    "INTEGER"
)
_add_column_if_missing(
    "artifacts",
    "project_id",
    "INTEGER"
)
_add_column_if_missing(
    "artifacts",
    "chat_id",
    "INTEGER"
)
_add_column_if_missing(
    "artifacts",
    "file_name",
    "TEXT"
)
_add_column_if_missing(
    "artifacts",
    "file_path",
    "TEXT"
)
_add_column_if_missing(
    "artifacts",
    "artifact_type",
    "TEXT"
)
_add_column_if_missing(
    "artifacts",
    "file_size",
    "INTEGER"
)
_add_column_if_missing(
    "artifacts",
    "created_at",
    "TEXT"
)

conn.commit()


def migrate_document_versions():

    cursor.execute(
        """
        SELECT id, chat_id, file_name, file_content, uploaded_at
        FROM documents
        WHERE file_content IS NOT NULL
        ORDER BY chat_id, file_name, id
        """
    )

    old_documents = cursor.fetchall()
    grouped_documents = {}

    for document in old_documents:

        document_id, chat_id, file_name, file_content, uploaded_at = document
        grouped_documents.setdefault(
            (chat_id, file_name),
            []
        ).append(document)

    for (chat_id, file_name), documents_group in grouped_documents.items():

        main_document_id = documents_group[0][0]

        cursor.execute(
            """
            SELECT COUNT(*)
            FROM document_versions
            WHERE document_id=?
            """,
            (main_document_id,)
        )

        if cursor.fetchone()[0] == 0:

            for version_index, document in enumerate(documents_group, start=1):

                (
                    document_id,
                    chat_id,
                    file_name,
                    file_content,
                    uploaded_at
                ) = document

                cursor.execute(
                    """
                    INSERT INTO document_versions
                    (document_id, version_number, file_content, uploaded_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        main_document_id,
                        version_index,
                        file_content,
                        uploaded_at
                    )
                )

        duplicate_ids = [
            document[0]
            for document in documents_group[1:]
        ]

        if duplicate_ids:

            cursor.executemany(
                """
                DELETE FROM documents
                WHERE id=?
                """,
                [
                    (duplicate_id,)
                    for duplicate_id in duplicate_ids
                ]
            )

        cursor.execute(
            """
            UPDATE documents
            SET file_content=NULL, uploaded_at=NULL
            WHERE id=?
            """,
            (main_document_id,)
        )

    conn.commit()


migrate_document_versions()


def save_message(
    chat_id,
    role,
    message,
    chat_title=None,
    project_id=None
):

    cursor.execute(
        """
        INSERT INTO chats
        (chat_id, chat_title, role, message, project_id)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            chat_id,
            chat_title,
            role,
            message,
            project_id
        )
    )

    conn.commit()


def load_chat(chat_id):

    cursor.execute(
        """
        SELECT role, message
        FROM chats
        WHERE chat_id=?
        ORDER BY id
        """,
        (chat_id,)
    )

    return cursor.fetchall()


def get_chat_list():

    cursor.execute(
        """
        SELECT chat_id
        FROM chats
        UNION
        SELECT chat_id
        FROM documents
        ORDER BY chat_id DESC
        """
    )

    return [row[0] for row in cursor.fetchall()]

def set_chat_title(chat_id, title):

    cursor.execute(
        """
        UPDATE chats
        SET chat_title=?
        WHERE chat_id=?
        """,
        (title, chat_id)
    )

    conn.commit()


def get_chat_title(chat_id):

    cursor.execute(
        """
        SELECT chat_title
        FROM chats
        WHERE chat_id=?
        LIMIT 1
        """,
        (chat_id,)
    )

    row = cursor.fetchone()

    if row and row[0]:
        return row[0]

    return f"Chat {chat_id}"

def delete_chat(chat_id):

    cursor.execute(
        """
        DELETE FROM chats
        WHERE chat_id=?
        """,
        (chat_id,)
    )

    conn.commit()


def split_text_into_chunks(text, chunk_size=1000, overlap=200):

    if not text:

        return []

    chunks = []
    start = 0
    text_length = len(text)

    while start < text_length:

        end = start + chunk_size
        chunk = text[start:end].strip()

        if chunk:

            chunks.append(chunk)

        if end >= text_length:

            break

        start = max(0, end - overlap)

    return chunks


def save_document_chunks(chat_id, document_id, version_id, chunks):

    cursor.execute(
        """
        DELETE FROM document_chunks
        WHERE version_id=?
        """,
        (version_id,)
    )

    for chunk_index, chunk_text in enumerate(chunks, start=1):

        cursor.execute(
            """
            INSERT INTO document_chunks
            (chat_id, document_id, version_id, chunk_index, chunk_text, created_at)
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (
                chat_id,
                document_id,
                version_id,
                chunk_index,
                chunk_text
            )
        )

    conn.commit()


def search_relevant_chunks(
    chat_id,
    query,
    limit=5,
    document_id=None,
    version_id=None
):

    sql = """
        SELECT
            c.id,
            c.document_id,
            c.version_id,
            c.chunk_index,
            c.chunk_text,
            d.file_name,
            v.version_number
        FROM document_chunks c
        JOIN documents d ON d.id=c.document_id
        JOIN document_versions v ON v.id=c.version_id
        WHERE c.chat_id=?
    """
    params = [chat_id]

    if document_id is not None:

        sql += " AND c.document_id=?"
        params.append(document_id)

    if version_id is not None:

        sql += " AND c.version_id=?"
        params.append(version_id)

    cursor.execute(
        sql,
        params
    )

    rows = cursor.fetchall()
    query_words = set(query.lower().split())
    scored_chunks = []

    for row in rows:

        (
            chunk_id,
            row_document_id,
            row_version_id,
            chunk_index,
            chunk_text,
            file_name,
            version_number
        ) = row

        chunk_words = set(chunk_text.lower().split())
        file_words = set(file_name.lower().split())
        score = len(query_words.intersection(chunk_words))
        score += len(query_words.intersection(file_words)) * 2

        if score > 0:

            scored_chunks.append((score, row))

    scored_chunks.sort(
        key=lambda item: item[0],
        reverse=True
    )

    return [
        row
        for score, row in scored_chunks[:limit]
    ]


def migrate_document_chunks():

    cursor.execute(
        """
        SELECT
            d.chat_id,
            d.id,
            v.id,
            v.file_content
        FROM documents d
        JOIN document_versions v ON v.document_id=d.id
        """
    )

    versions = cursor.fetchall()

    for chat_id, document_id, version_id, file_content in versions:

        cursor.execute(
            """
            SELECT COUNT(*)
            FROM document_chunks
            WHERE version_id=?
            """,
            (version_id,)
        )

        if cursor.fetchone()[0] > 0:

            continue

        chunks = split_text_into_chunks(file_content)

        save_document_chunks(
            chat_id,
            document_id,
            version_id,
            chunks
        )


def save_document_version(chat_id, file_name, file_content, project_id=None):

    cursor.execute(
        """
        SELECT id
        FROM documents
        WHERE chat_id=? AND file_name=?
        LIMIT 1
        """,
        (
            chat_id,
            file_name
        )
    )

    row = cursor.fetchone()

    if row:

        document_id = row[0]

        if project_id is not None:

            cursor.execute(
                """
                UPDATE documents
                SET project_id=?
                WHERE id=?
                """,
                (
                    project_id,
                    document_id
                )
            )

    else:

        cursor.execute(
            """
            INSERT INTO documents
            (chat_id, file_name, project_id, created_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (
                chat_id,
                file_name,
                project_id
            )
        )

        document_id = cursor.lastrowid

    cursor.execute(
        """
        SELECT COALESCE(MAX(version_number), 0) + 1
        FROM document_versions
        WHERE document_id=?
        """,
        (document_id,)
    )

    version_number = cursor.fetchone()[0]

    cursor.execute(
        """
        INSERT INTO document_versions
        (document_id, version_number, file_content, uploaded_at)
        VALUES (?, ?, ?, CURRENT_TIMESTAMP)
        """,
        (
            document_id,
            version_number,
            file_content
        )
    )

    version_id = cursor.lastrowid
    chunks = split_text_into_chunks(file_content)

    save_document_chunks(
        chat_id,
        document_id,
        version_id,
        chunks
    )

    conn.commit()

    return version_number


def save_document(chat_id, file_name, file_content, project_id=None):

    return save_document_version(
        chat_id,
        file_name,
        file_content,
        project_id
    )


def load_document(chat_id):

    cursor.execute(
        """
        SELECT d.file_name, v.file_content
        FROM documents d
        JOIN document_versions v ON v.document_id=d.id
        WHERE d.chat_id=?
        ORDER BY v.uploaded_at DESC, v.id DESC
        LIMIT 1
        """,
        (chat_id,)
    )

    return cursor.fetchone()


def load_chat_documents(chat_id):

    cursor.execute(
        """
        SELECT
            d.id,
            d.file_name,
            v.file_content,
            v.uploaded_at,
            v.version_number
        FROM documents d
        LEFT JOIN document_versions v
            ON v.document_id=d.id
            AND v.version_number=(
                SELECT MAX(version_number)
                FROM document_versions
                WHERE document_id=d.id
            )
        WHERE d.chat_id=?
        ORDER BY d.created_at DESC, d.id DESC
        """,
        (chat_id,)
    )

    return cursor.fetchall()


def delete_brand_html_messages():

    cursor.execute(
        """
        DELETE FROM chats
        WHERE message LIKE '%brand-name%'
           OR message LIKE '%brand-subtitle%'
           OR message LIKE '%brand-context%'
           OR message LIKE '%brand-header%'
        """
    )

    conn.commit()


def get_document_versions(chat_id, file_name):

    cursor.execute(
        """
        SELECT
            v.id,
            v.version_number,
            v.file_content,
            v.uploaded_at
        FROM documents d
        JOIN document_versions v ON v.document_id=d.id
        WHERE d.chat_id=? AND d.file_name=?
        ORDER BY v.version_number ASC
        """,
        (
            chat_id,
            file_name
        )
    )

    return cursor.fetchall()


def load_latest_document_version(chat_id, file_name):

    cursor.execute(
        """
        SELECT v.version_number, v.file_content, v.uploaded_at
        FROM documents d
        JOIN document_versions v ON v.document_id=d.id
        WHERE d.chat_id=? AND d.file_name=?
        ORDER BY v.version_number DESC
        LIMIT 1
        """,
        (
            chat_id,
            file_name
        )
    )

    return cursor.fetchone()


def load_specific_document_version(chat_id, file_name, version_number):

    cursor.execute(
        """
        SELECT v.version_number, v.file_content, v.uploaded_at
        FROM documents d
        JOIN document_versions v ON v.document_id=d.id
        WHERE d.chat_id=? AND d.file_name=? AND v.version_number=?
        LIMIT 1
        """,
        (
            chat_id,
            file_name,
            version_number
        )
    )

    return cursor.fetchone()


def delete_document(chat_id):

    cursor.execute(
        """
        DELETE FROM document_chunks
        WHERE chat_id=?
        """,
        (chat_id,)
    )

    cursor.execute(
        """
        DELETE FROM document_versions
        WHERE document_id IN (
            SELECT id
            FROM documents
            WHERE chat_id=?
        )
        """,
        (chat_id,)
    )

    cursor.execute(
        """
        DELETE FROM documents
        WHERE chat_id=?
        """,
        (chat_id,)
    )

    conn.commit()


def delete_document_by_id(document_id):

    cursor.execute(
        """
        DELETE FROM document_chunks
        WHERE document_id=?
        """,
        (document_id,)
    )

    cursor.execute(
        """
        DELETE FROM document_versions
        WHERE document_id=?
        """,
        (document_id,)
    )

    cursor.execute(
        """
        DELETE FROM documents
        WHERE id=?
        """,
        (document_id,)
    )

    conn.commit()


def delete_document_version(chat_id, file_name, version_number):

    cursor.execute(
        """
        SELECT id
        FROM documents
        WHERE chat_id=? AND file_name=?
        LIMIT 1
        """,
        (
            chat_id,
            file_name
        )
    )

    row = cursor.fetchone()

    if not row:

        return

    document_id = row[0]

    cursor.execute(
        """
        DELETE FROM document_chunks
        WHERE version_id IN (
            SELECT id
            FROM document_versions
            WHERE document_id=? AND version_number=?
        )
        """,
        (
            document_id,
            version_number
        )
    )

    cursor.execute(
        """
        DELETE FROM document_versions
        WHERE document_id=? AND version_number=?
        """,
        (
            document_id,
            version_number
        )
    )

    cursor.execute(
        """
        SELECT COUNT(*)
        FROM document_versions
        WHERE document_id=?
        """,
        (document_id,)
    )

    if cursor.fetchone()[0] == 0:

        cursor.execute(
            """
            DELETE FROM documents
            WHERE id=?
            """,
            (document_id,)
        )

    conn.commit()


def delete_document_with_versions(chat_id, file_name):

    cursor.execute(
        """
        SELECT id
        FROM documents
        WHERE chat_id=? AND file_name=?
        LIMIT 1
        """,
        (
            chat_id,
            file_name
        )
    )

    row = cursor.fetchone()

    if not row:

        return

    delete_document_by_id(row[0])

    
def get_chat_context(chat_id, limit=10):

    cursor.execute(
        """
        SELECT role, message
        FROM chats
        WHERE chat_id=?
        ORDER BY id DESC
        LIMIT ?
        """,
        (chat_id, limit)
    )

    rows = cursor.fetchall()

    rows.reverse()

    return rows


def create_project(title, description="", deadline=None):
    cursor.execute(
        """
        INSERT INTO projects
        (title, description, deadline, status, created_at, updated_at)
        VALUES (?, ?, ?, 'active', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """,
        (
            title,
            description,
            deadline
        )
    )
    conn.commit()

    return cursor.lastrowid


def get_projects():
    cursor.execute(
        """
        SELECT id, title, description, deadline, status, created_at, updated_at
        FROM projects
        ORDER BY updated_at DESC, id DESC
        """
    )

    return cursor.fetchall()


def get_project(project_id):
    if not project_id:

        return None

    cursor.execute(
        """
        SELECT id, title, description, deadline, status, created_at, updated_at
        FROM projects
        WHERE id=?
        LIMIT 1
        """,
        (project_id,)
    )

    return cursor.fetchone()


def update_project(
    project_id,
    title=None,
    description=None,
    deadline=None,
    status=None
):
    project = get_project(project_id)

    if not project:

        return

    current_title = project[1]
    current_description = project[2]
    current_deadline = project[3]
    current_status = project[4]

    cursor.execute(
        """
        UPDATE projects
        SET title=?,
            description=?,
            deadline=?,
            status=?,
            updated_at=CURRENT_TIMESTAMP
        WHERE id=?
        """,
        (
            title if title is not None else current_title,
            description if description is not None else current_description,
            deadline if deadline is not None else current_deadline,
            status if status is not None else current_status,
            project_id
        )
    )
    conn.commit()


def delete_project(project_id):
    if not project_id:

        return

    cursor.execute(
        """
        UPDATE chats
        SET project_id=NULL
        WHERE project_id=?
        """,
        (project_id,)
    )
    cursor.execute(
        """
        UPDATE documents
        SET project_id=NULL
        WHERE project_id=?
        """,
        (project_id,)
    )
    cursor.execute(
        """
        UPDATE artifacts
        SET project_id=NULL
        WHERE project_id=?
        """,
        (project_id,)
    )
    cursor.execute(
        """
        DELETE FROM projects
        WHERE id=?
        """,
        (project_id,)
    )
    conn.commit()


def get_project_chats(project_id):
    if not project_id:

        return []

    cursor.execute(
        """
        SELECT
            chat_id,
            COALESCE(MAX(chat_title), 'Chat ' || chat_id) AS title,
            MAX(id) AS last_message_id
        FROM chats
        WHERE project_id=?
        GROUP BY chat_id
        ORDER BY last_message_id DESC
        """,
        (project_id,)
    )

    return cursor.fetchall()


def get_project_documents(project_id):
    if not project_id:

        return []

    cursor.execute(
        """
        SELECT
            d.id,
            d.chat_id,
            d.file_name,
            d.created_at,
            COUNT(v.id) AS versions_count
        FROM documents d
        LEFT JOIN document_versions v ON v.document_id=d.id
        WHERE d.project_id=?
        GROUP BY d.id, d.chat_id, d.file_name, d.created_at
        ORDER BY d.created_at DESC, d.id DESC
        """,
        (project_id,)
    )

    return cursor.fetchall()


def get_project_artifacts(project_id):
    if not project_id:

        return []

    cursor.execute(
        """
        SELECT id, chat_id, file_name, file_path, artifact_type, file_size, created_at
        FROM artifacts
        WHERE project_id=?
        ORDER BY created_at DESC, id DESC
        """,
        (project_id,)
    )

    return cursor.fetchall()


def assign_chat_to_project(chat_id, project_id):
    cursor.execute(
        """
        UPDATE chats
        SET project_id=?
        WHERE chat_id=?
        """,
        (
            project_id,
            chat_id
        )
    )
    conn.commit()


def assign_document_to_project(document_id, project_id):
    cursor.execute(
        """
        UPDATE documents
        SET project_id=?
        WHERE id=?
        """,
        (
            project_id,
            document_id
        )
    )
    conn.commit()


def assign_artifact_to_project(artifact_id, project_id):
    cursor.execute(
        """
        UPDATE artifacts
        SET project_id=?
        WHERE id=?
        """,
        (
            project_id,
            artifact_id
        )
    )
    conn.commit()


def register_artifact(
    file_name,
    file_path="",
    artifact_type="",
    file_size=None,
    chat_id=None,
    project_id=None
):
    cursor.execute(
        """
        SELECT id
        FROM artifacts
        WHERE file_name=?
        LIMIT 1
        """,
        (file_name,)
    )
    row = cursor.fetchone()

    if row:

        artifact_id = row[0]
        cursor.execute(
            """
            UPDATE artifacts
            SET file_path=?,
                artifact_type=?,
                file_size=?,
                chat_id=COALESCE(?, chat_id),
                project_id=COALESCE(?, project_id)
            WHERE id=?
            """,
            (
                file_path,
                artifact_type,
                file_size,
                chat_id,
                project_id,
                artifact_id
            )
        )

    else:

        cursor.execute(
            """
            INSERT INTO artifacts
            (chat_id, project_id, file_name, file_path, artifact_type, file_size, created_at)
            VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (
                chat_id,
                project_id,
                file_name,
                file_path,
                artifact_type,
                file_size
            )
        )
        artifact_id = cursor.lastrowid

    conn.commit()

    return artifact_id


def delete_artifact_by_name(file_name):
    cursor.execute(
        """
        DELETE FROM artifacts
        WHERE file_name=?
        """,
        (file_name,)
    )
    conn.commit()


def get_chat_recent_messages(chat_id, limit=5):
    return get_chat_context(chat_id, limit)


def save_memory(memory_text, importance=3):

    cursor.execute(
        """
        INSERT INTO memory
        (memory_text, importance, created_at, updated_at)
        VALUES (?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """,
        (
            memory_text,
            importance
        )
    )

    conn.commit()


def load_memories():

    cursor.execute(
        """
        SELECT id, memory_text, importance, created_at, updated_at
        FROM memory
        ORDER BY importance DESC, updated_at DESC
        """
    )

    return cursor.fetchall()


def search_relevant_memories(query, limit=5):

    memories = load_memories()
    query_words = set(query.lower().split())
    scored_memories = []

    for memory in memories:

        memory_id, memory_text, importance, created_at, updated_at = memory
        memory_words = set(memory_text.lower().split())
        score = len(query_words.intersection(memory_words)) + importance

        if score > importance:

            scored_memories.append((score, memory))

    if not scored_memories:

        return memories[:limit]

    scored_memories.sort(
        key=lambda item: item[0],
        reverse=True
    )

    return [
        memory
        for score, memory in scored_memories[:limit]
    ]


def update_memory(memory_id, memory_text, importance):

    cursor.execute(
        """
        UPDATE memory
        SET memory_text=?, importance=?, updated_at=CURRENT_TIMESTAMP
        WHERE id=?
        """,
        (
            memory_text,
            importance,
            memory_id
        )
    )

    conn.commit()


def delete_memory(memory_id):

    cursor.execute(
        """
        DELETE FROM memory
        WHERE id=?
        """,
        (memory_id,)
    )

    conn.commit()


migrate_document_chunks()
