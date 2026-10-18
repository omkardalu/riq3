"""Demo support: sample resumes and a demo company account for a repeatable walkthrough.

    flask --app app demo            # writes ./demo_resumes and creates the demo account
See DEMO.md for the script and the expected results.
"""
from __future__ import annotations

import io
from pathlib import Path

DEMO_USERNAME = "demo"
DEMO_SKILLS = ["Python", "SQL", "Docker", "AWS", "React"]
DEMO_JOB_TITLE = "Full-Stack Developer"
DEMO_JOB_DESCRIPTION = (
    "We are hiring a full-stack developer to build web applications. You will design REST APIs, "
    "work with relational databases and deploy services in the cloud. Experience with microservices "
    "and automated testing is a plus. Python backend development, SQL, Docker and React are central to the role."
)

# (file name, kind, lines)
RESUMES: list[tuple[str, str, list[str]]] = [
    ("anita_rao.docx", "docx", [
        "Anita Rao", "anita.rao@example.com  +91 98100 11122", "",
        "Summary", "Full-stack developer who builds web applications with Python and React.", "",
        "Skills", "Python, SQL, Docker, AWS, React, Git, REST API, CI/CD", "",
        "Experience", "Software Engineer, Nimbus Labs - 3 years. Built REST APIs in Python and deployed Docker services on AWS.",
        "Designed relational databases in SQL and wrote automated tests for microservices.", "",
        "Education", "B.Tech in Computer Science, 2021", "",
        "Projects", "Resume screening portal (Python, React); Cloud cost dashboard (AWS, SQL)",
    ]),
    ("vikram_shah.pdf", "pdf", [
        "Vikram Shah", "vikram.shah@example.com  +91 98200 33344", "",
        "Skills", "Python, SQL, Docker, Linux, Git", "",
        "Experience", "Backend Developer, DataWorks - 2 years. Python services, SQL reporting, Docker deployments.", "",
        "Education", "B.E. in Information Technology, 2022", "",
        "Projects", "Inventory API in Python with SQL",
    ]),
    ("meera_iyer.docx", "docx", [
        "Meera Iyer", "meera.iyer@example.com  +91 98300 55566", "",
        "Skills", "React, JavaScript, HTML, CSS, Figma", "",
        "Experience", "Frontend Developer, PixelCraft - 2 years. Built responsive React interfaces.", "",
        "Education", "B.Sc in Computer Science, 2022", "",
        "Projects", "Portfolio builder (React); Design system (CSS)",
    ]),
    ("rohan_das.docx", "docx", [
        "Rohan Das", "rohan.das@example.com", "",
        "Skills", "Java, Spring, MySQL, Maven", "",
        "Experience", "Java Developer, FinServe - 4 years. Enterprise Java services.", "",
        "Education", "MCA, 2019",
    ]),
    ("scanned_resume.pdf", "scanned", []),  # image-only PDF: demonstrates the honest "Unsupported" result
]


def _pdf_escape(s: str) -> str:
    return s.encode("latin-1", "replace").decode("latin-1").replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def make_text_pdf(lines: list[str]) -> bytes:
    """A minimal, valid one-page PDF with a real text layer (no third-party library needed)."""
    ops = ["BT", "/F1 11 Tf", "14 TL", "50 800 Td"]
    for line in lines:
        ops.append(f"({_pdf_escape(line)}) Tj")
        ops.append("T*")
    ops.append("ET")
    return _assemble_pdf("\n".join(ops))


def make_image_only_pdf() -> bytes:
    """A PDF whose only content is a filled rectangle: what a scanned resume looks like to a text extractor."""
    return _assemble_pdf("0.8 g 50 500 300 250 re f")


def _assemble_pdf(stream: str) -> bytes:
    body = stream.encode("latin-1")
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(body)).encode() + b" >>\nstream\n" + body + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = io.BytesIO()
    out.write(b"%PDF-1.4\n")
    offsets = []
    for i, o in enumerate(objs, 1):
        offsets.append(out.tell())
        out.write(f"{i} 0 obj\n".encode() + o + b"\nendobj\n")
    xref = out.tell()
    out.write(f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode())
    for off in offsets:
        out.write(f"{off:010d} 00000 n \n".encode())
    out.write(f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
    return out.getvalue()


def make_docx(lines: list[str]) -> bytes:
    from docx import Document

    doc = Document()
    for line in lines:
        doc.add_paragraph(line)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def write_demo_files(folder: Path) -> list[Path]:
    folder.mkdir(parents=True, exist_ok=True)
    written = []
    for name, kind, lines in RESUMES:
        data = make_docx(lines) if kind == "docx" else make_image_only_pdf() if kind == "scanned" else make_text_pdf(lines)
        path = folder / name
        path.write_bytes(data)
        written.append(path)
    return written
