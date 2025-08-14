import asyncio
import os
import sys

from browser_use.llm import ChatOllama
from browser_use.browser import BrowserProfile

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv()


from browser_use import Agent

# Initialize the model with Ollama tuning for local GPT-OSS
llm = ChatOllama(
  model=os.getenv('BROWSER_USE_LLM_MODEL', 'gpt-oss:20b'),
  host=os.getenv('OLLAMA_HOST', 'http://localhost:11434'),
  # Keep the model loaded for faster successive calls
  keep_alive=os.getenv('OLLAMA_KEEP_ALIVE', '30m'),
  # Slightly higher request timeout to accommodate local generation
  timeout=float(os.getenv('OLLAMA_TIMEOUT', '180')),
  # Options passed through to Ollama
  options={
    # Larger context for long prompts; adjust to your model capability
    'num_ctx': int(os.getenv('OLLAMA_NUM_CTX', '8192')),
    # Deterministic, concise outputs
    'temperature': float(os.getenv('OLLAMA_TEMPERATURE', '0.2')),
    'top_p': float(os.getenv('OLLAMA_TOP_P', '0.9')),
    'repeat_penalty': float(os.getenv('OLLAMA_REPEAT_PENALTY', '1.1')),
    # Limit output tokens to avoid overlong thoughts
    'num_predict': int(os.getenv('OLLAMA_NUM_PREDICT', '768')),
  }
)


task = '''
Goal: Renew Sri Lankan National Identity Card (NIC) online for the applicant via the official Department for Registration of Persons (DRP) Sri Lanka website. Prefer the renewal/appointment flow. Use the provided data verbatim. If a field is missing or inconsistent, stop and summarize what is needed.

Applicant details (JSON):
{
  "serviceType": "new-id",
  "appointmentDate": "2025-08-13T05:30:00.000Z",
  "time": "11:00 AM",
  "address": {
    "value": "N 2, 2, WICKRAMASINGHA MAWATHA, MALKADUWAWA KURUNEGALA",
    "components": {
      "street": "SRI SARALANKARA MAWATHA",
      "city": "WELMILLA",
      "country": "Sri Lanka"
    }
  },
  "dob": {
    "value": "2003/08/04",
    "originalFormat": "5003/08/04",
    "possibleFormats": [
      "YYYY/MM/DD"
    ]
  },
  "document_type": {
    "value": "Sri Lankan National Identity Card",
    "indicators": [
      "SRILANKA NATIONAL IDENTITY CARD"
    ]
  },
  "gender": {
    "value": "Male"
  },
  "id_number": {
    "type": "NIC",
    "value": "200321710771"
  },
  "name": {
    "value": "ARSHA MARAKKALAGE RIVIDU PESARA LAKSHMAN"
  }
}

Success criteria:
- Book/renew NIC or secure an appointment as applicable.
- Save/copy the confirmation/reference number and download any receipt or confirmation.
- Save final output to a file named nic_renewal_result.txt describing the outcome and references.
'''
agent = Agent(
  task=task,
  llm=llm,
  # Extend LLM/step timeouts to handle slower local inference
  llm_timeout=int(os.getenv('BROWSER_USE_LLM_TIMEOUT', '180')),
  step_timeout=int(os.getenv('BROWSER_USE_STEP_TIMEOUT', '240')),
  # Keep outputs concise to avoid truncation
  use_thinking=False,
)


async def main():
	await agent.run()


if __name__ == '__main__':
	asyncio.run(main())
