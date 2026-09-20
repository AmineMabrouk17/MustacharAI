import os
from dotenv import load_dotenv
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_community.vectorstores import Chroma

load_dotenv()

PDF_PATH = "constitution-2022.pdf"
DB_DIR = "./chroma_db"


def build_vector_db():
    print("1. Loading PDF...")
    loader = PyPDFLoader(PDF_PATH)
    docs = loader.load()
    print(f"Loaded {len(docs)} pages.")

    print("2. Splitting text into chunks...")
    # Chunk size of 800 chars with 150 overlap works well for legal articles
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=800,
        chunk_overlap=150,
        separators=["\n\n", "\n", " ", ""]
    )
    chunks = splitter.split_documents(docs)
    print(f"Created {len(chunks)} chunks.")

    print("3. Generating embeddings and storing in ChromaDB...")
    embeddings = GoogleGenerativeAIEmbeddings(model="models/text-embedding-004")

    Chroma.from_documents(
        documents=chunks,
        embedding=embeddings,
        persist_directory=DB_DIR
    )
    print("Index created successfully in ./chroma_db!")


if __name__ == "__main__":
    build_vector_db()