from langchain_openai import ChatOpenAI
import os
from dotenv import load_dotenv

load_dotenv()
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

# temp = 0 for completely deterministic results
llm = ChatOpenAI(model="gpt-4o", temperature=0, api_key = OPENAI_API_KEY) 