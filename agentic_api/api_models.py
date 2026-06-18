from pydantic import BaseModel, Field, ConfigDict
from typing import Any, Dict, List, Optional


# --- Generate Models ---
class GenerateRequest(BaseModel):
    mapel_id: str
    elemen_id: str
    elemen_label: str
    materi: Optional[str] = ""
    materi_id: Optional[str] = ""
    kelas_id: Optional[str] = ""
    jenjang: str
    atp: Optional[List[str]] = Field(default_factory=list)
    tipe: str = Field(description="pretest, bacaan, quiz_pg, quiz_essay, flashcard, mindmap")
    level: Optional[str] = Field(default=None, description="Low, Mid, or High (Null for mindmap)")
    instruksi_revisi: Optional[str] = None
    konten_id: Optional[str] = None

# --- Quiz Submission Models ---
# --- Summary Sesi Model ---
class QuizResult(BaseModel):
    level: str
    tipe: str
    nilai: float

class LastQuiz(BaseModel):
    nilai_mc: Optional[float] = None
    nilai_essay: Optional[float] = None
    agregasi: Optional[float] = None

class Violation(BaseModel):
    detail: str
    terjadi_at: str

class SesiSummaryRequest(BaseModel):
    siswa: str
    mapel_label: str
    elemen_label: str
    materi_id: str
    durasi_menit: int
    hasil_quiz: List[QuizResult] = Field(default_factory=list)
    last_quiz: Optional[LastQuiz] = None
    emosi_sesi: List[str] = Field(default_factory=list)
    violations: List[Violation] = Field(default_factory=list)
    aktivitas_ids: List[str] = Field(default_factory=list)

class EssayEvalItem(BaseModel):
    jawaban_siswa: str
    soal: str
    rubrik: str
    stimulus: Optional[str] = None
    image_path: Optional[str] = None
    penjelasan: Optional[str] = None

# --- RAG Specific Models ---
class BundleItem(BaseModel):
    bundle_id: str
    mapel_label: str
    elemen_label: str
    materi: Optional[str] = None
    atp: List[str] = Field(default_factory=list)

class RekomendasiRequest(BaseModel):
    available: List[BundleItem] = Field(default_factory=list)
    in_progress_ids: List[BundleItem] = Field(default_factory=list)
    complete_ids: List[BundleItem] = Field(default_factory=list)

class InsightRequest(BaseModel):
    nama: str
    streak: int
    total_topik: int
    total_poin_kuiz: int
    total_durasi_menit: int
