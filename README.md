# 🌤️ Weather MCP Agent: Global Intelligence System

## 🚀 Overview

The **Weather MCP Agent** is a state-of-the-art implementation of the **Model Context Protocol (MCP)**, designed to demonstrate the future of AI interoperability. Unlike traditional chatbots that hallucinate data, this agent uses a standardized protocol to "connect" to live tools—fetching real-time weather forecasts, alerts, and atmospheric analytics for **any city on Earth**.

Built on **Streamlit** for a reactive UI and powered by **Groq's LPU** for near-instant inference, this system showcases how **Agentic AI** can orchestrate complex workflows (Geocoding -> Weather API -> Conversational Synthesis) in milliseconds.

---

### 🌟 Key Capabilities
*   **🌍 Global Coverage**: Instant weather intelligence for 100,000+ cities worldwide.
*   **⚡ Hyper-Fast Inference**: Uses Llama 3 70B on Groq LPUs for sub-second reasoning.
*   **🔌 Standardized Tooling**: Built 100% on the open-source MCP standard.
*   **🗣️ Multi-Modal Input**: Supports both Text and Voice (WebRTC) interaction.
*   **🧠 Smart Context**: Maintains conversation history and context-aware responses.

---

## 🎮 Interface & Features by Tab

The application is structured into 5 professional modules, each serving a specific purpose in the Agentic workflow:

![Weather MCP Agent UI](assets/app_mockup.png)

### 1. 🚀 Project Demo (Interactive Core)
The command center of the application.
*   **AI Chat Interface**: Real-time conversation with the Agent.
*   **Quick Action Grid**: One-click execution for 16+ common scenarios.
*   **Smart City Extraction**: NLP-powered logic covers complex queries.
*   **Voice Input**: Speak naturally to the agent.

### 2. ℹ️ About Project (Educational Hub)
A detailed breakdown of the paradigm shift in AI.
*   **Evolution Timeline**: Visualizing the shift from Static LLMs -> Tool-Use Agents -> MCP Ecosystems.
*   **Protocol Comparison**: Why MCP is superior to proprietary plugin architectures.
*   **Interactive Simulations**: step-by-step walkthroughs of the agent's decision-making process.
### 3. 🛠️ Tech Stack (Under the Hood)
Transparency in engineering.
*   **AI Core**: Llama 3.3 70B (Reasoning), LangChain (Orchestration).
*   **Frontend**: Streamlit Async Runtime, Custom CSS theming.
*   **Connectivity**: `mcp-use` Client, `requests` library, RESTful APIs (Open-Meteo, NWS).


### 4. 🏗️ Architecture (System Design)
Enterprise-grade visualization of the system.
*   **Data Flow**: `User -> Streamlit -> Agent -> MCP Client -> Tool -> Response`.
*   **Graphviz Charts**: Dynamically generated DAGs (Directed Acyclic Graphs) of the agent's logic.
*   **Network Topology**: Visualizing how the Host, Client, and Server interact.

### 5. 📋 System Logs (Observability)
Production-ready monitoring.
*   **Real-time Event Stream**: Live tracking of every thought, tool call, and API response.
*   **Status Codes**: Visual indicators for `SUCCESS`, `ERROR`, and `INFO`.
*   **Audit Trails**: Downloadable JSON/TXT logs for debugging and analytics.
---

## 🛠️ Technology Stack

| Component | Technology | Purpose |
| :--- | :--- | :--- |
| **Orchestration** | **LangChain** | Manages the ReAct (Reason+Act) loop and prompt engineering. |
| **Protocol** | **MCP (Model Context Protocol)** | The universal standard for connecting AI models to external tools. |
| **Inference Engine** | **Groq LPU** | Provides the speed necessary for real-time agentic workflows. |
| **LLM** | **Llama 3.3 70B** | The "Brain" capable of complex tool selection and JSON parsing. |
| **Frontend** | **Streamlit** | Delivers a responsive, Python-native web interface. |
| **Data Source** | **Open-Meteo API** | Provides high-precision weather data without API keys. |
| **Audio** | **SpeechRecognition / WebRTC** | Handles voice-to-text conversion. |
| **Resilience** | **Circuit Breaker + Retry Pattern** | Prevents cascading failures, handles transient errors. |
| **Security** | **HMAC-SHA256 + RBAC + Policy Engine** | Cryptographic identity, role-based access, policy enforcement. |
| **Observability** | **Structured Logging + Trace Context** | End-to-end trace correlation, SLO metrics, JSON event logs. |
| **Persistence** | **SQLite WAL Mode** | Durable idempotency store, ACID guarantees. |

---

## ⚙️ Installation & Local Setup

Follow these steps to run the agent on your local machine.

### Prerequisites
*   Python 3.10+
*   A [Groq API Key](https://console.groq.com/) (Free)

### 1. Clone the Repository
```bash
git clone https://github.com/sohanpatil4600/MCP-A2A-Weather-Agent.git
cd MCP-A2A-Weather-Agent
```

### 2. Set Up Virtual Environment
```bash
set Groq API Key first

python -m venv venv
# Windows
venv\Scripts\activate
# Mac/Linux
source venv/bin/activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Configure Secrets
Create a `.env` file in the root directory:
```env
GROQ_API_KEY=your_actual_api_key_here
```

### 5. Run the App
```bash
python -m streamlit run Weather_streamlit_app.py
```

---

## 🐳 Large File Support (Git LFS)

This repository may contain large assets (images/diagrams). We use Git LFS to manage them efficiently.

```bash
# Install Git LFS
git lfs install

# Track large files
git lfs track "*.png"
git lfs track "*.jpg"

# Push to remote
git add .
git commit -m "Add large visual assets"
git push origin main
```
---


## 📞 Contact & Community

**Sohan Patil**  
*AI/Ml Engineer*

*   💼 **LinkedIn**: [sohanrpatil](https://www.linkedin.com/in/sohanrpatil/)
*   🐙 **GitHub**: [sohanpatil4600](https://github.com/sohanpatil4600)
---

## 💼 Professional Networks

[![LinkedIn](https://img.shields.io/badge/💼_LinkedIn-0077B5?style=for-the-badge&logo=linkedin&logoColor=white)](https://www.linkedin.com/in/sohanrpatil/)
[![GitHub](https://img.shields.io/badge/🐙_GitHub-181717?style=for-the-badge&logo=github&logoColor=white)](https://github.com/sohanpatil4600)
[![Portfolio](https://img.shields.io/badge/🌐_Portfolio-FF6B6B?style=for-the-badge&logo=google-chrome&logoColor=white)](https://portfolio-sohanpatil4600.vercel.app)
[![Email](https://img.shields.io/badge/✉️_Email-D14836?style=for-the-badge&logo=gmail&logoColor=white)](mailto:sohanpatil.usa@gmail.com)


