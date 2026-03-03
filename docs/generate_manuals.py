#!/usr/bin/env python3
"""Generate ULF Web User Manual and Admin Manual as PDF files."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fpdf import FPDF

LOGO_PATH = os.path.join(
    os.path.dirname(__file__), "..", "frontend", "images", "ULF-icon-1-black.png"
)
OUTPUT_DIR = os.path.dirname(__file__)
SCREENSHOT_DIR = os.path.join(os.path.dirname(__file__), "screenshots")

FONT_DIR = "/usr/share/fonts/truetype/dejavu"
FONT_NAME = "DejaVu"


class ManualPDF(FPDF):
    """Base PDF class with common formatting for ULF Web manuals."""

    def __init__(self, title: str, subtitle: str):
        super().__init__()
        self.manual_title = title
        self.manual_subtitle = subtitle
        self.set_auto_page_break(auto=True, margin=25)
        # Register Unicode font
        self.add_font(FONT_NAME, "", os.path.join(FONT_DIR, "DejaVuSans.ttf"))
        self.add_font(FONT_NAME, "B", os.path.join(FONT_DIR, "DejaVuSans-Bold.ttf"))
        # No italic DejaVu Sans available, use regular as fallback
        self.add_font(FONT_NAME, "I", os.path.join(FONT_DIR, "DejaVuSans.ttf"))

    def header(self):
        if self.page_no() == 1:
            return
        self.set_font(FONT_NAME, "I", 8)
        self.set_text_color(128, 128, 128)
        self.cell(0, 10, f"ULF Web \u2014 {self.manual_subtitle}", align="L")
        self.cell(0, 10, f"Page {self.page_no()}", align="R", new_x="LMARGIN", new_y="NEXT")
        self.set_draw_color(200, 200, 200)
        self.line(10, self.get_y(), 200, self.get_y())
        self.ln(5)

    def footer(self):
        self.set_y(-15)
        self.set_font(FONT_NAME, "I", 8)
        self.set_text_color(128, 128, 128)
        if self.page_no() > 1:
            self.cell(0, 10, f"\u00a9 ULF Web", align="C")

    def cover_page(self):
        self.add_page()
        self.ln(30)
        if os.path.exists(LOGO_PATH):
            self.image(LOGO_PATH, x=80, y=40, w=50)
        self.ln(70)
        self.set_font(FONT_NAME, "B", 28)
        self.set_text_color(30, 30, 30)
        self.cell(0, 15, "ULF Web", align="C", new_x="LMARGIN", new_y="NEXT")
        self.set_font(FONT_NAME, "", 20)
        self.set_text_color(80, 80, 80)
        self.cell(0, 12, self.manual_subtitle, align="C", new_x="LMARGIN", new_y="NEXT")
        self.ln(20)
        self.set_font(FONT_NAME, "", 12)
        self.set_text_color(100, 100, 100)
        self.cell(0, 8, "Version 1.0", align="C", new_x="LMARGIN", new_y="NEXT")
        self.cell(0, 8, "March 2026", align="C", new_x="LMARGIN", new_y="NEXT")

    def chapter_title(self, number: int, title: str):
        self.add_page()
        self.set_font(FONT_NAME, "B", 22)
        self.set_text_color(30, 30, 30)
        self.cell(0, 15, f"{number}. {title}", new_x="LMARGIN", new_y="NEXT")
        self.set_draw_color(60, 60, 60)
        self.line(10, self.get_y(), 200, self.get_y())
        self.ln(8)

    def section_title(self, title: str):
        self.ln(4)
        self.set_font(FONT_NAME, "B", 14)
        self.set_text_color(50, 50, 50)
        self.cell(0, 10, title, new_x="LMARGIN", new_y="NEXT")
        self.ln(2)

    def subsection_title(self, title: str):
        self.ln(2)
        self.set_font(FONT_NAME, "B", 11)
        self.set_text_color(60, 60, 60)
        self.cell(0, 8, title, new_x="LMARGIN", new_y="NEXT")
        self.ln(1)

    def body_text(self, text: str):
        self.set_font(FONT_NAME, "", 10)
        self.set_text_color(40, 40, 40)
        self.multi_cell(0, 5.5, text)
        self.ln(2)

    def bullet(self, text: str, indent: int = 0):
        x = self.get_x() + indent
        self.set_font(FONT_NAME, "", 10)
        self.set_text_color(40, 40, 40)
        self.set_x(x + 5)
        self.cell(5, 5.5, "\u2022")
        self.multi_cell(0, 5.5, text)
        self.ln(1)

    def bold_bullet(self, label: str, desc: str, indent: int = 0):
        x = self.get_x() + indent
        self.set_x(x + 5)
        self.set_font(FONT_NAME, "", 10)
        self.set_text_color(40, 40, 40)
        self.cell(5, 5.5, "\u2022")
        self.set_font(FONT_NAME, "B", 10)
        self.write(5.5, f"{label}: ")
        self.set_font(FONT_NAME, "", 10)
        self.multi_cell(0, 5.5, desc)
        self.ln(1)

    def note_box(self, text: str):
        self.ln(2)
        self.set_fill_color(240, 245, 255)
        self.set_draw_color(100, 140, 200)
        y = self.get_y()
        self.set_font(FONT_NAME, "B", 10)
        self.set_text_color(50, 80, 140)
        self.set_x(15)
        self.cell(0, 6, "Note:", new_x="LMARGIN", new_y="NEXT")
        self.set_font(FONT_NAME, "", 9)
        self.set_text_color(50, 80, 140)
        self.set_x(15)
        self.multi_cell(175, 5, text, fill=True)
        self.ln(4)

    def toc_page(self, entries: list[tuple[int, str]]):
        self.add_page()
        self.set_font(FONT_NAME, "B", 20)
        self.set_text_color(30, 30, 30)
        self.cell(0, 15, "Table of Contents", new_x="LMARGIN", new_y="NEXT")
        self.ln(8)
        self.set_font(FONT_NAME, "", 12)
        self.set_text_color(40, 40, 40)
        for num, title in entries:
            self.cell(0, 8, f"  {num}.  {title}", new_x="LMARGIN", new_y="NEXT")
        self.ln(5)


def _embed_screenshot(pdf: ManualPDF, filename: str, caption: str):
    """Embed a screenshot image with caption, or a placeholder if missing."""
    img_path = os.path.join(SCREENSHOT_DIR, filename)
    if os.path.exists(img_path):
        # Page-break check: need ~120mm for image + caption
        if pdf.get_y() > 160:
            pdf.add_page()
        pdf.ln(3)
        pdf.image(img_path, x=20, w=170)
        pdf.ln(2)
    else:
        if pdf.get_y() > 200:
            pdf.add_page()
        pdf.ln(3)
        pdf.set_fill_color(230, 230, 230)
        pdf.set_draw_color(180, 180, 180)
        pdf.rect(20, pdf.get_y(), 170, 30, style="DF")
        pdf.set_font(FONT_NAME, "I", 9)
        pdf.set_text_color(120, 120, 120)
        y_center = pdf.get_y() + 12
        pdf.set_xy(20, y_center)
        pdf.cell(170, 6, f"[Screenshot: {filename}]", align="C")
        pdf.set_y(pdf.get_y() + 22)
        pdf.ln(2)
    # Caption
    pdf.set_font(FONT_NAME, "I", 9)
    pdf.set_text_color(100, 100, 100)
    pdf.set_x(20)
    pdf.cell(170, 5, caption, align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)
    # Reset text color
    pdf.set_text_color(40, 40, 40)


# ---------------------------------------------------------------------------
# User Manual
# ---------------------------------------------------------------------------
def generate_user_manual():
    pdf = ManualPDF("ULF Web User Manual", "User Manual")
    pdf.cover_page()

    toc = [
        (1, "Introduction"),
        (2, "Getting Started"),
        (3, "Chat"),
        (4, "Translation"),
        (5, "Document Search"),
        (6, "Dictation"),
        (7, "Vault"),
        (8, "Settings"),
        (9, "Tips & Shortcuts"),
    ]
    pdf.toc_page(toc)

    # Chapter 1: Introduction
    pdf.chapter_title(1, "Introduction")
    pdf.body_text(
        "ULF Web is a private, self-hosted chat application that provides a web interface "
        "to local large language models (LLMs) running via llama.cpp. It runs entirely "
        "offline on your local network \u2014 no data ever leaves your machine."
    )
    pdf.body_text(
        "The application provides several AI-powered tools beyond basic chat:"
    )
    pdf.bullet("Chat \u2014 Conversational AI with file attachment support")
    pdf.bullet("Translation \u2014 Translate text between 50+ languages with text-to-speech")
    pdf.bullet("Document Search \u2014 Upload documents and query them using AI (GraphRAG)")
    pdf.bullet("Dictation \u2014 Speech-to-text transcription including multi-speaker meetings")
    pdf.bullet("Vault \u2014 Organized case management with AI-powered record analysis")

    pdf.section_title("Key Features")
    pdf.bullet("Completely offline \u2014 all processing happens locally")
    pdf.bullet("Real-time streaming responses")
    pdf.bullet("Multi-format document support (PDF, DOCX)")
    pdf.bullet("Image analysis with vision-capable models")
    pdf.bullet("Encrypted data storage")
    pdf.bullet("Per-user settings and conversation history")

    # Chapter 2: Getting Started
    pdf.chapter_title(2, "Getting Started")

    pdf.section_title("Logging In")
    pdf.body_text(
        "Open ULF Web in your browser. You will see a login screen where you enter "
        "your username and password. Your administrator will have created your account. "
        "If your system is configured in single-user mode, you will be logged in "
        "automatically without needing to enter credentials."
    )

    pdf.section_title("The Main Interface")
    pdf.body_text(
        "After logging in, you will see the main interface with two areas:"
    )
    pdf.bold_bullet("Sidebar (left)", "Contains the navigation tabs, your conversation "
                    "list, and user controls. On mobile devices, the sidebar can be "
                    "toggled with the menu button.")
    pdf.bold_bullet("Main Panel (right)", "Displays the active tool \u2014 Chat, "
                    "Translate, Docs, Dictation, or Vault \u2014 depending on which "
                    "tab is selected.")

    pdf.section_title("Navigation Tabs")
    pdf.body_text("The sidebar contains five tabs to switch between tools:")
    pdf.bold_bullet("Chat", "Conversational AI with your local LLM")
    pdf.bold_bullet("Translate", "Text translation between languages")
    pdf.bold_bullet("Docs", "Document search and question answering")
    pdf.bold_bullet("Dictation", "Speech-to-text transcription")
    pdf.bold_bullet("Vault", "Case and record management")

    pdf.section_title("User Controls")
    pdf.body_text(
        "At the bottom of the sidebar you will find:"
    )
    pdf.bold_bullet("User Badge", "Click your username to change your password")
    pdf.bold_bullet("Settings", "Open the LLM settings modal (gear icon)")
    pdf.bold_bullet("Admin", "Access the admin panel (only visible to admin users)")
    pdf.bold_bullet("Logout", "End your session and return to the login screen")

    # Chapter 3: Chat
    pdf.chapter_title(3, "Chat")

    pdf.section_title("Starting a Conversation")
    pdf.body_text(
        "Click the \"New Chat\" button in the sidebar to start a new conversation. "
        "Your conversations are listed in the sidebar and persist across sessions. "
        "Click any conversation to resume it."
    )

    pdf.section_title("Sending Messages")
    pdf.body_text(
        "Type your message in the input area at the bottom of the chat panel and press "
        "Enter or click the Send button. The AI will respond in real time \u2014 you can "
        "see the response appear word by word as it is generated."
    )
    pdf.body_text(
        "While the AI is generating a response, you can click the Stop button to "
        "halt generation at any time."
    )

    pdf.section_title("Auto-Titling")
    pdf.body_text(
        "The first time you send a message in a new conversation, ULF Web will "
        "automatically generate a title based on your message. You can rename a "
        "conversation at any time by clicking on its title in the sidebar."
    )

    pdf.section_title("File Attachments")
    pdf.body_text(
        "You can attach files to your messages to provide context to the AI:"
    )
    pdf.bold_bullet("PDF Documents", "Text is extracted from the PDF and included "
                    "as context in your message. The AI can then answer questions "
                    "about the document content.")
    pdf.bold_bullet("DOCX Documents", "Word documents are similarly extracted to "
                    "text and provided as context.")
    pdf.bold_bullet("Images", "If the active model supports vision (multimodal), "
                    "images are sent to the model for visual analysis. The AI can "
                    "describe, analyze, and answer questions about images.")
    pdf.body_text(
        "Attached files appear as visual indicators below the input area. "
        "You can remove an attachment before sending by clicking the remove button."
    )

    pdf.section_title("Vault Context (@Case)")
    pdf.body_text(
        "You can reference Vault cases in your chat messages by typing \"@\" followed "
        "by the case name. When you send the message, recent records from the "
        "referenced case are automatically included as context, allowing the AI "
        "to answer questions about your case data."
    )

    pdf.section_title("Token Counter")
    pdf.body_text(
        "A token counter is displayed near the input area, showing an estimate of "
        "your message size. This helps you stay within the model's context window. "
        "The counter updates as you type."
    )

    pdf.section_title("Managing Conversations")
    pdf.bullet("Rename \u2014 Click the conversation title in the sidebar to edit it")
    pdf.bullet("Delete \u2014 Click the delete icon next to a conversation to remove it "
               "and all its messages")

    pdf.note_box(
        "Conversation history is automatically managed to fit within the model's "
        "context window. Older messages may be trimmed from the context if the "
        "conversation grows very long, but they remain stored in the database."
    )

    # Chapter 4: Translation
    pdf.chapter_title(4, "Translation")

    pdf.section_title("Translating Text")
    pdf.body_text(
        "The Translation tab provides a side-by-side translation interface. "
        "Select your source and target languages from the dropdown menus, enter "
        "your text, and click Translate."
    )

    pdf.section_title("How to Use")
    pdf.bullet("Select the source language from the left dropdown (or leave for auto-detect)")
    pdf.bullet("Enter the text you want to translate in the left text area")
    pdf.bullet("Select the target language from the right dropdown")
    pdf.bullet("Click the Translate button")
    pdf.bullet("The translation appears in the right text area in real time")

    pdf.section_title("Additional Features")
    pdf.bold_bullet("Swap Languages", "Click the swap button between the language "
                    "dropdowns to quickly reverse the translation direction, including "
                    "any text already entered.")
    pdf.bold_bullet("Text-to-Speech", "Click the speaker icon to hear the translated "
                    "text read aloud. The system automatically detects the language "
                    "and selects an appropriate voice.")
    pdf.bold_bullet("Stop", "Click Stop to halt an in-progress translation.")

    pdf.section_title("Supported Languages")
    pdf.body_text(
        "ULF Web supports translation between 50+ languages including Icelandic, "
        "English, Norwegian, Swedish, Danish, German, French, Spanish, Italian, "
        "Portuguese, Dutch, Russian, Chinese, Japanese, Korean, Arabic, Hindi, "
        "and many more."
    )

    # Chapter 5: Document Search
    pdf.chapter_title(5, "Document Search")

    pdf.section_title("Overview")
    pdf.body_text(
        "The Document Search feature (Docs tab) allows you to upload PDF and DOCX "
        "documents into collections and then ask questions about their content. "
        "ULF Web uses a combination of semantic search, full-text search, and "
        "knowledge graph extraction (GraphRAG) to find relevant information and "
        "generate answers with source citations."
    )

    pdf.section_title("Working with Collections")
    pdf.body_text(
        "Documents are organized into collections. Select a collection from the "
        "dropdown at the top of the Docs panel. Your administrator creates and "
        "manages collections."
    )

    pdf.section_title("Uploading Documents")
    pdf.bullet("Select a collection from the dropdown")
    pdf.bullet("Click the Upload button")
    pdf.bullet("Choose a PDF or DOCX file")
    pdf.bullet("The document will be processed in the background")
    pdf.body_text(
        "Processing includes text extraction, chunking, embedding generation, "
        "and optional entity extraction. A status indicator shows the processing "
        "progress. You can upload additional documents while others are being processed."
    )

    pdf.section_title("Querying Documents")
    pdf.bullet("Ensure a collection with processed documents is selected")
    pdf.bullet("Type your question in the query text area")
    pdf.bullet("Click Search")
    pdf.bullet("The AI-generated answer appears with source citations")
    pdf.body_text(
        "Source citations show which documents and sections were used to compose "
        "the answer, helping you verify the information."
    )

    pdf.section_title("Viewing Documents")
    pdf.body_text(
        "Click the Documents List toggle to see all documents in the current "
        "collection. The list shows each document's name, status, and "
        "processing information."
    )

    # Chapter 6: Dictation
    pdf.chapter_title(6, "Dictation")

    pdf.section_title("Overview")
    pdf.body_text(
        "The Dictation tab provides speech-to-text transcription powered by "
        "OpenAI's Whisper model, running locally. It supports two modes: "
        "standard single-speaker dictation and multi-speaker meeting transcription."
    )

    pdf.section_title("Standard Dictation")
    pdf.bullet("Select your language from the dropdown (or leave for auto-detect)")
    pdf.bullet("Click the Dictate button to start recording")
    pdf.bullet("Speak clearly into your microphone")
    pdf.bullet("A recording indicator shows elapsed time and audio level")
    pdf.bullet("Click Stop to end recording")
    pdf.bullet("The transcription appears in the result area")
    pdf.bullet("Click Copy to copy the text to your clipboard")

    pdf.section_title("Meeting Dictation")
    pdf.body_text(
        "Meeting mode is designed for recording conversations with multiple speakers. "
        "It includes speaker diarization \u2014 automatically detecting and labeling "
        "different speakers."
    )
    pdf.bullet("Select the meeting language from the dropdown")
    pdf.bullet("Click the Dictate Meeting button to start recording")
    pdf.bullet("The recording captures audio in chunks for reliable processing")
    pdf.bullet("Click Stop when the meeting is finished")
    pdf.body_text("Processing then proceeds through several stages:")
    pdf.bullet("Assembling \u2014 Audio chunks are combined", indent=5)
    pdf.bullet("Diarizing \u2014 Speakers are detected and separated", indent=5)
    pdf.bullet("Transcribing \u2014 Each speaker's segments are transcribed", indent=5)
    pdf.body_text(
        "A progress bar shows the current stage. The final transcript "
        "includes speaker labels (Speaker 1, Speaker 2, etc.) with timestamps."
    )

    pdf.section_title("Supported Languages")
    pdf.body_text(
        "The dictation system supports Icelandic, English, Norwegian, Swedish, "
        "Danish, German, French, Spanish, Italian, and many more languages "
        "via the Whisper model."
    )

    # Chapter 7: Vault
    pdf.chapter_title(7, "Vault")

    pdf.section_title("Overview")
    pdf.body_text(
        "The Vault is a case management system for organizing structured records. "
        "Each case can contain text notes, documents (PDFs), and images. The AI "
        "automatically generates descriptions and summaries to help you work "
        "with your case data."
    )

    pdf.section_title("Creating a Case")
    pdf.bullet("Click the New Case button in the Vault tab")
    pdf.bullet("Enter a unique identifier (e.g., a case number)")
    pdf.bullet("Enter a descriptive name")
    pdf.bullet("Optionally add a description")
    pdf.bullet("Choose whether the case is public (visible to all users) or private")
    pdf.bullet("Click Create")

    pdf.section_title("Case Status")
    pdf.body_text("Each case has a status that indicates its state:")
    pdf.bold_bullet("Active", "The case is open and actively being worked on")
    pdf.bold_bullet("Closed", "The case is resolved but preserved for reference")
    pdf.bold_bullet("Archived", "The case is stored long-term and no longer active")

    pdf.section_title("Adding Records")
    pdf.body_text(
        "Open a case by clicking on it, then add records of three types:"
    )
    pdf.bold_bullet("Text Records", "Free-form text notes. Enter a title, date, and "
                    "content. Useful for observations, summaries, or meeting notes.")
    pdf.bold_bullet("Document Records", "Upload PDF files. The AI will automatically "
                    "generate a summary of the document content.")
    pdf.bold_bullet("Image Records", "Upload images. If a vision-capable model is "
                    "configured, the AI will automatically generate a description of "
                    "the image.")

    pdf.section_title("Working with Records")
    pdf.bold_bullet("Star Records", "Click the star icon to mark important records. "
                    "Starred records are highlighted for quick reference.")
    pdf.bold_bullet("Delete Records", "Click the delete button to remove a record "
                    "from the case.")
    pdf.bold_bullet("View Inline", "Images are displayed inline in the case view. "
                    "Documents can be downloaded.")

    pdf.section_title("AI Summaries")
    pdf.body_text(
        "ULF Web automatically generates AI descriptions for uploaded images "
        "and documents. It also maintains an overall case summary that "
        "aggregates information from all records. These summaries are "
        "updated whenever records are added or removed."
    )

    pdf.section_title("Searching Cases")
    pdf.body_text(
        "Use the search bar at the top of the Vault panel to find cases by "
        "name or identifier. The search filters the case list in real time."
    )

    pdf.section_title("Exporting Cases")
    pdf.body_text("Cases can be exported in two formats:")
    pdf.bold_bullet("PDF Export", "Generates a formatted PDF document containing "
                    "the case metadata, description, AI summary, and all records "
                    "with embedded images and documents.")
    pdf.bold_bullet("JSON Export", "Exports the case data as a JSON file containing "
                    "all text content, metadata, and timestamps for programmatic use.")

    pdf.section_title("Using Cases in Chat")
    pdf.body_text(
        "You can reference vault cases in chat conversations using the @Case "
        "syntax. When a case is referenced, its recent records are included "
        "as context, allowing the AI to answer questions about the case data "
        "directly in the chat."
    )

    # Chapter 8: Settings
    pdf.chapter_title(8, "Settings")

    pdf.section_title("Accessing Settings")
    pdf.body_text(
        "Click the gear icon in the sidebar to open the Settings modal. These "
        "settings control how the AI generates responses and are saved per user."
    )

    pdf.section_title("LLM Parameters")
    pdf.bold_bullet("Temperature (0.0 \u2013 2.0)",
                    "Controls the randomness of responses. Lower values (e.g., 0.2) "
                    "produce more focused, deterministic answers. Higher values "
                    "(e.g., 1.5) produce more creative, varied responses. "
                    "Default: 0.7")
    pdf.bold_bullet("Top K (1 \u2013 100)",
                    "Limits the number of tokens considered at each step. Lower "
                    "values restrict the model to the most likely tokens. "
                    "Default: 40")
    pdf.bold_bullet("Top P (0.0 \u2013 1.0)",
                    "Nucleus sampling \u2014 only considers tokens whose cumulative "
                    "probability reaches this threshold. Lower values produce more "
                    "focused text. Default: 0.9")
    pdf.bold_bullet("Repeat Penalty (1.0 \u2013 2.0)",
                    "Penalizes the model for repeating the same words or phrases. "
                    "Higher values reduce repetition. Default: 1.1")
    pdf.bold_bullet("Max Tokens (256 \u2013 8192)",
                    "Maximum number of tokens in the AI's response. Higher values "
                    "allow longer responses. Default: 2048")
    pdf.bold_bullet("System Prompt",
                    "Custom instructions that are included at the beginning of every "
                    "conversation. Use this to set the AI's persona, behavior, "
                    "or specific instructions.")

    pdf.note_box(
        "Settings are saved automatically when you close the modal and persist "
        "across sessions. Each user has their own independent settings."
    )

    # Chapter 9: Tips & Shortcuts
    pdf.chapter_title(9, "Tips & Shortcuts")

    pdf.section_title("Keyboard Shortcuts")
    pdf.bold_bullet("Enter", "Send message (in chat and translation)")
    pdf.bold_bullet("Shift+Enter", "New line in the message input")

    pdf.section_title("Best Practices")
    pdf.bullet(
        "Be specific in your questions \u2014 the AI performs better with clear, "
        "detailed prompts"
    )
    pdf.bullet(
        "Use the system prompt to set context for your session (e.g., "
        "\"You are a legal expert\" or \"Respond in Icelandic\")"
    )
    pdf.bullet(
        "For document search, phrase your questions as complete questions "
        "rather than keywords"
    )
    pdf.bullet(
        "Use vault cases to organize information over time, then reference "
        "them in chat for contextual answers"
    )
    pdf.bullet(
        "Lower temperature for factual tasks (analysis, coding, translation); "
        "higher for creative tasks (brainstorming, writing)"
    )
    pdf.bullet(
        "If responses are being cut short, increase the Max Tokens setting"
    )

    pdf.section_title("Changing Your Password")
    pdf.body_text(
        "Click your username badge in the sidebar to open the password change "
        "dialog. You will need to enter your current password and your new "
        "password to confirm the change."
    )

    pdf.section_title("Privacy & Security")
    pdf.body_text(
        "All data in ULF Web is stored locally and encrypted at rest. Your "
        "conversations, documents, vault records, and all AI processing "
        "happen entirely on your local network. No data is sent to external "
        "servers or cloud services."
    )

    output_path = os.path.join(OUTPUT_DIR, "UlfWeb_User_Manual.pdf")
    pdf.output(output_path)
    print(f"User Manual saved to: {output_path}")


# ---------------------------------------------------------------------------
# Admin Manual
# ---------------------------------------------------------------------------
def generate_admin_manual():
    pdf = ManualPDF("ULF Web Admin Manual", "Admin Manual")
    pdf.cover_page()

    toc = [
        (1, "Introduction"),
        (2, "Installation & Configuration"),
        (3, "Server Management"),
        (4, "User Management"),
        (5, "AI Service Configuration"),
        (6, "Document Collections"),
        (7, "Security & Encryption"),
        (8, "Monitoring & Analytics"),
        (9, "Maintenance & Troubleshooting"),
    ]
    pdf.toc_page(toc)

    # Chapter 1: Introduction
    pdf.chapter_title(1, "Introduction")
    pdf.body_text(
        "This manual covers the administration of ULF Web, a self-hosted AI "
        "chat platform that runs entirely offline using llama.cpp as its LLM "
        "backend. As an administrator, you are responsible for managing LLM "
        "servers, user accounts, AI service assignments, document collections, "
        "and system monitoring."
    )
    pdf.body_text(
        "The admin panel is accessible at /admin and is only available to users "
        "with the admin role. Admin controls are separate from the main user "
        "interface and do not affect the user experience unless configuration "
        "changes are made."
    )

    pdf.section_title("System Architecture")
    pdf.body_text("ULF Web consists of several components:")
    pdf.bold_bullet("FastAPI Backend", "Python application that serves the API, "
                    "manages the database, and orchestrates AI services")
    pdf.bold_bullet("Frontend", "Vanilla JavaScript single-page application served "
                    "as static files. No build step required.")
    pdf.bold_bullet("SQLite/SQLCipher Database", "Stores all application data "
                    "with optional encryption at rest")
    pdf.bold_bullet("llama.cpp Servers", "One or more LLM server processes, each "
                    "loading a GGUF model file for inference")
    pdf.bold_bullet("Whisper", "Speech-to-text model for dictation features")
    pdf.bold_bullet("TTS Engine", "Text-to-speech for translation audio playback")

    # Chapter 2: Installation & Configuration
    pdf.chapter_title(2, "Installation & Configuration")

    pdf.section_title("Prerequisites")
    pdf.bullet("Python 3.10 or later")
    pdf.bullet("llama.cpp compiled with the llama-server binary")
    pdf.bullet("GGUF model files for the LLMs you wish to use")
    pdf.bullet("Sufficient RAM/VRAM for your chosen models")

    pdf.section_title("Installation")
    pdf.body_text("Set up ULF Web with the following steps:")
    pdf.bullet("Clone the repository to your server")
    pdf.bullet("Create and activate a Python virtual environment:")
    pdf.body_text("    python3 -m venv .venv && source .venv/bin/activate")
    pdf.bullet("Install dependencies:")
    pdf.body_text("    pip install -r requirements.txt")
    pdf.bullet("Configure the application (see Configuration below)")
    pdf.bullet("Start the server:")
    pdf.body_text("    python3 -m backend.main")

    pdf.section_title("Configuration File (config.yaml)")
    pdf.body_text(
        "The primary configuration file is config.yaml in the project root. "
        "It controls the server, database, LLM defaults, and paths."
    )

    pdf.subsection_title("Server Settings")
    pdf.bold_bullet("host", "Bind address for the web server. Default: 0.0.0.0 "
                    "(all interfaces)")
    pdf.bold_bullet("port", "HTTP port. Default: 8000")

    pdf.subsection_title("Database Settings")
    pdf.bold_bullet("path", "Path to the SQLite database file. Default: data/ulfweb.db")

    pdf.subsection_title("Model Settings")
    pdf.bold_bullet("models.path", "Directory containing GGUF model files. "
                    "The admin panel scans this directory for available models.")
    pdf.bold_bullet("models.llama_server", "Path to the llama-server executable")

    pdf.subsection_title("Encryption Settings")
    pdf.bold_bullet("encryption.enabled", "Enable encryption at rest (true/false). "
                    "Default: true")
    pdf.bold_bullet("encryption.key_file", "Path to the encryption key file. "
                    "Default: data/encryption.key")

    pdf.subsection_title("Default LLM Parameters")
    pdf.body_text(
        "The defaults section sets the initial LLM parameters for new users:"
    )
    pdf.bold_bullet("temperature", "Default: 0.7")
    pdf.bold_bullet("top_k", "Default: 40")
    pdf.bold_bullet("top_p", "Default: 0.9")
    pdf.bold_bullet("repeat_penalty", "Default: 1.1")
    pdf.bold_bullet("max_tokens", "Default: 2048")
    pdf.bold_bullet("system_prompt", "Default: \"You are a helpful assistant.\"")

    pdf.section_title("Environment Variables")
    pdf.body_text(
        "Configuration values can be overridden with environment variables "
        "using the ULFWEB_ prefix:"
    )
    pdf.bullet("ULFWEB_LLAMA_URL \u2014 Override the default LLM server URL")
    pdf.bullet("ULFWEB_DATABASE_PATH \u2014 Override the database file path")
    pdf.bullet("ULFWEB_SERVER_HOST \u2014 Override the bind address")
    pdf.bullet("ULFWEB_SERVER_PORT \u2014 Override the HTTP port")

    # Chapter 3: Server Management
    pdf.chapter_title(3, "Server Management")

    pdf.section_title("Overview")
    pdf.body_text(
        "ULF Web can manage multiple llama.cpp server instances, each running "
        "a different model. This allows you to assign specialized models to "
        "different tasks (chat, translation, document analysis, etc.) and "
        "run them concurrently."
    )

    pdf.section_title("Adding a Server")
    pdf.body_text(
        "Click the Add Server button in the admin panel's Servers section. "
        "Configure the following settings:"
    )
    pdf.bold_bullet("Friendly Name", "A descriptive name for the server "
                    "(e.g., \"Chat - Llama 3.1 8B\")")
    pdf.bold_bullet("URL", "The server URL and port. Leave empty for auto-assigned "
                    "port. If managing external servers, enter the full URL.")
    pdf.bold_bullet("Model Path", "Select a GGUF model file from the dropdown. "
                    "Models are scanned from the configured models directory.")
    pdf.bold_bullet("Parallel Slots (1\u20134)", "Number of concurrent request slots. "
                    "Higher values allow more simultaneous users but require more "
                    "memory. Default: 1")
    pdf.bold_bullet("Context Size", "Context window size in tokens. Options range "
                    "from 8K to 128K. Larger contexts require more memory. "
                    "Default: 32768")
    pdf.bold_bullet("Active", "Whether this server is available for use")
    pdf.bold_bullet("Autoload on Startup", "When enabled, this server will "
                    "automatically start when ULF Web launches. Useful for "
                    "ensuring key services are always available without manual "
                    "intervention after a reboot or restart.")

    pdf.section_title("Starting and Stopping Servers")
    pdf.body_text("Each server has three control buttons:")
    pdf.bold_bullet("Start", "Launch the llama.cpp process with the configured "
                    "model and settings")
    pdf.bold_bullet("Stop", "Gracefully shut down the server process")
    pdf.bold_bullet("Restart", "Stop and restart the server (useful after "
                    "changing settings)")
    pdf.body_text(
        "A status indicator shows whether the server is running (green), "
        "stopped (gray), or in an error state (red)."
    )

    pdf.section_title("Autoload on Startup")
    pdf.body_text(
        "Servers with the Autoload option enabled are automatically started "
        "when ULF Web launches. This is useful for production deployments "
        "where you want key models to be immediately available after a "
        "system reboot or application restart."
    )
    pdf.body_text(
        "During startup, ULF Web iterates through all active servers that "
        "have autoload enabled and a model path configured, and starts them "
        "in sequence. If a server fails to autoload (e.g., insufficient "
        "memory), the error is logged and the remaining servers continue "
        "to start normally."
    )
    pdf.note_box(
        "Ensure your system has enough RAM and VRAM to load all autoload "
        "servers simultaneously. Check System Info after startup to verify "
        "all expected servers are running."
    )

    pdf.section_title("Server Logs")
    pdf.body_text(
        "Click the View Log button on any server to see the last 200 lines "
        "of its log output. This is useful for diagnosing startup problems, "
        "monitoring model loading, and checking for errors."
    )

    pdf.section_title("Memory Considerations")
    pdf.body_text(
        "Each running server loads its model into RAM and/or GPU VRAM. Use the "
        "System Info panel to monitor memory usage. Consider:"
    )
    pdf.bullet("Larger models require more memory (7B ~ 4\u20138 GB, 13B ~ 8\u201316 GB)")
    pdf.bullet("Larger context sizes increase memory usage")
    pdf.bullet("Multiple parallel slots multiply memory requirements")
    pdf.bullet("Running multiple servers simultaneously requires sufficient total memory")

    pdf.note_box(
        "If a server fails to start, check the server log for error messages. "
        "Common causes include insufficient memory, invalid model paths, or "
        "port conflicts."
    )

    # Chapter 4: User Management
    pdf.chapter_title(4, "User Management")

    pdf.section_title("User Accounts")
    pdf.body_text(
        "Click the Users button in the admin panel header to manage user "
        "accounts. Users are authenticated with usernames and passwords "
        "(bcrypt-hashed)."
    )

    pdf.section_title("Creating Users")
    pdf.body_text("When creating a new user, provide:")
    pdf.bold_bullet("Username", "A unique login name")
    pdf.bold_bullet("Password", "The user's initial password")
    pdf.bold_bullet("User Type", "\"normal\" for regular users, \"admin\" for "
                    "administrator access")
    pdf.bold_bullet("Full Name", "Optional display name")
    pdf.bold_bullet("Description", "Optional notes about the user")

    pdf.section_title("Managing Users")
    pdf.bullet("Edit user details (name, type, description)")
    pdf.bullet("Reset user passwords")
    pdf.bullet("Delete users (you cannot delete your own account)")
    pdf.body_text(
        "When a user is deleted, their sessions are immediately invalidated. "
        "Conversations and vault data belonging to the user are also removed."
    )

    pdf.section_title("Single-User Mode")
    pdf.body_text(
        "In the Authentication section of the admin panel, you can select a "
        "user for single-user mode. When enabled, all visitors to ULF Web "
        "are automatically logged in as the selected user without needing "
        "to enter credentials."
    )
    pdf.body_text(
        "This is useful for personal or single-person deployments where "
        "login overhead is unnecessary. Set the dropdown to empty to require "
        "normal login."
    )

    pdf.note_box(
        "Single-user mode bypasses authentication entirely. Only use this "
        "in trusted, private network environments."
    )

    # Chapter 5: AI Service Configuration
    pdf.chapter_title(5, "AI Service Configuration")

    pdf.section_title("Overview")
    pdf.body_text(
        "Different features in ULF Web can use different LLM servers. This "
        "allows you to assign specialized models to tasks they are best "
        "suited for \u2014 for example, a large model for chat and a smaller, "
        "faster model for translation."
    )

    pdf.section_title("Service Assignments")
    pdf.body_text(
        "The admin panel has several sections for assigning servers to "
        "specific AI services:"
    )

    pdf.subsection_title("Chat")
    pdf.bold_bullet("Chat Server", "The server used for chat conversations. "
                    "If not set, the first active server is used.")

    pdf.subsection_title("Translation")
    pdf.bold_bullet("Translation Server", "The server used for text translation. "
                    "If not set, the first active server is used.")

    pdf.subsection_title("Document AI")
    pdf.bold_bullet("Query Server", "Handles document search questions \u2014 "
                    "generates answers from retrieved chunks")
    pdf.bold_bullet("Extraction Server", "Extracts entities and relationships "
                    "from documents for the knowledge graph")
    pdf.bold_bullet("Understanding Server", "Generates contextual summaries "
                    "for document chunks")
    pdf.bold_bullet("Skip Contextual Retrieval", "When enabled, skips the "
                    "contextual retrieval step to speed up document processing "
                    "at the cost of some accuracy")

    pdf.subsection_title("Vault")
    pdf.bold_bullet("Image Analysis Server", "Generates AI descriptions for "
                    "uploaded images (requires a vision-capable model)")
    pdf.bold_bullet("Text Analysis Server", "Generates AI summaries for "
                    "uploaded documents and overall case summaries")
    pdf.bold_bullet("Chat Context Records", "Number of recent vault records "
                    "included when a case is referenced in chat (5, 10, 20, or all)")

    pdf.subsection_title("Dictation")
    pdf.bold_bullet("Whisper Model", "Select the speech-to-text model. Larger "
                    "models are more accurate but slower and require more memory. "
                    "Available options: tiny, base, small, medium, large-v3, "
                    "large-v3-turbo, and a specialized Icelandic model.")

    pdf.section_title("Display Settings")
    pdf.bold_bullet("Date Format", "Controls how dates are displayed throughout "
                    "the application. Options: YYYY-MM-DD (ISO), DD/MM/YYYY "
                    "(European), MM/DD/YYYY (US), DD.MM.YYYY (Continental), "
                    "D MMM YYYY (Short month)")

    pdf.note_box(
        "If a configured server is stopped or deleted, the system falls back "
        "to the first available active server. If no servers are running, "
        "AI features will return errors."
    )

    # Chapter 6: Document Collections
    pdf.chapter_title(6, "Document Collections")

    pdf.section_title("Overview")
    pdf.body_text(
        "Document collections organize uploaded files for AI-powered search. "
        "Each collection is independent and can contain multiple PDF and DOCX "
        "documents. Administrators create and manage collections; users can "
        "upload documents and query them."
    )

    pdf.section_title("Creating a Collection")
    pdf.body_text(
        "In the Document Collections section of the admin panel (or via "
        "the main interface), click Add Collection and provide:"
    )
    pdf.bold_bullet("Name", "A unique, descriptive name for the collection")
    pdf.bold_bullet("Description", "Optional description of the collection's purpose")

    pdf.section_title("Document Processing Pipeline")
    pdf.body_text(
        "When a document is uploaded to a collection, it goes through a "
        "multi-stage processing pipeline:"
    )
    pdf.bullet("1. Text extraction \u2014 Content is extracted from PDF/DOCX")
    pdf.bullet("2. Chunking \u2014 Text is split into manageable segments")
    pdf.bullet("3. Embedding \u2014 Each chunk is encoded as a vector using "
               "the paraphrase-multilingual-mpnet-base-v2 model")
    pdf.bullet("4. Full-text indexing \u2014 BM25 index for keyword search")
    pdf.bullet("5. Entity extraction \u2014 Named entities and relationships "
               "are identified (GraphRAG)")
    pdf.bullet("6. Contextual retrieval \u2014 Each chunk gets a contextual "
               "prefix summarizing its role (optional)")

    pdf.body_text(
        "Processing happens in the background. The document status changes "
        "from \"pending\" to \"processing\" to \"ready\" (or \"error\" if "
        "something fails)."
    )

    pdf.section_title("Query System")
    pdf.body_text("When a user queries a collection, the system:")
    pdf.bullet("Runs BM25 full-text search on the query")
    pdf.bullet("Runs vector similarity search on the query embedding")
    pdf.bullet("Combines and ranks results (hybrid search)")
    pdf.bullet("Sends top-ranked chunks to the LLM for answer generation")
    pdf.bullet("Returns the answer with source citations")

    pdf.section_title("Managing Collections")
    pdf.bullet("Edit collection name and description")
    pdf.bullet("Upload additional documents")
    pdf.bullet("Delete individual documents")
    pdf.bullet("Delete entire collections (removes all documents and indexes)")

    pdf.note_box(
        "Document processing requires an active LLM server for entity "
        "extraction and contextual retrieval. Ensure the relevant Document "
        "AI servers are configured and running before uploading documents."
    )

    # Chapter 7: Security & Encryption
    pdf.chapter_title(7, "Security & Encryption")

    pdf.section_title("Authentication")
    pdf.body_text("ULF Web uses session-based authentication:")
    pdf.bullet("Passwords are hashed with bcrypt")
    pdf.bullet("Sessions are stored as HTTP-only cookies (7-day expiration)")
    pdf.bullet("SameSite=Lax cookie policy prevents CSRF attacks")
    pdf.bullet("Expired sessions are cleaned up automatically on startup")

    pdf.section_title("Authorization")
    pdf.bullet("Users can only access their own conversations, settings, "
               "and private vault cases")
    pdf.bullet("Public vault cases are readable by all authenticated users")
    pdf.bullet("Admin endpoints require admin role")
    pdf.bullet("Users cannot delete their own admin account")

    pdf.section_title("Encryption at Rest")
    pdf.body_text(
        "ULF Web supports two layers of encryption for data at rest:"
    )

    pdf.subsection_title("Database Encryption (SQLCipher)")
    pdf.body_text(
        "When encryption is enabled in config.yaml, the SQLite database is "
        "encrypted using SQLCipher. A 32-byte encryption key is automatically "
        "generated on first run and stored in the configured key file "
        "(default: data/encryption.key)."
    )

    pdf.subsection_title("File Encryption (Fernet)")
    pdf.body_text(
        "Vault files (uploaded documents and images) are encrypted using "
        "the Fernet symmetric encryption scheme. Files are encrypted when "
        "stored and decrypted when accessed."
    )

    pdf.subsection_title("Automatic Migration")
    pdf.body_text(
        "If you enable encryption on an existing installation, ULF Web "
        "automatically migrates the unencrypted database to an encrypted "
        "format. A backup of the original unencrypted database is created "
        "as data/ulfweb.db.unencrypted_backup."
    )

    pdf.note_box(
        "CRITICAL: Back up your encryption key file (data/encryption.key). "
        "If this file is lost, all encrypted data becomes irrecoverable. "
        "Store a copy in a secure location outside the application directory."
    )

    pdf.section_title("Activity Logging")
    pdf.body_text(
        "All user actions are recorded in the activity log, including:"
    )
    pdf.bullet("Login/logout events")
    pdf.bullet("Chat messages sent")
    pdf.bullet("File uploads and downloads")
    pdf.bullet("Settings changes")
    pdf.bullet("Administrative actions")
    pdf.body_text(
        "Each log entry includes a timestamp, the user's IP address, "
        "action type, and a description. Administrators can view, search, "
        "and filter the activity log from the admin panel."
    )

    pdf.section_title("Network Security")
    pdf.body_text(
        "ULF Web is designed to run on a private network. All AI processing "
        "happens locally \u2014 no data is transmitted to external services. "
        "For production deployments, consider:"
    )
    pdf.bullet("Running behind a reverse proxy (e.g., nginx) with HTTPS")
    pdf.bullet("Restricting network access to trusted clients")
    pdf.bullet("Regularly backing up the database and encryption key")
    pdf.bullet("Keeping the system and dependencies up to date")

    # Chapter 8: Monitoring & Analytics
    pdf.chapter_title(8, "Monitoring & Analytics")

    pdf.section_title("Admin Panel Header")
    pdf.body_text(
        "The admin panel header provides quick access to monitoring tools "
        "via dedicated buttons:"
    )

    pdf.subsection_title("Usage Statistics")
    pdf.body_text(
        "Click the Usage button to view aggregate statistics including "
        "the number of conversations, messages, and files per user. "
        "This helps track system utilization."
    )

    pdf.subsection_title("System Info")
    pdf.body_text(
        "Click the System Info button to view hardware utilization:"
    )
    pdf.bullet("Total and available RAM")
    pdf.bullet("GPU VRAM usage (if available)")
    pdf.bullet("Per-model memory breakdown showing which models are loaded "
               "and how much memory each consumes")
    pdf.bullet("Memory mode indicators (VRAM only, RAM only, or hybrid)")

    pdf.subsection_title("File Info")
    pdf.body_text(
        "Click the System Files button to view information about project "
        "files and model files, including sizes, modification dates, and "
        "age indicators. Useful for verifying deployments and tracking "
        "model updates."
    )

    pdf.subsection_title("Activity Log")
    pdf.body_text(
        "Click the User Logs button to view the activity log. Features:"
    )
    pdf.bullet("Filterable by action type (dropdown of distinct types)")
    pdf.bullet("Filterable by IP address")
    pdf.bullet("Searchable by description text")
    pdf.bullet("Paginated for large log volumes")
    pdf.bullet("Shows timestamp, user, IP, action, and description")

    pdf.section_title("Server Health")
    pdf.body_text(
        "Each server in the Servers section shows a status indicator. "
        "Monitor these indicators to ensure all required servers are "
        "running. Check server logs when status shows an error."
    )

    # Chapter 9: Maintenance & Troubleshooting
    pdf.chapter_title(9, "Maintenance & Troubleshooting")

    pdf.section_title("Restarting ULF Web")
    pdf.body_text(
        "Click the Restart ULF Web button in the admin panel header to "
        "trigger a graceful application restart. This reloads the Python "
        "backend via uvicorn. Running llama.cpp server processes are "
        "cleaned up during shutdown."
    )

    pdf.section_title("Starting the Application")
    pdf.body_text("To start ULF Web from the command line:")
    pdf.body_text("    source .venv/bin/activate")
    pdf.body_text("    python3 -m backend.main")
    pdf.body_text(
        "The server listens on the configured host and port (default: "
        "http://0.0.0.0:8000). If the port is already in use:"
    )
    pdf.body_text("    pkill -f \"python.*backend.main\"")

    pdf.section_title("Database Management")
    pdf.body_text(
        "The SQLite database is stored at the configured path (default: "
        "data/ulfweb.db). Schema migrations are applied automatically on "
        "startup. To back up the database:"
    )
    pdf.bullet("Stop the application")
    pdf.bullet("Copy data/ulfweb.db and data/encryption.key to a secure location")
    pdf.bullet("Restart the application")

    pdf.note_box(
        "If encryption is enabled, backing up the database alone is not "
        "sufficient. You must also back up the encryption key file."
    )

    pdf.section_title("Common Issues")

    pdf.subsection_title("Server Fails to Start")
    pdf.bullet("Check the server log for error messages")
    pdf.bullet("Verify the model file path is correct and the file exists")
    pdf.bullet("Ensure sufficient RAM/VRAM for the model and context size")
    pdf.bullet("Check for port conflicts with other services")
    pdf.bullet("Verify the llama-server executable path in config.yaml")

    pdf.subsection_title("Slow Responses")
    pdf.bullet("Check System Info for memory pressure")
    pdf.bullet("Reduce context size or parallel slots")
    pdf.bullet("Use a smaller model for non-critical tasks (translation, extraction)")
    pdf.bullet("Ensure the model fits in GPU VRAM for optimal speed")

    pdf.subsection_title("Document Processing Fails")
    pdf.bullet("Ensure Document AI servers are configured and running")
    pdf.bullet("Check that the uploaded file is a valid PDF or DOCX")
    pdf.bullet("Review server logs for error details")
    pdf.bullet("Verify the server has sufficient context size for extraction")

    pdf.subsection_title("Dictation Not Working")
    pdf.bullet("Verify the Whisper model is configured in admin settings")
    pdf.bullet("Check that the browser has microphone permissions")
    pdf.bullet("Ensure sufficient RAM for the chosen Whisper model")
    pdf.bullet("Try a smaller Whisper model (e.g., base or small) first")

    pdf.subsection_title("Encryption Key Lost")
    pdf.body_text(
        "If the encryption key is lost and no backup exists, the encrypted "
        "database cannot be recovered. You will need to:"
    )
    pdf.bullet("Delete the encrypted database file")
    pdf.bullet("Start ULF Web fresh (a new database and key will be created)")
    pdf.bullet("Immediately back up the new encryption key")

    pdf.section_title("Data Directories")
    pdf.body_text("ULF Web stores data in the following default locations:")
    pdf.bold_bullet("data/ulfweb.db", "Main application database")
    pdf.bold_bullet("data/encryption.key", "Database and file encryption key")
    pdf.bold_bullet("data/vault/", "Encrypted vault files (documents, images)")
    pdf.bold_bullet("data/uploads/", "Document collection files")
    pdf.bold_bullet("data/logs/", "Server process log files")

    pdf.section_title("Log Files")
    pdf.body_text(
        "llama.cpp server logs are stored in data/logs/ and can be viewed "
        "from the admin panel. Application logs are output to the console "
        "(stdout/stderr) by the uvicorn server."
    )

    output_path = os.path.join(OUTPUT_DIR, "UlfWeb_Admin_Manual.pdf")
    pdf.output(output_path)
    print(f"Admin Manual saved to: {output_path}")


# ---------------------------------------------------------------------------
# Vault Tutorial
# ---------------------------------------------------------------------------
def generate_vault_tutorial():
    pdf = ManualPDF("ULF Web Vault Tutorial", "Vault Tutorial")
    pdf.cover_page()

    toc = [
        (1, "Introduction"),
        (2, "Navigating to the Vault"),
        (3, "Creating a Case"),
        (4, "The Case Detail View"),
        (5, "Adding Records"),
        (6, "Working with Records"),
        (7, "Exporting Cases"),
        (8, "Using Vault Cases in Chat"),
    ]
    pdf.toc_page(toc)

    # Chapter 1: Introduction
    pdf.chapter_title(1, "Introduction")
    pdf.body_text(
        "The Vault is ULF Web\u2019s built-in case management system. It lets you "
        "organize information into cases, each containing text notes, documents, "
        "and images. The AI automatically generates descriptions and summaries "
        "to help you work with your data."
    )
    pdf.body_text(
        "In this tutorial you will learn how to:"
    )
    pdf.bullet("Navigate to the Vault and search for cases")
    pdf.bullet("Create a new case with an identifier and description")
    pdf.bullet("View and manage case details")
    pdf.bullet("Add text, document, and image records to a case")
    pdf.bullet("Star important records and manage record lifecycle")
    pdf.bullet("Export cases as PDF or JSON")
    pdf.bullet("Reference vault cases in chat conversations using @mentions")
    pdf.note_box(
        "This tutorial assumes you are already logged in to ULF Web. "
        "If you need help logging in, see the User Manual."
    )

    # Chapter 2: Navigating to the Vault
    pdf.chapter_title(2, "Navigating to the Vault")
    pdf.body_text(
        "The Vault is one of the five main tools in ULF Web, accessible from "
        "the sidebar navigation tabs. Click the Vault tab to switch to the "
        "Vault panel."
    )
    _embed_screenshot(pdf, "01-vault-tab.png",
                      "Figure 1 \u2014 The Vault panel after clicking the Vault tab")
    pdf.body_text(
        "The Vault panel displays your list of cases. At the top you will find "
        "a search bar that filters cases in real time as you type. Below it is "
        "the New Case button for creating new cases."
    )
    pdf.body_text(
        "Cases you own (created by you) and public cases created by other "
        "users are both shown in the list. Private cases are only visible "
        "to their owner."
    )

    # Chapter 3: Creating a Case
    pdf.chapter_title(3, "Creating a Case")
    pdf.body_text(
        "To create a new case, click the New Case button. A form will appear "
        "with the following fields:"
    )
    pdf.bold_bullet("Identifier", "A short, unique code for the case (e.g., "
                    "CASE-001, INV-2026-042). This is used as a reference label.")
    pdf.bold_bullet("Name", "A descriptive name for the case (e.g., "
                    "\u201cSmith Investigation\u201d).")
    pdf.bold_bullet("Description", "Optional free-text description providing "
                    "background or context for the case.")
    pdf.bold_bullet("Visibility", "Choose Public (visible to all users) or "
                    "Private (visible only to you).")

    _embed_screenshot(pdf, "02-new-case-form.png",
                      "Figure 2 \u2014 The new case form with fields filled in")

    pdf.body_text(
        "Click Create to submit the form. The new case appears immediately "
        "in the case list."
    )
    _embed_screenshot(pdf, "03-case-list.png",
                      "Figure 3 \u2014 The case list showing the newly created case")

    # Chapter 4: The Case Detail View
    pdf.chapter_title(4, "The Case Detail View")
    pdf.body_text(
        "Click on a case in the list to open its detail view. The detail "
        "view shows:"
    )
    pdf.bullet("The case identifier, name, and status at the top")
    pdf.bullet("An AI-generated summary (updated automatically as records are added)")
    pdf.bullet("Action buttons for adding records, exporting, and managing the case")
    pdf.bullet("A chronological list of all records in the case")

    _embed_screenshot(pdf, "04-case-detail.png",
                      "Figure 4 \u2014 The case detail view")

    pdf.body_text(
        "The case status can be Active, Closed, or Archived. Active cases "
        "are open for editing. Closed cases are preserved for reference. "
        "Archived cases are stored long-term."
    )

    # Chapter 5: Adding Records
    pdf.chapter_title(5, "Adding Records")
    pdf.body_text(
        "Records are the individual pieces of information stored in a case. "
        "ULF Web supports three types of records:"
    )
    pdf.bold_bullet("Text", "Free-form text notes with a title, date, and content. "
                    "Ideal for interview notes, observations, or summaries.")
    pdf.bold_bullet("Document", "PDF files uploaded to the case. The AI automatically "
                    "generates a summary of the document content.")
    pdf.bold_bullet("Image", "Image files (JPEG, PNG). If a vision-capable model is "
                    "configured, the AI automatically generates a description.")

    pdf.section_title("Adding a Text Record")
    pdf.body_text(
        "Click the Add Record button to open the record form. Select the "
        "record type (Text is the default), then fill in the title and content."
    )
    _embed_screenshot(pdf, "05-add-text-record.png",
                      "Figure 5 \u2014 The add record form with a text record")

    pdf.body_text(
        "Click Submit to save the record. It appears in the record list "
        "below the case details. You can add as many records as needed."
    )
    _embed_screenshot(pdf, "06-records-populated.png",
                      "Figure 6 \u2014 The case with two text records")

    pdf.section_title("Uploading Documents and Images")
    pdf.body_text(
        "To upload a document or image, change the record type dropdown to "
        "Document or Image. A file upload area appears where you can click "
        "to browse or drag-and-drop a file. The AI will process the file "
        "in the background after upload."
    )

    # Chapter 6: Working with Records
    pdf.chapter_title(6, "Working with Records")

    pdf.section_title("Starring Records")
    pdf.body_text(
        "Click the star icon on any record to mark it as important. Starred "
        "records are visually highlighted, making them easy to spot in long "
        "case files. Click the star again to remove the highlight."
    )
    _embed_screenshot(pdf, "07-starred-record.png",
                      "Figure 7 \u2014 A starred record highlighted in the list")

    pdf.section_title("Editing Records")
    pdf.body_text(
        "Text records can be edited within 24 hours of creation. Click the "
        "edit button on a record to modify its title or content. After 24 "
        "hours, records are locked to preserve the integrity of the case "
        "history."
    )

    pdf.section_title("Deleting Records")
    pdf.body_text(
        "Click the delete button on a record to permanently remove it from "
        "the case. You will be asked to confirm before the record is deleted. "
        "The AI case summary is automatically updated after deletion."
    )

    # Chapter 7: Exporting Cases
    pdf.chapter_title(7, "Exporting Cases")
    pdf.body_text(
        "ULF Web provides two export formats for sharing or archiving cases. "
        "Click the Export button in the case detail view to see the options."
    )
    _embed_screenshot(pdf, "08-export-menu.png",
                      "Figure 8 \u2014 The export dropdown menu")

    pdf.section_title("PDF Export")
    pdf.body_text(
        "Generates a formatted PDF document containing the full case: "
        "metadata, description, AI summary, and all records with any "
        "embedded images and documents. Ideal for sharing with colleagues "
        "or printing."
    )

    pdf.section_title("JSON Export")
    pdf.body_text(
        "Exports the case data as a structured JSON file containing all "
        "text content, metadata, timestamps, and record details. Useful "
        "for backups, data migration, or programmatic analysis."
    )

    # Chapter 8: Using Vault Cases in Chat
    pdf.chapter_title(8, "Using Vault Cases in Chat")
    pdf.body_text(
        "One of the most powerful features of the Vault is the ability to "
        "reference cases directly in chat conversations. This injects the "
        "case\u2019s recent records as context, allowing the AI to answer "
        "questions about your case data."
    )

    pdf.section_title("The @Mention Syntax")
    pdf.body_text(
        "In the chat input, type the @ symbol followed by part of the case "
        "name or identifier. An autocomplete dropdown appears showing "
        "matching cases."
    )
    _embed_screenshot(pdf, "09-chat-at-mention.png",
                      "Figure 9 \u2014 The @mention autocomplete dropdown")

    pdf.body_text(
        "Click on a case in the dropdown (or use the arrow keys and Enter) "
        "to insert the @mention into your message."
    )
    _embed_screenshot(pdf, "10-chat-with-mention.png",
                      "Figure 10 \u2014 A completed @mention in the chat input")

    pdf.section_title("How Context Injection Works")
    pdf.body_text(
        "When you send a message containing one or more @mentions, ULF Web "
        "retrieves the recent records from each referenced case and includes "
        "them as context in the conversation. The AI can then reason about "
        "the case data alongside your question."
    )
    pdf.body_text(
        "The number of records included is controlled by the administrator "
        "in the Vault settings (default: 10 most recent records). Starred "
        "records are always prioritized."
    )

    pdf.section_title("Example Use Cases")
    pdf.bullet("\"@Smith Investigation \u2014 Summarize the key findings so far\"")
    pdf.bullet("\"Based on @CASE-001, are there any contradictions in the witness statements?\"")
    pdf.bullet("\"Compare the timelines in @CASE-001 and @CASE-002\"")

    pdf.note_box(
        "You can reference multiple cases in a single message. Each case\u2019s "
        "records are injected separately, allowing the AI to cross-reference "
        "information across cases."
    )

    output_path = os.path.join(OUTPUT_DIR, "UlfWeb_Vault_Tutorial.pdf")
    pdf.output(output_path)
    print(f"Vault Tutorial saved to: {output_path}")


if __name__ == "__main__":
    generate_user_manual()
    generate_admin_manual()
    generate_vault_tutorial()
    print("Done! All manuals generated.")
