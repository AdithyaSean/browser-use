import asyncio
import os
import sys

from browser_use.llm import ChatOllama

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv()


from browser_use import Agent

# Initialize the model
llm = ChatOllama(
model=os.getenv('BROWSER_USE_LLM_MODEL', 'gpt-oss:20b'),
host=os.getenv('OLLAMA_HOST', 'http://localhost:11434'),
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
agent = Agent(task=task, llm=llm)


async def main():
	await agent.run()


if __name__ == '__main__':
	asyncio.run(main())
