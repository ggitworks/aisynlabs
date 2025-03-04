def simulate_focus_group(personas_dict, brief):
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

Personas:

{persona_string}
    """
    model = genai.GenerativeModel(
        model_name="gemini-2.0-flash",
        generation_config=generation_config,
        system_instruction=system_instruction,
    )
    history = [
        {
            "role": "user",
            "parts": [brief],
        }
    ]
    chat_session = model.start_chat(history=history)

    # Moderate the discussion and return full dialog
    response = chat_session.send_message(
        "Please review personas and brief, moderate focus group discussion based on questions with Turkish personas. Return all complete dialog between you and the personas."
    )
    full_dialog = response.text

    # Generate a research report based on the discussion
    r = chat_session.send_message(
        "create a full research report based on this discussion between the moderator and the personas"
    )
    research_report = r.text

    return full_dialog, research_report


def simulate_focus_group_extended(personas_dict, brief):
    """
    This extended function first generates the complete dialog between the moderator and focus group personas,
    then generates the qualitative research report section by section based on a predefined template.
    Returns:
      - full_dialog: The complete dialog from the focus group discussion.
      - report_sections: A dictionary where keys are section titles and values are the generated content.
      - full_report: A concatenated string of all sections for the complete report.
    """
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

Personas:

{persona_string}
    """
    model = genai.GenerativeModel(
        model_name="gemini-2.0-flash",
        generation_config=generation_config,
        system_instruction=system_instruction,
    )
    history = [
        {
            "role": "user",
            "parts": [brief],
        }
    ]
    chat_session = model.start_chat(history=history)
    # Moderate the discussion and return full dialog
    response = chat_session.send_message(
        "Please review personas and brief, moderate focus group discussion based on questions with Turkish personas. Return all complete dialog between you and the personas."
    )
    full_dialog = response.text

    system_instruction = f"""
You are an experienced qualitative researcher and moderator, specializing in synthetic focus groups and in-depth interviews using AI-generated personas. Your task is:
1. Generate a detailed qualitative research report following the template provided below, section by section. Dialog between AI-generated personas are at the end.

Template for Qualitative Research Reports

Title: [Study Title]

1. Introduction
1.1 Project Background: [Provide context and rationale for the study.]
1.2 Research Objectives: [Clearly state the research aims.]
1.3 Target Audience: [Define who the research is about.]

2. Methodology
[Describe the qualitative approach, sampling, and analysis methods used.]

3. Key Findings
3.1 Key Finding 1: [State the finding concisely.]
Verbatims: [Include 2-3 relevant quotes that illustrate the finding.]
3.2 Key Finding 2: [State the finding concisely.]
Verbatims: [Include 2-3 relevant quotes that illustrate the finding.]
3.3 Key Finding 3: [State the finding concisely.]
Verbatims: [Include 2-3 relevant quotes that illustrate the finding.]

4. Discussion and Interpretation
4.1 Insights: [Elaborate on the significance of the findings.]
4.2 Implications: [Discuss the potential consequences and applications of the findings.]

5. Recommendations
[Provide specific and actionable recommendations based on the research.]
[Prioritize recommendations based on their potential impact.]

7. Conclusion
[Summarize the key takeaways and the overall contribution of the research.]

8. Appendix
[Include any supplementary materials, such as interview guides or data tables.]

Personas provided:
{persona_string}

Dialog Between Personas:
{full_dialog}

Please generate a detailed report following the template above, section by section. 
Start your answers directly, without repeating section title back. 
Do not start your answer with a like "3. Key Findings:".
If a question is already answered, don't say "This is already addressed" etc, just return the answer.
    """
    model = genai.GenerativeModel(
        model_name="gemini-2.0-flash",
        generation_config=generation_config,
        system_instruction=system_instruction,
    )
    history = [
        {
            "role": "user",
            "parts": [brief],
        }
    ]
    chat_session = model.start_chat(history=history)

    # Now, generate the report sections one by one.
    sections = {
        "Title": "Generate a study title for the research report.",
        "1. Introduction": "Write a brief introduction for the research report.",
        "1.1 Project Background": "Provide context and rationale for the study.",
        "1.2 Research Objectives": "Clearly state the research aims.",
        "1.3 Target Audience": "Define who the research is about.",
        "2. Methodology": "Describe the overall methodology used in the research.",
        "3. Key Findings": "Summarize the key findings from the research.",
        "3.1 Key Finding 1": "State the first key finding concisely and provide 2-3 relevant quotes (verbatims).",
        "3.2 Key Finding 2": "State the second key finding concisely and provide 2-3 relevant quotes (verbatims).",
        "3.3 Key Finding 3": "State the third key finding concisely and provide 2-3 relevant quotes (verbatims).",
        "4. Discussion and Interpretation": "Discuss the significance of the findings.",
        "4.1 Insights": "Elaborate on the insights derived from the study.",
        "4.2 Implications": "Discuss the potential consequences and applications of the findings.",
        "5. Recommendations": "Provide specific and actionable recommendations based on the research.",
        "7. Conclusion": "Summarize the key takeaways and overall contribution of the research.",
        "8. Appendix": "Include any supplementary materials, such as interview guides",
    }
    report_sections = {}
    for section, section_prompt in sections.items():
        prompt_message = f"{section_prompt}"
        print(f"Section '{section}': {section_prompt}")
        forbidden = "\nDo not start your answer with a like '3. Key Findings:' or '3.3 Key Finding 3'. Start your answer directly with the content."
        response = chat_session.send_message(prompt_message + forbidden)
        report_sections[section] = response.text

    # Concatenate all sections to form the full report.
    full_report = ""
    for section, content in report_sections.items():
        full_report += f"{section}:\n{content}\n\n"

    return full_dialog, report_sections, full_report
