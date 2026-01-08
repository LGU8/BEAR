from langchain_community.document_loaders import PyPDFLoader, UnstructuredURLLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings
from langchain_chroma import Chroma
from dotenv import load_dotenv
import os

rag_path = "./RAG"
all_splits = []
text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=100)

# pdf 불러오기 및 청크화
for filename in os.listdir(rag_path):
    if filename.endswith(".pdf"):
        input_path = os.path.join(rag_path, filename)
        
        try:
            loader = PyPDFLoader(input_path)
            docs = loader.load()

            # 문서에 metadata 추가
            for d in docs:
                d.metadata["source_file"] = filename

            splits = text_splitter.split_documents(docs)
            all_splits.extend(splits)

        except Exception as e:
            print(f"[ERROR] PDF 로딩 실패: {input_path}: {e}")

# html 불러오기 및 청크화
urls = ["https://www.npr.org/sections/health-shots/2023/09/19/1200223456/depression-anxiety-prevention-mental-health-healthy-habits"]
for url in urls:
    try:
        loader = UnstructuredURLLoader(
            urls=[url],
            mode="single",
            headers={"User-Agent": "Mozilla/5.0"},
        )
        docs = loader.load()
        splits = text_splitter.split_documents(docs)


        all_splits.extend(splits)

    except Exception as e:
        print(f"[ERROR] URL 로딩 실패: {url}: {e}")

print(f"총 청크 수: {len(all_splits)}")

# Embedding
load_dotenv("./Chain/.env")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
embeddings = OpenAIEmbeddings(model="text-embedding-3-large", api_key=OPENAI_API_KEY)
# test_vector_result = embeddings.embed_query("부정적인 감정일 때,  기분 개선에 효과적인 추천 행동은 뭐야?")
# print(test_vector_result)
# print(f"임베딩 벡터 차원 수: {len(test_vector_result)}")

# VectorDB
persist_directory = "./Chain/chroma_store"
if not os.path.exists(persist_directory):
    vectorstore = Chroma.from_documents(
        documents=all_splits, embedding=embeddings, persist_directory=persist_directory
    )
else:
    vectorstore = Chroma(
        embedding_function=embeddings, persist_directory=persist_directory
    )
print("저장된 벡터 개수:", vectorstore._collection.count())