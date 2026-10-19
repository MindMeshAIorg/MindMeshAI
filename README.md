#  MindMeshAI — Forgetfulness Firewall

**An AI-powered personal memory and commitment assistant that helps you remember important messages, deadlines, promises, and pending tasks from your conversations.**

MindMeshAI aims to transform everyday conversations into actionable memories. Instead of manually creating reminders, users can ask questions about past conversations and receive relevant information, while important commitments can be identified for follow-up notifications.

##  The Problem

Important information gets lost in everyday conversations:

- A friend asks you to return money on a particular date.
- Your manager assigns a task with a deadline in WhatsApp.
- An email contains an important meeting date or submission deadline.
- You promise someone that you will complete a task but forget about it later.
- You need to find when, where, or to whom you made a particular commitment.

Traditional reminder applications require users to manually create reminders. MindMeshAI aims to reduce this effort by extracting useful information from connected communication sources.

##  The Solution

MindMeshAI combines conversational AI, Retrieval-Augmented Generation (RAG), message processing, and notification workflows to build a searchable personal memory system.

Its core workflow is:

**Detect → Remember → Connect → Monitor → Verify → Intervene**

1. **Detect:** Process connected messages and identify potentially important information.
2. **Remember:** Store searchable conversation content and relevant metadata.
3. **Connect:** Retrieve context from previous conversations to answer questions.
4. **Monitor:** Track important commitments, deadlines, events, and pending responses.
5. **Verify:** Allow users to review and manage identified reminders.
6. **Intervene:** Deliver useful notifications and support reminder actions.

##  Key Features

###  Intelligent Reminder Workflow

The project includes a notification pipeline designed to identify and manage important information, including:

- `UNSEEN` — important information that has not yet been reviewed.
- `WORK` — tasks and work-related responsibilities.
- `DEADLINE` — time-sensitive submissions and deliverables.
- `COMMITMENT` — promises and obligations.
- `EVENT` — meetings and scheduled events.
- `WAITING_FOR` — responses, files, or actions expected from others.

###  Conversational Memory Search

Ask questions about your past WhatsApp conversations and emails using natural language.

Example questions:

- "When did I tell Zain I would return his money?"
- "What deadline did my manager mention?"
- "What work am I supposed to finish this week?"
- "Which messages contain important commitments?"
- "What am I waiting for someone to send me?"

MindMeshAI uses retrieval to find relevant context and generate an answer grounded in the available conversation data.

###  WhatsApp Integration

- Connect a personal WhatsApp account through a QR-based authentication flow supported by the WhatsApp MCP integration.
- Access available chat history through a read-only integration.
- Process messages and their metadata for search and analysis.
- Use conversation and message identifiers to help trace retrieved information back to its source.
- Support incremental synchronization using checkpoints, where configured.

###  Gmail Integration

- Connect Gmail through Google OAuth.
- Retrieve email content using the configured Gmail API permissions.
- Process emails for semantic retrieval and important information detection.
- Preserve email identifiers and relevant metadata for source tracking.

###  Retrieval-Augmented Generation (RAG)

MindMeshAI uses a RAG pipeline to answer questions using relevant stored conversation content rather than relying only on the language model's pretrained knowledge.

The pipeline includes:

1. Fetching messages and emails from connected sources.
2. Normalizing source data.
3. Splitting content into searchable chunks where appropriate.
4. Generating embeddings using `BAAI/bge-m3`.
5. Storing and retrieving vectors through Qdrant.
6. Supplying relevant context to the language model.
7. Generating a context-aware answer.


The intended notification workflow supports actionable reminders, with options such as marking an item complete or requesting a later reminder, depending on the configured notification interface.

###  Source-Aware Memory

Conversation records can include metadata such as:

- User and source identifiers
- Chat or conversation identifiers
- Message or email identifiers
- Sender and receiver information
- Timestamps
- Relevant content and classification metadata

This metadata helps associate retrieved information with its original source.


## Technology Stack

| Technology | Purpose |
|---|---|
| Python | Main application language |
| FastAPI | Backend APIs |
| LangChain / LLM integrations | Language-model and retrieval workflows, where configured |
| Qdrant | Vector storage and semantic retrieval |
| BAAI/bge-m3 | Text embeddings |
| PostgreSQL | Structured application data and reminder records |
| WhatsApp MCP | WhatsApp connection and message retrieval |
| Gmail API | Email retrieval |
| Google OAuth 2.0 | Gmail authentication |
| Pydantic | Request and data validation |
| Python dotenv | Environment variable configuration |
| Progressive Web App / Service Worker | Browser notification support, where configured |

