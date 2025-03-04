from langchain.chains import LLMChain
from langchain.output_parsers import PydanticOutputParser
from langchain.prompts import PromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI

from prompts import persona_prompt_template
from sentetik.models import PersonasOutput


def generate_personas(num_personas: int, brief: str) -> PersonasOutput:
    llm = ChatGoogleGenerativeAI(
        model="gemini-2.0-flash",
        temperature=1,
        api_key="AIzaSyBAYNZ3ty4PU3bRFsg5twQpGEaYypcxWFU",
    )  # Use a valid model name

    persona_prompt = PromptTemplate(
        template=persona_prompt_template, input_variables=["num_personas", "brief"]
    )
    persona_parser = PydanticOutputParser(pydantic_object=PersonasOutput)
    chain = LLMChain(llm=llm, prompt=persona_prompt, output_parser=persona_parser)

    result = chain.invoke({"num_personas": num_personas, "brief": brief})

    parsed_result = result["text"].personas  # Parse the output
    return parsed_result
