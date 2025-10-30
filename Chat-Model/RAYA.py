import streamlit as st
import google.generativeai as genai
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
import sqlite3, json
from datetime import datetime
import speech_recognition as sr
from gtts import gTTS
import tempfile
import threading

# ================== CONFIG ==================
genai.configure(api_key="AIzaSyB91V7EfZm2C7EAxa_9CZKfBJd5VkYDBVg")
model = genai.GenerativeModel("models/gemini-2.5-flash")
DB_NAME = "raya_chat.db"

# ================== DATABASE ==================
def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS conversations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_name TEXT,
                    timestamp TEXT,
                    history TEXT
                )''')
    conn.commit(); conn.close()

def save_conversation(session_name, chat_history):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("INSERT INTO conversations (session_name, timestamp, history) VALUES (?, ?, ?)",
              (session_name, datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
               json.dumps([(m.__class__.__name__, m.content) for m in chat_history])))
    conn.commit(); conn.close()

def update_conversation(chat_id, chat_history):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("UPDATE conversations SET history=?, timestamp=? WHERE id=?",
              (json.dumps([(m.__class__.__name__, m.content) for m in chat_history]),
               datetime.now().strftime("%Y-%m-%d %H:%M:%S"), chat_id))
    conn.commit(); conn.close()

def load_conversations():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT id, session_name, timestamp FROM conversations ORDER BY id DESC")
    rows = c.fetchall(); conn.close(); return rows

def load_conversation_by_id(chat_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor(); c.execute("SELECT history FROM conversations WHERE id=?", (chat_id,))
    result = c.fetchone(); conn.close()
    if result:
        history = json.loads(result[0]); restored = []
        for role, text in history:
            if role == "SystemMessage": restored.append(SystemMessage(content=text))
            elif role == "HumanMessage": restored.append(HumanMessage(content=text))
            elif role == "AIMessage": restored.append(AIMessage(content=text))
        return restored
    return []

def delete_conversation(chat_id):
    conn = sqlite3.connect(DB_NAME); c = conn.cursor()
    c.execute("DELETE FROM conversations WHERE id=?", (chat_id,))
    conn.commit(); conn.close()

init_db()

# ================== SPEECH SETUP ==================
recognizer = sr.Recognizer()

import threading

def speak(text):
    try:
        tts = gTTS(text)
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as fp:
            tts.save(fp.name)
            st.audio(fp.name, format="audio/mp3", autoplay=True)
    except Exception as e:
        st.toast(f"Speech error: {e}", icon="⚠️")


def listen():
    with sr.Microphone() as source:
        st.toast("🎙 Listening...", icon="🎧")
        audio = recognizer.listen(source, phrase_time_limit=6)
        try:
            query = recognizer.recognize_google(audio)
            st.toast(f"✅ You said: {query}", icon="💬")
            return query
        except:
            st.toast("⚠️ Sorry, I couldn’t hear properly.", icon="❌")
            return None

# ================== STREAMLIT UI ==================
st.set_page_config(page_title="Raya • AI Voice Assistant", page_icon="🎧", layout="wide")

# ---- Sidebar: Chat Management ----
st.sidebar.header("💾 Raya Chat History")
conversations = load_conversations()
selected_chat = None

if conversations:
    chat_labels = [f"{name} ({time})" for _, name, time in conversations]
    selected_label = st.sidebar.selectbox("Select a chat to open:", chat_labels)
    selected_chat = conversations[chat_labels.index(selected_label)][0]

col1, col2 = st.sidebar.columns(2)
if col1.button("➕ New Chat"):
    new_name = f"Chat {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    st.session_state.chat_history = [SystemMessage(content="Raya is ready to assist you.")]
    st.session_state.session_name = new_name
    save_conversation(new_name, st.session_state.chat_history)
    st.rerun()

if selected_chat and col2.button("🗑️ Delete"):
    delete_conversation(selected_chat)
    st.sidebar.success("Chat deleted ✅")
    st.rerun()

# ---- Load selected chat ----
if selected_chat:
    st.session_state.chat_id = selected_chat
    st.session_state.chat_history = load_conversation_by_id(selected_chat)
else:
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = [SystemMessage(content="Raya initialized successfully.")]
        st.session_state.chat_id = None

# ---- CSS for layout ----
st.markdown("""
    <style>
        body, .stApp {
            background-color: #0B0B0C;
            color: #E4E4E6;
        }
        .stChatMessage {
            border-radius: 14px;
            padding: 10px 16px;
            margin: 6px 0;
        }
        .stChatMessage.user {
            background-color: #1A1A1D;
            text-align: right;
        }
        .stChatMessage.assistant {
            background-color: #111113;
            color: #AEE2FF;
        }
        #MainMenu, header, footer {visibility: hidden;}
    </style>
""", unsafe_allow_html=True)

# ---- Main Chat Window ----
st.markdown("<h1 style='text-align:center; margin-top:15px;'>💬 Raya — Your Voice AI Companion</h1>", unsafe_allow_html=True)
chat_container = st.container()

with chat_container:
    for msg in st.session_state.chat_history:
        if isinstance(msg, HumanMessage):
            with st.chat_message("user"):
                st.markdown(msg.content)
        elif isinstance(msg, AIMessage):
            with st.chat_message("assistant"):
                st.markdown(msg.content)

# ---- Bottom input (persistent) ----
col1, col2 = st.columns([5, 1])
with col1:
    user_input = st.chat_input("Type your message or speak...")

with col2:
    if st.button("🎤 Speak", use_container_width=True):
        spoken = listen()
        if spoken:
            user_input = spoken

# ---- Chat Logic ----
if user_input:
    st.session_state.chat_history.append(HumanMessage(content=user_input))
    with st.chat_message("user"):
        st.markdown(user_input)

    prompt_text = "\n".join([
        f"{'User' if isinstance(m, HumanMessage) else 'Raya'}: {m.content}"
        for m in st.session_state.chat_history if not isinstance(m, SystemMessage)
    ])
    result = model.generate_content(prompt_text)
    response = result.text.strip()

    st.session_state.chat_history.append(AIMessage(content=response))
    with st.chat_message("assistant"):
        st.markdown(response)
        speak(response)

    if st.session_state.chat_id:
        update_conversation(st.session_state.chat_id, st.session_state.chat_history)
    else:
        save_conversation("Raya Session", st.session_state.chat_history)

