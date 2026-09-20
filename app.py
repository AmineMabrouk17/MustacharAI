import streamlit as st
from dotenv import load_dotenv
from langchain_google_genai import GoogleGenerativeAIEmbeddings, ChatGoogleGenerativeAI
from langchain_community.vectorstores import Chroma
from langchain.chains import create_retrieval_chain
from langchain.chains.combine_documents import create_stuff_documents_chain
from langchain_core.prompts import ChatPromptTemplate

load_dotenv()

st.set_page_config(page_title="مساعد دستور 2022", page_icon="📜", layout="centered")

# Right-to-left layout styling for Arabic
st.markdown("""
    <style>
    .stTextInput > div > div > input { direction: rtl; text-align: right; }
    .stMarkdown { direction: rtl; text-align: right; }
    </style>
""", unsafe_allow_html=True)

st.title("📜 مساعد الدستور التونسي 2022")
st.caption("اسأل أي سؤال حول نصوص وفصول دستور 2022")


@st.cache_resource
def load_rag_chain():
    embeddings = GoogleGenerativeAIEmbeddings(model="models/text-embedding-004")
    db = Chroma(persist_directory="./chroma_db", embedding_function=embeddings)
    retriever = db.as_retriever(search_kwargs={"k": 4})

    llm = ChatGoogleGenerativeAI(
        model="gemini-1.5-flash",
        temperature=0.2
    )

    system_prompt = (
        "أنت مساعد قانوني ذكي وموضوعي.\n"
        "أجب عن سؤال المستخدم باللغة العربية بدقة بناءً على نصوص الدستور المرفقة فقط.\n"
        "إذا لم تكن الإجابة موجودة في النص، قل: 'المعلومة غير موجودة في دستور 2022 المرفق'.\n"
        "اذكر رقم الفصل إن وُجد في السياق.\n\n"
        "السياق:\n{context}"
    )

    prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt),
        ("human", "{input}"),
    ])

    question_answer_chain = create_stuff_documents_chain(llm, prompt)
    return create_retrieval_chain(retriever, question_answer_chain)


rag_chain = load_rag_chain()

# Session state for chat history
if "messages" not in st.session_state:
    st.session_state.messages = []

# Display conversation history
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# User Input
if user_prompt := st.chat_input("اكتب سؤالك هنا (مثلاً: ما هي شروط الترشح لرئاسة الجمهورية؟)..."):
    st.session_state.messages.append({"role": "user", "content": user_prompt})
    with st.chat_message("user"):
        st.markdown(user_prompt)

    with st.chat_message("assistant"):
        with st.spinner("جارٍ البحث في الدستور..."):
            response = rag_chain.invoke({"input": user_prompt})
            bot_reply = response["answer"]
            st.markdown(bot_reply)

    st.session_state.messages.append({"role": "assistant", "content": bot_reply})