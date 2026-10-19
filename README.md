# 🧠 MindMeshAI

### AI-Powered Personal Assistant for Tasks, Deadlines & Reminders

MindMeshAI is an AI-powered productivity assistant that transforms scattered conversations and emails into actionable tasks and reminders. It identifies commitments, extracts deadlines, tracks changes, and helps users stay organized through an intelligent chatbot powered by Retrieval-Augmented Generation (RAG).

Instead of manually checking multiple platforms for important tasks, MindMeshAI brings relevant information together in one place.

## 🚀 Key Features

- **📩 Multi-Platform Integration:** Connects communication sources such as Gmail, Telegram, and WhatsApp.
- **🤖 Automatic Task Detection:** Identifies actionable commitments, assignments, meetings, and work-related tasks from messages and emails.
- **⏰ Smart Deadline Extraction:** Understands dates, times, and contextual deadlines to generate useful reminders.
- **🔄 Deadline Updates:** Detects changes in task deadlines and updates existing reminders where supported.
- **💬 AI-Powered Chatbot:** Answers questions using relevant information retrieved from connected data sources.
- **🔎 Hybrid Retrieval:** Combines semantic vector search and keyword-based retrieval to improve information discovery.
- **🔒 Privacy Filtering:** Redacts sensitive information, including OTPs, phone numbers, email addresses, and passwords, before storage where detected.
- **🛡️ Privacy Middleware:** Adds an additional layer of protection when processing user data.
- **🧠 Context-Aware Assistance:** Uses retrieved conversation and email context to provide relevant responses.

## 🏗️ System Architecture

MindMeshAI consists of a frontend, backend, communication connectors, data-processing pipelines, databases, and AI-powered components.

### Architecture Workflow

```text
             User Interface
        React + TypeScript + Tailwind
                     |
                     v
              FastAPI Backend
                     |
          Authentication / OAuth
                     |
          +----------+----------+
          |          |          |
        Gmail     Telegram   WhatsApp
          |          |          |
          +----------+----------+
                     |
                     v
          Data Ingestion Pipeline
                     |
          Normalization & Cleaning
                     |
             Privacy Filtering
                     |
          +----------+----------+
          |                     |
          v                     v
    Task Detection         RAG Pipeline
          |                     |
          v                     v
    Deadline Extraction    Retrieval System
          |                     |
          v                     v
    Reminder Generation    LLM Chatbot
          |                     |
          +----------+----------+
                     |
                     v
           PostgreSQL / Qdrant
```

*The diagram represents the overall architecture; individual integrations and processing steps depend on their implementation.*

## ⚙️ Technology Stack

| Component | Technologies |
|---|---|
| Frontend | React, TypeScript, Tailwind CSS |
| Backend | Python, FastAPI |
| Authentication | OAuth integrations |
| Relational Database | PostgreSQL |
| Vector Database | Qdrant |
| AI & Language Models | LLMs, Agentic AI |
| Retrieval | RAG, semantic search, BM25 |
| Data Processing | Normalization, cleaning, metadata handling |
| Privacy | PII detection and redaction middleware |
| Version Control | Git, GitHub |

## 🔄 How It Works

### 1. Connect Communication Sources
Users connect supported communication platforms to retrieve relevant messages and emails.

### 2. Ingest and Process Data
The connectors fetch messages, which are normalized into a consistent structure. Cleaning and metadata processing prepare the data for downstream pipelines.

### 3. Protect Sensitive Information
Privacy filters detect and redact supported sensitive information before records are stored, helping reduce unnecessary exposure of personal data.

### 4. Detect Tasks and Deadlines
The task-detection pipeline identifies commitments, extracts relevant deadlines, and converts actionable information into structured tasks and reminders.

### 5. Store and Retrieve Information
PostgreSQL stores structured application data, while Qdrant supports vector-based retrieval for relevant contextual information.

### 6. Generate Contextual Responses
The RAG pipeline retrieves relevant information and supplies it to the language model, enabling the chatbot to answer questions using available context.

## 🧠 AI & RAG Pipeline

The RAG system helps users retrieve information from their connected communication data.

The pipeline includes:

- Document and message ingestion
- Text cleaning and normalization
- Metadata extraction
- Text embeddings
- Vector storage using Qdrant
- Keyword-based retrieval using BM25
- Hybrid retrieval using semantic and keyword search
- Context retrieval for LLM-generated responses

This approach helps the chatbot find relevant information instead of relying only on the language model's pretrained knowledge.

## 🔐 Privacy & Security

MindMeshAI is designed with privacy as an important part of its data-processing workflow.

- **Sensitive Data Redaction:** Detects and redacts supported PII and secrets before database storage.
- **Privacy Middleware:** Provides an additional processing safeguard.
- **OAuth Authentication:** Enables authorized access to supported communication services.
- **Controlled Data Processing:** Normalizes and filters retrieved messages before passing relevant information to downstream components.

*Privacy filters can only redact information they successfully detect. Production deployments should also enforce secure credential management, access controls, encryption, and appropriate data-retention policies.*

## 💻 Getting Started

### Prerequisites

- Python 3.10 or later
- Node.js and npm
- Git
- Access to the required communication platform APIs
- PostgreSQL and Qdrant instances
- API credentials for the services you configure

### 1. Clone the Repository

```bash
git clone https://github.com/MindMeshAIorg/MindMeshAI.git
cd MindMeshAI
```

### 2. Configure Environment Variables

Create a `.env` file in the location expected by your application and configure the credentials and connection settings required by your enabled services.

Typical configuration categories include:

- Google OAuth credentials for Gmail
- Telegram API credentials
- PostgreSQL connection settings
- Qdrant connection settings
- LLM provider API credentials
- OAuth callback URLs

**Important:** Use your project's actual environment variable names and never commit `.env`, OAuth tokens, API keys, or other secrets to GitHub.

### 3. Install Dependencies

Install the Python and frontend dependencies using the dependency files and commands configured in the repository.

### 4. Start the Application

Run the FastAPI backend and React frontend using their respective development commands. Configure the frontend to communicate with the correct backend URL.

Refer to the project configuration for the exact commands, ports, and service-specific setup.

## 📂 Core Components

| Component | Responsibility |
|---|---|
| Frontend | User interface and chatbot interaction |
| FastAPI Backend | API endpoints and application logic |
| Connectors | Retrieve messages from supported platforms |
| Normalizer | Convert messages into a consistent data format |
| Privacy Filter | Detect and redact sensitive information |
| Task Detection | Identify actionable commitments and deadlines |
| PostgreSQL | Store structured application data |
| Qdrant | Store and retrieve vector embeddings |
| RAG Pipeline | Retrieve relevant context for chatbot responses |
| LLM | Generate contextual natural-language responses |

## 👥 Team

- **Abubakar**
- **Abdul Hannan**

## 🎯 Project Goal

MindMeshAI aims to eliminate the need to manually track commitments across multiple communication platforms by turning conversations into actionable reminders and making important information easier to find.

---

**MindMeshAI | Your conversations, organized into actions.**
