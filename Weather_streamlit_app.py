import streamlit as st
import asyncio
import os
import io
import traceback
import nest_asyncio
import json
import datetime
import base64
from dotenv import load_dotenv
from langchain_groq import ChatGroq
from mcp_use import MCPAgent, MCPClient
from streamlit_mic_recorder import mic_recorder
import speech_recognition as sr

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



def safe_image(path, caption=None, use_container_width=True):
    try:
        from PIL import Image
        import streamlit as st
        # Verify it's a valid image
        Image.open(path).verify()
        safe_image(path, caption=caption, use_container_width=use_container_width)
    except Exception:
        # If it's a git lfs pointer or missing
        st.info(f"🖼️ [Image Placeholder for {path}]")

def add_log(message, type="info"):
    # Streamlit Cloud uses UTC by default. Adding 5:30 for IST.
    from datetime import datetime as dt, timedelta
    ist_cutoff = timedelta(hours=5, minutes=30)
    timestamp = (dt.utcnow() + ist_cutoff).strftime("%H:%M:%S")
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
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "🚀 Project Demo", 
    "ℹ️ About Project", 
    "🛠️ Tech Stack", 
    "🏗️ Architecture", 
    "📋 System Logs"
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
    
    if q1.button("🗽 NY Weather", use_container_width=True):
         st.session_state.messages.append({"role": "user", "content": "What is the current weather in New York?"})
         st.rerun()
         
    if q2.button("🌧️ London Rain?", use_container_width=True):
         st.session_state.messages.append({"role": "user", "content": "Is it going to rain in London today?"})
         st.rerun()
         
    if q3.button("🇯🇵 Tokyo Forecast", use_container_width=True):
         st.session_state.messages.append({"role": "user", "content": "Give me a 3-day forecast for Tokyo."})
         st.rerun()
         
    if q4.button("⚠️ US Alerts", use_container_width=True):
         st.session_state.messages.append({"role": "user", "content": "Are there any severe weather alerts in California right now?"})
         st.rerun()

    # Row 2
    q5, q6, q7, q8 = st.columns(4)
    if q5.button("🌅 Paris Sunrise", use_container_width=True):
         st.session_state.messages.append({"role": "user", "content": "When is sunrise in Paris tomorrow?"})
         st.rerun()
    
    if q6.button("💨 Chicago Wind", use_container_width=True):
         st.session_state.messages.append({"role": "user", "content": "What is the current wind speed in Chicago?"})
         st.rerun()
         
    if q7.button("🌡️ Dubai Temp", use_container_width=True):
         st.session_state.messages.append({"role": "user", "content": "What is the current temperature in Dubai?"})
         st.rerun()
         
    if q8.button("☔ Mumbai Rain", use_container_width=True):
         st.session_state.messages.append({"role": "user", "content": "Is it raining in Mumbai right now?"})
         st.rerun()

    # Row 3 (Indian Cities)
    q9, q10, q11, q12 = st.columns(4)
    if q9.button("🌫️ Delhi Weather", use_container_width=True):
         st.session_state.messages.append({"role": "user", "content": "What is the current weather in New Delhi?"})
         st.rerun()
    
    if q10.button("💻 Bangalore Temp", use_container_width=True):
         st.session_state.messages.append({"role": "user", "content": "What is the current temperature in Bangalore?"})
         st.rerun()
         
    if q11.button("🌊 Chennai Rain", use_container_width=True):
         st.session_state.messages.append({"role": "user", "content": "Is it raining in Chennai right now?"})
         st.rerun()
         
    if q12.button("🏰 Hyderabad Cast", use_container_width=True):
         st.session_state.messages.append({"role": "user", "content": "Give me a weather forecast for Hyderabad, India."})
         st.rerun()

    # Row 4 (Global Mix)
    q13, q14, q15, q16 = st.columns(4)
    if q13.button("🐨 Sydney Sun", use_container_width=True):
         st.session_state.messages.append({"role": "user", "content": "Is it sunny in Sydney right now?"})
         st.rerun()
    
    if q14.button("🍁 Toronto Snow", use_container_width=True):
         st.session_state.messages.append({"role": "user", "content": "Is it snowing in Toronto?"})
         st.rerun()
         
    if q15.button("🦁 Singapore Humid", use_container_width=True):
         st.session_state.messages.append({"role": "user", "content": "What is the humidity in Singapore?"})
         st.rerun()
         
    if q16.button("🐻 Berlin Temp", use_container_width=True):
         st.session_state.messages.append({"role": "user", "content": "What is the current temperature in Berlin?"})
         st.rerun()

    # Weather Visuals Gallery
    st.markdown("### 📸 Weather Landscapes")
    g1, g2, g3, g4 = st.columns(4)
    with g1:
        safe_image("assets/snow_winter.png", caption="Snowy Winter", use_container_width=True)
    with g2:
        safe_image("assets/rain_storm.png", caption="Rainy Cloud", use_container_width=True)
    with g3:
        safe_image("assets/green_hills.png", caption="Green Hills", use_container_width=True)
    with g4:
        safe_image("assets/sea_beach.png", caption="Sea Water", use_container_width=True)

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
                submitted = st.form_submit_button("🚀 Enter", use_container_width=True)
            with col_btn_stop:
                stopped = st.form_submit_button("⏹️ Stop", use_container_width=True)
    
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
                    use_container_width=True
                )
            with exp_col2:
                st.download_button(
                    label="📄 TXT",
                    data=chat_history_txt,
                    file_name="weather_chat_history.txt",
                    mime="text/plain",
                    use_container_width=True
                )
            
        with col_clear:
            st.write("🧹 **Clear:**")
            if st.button("Clear Chat", use_container_width=True):
                st.session_state.messages = []
                add_log("Chat history cleared", "INFO")
                st.rerun()

        with col_reset:
            st.write("🔄 **Reset:**")
            if st.button("Reset System", use_container_width=True):
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
                            elif "📄 Tool result:" in msg:
                                add_log(msg[:200] + ("..." if len(msg) > 200 else ""), "SUCCESS")
                    
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
                            from langgraph.prebuilt import create_react_agent
                            from langchain_core.messages import HumanMessage
                            from langchain_core.tools import tool
                            import asyncio as aio
                            
                            @tool("ask_weather_specialist")
                            async def ask_weather_specialist(query: str) -> str:
                                """Delegate tasks directly to the Weather Specialist Agent."""
                                supervisor_card.info("👤 **Supervisor Agent**: Waiting for Specialist...")
                                specialist_card.warning("🌩️ **Weather Specialist**: Extracting MCP Data...")
                                
                                last_error = None
                                for attempt in range(3):
                                    specialist = get_agent(current_model)
                                    try:
                                        result = await specialist.run(query) 
                                        specialist_card.success("🌩️ **Weather Specialist**: Task Complete!")
                                        supervisor_card.success("👤 **Supervisor Agent**: Analyzing results...")
                                        return result
                                    except Exception as e:
                                        last_error = e
                                        await aio.sleep(1)
                                    finally:
                                        await specialist.close()
                                return f"Specialist failed to retrieve data: {last_error}"

                            sys_msg = "You are the elite Supervisor Agent of a multi-agent system. You DO NOT have weather data. If the user asks for weather, you MUST delegate the task to the 'ask_weather_specialist' tool. Once the specialist returns the raw data, format it beautifully and conversationally for the user."
                            
                            llm = ChatGroq(model=current_model, streaming=True, callbacks=[stream_handler])
                            tools = [ask_weather_specialist]
                            agent_executor = create_react_agent(llm, tools)
                            
                            supervisor_card.success("👤 **Supervisor Agent**: Processing Query...")
                            stream_handler.text = ""
                            
                            try:
                                from langchain_core.messages import SystemMessage
                                messages_payload = [SystemMessage(content=sys_msg)] + chat_history + [HumanMessage(content=prompt_content)]
                                response_obj = await agent_executor.ainvoke({"messages": messages_payload})
                                response_text = response_obj["messages"][-1].content
                            except Exception as e:
                                response_text = f"Agent Orchestration Error: {e}"
                                
                            supervisor_card.success("👤 **Supervisor Agent**: Finished.")
                            stream_placeholder.empty()
                            return response_text

                        # Run the MCP Agent with isolated event loop
                        response = asyncio.run(run_loop_safe())
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
        filter_types = st.multiselect("Log Levels", ["INFO", "SUCCESS", "WARNING", "ERROR"], 
                                    default=["INFO", "SUCCESS", "WARNING", "ERROR"], 
                                    label_visibility="collapsed")

    # Row 2: Actions (Next Line)
    b1, b2, b3, b4 = st.columns(4)
    with b1:
        st.button("🔄 Refresh", use_container_width=True, on_click=lambda: st.rerun())
    with b2:
        if st.button("🗑️ Clear", use_container_width=True):
                st.session_state.logs = []
                st.rerun()
    with b3:
        log_text = "\n".join([f"[{l['time']}] {l['type']}: {l['msg']}" for l in log_data])
        st.download_button("📄 Save TXT", data=log_text, file_name=f"log_{datetime.datetime.now().strftime('%H%M%S')}.txt", mime="text/plain", use_container_width=True)
    with b4:
        log_json = json.dumps(log_data, indent=2)
        st.download_button("💾 Save JSON", data=log_json, file_name=f"log_{datetime.datetime.now().strftime('%H%M%S')}.json", mime="application/json", use_container_width=True)

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
