import streamlit as st
import google.generativeai as genai
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
import sqlite3, json
from datetime import datetime
import speech_recognition as sr
import threading
import io
from gtts import gTTS # NEW: Import gTTS

# ================== CONFIG ==================
# IMPORTANT: Load API key from Streamlit secrets instead of hardcoding
try:
    genai.configure(api_key="AIzaSyB91V7EfZm2C7EAxa_9CZKfBJd5VkYDBVg")
except Exception:
    st.error("Error: GEMINI_API_KEY not found in Streamlit secrets. Please configure it.")
    st.stop()

model = genai.GenerativeModel("models/gemini-2.5-flash")
DB_NAME = "raya_chat.db"

# ================== DATABASE ==================
def init_db():
    """Initializes the SQLite database and the conversations table."""
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
    """Saves the current chat history to a new conversation record."""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    # Serialize chat history (message type and content) to JSON string
    serialized_history = json.dumps([(m.__class__.__name__, m.content) for m in chat_history])
    c.execute("INSERT INTO conversations (session_name, timestamp, history) VALUES (?, ?, ?)",
              (session_name, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), serialized_history))
    conn.commit(); conn.close()

def update_conversation(chat_id, chat_history):
    """Updates the chat history for an existing conversation."""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    serialized_history = json.dumps([(m.__class__.__name__, m.content) for m in chat_history])
    c.execute("UPDATE conversations SET history=?, timestamp=? WHERE id=?",
              (serialized_history, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), chat_id))
    conn.commit(); conn.close()

def load_conversations():
    """Loads a list of all saved conversation names and IDs."""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT id, session_name, timestamp FROM conversations ORDER BY id DESC")
    rows = c.fetchall(); conn.close(); return rows

def load_conversation_by_id(chat_id):
    """Loads the full chat history for a given conversation ID and restores message objects."""
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
    """Deletes a conversation record from the database."""
    conn = sqlite3.connect(DB_NAME); c = conn.cursor()
    c.execute("DELETE FROM conversations WHERE id=?", (chat_id,))
    conn.commit(); conn.close()

# Initialize database on app startup
init_db()

# ================== SPEECH SETUP ==================
# Only initialize SpeechRecognizer globally, pyttsx3 is removed
recognizer = sr.Recognizer()

def speak(text):
    """
    Converts text to speech using gTTS, saves it to an in-memory MP3,
    and plays it using st.audio(). This is Cloud-compatible.
    """
    try:
        # Generate speech
        tts = gTTS(text=text, lang='en')
        
        # Save to an in-memory binary stream
        mp3_fp = io.BytesIO()
        tts.write_to_fp(mp3_fp)
        mp3_fp.seek(0)
        
        # Display the audio player in Streamlit to play the sound
        st.audio(mp3_fp.read(), format='audio/mp3', autoplay=True)
        
    except Exception as e:
        # In a real app, this should probably log the error.
        st.toast(f"Voice generation error (gTTS): {e}", icon="⚠️")


def listen():
    """Listens for user input via microphone and converts it to text using Google Speech Recognition."""
    # Use a threading lock if this were called frequently, but for simplicity, 
    # Streamlit's single-thread model handles this well enough on button click.
    with sr.Microphone() as source:
        st.toast("🎙 Listening...", icon="🎧")
        # Adjust for ambient noise for better quality
        recognizer.adjust_for_ambient_noise(source, duration=0.5)
        try:
            # Listen for up to 6 seconds
            audio = recognizer.listen(source, phrase_time_limit=6)
            
            # Recognize speech
            query = recognizer.recognize_google(audio)
            st.toast(f"✅ You said: {query}", icon="💬")
            return query
        except sr.UnknownValueError:
            st.toast("⚠️ Sorry, I couldn’t hear properly.", icon="❌")
            return None
        except sr.RequestError as e:
            st.toast(f"⚠️ Speech Recognition service error: {e}", icon="❌")
            return None
        except Exception as e:
            st.toast(f"⚠️ An unexpected error occurred: {e}", icon="❌")
            return None

# ================== STREAMLIT UI ==================
st.set_page_config(page_title="Raya • AI Voice Assistant", page_icon="🎧", layout="wide")

# ---- Sidebar: Chat Management ----
st.sidebar.header("💾 Raya Chat History")
conversations = load_conversations()
selected_chat = None

# Logic to handle selecting or deleting chats
if conversations:
    chat_labels = [f"{name} ({time})" for _, name, time in conversations]
    
    # Pre-select the current session if it exists
    current_chat_id = st.session_state.get('chat_id')
    default_index = 0
    if current_chat_id:
        try:
            # Find the index of the currently loaded chat
            default_index = [c[0] for c in conversations].index(current_chat_id)
        except ValueError:
            default_index = 0 # Fallback if chat_id doesn't match list

    selected_label = st.sidebar.selectbox("Select a chat to open:", chat_labels, index=default_index)
    selected_chat_tuple = conversations[chat_labels.index(selected_label)]
    selected_chat = selected_chat_tuple[0]
    
    # Store the session name for display
    st.session_state.session_name = selected_chat_tuple[1]
else:
     st.session_state.session_name = "New Raya Session"

col1, col2 = st.sidebar.columns(2)
if col1.button("➕ New Chat"):
    new_name = f"Chat {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    # Start new chat with initial system message
    st.session_state.chat_history = [SystemMessage(content="Raya is ready to assist you.")]
    st.session_state.session_name = new_name
    
    # Create an initial entry in the database for the new chat
    save_conversation(new_name, st.session_state.chat_history)
    st.rerun()

if selected_chat and col2.button("🗑️ Delete"):
    # Delete the selected chat
    delete_conversation(selected_chat)
    st.sidebar.success("Chat deleted ✅")
    # Reset session state to force a clean start
    if st.session_state.get('chat_id') == selected_chat:
        del st.session_state['chat_history']
        del st.session_state['chat_id']
        del st.session_state['session_name']
    st.rerun()

# ---- Load selected chat or initialize new one ----
if selected_chat and st.session_state.get('chat_id') != selected_chat:
    # Load history if a different chat is selected in the sidebar
    st.session_state.chat_id = selected_chat
    st.session_state.chat_history = load_conversation_by_id(selected_chat)
elif "chat_history" not in st.session_state:
    # Initialize a clean session if no previous state exists
    st.session_state.chat_history = [SystemMessage(content="Raya initialized successfully.")]
    st.session_state.chat_id = None
    st.session_state.session_name = "New Raya Session"

# ---- CSS for layout ----
st.markdown("""
    <style>
        /* General page styling */
        body, .stApp {
            background-color: #0B0B0C;
            color: #E4E4E6;
            font-family: 'Inter', sans-serif;
        }
        /* Custom Chat Message Styling */
        .stChatMessage {
            border-radius: 14px;
            padding: 10px 16px;
            margin: 6px 0;
            max-width: 90%; /* Ensure it's not too wide */
        }
        .stChatMessage.user {
            background-color: #1A1A1D; /* Darker for user */
            text-align: right;
            margin-left: auto; /* Push user message to the right */
        }
        .stChatMessage.assistant {
            background-color: #111113; /* Slightly lighter for assistant */
            color: #AEE2FF;
            text-align: left;
            margin-right: auto; /* Keep assistant message to the left */
        }
        /* Hide default Streamlit elements */
        #MainMenu, header, footer {visibility: hidden;}
    </style>
""", unsafe_allow_html=True)

# ---- Main Chat Window ----
st.markdown(f"<h1 style='text-align:center; margin-top:15px;'>💬 {st.session_state.session_name}</h1>", unsafe_allow_html=True)
chat_container = st.container()

with chat_container:
    # Display chat history, skipping the SystemMessage
    for msg in st.session_state.chat_history:
        if isinstance(msg, HumanMessage):
            with st.chat_message("user"):
                st.markdown(msg.content)
        elif isinstance(msg, AIMessage):
            with st.chat_message("assistant"):
                st.markdown(msg.content)

# ---- Bottom input (persistent) ----
# Use an empty container to display audio without causing re-runs in the main block
audio_placeholder = st.empty() 

col1, col2 = st.columns([5, 1])
with col1:
    user_input = st.chat_input("Type your message or speak...", key="chat_input")

with col2:
    # Button to trigger speech recognition
    if st.button("🎤 Speak", use_container_width=True, key="speak_button"):
        spoken = listen()
        if spoken:
            # If spoken text is captured, inject it back into the chat input
            user_input = spoken

# ---- Chat Logic ----
if user_input:
    # 1. User message
    st.session_state.chat_history.append(HumanMessage(content=user_input))
    with st.chat_message("user"):
        st.markdown(user_input)

    # 2. Prepare prompt for Gemini
    prompt_text = "\n".join([
        f"{'User' if isinstance(m, HumanMessage) else 'Raya'}: {m.content}"
        for m in st.session_state.chat_history if not isinstance(m, SystemMessage)
    ])
    
    # 3. Generate response
    result = model.generate_content(prompt_text)
    response = result.text.strip()

    # 4. Assistant message
    st.session_state.chat_history.append(AIMessage(content=response))
    with st.chat_message("assistant"):
        st.markdown(response)
        
        # 5. Play the response using gTTS
        # IMPORTANT: We use the audio placeholder to display the audio player 
        # outside of the main chat loop to avoid display issues.
        with audio_placeholder:
             speak(response)

    # 6. Save/Update Conversation
    if st.session_state.chat_id:
        update_conversation(st.session_state.chat_id, st.session_state.chat_history)
    else:
        # Save new session if one was created
        save_conversation(st.session_state.session_name, st.session_state.chat_history)
        st.rerun() # Rerun to assign the new chat_id and update the sidebar
