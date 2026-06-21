from pydantic import BaseModel, Field, ConfigDict, field_validator
from typing import Any, Dict, List, Optional


# --- Generate Models ---
class GenerateRequest(BaseModel):
    mapel_id: str = Field(max_length=100)
    elemen_id: str = Field(max_length=100)
    elemen_label: str = Field(max_length=200)
    materi: Optional[str] = Field("", max_length=1000)
    materi_id: Optional[str] = Field("", max_length=100)
    kelas_id: Optional[str] = Field("", max_length=50)
    jenjang: str = Field(max_length=50)
    atp: Optional[List[str]] = Field(default_factory=list)
    tipe: str = Field(description="pretest, bacaan, quiz_pg, quiz_essay, flashcard, mindmap", max_length=50)
    level: Optional[str] = Field(default=None, description="Low, Mid, or High (Null for mindmap)", max_length=20)
    instruksi_revisi: Optional[str] = Field(None, max_length=1000)
    konten_id: Optional[str] = Field(None, max_length=100)
    buku_id: Optional[str] = Field(None, max_length=200, description="ID unik buku untuk filter referensi spesifik buku")
    user_id: Optional[str] = Field(None, max_length=100, description="ID user untuk tracking")

    @field_validator("buku_id")
    @classmethod
    def normalize_buku_id(cls, v):
        if v is not None and v.strip() == "":
            return None
        return v

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
    visuals: Optional[List[str]] = None
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
