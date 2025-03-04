import json
import logging
import os
import re
import time
import uuid
from dataclasses import dataclass
from datetime import datetime
from functools import wraps
from typing import Dict, List

import google.generativeai as genai
import requests
from flask import (
    Flask,
    Response,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    stream_with_context,
    url_for,
)
from flask_babel import Babel
from flask_login import LoginManager, UserMixin, login_user, logout_user
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import Flow
from markdown import markdown  # Import the markdown conversion function
from werkzeug.utils import secure_filename

from pdf import create_pdf  # Add this import at the top
from prompts import validation_prompt

logger = logging.getLogger(__name__)

# In production, use the real login_required from flask_login
from flask_login import login_required as real_login_required


# Define a no-op decorator that simply returns the function unmodified.
def noop_decorator(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        return func(*args, **kwargs)

    return wrapper


# Choose which decorator to use based on an environment variable.
if os.environ.get("FLASK_ENV") == "development":
    login_required = noop_decorator
else:
    login_required = real_login_required


import os

os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"


app = Flask(__name__)
app.secret_key = "dsdsadsad32523523"  # Change this to a strong secret key
app.config["BABEL_DEFAULT_LOCALE"] = "en"
app.config["BABEL_TRANSLATION_DIRECTORIES"] = "translations"

# Development configuration
app.config.update(DEBUG=True, TEMPLATES_AUTO_RELOAD=True)
app.jinja_env.auto_reload = True


def get_locale():
    return request.args.get("lang") or session.get("lang", "en")


babel = Babel(app, locale_selector=get_locale)


@app.route("/set_language/<lang>")
def set_language(lang):
    session["lang"] = lang
    next_url = request.referrer or url_for("start")
    return redirect(next_url)


# Load Google OAuth credentials
GOOGLE_CLIENT_SECRETS_FILE = "client_secret_184123637715-i74v9b1ctb01m9n25eqejnmqe3d3i774.apps.googleusercontent.com.json"
SCOPES = ["https://www.googleapis.com/auth/userinfo.email", "openid"]

AUTHORIZED_DOMAINS = {"google.com"}
APPROVED_EMAILS = {"ugur@kriko.com.tr"}  # Pre-approved list

# Flask-Login setup
login_manager = LoginManager()
login_manager.init_app(app)

login_manager.login_view = "login"  # Redirects instead of returning 401
login_manager.login_message_category = "info"  # Optional: Flash message category


class User(UserMixin):
    def __init__(self, email):
        self.id = email
        self.email = email


@login_manager.user_loader
def load_user(email):
    return User(email)


@app.route("/login")
def login():
    flow = Flow.from_client_secrets_file(
        GOOGLE_CLIENT_SECRETS_FILE,
        scopes=SCOPES,
        redirect_uri=url_for("authorized", _external=True, _scheme="https"),
    )
    auth_url, _ = flow.authorization_url(prompt="consent")
    return redirect(auth_url)


@app.route("/login/callback")
def authorized():

    logging.warning(f"OAuth Callback URL: {request.url}")  # Logs full callback URL
    flow = Flow.from_client_secrets_file(
        GOOGLE_CLIENT_SECRETS_FILE,
        scopes=SCOPES,
        redirect_uri=url_for("authorized", _external=True, _scheme="https"),
    )

    flow.fetch_token(authorization_response=request.url)
    credentials = flow.credentials

    # Extract email from token
    from google.oauth2 import id_token

    token_info = id_token.verify_oauth2_token(credentials.id_token, Request())

    email = token_info.get("email")
    domain = email.split("@")[-1]

    # Restrict access based on domain or pre-approved list
    if domain not in AUTHORIZED_DOMAINS and email not in APPROVED_EMAILS:
        return "Unauthorized access", 403

    user = User(email)
    login_user(user)
    session["google_token"] = credentials.token
    return redirect(url_for("start"))


@app.route("/logout")
@login_required
def logout():
    logout_user()
    session.pop("google_token", None)
    return redirect(url_for("start"))


# Configure your API key
genai.configure(api_key="AIzaSyBAYNZ3ty4PU3bRFsg5twQpGEaYypcxWFU")


UPLOAD_FOLDER = "uploads"
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER


# Create a folder for storing submission files
SUBMISSIONS_FOLDER = "submissions"
if not os.path.exists(SUBMISSIONS_FOLDER):
    os.makedirs(SUBMISSIONS_FOLDER)


# Global dictionary to store submissions for asynchronous processing.
submissions = {}

# Add at the top with other global variables
chat_sessions = {}


# Add these new classes near the top with other models
@dataclass
class SurveyQuestion:
    text: str
    responses: Dict[str, int] = None  # yes/no counts

    def __init__(self, text):
        self.text = text
        self.responses = {"yes": 0, "no": 0}


@dataclass
class Survey:
    uid: str
    brief: str
    questions: List[SurveyQuestion]
    personas: List[dict]
    status: str = "pending"  # pending, in_progress, completed
    progress: int = 0
    total_personas: int = None  # Changed from hardcoded 100
    persona_responses: Dict[int, List[str]] = None

    def __init__(
        self,
        uid,
        brief,
        questions,
        personas,
        total_personas,
        status="pending",
        progress=0,
    ):
        self.uid = uid
        self.brief = brief
        self.questions = questions
        self.personas = personas
        self.status = status
        self.progress = progress
        self.total_personas = total_personas
        self.persona_responses = {}


# Add this with other global variables
active_surveys = {}

# Add with other folder definitions
SURVEYS_FOLDER = "surveys"
if not os.path.exists(SURVEYS_FOLDER):
    os.makedirs(SURVEYS_FOLDER)

# --- Helper Functions ---


def upload_to_gemini(path, mime_type=None):
    file = genai.upload_file(path, mime_type=mime_type)
    print(f"Uploaded file '{file.display_name}' as: {file.uri}")
    return file


def wait_for_files_active(files):
    """Waits for the given files to be active."""
    print("Waiting for file processing...")
    for name in (file.name for file in files):
        file = genai.get_file(name)
        while file.state.name == "PROCESSING":
            print(".", end="", flush=True)
            time.sleep(10)
            file = genai.get_file(name)
        if file.state.name != "ACTIVE":
            raise Exception(f"File {file.name} failed to process")
    print("...all files ready")


def get_language_instruction():
    language = get_locale()
    print(f"Language: {language}")

    language_instruction = "Output should be always in ENGLISH, even if the user selects another language.  Keep string keys in English., but values should be in ENGLISH."
    if language == "fr":
        language_instruction = "Output should be always in FRENCH, even if the user selects another language.  Keep string keys in English, but values should be in FRENCH."
    elif language == "de":
        language_instruction = "Output should be always in GERMAN, even if the user selects another language.  Keep string keys in English, but values should be in GERMAN."
    elif language == "tr":
        language_instruction = "Output should be always in TURKISH, even if the user selects another language.  Keep string keys in English, but values should be in TURKISH."

    return language_instruction


def generate_personas(brief, number_of_personas=5):

    numbers = [
        None,
        "one",
        "two",
        "three",
        "four",
        "five",
        "six",
        "seven",
        "eight",
        "nine",
        "ten",
        "eleven",
        "twelve",
        "thirteen",
        "fourteen",
        "fifteen",
        "sixteen",
        "seventeen",
        "eighteen",
        "nineteen",
        "twenty",
    ]

    language = get_locale()
    print(f"Language: {language}")

    system_instruction = f"""

Your task is to create {numbers[number_of_personas]}  unique fictional AI personas based on the following attributes:

1. **name** (string): The persona's name.
2. **age** (integer): The persona's age or age range. Do not use words like "20s", "30s", "40s", etc. Just use the actual age. Do not add any additional text.
3. **gender** (string): The persona's gender.
4. **location** (string): The persona's location.
5. **occupation** (string): The persona's occupation or industry.
6. **income** (string): The persona's income level.
7. **education** (string): The persona's education level.
8. **personality** (list of strings, multiple choice): Options include "Friendly", "Formal", "Humorous", "Sarcastic", "Analytical", etc. The user may select multiple.
9. **background** (string): A brief narrative about the persona's origins and experiences.
10. **interests** (list of strings): A comma-separated list of hobbies and interests.
11. **communication_style** (list of strings, multiple choice): Options include "Formal", "Informal", "Uses slang", "Concise", "Verbose", etc. The user may select multiple.
12. **core_values** (string, optional): The persona's core values or beliefs.
13. **knowledge_domain** (list of strings): Areas of expertise or knowledge.

### **Output Instructions:**
- Return exactly **{numbers[number_of_personas]} personas** in a well-structured JSON format.
- Do **not** include any additional text or explanations outside of the JSON structure.
- Ensure that the output can be directly parsed using `json.loads()` in Python.
- {get_language_instruction()}
    """

    generation_config = {
        "temperature": 1,
        "top_p": 0.95,
        "top_k": 40,
        "max_output_tokens": 8192,
        "response_mime_type": "text/plain",
    }
    model = genai.GenerativeModel(
        model_name="gemini-2.0-flash",
        generation_config=generation_config,
        system_instruction=system_instruction,
    )
    chat_session = model.start_chat()
    response = chat_session.send_message(
        f" Generate personas using this brief: {brief}"
    )
    personas_text = response.text
    print(personas_text)

    try:
        # Adjust slicing as needed to properly parse the JSON response.
        personas_dict = json.loads(personas_text[7:-3])

        # if interest field is not a list, make it a list
        try:
            for persona in personas_dict:
                if isinstance(persona["interests"], str):
                    persona["interests"] = persona["interests"].split(",")
        except Exception as e:
            print(f"Error: {e}")
            print(personas_dict)
    except Exception as e:

        personas_dict = {"error": "Failed to parse personas JSON", "raw": personas_text}
    return personas_dict


def simulate_focus_group_extended_gen(personas_dict, brief):

    language_instruction = get_language_instruction()
    persona_string = str(personas_dict)
    generation_config = {
        "temperature": 1,
        "top_p": 0.95,
        "top_k": 40,
        "max_output_tokens": 8192,
        "response_mime_type": "text/plain",
    }
    system_instruction = f"""
You are an experienced qualitative researcher and moderator, specializing in synthetic focus groups and in-depth interviews using AI-generated personas. Your responsibilities include reviewing the personas provided, moderating a focus group discussion using the brief below, and producing a written research report.

IMPORTANT: {language_instruction}

### **Output Instructions:**
- Return a formatted Markdown text.
- Do **not** include any additional text or explanations outside of the dialog.

Personas:
{persona_string}
    """
    model = genai.GenerativeModel(
        model_name="gemini-2.0-flash",
        generation_config=generation_config,
        system_instruction=system_instruction,
    )
    history = [{"role": "user", "parts": [brief]}]
    chat_session = model.start_chat(history=history)

    # --- Step 1: Moderate the Discussion ---
    yield {"step": "moderation", "message": "Moderating focus group discussion..."}
    response_outline = chat_session.send_message(
        "Please produce a detailed discussion outline of the focus group discussion. Include key themes, questions addressed, and topics covered. Only produce the outline."
    )
    outline = response_outline.text

    response_transcript = chat_session.send_message(
        "Now produce the full transcript of the focus group discussion."
    )

    full_transcript = response_transcript.text

    full_dialog = full_transcript

    yield {
        "step": "dialog",
        "data": full_dialog,
        "message": "Focus group discussion moderated.",
    }

    # --- Step 2: Generate Research Report Sections ---
    yield {"step": "report_generation", "message": "Generating research report..."}
    sections = {
        "Title": "Generate a study title for the research report.",
        "1. Introduction": "Write a brief introduction for the research report.",
        "1.1 Project Background": "Provide context and rationale for the study.",
        "1.2 Research Objectives": "Clearly state the research aims.",
        "1.3 Target Audience": "Define who the research is about.",
        "2. Methodology": '''Return the next paragraph verbatim. (For other languages than English, transate.) : "Qualitative Approach: This study utilized a qualitative approach to gain an in-depth understanding of user perceptions, motivations, and attitudes.
Synthetic Focus Group: A synthetic focus group methodology was chosen, using AI-generated personas to simulate a group discussion. This approach allowed for the exploration of complex issues within controlled parameters, using profiles based on the target audience.
AI-Generated Personas: Five distinct personas were created to represent the target audience
Discussion Guide: The discussion guide was designed to explore all facets of the research objectives."''',
        "3. Key Findings": "Summarize the key findings from the research.",
        "3.1 Key Finding 1": "State the first key finding concisely and provide 2-3 relevant quotes (verbatims).",
        "3.2 Key Finding 2": "State the second key finding concisely and provide 2-3 relevant quotes (verbatims).",
        "3.3 Key Finding 3": "State the third key finding concisely and provide 2-3 relevant quotes (verbatims).",
        "4. Discussion and Interpretation": "Discuss the significance of the findings.",
        "4.1 Insights": "Elaborate on the insights derived from the study.",
        "4.2 Implications": "Discuss the potential consequences and applications of the findings.",
        "5. Recommendations": "Provide specific and actionable recommendations based on the research.",
        "6. Conclusion": "Summarize the key takeaways and overall contribution of the research.",
        "7. Appendix": "Include any supplementary materials, such as interview guides",
    }
    report_sections = {}
    for section, prompt_message in sections.items():
        forbidden = "\nDo not start your answer with a section title. Start your answer directly with the content."
        response = chat_session.send_message(prompt_message + forbidden)
        report_sections[section] = response.text
        print(f"Section '{section}': {response.text}")
        if section == "Title":
            title = response.text
        yield {
            "step": "section_complete",
            "section": section,
            "data": response.text,
            "message": "Research report section completed.",
        }

    full_report = "\n\n".join(
        [f"{section}:\n{content}" for section, content in report_sections.items()]
    )
    # --- Final Update with All Key Variables ---
    yield {
        "step": "done",
        "final_report": full_report,
        "research_sections": report_sections,
        "dialog": full_dialog,
        "title": title,
    }


def validate_research(research_report, comparison_file_path):

    language_instruction = get_language_instruction()

    generation_config = {
        "temperature": 1,
        "top_p": 0.95,
        "top_k": 40,
        "max_output_tokens": 8192,
        "response_mime_type": "text/plain",
    }

    system_instruction = validation_prompt + language_instruction

    model = genai.GenerativeModel(
        model_name="gemini-2.0-flash",
        generation_config=generation_config,
        system_instruction=system_instruction,
    )

    chat_session = model.start_chat()

    yield {"step": "validation", "message": "Validating research..."}

    # Save the generated research report to a file
    generated_report_path = os.path.join("uploads", "research_report.txt")
    with open(generated_report_path, "w", encoding="utf-8") as f:
        f.write(research_report)
    print(f"research report written to {generated_report_path}")

    yield {"step": "preparing", "message": "Preparing files for validation..."}

    # Upload files to Gemini
    files = [
        upload_to_gemini(generated_report_path, mime_type="text/plain"),
        upload_to_gemini(comparison_file_path, mime_type="application/pdf"),
    ]
    wait_for_files_active(files)

    time.sleep(3)

    yield {"step": "uploaded", "message": "Files uploaded..."}

    chat_session = model.start_chat(
        history=[
            {
                "role": "user",
                "parts": [
                    files[0],
                    files[1],
                ],
            },
        ]
    )

    yield {"step": "validating", "message": "Validating research..."}

    response = chat_session.send_message(
        "Compare the two reports and give me a comparative analysis."
    )
    final_report = response.text

    response = chat_session.send_message(
        """
        - Give me the confidence scores for the two reports back in a JSON object.
        - Use the scores from the comparative analysis to give me the scores, do not make up new scores
        - Use report1_confidence and report2_confidence as the keys for the scores. Do not change the keys.

        Return your output as a valid JSON object (for example: {\"report1_confidence\": 0.9, \"report2_confidence\": 0.85}).
        """
    )

    try:
        scores = json.loads(response.text[7:-3])
    except Exception as e:
        scores = {"error": "Failed to parse scores JSON", "raw": response.text}

    yield {
        "step": "done",
        "message": "Validation complete.",
        "final_report": markdown(final_report, extensions=["tables"]),
        "scores": scores,
    }


def run_comparative_analysis(research_report, comparison_file_path):

    language_instruction = get_language_instruction()

    print(
        f"starting comparative analysis {research_report[0:100]} {comparison_file_path[0:100]}"
    )
    prompt = """
You are a validation research agent specializing in data quality for research reports. Treat all research reports equally, regardless of whether they are based on synthetic or real data. Your task is to perform a comparative analysis of the two attached research reports and evaluate their respective qualities, including a comparative confidence score. Focus on identifying and explaining discrepancies or inconsistencies between the two reports, regardless of which report presents which data type.

*Comparative Analysis Focus:*

Analyze the attached reports, paying close attention to the following areas to facilitate a comprehensive comparison:

* *Outcome Alignment:* How well do the conclusions and findings of each report align with each other? Identify areas of agreement, disagreement, and any significant differences in interpretation.
* *Key Factor Benchmarking:* Compare the data for the following factors across both reports: [List specific key factors]. Calculate the percentage difference or other relevant metric for comparison. Present these comparisons in a clear and concise manner, such as a table or chart.
* *Data Fidelity (where applicable):* How accurately does the data in each report represent the phenomena being studied? (Consider this in the context of the data source described in each report). Discuss the strengths and limitations of each data source and its potential impact on the reported findings.
* *Study Design Validity:* Assess the appropriateness and rigor of the study design described in each report. Compare and contrast the methodologies used, including sample selection, data collection methods, and statistical analyses.
* *Narrative and Argumentation:* Compare the way each report presents its findings. Are the arguments well-supported by the data? Are there any biases or limitations in the narrative presented?
* *Treat all research reports equally, regardless of whether they are based on synthetic or real data.
* *Your task is to perform a comparative analysis of the two attached research reports and evaluate their respective qualities, including a comparative confidence score.

*Report Requirements:*

Provide a detailed report summarizing your comparative analysis, including:

* A structured comparison of the key factors (e.g., using tables or charts).
* An assessment of the strengths and weaknesses of each report, considering its data, methodology, and narrative.
* A clear articulation of the key differences and similarities between the two reports.
* A confidence score for each report, indicating how reliably the information presented can be used, based on your comparative analysis. Justify your confidence scores.
* *Treat all research reports equally, regardless of whether they are based on synthetic or real data. Being synthetic is not automatically a negative thing.
* *Your task is to perform a comparative analysis of the two attached research reports and evaluate their respective qualities, including a comparative confidence score.
"""
    generation_config = {
        "temperature": 1,
        "top_p": 0.95,
        "top_k": 40,
        "max_output_tokens": 8192,
        "response_mime_type": "text/plain",
    }
    system_instruction = validation_prompt + language_instruction
    model = genai.GenerativeModel(
        model_name="gemini-2.0-flash",
        generation_config=generation_config,
        system_instruction=system_instruction,
    )
    # Save the generated research report to a file
    generated_report_path = os.path.join("uploads", "research_report.txt")
    with open(generated_report_path, "w", encoding="utf-8") as f:
        f.write(research_report)
    print(f"research report written to {generated_report_path}")
    # Upload both the user-provided file and the generated report
    files = [
        upload_to_gemini(comparison_file_path, mime_type="application/pdf"),
        upload_to_gemini(generated_report_path, mime_type="text/plain"),
    ]
    wait_for_files_active(files)

    # Pause briefly to ensure processing
    time.sleep(10)

    chat_session = model.start_chat(
        history=[
            {
                "role": "user",
                "parts": [
                    files[0],
                    files[1],
                ],
            },
        ]
    )

    time.sleep(1)
    response = chat_session.send_message(
        "Compare the two reports and give me a comparative analysis."
    )
    final_report = response.text

    response = chat_session.send_message("give me an executive summary of this report")
    executive_summary = response.text

    response = chat_session.send_message("give me key insights of this report")
    key_insights = response.text

    # Request scores in valid JSON format so they can be easily parsed
    response = chat_session.send_message(
        "Give me scores to use in the header of this report like a confidence report. I need 3 or 4 scores. "
        'Return your output as a valid JSON object (for example: {"overall_confidence": 0.9, "data_quality": 0.85, "alignment": 0.95}).'
    )
    print(response.text)
    try:
        scores = json.loads(response.text[7:-3])

    except Exception as e:
        scores = {"error": "Failed to parse scores JSON", "raw": response.text}

    other_data = {
        "executive_summary": executive_summary,
        "key_insights": key_insights,
        "scores": scores,
    }

    return final_report, other_data


# Add this helper function to generate a research brief based on a short prompt.
def generate_research_brief(short_prompt):

    print("ugur")

    language_instruction = get_language_instruction()

    system_instruction = f"""

IMPORTANT:    {language_instruction}

You are a research brief generator. Your task is to create a detailed research brief based on a short prompt describing a company or market scenario. The brief must include the following sections with numbered headings, and should be formatted for clarity and readability.  Specifically:

1. *Title:* A concise and descriptive title reflecting the research focus.

2. *Objective:*  A clear and specific statement of what the research aims to achieve.  This should be actionable and measurable where possible.  Consider what key questions the research needs to answer.

3. *Background:* A brief overview of the company, market, or situation that provides context for the research.  Include relevant history, current state, and key players.

4. *What We Know (Global/Current Insights):*  A summary of existing knowledge and insights relevant to the topic. This should include both general market trends and specific information about the company or scenario.  Cite sources if possible, but prioritize conciseness.

5 *Methodology:* Return the next paragraph verbatim.: "Qualitative Approach: This study utilized a qualitative approach to gain an in-depth understanding of user perceptions, motivations, and attitudes.
Synthetic Focus Group: A synthetic focus group methodology was chosen, using AI-generated personas to simulate a group discussion. This approach allowed for the exploration of complex issues within controlled parameters, using profiles based on the target audience.
AI-Generated Personas: Five distinct personas were created to represent the target audience
Discussion Guide: The discussion guide was designed to explore all facets of the research objectives."

6. 6. **Target Audience (Sample):*  For the purposes of this research brief generator, the target audience for every generated brief represents the sample for this research.  This sample should be the group of people we need to better understand to achieve the research objective, and upon which we will create user personas.  Assume this sample will be used for primary research (e.g., interviews, surveys).  Therefore, the brief should focus on defining the key characteristics of this sample.  Consider demographics, psychographics, behaviors, needs, motivations, and pain points relevant to the research objective.  Be as specific as possible about who this sample represents. For example: "Millennial urban dwellers aged 25-35 interested in sustainable fashion" or "Small business owners in the tech industry with annual revenue under $1 million."

7. *Deliverables:* Specify the expected outputs of the research. This could include reports, presentations, data visualizations, or other formats. Be specific about the content and format of each deliverable. For example: "A written report summarizing key findings and recommendations"

Return the brief as plain text only. Do not include any additional commentary, explanations, or formatting beyond the numbered headings. Focus on providing a well-structured, comprehensive, and actionable research brief that clearly defines the target audience (sample) for the researc

- {language_instruction}

    """
    generation_config = {
        "temperature": 1,
        "top_p": 0.95,
        "top_k": 40,
        "max_output_tokens": 2048,
        "response_mime_type": "text/plain",
    }
    model = genai.GenerativeModel(
        model_name="gemini-2.0-flash",
        generation_config=generation_config,
        system_instruction=system_instruction,
    )
    chat_session = model.start_chat()

    logger.info(f"Generating research brief for: {short_prompt}")

    if short_prompt.startswith("https"):

        url = short_prompt
        logger.debug(f"Fetching URL: {url}")
        response = requests.get(url)
        short_prompt = response.text

        # get only the content text
        short_prompt = re.sub(r"<.*?>", "", short_prompt)
        pre_prompt = "This is the webpage of the company. Please try to understand the company and market it operates in. Based on the information provided, generate a research brief.\n\n"

        short_prompt = pre_prompt + short_prompt

        logger.debug(f"Short prompt from URL: {short_prompt}")

    print(short_prompt)
    response = chat_session.send_message(
        f"Generate a research brief for: {short_prompt}"
    )
    return response.text


# Add this new endpoint to handle both displaying the form and returning the generated brief.
@app.route("/brief-generator", methods=["GET", "POST"])
@login_required
def brief_generator():
    generated_brief = None
    if request.method == "POST":
        short_prompt = request.form.get("short_prompt")
        if short_prompt:
            generated_brief = generate_research_brief(short_prompt)
    return render_template("brief_generator.html", generated_brief=generated_brief)


# --- Original Synchronous Routes ---


@app.route("/about", methods=["GET"])
def about_page():
    return render_template("about.html")


# --- New Asynchronous Endpoints ---


@app.route("/old", methods=["GET"])
def test_form():
    return render_template("new.html")


@app.route("/create-personas", methods=["GET", "POST"])
@login_required
def create_personas():
    personas = []
    if request.method == "POST":
        num_personas = int(request.form.get("num_personas", 5))

        # Check if brief is provided
        brief = request.form.get("brief")
        if brief:
            personas = generate_personas(brief, num_personas)

        # Check if file is provided
        elif "document" in request.files:
            file = request.files["document"]
            if file:
                # Save the uploaded file temporarily
                filename = secure_filename(file.filename)
                filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
                file.save(filepath)

                try:
                    # Generate personas from the document
                    personas = generate_personas_from_document(filepath, num_personas)
                finally:
                    # Clean up the temporary file
                    if os.path.exists(filepath):
                        os.remove(filepath)

    return render_template("create_personas.html", personas=personas)


@app.route("/async_results", methods=["POST"])
@login_required
def async_results():
    brief = request.form.get("brief")
    comparison_file = request.files.get("comparison_file")
    if not brief:
        return "Missing required brief.", 400

    filename = secure_filename(comparison_file.filename)

    comparison_file = request.files.get("comparison_file")

    if comparison_file:
        comparison_file_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
        comparison_file.save(comparison_file_path)
    else:
        comparison_file_path = None

    # Generate a unique ID for this submission.
    uid = str(uuid.uuid4())
    submissions[uid] = {
        "brief": brief,
        "comparison_file_path": comparison_file_path,
    }
    # Render the async_results template that will display progress. ss
    return render_template("async_results.html", uid=uid)


@app.route("/run_async/<uid>", methods=["GET"])
@login_required
def run_workflow_async(uid):
    if uid not in submissions:
        return "Submission not found", 404

    data = submissions[uid]
    brief = data["brief"]
    comparison_file_path = data["comparison_file_path"]
    # Initialize personas from submissions data, with empty list as default
    personas = data.get("personas", [])

    @stream_with_context
    def generate():

        nonlocal personas
        yield f"data: {json.dumps({'step': 'upload', 'message': 'Report generation started.'})}\n\n"

        # Step 1: Generate personas if none exist
        if not personas:
            personas = generate_personas(brief)

        yield f"data: {json.dumps({'step': 'personas', 'data': personas})}\n\n"

        # Step 2: Simulate focus group discussion
        # full_dialog, research_sections, research_report = simulate_focus_group_extended(personas, brief)
        # research_report_html = markdown(research_report)
        # full_dialog_html = markdown(full_dialog)
        # yield f"data: {json.dumps({'step': 'dialog', 'data': full_dialog_html})}\n\n"
        # yield f"data: {json.dumps({'step': 'research_report', 'data': research_report_html})}\n\n"
        # yield f"data: {json.dumps({'step': 'research_sections', 'data': research_sections})}\n\n"

        # Use the generator function to yield intermediate updates.
        final_update = None
        for update in simulate_focus_group_extended_gen(personas, brief):
            # Save the final update for later use if needed.
            if update.get("step") == "done":
                final_update = update
            yield f"data: {json.dumps(update)}\n\n"

        if comparison_file_path:
            # Step 3: Run comparative analysis
            final_report, other_data = run_comparative_analysis(
                final_update.get("final_report") if final_update else "",
                comparison_file_path,
            )
            final_report_html = markdown(final_report)
            yield f"data: {json.dumps({'step': 'final_report', 'data': final_report_html})}\n\n"
            yield f"data: {json.dumps({'step': 'done', 'message': 'Process completed.'})}\n\n"

        else:
            final_report = None
            final_report_html = None
            other_data = None
            yield f"data: {json.dumps({'step': 'done', 'message': 'Process completed.'})}\n\n"

        # Save the submission data to a file for later retrieval.
        submission_data = {
            "brief": brief,
            "personas": personas,
            "dialog": final_update.get("dialog") if final_update else "",
            "research_report": final_update.get("final_report") if final_update else "",
            "research_sections": (
                final_update.get("research_sections") if final_update else {}
            ),
            "title": final_update.get("title") if final_update else "",
            "final_report": final_report_html,
            "other_data": other_data,
        }
        submission_file = os.path.join(SUBMISSIONS_FOLDER, f"{uid}.json")
        with open(submission_file, "w", encoding="utf-8") as f:
            json.dump(submission_data, f, ensure_ascii=False, indent=2)

        submissions.pop(uid, None)

        # Send a redirect message to the client
        yield f"data: {json.dumps({'step': 'redirect', 'url': url_for('submission_view', submission_id=uid)})}\n\n"

    response = Response(generate(), mimetype="text/event-stream")
    response.headers["Cache-Control"] = "no-cache"
    response.headers["X-Accel-Buffering"] = "no"

    return response


# New endpoint to view submission details via URL "s/{id}"
@app.route("/s/<submission_id>", methods=["GET"])
@login_required
def submission_view(submission_id):
    file_path = os.path.join(SUBMISSIONS_FOLDER, f"{submission_id}.json")
    if not os.path.exists(file_path):
        return "Submission not found", 404

    with open(file_path, "r", encoding="utf-8") as f:
        submission_data = json.load(f)

    # Add submission ID to the data for the template // markdown conversion
    submission_data["id"] = submission_id

    submission_data["brief"] = markdown(
        submission_data["brief"], extensions=["tables", "fenced_code", "toc"]
    )

    submission_data["dialog"] = markdown(
        submission_data["dialog"], extensions=["tables", "fenced_code", "toc"]
    )

    for k, v in submission_data["research_sections"].items():
        submission_data["research_sections"][k] = markdown(
            v, extensions=["tables", "fenced_code", "toc"]
        )
        if k == "Title":
            submission_data["title"] = v

    if submission_data.get("final_report"):
        submission_data["final_report"] = markdown(
            submission_data["final_report"], extensions=["tables", "fenced_code", "toc"]
        )

    return render_template("submission_view.html", submission_data=submission_data)


@app.route("/download/<submission_id>")
@login_required
def download_pdf(submission_id):
    file_path = os.path.join(SUBMISSIONS_FOLDER, f"{submission_id}.json")
    if not os.path.exists(file_path):
        return "Submission not found", 404

    with open(file_path, "r", encoding="utf-8") as f:
        submission_data = json.load(f)

    # Add submission ID to the data for the template
    submission_data["id"] = submission_id

    # Generate PDF
    pdf_buffer = create_pdf(submission_data)

    # Send file
    return Response(
        pdf_buffer,
        mimetype="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename=synthetic_report_{submission_id[:8]}.pdf"
        },
    )


@app.route("/")
def start():
    return render_template("start.html")


@app.route("/brief", methods=["GET"])
@login_required
def brief_step():
    return render_template("brief_step.html")


@app.route("/generate-brief", methods=["POST"])
def generate_brief_endpoint():
    data = request.get_json()
    brief = generate_research_brief(data["prompt"])
    return jsonify({"brief": brief})


@app.route("/personas", methods=["POST"])
@login_required
def personas_step():
    brief = request.form.get("brief")
    comparison_file = request.files.get("comparison_file")

    # Handle file upload if provided
    comparison_file_path = None
    if comparison_file:
        filename = secure_filename(comparison_file.filename)
        comparison_file_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
        comparison_file.save(comparison_file_path)

    # Generate initial personas
    personas = generate_personas(brief)

    # If personas are an object, personas array is under the key "personas"
    if isinstance(personas, dict):
        personas = personas.get("personas", [])

    return render_template(
        "personas_step.html",
        personas=personas,
        brief=brief,
        comparison_file_path=comparison_file_path,
    )


# Update the existing run_async route to handle the new flow
@app.route("/run_async", methods=["POST"])
@login_required
def run_async():
    brief = request.form.get("brief")
    personas_json = request.form.get("personas")
    comparison_file_path = request.form.get("comparison_file_path")

    # Safely parse personas JSON, defaulting to empty list if invalid
    try:
        personas = json.loads(personas_json) if personas_json else []
    except (json.JSONDecodeError, TypeError):
        personas = []

    # Generate unique ID and store submission data
    uid = str(uuid.uuid4())
    submissions[uid] = {
        "brief": brief,
        "personas": personas,
        "comparison_file_path": comparison_file_path,
    }

    return render_template("async_results.html", uid=uid)


@app.route("/generate-persona", methods=["POST"])
@login_required
def generate_persona():
    data = request.get_json()
    brief = data["brief"]
    existing_personas = data["existing_personas"]

    # Add context about existing personas to avoid duplicates
    context = f"""
    Brief: {brief}

    Existing Personas: {json.dumps(existing_personas, indent=2)}

    Generate a new unique persona that is different from the existing ones but still relevant to the brief.
    The persona should have different personality traits, background, and interests while still being appropriate for the research context.
    """

    # Generate a single new persona

    new_persona = generate_personas(context, number_of_personas=1)

    return jsonify(new_persona)


@app.route("/start-chat-session", methods=["POST"])
@login_required
def start_chat_session():
    data = request.get_json()
    persona = data["persona"]
    dialog = data["dialog"]

    session_id = str(uuid.uuid4())

    system_prompt = f"""You are roleplaying as a research participant with the following characteristics:

Name: {persona['name']}
Personality: {', '.join(persona['personality'])}
Background: {persona['background']}
Interests: {', '.join(persona['interests'])}
Communication Style: {', '.join(persona['communication_style'])}
Core Values: {persona['core_values']}
Knowledge Domain: {', '.join(persona['knowledge_domain'])}

You participated in a focus group discussion about the following:
{dialog}

Stay in character and respond as this persona would, maintaining their personality traits, communication style, and knowledge level. Use their background and interests to inform your responses.
"""

    generation_config = {
        "temperature": 0.9,
        "top_p": 0.95,
        "top_k": 40,
        "max_output_tokens": 1024,
    }

    model = genai.GenerativeModel(
        model_name="gemini-2.0-flash",
        generation_config=generation_config,
        system_instruction=system_prompt,
    )

    chat = model.start_chat()
    chat_sessions[session_id] = chat

    return jsonify(
        {
            "session_id": session_id,
            "welcome_message": f"Hello! I am {persona['name']}. {persona['background']} How can I help you today?",
        }
    )


@app.route("/chat-message/<session_id>", methods=["POST"])
@login_required
def chat_message(session_id):
    if session_id not in chat_sessions:
        return jsonify({"error": "Chat session not found"}), 404

    data = request.get_json()
    message = data["message"]

    chat = chat_sessions[session_id]
    response = chat.send_message(message)

    return jsonify({"response": response.text})


@app.route("/compare_reports", methods=["POST"])
@login_required
def compare_reports_async():
    submission_id = request.form.get("submission_id")
    report_file = request.files.get("report")

    # Save the uploaded file temporarily
    filename = secure_filename(report_file.filename)
    report_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
    report_file.save(report_path)

    # Load the submission data
    comparison_data = load_submission_data(submission_id)
    research_report = comparison_data["research_report"]

    @stream_with_context
    def generate():
        try:
            for step in validate_research(research_report, report_path):
                # Format the message as a Server-Sent Event
                sse_message = "data: " + json.dumps(step) + "\n\n"
                yield sse_message.encode("utf-8")
        except Exception as e:
            error_message = (
                "data: " + json.dumps({"step": "error", "message": str(e)}) + "\n\n"
            )
            yield error_message.encode("utf-8")
        finally:
            if os.path.exists(report_path):
                os.remove(report_path)

    response = Response(generate(), mimetype="text/event-stream")
    response.headers["Cache-Control"] = "no-cache"
    response.headers["X-Accel-Buffering"] = "no"
    return response


# Add cleanup for old sessions (optional)
def cleanup_old_sessions():
    # Implement session cleanup logic here
    pass


@app.route("/all")
@login_required
def list_submissions():
    submissions_list = []
    for filename in os.listdir(SUBMISSIONS_FOLDER):
        if filename.endswith(".json"):
            submission_id = filename[:-5]  # Remove .json extension
            file_path = os.path.join(SUBMISSIONS_FOLDER, filename)

            # Get creation time of the file
            creation_time = os.path.getctime(file_path)
            creation_datetime = datetime.fromtimestamp(creation_time)

            # Extract key information
            submissions_list.append(
                {
                    "id": submission_id,
                    "created_at": creation_datetime,
                }
            )

    # Sort by creation time, newest first
    submissions_list.sort(key=lambda x: x["created_at"], reverse=True)

    return render_template("submissions_list.html", submissions=submissions_list)


def generate_personas_from_document(file_path, number_of_personas=5):
    """Generate personas from an uploaded document using Gemini"""
    system_instruction = f"""
You are an expert at analyzing documents and extracting information to create realistic personas. Your task is to:

1. Analyze the provided document content
2. Identify key characteristics, behaviors, and patterns that could inform persona creation. If the report is a survey, focus group, or interview, identify the key characteristics of the respondents
3. Generate {number_of_personas} unique personas that would be representative of the people described in, interviewed in, or targeted by the document.


For each persona, provide:
- name (string): A realistic name
- personality (list): Key personality traits
- background (string): Brief personal history
- interests (list): Hobbies and interests
- communication_style (list): How they communicate
- core_values (string): What they believe in
- knowledge_domain (list): Areas of expertise

Return the personas in valid JSON format that can be parsed by json.loads().
Do not include any additional text or explanations outside of the JSON structure.
"""

    generation_config = {
        "temperature": 1,
        "top_p": 0.95,
        "top_k": 40,
        "max_output_tokens": 8192,
    }

    model = genai.GenerativeModel(
        model_name="gemini-2.0-flash",
        generation_config=generation_config,
        system_instruction=system_instruction,
    )

    # Upload file to Gemini
    file = upload_to_gemini(file_path)
    wait_for_files_active([file])

    chat = model.start_chat()
    response = chat.send_message(
        f"Generate {number_of_personas} personas from the document supplied"
    )
    print(response.text)

    try:
        return json.loads(response.text)
    except json.JSONDecodeError:
        print("JSON parsing failed")
        # If JSON parsing fails, try to extract JSON portion
        try:
            print("Trying to parse JSON from response")
            json_start = response.text.find("[")
            json_end = response.text.rfind("]") + 1
            return json.loads(response.text[json_start:json_end])
        except:
            print(response.text)
            return {"error": "Failed to parse personas from response"}


def load_submission_data(submission_id):
    file_path = os.path.join(SUBMISSIONS_FOLDER, f"{submission_id}.json")
    with open(file_path, "r", encoding="utf-8") as f:
        submission_data = json.load(f)
    return submission_data


if __name__ == "__main__":
    app.run(
        use_reloader=True,
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 8080)),
        extra_files=["template/*.html"],
    )
