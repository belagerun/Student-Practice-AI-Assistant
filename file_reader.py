from pypdf import PdfReader
from docx import Document


def read_file(uploaded_file):

    if uploaded_file is None:
        return ""

    uploaded_file.seek(0)

    filename = uploaded_file.name.lower()

    if filename.endswith(".txt"):

        return uploaded_file.read().decode("utf-8")

    elif filename.endswith(".pdf"):

        text = ""

        reader = PdfReader(uploaded_file)

        for page in reader.pages:

            page_text = page.extract_text()

            if page_text:
                text += page_text + "\n"

        return text

    elif filename.endswith(".docx"):

        document = Document(uploaded_file)

        text = ""

        for paragraph in document.paragraphs:

            text += paragraph.text + "\n"

        return text

    return ""
