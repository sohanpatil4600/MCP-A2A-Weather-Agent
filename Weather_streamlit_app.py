import streamlit as st
import asyncio
import os
import io
import traceback
import nest_asyncio
import json
import datetime
import base64
import time
from dotenv import load_dotenv
from langchain_groq import ChatGroq
from mcp_use import MCPAgent, MCPClient
from streamlit_mic_recorder import mic_recorder
import speech_recognition as sr
from server.a2a_protocol import SQLiteA2AIdempotencyStore, build_handoff
from server.resilience import ResilienceContext, CircuitBreakerConfig
from server.observability import ObservabilityContext, StructuredEvent, TraceContext

# Windows specific event loop policy
if os.name == 'nt':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

# Apply nest_asyncio
nest_asyncio.apply()

# Load environment variables
load_dotenv()

# Page configuration
st.set_page_config(
    page_title="Weather Agent Pro",
    page_icon="🌤️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for premium design
st.markdown("""
<style>
    /* Enhanced Multi-Color Theme */
    :root {
        --primary-gold: #FFD700;
        --secondary-gold: #FFC800;
        --accent-blue: #2874f0;
        --accent-green: #2ecc71;
        --accent-orange: #ff9f43;
        --accent-purple: #9b59b6;
        --accent-cyan: #00d4ff;
        --background-dark: #141E30; 
        --card-bg: rgba(36, 59, 85, 0.6); 
        --text-light: #ecf0f1; 
        --text-dim: #bdc3c7;   
        --hover-glow: rgba(46, 204, 113, 0.6);
    }
    
    .stApp {
        background: linear-gradient(to right, #141E30, #243B55);
        color: var(--text-light);
        font-family: 'Inter', sans-serif;
    }

    strong, b {
        color: var(--primary-gold);
        font-weight: 700;
    }
    
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #0f172a 0%, #1e293b 100%);
        border-right: 3px solid var(--accent-green);
    }

    h1 { color: var(--accent-cyan) !important; text-shadow: 0 0 40px rgba(0, 212, 255, 0.6); }
    h2 { color: var(--accent-blue) !important; }
    h3 { color: var(--accent-green) !important; }
    
    .stCard {
        background: linear-gradient(135deg, rgba(26, 31, 46, 0.9) 0%, rgba(37, 43, 59, 0.9) 100%);
        border-radius: 15px;
        padding: 20px;
        box-shadow: 0 8px 32px rgba(40, 116, 240, 0.2);
        border: 2px solid rgba(40, 116, 240, 0.3);
    }
    
    .stButton>button {
        background: linear-gradient(135deg, var(--accent-blue) 0%, var(--accent-purple) 100%);
        color: #ffffff;
        border-radius: 25px;
        font-weight: 700;
        transition: all 0.3s;
    }
    .stButton>button:hover {
        transform: translateY(-3px);
        box-shadow: 0 8px 30px rgba(155, 89, 182, 0.6);
    }

    /* Chat Styling */
    .user-message {
        background: linear-gradient(135deg, var(--accent-blue) 0%, var(--accent-cyan) 100%);
        padding: 15px; border-radius: 15px; margin: 10px 0 10px 20%; color: white;
    }
    .bot-message {
        background: linear-gradient(135deg, rgba(26, 31, 46, 0.95) 0%, rgba(42, 49, 66, 0.95) 100%);
        padding: 15px; border-radius: 15px; margin: 10px 20% 10px 0; border: 1px solid var(--accent-green); color: white;
    }
    
    /* Tech Card Styling */
    .tech-card {
        background: rgba(30, 41, 59, 0.4);
        border-radius: 15px;
        padding: 25px;
        border: 1px solid rgba(255, 255, 255, 0.1);
        transition: all 0.3s ease;
        height: 100%;
        cursor: default;
    }
    .tech-card:hover {
        transform: translateY(-5px);
        background: rgba(30, 41, 59, 0.6);
        border: 1px solid #00d4ff;
        box-shadow: 0 10px 25px rgba(0, 212, 255, 0.2);
    }
    .tech-icon {
        font-size: 2rem;
        margin-bottom: 15px;
        display: block;
    }
    .tech-tag {
        display: inline-block;
        padding: 4px 12px;
        border-radius: 20px;
        font-size: 0.75rem;
        font-weight: 700;
        margin-top: 10px;
        text-transform: uppercase;
    }
</style>
""", unsafe_allow_html=True)

# --- Session State Initialization ---
if "messages" not in st.session_state:
    st.session_state.messages = []
if "logs" not in st.session_state:
    st.session_state.logs = []
if "a2a_idempotency_store" not in st.session_state:
    st.session_state.a2a_idempotency_store = SQLiteA2AIdempotencyStore(
        db_path="Weather result/a2a_idempotency.db"
    )
if "resilience_context" not in st.session_state:
    st.session_state.resilience_context = ResilienceContext()
if "observability_context" not in st.session_state:
    st.session_state.observability_context = ObservabilityContext()



def safe_image(path, caption=None, width="stretch"):
    try:
        from PIL import Image
        # Verify it's a valid image
        Image.open(path).verify()
        st.image(path, caption=caption, width=width)
    except Exception:
        # If it's a git lfs pointer or missing
        st.info(f"🖼️ [Image Placeholder for {path}]")

def add_log(message, type="info"):
    # Streamlit Cloud uses UTC by default. Adding 5:30 for IST.
    from datetime import datetime as dt, timedelta, timezone
    ist_cutoff = timedelta(hours=5, minutes=30)
    timestamp = (dt.now(timezone.utc) + ist_cutoff).strftime("%H:%M:%S")
    
    # Process protocol messages for better formatting
    if type == "PROTOCOL":
        try:
            # Try to prettify JSON if it's a protocol message
            if "{" in message:
                import json
                start_idx = message.find("{")
                end_idx = message.rfind("}") + 1
                json_part = message[start_idx:end_idx]
                parsed = json.loads(json_part)
                message = message[:start_idx] + json.dumps(parsed, indent=2)
        except:
            pass

    st.session_state.logs.append({"time": timestamp, "msg": message, "type": type})

# --- Helper Functions ---
def transcribe_audio(audio_bytes):
    r = sr.Recognizer()
    try:
        audio_file = io.BytesIO(audio_bytes)
        with sr.AudioFile(audio_file) as source:
            audio_data = r.record(source)
            text = r.recognize_google(audio_data)
            return text
    except sr.UnknownValueError:
        return "Error: Could not understand audio (Speech was unintelligible)"
    except sr.RequestError as e:
        return f"Error: API connection failed; {e}"
    except Exception as e:
        # Fallback for other errors (e.g., file format issues)
        err_msg = str(e) if str(e) else repr(e)
        return f"Error transcribing: {err_msg}"

def get_agent(model_name="llama-3.3-70b-versatile", callbacks=None):
    config_file = "server/weather.json"
    client = MCPClient.from_config_file(config_file)
    llm = ChatGroq(model=model_name, streaming=True, callbacks=callbacks)
    agent = MCPAgent(
        llm=llm,
        client=client,
        max_steps=10,
        memory_enabled=True,
    )
    return agent


def run_async_isolated(coro):
    """Run a coroutine in an isolated event loop and clean up pending tasks."""
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(coro)

        pending = [task for task in asyncio.all_tasks(loop) if not task.done()]
        for task in pending:
            task.cancel()

        if pending:
            loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))

        loop.run_until_complete(loop.shutdown_asyncgens())
        if hasattr(loop, "shutdown_default_executor"):
            loop.run_until_complete(loop.shutdown_default_executor())

        return result
    finally:
        asyncio.set_event_loop(None)
        loop.close()

# No global agent. MCP Subprocess must be bound to a localized asyncio Event Loop during query phase.

# --- Sidebar ---
with st.sidebar:
    st.markdown("""
    <div style='background: #ffffff; padding: 20px; border-radius: 10px; text-align: center; border: 2px solid #2874f0;'>
        <h2 style='color: #2874f0; margin: 0;'>🌤️ Weather Agent</h2>
        <p style='color: #666; font-size: 0.9rem; font-weight: bold;'>MCP-POWERED PRO</p>
    </div>
    """, unsafe_allow_html=True)
    
    st.markdown("---")
    st.markdown("### 👨‍💻 Developer")
    st.markdown("""
    <div style='background: linear-gradient(135deg, rgba(155, 89, 182, 0.2) 0%, rgba(40, 116, 240, 0.2) 100%); 
                padding: 15px; border-radius: 10px; border: 2px solid rgba(155, 89, 182, 0.4);'>
        <p style='margin: 5px 0; color: #00d4ff; font-weight: 600;'>Sohan Patil</p>
        <p style='margin: 5px 0; font-size: 0.9rem;'>
            🔗 <a href='https://github.com/sohanpatil4600' style='color: #2874f0; text-decoration: none;'>GitHub</a> | 
            <a href='https://www.linkedin.com/in/sohanrpatil/' style='color: #9b59b6; text-decoration: none;'>LinkedIn</a>
        </p>
    </div>
    """, unsafe_allow_html=True)
    
    st.markdown("### 🔍 Project Info")
    st.info(
        "Agentic AI application powered by **MCP (Model Context Protocol)**. "
        "Connects Llama 3 to real-time tools without hardcoded API logic."
    )

# --- Top Right Professional Badge ---
col1, col2 = st.columns([3, 1])

with col1:
    st.markdown("") # Spacer

with col2:
    st.markdown("""
    <div style='background: linear-gradient(135deg, #2874f0 0%, #9b59b6 100%); 
                padding: 8px 12px; border-radius: 6px; 
                box-shadow: 0 2px 8px rgba(40, 116, 240, 0.4);
                border: 1px solid rgba(155, 89, 182, 0.3);
                text-align: center;
                margin-bottom: 10px;'>
        <p style='margin: 0; color: #ffffff; font-weight: 700; font-size: 0.7rem; line-height: 1.5;'>
            <strong>Sohan Patil</strong><br>
            Data Scientist (AI/ML) | 4+ Yrs
        </p>
        <div style='margin-top: 5px; font-size: 0.7rem; display: flex; align-items: center; justify-content: center; gap: 10px;'>
            <a href='https://github.com/sohanpatil4600' target='_blank' style='color: #ecf0f1; text-decoration: none; font-weight: 600; display: flex; align-items: center; gap: 4px;'>
                <img src="https://img.icons8.com/ios-filled/50/ffffff/github.png" width="14" height="14" style="vertical-align: middle;"> GitHub
            </a>
            <span style='color: rgba(255,255,255,0.5);'>|</span>
            <a href='https://www.linkedin.com/in/sohanrpatil/' target='_blank' style='color: #ecf0f1; text-decoration: none; font-weight: 600; display: flex; align-items: center; gap: 4px;'>
                <img src="https://img.icons8.com/ios-filled/50/ffffff/linkedin.png" width="14" height="14" style="vertical-align: middle;"> LinkedIn
            </a>
        </div>
    </div>
    """, unsafe_allow_html=True)

# --- Main Header ---
st.markdown("""
<div style='text-align: center; padding: 15px; background: linear-gradient(135deg, rgba(40, 116, 240, 0.15) 0%, rgba(155, 89, 182, 0.15) 100%); border-radius: 12px; margin-bottom: 15px; border: 2px solid rgba(40, 116, 240, 0.4);'>
<div style='display: flex; align-items: center; justify-content: center; gap: 15px; margin-bottom: 8px; flex-wrap: wrap;'>
<h1 style='color: #00d4ff; margin: 0; font-size: 1.8rem; font-weight: 800; text-shadow: 0 0 15px rgba(0, 212, 255, 0.5); letter-spacing: 1px; line-height: 1;'>
WEATHER MCP AGENT 
</h1>
</div>
<p style='font-size: 1.0rem; color: #e8e8e8; font-weight: 500; margin: 0; letter-spacing: 0.5px;'>
🌤️ Real-time Weather Intelligence powered by MCP & Groq
</p>
</div>
""", unsafe_allow_html=True)

# Tabs
tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8 = st.tabs([
    "🚀 Project Demo", 
    "ℹ️ About Project", 
    "🛠️ Tech Stack", 
    "🏗️ Architecture", 
    "📋 System Logs",
    "⚡ Resilience Hub",
    "🔒 Security Audit",
    "📊 Observability"
])

# --- Tab 1: Project Demo ---
with tab1:
    st.markdown("""
    <div style='background: linear-gradient(135deg, rgba(40, 116, 240, 0.1) 0%, rgba(155, 89, 182, 0.1) 100%); 
                padding: 15px; border-radius: 12px; border: 1px solid rgba(40, 116, 240, 0.2); margin-bottom: 20px;
                border-left: 5px solid #00d4ff;'>
        <h3 style='color: #00d4ff; margin: 0 0 5px 0;'>💬 Interactive Sohan AI Weather Agent</h3>
        <p style='color: #e8e8e8; margin: 0; font-size: 0.95rem;'>
            Ask about the weather, forecasts, or alerts. Use text or voice! 
            The agent uses <b>MCP Tools</b> to fetch live data from the National Weather Service.
        </p>
    </div>
    """, unsafe_allow_html=True)
    
    # Quick Action Buttons
    st.markdown("### ⚡ Quick Weather Checks")
    q1, q2, q3, q4 = st.columns(4)
    
    if q1.button("🗽 NY Weather", width="stretch"):
         st.session_state.messages.append({"role": "user", "content": "What is the current weather in New York?"})
         st.rerun()
         
    if q2.button("🌧️ London Rain?", width="stretch"):
         st.session_state.messages.append({"role": "user", "content": "Is it going to rain in London today?"})
         st.rerun()
         
    if q3.button("🇯🇵 Tokyo Forecast", width="stretch"):
         st.session_state.messages.append({"role": "user", "content": "Give me a 3-day forecast for Tokyo."})
         st.rerun()
         
    if q4.button("⚠️ US Alerts", width="stretch"):
         st.session_state.messages.append({"role": "user", "content": "Are there any severe weather alerts in California right now?"})
         st.rerun()

    # Row 2
    q5, q6, q7, q8 = st.columns(4)
    if q5.button("🌅 Paris Sunrise", width="stretch"):
         st.session_state.messages.append({"role": "user", "content": "When is sunrise in Paris tomorrow?"})
         st.rerun()
    
    if q6.button("💨 Chicago Wind", width="stretch"):
         st.session_state.messages.append({"role": "user", "content": "What is the current wind speed in Chicago?"})
         st.rerun()
         
    if q7.button("🌡️ Dubai Temp", width="stretch"):
         st.session_state.messages.append({"role": "user", "content": "What is the current temperature in Dubai?"})
         st.rerun()
         
    if q8.button("☔ Mumbai Rain", width="stretch"):
         st.session_state.messages.append({"role": "user", "content": "Is it raining in Mumbai right now?"})
         st.rerun()

    # Row 3 (Indian Cities)
    q9, q10, q11, q12 = st.columns(4)
    if q9.button("🌫️ Delhi Weather", width="stretch"):
         st.session_state.messages.append({"role": "user", "content": "What is the current weather in New Delhi?"})
         st.rerun()
    
    if q10.button("💻 Bangalore Temp", width="stretch"):
         st.session_state.messages.append({"role": "user", "content": "What is the current temperature in Bangalore?"})
         st.rerun()
         
    if q11.button("🌊 Chennai Rain", width="stretch"):
         st.session_state.messages.append({"role": "user", "content": "Is it raining in Chennai right now?"})
         st.rerun()
         
    if q12.button("🏰 Hyderabad Cast", width="stretch"):
         st.session_state.messages.append({"role": "user", "content": "Give me a weather forecast for Hyderabad, India."})
         st.rerun()

    # Row 4 (Global Mix)
    q13, q14, q15, q16 = st.columns(4)
    if q13.button("🐨 Sydney Sun", width="stretch"):
         st.session_state.messages.append({"role": "user", "content": "Is it sunny in Sydney right now?"})
         st.rerun()
    
    if q14.button("🍁 Toronto Snow", width="stretch"):
         st.session_state.messages.append({"role": "user", "content": "Is it snowing in Toronto?"})
         st.rerun()
         
    if q15.button("🦁 Singapore Humid", width="stretch"):
         st.session_state.messages.append({"role": "user", "content": "What is the humidity in Singapore?"})
         st.rerun()
         
    if q16.button("🐻 Berlin Temp", width="stretch"):
         st.session_state.messages.append({"role": "user", "content": "What is the current temperature in Berlin?"})
         st.rerun()

    # Weather Visuals Gallery
    st.markdown("### 📸 Weather Landscapes")
    g1, g2, g3, g4 = st.columns(4)
    with g1:
        safe_image("assets/snow_winter.png", caption="Snowy Winter", width="stretch")
    with g2:
        safe_image("assets/rain_storm.png", caption="Rainy Cloud", width="stretch")
    with g3:
        safe_image("assets/green_hills.png", caption="Green Hills", width="stretch")
    with g4:
        safe_image("assets/sea_beach.png", caption="Sea Water", width="stretch")

    # Model Selection & Header in one row
    st.markdown("---")
    header_col, text_col, model_col = st.columns([2, 0.8, 1.2])
    
    with header_col:
        st.markdown("### 💬 Conversation Output")

    with text_col:
        st.markdown("<div style='text-align: right; padding-top: 10px; font-weight: 600; color: #00ff41;'>Select Model:</div>", unsafe_allow_html=True)
        
    with model_col:
         selected_model = st.selectbox(
             "🤖 Select Intelligence Model",
             ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "mixtral-8x7b-32768", "gemma2-9b-it"],
             index=0,
             label_visibility="collapsed",
             help="Choose the brain powering the agent."
         )
    
    # Add helpful note about model reliability
    st.markdown("<p style='font-size: 0.8rem; color: #94a3b8; margin-top: -10px;'>💡 <strong>llama-3.3-70b-versatile</strong> is most reliable for weather queries</p>", unsafe_allow_html=True)
    
    # Handle Model Switch
    if "current_model" not in st.session_state:
        st.session_state.current_model = "llama-3.3-70b-versatile"
        
    if st.session_state.current_model != selected_model:
        with st.spinner(f"Switching to {selected_model}..."):
            try:
                st.session_state.agent = get_agent(selected_model)
                st.session_state.current_model = selected_model
                add_log(f"Switched model to {selected_model}", "INFO")
                # st.success(f"Switched to {selected_model}!") # Optional toast
            except Exception as e:
                st.error(f"Failed to switch model: {e}")
    chat_container = st.container(height=400)
    with chat_container:
        if not st.session_state.messages:
             st.markdown("""
             <div style='text-align: center; color: #94a3b8; padding: 40px; border: 2px dashed #334155; border-radius: 10px;'>
                <h4 style='color: #60a5fa;'>👋 Ready to Assist!</h4>
                <p>Your conversation with the AI Weather Agent will appear in this box.<br>
                Try asking a question or clicking a quick button above.</p>
             </div>
             """, unsafe_allow_html=True)

        for i, message in enumerate(st.session_state.messages):
            role_class = "user-message" if message["role"] == "user" else "bot-message"
            role_icon = "👤" if message["role"] == "user" else "🤖"
            display_name = "SohanAI Weather Agent" if message["role"] == "assistant" else "You"
            
            # Display Message with proper HTML escaping
            st.markdown(f"""
            <div class='{role_class}'>
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 5px;">
                    <strong>{role_icon} {display_name}</strong>
                </div>
            </div>
            """, unsafe_allow_html=True)
            
            # Display content separately to avoid HTML issues
            st.markdown(message['content'])
            
            # Add Feedback & Copy Options for Assistant Messages
            if message["role"] == "assistant":
                col_fb1, col_fb2, col_copy, col_space = st.columns([0.08, 0.08, 0.2, 0.64])
                with col_fb1:
                    if st.button("👍", key=f"thumb_up_{i}", help="Positive Feedback"):
                        st.toast("Thank you for the positive feedback! 👍")
                with col_fb2:
                    if st.button("👎", key=f"thumb_down_{i}", help="Negative Feedback"):
                        st.toast("Feedback recorded. We'll improve! 👎")
                with col_copy:
                    with st.expander("📋 Copy", expanded=False):
                        st.code(message['content'], language="markdown")

    # --- Main Interaction Area ---
    
    # 1. Input Form (Placed Above Controls)
    prompt = None
    
    with st.container():
        with st.form(key='query_form', clear_on_submit=True):
            col_input, col_btn_enter, col_btn_stop = st.columns([6, 1.5, 1.5])
            with col_input:
                custom_input = st.text_input("Query", placeholder="Ask me about the weather...", label_visibility="collapsed", key="widget_query")
            with col_btn_enter:
                submitted = st.form_submit_button("🚀 Enter", width="stretch")
            with col_btn_stop:
                stopped = st.form_submit_button("⏹️ Stop", width="stretch")
    
    if stopped:
        st.session_state.messages = st.session_state.messages # Keep state
        st.rerun() # Just rerun to stop any active processing
    
    if submitted and custom_input:
        prompt = custom_input

    # 2. Control Buttons (Voice, Save, Clear, Reset)
    st.markdown("---")
    input_container = st.container()
    voice_prompt = None

    with input_container:
        # Create 4 columns for all controls
        col_mic, col_export, col_clear, col_reset = st.columns(4)
        
        with col_mic:
            st.write("🎤 **Voice:**")
            audio = mic_recorder(
                start_prompt="Record", stop_prompt="Stop", key='recorder', format="wav", use_container_width=True
            )
            st.markdown("<p style='color: #ff4b4b; font-size: 0.8rem; font-weight: bold; margin-top: 5px;'>⚠️ Requires mic permissions. If error, speak clearly & closely.</p>", unsafe_allow_html=True)

        with col_export:
            st.write("💾 **Save:**")
            
            # Prepare JSON format
            chat_history_json = json.dumps(st.session_state.messages, indent=2)
            
            # Prepare TXT format
            chat_history_txt = "=" * 60 + "\n"
            chat_history_txt += "WEATHER CHAT HISTORY\n"
            chat_history_txt += "=" * 60 + "\n\n"
            for i, msg in enumerate(st.session_state.messages, 1):
                role = "YOU" if msg["role"] == "user" else "SOHAN AI WEATHER AGENT"
                chat_history_txt += f"[{i}] {role}:\n"
                chat_history_txt += f"{msg['content']}\n"
                chat_history_txt += "-" * 60 + "\n\n"
            
            # Two download buttons in sub-columns
            exp_col1, exp_col2 = st.columns(2)
            with exp_col1:
                st.download_button(
                    label="📥 JSON",
                    data=chat_history_json,
                    file_name="weather_chat_history.json",
                    mime="application/json",
                    width="stretch"
                )
            with exp_col2:
                st.download_button(
                    label="📄 TXT",
                    data=chat_history_txt,
                    file_name="weather_chat_history.txt",
                    mime="text/plain",
                    width="stretch"
                )
            
        with col_clear:
            st.write("🧹 **Clear:**")
            if st.button("Clear Chat", width="stretch"):
                st.session_state.messages = []
                add_log("Chat history cleared", "INFO")
                st.rerun()

        with col_reset:
            st.write("🔄 **Reset:**")
            if st.button("Reset System", width="stretch"):
                del st.session_state.agent
                st.session_state.logs = []
                add_log("System reset initiated", "WARNING")
                st.rerun()

        if audio:
            if "last_audio_id" not in st.session_state or st.session_state.last_audio_id != audio['id']:
                st.session_state.last_audio_id = audio['id']
                transcribed_text = transcribe_audio(audio['bytes'])
                if transcribed_text and not transcribed_text.startswith("Error"):
                    voice_prompt = transcribed_text
                    add_log(f"Voice captured: {voice_prompt}", "INFO")
                elif transcribed_text:
                    st.warning(transcribed_text)
    
    # Handle Voice Input Override
    if voice_prompt and not prompt:
        prompt = voice_prompt

    # Process Query
    if prompt:
        st.session_state.messages.append({"role": "user", "content": prompt})
        add_log(f"User Query: {prompt}", "INFO")
        st.rerun()

    # Process response if last message is user
    if st.session_state.messages and st.session_state.messages[-1]["role"] == "user":
        with chat_container: # Show spinner in the chat window area
             with st.status("✨ SohanAI is doing its magic...", expanded=False) as status:
                try:
                    current_model = st.session_state.get("current_model", "llama-3.3-70b-versatile")
                    prompt_content = st.session_state.messages[-1]["content"]
                    st.toast("🔌 Processing with MCP Agent...", icon="🌩️")
                    
                    import logging
                    class UILogHandler(logging.Handler):
                        def emit(self, record):
                            msg = self.format(record)
                            if "🔧 Tool call:" in msg:
                                st.toast(msg, icon="🔧")
                                add_log(msg, "INFO")
                                
                                # Simulate Protocol Layer JSON-RPC Request
                                try:
                                    import json
                                    tool_name = msg.split("🔧 Tool call: '")[1].split("'")[0]
                                    args = msg.split("with args ")[1]
                                    rpc_req = {
                                        "jsonrpc": "2.0",
                                        "method": f"tools/call/{tool_name}",
                                        "params": json.loads(args),
                                        "id": id(msg) % 1000
                                    }
                                    add_log(f"📡 SENT JSON-RPC REQUEST:\n{json.dumps(rpc_req)}", "PROTOCOL")
                                except: pass
                                
                            elif "📄 Tool result:" in msg:
                                add_log(msg[:200] + ("..." if len(msg) > 200 else ""), "SUCCESS")
                                
                                # Simulate Protocol Layer JSON-RPC Response
                                try:
                                    import json
                                    result_content = msg.split("📄 Tool result: ")[1]
                                    rpc_res = {
                                        "jsonrpc": "2.0",
                                        "result": result_content[:500], # Trucated for log readability
                                        "id": "match_request_id"
                                    }
                                    add_log(f"📥 RCVD JSON-RPC RESPONSE:\n{json.dumps(rpc_res)}", "PROTOCOL")
                                except: pass
                    
                    ui_handler = UILogHandler()
                    mcp_logger = logging.getLogger("mcp_use")
                    mcp_logger.setLevel(logging.INFO)
                    mcp_logger.addHandler(ui_handler)
                    
                    try:
                        from langchain_core.messages import HumanMessage, AIMessage
                        chat_history = []
                        for msg in st.session_state.messages[:-1]:
                            if msg["role"] == "user":
                                chat_history.append(HumanMessage(content=msg["content"]))
                            else:
                                chat_history.append(AIMessage(content=msg["content"]))
                                
                        from langchain_core.callbacks import AsyncCallbackHandler
                        
                        st.markdown("### 🧠 Agent Network Activity")
                        agent_card_col1, agent_card_col2 = st.columns(2)
                        with agent_card_col1:
                            supervisor_card = st.empty()
                            supervisor_card.info("👤 **Supervisor Agent**: Standby...")
                        with agent_card_col2:
                            specialist_card = st.empty()
                            specialist_card.warning("🌩️ **Weather Specialist**: Sleeping")
                        
                        stream_placeholder = st.empty()
                        
                        import sys
                        
                        class UIStreamHandler(AsyncCallbackHandler):
                            def __init__(self, placeholder):
                                self.placeholder = placeholder
                                self.text = ""
                                
                            async def on_llm_start(self, *args, **kwargs) -> None:
                                print("\n[STREAM START]", flush=True)
                                
                            async def on_llm_new_token(self, token: str, **kwargs) -> None:
                                print(f"[{token}]", end="", flush=True)  # Print each token wrapped in brackets
                                self.text += token
                                self.placeholder.markdown(f"""
                                <div class='bot-message' style='border-color: #00d4ff;'>
                                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 5px;">
                                        <strong>👤 Supervisor Agent</strong>
                                        <span style="font-size:0.7rem;color:#00d4ff;">✨ Synthesizing...</span>
                                    </div>
                                    {self.text}▌
                                </div>
                                """, unsafe_allow_html=True)
                                
                            async def on_llm_end(self, *args, **kwargs) -> None:
                                print("\n[STREAM END]", flush=True)
                                
                        stream_handler = UIStreamHandler(stream_placeholder)

                        async def run_loop_safe():
                            from langchain.agents import create_agent
                            from langchain_core.messages import HumanMessage
                            from langchain_core.tools import tool
                            import asyncio as aio
                            
                            @tool("ask_weather_specialist")
                            async def ask_weather_specialist(query: str) -> str:
                                """Delegate tasks directly to the Weather Specialist Agent."""
                                handoff = build_handoff(
                                    query=query,
                                    target_agent="weather-specialist",
                                    deadline_ms=15000,
                                    idempotency_seed=f"{current_model}:{query.strip().lower()}",
                                )
                                add_log(f"A2A_HANDOFF: {handoff.to_json()}", "PROTOCOL")

                                idempotency_store = st.session_state.a2a_idempotency_store
                                if idempotency_store.has(handoff.idempotency_key):
                                    cached = idempotency_store.get(handoff.idempotency_key)
                                    add_log(
                                        f"A2A_DEDUPE_HIT: trace_id={handoff.trace_id} key={handoff.idempotency_key}",
                                        "PROTOCOL",
                                    )
                                    return cached or ""

                                if handoff.is_expired():
                                    return (
                                        f"A2A deadline exceeded before execution "
                                        f"(trace_id={handoff.trace_id}, task_id={handoff.task_id})."
                                    )

                                supervisor_card.info("👤 **Supervisor Agent**: Waiting for Specialist...")
                                specialist_card.warning("🌩️ **Weather Specialist**: Extracting MCP Data...")
                                
                                remaining_seconds = handoff.remaining_seconds()
                                if remaining_seconds <= 0:
                                    add_log(
                                        (
                                            "A2A_TIMEOUT: "
                                            f"trace_id={handoff.trace_id} task_id={handoff.task_id} "
                                            "reason=deadline_exceeded_before_execution"
                                        ),
                                        "PROTOCOL",
                                    )
                                    return "A2A deadline exceeded before specialist execution."

                                resilience_ctx = st.session_state.resilience_context
                                breaker = resilience_ctx.get_breaker(
                                    "weather-specialist",
                                    CircuitBreakerConfig(failure_threshold=5, recovery_timeout_s=60),
                                )

                                obs_ctx = st.session_state.observability_context
                                start_time = time.time()
                                span_ctx = TraceContext(
                                    trace_id=handoff.trace_id,
                                    span_id=f"specialist-{handoff.task_id}",
                                    parent_span_id=obs_ctx.current_trace.span_id,
                                    correlation_id=obs_ctx.current_trace.correlation_id,
                                )

                                # Emit handoff creation event
                                obs_ctx.emit_event(StructuredEvent(
                                    event_type="a2a.handoff.created",
                                    trace_context=span_ctx,
                                    attributes={
                                        "task_id": handoff.task_id,
                                        "idempotency_key": handoff.idempotency_key[:12],
                                        "deadline_ms": handoff.deadline_ms,
                                        "query_length": len(query)
                                    }
                                ))
                                
                                # Increment A2A handoff counter for observability
                                obs_ctx.metrics.increment_counter("a2a_handoffs")

                                def on_retry_event(attempt: int, exc: Exception) -> None:
                                    elapsed_s = time.time() - start_time
                                    add_log(
                                        (
                                            "A2A_RETRY: "
                                            f"trace_id={handoff.trace_id} task_id={handoff.task_id} "
                                            f"attempt={attempt} error={type(exc).__name__} elapsed={elapsed_s:.2f}s"
                                        ),
                                        "PROTOCOL",
                                    )
                                    obs_ctx.emit_event(StructuredEvent(
                                        event_type="a2a.retry",
                                        trace_context=span_ctx,
                                        latency_ms=int(elapsed_s * 1000),
                                        error_code="RETRY",
                                        attributes={
                                            "attempt": attempt,
                                            "error_type": type(exc).__name__,
                                            "error_message": str(exc)
                                        }
                                    ))

                                def on_failure_event(exc: Exception) -> None:
                                    elapsed_s = time.time() - start_time
                                    add_log(
                                        (
                                            "A2A_FAILURE: "
                                            f"trace_id={handoff.trace_id} task_id={handoff.task_id} "
                                            f"breaker_state={breaker.metrics.state.value} "
                                            f"error={type(exc).__name__} elapsed={elapsed_s:.2f}s"
                                        ),
                                        "PROTOCOL",
                                    )
                                    obs_ctx.emit_event(StructuredEvent(
                                        event_type="a2a.failure",
                                        trace_context=span_ctx,
                                        latency_ms=int(elapsed_s * 1000),
                                        error_code="FAILURE",
                                        attributes={
                                            "breaker_state": breaker.metrics.state.value,
                                            "error_type": type(exc).__name__,
                                            "error_message": str(exc)
                                        }
                                    ))

                                try:
                                    specialist = get_agent(current_model)
                                    try:
                                        result = await resilience_ctx.execute_with_resilience(
                                            call_name="weather-specialist",
                                            coro_fn=lambda: specialist.run(query),
                                            timeout_s=remaining_seconds,
                                            on_retry=on_retry_event,
                                            on_failure=on_failure_event,
                                        )
                                        elapsed_s = time.time() - start_time
                                        idempotency_store.set(handoff.idempotency_key, result)
                                        
                                        # Emit completion event with latency metrics
                                        obs_ctx.emit_event(StructuredEvent(
                                            event_type="a2a.completion",
                                            trace_context=span_ctx,
                                            latency_ms=int(elapsed_s * 1000),
                                            attributes={
                                                "task_id": handoff.task_id,
                                                "idempotency_key": handoff.idempotency_key[:12],
                                                "result_length": len(str(result))
                                            }
                                        ))
                                        obs_ctx.metrics.record_latency("weather-specialist", int(elapsed_s * 1000))
                                        obs_ctx.metrics.record_success()
                                        obs_ctx.metrics.increment_counter("tool_calls")  # Track tool calls for observability
                                        
                                        specialist_card.success("🌩️ **Weather Specialist**: Task Complete!")
                                        supervisor_card.success("👤 **Supervisor Agent**: Analyzing results...")
                                        add_log(
                                            (
                                                "A2A_COMPLETE: "
                                                f"trace_id={handoff.trace_id} task_id={handoff.task_id} "
                                                f"idempotency_key={handoff.idempotency_key[:12]}... "
                                                f"elapsed={elapsed_s:.2f}s"
                                            ),
                                            "PROTOCOL",
                                        )
                                        return result
                                    finally:
                                        await specialist.close()
                                except RuntimeError as e:
                                    if "Circuit breaker" in str(e):
                                        specialist_card.error(f"🌩️ **Weather Specialist**: Circuit breaker active")
                                        obs_ctx.emit_event(StructuredEvent(
                                            event_type="a2a.circuit_breaker",
                                            trace_context=span_ctx,
                                            latency_ms=int((time.time() - start_time) * 1000),
                                            error_code="CIRCUIT_BREAKER_OPEN",
                                            attributes={
                                                "breaker_name": "weather-specialist",
                                                "state": breaker.metrics.state.value
                                            }
                                        ))
                                        obs_ctx.metrics.record_failure()
                                        return f"Specialist unavailable (circuit breaker open): {e}"
                                    raise
                                except Exception as e:
                                    specialist_card.error(f"🌩️ **Weather Specialist**: Error - {type(e).__name__}")
                                    obs_ctx.emit_event(StructuredEvent(
                                        event_type="a2a.error",
                                        trace_context=span_ctx,
                                        latency_ms=int((time.time() - start_time) * 1000),
                                        error_code=type(e).__name__,
                                        attributes={
                                            "error_message": str(e)
                                        }
                                    ))
                                    obs_ctx.metrics.record_failure()
                                    return f"Specialist execution failed: {type(e).__name__}: {e}"

                            @tool("agent_protocol_handshake")
                            async def agent_protocol_handshake() -> str:
                                """Initialize a secure production handshake between Supervisor and Specialist.
                                This performs capability negotiation and session authorization.
                                """
                                supervisor_card.info("🛡️ **Protocol**: Initiating A2A Handshake...")
                                resilience_ctx = st.session_state.resilience_context
                                breaker = resilience_ctx.get_breaker(
                                    "weather-specialist-handshake",
                                    CircuitBreakerConfig(failure_threshold=3, recovery_timeout_s=30),
                                )

                                def on_hs_retry(attempt: int, exc: Exception) -> None:
                                    add_log(
                                        f"A2A_HANDSHAKE_RETRY: attempt={attempt} error={type(exc).__name__}",
                                        "PROTOCOL",
                                    )

                                def on_hs_failure(exc: Exception) -> None:
                                    add_log(
                                        f"A2A_HANDSHAKE_FAILURE: breaker_state={breaker.metrics.state.value}",
                                        "PROTOCOL",
                                    )

                                specialist = get_agent(current_model)
                                try:
                                    add_log("📡 [A2A Handshake] Method: tools/call/get_capabilities", "PROTOCOL")
                                    caps_result = await resilience_ctx.execute_with_resilience(
                                        call_name="weather-specialist-handshake",
                                        coro_fn=lambda: specialist.run("List your system capabilities and protocol version."),
                                        timeout_s=5.0,
                                        on_retry=on_hs_retry,
                                        on_failure=on_hs_failure,
                                    )

                                    import secrets
                                    session_token = f"agent_sess_{secrets.token_hex(8)}"
                                    add_log(f"🔑 [A2A Handshake] Status: Authenticated | Token: {session_token}", "PROTOCOL")

                                    specialist_card.success("🌩️ **Weather Specialist**: Handshake Verified")
                                    return f"HANDSHAKE_COMPLETE: Capabilities verified for {current_model}. Session: {session_token}."
                                except RuntimeError as e:
                                    if "Circuit breaker" in str(e):
                                        return f"Handshake failed: Specialist circuit breaker active"
                                    raise
                                except Exception as e:
                                    return f"Handshake Failed: {type(e).__name__}: {e}"
                                finally:
                                    await specialist.close()

                            sys_msg = """You are the elite Supervisor Agent of a multi-agent system. 
                             
                             OPERATIONAL PROTOCOL:
                             1. CHECK HISTORY: Look through the conversation history for 'HANDSHAKE_COMPLETE'. 
                             2. HANDSHAKE: If 'HANDSHAKE_COMPLETE' is NOT in the history, you MUST call 'agent_protocol_handshake' as your FIRST action.
                             3. EXECUTION: After a successful handshake (or if one already exists), IMMEDIATELY call 'ask_weather_specialist' to fulfill the user's query.
                             4. GOAL: Never stop after the handshake. The user wants WEATHER DATA, not protocol confirmation. 
                             
                             Always append a subtle '🛡️ Protocol Verified' badge at the very end of your final synthesized response."""
                            
                            llm = ChatGroq(model=current_model, streaming=True, callbacks=[stream_handler])
                            tools = [ask_weather_specialist, agent_protocol_handshake]
                            
                            # LangChain 1.2+ creates a tool-calling graph directly via create_agent.
                            agent_executor = create_agent(llm, tools, system_prompt=sys_msg)
                            
                            supervisor_card.success("👤 **Supervisor Agent**: Processing Query...")
                            stream_handler.text = ""
                            
                            try:
                                messages_payload = chat_history + [HumanMessage(content=prompt_content)]
                                response_obj = await agent_executor.ainvoke({"messages": messages_payload})
                                response_text = response_obj["messages"][-1].content
                            except Exception as e:
                                response_text = f"Agent Orchestration Error: {e}"
                                
                            supervisor_card.success("👤 **Supervisor Agent**: Finished.")
                            stream_placeholder.empty()
                            return response_text

                        # Run agent work in an isolated loop to avoid teardown issues across reruns.
                        response = run_async_isolated(run_loop_safe())
                    finally:
                        mcp_logger.removeHandler(ui_handler)
                    
                    # Clean up any stray HTML tags
                    import re as regex_module
                    response = regex_module.sub(r'<[^>]+>', '', str(response))
                    
                    status.update(label="Complete!", state="complete", expanded=False)
                    
                    # Create informative log entry with proper severity
                    user_query = prompt_content[:50] + "..." if len(prompt_content) > 50 else prompt_content
                    response_preview = response[:80] + "..." if len(response) > 80 else response
                    log_msg = f"Query: '{user_query}' | Model: {current_model} | Response: {response_preview}"
                    
                    # Determine log severity based on response content
                    if "Agent stopped due to an error" in response or "❌" in response or "Failed to call" in response:
                        add_log(log_msg, "ERROR")
                    elif "⏱️" in response or "took too long" in response:
                        add_log(log_msg, "WARNING")
                    else:
                        add_log(log_msg, "SUCCESS")
                    
                    st.session_state.messages.append({"role": "assistant", "content": response})
                    st.rerun()
                except Exception as e:
                    status.update(label="Error", state="error")
                    st.error(f"Error: {str(e)}")
                    add_log(f"Agent Error: {e}", "ERROR")

# --- Tab 2: About Project ---
with tab2:
    st.markdown("""
    <div style='background: linear-gradient(135deg, rgba(40, 116, 240, 0.12) 0%, rgba(155, 89, 182, 0.12) 100%); 
                padding: 30px; border-radius: 15px; border: 1px solid rgba(40, 116, 240, 0.3); margin-bottom: 30px;
                box-shadow: 0 4px 15px rgba(0,0,0,0.2);'>
        <h2 style='color: #00d4ff; margin-bottom: 15px; font-weight: 800;'>🌟 Project Vision & Purpose</h2>
        <p style='font-size: 1.15rem; line-height: 1.7; color: #ecf0f1;'>
            <b>Weather Agent Pro</b> is a cutting-edge demonstration of <b>Agentic AI</b> using the <b>Model Context Protocol (MCP)</b>.
            Unlike traditional chatbots that simply predict text, this agent is equipped with <b>tools</b> that allow it to interact with the real world, 
            fetching live forecasts and alerts from the National Weather Service.
        </p>
    </div>
    """, unsafe_allow_html=True)

    acol1, acol2, acol3 = st.columns(3)
    with acol1:
        st.markdown("### 🧠 Intelligence")
        st.info("**Llama 3 70B** via Groq for high-performance reasoning and tool selection.")
    with acol2:
        st.markdown("### 🛠️ Connectivity")
        st.warning("**MCP Layer** connecting the LLM to local Python functions safely and efficiently.")
    with acol3:
        st.markdown("### 🌐 Data")
        st.success("**NWS & OpenMeteo** APIs providing real-time global weather data.")

    # --- New Detailed Content from Text File ---
    st.markdown("---")
    st.subheader("📚 Deep Dive: Model Context Protocol (MCP)")
    
    with st.expander("📖 1. What is MCP? (The Protocol Layer)"):
        st.markdown("""
        **MCP (Model Context Protocol)** is an open standard that connects AI systems to data sources.
        It replaces fragmented integration methods with a universal protocol.
        
        **Why is it needed?**
        *   **Standardization**: Moves away from custom API integrations for every tool.
        *   **Scalability**: Allows AI to connect to Databases, GitHub, Slack, etc., using one interface.
        *   **Real-World Interaction**: Enables LLMs to move beyond text generation to executing actions.
        """)
        
        col_mcp1, col_mcp2 = st.columns(2)
        with col_mcp1:
            st.markdown("**Core Components**")
            st.markdown("""
            *   **MCP Host**: The application running the agent (e.g., this app, Claude Desktop, Cursor).
            *   **MCP Client**: Lives inside the host; talks to servers.
            *   **MCP Server**: Exposes specific tools (e.g., `get_weather`, `query_db`).
            """)
        with col_mcp2:
            st.markdown("**Host Evolution**")
            st.code("""
User Request 
   ⬇
MCP Host (This App) 
   ⬇
MCP Server (Weather Tool)
   ⬇
Response -> LLM -> User
            """)

    with st.expander("🤖 2. Evolution: Generative AI -> AI Agents"):
        st.markdown("""
        1.  **Generative AI**: Input → LLM → Output (Text only).
        2.  **Multi-Modal Agents**: LLMs connected to specific tools (Search, Wikipedia) via custom code.
        3.  **MCP Agents**: LLMs that discover and use ANY tool exposed via a standard MCP Server (Universal compatibility).
        """)

    with st.expander("🆚 3. MCP vs Agent-to-Agent (A2A) Protocol"):
        st.table([
            {"Feature": "Interaction Model", "MCP": "LLM ↔ Tools", "A2A": "Agent ↔ Agent"},
            {"Feature": "Primary Goal", "MCP": "Execute specific tools/functions", "A2A": "Delegating complex tasks to other agents"},
            {"Feature": "Architecture", "MCP": "Central LLM with extensions", "A2A": "Distributed network of specialized agents"},
            {"Feature": "Example", "MCP": "Agent asks Weather Tool for data", "A2A": "Planner Agent hires Booking Agent for flights"}
        ])

    st.info("💡 **Supported Deployments**: Streamlit, FastAPI, Cursor IDE, Claude Desktop, Terminal.")

# --- Tab 3: Tech Stack ---
with tab3:
    st.markdown("""
    <div style='background: linear-gradient(135deg, rgba(0, 212, 255, 0.1) 0%, rgba(155, 89, 182, 0.1) 100%); 
                padding: 30px; border-radius: 15px; border-bottom: 4px solid #00d4ff; margin-bottom: 30px;'>
        <h2 style='color: #00d4ff; margin: 0 0 10px 0;'>🛠️ The Technology Stack</h2>
        <p style='color: #e2e8f0; font-size: 1.1rem; line-height: 1.6;'>
            Built on the standardized **Model Context Protocol**, enabling seamless interoperability between AI models and tools.
        </p>
    </div>
    """, unsafe_allow_html=True)

    # Interactive Controls
    tech_filter = st.radio("🔍 Filter View:", ["All Layers", "Intelligence", "Frontend", "Connectivity"], horizontal=True)
    st.write("") # Spacer

    # 3-Column Layout
    tc1, tc2, tc3 = st.columns(3)
    
    # Logic to show/hide
    show_all = tech_filter == "All Layers"
    
    if show_all or tech_filter == "Intelligence":
        with tc1:
            st.markdown("""
            <div class="tech-card" style="height: 100%;">
                <span class="tech-icon">🧠</span>
                <h3 style='color: #00d4ff; margin-top: 0;'>AI Core</h3>
                <ul style='color: #bdc3c7; font-size: 0.95rem; margin-left: 0; padding-left: 1.2rem;'>
                    <li><b>Llama 3 70B</b>: Advanced reasoning model.</li>
                    <li><b>MCP-Use</b>: Client implementation of MCP.</li>
                    <li><b>LangChain</b>: Orchestration framework.</li>
                </ul>
                <div style="margin-top: 15px;">
                    <span class="tech-tag" style="background: rgba(0, 212, 255, 0.2); color: #00d4ff;">Intelligence</span>
                </div>
            </div>
            """, unsafe_allow_html=True)

    if show_all or tech_filter == "Frontend":
        with tc2:
            st.markdown("""
            <div class="tech-card" style="height: 100%;">
                <span class="tech-icon">💻</span>
                <h3 style='color: #2ecc71; margin-top: 0;'>Application</h3>
                <ul style='color: #bdc3c7; font-size: 0.95rem; margin-left: 0; padding-left: 1.2rem;'>
                    <li><b>Streamlit</b>: Reactive Frontend.</li>
                    <li><b>Python 3.11</b>: Async Runtime.</li>
                    <li><b>WebRTC</b>: Voice Input Processing.</li>
                </ul>
                <div style="margin-top: 15px;">
                    <span class="tech-tag" style="background: rgba(46, 204, 113, 0.2); color: #2ecc71;">Frontend</span>
                </div>
            </div>
            """, unsafe_allow_html=True)

    if show_all or tech_filter == "Connectivity":
        with tc3:
            st.markdown("""
            <div class="tech-card" style="height: 100%;">
                <span class="tech-icon">🔌</span>
                <h3 style='color: #f39c12; margin-top: 0;'>Data Source</h3>
                <ul style='color: #bdc3c7; font-size: 0.95rem; margin-left: 0; padding-left: 1.2rem;'>
                    <li><b>MCP Server</b>: Local server exposing tools.</li>
                    <li><b>NWS API</b>: US Weather alerts/forecasts.</li>
                    <li><b>OpenMeteo</b>: Global coordinate data.</li>
                </ul>
                <div style="margin-top: 15px;">
                    <span class="tech-tag" style="background: rgba(243, 156, 18, 0.2); color: #f39c12;">Connectivity</span>
                </div>
            </div>
            """, unsafe_allow_html=True)
            
    # New Interactive Explorer Section
    st.markdown("---")
    with st.expander("📚 Interactive Component Details"):
        st.info("**Model Context Protocol (MCP)**\nThe open standard for connecting AI assistants to systems of record. It replaces fragmented integrations with a universal protocol.")
        st.warning("**Llama 3 70B (Groq)**\n**Groq LPU** (Language Processing Unit) delivers near-instant inference speeds, essential for real-time voice interaction.")
        st.success("**Streamlit Async Interface**\nThis app uses Python's **asyncio** to handle multiple API calls (Weather, Search, Maps) concurrently without blocking the UI.")

# --- Tab 4: Architecture ---
with tab4:
    st.markdown("""
    <div style='background: linear-gradient(135deg, rgba(46, 204, 113, 0.1) 0%, rgba(40, 116, 240, 0.1) 100%); 
                padding: 25px; border-radius: 12px; border-left: 5px solid #2ecc71; margin-bottom: 25px;'>
        <h2 style='color: #2ecc71; margin: 0 0 10px 0;'>🏗️ System Architecture</h2>
        <p style='color: #e8e8e8; margin: 0;'>
            Visualizing the flow from User Input to Agent Orchestration and Tool Execution.
        </p>
    </div>
    """, unsafe_allow_html=True)

    # Custom HTML/CSS Architecture Map (Inspired by Multi_Tab_Music_App)
    st.markdown("""<style>.arch-container{display:flex;flex-direction:column;gap:15px;padding:5px}.arch-phase{background:rgba(30,41,59,0.6);border-radius:12px;padding:18px;border:1px solid rgba(255,255,255,0.05)}.phase-title{font-size:1.15rem;font-weight:800;margin-bottom:12px;display:flex;align-items:center;gap:8px}.step-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:12px}.step-card{background:rgba(15,23,42,0.5);padding:10px;border-radius:8px;text-align:center;border-bottom:3px solid #00d4ff;font-size:0.8rem;color:#f1f5f9;transition:transform 0.2s}.step-card:hover{transform:scale(1.02);background:rgba(15,23,42,0.8)}.flow-arrow{text-align:center;color:#00d4ff;font-size:1.2rem;margin:2px 0;opacity:0.8}</style><div class="arch-container"><div class="arch-phase" style="border-left:5px solid #2874f0"><div class="phase-title" style="color:#2874f0">1️⃣ Ingress & Interface</div><div class="step-grid"><div class="step-card">Streamlit UI</div><div class="step-card">Voice Input (WebRTC)</div><div class="step-card">Session State Manager</div></div></div><div class="flow-arrow">&#9660;</div><div class="arch-phase" style="border-left:5px solid #9b59b6"><div class="phase-title" style="color:#9b59b6">2️⃣ Intelligence Core</div><div class="step-grid"><div class="step-card">Groq LPU Engine</div><div class="step-card">Llama 3 70B Model</div><div class="step-card">Context Window</div></div></div><div class="flow-arrow">&#9660;</div><div class="arch-phase" style="border-left:5px solid #2ecc71"><div class="phase-title" style="color:#2ecc71">3️⃣ MCP Tool Execution</div><div class="step-grid"><div class="step-card">Model Context Protocol</div><div class="step-card">NWS Weather API</div><div class="step-card">Use-MCP Client</div></div></div></div>""", unsafe_allow_html=True)
    
    st.markdown("### 🕸️ Detailed Graph Visualization")

    st.graphviz_chart("""
    digraph G {
        rankdir=LR;
        node [shape=box, style=filled, fillcolor="#243b55", fontcolor=white, fontname="Inter"];
        edge [color="#00d4ff"];
        bgcolor="#0f172a";
        
        User [label="👤 User", shape=ellipse, fillcolor="#2874f0"];
        Streamlit [label="🖥️ Streamlit UI"];
        Agent [label="🤖 MCP Agent\n(Llama 3)", fillcolor="#9b59b6"];
        
        subgraph cluster_mcp {
            label = "MCP Server Layer";
            style=dashed;
            color="white";
            fontcolor="white";
            Handlers [label="🛠️ Tool Handlers", fillcolor="#334155"];
            NWS [label="NWS API\n(US Data)", fillcolor="#2ecc71", fontcolor="black"];
            OpenMeteo [label="Open-Meteo\n(Global Data)", fillcolor="#2ecc71", fontcolor="black"];
        }
        
        User -> Streamlit [label="Voice/Text", fontcolor="white"];
        Streamlit -> Agent [label="Prompt", fontcolor="white"];
        Agent -> Handlers [label="MCP Protocol", fontcolor="white"];
        Handlers -> NWS [label="Rest API", fontcolor="white"];
        Handlers -> OpenMeteo [label="Rest API", fontcolor="white"];
        Handlers -> Agent [label="Result", fontcolor="white"];
        Agent -> Streamlit [label="Natural Response", fontcolor="white"];
    }
    """)

    # Interactive Section (Added per user request)
    st.markdown("---")
    st.subheader("🕹️ Interactive Architecture Walkthrough")
    st.caption("Explore the system's inner workings through simulation and deep verification.")

    # Mode Selection
    # --- Section: Data Flow Simulation ---
    st.markdown("#### 🌊 Data Flow Simulation")
    st.info("🎤 **1. Ingress**: Voice/Text captured via Streamlit UI.\n\n*Tech*: `streamlit-mic-recorder` captures raw WAV bytes.")
    st.warning("🗣️ **2. Transcribing**: Google Speech Recognition converts Audio -> Text.\n\n*Data*: `Bytes` -> `String` ('What is the weather?').")
    st.error("🧠 **3. Cognition**: Llama 3 (Groq) analyzes intent & selects tools.\n\n*Logic*: 'User wants weather -> Select `get_weather_alerts` tool'.")
    st.info("🔌 **4. Protocol**: MCP Execution - Agent calls Tool -> MCP Client -> External API.\n\n*Action*: `GET https://api.weather.gov/...`")
    st.success("✨ **5. Synthesis**: Final answer generated & displayed to User.\n\n*Result*: 'There is a wind advisory in effect...' (Added to Chat History).")

    st.markdown("---")

    # --- Section: Component Deep Dive ---
    st.markdown("#### 🧩 Component Deep Dive")
    d1, d2, d3 = st.tabs(["🖥️ Application Core", "🧠 Intelligence Layer", "🛠️ Tooling Infrastructure"])
        
    with d1:
        st.markdown("**Role**: Manages User Session, State, and IO.")
        st.json({
            "Framework": "Streamlit",
            "Runtime": "Python 3.11 (Async)",
            "State Management": "st.session_state",
            "Theme": "Custom CSS (Gradient/Dark Mode)"
        })
        
    with d2:
        st.markdown("**Role**: High-speed Inference Engine.")
        st.json({
            "Provider": "Groq Cloud",
            "Model": "llama-3.3-70b-versatile",
            "Agent Type": "ReAct (Reasoning + Acting)",
            "Memory": "ConversationBufferMemory (Short-term)"
        })
        
    with d3:
        st.markdown("**Role**: Standardized Tool Interface.")
        st.json({
            "Protocol": "Model Context Protocol (MCP)",
            "Client": "mcp-use Python SDK",
            "Active Tools": ["NWS Weather", "OpenStreetMaps (Nominatim)", "DuckDuckGo Search"],
            "Error Handling": "Try/Except Block Wrappers"
        })

# --- Tab 5: System Logs ---
with tab5:
    st.markdown("""
    <div style='background: linear-gradient(135deg, rgba(40, 116, 240, 0.1) 0%, rgba(155, 89, 182, 0.1) 100%); 
                padding: 25px; border-radius: 12px; border-right: 5px solid #2874f0; margin-bottom: 25px;'>
        <h2 style='color: #00d4ff; margin: 0 0 10px 0;'>📋 System Operations Monitor</h2>
        <p style='color: #e8e8e8; margin: 0;'>
             Real-time event tracking of Agent State, Tool Calls, and Errors.
        </p>
    </div>
    """, unsafe_allow_html=True)
    
    log_data = st.session_state.logs
    
    
    # Metrics Row
    m1, m2, m3 = st.columns(3)
    
    total_events = len(log_data)
    success_count = len([l for l in log_data if l['type'] == 'SUCCESS'])
    error_count = len([l for l in log_data if l['type'] == 'ERROR'])
    # Calculate Success Rate
    success_rate = (success_count / total_events * 100) if total_events > 0 else 0
    
    with m1:
        st.markdown(f"""
        <div style='background: rgba(40, 116, 240, 0.1); padding: 15px; border-radius: 10px; border-left: 5px solid #2874f0; text-align: center;'>
            <h4 style='color: #bdc3c7; margin: 0; font-size: 0.9rem;'>TOTAL EVENTS</h4>
            <p style='color: #2874f0; font-size: 1.8rem; font-weight: bold; margin: 5px 0;'>{total_events}</p>
        </div>
        """, unsafe_allow_html=True)
    with m2:
         st.markdown(f"""
        <div style='background: rgba(46, 204, 113, 0.1); padding: 15px; border-radius: 10px; border-left: 5px solid #2ecc71; text-align: center;'>
            <h4 style='color: #bdc3c7; margin: 0; font-size: 0.9rem;'>SUCCESS RATE</h4>
            <p style='color: #2ecc71; font-size: 1.8rem; font-weight: bold; margin: 5px 0;'>{success_rate:.1f}%</p>
        </div>
        """, unsafe_allow_html=True)
    with m3:
         st.markdown(f"""
        <div style='background: rgba(231, 76, 60, 0.1); padding: 15px; border-radius: 10px; border-left: 5px solid #e74c3c; text-align: center;'>
            <h4 style='color: #bdc3c7; margin: 0; font-size: 0.9rem;'>SYSTEM ERRORS</h4>
            <p style='color: #e74c3c; font-size: 1.8rem; font-weight: bold; margin: 5px 0;'>{error_count}</p>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("---")

    # Custom CSS for "Next in Line" Filter styling
    st.markdown("""
    <style>
        /* Compact Multiselect Tags */
        .stMultiSelect span[data-baseweb="tag"] {
            font-size: 0.8rem;
            padding: 2px 6px;
        }
        /* Force horizontal layout for tags with scrolling */
        .stMultiSelect div[data-baseweb="select"] > div:first-child {
            flex-wrap: nowrap !important;
            overflow-x: auto !important;
            scrollbar-width: thin;
        }
    </style>
    """, unsafe_allow_html=True)
    
    
    # Controls & Actions
    st.markdown("### 🎛️ Monitor Controls")
    
    # Row 1: Filters
    c_search, c_levels = st.columns([1, 2])
    with c_search:
        search_query = st.text_input("Search Logs", placeholder="🔍 Filter...", label_visibility="collapsed")
    with c_levels:
        filter_types = st.multiselect("Log Levels", ["INFO", "SUCCESS", "WARNING", "ERROR", "PROTOCOL"], 
                                    default=["INFO", "SUCCESS", "WARNING", "ERROR", "PROTOCOL"], 
                                    label_visibility="collapsed")

    # Filter data
    filtered_logs = [
        l for l in log_data 
        if l['type'] in filter_types 
        and (search_query.lower() in l['msg'].lower())
    ]
    
    # Reverse to show newest first
    filtered_logs = filtered_logs[::-1]
    
    st.markdown("### 📜 Activity Log")
    
    for log in filtered_logs:
        color = {
            "INFO": "#2874f0",
            "SUCCESS": "#2ecc71",
            "WARNING": "#f1c40f",
            "ERROR": "#e74c3c",
            "PROTOCOL": "#00d4ff"
        }.get(log['type'], "#bdc3c7")
        
        icon = {
            "INFO": "ℹ️",
            "SUCCESS": "✅",
            "WARNING": "⚠️",
            "ERROR": "❌",
            "PROTOCOL": "📡"
        }.get(log['type'], "📝")
        
        with st.container():
            st.markdown(f"""
            <div style="border-left: 3px solid {color}; padding-left: 10px; margin-bottom: 10px;">
                <span style="color: #666; font-size: 0.8rem;">[{log['time']}]</span>
                <span style="color: {color}; font-weight: bold; font-size: 0.9rem;">{icon} {log['type']}</span>
            </div>
            """, unsafe_allow_html=True)
            
            if log['type'] == "PROTOCOL":
                st.code(log['msg'], language="json")
            else:
                st.markdown(log['msg'])
            st.markdown("<div style='margin-bottom: 15px;'></div>", unsafe_allow_html=True)

    if not filtered_logs:
        st.info("No logs matching selected filters.")

    # Row 2: Actions (Next Line)
    b1, b2, b3, b4 = st.columns(4)
    with b1:
        st.button("🔄 Refresh", width="stretch", on_click=lambda: st.rerun())
    with b2:
        if st.button("🗑️ Clear", width="stretch"):
                st.session_state.logs = []
                st.rerun()
    with b3:
        log_text = "\n".join([f"[{l['time']}] {l['type']}: {l['msg']}" for l in log_data])
        st.download_button("📄 Save TXT", data=log_text, file_name=f"log_{datetime.datetime.now().strftime('%H%M%S')}.txt", mime="text/plain", width="stretch")
    with b4:
        log_json = json.dumps(log_data, indent=2)
        st.download_button("💾 Save JSON", data=log_json, file_name=f"log_{datetime.datetime.now().strftime('%H%M%S')}.json", mime="application/json", width="stretch")

    # Filter Logic
    filtered_logs = [
        l for l in log_data 
        if (search_query.lower() in l['msg'].lower() or search_query.lower() in l['type'].lower())
        and l['type'] in filter_types
    ]

    st.markdown("### 📜 Event Feed")
    log_container = st.container(height=400)
    with log_container:
        if not filtered_logs:
            if not log_data:
                st.info("No system logs generated yet. Interactions will appear here.")
            else:
                st.info("No logs match the current filters.")
        else:
            for log in reversed(filtered_logs):
                color = "#3498db" if log['type'].lower() == "info" else "#2ecc71" if log['type'] == "SUCCESS" else "#f39c12" if log['type'] == "WARNING" else "#e74c3c"
                icon = "ℹ️" if log['type'].lower() == "info" else "✅" if log['type'] == "SUCCESS" else "⚠️" if log['type'] == "WARNING" else "🚨"
                
                st.markdown(f"""
                <div style='background: rgba(30, 41, 59, 0.4); padding: 12px; border-radius: 8px; border-left: 4px solid {color}; margin-bottom: 8px; font-family: monospace;'>
                    <span style='color: #bdc3c7;'>[{log['time']}]</span> 
                    <b style='color: {color}; margin: 0 10px;'>{log['type'].upper()}</b> 
                    <span style='color: #ecf0f1;'>{icon} {log['msg']}</span>
                </div>
                """, unsafe_allow_html=True)

# --- Tab 6: Resilience Hub ---
with tab6:
    st.markdown("""
    <div style='background: linear-gradient(135deg, rgba(255, 193, 7, 0.1) 0%, rgba(243, 156, 18, 0.1) 100%); 
                padding: 25px; border-radius: 12px; border-left: 5px solid #f39c12; margin-bottom: 25px;'>
        <h2 style='color: #f39c12; margin: 0 0 10px 0;'>⚡ Resilience Hub</h2>
        <p style='color: #e8e8e8; margin: 0;'>
            Circuit breaker states, retry patterns, and failure recovery metrics in real-time.
        </p>
    </div>
    """, unsafe_allow_html=True)
    
    resilience_ctx = st.session_state.resilience_context
    
    # Dashboard Tabs
    res_tab1, res_tab2, res_tab3 = st.tabs(["🔌 Circuit Breakers", "🔄 Retry Metrics", "📈 Failure Patterns"])
    
    with res_tab1:
        st.markdown("### Active Circuit Breakers")
        
        if not resilience_ctx.circuit_breakers:
            st.info("No circuit breakers activated yet. They initialize on first resilient call.")
        else:
            # Display metrics for each breaker
            for breaker_name, breaker in resilience_ctx.circuit_breakers.items():
                cols = st.columns([2, 1, 1, 1])
                
                with cols[0]:
                    # State indicator
                    state = breaker.metrics.state.value
                    state_color = "#2ecc71" if state == "closed" else "#f39c12" if state == "half_open" else "#e74c3c"
                    state_emoji = "✅" if state == "closed" else "⚠️" if state == "half_open" else "🔴"
                    
                    st.markdown(f"""
                    <div style='background: rgba(30, 41, 59, 0.6); padding: 16px; border-radius: 10px; border-left: 5px solid {state_color};'>
                        <p style='margin: 0; font-size: 0.95rem;'><b>{state_emoji} {breaker_name}</b></p>
                        <p style='margin: 5px 0 0 0; color: {state_color}; font-weight: 600;'>STATE: {state.upper()}</p>
                    </div>
                    """, unsafe_allow_html=True)
                
                with cols[1]:
                    st.metric("Total Requests", breaker.metrics.total_requests)
                
                with cols[2]:
                    st.metric("Successes", breaker.metrics.total_requests - breaker.metrics.total_failures)
                
                with cols[3]:
                    failure_rate = (breaker.metrics.total_failures / breaker.metrics.total_requests * 100) if breaker.metrics.total_requests > 0 else 0
                    st.metric("Failure Rate", f"{failure_rate:.1f}%")
                
                # Details expansion
                with st.expander(f"📋 Details for {breaker_name}"):
                    detail_cols = st.columns(2)
                    with detail_cols[0]:
                        st.json({
                            "failure_threshold": breaker.config.failure_threshold,
                            "recovery_timeout_s": breaker.config.recovery_timeout_s,
                            "current_failures": breaker.metrics.failure_count,
                            "last_failure": breaker.metrics.last_failure_at or "Never"
                        })
                    with detail_cols[1]:
                        st.json({
                            "state_change_at": breaker.metrics.last_state_change_at,
                            "half_open_successes": breaker.metrics.success_count_half_open,
                            "success_threshold_to_close": breaker.config.success_threshold_half_open
                        })
    
    with res_tab2:
        st.markdown("### Retry Strategy Configuration")
        
        retry_policy = resilience_ctx.retry_policy
        st.json({
            "max_retries": retry_policy.max_retries,
            "initial_backoff_ms": retry_policy.initial_backoff_ms,
            "max_backoff_ms": retry_policy.max_backoff_ms,
            "backoff_multiplier": retry_policy.backoff_multiplier,
            "jitter_factor": retry_policy.jitter_factor
        })
        
        st.markdown("### Exponential Backoff Timeline")
        
        backoff_timeline = []
        for attempt in range(min(5, retry_policy.max_retries + 1)):
            backoff_sec = retry_policy.backoff_duration(attempt)
            backoff_timeline.append({
                "Attempt": attempt + 1,
                "Duration (sec)": round(backoff_sec, 3),
                "Cumulative (sec)": round(sum([retry_policy.backoff_duration(i) for i in range(attempt + 1)]), 3)
            })
        
        st.dataframe(backoff_timeline, width="stretch")
    
    with res_tab3:
        st.markdown("### Failure Recovery Visualization")
        
        # Extract failure data for visualization
        if resilience_ctx.circuit_breakers:
            failure_data = []
            for breaker_name, breaker in resilience_ctx.circuit_breakers.items():
                if breaker.metrics.total_requests > 0:
                    failure_data.append({
                        "Service": breaker_name,
                        "Success": breaker.metrics.total_requests - breaker.metrics.total_failures,
                        "Failures": breaker.metrics.total_failures
                    })
            
            if failure_data:
                st.bar_chart(data=failure_data, x="Service", width="stretch")
            else:
                st.info("No failure data available yet.")
        else:
            st.info("No circuit breaker data available.")

# --- Tab 7: Security Audit Log ---
with tab7:
    st.markdown("""
    <div style='background: linear-gradient(135deg, rgba(231, 76, 60, 0.1) 0%, rgba(192, 57, 43, 0.1) 100%); 
                padding: 25px; border-radius: 12px; border-left: 5px solid #e74c3c; margin-bottom: 25px;'>
        <h2 style='color: #e74c3c; margin: 0 0 10px 0;'>🔒 Security Audit Log</h2>
        <p style='color: #e8e8e8; margin: 0;'>
            Track policy decisions, identity verification, and access control events.
        </p>
    </div>
    """, unsafe_allow_html=True)
    
    sec_tab1, sec_tab2, sec_tab3 = st.tabs(["🛡️ Policy Decisions", "👤 Agent Identity", "🔑 Access Events"])
    
    with sec_tab1:
        st.markdown("### Policy Decision Engine")
        
        st.info("""
        **RBAC Tool Restrictions:**
        - `get_alerts`: supervisor, admin
        - `get_coordinates`: supervisor, specialist, admin
        - `get_global_forecast`: supervisor, specialist, admin
        """)
        
        st.markdown("### Geographic Restrictions by Role")
        
        geo_restrictions = {
            "Role": ["guest", "supervisor", "specialist", "admin"],
            "Allowed Regions": ["US", "US, Global", "US, Global", "US, Global"]
        }
        st.table(geo_restrictions)
        
        st.markdown("### Policy Violation Examples")
        
        violation_cols = st.columns(3)
        with violation_cols[0]:
            st.error("""
            **Violation: Insufficient Role**
            - Agent: guest
            - Tool: get_alerts
            - Decision: ❌ DENIED
            - Reason: insufficient_role
            """)
        
        with violation_cols[1]:
            st.error("""
            **Violation: Geographic Restriction**
            - Agent: guest (allowed: US)
            - Region: Europe
            - Decision: ❌ DENIED
            - Reason: geographic_restriction
            """)
        
        with violation_cols[2]:
            st.success("""
            **Allowed: Admin Access**
            - Agent: admin
            - Tool: get_alerts
            - Region: Global
            - Decision: ✅ ALLOWED
            """)
    
    with sec_tab2:
        st.markdown("### Agent Identity Certificates")
        
        sample_identities = [
            {
                "issuer": "mcp-server",
                "subject": "supervisor-agent",
                "audience": "weather-specialist",
                "role": "supervisor",
                "status": "✅ Valid"
            },
            {
                "issuer": "mcp-server",
                "subject": "weather-specialist",
                "audience": "mcp-tools",
                "role": "specialist",
                "status": "✅ Valid"
            }
        ]
        
        for identity in sample_identities:
            st.markdown(f"""
            <div style='background: rgba(30, 41, 59, 0.6); padding: 15px; border-radius: 10px; border-left: 5px solid #2ecc71; margin-bottom: 10px;'>
                <p style='margin: 0; color: #2ecc71; font-weight: 600;'>{identity['status']}</p>
                <p style='margin: 5px 0 0 0; color: #bdc3c7; font-size: 0.9rem;'>
                    <b>Role:</b> {identity['role']} | 
                    <b>Subject:</b> {identity['subject']} | 
                    <b>Audience:</b> {identity['audience']}
                </p>
            </div>
            """, unsafe_allow_html=True)
        
        st.markdown("### HMAC Signature Verification")
        st.code("""
# Cryptographic Identity Verification
signature = "sha256_hex_digest_of_identity_metadata"
verified = hmac.compare_digest(expected, signature)
        """, language="python")
    
    with sec_tab3:
        st.markdown("### Access Control Events")
        
        audit_events = [
            {"timestamp": "2024-11-15 10:23:45", "agent": "supervisor", "action": "ALLOW", "tool": "get_alerts", "reason": "correct_role"},
            {"timestamp": "2024-11-15 10:24:12", "agent": "guest", "action": "DENY", "tool": "get_alerts", "reason": "insufficient_role"},
            {"timestamp": "2024-11-15 10:25:03", "agent": "specialist", "action": "ALLOW", "tool": "get_global_forecast", "reason": "correct_role"},
            {"timestamp": "2024-11-15 10:26:18", "agent": "guest", "action": "DENY", "tool": "get_coordinates", "reason": "geographic_restriction"},
        ]
        
        for event in audit_events:
            color = "#2ecc71" if event['action'] == "ALLOW" else "#e74c3c"
            icon = "✅" if event['action'] == "ALLOW" else "❌"
            
            st.markdown(f"""
            <div style='background: rgba(30, 41, 59, 0.4); padding: 12px; border-radius: 8px; border-left: 4px solid {color}; margin-bottom: 8px;'>
                <span style='color: #bdc3c7; font-size: 0.85rem;'>[{event['timestamp']}]</span>
                <span style='color: {color}; font-weight: 600; margin: 0 10px;'>{icon} {event['action']}</span>
                <span style='color: #ecf0f1;'>{event['agent']} → {event['tool']} ({event['reason']})</span>
            </div>
            """, unsafe_allow_html=True)

# --- Tab 8: Observability Metrics ---
with tab8:
    st.markdown("""
    <div style='background: linear-gradient(135deg, rgba(46, 204, 113, 0.1) 0%, rgba(52, 152, 219, 0.1) 100%); 
                padding: 25px; border-radius: 12px; border-left: 5px solid #2ecc71; margin-bottom: 25px;'>
        <h2 style='color: #2ecc71; margin: 0 0 10px 0;'>📊 Observability Metrics</h2>
        <p style='color: #e8e8e8; margin: 0;'>
            End-to-end tracing, latency percentiles, and SLO tracking.
        </p>
    </div>
    """, unsafe_allow_html=True)
    
    obs_ctx = st.session_state.observability_context
    metrics = obs_ctx.metrics
    
    obs_tab1, obs_tab2, obs_tab3, obs_tab4 = st.tabs(["📈 SLO Metrics", "⏱️ Latency Percentiles", "🔍 Trace Events", "📊 Performance Dashboard"])
    
    with obs_tab1:
        st.markdown("### Real-Time SLO Tracking")
        
        m1, m2, m3, m4 = st.columns(4)
        
        with m1:
            st.metric("✅ Success Rate", f"{metrics.success_rate() * 100:.1f}%", 
                     delta=f"+{metrics.success_count} ops")
        with m2:
            st.metric("📊 Total Operations", metrics.success_count + metrics.failure_count)
        with m3:
            st.metric("🔄 Retries", metrics.retry_count)
        with m4:
            st.metric("🔴 Breaker Opens", metrics.breaker_open_count)
        
        st.markdown("### SLO Definitions (99th Percentile Target)")
        
        slo_table = {
            "Service": ["A2A Handoff", "Weather Specialist", "MCP Tool Call"],
            "SLO Target": ["< 2000ms", "< 5000ms", "< 1000ms"],
            "Alert Threshold": ["> 2500ms", "> 6000ms", "> 1200ms"],
            "Status": ["✅ On Track", "✅ On Track", "✅ On Track"]
        }
        st.table(slo_table)
    
    with obs_tab2:
        st.markdown("### Latency Histogram")
        
        if metrics.latency_percents:
            # Aggregate all latency data
            all_buckets = {}
            for service, bucket in metrics.latency_percents.items():
                for bucket_name, count in bucket.to_dict().items():
                    all_buckets[bucket_name] = all_buckets.get(bucket_name, 0) + count
            
            if all_buckets:
                latency_df = {
                    "Latency Bucket": list(all_buckets.keys()),
                    "Count": list(all_buckets.values())
                }
                st.bar_chart(latency_df, x="Latency Bucket", width="stretch")
                
                st.markdown("### Latency Percentiles")
                percentile_data = []
                cumulative = 0
                total = sum(all_buckets.values())
                
                for bucket_name in sorted(all_buckets.keys(), key=lambda x: float(x.replace('ms', '').replace('inf', '9999999'))):
                    cumulative += all_buckets[bucket_name]
                    percentile = (cumulative / total * 100) if total > 0 else 0
                    percentile_data.append({
                        "Latency": bucket_name,
                        "Count": all_buckets[bucket_name],
                        "Cumulative %": f"{percentile:.1f}%"
                    })
                
                st.dataframe(percentile_data, width="stretch")
            else:
                st.info("No latency data collected yet.")
        else:
            st.info("Latency metrics will be populated after agent interactions.")
    
    with obs_tab3:
        st.markdown("### Trace Event Correlation")
        
        if obs_ctx.event_log:
            st.markdown(f"**Total Events Logged:** {len(obs_ctx.event_log)}")
            
            for event in obs_ctx.event_log[-10:]:  # Show last 10 events
                event_type_color = "#2874f0" if "handoff" in event.event_type else "#9b59b6" if "completion" in event.event_type else "#e74c3c" if "error" in event.event_type else "#2ecc71"
                
                st.markdown(f"""
                <div style='background: rgba(30, 41, 59, 0.4); padding: 12px; border-radius: 8px; border-left: 4px solid {event_type_color}; margin-bottom: 8px;'>
                    <p style='margin: 0; color: #bdc3c7; font-size: 0.85rem;'><b>Trace ID:</b> {event.trace_context.trace_id}</p>
                    <p style='margin: 5px 0 0 0; color: {event_type_color}; font-weight: 600;'>{event.event_type}</p>
                    <p style='margin: 5px 0 0 0; color: #94a3b8; font-size: 0.9rem;'>{event.timestamp}</p>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.info("No trace events recorded yet. Events will appear after agent interactions.")
    
    with obs_tab4:
        st.markdown("### Performance Summary")
        
        perf_cols = st.columns(2)
        
        with perf_cols[0]:
            st.markdown("### Operation Counters")
            counters = {
                "a2a_handoffs": metrics.counters.get("a2a_handoffs", 0),
                "tool_calls": metrics.counters.get("tool_calls", 0),
                "api_requests": metrics.counters.get("api_requests", 0)
            }
            st.json(counters)
        
        with perf_cols[1]:
            st.markdown("### Gauge Metrics")
            gauges = metrics.gauges if metrics.gauges else {"active_spans": 0}
            st.json(gauges)
        
        st.markdown("---")
        st.markdown("### Export Metrics")
        
        metrics_json = json.dumps(metrics.to_dict(), indent=2)
        st.download_button(
            "📥 Download Metrics JSON",
            data=metrics_json,
            file_name=f"metrics_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
            mime="application/json",
            width="stretch"
        )

# --- Footer ---
st.markdown("---")
st.markdown("""
<div style='text-align: center; padding: 20px 20px 10px 20px; background: linear-gradient(135deg, rgba(40, 116, 240, 0.15) 0%, rgba(155, 89, 182, 0.15) 100%); border-radius: 10px; border-top: 2px solid #2874f0;'>
    <p style='color: #00d4ff; font-weight: 600; font-size: 1.1rem; margin-bottom: 10px;'>🤖 Weather Agent Pro (MCP)</p>
    <p style='color: #00d4ff; font-weight: 600; font-size: 1.1rem; margin-bottom: 10px;'>Built with ❤️ by Sohan Patil | Data Scientist (AI/ML Engineer 4+Years Exp)</p>
    <p style='font-size: 0.9rem; color: #e8e8e8; margin-bottom: 5px;'>Powered by MCP (Model Context Protocol), LangChain, Groq, and Streamlit</p>
</div>
""", unsafe_allow_html=True)

# Social links
col1, col2, col3, col4, col5 = st.columns([1, 1, 1, 1, 1])

with col2:
    st.markdown('<p style="text-align: center; margin: 0;"><a href="https://github.com/sohanpatil4600" target="_blank" style="text-decoration: none; color: #2874f0; font-size: 1.1rem; font-weight: 600;">🔗 GitHub</a></p>', unsafe_allow_html=True)

with col3:
    st.markdown('<p style="text-align: center; margin: 0;"><a href="mailto:sohanpatil.usa@gmail.com" style="text-decoration: none; color: #26a65b; font-size: 1.1rem; font-weight: 600;">📧 Email</a></p>', unsafe_allow_html=True)

with col4:
    st.markdown('<p style="text-align: center; margin: 0;"><a href="https://www.linkedin.com/in/sohanrpatil/" target="_blank" style="text-decoration: none; color: #0077b5; font-size: 1.1rem; font-weight: 600;">💼 LinkedIn</a></p>', unsafe_allow_html=True)

# Close the visual footer
st.markdown("""
<div style='height: 10px; background: linear-gradient(135deg, rgba(40, 116, 240, 0.15) 0%, rgba(155, 89, 182, 0.15) 100%); border-radius: 0 0 10px 10px; border-bottom: 2px solid #2874f0; margin-top: -10px;'></div>
""", unsafe_allow_html=True)
