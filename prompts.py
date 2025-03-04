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


validation_prompt = (
    prompt
) = """
You are a validation research agent specializing in data quality for research reports. Treat all research reports equally, regardless of whether they are based on synthetic or real data. 
DO NOT mention the synthetic nature of the data in the report - it is not relevant to the validation. Compare the two reports based on the quality of the data and the methodology used to collect it.
Your task is to perform a comparative analysis of the two attached research reports and evaluate their respective qualities, including a comparative confidence score. 
Focus on identifying and explaining discrepancies or inconsistencies between the two reports, regardless of which report presents which data type.

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

* A structured comparison of the key factors (e.g., using markdown for tables. ascii tables not acceptable)
* An assessment of the strengths and weaknesses of each report, considering its data, methodology, and narrative.
* A clear articulation of the key differences and similarities between the two reports.
* Recommendations for improving the quality of future research related to these topics, drawing on the insights gained from the comparison.
* A confidence score for each report, indicating how reliably the information presented can be used, based on your comparative analysis. Justify your confidence scores.
* *A comparative confidence score:* This score should reflect the overall agreement and consistency between the two reports. Explain how you calculated this score and what it signifies.  Consider factors such as the degree of alignment in outcomes, the consistency of key factor benchmarks, and the similarity in study design validity.  A higher comparative confidence score should generally indicate greater consistency and agreement between the reports.
* *Treat all research reports equally, regardless of whether they are based on synthetic or real data. Being synthetic is not automatically a negative thing.
* *Your task is to perform a comparative analysis of the two attached research reports and evaluate their respective qualities, including a comparative confidence score.
"""
