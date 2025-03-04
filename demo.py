import json
import os
from typing import List, Optional

import google.generativeai as genai
from flask import Flask, render_template, request
from langchain.chains import LLMChain
from langchain.output_parsers import PydanticOutputParser
from langchain.prompts import PromptTemplate
from langchain_community.llms import VertexAI
from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import BaseModel

app = Flask(__name__)
app.config["UPLOAD_FOLDER"] = "uploads"
app.config["SUBMISSIONS_FOLDER"] = "submissions"

if not os.path.exists(app.config["UPLOAD_FOLDER"]):
    os.makedirs(app.config["UPLOAD_FOLDER"])
if not os.path.exists(app.config["SUBMISSIONS_FOLDER"]):
    os.makedirs(app.config["SUBMISSIONS_FOLDER"])

# Configure Generative AI
genai.configure(
    api_key=os.getenv("AIzaSyBAYNZ3ty4PU3bRFsg5twQpGEaYypcxWFU")
)  # Use environment variable for API key


# Define Pydantic models for structured output
class Persona(BaseModel):
    name: str
    age: str
    gender: str
    location: str
    occupation: str
    income: str
    education: str
    personality: List[str]
    background: str
    interests: List[str]
    communication_style: List[str]
    core_values: Optional[str] = None
    knowledge_domain: List[str]


class PersonasOutput(BaseModel):
    personas: List[Persona]


# LangChain chains for persona generation
persona_prompt_template = """
You are tasked with creating {num_personas} unique fictional AI personas based on the following brief:
{brief}

Each persona must include these fields:
- name (string)
- age (string)
- gender (string)
- location (string)
- occupation (string)
- income (string)
- education (string)
- personality (list of strings)
- background (string)
- interests (list of strings)
- communication_style (list of strings)
- core_values (string, optional)
- knowledge_domain (list of strings)


Return your output **only** as a valid JSON object without additional explanation or formatting.

JSON Output Format:
```json
{{
  "personas": [
    {{
      "name": "Example Name",
      "age": "Example Age",
      "gender": "Example Gender",
      "location": "Example Location",
      "occupation": "Example Occupation",
      "income": "Example Income",
      "education": "Example Education",
      "personality": ["Trait1", "Trait2"],
      "background": "Example Background",
      "interests": ["Interest1", "Interest2"],
      "communication_style": ["Style1", "Style2"],
      "core_values": "Example Core Values",
      "knowledge_domain": ["Domain1", "Domain2"]
    }}
  ]
}}
```
Ensure that the response strictly follows this format

"""

persona_prompt = PromptTemplate(
    input_variables=["num_personas", "brief"], template=persona_prompt_template
)

persona_parser = PydanticOutputParser(pydantic_object=PersonasOutput)


def generate_personas_chain(num_personas: int, brief: str) -> PersonasOutput:
    llm = ChatGoogleGenerativeAI(
        model="gemini-2.0-flash",
        temperature=1,
        api_key="AIzaSyBAYNZ3ty4PU3bRFsg5twQpGEaYypcxWFU",
    )  # Use a valid model name
    chain = LLMChain(llm=llm, prompt=persona_prompt, output_parser=persona_parser)
    breakpoint()

    result = chain.invoke({"num_personas": num_personas, "brief": brief})
    parsed_result = persona_parser.parse(result["text"])  # Parse the output
    return parsed_result


# LangChain chain for research brief generation
research_brief_template = """
You are a research brief generator. Based on the prompt provided below, generate a detailed research brief that includes these sections with numbered headings:
1. Title
2. Objective
3. Background
4. What We Know
5. Methodology
6. Target Audience
7. Deliverables

Prompt: {prompt}

Return only the plain text brief.
"""

research_brief_prompt = PromptTemplate(
    input_variables=["prompt"], template=research_brief_template
)


def generate_research_brief(prompt_text: str) -> str:
    llm = VertexAI(temperature=1, model_name="text-bison")  # Use a valid model name
    chain = LLMChain(llm=llm, prompt=research_brief_prompt)
    brief = chain.run(prompt=prompt_text)
    return brief


# Flask endpoints
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/create-personas", methods=["GET", "POST"])
def create_personas():
    if request.method == "POST":
        brief = request.form.get("brief")
        num_personas = int(request.form.get("num_personas", 5))
        if brief:
            try:
                personas_output = generate_personas_chain(num_personas, brief)
                personas_json = personas_output.json()
                print(f"Personas generated: {personas_json}")
            except Exception as e:
                personas_json = json.dumps(
                    {"error": "Failed to generate personas", "raw": str(e)}
                )
                print(f"Error: {e}")
            return render_template("create_personas.html", personas=personas_json)
    return render_template("create_personas.html", personas="")


@app.route("/brief-generator", methods=["GET", "POST"])
def brief_generator():
    generated_brief = None
    if request.method == "POST":
        short_prompt = request.form.get("short_prompt")
        if short_prompt:
            generated_brief = generate_research_brief(short_prompt)
    return render_template("brief_generator.html", generated_brief=generated_brief)


if __name__ == "__main__":
    app.run(use_reloader=True, host="0.0.0.0", port=8080)
