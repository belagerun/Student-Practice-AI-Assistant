# Streamlit AI Assistant

Streamlit AI Assistant is a student-focused AI chat app with Gemini integration, chat history, long-term memory, multi-document workspaces, document versions, and Mini-RAG search over document chunks.

## Features

- Multiple chats with saved history.
- Long-term user memory.
- Upload and analyze `.txt`, `.pdf`, and `.docx` files.
- Multiple documents per chat.
- Document version history.
- Mini-RAG chunk search for document questions.
- Automatic agent routing.
- Safe Gemini quota handling.
- SQLite storage with a configurable database path.

## Project Structure

```text
.
├── app.py              # Streamlit entry point
├── database.py         # SQLite tables and data functions
├── gemini_client.py    # Gemini API client and agents
├── file_reader.py      # TXT, PDF, DOCX text extraction
├── requirements.txt    # Python dependencies
├── render.yaml         # Render deployment config
└── .env.example        # Environment variable template
```

## Environment Variables

Create a local `.env` file from `.env.example` if you run the app locally with environment variables, or set these variables directly in your shell or hosting platform.

```env
GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=gemini-2.5-flash
SQLITE_DB_PATH=chat_history.db
```

`GEMINI_API_KEY` is required for Gemini responses. Do not commit real API keys to GitHub.

## Local Run

Install dependencies:

```bash
pip install -r requirements.txt
```

Run the app:

```bash
streamlit run app.py
```

The app starts from `app.py`.

## SQLite Notes

By default, SQLite stores data in `chat_history.db` in the project folder. This is fine for local development.

On Render, the filesystem is ephemeral unless you attach a Persistent Disk. The included `render.yaml` sets:

```env
SQLITE_DB_PATH=/var/data/chat_history.db
```

and mounts a Persistent Disk at `/var/data`, so chats, memories, documents, versions, and chunks can survive service restarts and deploys.

For heavier production usage, multiple app instances, or concurrent users, migrate from SQLite to PostgreSQL. Render PostgreSQL is a better long-term option when the app becomes multi-user.

## Deploy To Render

1. Push this project to a GitHub repository.
2. Make sure `.env`, local `.db` files, and `.streamlit/secrets.toml` are not committed.
3. Open Render and choose **New +** → **Blueprint**.
4. Connect the GitHub repository.
5. Render will detect `render.yaml`.
6. Add the `GEMINI_API_KEY` secret value when Render asks for environment variables.
7. Deploy.
8. After deploy, open the Render service URL.

The Render service uses:

```bash
streamlit run app.py --server.address 0.0.0.0 --server.port $PORT --server.headless true
```

## GitHub Publishing Checklist

- No API keys in source code.
- Real `.env` file is ignored.
- SQLite database files are ignored.
- `requirements.txt` is present.
- `render.yaml` is present.
- App entry point is `app.py`.

## Important Security Note

If an API key was ever pasted into chat or committed to Git, rotate it in Google AI Studio before making the repository public.
