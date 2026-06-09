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
    chat_title=None
):

    cursor.execute(
        """
        INSERT INTO chats
        (chat_id, chat_title, role, message)
        VALUES (?, ?, ?, ?)
        """,
        (
            chat_id,
            chat_title,
            role,
            message
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


def save_document_version(chat_id, file_name, file_content):

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

    else:

        cursor.execute(
            """
            INSERT INTO documents
            (chat_id, file_name, created_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            """,
            (
                chat_id,
                file_name
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


def save_document(chat_id, file_name, file_content):

    return save_document_version(
        chat_id,
        file_name,
        file_content
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
