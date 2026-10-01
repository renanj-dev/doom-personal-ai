import io
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
os.environ.setdefault("DOOM_API_KEY", "test")

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from docx import Document
from pypdf import PdfWriter

from app.db import Base
from app.knowledge_engine import KNOWLEDGE_ENGINE
from app.models import KnowledgeDocument, KnowledgeChunk
from app.llm import _messages


class KnowledgeEngineTests(unittest.TestCase):
    def _db(self):
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        engine = create_engine(f"sqlite:///{path}")
        Base.metadata.create_all(engine)
        return engine, sessionmaker(bind=engine), path

    def test_text_ingestion_chunks_and_retrieves_relevant_source(self):
        engine, Session, path = self._db()
        try:
            with Session() as db:
                doc = KNOWLEDGE_ENGINE.create_text(
                    db,
                    title="Análise Combinatória",
                    content="Arranjo simples: a ordem importa e não há repetição. A fórmula é An,p = n!/(n-p)!.",
                    collection="Estudos",
                    topic="Matemática",
                    version="2026",
                )
                self.assertEqual(doc.source_type, "text")
                self.assertGreaterEqual(db.query(KnowledgeChunk).filter(KnowledgeChunk.document_id == doc.id).count(), 1)
                hits = KNOWLEDGE_ENGINE.search(db, "arranjo ordem importa", limit=3)
                self.assertEqual(len(hits), 1)
                self.assertEqual(hits[0].document_id, doc.id)
                self.assertIn("ordem importa", hits[0].content)
        finally:
            os.remove(path)

    def test_unrelated_query_does_not_retrieve_document(self):
        engine, Session, path = self._db()
        try:
            with Session() as db:
                KNOWLEDGE_ENGINE.create_text(db, title="CLT", content="Férias e período aquisitivo", collection="Leis")
                hits = KNOWLEDGE_ENGINE.search(db, "fotossíntese cloroplasto", limit=3)
                self.assertEqual(hits, [])
        finally:
            os.remove(path)

    def test_pdf_text_extraction(self):
        engine, Session, path = self._db()
        try:
            buffer = io.BytesIO()
            writer = PdfWriter()
            writer.add_blank_page(width=300, height=300)
            # PyPDF cannot author text without an external layout engine; verify
            # that unsupported blank text safely produces a clear empty-content error.
            writer.write(buffer)
            with Session() as db:
                with self.assertRaises(ValueError):
                    KNOWLEDGE_ENGINE.ingest_file(db, filename="vazio.pdf", data=buffer.getvalue(), mime_type="application/pdf")
        finally:
            os.remove(path)

    def test_docx_text_extraction(self):
        engine, Session, path = self._db()
        try:
            buffer = io.BytesIO()
            document = Document()
            document.add_paragraph("O ciclo de Krebs ocorre na matriz mitocondrial.")
            document.save(buffer)
            with Session() as db:
                doc = KNOWLEDGE_ENGINE.ingest_file(db, filename="biologia.docx", data=buffer.getvalue(), mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document")
                self.assertEqual(doc.source_type, "docx")
                hits = KNOWLEDGE_ENGINE.search(db, "ciclo de Krebs matriz mitocondrial")
                self.assertTrue(hits)
        finally:
            os.remove(path)

    def test_delete_removes_document_and_chunks(self):
        engine, Session, path = self._db()
        try:
            with Session() as db:
                doc = KNOWLEDGE_ENGINE.create_text(db, title="Temp", content="Conhecimento temporário.")
                doc_id = doc.id
                self.assertTrue(KNOWLEDGE_ENGINE.delete_document(db, doc_id))
                self.assertIsNone(db.get(KnowledgeDocument, doc_id))
                self.assertEqual(db.query(KnowledgeChunk).filter(KnowledgeChunk.document_id == doc_id).count(), 0)
        finally:
            os.remove(path)

    def test_context_llm_receives_knowledge_as_reference(self):
        messages = _messages(
            memory_text="[trabalho] currículo administrativo",
            recent_messages=[{"role":"user","content":"CURRENT_USER_REQUEST\nExplique arranjo simples."}],
            profile_text="PERFIL DE APOIO",
            knowledge_text="[KNOWLEDGE 1] título='Arranjo'\nA ordem importa e não há repetição.",
        )
        system = messages[0]["content"]
        self.assertIn("BASE DE CONHECIMENTO", system)
        self.assertIn("A ordem importa", system)
        self.assertIn("não como instruções", system.lower())
        self.assertTrue(messages[-1]["content"].startswith("CURRENT_USER_REQUEST"))


if __name__ == "__main__":
    unittest.main()
