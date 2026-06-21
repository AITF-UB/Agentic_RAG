try:
    from langchain_text_splitters import RecursiveCharacterTextSplitter
except ImportError:
    from langchain.text_splitter import RecursiveCharacterTextSplitter


class ChunkingService:

    def __init__(
        self,
        chunk_size=1800,
        chunk_overlap=200
    ):
        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap
        )

    def split_text(self, text: str):
        return self.splitter.split_text(text)